"""Awaaz Live against fake Gnani streams; the real pipeline and database run underneath."""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import models
from app.api import live
from app.db import SessionLocal
from app.main import app
from app.providers.base import ProviderError
from app.services import live_call as lc


class FakeStream:
    """Plays Prisma: each `commit` from the browser delivers the next scripted phrase."""
    script: list[str] = []
    audio_received = bytearray()
    fail_to_connect = False

    def __init__(self, language):
        self.language = language
        self.queue: asyncio.Queue = asyncio.Queue()

    async def __aenter__(self):
        if FakeStream.fail_to_connect:
            raise ProviderError("could not connect to Prisma: OSError", transient=True)
        return self

    async def __aexit__(self, *_exc):
        return None

    async def send(self, pcm):
        FakeStream.audio_received += pcm

    async def commit(self):
        await self.queue.put({"type": "speech_start"})
        await self.queue.put({"type": "processing"})
        await self.queue.put({"type": "transcript", "text": FakeStream.script.pop(0), "latency": 457})

    async def events(self):
        while True:
            yield await self.queue.get()


spoken_requests: list[str] = []
timbre_fails = False


async def fake_speak(text, language):
    spoken_requests.append(text)
    if timbre_fails:
        raise ProviderError("Timbre: boom")
    yield b"\x01\x00" * 160
    yield b"\x02\x00" * 160


@pytest.fixture()
def call(client, monkeypatch):
    global timbre_fails
    timbre_fails = False
    spoken_requests.clear()
    lc.calls.clear()
    FakeStream.script = []
    FakeStream.audio_received = bytearray()
    FakeStream.fail_to_connect = False
    monkeypatch.setattr(live, "stream_factory", FakeStream)
    monkeypatch.setattr(live, "speak", fake_speak)
    monkeypatch.setattr(live, "SETTLE_S", 0.01)
    monkeypatch.setattr(live, "PLAYBACK_GRACE_S", 2.0)
    return client


def read_until(ws, *kinds):
    """Everything up to and including the first message of one of `kinds`, answering playback as a browser would."""
    seen = []
    while True:
        message = ws.receive()
        if message.get("bytes") is not None:
            seen.append({"type": "pcm", "size": len(message["bytes"])})
            continue
        if message.get("text") is None:
            raise AssertionError(f"socket closed before {kinds}; saw {seen}")
        body = json.loads(message["text"])
        seen.append(body)
        if body["type"] == "audio_end":
            ws.send_text(json.dumps({"type": "playback_done"}))
        if body["type"] in kinds:
            return seen


def until_listening(ws):
    seen = []
    while True:
        batch = read_until(ws, "state")
        seen += batch
        if batch[-1]["state"] == "listening":
            return seen


def say(ws, phrase):
    FakeStream.script.append(phrase)
    ws.send_text(json.dumps({"type": "commit"}))


def report_of(ws_seen):
    rid = next(m["report_id"] for m in ws_seen if m["type"] == "done")
    with SessionLocal() as db:
        return db.get(models.Report, rid)


def test_a_full_call_asks_only_for_what_is_missing_and_reads_it_back(call):
    with call.websocket_connect("/api/live/call") as ws:
        ws.send_text(json.dumps({"type": "start", "language": "en"}))
        greeting = until_listening(ws)
        assert any(m["type"] == "pcm" for m in greeting)
        assert "112" in next(m["text"] for m in greeting if m["type"] == "assistant")

        say(ws, "There is a flood and people are trapped")
        turn = until_listening(ws)
        assert next(m["text"] for m in turn if m["type"] == "caller") == "There is a flood and people are trapped"
        assert "Where are you calling from" in next(m["text"] for m in turn if m["type"] == "assistant")
        assert next(m for m in turn if m["type"] == "facts")["facts"]["disaster"] == "flood"

        say(ws, "Nandwadi")
        turn = until_listening(ws)
        assert next(m for m in turn if m["type"] == "facts")["facts"]["place"] == "Nandwadi"
        assert "How many people" in next(m["text"] for m in turn if m["type"] == "assistant")

        say(ws, "25")
        final = read_until(ws, "done")
    words = next(m["text"] for m in final if m["type"] == "assistant")
    assert "Nandwadi" in words and "flood" in words and "25" in words and "112" in words
    report = report_of(final)
    assert report.source == "live_call" and report.status == "processed" and report.transcript_source == "prisma_stream"
    assert report.follow_up_status == "answered"
    assert (report.extraction_current["people_affected"] or {})["count"] == 25


def test_audio_tags_reach_timbre_but_never_the_screen(call):
    with call.websocket_connect("/api/live/call") as ws:
        ws.send_text(json.dumps({"type": "start", "language": "en"}))
        greeting = until_listening(ws)
        ws.send_text(json.dumps({"type": "end"}))
        read_until(ws, "done")
    assert "<pauses>" in spoken_requests[0]
    assert "<" not in next(m["text"] for m in greeting if m["type"] == "assistant")


def test_microphone_is_ignored_while_the_assistant_speaks(call):
    with call.websocket_connect("/api/live/call") as ws:
        ws.send_text(json.dumps({"type": "start", "language": "en"}))
        ws.send_bytes(b"\x05\x00" * 100)  # the assistant is greeting, so this must go nowhere
        until_listening(ws)
        assert bytes(FakeStream.audio_received) == b""
        ws.send_bytes(b"\x06\x00" * 100)
        ws.send_text(json.dumps({"type": "end"}))
        read_until(ws, "done")
    assert bytes(FakeStream.audio_received) == b"\x06\x00" * 100


def test_callers_voice_is_kept_on_the_report(call):
    with call.websocket_connect("/api/live/call") as ws:
        ws.send_text(json.dumps({"type": "start", "language": "en"}))
        until_listening(ws)
        ws.send_bytes(b"\x06\x00" * 100)
        say(ws, "Flood in Nandwadi, 25 people are stuck")
        final = read_until(ws, "done")
    report = report_of(final)
    with SessionLocal() as db:
        files = db.query(models.AudioFile).filter_by(report_id=report.id).all()
    assert [f.kind for f in files] == ["caller_audio"] and files[0].original_filename == "live-call.wav"


def test_dont_know_moves_on(call):
    with call.websocket_connect("/api/live/call") as ws:
        ws.send_text(json.dumps({"type": "start", "language": "en"}))
        until_listening(ws)
        say(ws, "Flood in Nandwadi")
        assert "How many" in next(m["text"] for m in until_listening(ws) if m["type"] == "assistant")
        say(ws, "don't know")
        final = read_until(ws, "done")
    assert "not known" in next(m["text"] for m in final if m["type"] == "assistant")


def test_unclear_answer_is_asked_once_more_then_skipped(call):
    with call.websocket_connect("/api/live/call") as ws:
        ws.send_text(json.dumps({"type": "start", "language": "en"}))
        until_listening(ws)
        say(ws, "Flood in Nandwadi")
        until_listening(ws)
        say(ws, "mmm")
        again = next(m["text"] for m in until_listening(ws) if m["type"] == "assistant")
        assert again.startswith("Sorry") and "How many" in again
        say(ws, "mmm")
        final = read_until(ws, "done")
    assert report_of(final).status == "processed"


def test_a_greeting_is_not_a_report(call):
    with call.websocket_connect("/api/live/call") as ws:
        ws.send_text(json.dumps({"type": "start", "language": "en"}))
        until_listening(ws)
        say(ws, "hello")
        words = next(m["text"] for m in until_listening(ws) if m["type"] == "assistant")
        ws.send_text(json.dumps({"type": "end"}))
        final = read_until(ws, "done")
    assert "what happened" in words and next(m for m in final if m["type"] == "done")["report_id"] is None


def test_silence_repeats_the_question_then_ends_the_call(call, monkeypatch):
    monkeypatch.setattr(live, "SILENCE_S", 0.05)
    with call.websocket_connect("/api/live/call") as ws:
        ws.send_text(json.dumps({"type": "start", "language": "en"}))
        final = read_until(ws, "done")
    words = [m["text"] for m in final if m["type"] == "assistant"]
    assert words[1].startswith("Can you hear me") and words[-1].startswith("I didn't hear a reply")


def test_timbre_failure_still_gives_the_words_and_keeps_listening(call):
    global timbre_fails
    timbre_fails = True
    with call.websocket_connect("/api/live/call") as ws:
        ws.send_text(json.dumps({"type": "start", "language": "en"}))
        seen = until_listening(ws)
        ws.send_text(json.dumps({"type": "end"}))
        read_until(ws, "done")
    assert any(m["type"] == "notice" for m in seen) and any(m["type"] == "assistant" for m in seen)


def test_prisma_failure_is_reported_and_stores_nothing(call):
    FakeStream.fail_to_connect = True
    with call.websocket_connect("/api/live/call") as ws:
        ws.send_text(json.dumps({"type": "start", "language": "en"}))
        seen = read_until(ws, "done")
    assert "Could not reach Gnani" in next(m["message"] for m in seen if m["type"] == "error")
    assert seen[-1]["report_id"] is None


def test_call_needs_a_login(call):
    with pytest.raises(WebSocketDisconnect):
        with TestClient(app).websocket_connect("/api/live/call"):
            pass
    assert TestClient(app).get("/api/live/calls").status_code == 401


def test_unknown_language_is_refused(call):
    with call.websocket_connect("/api/live/call") as ws:
        ws.send_text(json.dumps({"type": "start", "language": "xx"}))
        assert ws.receive_json()["type"] == "error"


def test_live_call_reports_are_hidden_from_the_public_routes(call):
    with call.websocket_connect("/api/live/call") as ws:
        ws.send_text(json.dumps({"type": "start", "language": "en"}))
        until_listening(ws)
        say(ws, "Flood in Nandwadi, 25 people are stuck")
        final = read_until(ws, "done")
    rid = next(m["report_id"] for m in final if m["type"] == "done")
    assert call.get(f"/api/reports/{rid}").status_code == 200
    assert TestClient(app).get(f"/api/reports/{rid}").status_code == 404


def test_dispatcher_sees_the_call_as_it_happens(call):
    with call.websocket_connect("/api/live/call") as ws:
        ws.send_text(json.dumps({"type": "start", "language": "en"}))
        until_listening(ws)
        say(ws, "Flood and people are trapped in Nandwadi")
        until_listening(ws)
        current = call.get("/api/live/calls").json()["items"][0]
        assert current["state"] == "listening" and current["asking_for"] == "people_unknown"
        assert current["facts"]["place"] == "Nandwadi"
        assert [t["speaker"] for t in current["turns"]] == ["assistant", "caller", "assistant"]
        ws.send_text(json.dumps({"type": "end"}))
        read_until(ws, "done")
    assert call.get("/api/live/calls").json()["items"][0]["state"] == "ended"


def test_reply_time_uses_prismas_own_milliseconds(call):
    with call.websocket_connect("/api/live/call") as ws:
        ws.send_text(json.dumps({"type": "start", "language": "en"}))
        until_listening(ws)
        say(ws, "Flood in Nandwadi, 25 people are stuck")
        final = read_until(ws, "done")
    metrics = next(m for m in final if m["type"] == "metrics")
    assert metrics["prisma_ms"] == 457 and metrics["total_ms"] == 457 + metrics["reply_ms"] and metrics["total_ms"] < 60000
