"""The login, and which routes stay open for the public caller app."""
from __future__ import annotations

import dataclasses
import time

import pytest
from fastapi.testclient import TestClient

from app import auth, models
from app.auth import MAX_FAILURES, SESSION_COOKIE, SESSION_SECONDS, create_session, login_throttle
from app.db import SessionLocal
from app.main import app
from tests.conftest import ADMIN_PASSWORD, API_TOKEN, wait_for


@pytest.fixture()
def anon(client):  # `client` starts the app and resets the database; this one has no session cookie
    login_throttle.reset()
    yield TestClient(app)
    login_throttle.reset()


def login(c, password=ADMIN_PASSWORD, username="admin"):
    return c.post("/api/auth/login", json={"username": username, "password": password})


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/reports"),
    ("GET", "/api/incidents"),
    ("GET", "/api/incidents/INC-0001"),
    ("GET", "/api/stats"),
    ("GET", "/api/settings"),
    ("GET", "/api/reports/R-1/audio/1"),
    ("POST", "/api/reports/R-1/process"),
    ("POST", "/api/reports/R-1/transcript"),
    ("POST", "/api/demo/reset"),
    ("GET", "/api/a-route-nobody-has-written-yet"),
])
def test_private_routes_refuse_anonymous_requests(anon, method, path):
    assert anon.request(method, path).status_code == 401


def test_caller_app_flow_works_without_logging_in(anon):
    created = anon.post("/api/reports", json={"transcript": "Flood in Nandwadi, 25 people are stuck",
                                              "language_hint": "en", "process": True})
    assert created.status_code == 201
    report = wait_for(anon, created.json()["id"])
    assert report["status"] == "processed"
    assert anon.post(f"/api/reports/{report['id']}/acknowledgement", params={"synthesize": "false"}).status_code == 200
    assert anon.get("/api/health").status_code == 200


def telegram_report() -> str:
    with SessionLocal() as db:
        db.add(models.Report(id="R-TELEGRAM", source="telegram", status="processed", review_reasons=[],
                             caller_latitude=18.5, caller_longitude=73.8))
        db.commit()
    return "R-TELEGRAM"


@pytest.mark.parametrize("method,suffix", [("GET", ""), ("POST", "/acknowledgement"),
                                           ("GET", "/acknowledgement/audio")])
def test_telegram_reports_are_hidden_from_the_public_routes(anon, method, suffix):
    rid = telegram_report()
    response = anon.request(method, f"/api/reports/{rid}{suffix}")
    assert response.status_code == 404 and "18.5" not in response.text


def test_logged_in_admin_can_read_telegram_reports(client, anon):
    rid = telegram_report()
    assert client.get(f"/api/reports/{rid}").json()["caller_location"]["latitude"] == 18.5


def test_login_sets_a_cookie_scripts_cannot_read_and_logout_ends_it(anon):
    response = login(anon)
    assert response.status_code == 200 and response.json()["username"] == "admin"
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and ADMIN_PASSWORD not in response.text
    assert anon.get("/api/reports").status_code == 200
    assert anon.get("/api/auth/me").json()["authenticated"] is True

    assert anon.post("/api/auth/logout").status_code == 200
    anon.cookies.clear()
    assert anon.get("/api/reports").status_code == 401


@pytest.mark.parametrize("username,password", [("admin", "wrong"), ("someone", ADMIN_PASSWORD)])
def test_wrong_credentials_are_refused_with_one_message(anon, username, password):
    response = login(anon, password, username)
    assert response.status_code == 401 and response.json()["detail"] == "Wrong username or password."
    assert SESSION_COOKIE not in response.cookies


def test_repeated_failures_lock_the_login_even_for_the_right_password(anon):
    for _ in range(MAX_FAILURES):
        assert login(anon, "wrong").status_code == 401
    assert login(anon).status_code == 429


def test_success_clears_the_failure_count(anon):
    for _ in range(MAX_FAILURES - 1):
        login(anon, "wrong")
    assert login(anon).status_code == 200
    anon.cookies.clear()
    assert login(anon, "wrong").status_code == 401


def test_forged_tampered_and_expired_sessions_are_refused(anon):
    good = create_session("admin")
    payload, signature = good.split(".")
    for token in [f"{payload}.{'0' * len(signature)}", f"{payload}x.{signature}", "nonsense", "a.b.c",
                  create_session("admin", now=time.time() - SESSION_SECONDS - 1), create_session("someone")]:
        anon.cookies.set(SESSION_COOKIE, token)
        assert anon.get("/api/reports").status_code == 401, token
    anon.cookies.set(SESSION_COOKIE, good)
    assert anon.get("/api/reports").status_code == 200


def test_api_token_opens_the_api_for_the_mcp_server(anon):
    assert anon.get("/api/incidents", headers={"Authorization": f"Bearer {API_TOKEN}"}).status_code == 200
    assert anon.get("/api/incidents", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_without_an_admin_password_nobody_can_log_in(anon, monkeypatch):
    monkeypatch.setattr(auth, "settings", dataclasses.replace(auth.settings, admin_password="", api_token=""))
    token = create_session("admin")
    monkeypatch.setattr("app.api.auth.settings", auth.settings)
    assert login(anon, "").status_code == 422
    assert login(anon, "anything").status_code == 503
    anon.cookies.set(SESSION_COOKIE, token)
    assert anon.get("/api/reports").status_code == 401
    assert anon.get("/api/auth/me").json() == {"authenticated": False, "username": None, "login_configured": False}


def test_settings_repr_hides_the_login_secrets():
    text = repr(auth.settings)
    assert ADMIN_PASSWORD not in text and API_TOKEN not in text
