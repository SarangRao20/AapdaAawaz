"""The seven extra languages (bn gu kn ml pa ta te): fixed wording is complete, facts are read from a
machine translation and always go to a person, and Prisma is told nothing that pulls it towards Hindi."""
from __future__ import annotations

import pytest

from app.api import live
from app.providers.prisma import PrismaSTT
from app.services import extraction, followup, live_call, translate, voice_alerts
from app.services import acknowledgement as ack
from app.services import telegram_bot as tg
from app.services.languages import ALL, CORE, EXTRA

ENGLISH = "Flood has come in our village. 20 people are stuck on the roof. Children and elders are with us. Need help now."


def test_every_fixed_text_exists_in_every_language():
    for table in (live_call.SPOKEN, live_call.HAZARD_WORDS, followup._FALLBACK_QUESTIONS, tg.TEXT):
        for key, by_language in table.items():
            assert set(ALL) <= set(by_language), f"{key} is missing {set(ALL) - set(by_language)}"
    for template in voice_alerts.TEMPLATES.values():
        assert set(ALL) <= set(template["text"])
    assert set(ALL) <= set(ack.TEMPLATES)


def test_safety_alerts_in_new_languages_point_to_112_and_format():
    for template in voice_alerts.TEMPLATES.values():
        for language in EXTRA:
            text = template["text"][language].format(place="Nandwadi")
            assert "112" in text and "Nandwadi" in text


def test_live_call_and_alerts_accept_every_language():
    assert live.LANGUAGES == set(ALL)
    assert set(voice_alerts.LANGUAGES) == set(ALL)
    assert set(tg.LANG_BUTTONS.values()) == set(ALL)


@pytest.mark.parametrize("language", EXTRA)
def test_facts_come_from_the_translation_and_always_need_review(monkeypatch, language):
    monkeypatch.setattr(extraction, "to_english", lambda text, source: ENGLISH)
    result = extraction.extract("<original script transcript>", language)
    assert result.disaster_type == "flood"
    assert result.people_affected.count == 20
    assert result.language == language
    assert result.requires_human_review
    assert "machine translation" in result.uncertainties[0]


def test_untranslatable_report_goes_to_a_person_instead_of_failing(monkeypatch):
    monkeypatch.setattr(extraction, "to_english", lambda text, source: None)
    result = extraction.extract("தமிழ் உரை", "ta")
    assert result.language == "ta" and result.requires_human_review
    assert "could not be translated" in result.uncertainties[0]


def test_core_languages_never_touch_the_translator(monkeypatch):
    def boom(*_a):
        raise AssertionError("translator called")
    monkeypatch.setattr(extraction, "to_english", boom)
    for language in CORE:
        extraction.extract("flood in the village, 20 people on the roof", language)


def test_translate_falls_through_to_the_next_provider_and_does_not_cache_failures(monkeypatch):
    import httpx
    calls = []

    def failing(text, source):
        calls.append("a")
        raise httpx.HTTPError("429")

    def working(text, source):
        calls.append("b")
        return "hello"

    translate._cache.clear()
    monkeypatch.setattr(translate, "PROVIDERS", [("a", failing), ("b", working)])
    assert translate.to_english("x", "ta") == "hello" and calls == ["a", "b"]

    translate._cache.clear()
    monkeypatch.setattr(translate, "PROVIDERS", [("a", failing)])
    assert translate.to_english("y", "ta") is None
    monkeypatch.setattr(translate, "PROVIDERS", [("b", working)])
    assert translate.to_english("y", "ta") == "hello"  # the earlier failure was not remembered


def test_keyterms_are_sent_for_core_languages_only():
    stt = PrismaSTT(api_key="k", keyterms=["Nandwadi"])
    assert "keyterms" in stt.request_fields("hi")
    for language in EXTRA:
        assert "keyterms" not in stt.request_fields(language)
        assert stt.request_fields(language)["language_code"] == f"{language}-IN"


def test_bare_answers_get_an_english_noun_in_new_languages():
    assert tg._PEOPLE_SUFFIX["ta"] == "people" and tg._PLACE_SUFFIX["bn"] == "gaon"
