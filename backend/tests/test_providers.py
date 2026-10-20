"""Provider adapters, using httpx.MockTransport (no network)."""
import json
from pathlib import Path

import httpx
import pytest

from app.providers.base import ProviderError, ProviderUnavailable
from app.providers.mock_stt import MockFixtureSTT
from app.providers.prisma import PrismaSTT
from app.providers.registry import get_stt, get_tts
from app.providers.timbre import TimbreTTS

AUDIO = Path(__file__).resolve().parent.parent / "data" / "audio"


def test_prisma_requires_key():
    with pytest.raises(ProviderUnavailable):
        PrismaSTT(api_key="")


def test_prisma_success_request_shape():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("X-API-Key-ID")
        seen["body"] = request.content
        return httpx.Response(200, json={"success": True, "request_id": "req-1", "timestamp": "t",
                                         "transcript": "नंदवाडी"})

    stt = PrismaSTT(api_key="k", base_url="https://example.test", transport=httpx.MockTransport(handler))
    res = stt.transcribe(AUDIO / "syn-006.wav", "audio/wav", "mr")
    assert seen["url"] == "https://example.test/stt/v3"
    assert seen["key"] == "k"
    assert b'name="language_code"' in seen["body"] and b"mr-IN" in seen["body"]
    assert res.transcript == "नंदवाडी" and res.mode == "real" and res.request_id == "req-1"
    assert res.raw["transcript"] == "नंदवाडी"


def test_prisma_retries_transient_then_succeeds(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, json={"detail": "busy"})
        return httpx.Response(200, json={"success": True, "transcript": "ok"})

    stt = PrismaSTT(api_key="k", base_url="https://x.test", max_retries=2, transport=httpx.MockTransport(handler))
    assert stt.transcribe(AUDIO / "syn-006.wav", "audio/wav", "en").transcript == "ok"
    assert calls["n"] == 2


def test_prisma_auth_error_is_not_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(403, json={"detail": "bad key"})

    secret = "SECRET-KEY-5d1e"
    stt = PrismaSTT(api_key=secret, base_url="https://x.test", max_retries=3, transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as exc:
        stt.transcribe(AUDIO / "syn-006.wav", "audio/wav", "en")
    assert calls["n"] == 1 and "403" in str(exc.value)
    assert secret not in str(exc.value) and secret not in repr(stt.__dict__.get("base_url"))


def test_timbre_returns_audio_and_reports_errors():
    def ok(request):
        body = json.loads(request.content)
        assert body["language"] == "hi-en" and body["voice"] and body["model"]
        return httpx.Response(200, content=b"RIFF....WAVE", headers={"content-type": "audio/wav"})

    res = TimbreTTS(api_key="k", base_url="https://x.test", transport=httpx.MockTransport(ok)).synthesize("hi", "mixed")
    assert res.audio.startswith(b"RIFF") and res.mode == "real"

    def bad(request):
        return httpx.Response(400, json={"success": False, "error": {"type": "invalid", "message": "voice"}})

    with pytest.raises(ProviderError):
        TimbreTTS(api_key="k", base_url="https://x.test", transport=httpx.MockTransport(bad)).synthesize("hi", "mixed")


def test_registry_without_key_uses_labelled_mock_and_no_tts():
    stt = get_stt("auto")
    assert isinstance(stt, MockFixtureSTT) and stt.mode == "mock"
    assert get_tts("auto") is None


def test_mock_stt_never_invents_text(tmp_path):
    p = tmp_path / "x.wav"
    p.write_bytes((AUDIO / "syn-006.wav").read_bytes() + b"\x00")
    res = MockFixtureSTT().transcribe(p, "audio/wav", "en")
    assert res.transcript is None and res.mode == "mock"
    hit = MockFixtureSTT().transcribe(AUDIO / "syn-006.wav", "audio/wav", "en")
    assert hit.transcript and hit.raw["matched_fixture"] == "SYN-006"
