"""A follow-up answer joins the report it belongs to. It must never start a second report (that made the
journey page loop: each answer lacked the other details, so it asked again, forever)."""
from .conftest import wait_for


def _report(client, text):
    r = client.post("/api/reports", json={"transcript": text, "process": True, "language_hint": "en"})
    return wait_for(client, r.json()["id"])


def test_answer_is_merged_into_the_same_report(client):
    rep = _report(client, "Water is rising and people are trapped on the roof")
    assert rep["follow_up_needed"] and "location_missing" in rep["follow_up_missing_fields"]
    before = client.get("/api/reports").json()["total"]

    r = client.post(f"/api/reports/{rep['id']}/followup", data={"text": "Kothale village"})
    assert r.status_code == 202
    assert r.json()["id"] == rep["id"]
    assert r.json()["answered_field"] == "location_missing"

    after = wait_for(client, rep["id"])
    assert client.get("/api/reports").json()["total"] == before  # no new report was created
    assert "Kothale" in after["transcript"] and "Water is rising" in after["transcript"]
    assert "location_missing" not in after["follow_up_missing_fields"]
    assert any(a["action"] == "followup_answer" for a in after["audit"])


def test_followup_is_refused_when_nothing_is_missing_or_text_is_empty(client):
    rep = _report(client, "Kothale gaon, 5 people trapped by the flood, water rising")
    if not rep["follow_up_missing_fields"]:
        assert client.post(f"/api/reports/{rep['id']}/followup", data={"text": "x"}).status_code == 409
    incomplete = _report(client, "Water is rising")
    assert client.post(f"/api/reports/{incomplete['id']}/followup", data={"text": "   "}).status_code == 422
    assert client.post("/api/reports/R-NOPE/followup", data={"text": "x"}).status_code == 404


def test_only_telegram_and_live_calls_count_as_contacted(client):
    rep = _report(client, "Water is rising")
    assert rep["follow_up_status"] == "pending"
    assert rep["follow_up_channel"] is None  # a typed or uploaded report: nobody was asked anything
