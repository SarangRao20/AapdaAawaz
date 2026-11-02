"""Provider adapters, using httpx.MockTransport (no network)."""
import dataclasses
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


def _captured_fields(**kwargs):
    seen = {}

    def handler(request):
        seen["body"] = request.content
        return httpx.Response(200, json={"success": True, "transcript": "x", "detected_language_code": "mr-IN"})

    stt = PrismaSTT(api_key="k", base_url="https://x.test", transport=httpx.MockTransport(handler), **kwargs)
    return stt, seen


def test_prisma_v3_sends_model_and_village_hints():
    stt, seen = _captured_fields(model="prisma-v3.0")
    res = stt.transcribe(AUDIO / "syn-006.wav", "audio/wav", "mr")
    body = seen["body"].decode("utf-8", "ignore")
    assert "prisma-v3.0" in body and 'name="keyterms"' in body and "Nandwadi" in body
    assert res.provider == "gnani-prisma-v3.0" and res.language_code == "mr-IN"


def test_prisma_v3_gives_language_hints_when_the_caller_mixes_or_has_not_said():
    stt, _ = _captured_fields(model="prisma-v3.0")
    assert stt.request_language("mixed") == "hi-IN,en-IN"
    assert stt.request_language(None) == "hi-IN,mr-IN,en-IN"
    assert stt.request_language("mr") == "mr-IN"


def test_prisma_v25_sends_none_of_the_v3_fields():
    stt, seen = _captured_fields(model="prisma-v2.5")
    stt.transcribe(AUDIO / "syn-006.wav", "audio/wav", None)
    assert stt.keyterms == ()
    assert b'name="keyterms"' not in seen["body"] and b'name="model"' not in seen["body"]


def test_village_hints_stay_inside_the_documented_limit_and_lead_with_places():
    from app.services.stt_hints import MAX_KEYTERMS, disaster_keyterms
    terms = disaster_keyterms()
    assert len(terms) <= MAX_KEYTERMS and terms[0] == "Nandwadi" and len(set(terms)) == len(terms)


def test_live_stream_sends_several_languages_the_way_the_live_api_requires(monkeypatch):
    from app import config
    from app.providers import gnani_stream, prisma
    keyed = dataclasses.replace(config.settings, gnani_api_key="k", prisma_model="prisma-v3.0")
    monkeypatch.setattr(gnani_stream, "settings", keyed)
    monkeypatch.setattr(prisma, "settings", keyed)
    mixed = gnani_stream.PrismaStream("mixed")._headers
    assert mixed["language_code"] == "hi-IN" and mixed["multi_lang_codes"] == "hi-IN,en-IN"
    single = gnani_stream.PrismaStream("mr")._headers
    assert single["language_code"] == "mr-IN" and "multi_lang_codes" not in single
    # Headers must be plain ASCII, so Indian scripts travel as \\u escapes.
    assert mixed["keyterms"].isascii() and "Nandwadi" in mixed["keyterms"]
