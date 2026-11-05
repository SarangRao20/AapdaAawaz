"""Awaaz Live against fake Gnani streams; the real pipeline and database run underneath."""
from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import models
from app.api import live
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.providers.base import ProviderError
from app.services import live_call as lc
from app.services.live_guard import LiveGuard


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


# ---- the public caller-app socket ---------------------------------------------------------------

@pytest.fixture()
def public(call, monkeypatch):
    """The same fake Gnani streams, but as an anonymous caller app would connect."""
    monkeypatch.setattr(live, "settings", replace(settings, live_public=True))
    fresh = LiveGuard(max_concurrent=6, max_per_ip=1, max_per_hour=10)
    monkeypatch.setattr(live, "guard", fresh)
    return TestClient(app), fresh


@contextmanager
def open_call(guest):
    """A public call that is already connected and listening."""
    with guest.websocket_connect("/api/live/call") as ws:
        ws.send_text(json.dumps({"type": "start", "language": "en"}))
        until_listening(ws)
        yield ws


def test_public_calls_are_off_by_default(call):
    assert settings.live_public is False
    with pytest.raises(WebSocketDisconnect):
        with TestClient(app).websocket_connect("/api/live/call"):
            pass


def test_a_public_caller_gets_a_full_call(public):
    guest, _ = public
    with open_call(guest) as ws:
        say(ws, "Flood in Nandwadi, 25 people are stuck")
        final = read_until(ws, "done")
    report = report_of(final)
    assert report.source == "live_call" and report.status == "processed"


def test_one_call_at_a_time_per_device(public):
    guest, guard = public
    with open_call(guest) as first:
        with guest.websocket_connect("/api/live/call") as second:
            message = second.receive_json()
            assert message["type"] == "error" and "already open" in message["message"]
        first.send_text(json.dumps({"type": "end"}))
        read_until(first, "done")
    assert guard.snapshot()["active"] == 0


def test_the_slot_is_released_after_a_call(public):
    guest, guard = public
    with open_call(guest) as ws:
        ws.send_text(json.dumps({"type": "end"}))
        read_until(ws, "done")
    assert guard.snapshot()["active"] == 0
    # The next call from the same address is accepted, so a dropped call never locks the app out.
    with open_call(guest) as ws:
        ws.send_text(json.dumps({"type": "end"}))
        read_until(ws, "done")


def test_global_capacity_refuses_extra_calls(call, monkeypatch):
    monkeypatch.setattr(live, "settings", replace(settings, live_public=True))
    monkeypatch.setattr(live, "guard", LiveGuard(max_concurrent=1, max_per_ip=5, max_per_hour=10))
    guest = TestClient(app)
    with open_call(guest) as first:
        with guest.websocket_connect("/api/live/call") as second:
            message = second.receive_json()
            assert message["type"] == "error" and "busy" in message["message"].lower()
        first.send_text(json.dumps({"type": "end"}))
        read_until(first, "done")


def test_guard_enforces_a_rolling_hourly_quota():
    now = [1_000.0]
    guard = LiveGuard(max_concurrent=10, max_per_ip=10, max_per_hour=2, clock=lambda: now[0])
    assert guard.allow("a") is None
    guard.release("a")
    assert guard.allow("a") is None
    guard.release("a")
    assert guard.allow("a") == "hourly_limit"
    now[0] += 3_601
    assert guard.allow("a") is None


def test_a_foreign_website_cannot_start_a_public_call(public):
    guest, guard = public
    with guest.websocket_connect("/api/live/call", headers={"origin": "https://evil.example"}) as ws:
        message = ws.receive_json()
        assert message["type"] == "error" and "update" in message["message"]
    assert guard.snapshot()["active"] == 0


def test_the_caller_app_origin_is_allowed(public):
    guest, _ = public
    with guest.websocket_connect("/api/live/call", headers={"origin": "http://localhost"}) as ws:
        ws.send_text(json.dumps({"type": "start", "language": "en"}))
        until_listening(ws)
        ws.send_text(json.dumps({"type": "end"}))
        read_until(ws, "done")


# ---- tickets: a socket on another host cannot carry the dashboard's login cookie --------------------------
def test_a_ticket_needs_a_login(call):
    assert TestClient(app).post("/api/live/ticket").status_code == 401
    body = call.post("/api/live/ticket").json()
    assert body["ticket"] and body["expires_in"] == 60


def test_a_ticket_opens_a_call_without_the_cookie_even_when_public_calls_are_off(call):
    assert settings.live_public is False
    ticket = call.post("/api/live/ticket").json()["ticket"]
    with TestClient(app).websocket_connect(f"/api/live/call?ticket={ticket}") as ws:
        ws.send_text(json.dumps({"type": "start", "language": "en"}))
        until_listening(ws)
        ws.send_text(json.dumps({"type": "end"}))
        read_until(ws, "done")


def test_forged_and_expired_tickets_are_refused(call):
    from app import auth

    with pytest.raises(WebSocketDisconnect):
        with TestClient(app).websocket_connect("/api/live/call?ticket=forged.ticket"):
            pass
    old = auth.create_ws_ticket(now=1_000.0)
    assert auth.valid_ws_ticket(old, now=1_030.0)
    assert not auth.valid_ws_ticket(old, now=1_061.0)  # a minute is all it lasts
    payload, signature = old.split(".")
    assert not auth.valid_ws_ticket(f"{payload}.{signature[::-1]}", now=1_030.0)
    # A login session token is not a ticket, and a ticket is not a login session.
    assert not auth.valid_ws_ticket(auth.create_session("admin"))
    assert auth.session_username(auth.create_ws_ticket()) is None


def test_behind_a_trusted_proxy_the_forwarded_address_is_the_caller(call, monkeypatch):
    class Socket:
        client = type("C", (), {"host": "10.0.0.1"})()
        headers = {"x-forwarded-for": "203.0.113.9, 10.0.0.1"}

    assert live.client_address(Socket()) == "10.0.0.1"  # not trusted by default: anyone can send that header
    monkeypatch.setattr(live, "settings", replace(settings, trust_proxy=True))
    assert live.client_address(Socket()) == "203.0.113.9"
