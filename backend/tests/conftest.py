"""Test configuration: isolated temporary database, offline providers only."""
import os
import tempfile

# Must be set before the app is imported (config is read at import time).
os.environ["AAPDA_VAR_DIR"] = tempfile.mkdtemp(prefix="aapda-test-")
os.environ["GNANI_API_KEY"] = ""
ADMIN_PASSWORD = "test-admin-password"
API_TOKEN = "test-api-token"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = ADMIN_PASSWORD
os.environ["API_TOKEN"] = API_TOKEN
os.environ["COOKIE_SECURE"] = "false"
# A real token in .env must never make the test app poll the real bot and take its messages.
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["STT_PROVIDER"] = "mock"
os.environ["TTS_PROVIDER"] = "none"
os.environ["LOG_LEVEL"] = "WARNING"
# A developer's .env may switch public live calls on; the tests need a known default.
os.environ["LIVE_PUBLIC"] = "false"

import time  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services.settings_store import get_config  # noqa: E402


@pytest.fixture(scope="session")
def cfg():
    return get_config(None)


@pytest.fixture()
def client():
    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 200
        c.post("/api/demo/reset", json={})
        yield c


def wait_for(client, report_id, statuses=("processed", "needs_transcript", "failed"), timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/reports/{report_id}").json()
        if body["status"] in statuses:
            return body
        time.sleep(0.05)
    raise AssertionError(f"report {report_id} did not reach {statuses}; last status {body['status']}")
