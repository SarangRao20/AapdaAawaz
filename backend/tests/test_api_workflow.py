"""End-to-end API workflow on an isolated database."""
import io
import struct
import wave
from pathlib import Path

from sqlalchemy import create_engine, text

from app.config import settings

from .conftest import wait_for

AUDIO = Path(__file__).resolve().parent.parent / "data" / "audio"


def _wav(seconds=1.0, rate=16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<h", 0) * int(rate * seconds))
    return buf.getvalue()


def _incident_with(client, report_id):
    return client.get(f"/api/reports/{report_id}").json()["incident_id"]


def test_manual_report_to_incident(client):
    r = client.post("/api/reports", json={
        "transcript": "Calling about the Nandwadi ZP school. Around 25 people are stuck on the roof including kids "
                      "and two elderly people. Flood water level is rising fast.",
        "language_hint": "en", "process": True})
    assert r.status_code == 201
    rep = wait_for(client, r.json()["id"])
    assert rep["status"] == "processed"
    assert rep["transcript_provider_mode"] == "human"
    assert [j["stage"] for j in rep["jobs"]] == ["transcription", "extraction", "priority", "confidence_gate",
                                                 "deduplication"]
    inc = client.get(f"/api/incidents/{rep['incident_id']}").json()
    assert inc["priority_label"] == "critical"
    assert inc["latitude"] is not None and inc["coordinates_are_simulated"]
    assert inc["priority_breakdown"]["factors"]
    assert rep["acknowledgement"]["status"] == "text_only"
    assert rep["acknowledgement"]["audio_url"] is None
    stats = client.get("/api/dashboard/stats").json()
    assert stats["total_reports"] == 1 and stats["unique_incidents"] == 1


def test_invalid_inputs_return_clear_errors(client):
    r = client.post("/api/reports", json={"process": True})
    assert r.status_code == 422 and "transcript" in r.json()["detail"]
    r = client.post("/api/reports", json={"transcript": "x", "language_hint": "fr"})
    assert r.status_code == 422 and "language_hint" in r.json()["detail"]
    r = client.post("/api/reports/upload", files={"file": ("evil.wav", b"MZ\x90\x00not audio", "audio/wav")})
    assert r.status_code == 400 and "unsupported" in r.json()["detail"]
    r = client.post("/api/reports/upload", files={"file": ("long.wav", _wav(31), "audio/wav")})
    assert r.status_code == 400 and "30" in r.json()["detail"]
    assert client.get("/api/reports/R-NOPE").status_code == 404
    assert client.post("/api/incidents/INC-9999/review", json={"reviewer": "a", "mark_reviewed": True}).status_code == 404


def test_fixture_audio_goes_through_mock_stt_labelled_as_mock(client):
    data = (AUDIO / "syn-006.wav").read_bytes()
    r = client.post("/api/reports/upload", files={"file": ("call.wav", data, "audio/wav")}, data={"language_hint": "en"})
    assert r.status_code == 201
    rep = wait_for(client, r.json()["id"])
    assert rep["status"] == "processed"
    assert rep["transcript_provider_mode"] == "mock"
    assert rep["transcript_source"] == "mock_fixture_lookup"
    assert "No speech recognition" in rep["jobs"][0]["detail"]["note"]
    audio = client.get(rep["audio"][0]["url"])
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/wav"


def test_unknown_audio_needs_manual_transcript_then_processes(client):
    r = client.post("/api/reports/upload", files={"file": ("x.wav", _wav(1.5), "audio/wav")})
    rep = wait_for(client, r.json()["id"])
    assert rep["status"] == "needs_transcript"
    assert rep["transcript"] is None  # no invented text
    r = client.post(f"/api/reports/{rep['id']}/transcript",
                    json={"text": "Ranwadi market ke paas ek buzurg uncle ko insulin chahiye.", "reviewer": "op1"})
    assert r.status_code == 200
    rep = wait_for(client, rep["id"], ("processed", "failed"))
    assert rep["status"] == "processed" and rep["transcript_provider_mode"] == "human"
    assert any(a["action"] == "transcript_entered" for a in rep["audit"])


def test_seed_review_merge_split_and_persistence(client):
    r = client.post("/api/demo/seed", json={"mode": "all"})
    assert r.status_code == 200 and r.json()["created"] == 40
    stats = r.json()["stats"]
    assert stats["total_reports"] == 40
    assert 0 < stats["unique_incidents"] < 40
    assert stats["duplicates_linked"] == 40 - stats["unique_incidents"]  # every report beyond an incident's first
    assert client.post("/api/demo/seed", json={"mode": "all"}).status_code == 409

    queue = client.get("/api/incidents").json()["items"]
    ranks = {"critical": 3, "high": 2, "medium": 1, "low": 0}
    keys = [(ranks[i["priority_label"]], i["priority_score"]) for i in queue]
    assert keys == sorted(keys, reverse=True)

    # Hero cluster: SYN-001/002/003/004/006 auto-linked; noisy SYN-005 only suggested.
    hero = _incident_with(client, "R-SYN-001")
    for rid in ("R-SYN-002", "R-SYN-003", "R-SYN-004", "R-SYN-006"):
        assert _incident_with(client, rid) == hero
    noisy_inc = _incident_with(client, "R-SYN-005")
    assert noisy_inc != hero
    sugg = [s for s in client.get("/api/suggestions").json()["items"] if s["report_id"] == "R-SYN-005"]
    assert sugg and sugg[0]["candidate_incident_id"] == hero

    # Confirm the duplicate: report moves, original report and link history kept.
    r = client.post(f"/api/suggestions/{sugg[0]['id']}/confirm", json={"reviewer": "op1", "notes": "same school"})
    assert r.status_code == 200 and r.json()["status"] == "confirmed"
    assert _incident_with(client, "R-SYN-005") == hero
    old = client.get(f"/api/incidents/{noisy_inc}").json()
    assert old["status"] == "merged" and old["merged_into_id"] == hero
    rep5 = client.get("/api/reports/R-SYN-005").json()
    assert rep5["transcript"].startswith("[noise]")
    assert [l["active"] for l in rep5["links"]] == [False, True]
    assert client.post(f"/api/suggestions/{sugg[0]['id']}/confirm", json={"reviewer": "op1"}).status_code == 409

    # Reject an incorrect suggestion (power-outage report vs. school shelter).
    s39 = next(s for s in client.get("/api/suggestions").json()["items"] if s["report_id"] == "R-SYN-039")
    assert client.post(f"/api/suggestions/{s39['id']}/reject", json={"reviewer": "op1"}).json()["status"] == "rejected"
    assert _incident_with(client, "R-SYN-039") == s39["source_incident_id"]

    # Ambiguous location: dispatcher verifies it; AI extraction stays untouched.
    amb = _incident_with(client, "R-SYN-026")
    before = client.get(f"/api/incidents/{amb}").json()
    assert before["location_status"] == "ambiguous" and before["latitude"] is None
    r = client.post(f"/api/incidents/{amb}/review", json={
        "reviewer": "op2", "notes": "caller confirmed Karanjkhed bridge", "verify_location": {"place_id": "P08"},
        "people_count": 2, "mark_reviewed": True})
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["location_status"] == "human_verified" and after["latitude"] is not None
    assert after["review_status"] == "reviewed"
    assert any(a["action"] == "human_correction" and a["field"] == "location" and a["old_value"] for a in after["audit"])
    rep26 = client.get("/api/reports/R-SYN-026").json()
    assert rep26["extraction_current"]["location"]["status"] == "ambiguous"
    assert rep26["extraction_original"] == rep26["extraction_current"]

    # Manual merge and split keep every report.
    amb2 = _incident_with(client, "R-SYN-025")
    merged = client.post(f"/api/incidents/{amb}/merge", json={"source_incident_ids": [amb2], "reviewer": "op2"}).json()
    assert {m["id"] for m in merged["reports"]} == {"R-SYN-025", "R-SYN-026"}
    split = client.post(f"/api/incidents/{amb}/split", json={"report_ids": ["R-SYN-025"], "reviewer": "op2"})
    assert split.status_code == 200
    assert _incident_with(client, "R-SYN-025") == split.json()["new_incident"]["id"]
    bad = client.post(f"/api/incidents/{amb}/split", json={"report_ids": ["R-SYN-026"], "reviewer": "op2"})
    assert bad.status_code == 400

    # Persistence: a brand-new engine on the same SQLite file sees the same data.
    eng = create_engine(settings.database_url)
    with eng.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM reports")).scalar() == 40
        assert conn.execute(text("SELECT COUNT(*) FROM audit_log WHERE action='human_correction'")).scalar() >= 2
    eng.dispose()


def test_demo_inject_hero_with_audio(client):
    r = client.post("/api/demo/inject", json={"fixture_id": "SYN-001", "use_audio": True})
    assert r.status_code == 202
    rep = wait_for(client, r.json()["id"])
    assert rep["status"] == "processed"
    assert rep["has_audio"] and rep["transcript_provider_mode"] == "mock"
    assert rep["ground_truth"]["incident_group"] == "G01"
    assert client.post("/api/demo/inject", json={"fixture_id": "SYN-001"}).status_code == 409
    r = client.post("/api/demo/seed", json={"mode": "remaining"})
    assert r.json()["created"] == 39


def test_settings_validation_and_update(client):
    bad = client.put("/api/settings", json={"dedup": {"likely_threshold": 0.3, "possible_threshold": 0.5}})
    assert bad.status_code == 422
    ok = client.put("/api/settings", json={"gate": {"min_location_confidence": 0.85}})
    assert ok.status_code == 200 and ok.json()["config"]["gate"]["min_location_confidence"] == 0.85
    assert client.get("/api/settings").json()["providers"]["speech_to_text"]["mode"] == "mock"
    client.put("/api/settings", json={"gate": {"min_location_confidence": 0.7}})


def test_evaluation_and_csv(client):
    ev = client.post("/api/evaluation/run").json()
    dev, hold = ev["splits"]["development"]["metrics"], ev["splits"]["holdout"]["metrics"]
    assert dev["n_reports"] == 40 and hold["n_reports"] == 12
    assert dev["deduplication"]["pairwise"]["precision"] is not None
    assert ev["stt"]["measured"] is False
    assert any("optimistic" in c for c in ev["caveats"])
    csv = client.get("/api/evaluation/export.csv")
    assert csv.status_code == 200 and csv.text.splitlines()[0].startswith("split,fixture_id,")
    assert len(csv.text.strip().splitlines()) == 1 + 40 + 12


def test_health_reports_providers_without_secrets(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["providers"]["extraction"]["evon_available"] is False
    assert "api_key" not in str(body).replace("gnani_api_key_configured", "")
