"""Deterministic duplicate detection."""
from datetime import datetime, timedelta, timezone

from app.services import matching
from app.services.aggregation import Member, aggregate
from app.services.extraction import extract

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _incident(cfg, *texts, minutes=0):
    members = [Member(f"R{i}", extract(t).model_dump(), T0 + timedelta(minutes=minutes), t, [], False)
               for i, t in enumerate(texts)]
    return aggregate(members, {}, cfg)["profile"]


def _report(text, minutes=10):
    return matching.report_profile(extract(text).model_dump(), T0 + timedelta(minutes=minutes), text)


NANDWADI = "Calling about the Nandwadi ZP school. Around 25 people are stuck on the roof including kids. Flood water level is rising fast."


def test_same_place_landmark_and_facts_is_likely_duplicate(cfg):
    inc = _incident(cfg, NANDWADI)
    r = _report("नंदवाडीतील जिल्हा परिषद शाळेच्या छतावर वीस ते पंचवीस लोक अडकले आहेत. पुराचे पाणी वाढत आहे.")
    m = matching.score_pair(r, inc, "I1", cfg)
    assert m.outcome == "likely_duplicate"
    features = {e["feature"] for e in m.evidence}
    assert {"same_place", "same_landmark", "same_hazard"} <= features


def test_different_village_is_distinct(cfg):
    inc = _incident(cfg, NANDWADI)
    r = _report("Dongarwadi school mein 30 log hain, bacche bhooke hain, khana chahiye. Abhi sab safe hain.")
    assert matching.score_pair(r, inc, "I1", cfg).outcome == "distinct"


def test_same_village_different_landmark_and_facts_is_distinct(cfg):
    inc = _incident(cfg, "Kothale gram panchayat shelter: about 50 families, everyone is safe, but drinking water is running low.")
    r = _report("कोठाले में विठ्ठल मंदिर के पास एक गर्भवती महिला को प्रसव पीड़ा हो रही है।")
    assert matching.score_pair(r, inc, "I1", cfg).outcome == "distinct"


def test_contradictory_counts_cap_at_possible(cfg):
    inc = _incident(cfg, "सोनारवाडी में पानी की टंकी के पास चालीस लोग फंसे हैं, जल्दी बचाइए।")
    r = _report("सोनारवाडीत पाण्याच्या टाकीजवळ आठ लोक अडकले आहेत. पुराचे पाणी वाढत आहे, लवकर या.")
    m = matching.score_pair(r, inc, "I1", cfg)
    assert m.score >= cfg["dedup"]["likely_threshold"]
    assert m.outcome == "possible_duplicate"
    assert any("People count differs" in c for c in m.contradictions)


def test_safe_vs_trapped_is_a_contradiction(cfg):
    inc = _incident(cfg, "Sonarwadi tanki ke paas ab koi nahi hai, sab log nikal gaye, sab safe hain.")
    r = _report("सोनारवाडी में पानी की टंकी के पास चालीस लोग फंसे हैं, जल्दी बचाइए।")
    m = matching.score_pair(r, inc, "I1", cfg)
    assert m.outcome == "possible_duplicate" and m.contradictions


def test_ungrounded_locations_never_auto_merge(cfg):
    inc = _incident(cfg, "Bade pul ke paas ek gaadi baadh mein beh gayi, andar do log the. Jaldi aao.")
    r = _report("मोठ्या पुलाजवळ एक गाडी पुराच्या पाण्यात वाहून गेली, आत दोन लोक होते.")
    m = matching.score_pair(r, inc, "I1", cfg)
    assert m.outcome == "possible_duplicate"
    assert "report location is not grounded" in m.caps


def test_low_quality_transcript_never_auto_merges(cfg):
    inc = _incident(cfg, NANDWADI)
    r = _report("[noise] ... nandwadi ... school ... [inaudible] ... chhat pe ... bachao ... paani")
    m = matching.score_pair(r, inc, "I1", cfg)
    assert m.outcome == "possible_duplicate"


def test_outside_time_window_penalised(cfg):
    inc = _incident(cfg, NANDWADI)
    r = _report(NANDWADI, minutes=cfg["dedup"]["time_window_minutes"] + 60)
    m = matching.score_pair(r, inc, "I1", cfg)
    assert any(e["feature"] == "outside_time_window" for e in m.evidence)


def test_decide_picks_best_and_is_deterministic(cfg):
    incs = {"I1": _incident(cfg, NANDWADI),
            "I2": _incident(cfg, "There was a landslide at Ambeghat near the bus stand. A bus is trapped with about 40 passengers.")}
    r = _report("नंदवाडी गांव में स्कूल की छत पर बहुत सारे लोग फंसे हुए हैं। बाढ़ का पानी बढ़ रहा है, जल्दी नाव भेजिए।")
    d1, d2 = matching.decide(r, incs, cfg), matching.decide(r, incs, cfg)
    assert d1.outcome == "likely_duplicate" and d1.incident_id == "I1"
    assert d1.to_dict() == d2.to_dict()
