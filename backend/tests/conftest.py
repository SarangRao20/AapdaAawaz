"""Test configuration: isolated temporary database, offline providers only."""
import os
import tempfile

# Must be set before the app is imported (config is read at import time).
os.environ["AAPDA_VAR_DIR"] = tempfile.mkdtemp(prefix="aapda-test-")
os.environ["GNANI_API_KEY"] = ""
os.environ["STT_PROVIDER"] = "mock"
os.environ["TTS_PROVIDER"] = "none"
os.environ["LOG_LEVEL"] = "WARNING"

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
