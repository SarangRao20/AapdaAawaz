"""Evon LLM extraction adapter — all Evon HTTP calls are intercepted with httpx.MockTransport."""
from __future__ import annotations

import json

import httpx
import pytest

from app.providers.base import ProviderError, ProviderUnavailable
from app.providers.evon import EvonExtractor, _parse_json, _to_extraction_result
from app.schemas import ExtractionResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _evon_response(data: dict) -> httpx.Response:
    """Wrap a dict in the OpenAI-compatible chat-completions envelope Evon returns."""
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": json.dumps(data, ensure_ascii=False)}}]},
    )


def _minimal_evon_data(**overrides) -> dict:
    base = {
        "disaster_type": "flood",
        "location_place": "Khadakwasla",
        "location_landmark": "dam gate",
        "people_count": 30,
        "people_approximate": False,
        "vulnerable_groups": ["elderly", "children"],
        "immediate_needs": ["rescue_evacuation", "medical"],
        "reported_dangers": ["trapped", "water_rising"],
        "medical_emergency": True,
        "urgency": "critical",
        "language": "hi",
        "transcript_quality": "ok",
        "summary": "Flood at Khadakwasla dam gate; 30 people trapped including elderly and children; medical emergency; critical urgency.",
        "uncertainties": ["Exact location of all trapped people unclear"],
    }
    base.update(overrides)
    return base


def _make_extractor(handler) -> EvonExtractor:
    return EvonExtractor(
        api_key="test-key",
        base_url="https://evon.test",
        transport=httpx.MockTransport(handler),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_evon_requires_api_key():
    with pytest.raises(ProviderUnavailable, match="GNANI_API_KEY"):
        EvonExtractor(api_key="", base_url="https://x.test")


def test_evon_happy_path():
    data = _minimal_evon_data()

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.host == "evon.test"
        assert "Bearer test-key" in req.headers["Authorization"]
        body = json.loads(req.content)
        assert body["temperature"] == 0.0
        assert body["response_format"] == {"type": "json_object"}
        return _evon_response(data)

    result = _make_extractor(handler).extract("Khadakwasla mein baadhon ne logon ko ghera.", "hi")
    assert isinstance(result, ExtractionResult)
    assert result.disaster_type == "flood"
    assert result.urgency == "critical"
    assert result.language == "hi"
    assert result.provider == "gnani-evon-v3.3"
    assert result.provider_mode == "real"
    assert result.people_affected.count == 30
    assert "rescue_evacuation" in result.immediate_needs
    assert "trapped" in result.reported_danger
    assert result.medical_emergency is True
    assert result.vulnerable_people.elderly is not None
    assert result.vulnerable_people.children is not None
    assert "Khadakwasla" in result.summary


def test_evon_retries_on_503(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, json={"detail": "temporary overload"})
        return _evon_response(_minimal_evon_data())

    result = _make_extractor(handler).extract("flood report", "en")
    assert result.disaster_type == "flood"
    assert calls["n"] == 2


def test_evon_no_retry_on_400():
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    with pytest.raises(ProviderError, match="400"):
        _make_extractor(handler).extract("test", "en")
    assert calls["n"] == 1


def test_evon_403_not_retried():
    calls = {"n": 0}
    secret = "MY-SECRET-KEY-abc123"

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(403, json={"error": {"message": "invalid key"}})

    ev = EvonExtractor(api_key=secret, base_url="https://x.test", transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as exc_info:
        ev.extract("test", "hi")
    assert calls["n"] == 1
    # Secret must not appear in the error message
    assert secret not in str(exc_info.value)


def test_evon_bad_json_raises_provider_error():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "this is not json at all"}}]},
        )

    with pytest.raises(ProviderError, match="non-JSON"):
        _make_extractor(handler).extract("test", "en")


def test_evon_markdown_fence_stripped():
    """Model sometimes wraps JSON in ```json ... ``` despite instructions."""
    data = _minimal_evon_data(disaster_type="fire", urgency="high")
    fenced = f"```json\n{json.dumps(data)}\n```"

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": fenced}}]},
        )

    result = _make_extractor(handler).extract("fire report", "en")
    assert result.disaster_type == "fire"
    assert result.urgency == "high"


def test_evon_invalid_enum_coerced_to_default():
    """Unknown enum values are silently mapped to safe defaults, not raised."""
    data = _minimal_evon_data(
        disaster_type="tsunami",   # not a valid DisasterType
        urgency="extreme",         # not a valid Urgency
        language="ta",             # not in _LANGUAGES
    )

    def handler(req: httpx.Request) -> httpx.Response:
        return _evon_response(data)

    result = _make_extractor(handler).extract("test", None)
    assert result.disaster_type == "unknown"   # coerced
    assert result.urgency == "unknown"          # coerced
    assert result.language == "unknown"         # coerced


def test_evon_filters_invalid_list_values():
    """Array fields only keep allowed values; unknown ones are dropped."""
    data = _minimal_evon_data(
        immediate_needs=["rescue_evacuation", "helicopter", "money"],  # last two invalid
        reported_dangers=["trapped", "sinking"],                        # last one invalid
        vulnerable_groups=["elderly", "pets"],                          # last one invalid
    )

    def handler(req: httpx.Request) -> httpx.Response:
        return _evon_response(data)

    result = _make_extractor(handler).extract("test", "hi")
    assert result.immediate_needs == ["rescue_evacuation"]
    assert result.reported_danger == ["trapped"]
    assert result.vulnerable_people.elderly is not None
    # "pets" should not appear in any vulnerable field
    assert result.vulnerable_people.children is None


def test_evon_null_location_produces_missing_location():
    data = _minimal_evon_data(location_place=None, location_landmark=None)

    def handler(req: httpx.Request) -> httpx.Response:
        return _evon_response(data)

    result = _make_extractor(handler).extract("test", "hi")
    assert result.location.status == "missing"
    assert result.location.place_name is None


def test_evon_no_people_count():
    data = _minimal_evon_data(people_count=None, people_approximate=False)

    def handler(req: httpx.Request) -> httpx.Response:
        return _evon_response(data)

    result = _make_extractor(handler).extract("test", "hi")
    assert result.people_affected.count is None


def test_evon_uses_language_hint_fallback():
    """If Evon returns an invalid language, the language_hint is used instead."""
    data = _minimal_evon_data(language="xx")  # invalid

    def handler(req: httpx.Request) -> httpx.Response:
        return _evon_response(data)

    # With hint "mr" — should fall back to "mr" since "xx" is not in _LANGUAGES
    result = _make_extractor(handler).extract("test", "mr")
    assert result.language == "mr"


# ---------------------------------------------------------------------------
# Unit tests for helpers (no network)
# ---------------------------------------------------------------------------

def test_parse_json_strips_fences():
    raw = "```json\n{\"a\": 1}\n```"
    assert _parse_json(raw) == {"a": 1}


def test_parse_json_plain():
    assert _parse_json('{"b": 2}') == {"b": 2}


def test_parse_json_invalid_raises():
    with pytest.raises(ValueError):
        _parse_json("not json")


def test_to_extraction_result_sets_provider_fields():
    data = _minimal_evon_data()
    result = _to_extraction_result(data, "transcript", "hi")
    assert result.provider == "gnani-evon-v3.3"
    assert result.provider_mode == "real"


def test_to_extraction_result_evon_summary_preferred():
    """Evon's natural-language summary should be used over any fallback."""
    data = _minimal_evon_data(summary="Flood near dam. 30 trapped. Medical emergency.")
    result = _to_extraction_result(data, "transcript", "hi")
    assert result.summary == "Flood near dam. 30 trapped. Medical emergency."
