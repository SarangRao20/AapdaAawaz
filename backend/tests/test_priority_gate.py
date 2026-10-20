"""Priority scoring and the field-level confidence gate."""
from app.services import gate
from app.services import priority as prio
from app.services.extraction import extract


def _score(text, cfg, hint=None):
    ext = extract(text, hint).model_dump()
    return ext, prio.score(prio.features_from_extraction(ext), cfg)


def test_explicit_threat_to_life_is_critical(cfg):
    _, pr = _score("सोनारवाडीत पाण्याच्या टाकीजवळ आठ लोक अडकले आहेत.", cfg)
    assert pr["label"] == "critical"
    assert pr["factors"][0]["key"] == "life_threat"


def test_safe_status_caps_label(cfg):
    _, pr = _score("Dongarwadi school mein 30 log hain, bacche bhooke hain, khana chahiye. Abhi sab safe hain.", cfg)
    assert pr["computed_label"] == "high"
    assert pr["label"] == "medium"
    assert any("Capped" in n for n in pr["notes"])


def test_uncertain_location_does_not_lower_severity(cfg):
    grounded = prio.SeverityFeatures(dangers={"swept_away"}, location_grounded=True)
    unknown = prio.SeverityFeatures(dangers={"swept_away"}, location_grounded=False)
    a, b = prio.score(grounded, cfg), prio.score(unknown, cfg)
    assert a["score"] == b["score"] and a["label"] == b["label"] == "critical"
    assert "Location not grounded to a reference place" in b["missing_info"]


def test_unknown_people_count_is_missing_info_not_zero(cfg):
    pr = prio.score(prio.SeverityFeatures(dangers={"trapped"}), cfg)
    assert "Number of people unknown" in pr["missing_info"]
    assert not any(f["key"].startswith("people_") for f in pr["factors"])


def test_dispatcher_override_is_explained(cfg):
    pr = prio.score(prio.SeverityFeatures(needs={"food"}), cfg, override_label="high")
    assert pr["label"] == "high" and pr["computed_label"] == "medium"
    assert any("Dispatcher set priority" in n for n in pr["notes"])


def test_basic_needs_only_is_medium(cfg):
    _, pr = _score("कोठाळे ग्रामपंचायत कार्यालयात पन्नास कुटुंबे थांबली आहेत. सगळे सुरक्षित आहेत, पण पिण्याचे पाणी संपत आले आहे.", cfg)
    assert pr["label"] == "medium"


def test_gate_flags_fields_individually(cfg):
    ext, pr = _score("Bade pul ke paas ek gaadi baadh mein beh gayi, andar do log the. Jaldi aao.", cfg)
    fields, reasons = gate.assess(ext, pr["label"], cfg)
    codes = {r["code"] for r in reasons}
    assert "location_ambiguous" in codes
    assert fields["location"]["status"] == "review"
    assert fields["people_count"]["status"] == "ok"  # "do log" = 2 is stated
    assert fields["urgency"]["caller_urgency"] == "high"


def test_gate_unknown_count_only_matters_when_priority_is_high(cfg):
    ext = extract("कोठाले ग्राम पंचायत में पचास परिवार ठहरे हैं। पीने का पानी खत्म हो रहा है।").model_dump()
    _, reasons_medium = gate.assess(ext, "medium", cfg)
    _, reasons_critical = gate.assess(ext, "critical", cfg)
    assert "people_count_unknown" not in {r["code"] for r in reasons_medium}
    assert "people_count_unknown" in {r["code"] for r in reasons_critical}


def test_gate_low_quality_transcript(cfg):
    ext, pr = _score("[noise] ... nandwadi ... school ... [inaudible] ... chhat pe ... bachao ... paani", cfg)
    _, reasons = gate.assess(ext, pr["label"], cfg)
    codes = {r["code"] for r in reasons}
    assert {"low_quality_transcript", "location_low_confidence"} <= codes
    assert pr["label"] == "critical"  # still severe even though unreliable


def test_gate_contradiction_inside_one_report(cfg):
    ext = extract("Sonarwadi mein sab safe hain lekin 8 log phase hain").model_dump()
    _, reasons = gate.assess(ext, "critical", cfg)
    assert "inconsistent_fields" in {r["code"] for r in reasons}
