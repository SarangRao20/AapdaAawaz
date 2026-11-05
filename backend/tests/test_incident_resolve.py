"""A dispatcher can close an incident once responders have dealt with it, and reopen it."""
from .conftest import wait_for


def _incident(client, text="Kothale gaon mein 5 log chhat par fanse hain, paani badh raha hai"):
    r = client.post("/api/reports", json={"transcript": text, "process": True})
    rep = wait_for(client, r.json()["id"])
    assert rep["status"] == "processed"
    return rep["incident_id"], rep["id"]


def test_resolve_removes_incident_from_board_and_reopen_restores_it(client):
    incident_id, _ = _incident(client)
    assert incident_id in {i["id"] for i in client.get("/api/incidents").json()["items"]}
    active_before = client.get("/api/dashboard/stats").json()["unique_incidents"]

    r = client.post(f"/api/incidents/{incident_id}/resolve", json={"reviewer": "asha", "reason": "rescued"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "closed"
    assert body["human_overrides"]["resolution"]["reason"] == "rescued"
    assert body["human_overrides"]["resolution"]["by"] == "asha"

    assert incident_id not in {i["id"] for i in client.get("/api/incidents").json()["items"]}
    assert incident_id in {i["id"] for i in client.get("/api/incidents?status=closed").json()["items"]}
    assert client.get("/api/dashboard/stats").json()["unique_incidents"] == active_before - 1
    assert any(a["action"] == "resolved" for a in body["audit"])

    # Closing twice, or reviewing a closed incident, is refused rather than silently ignored.
    assert client.post(f"/api/incidents/{incident_id}/resolve", json={"reviewer": "asha"}).status_code == 400

    r = client.post(f"/api/incidents/{incident_id}/reopen", json={"reviewer": "asha"})
    assert r.status_code == 200
    assert r.json()["status"] == "active"
    assert "resolution" not in r.json()["human_overrides"]
    assert incident_id in {i["id"] for i in client.get("/api/incidents").json()["items"]}


def test_reprocessing_a_report_does_not_reopen_a_resolved_incident(client):
    incident_id, report_id = _incident(client)
    client.post(f"/api/incidents/{incident_id}/resolve", json={"reviewer": "asha", "reason": "false_alarm"})
    assert client.post(f"/api/reports/{report_id}/process").status_code == 202
    wait_for(client, report_id)
    inc = client.get(f"/api/incidents/{incident_id}").json()
    assert inc["status"] == "closed" or inc["report_count"] == 0  # never silently back on the live board
    assert incident_id not in {i["id"] for i in client.get("/api/incidents").json()["items"]}


def test_reopen_requires_a_closed_incident_and_unknown_ids_404(client):
    incident_id, _ = _incident(client)
    assert client.post(f"/api/incidents/{incident_id}/reopen", json={"reviewer": "a"}).status_code == 400
    assert client.post("/api/incidents/INC-9999/resolve", json={"reviewer": "a"}).status_code == 404
