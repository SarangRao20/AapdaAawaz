"""Tests for Twilio Voice and Telephony Integration."""
import pytest
import httpx
from fastapi.testclient import TestClient

from app.main import app


def test_twilio_incoming_voice_twiml(client):
    """Verify incoming call webhook returns valid TwiML greeting and record verb."""
    # Test POST
    resp = client.post("/api/twilio/voice", data={"CallSid": "CA123", "From": "+919421140800"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/xml"
    content = resp.text
    assert "<Response>" in content
    assert "<Say" in content
    assert "<Record" in content
    assert "/api/twilio/recording" in content

    # Test GET
    resp_get = client.get("/api/twilio/incoming")
    assert resp_get.status_code == 200
    assert "<Response>" in resp_get.text


def test_twilio_recording_webhook_creates_report(client, monkeypatch):
    """Verify recording webhook downloads audio, creates report, and queues processing."""
    fake_wav = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    dummy_req = httpx.Request("GET", "https://api.twilio.com/fake.wav")

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url, **kwargs):
            return httpx.Response(200, content=fake_wav, request=dummy_req)

    monkeypatch.setattr("httpx.AsyncClient", MockAsyncClient)

    resp = client.post("/api/twilio/recording", data={
        "RecordingUrl": "https://api.twilio.com/2010-04-01/Accounts/ACfake/Recordings/RE123",
        "RecordingDuration": "15",
        "From": "+919421140800",
        "CallSid": "CA999",
        "To": "+17372508034",
    })

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/xml"
    assert "<Response>" in resp.text
    assert "<Hangup/>" in resp.text

    # Verify a report was created in database
    reports = client.get("/api/reports?source=twilio").json()["items"]
    assert len(reports) > 0
    twilio_report = reports[0]
    assert twilio_report["source"] == "twilio"
    assert twilio_report["has_audio"] is True


def test_twilio_status_callback(client):
    """Verify status callback logs call state."""
    resp = client.post("/api/twilio/status", data={
        "CallSid": "CA123",
        "CallStatus": "completed",
        "CallDuration": "45",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_twilio_outbound_call_mocked(client, monkeypatch):
    """Verify outbound emergency call triggers Twilio API with right parameters."""
    dummy_req = httpx.Request("POST", "https://api.twilio.com/fake")

    class MockSettings:
        twilio_configured = True
        twilio_account_sid = "ACtest123"
        twilio_auth_token = "secret123"
        twilio_phone_number = "+17372508034"

    monkeypatch.setattr("app.api.twilio.settings", MockSettings())

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, data=None, **kwargs):
            assert "ACtest123" in url
            assert data["To"] == "+919421140800"
            assert data["From"] == "+17372508034"
            assert "/api/twilio/voice" in data["Url"]
            return httpx.Response(201, json={"sid": "CAoutbound123", "status": "queued"}, request=dummy_req)

    monkeypatch.setattr("httpx.AsyncClient", MockAsyncClient)

    resp = client.post("/api/twilio/call", json={
        "to_phone": "+919421140800",
        "language": "hi",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "call_initiated"
    assert data["call_sid"] == "CAoutbound123"


@pytest.fixture()
def anon(client):  # `client` boots the app and resets the database; this one holds no session cookie
    yield TestClient(app)


def test_twilio_webhooks_are_public_but_outbound_call_is_private(anon):
    """Twilio cannot log in, so its webhooks must stay open; starting calls must not."""
    assert anon.post("/api/twilio/voice", data={}).status_code == 200
    assert anon.get("/api/twilio/incoming").status_code == 200
    assert anon.post("/api/twilio/status", data={"CallSid": "CA1", "CallStatus": "completed"}).status_code == 200
    assert anon.post("/api/twilio/call", json={"to_phone": "+919421140800"}).status_code == 401
