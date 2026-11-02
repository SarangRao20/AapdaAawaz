"""Regressions for problems found by testing against the real Gnani API."""
from __future__ import annotations

import copy

import httpx
import pytest

from app import config
from app.providers.base import ProviderError
from app.providers.timbre import TimbreTTS
from app.services import gate
from app.services import priority as prio
from app.services.extraction import extract
from app.services.settings_store import validate_update
from tests.conftest import wait_for


# ---- Timbre ----------------------------------------------------------------------------
def test_default_timbre_model_matches_the_default_voices(monkeypatch):
    for name in ("TIMBRE_MODEL", "TIMBRE_VOICE_MR", "TIMBRE_VOICE_HI", "TIMBRE_VOICE_EN", "TIMBRE_VOICE_MIXED"):
        monkeypatch.delenv(name, raising=False)
    loaded = config.load_settings()
    assert loaded.timbre_model == "timbre-v3.0"
    assert set(loaded.timbre_voices.values()) == {"Shivani"}


def test_timbre_400_error_message_reaches_the_user():
    def reject(_request):
        return httpx.Response(400, json={"success": False, "status_code": 400,
                                         "message": "Voice 'Nalini' is not supported by model 'timbre-v3.0'"})

    tts = TimbreTTS(api_key="k", base_url="https://x.test", transport=httpx.MockTransport(reject))
    with pytest.raises(ProviderError, match="Voice 'Nalini' is not supported"):
        tts.synthesize("hello", "hi")


# ---- people counts ---------------------------------------------------------------------
@pytest.mark.parametrize(("text", "expected"), [
    ("around twenty five people are stuck on the roof", 25),
    ("twenty-five people are stuck", 25),
    ("thirty two people are trapped", 32),
    ("ninety nine people need help", 99),
    ("two hundred people are stranded here", 200),
    ("one hundred and fifty people are here", 150),
    ("two hundred fifty people are here", 250),
    ("25 people are stuck", 25),
    ("पच्चीस लोग फंसे हैं", 25),
    ("do sau log phase hain", 200),
])
def test_compound_people_counts(text, expected):
    assert extract(text, None).people_affected.count == expected


def test_digits_do_not_combine():
    assert extract("100 20 people are stuck", "en").people_affected.count != 120


def test_comma_keeps_numbers_separate():
    assert extract("we counted twenty, five people are stuck", "en").people_affected.count == 5


def test_range_with_compound_upper_bound():
    people = extract("twenty to twenty five people are stuck", "en").people_affected
    assert people.count == 25 and people.range == [20, 25]


def test_compound_count_of_a_vulnerable_group():
    result = extract("twenty five elderly people are stuck", "en")
    assert result.vulnerable_people.elderly.count == 25
    assert result.people_affected.count is None  # a sub-group is not everyone


# ---- places ----------------------------------------------------------------------------
def test_marathi_spelling_of_nandwadi_is_grounded():
    for text in ("मी नांदवाडी गावातून बोलतोय, इथे पूर आला आहे.", "नांदवाडीत पूर आला आहे"):
        loc = extract(text, "mr").location
        assert loc.status == "grounded" and loc.place_id == "P01"


@pytest.mark.parametrize("text", ["calling about the nandwati zp school", "हेलो मैं नैंदवाडी से बोल रहा हूं"])
def test_possible_misheard_village_is_a_candidate_without_a_pin(text):
    loc = extract(text, None).location
    assert loc.status == "ambiguous" and loc.candidates == ["P01"]
    assert loc.latitude is None and loc.longitude is None
    assert loc.place_id is None and "misheard" in loc.confidence_basis


def test_possible_match_needs_review(cfg):
    ext = extract("calling about the nandwati school, people are trapped", "en").model_dump()
    _, reasons = gate.assess(ext, "critical", cfg)
    assert "location_ambiguous" in [r["code"] for r in reasons]


@pytest.mark.parametrize(("text", "status"), [
    ("madrasa mein paani bhar gaya hai", "missing"),      # one letter from the alias "madras"
    ("Kesarwadi gaon mein baadh hai", "unmapped"),         # a different village stays different
    ("the bridge near the school is gone", "ambiguous"),
    ("ranwadi mein baadh hai", "grounded"),
])
def test_near_matches_do_not_invent_a_village(text, status):
    loc = extract(text, None).location
    assert loc.status == status
    assert (loc.place_id == "P10") if status == "grounded" else (loc.place_id is None)


def test_words_close_to_two_villages_are_not_guessed(monkeypatch):
    import app.services.extraction as ex
    from app.services.gazetteer import Gazetteer, Landmark, Place

    def place(pid, alias):
        return Place(pid, alias, alias, (alias,), 0.0, 0.0)

    fake = Gazetteer("", "", "", {"A": place("A", "barwadi"), "B": place("B", "sarwadi")},
                     {"L1": Landmark("L1", "A", "school", "", ()), "L2": Landmark("L2", "B", "school", "", ())})
    monkeypatch.setattr(ex, "load_gazetteer", lambda: fake)
    assert ex._possible_village(ex.tokenize("near barwadi")) == ("A", "barwadi")
    assert ex._possible_village(ex.tokenize("near marwadi")) is None  # not the same first letter
    assert ex._possible_village(ex.tokenize("near barwadi and sarwadi")) is None  # two villages


# ---- ranking rule ----------------------------------------------------------------------
# Exactly what real Prisma returned for syn-001. It mentions elderly people, so it scores a few
# points, yet says nothing about what is happening.
GARBLED = ("हेलो मेन नैंदवाडी जे ऑन एस इ बाल राहुन यहां बैड ए के आई हाय जिला परिषद स्कूल कीच है "
           "पी ए आर हम लगबगची एस इ बैड रह साथ मेन कोट बैक बुजुर्गो प्लीज़")


def _score(text, cfg, hint=None):
    return prio.score(prio.features_from_extraction(extract(text, hint).model_dump()), cfg)


def test_unreadable_report_is_raised_above_low_without_faking_a_score(cfg):
    pr = _score(GARBLED, cfg, "hi")
    assert pr["computed_label"] == "low" and pr["label"] == "medium"
    assert 0 < pr["score"] < cfg["priority"]["thresholds"]["medium"]  # real points, still unclear
    assert any("could not be understood" in n for n in pr["notes"])


def test_people_present_is_not_knowing_what_is_happening(cfg):
    pr = prio.score(prio.SeverityFeatures(vulnerable={"elderly"}, people_count=3), cfg)
    assert pr["computed_label"] == "low" and pr["label"] == "medium"


def test_low_quality_transcript_with_a_weak_signal_is_raised(cfg):
    pr = prio.score(prio.SeverityFeatures(caller_urgency="medium", transcript_low_quality=True), cfg)
    assert pr["computed_label"] == "low" and pr["label"] == "medium"


@pytest.mark.parametrize("features", [
    prio.SeverityFeatures(status_claims={"reported_safe"}),
    prio.SeverityFeatures(status_claims={"reported_evacuated"}, transcript_low_quality=True),
    prio.SeverityFeatures(caller_urgency="low"),
])
def test_clear_all_clear_reports_stay_low(cfg, features):
    assert prio.score(features, cfg)["label"] == "low"


def test_floor_never_lowers_a_report(cfg):
    pr = prio.score(prio.SeverityFeatures(dangers={"swept_away"}, transcript_low_quality=True), cfg)
    assert pr["label"] == "critical" and not pr["unclear_floor_applied"]


def test_understood_low_report_is_not_raised(cfg):
    pr = prio.score(prio.SeverityFeatures(caller_urgency="medium"), cfg)
    assert pr["label"] == "low" and not pr["unclear_floor_applied"]


def test_dispatcher_decision_beats_the_floor(cfg):
    pr = prio.score(prio.SeverityFeatures(), cfg, override_label="low")
    assert pr["label"] == "low" and not pr["unclear_floor_applied"]


def test_floor_is_configurable(cfg):
    for floor, label in (("low", "low"), ("high", "high")):
        custom = copy.deepcopy(cfg)
        custom["priority"]["unclear_floor"] = floor
        assert prio.score(prio.SeverityFeatures(), custom)["label"] == label


def test_floor_setting_is_validated():
    with pytest.raises(ValueError, match="unclear_floor"):
        validate_update("priority", {"unclear_floor": "critical"})


def test_unreadable_call_reaches_the_incident_queue_above_low(client):
    rid = client.post("/api/reports", json={"transcript": GARBLED, "language_hint": "hi", "process": True}).json()["id"]
    report = wait_for(client, rid)
    assert report["priority_label"] == "medium" and report["gate_status"] == "needs_review"
    incident = client.get(f"/api/incidents/{report['incident_id']}").json()
    assert incident["priority_label"] == "medium"
    assert "call back" in incident["recommended_action"]
    assert "relief supplies" not in incident["recommended_action"]
