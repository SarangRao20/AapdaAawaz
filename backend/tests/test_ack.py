"""Acknowledgement service — Evon-powered personalised acks + static template fallback."""
from __future__ import annotations

import json

import httpx
import pytest

from app.providers.base import ProviderError, ProviderUnavailable
from app.providers.evon import EvonExtractor
from app.services.acknowledgement import FORBIDDEN_PHRASES, TEMPLATES, _generate_evon_ack, ack_language


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ack_response(text: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": text}}]},
    )


def _make_extractor(handler, api_key: str = "test-key") -> EvonExtractor:
    return EvonExtractor(
        api_key=api_key,
        base_url="https://evon.test",
        transport=httpx.MockTransport(handler),
    )


def _minimal_ext(**overrides) -> dict:
    base = {
        "disaster_type": "flood",
        "urgency": "critical",
        "language": "hi",
        "summary": "Flood at Khadakwasla; 50 people trapped.",
        "location": {"place_name": "Khadakwasla", "landmark": None, "status": "unmapped"},
        "people_affected": {"count": 50, "approximate": False},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# _generate_evon_ack tests
# Patch at app.providers.evon.EvonExtractor — the import in acknowledgement.py
# is `from ..providers.evon import EvonExtractor` (inside the function), so
# patching the class on the source module is the correct target.
# ---------------------------------------------------------------------------

def test_evon_ack_happy_path(monkeypatch):
    expected = "Aapki Khadakwasla mein baadhon ki report mili. 50 logon ki jankari darj ki ja rahi hai."

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        assert body.get("temperature") == pytest.approx(0.3)
        assert "response_format" not in body
        assert "Khadakwasla" in body["messages"][1]["content"]
        return _ack_response(expected)

    monkeypatch.setattr("app.providers.evon.EvonExtractor", lambda: _make_extractor(handler))
    result = _generate_evon_ack(_minimal_ext(), "hi")
    assert result == expected


def test_evon_ack_returns_none_when_provider_unavailable(monkeypatch):
    def _raise():
        raise ProviderUnavailable("no key")

    monkeypatch.setattr("app.providers.evon.EvonExtractor", _raise)
    assert _generate_evon_ack(_minimal_ext(), "hi") is None


def test_evon_ack_returns_none_on_provider_error(monkeypatch):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "overload"})

    monkeypatch.setattr("app.providers.evon.EvonExtractor", lambda: _make_extractor(handler))
    assert _generate_evon_ack(_minimal_ext(), "hi") is None


def test_evon_ack_rejects_forbidden_phrase(monkeypatch):
    bad_text = "Help is on its way. Please wait."

    def handler(req: httpx.Request) -> httpx.Response:
        return _ack_response(bad_text)

    monkeypatch.setattr("app.providers.evon.EvonExtractor", lambda: _make_extractor(handler))
    assert _generate_evon_ack(_minimal_ext(), "en") is None


def test_evon_ack_uses_location_and_people(monkeypatch):
    captured = {}

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        captured["msg"] = body["messages"][1]["content"]
        return _ack_response("Report received. 30 people noted.")

    monkeypatch.setattr("app.providers.evon.EvonExtractor", lambda: _make_extractor(handler))
    ext = _minimal_ext(people_affected={"count": 30, "approximate": False},
                       location={"place_name": "Nashik", "landmark": None})
    _generate_evon_ack(ext, "hi")
    assert "Nashik" in captured["msg"]
    assert "30" in captured["msg"]


# ---------------------------------------------------------------------------
# ack_language tests
# ---------------------------------------------------------------------------

def test_ack_language_known():
    for lang in ("mr", "hi", "en", "mixed"):
        assert ack_language(lang) == lang


def test_ack_language_unknown_falls_back_to_mixed():
    assert ack_language("xx") == "mixed"
    assert ack_language(None) == "mixed"
    assert ack_language("ta") == "ta"  # Tamil is a supported language now
