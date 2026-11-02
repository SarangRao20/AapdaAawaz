"""Admin login: one account from .env, a signed session cookie, and a default-deny rule for /api.

Everything under /api needs a login unless it is listed in PUBLIC_ROUTES. Those routes are what the
public caller app needs to send a report and hear the reply; a new route is private until someone
decides otherwise. With no ADMIN_PASSWORD set nobody can log in, so a misconfigured server stays closed.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import threading
import time

from starlette.requests import Request

from .config import settings

SESSION_COOKIE = "aapda_session"
SESSION_SECONDS = 12 * 60 * 60
MAX_FAILURES = 5
LOCK_SECONDS = 60

# Without SESSION_SECRET the key lasts until the process restarts, which only logs people out.
_secret = (settings.session_secret or secrets.token_hex(32)).encode()

PUBLIC_ROUTES: list[tuple[str, re.Pattern[str]]] = [
    ("GET", re.compile(r"/api/health")),
    ("GET", re.compile(r"/api/auth/me")),
    ("POST", re.compile(r"/api/auth/log(in|out)")),
    # The caller app. Reports from Telegram are refused on the {id} routes: see reports.py.
    ("POST", re.compile(r"/api/reports")),
    ("POST", re.compile(r"/api/reports/upload")),
    ("GET", re.compile(r"/api/reports/[^/]+")),
    ("POST", re.compile(r"/api/reports/[^/]+/acknowledgement")),
    ("GET", re.compile(r"/api/reports/[^/]+/acknowledgement/audio")),
]


def is_public(method: str, path: str) -> bool:
    return any(method == m and pattern.fullmatch(path) for m, pattern in PUBLIC_ROUTES)


def _digest(value: str) -> bytes:
    # Hashing first makes the comparison independent of the length of the secret.
    return hashlib.sha256(value.encode()).digest()


def _same(a: str, b: str) -> bool:
    return hmac.compare_digest(_digest(a), _digest(b))


def login_configured() -> bool:
    return bool(settings.admin_password)


def check_credentials(username: str, password: str) -> bool:
    if not login_configured():
        return False
    # Evaluate both so a wrong username takes as long as a wrong password.
    username_ok = _same(username, settings.admin_username)
    password_ok = _same(password, settings.admin_password)
    return username_ok and password_ok


def _sign(payload: str) -> str:
    return hmac.new(_secret, payload.encode(), hashlib.sha256).hexdigest()


def create_session(username: str, now: float | None = None) -> str:
    expires = int((now if now is not None else time.time()) + SESSION_SECONDS)
    payload = base64.urlsafe_b64encode(f"{username}|{expires}".encode()).decode()
    return f"{payload}.{_sign(payload)}"


def session_username(token: str | None) -> str | None:
    """The logged-in username, or None for a missing, forged or expired session."""
    if not token or token.count(".") != 1:
        return None
    payload, signature = token.split(".")
    if not hmac.compare_digest(_sign(payload), signature):
        return None
    try:
        username, expires = base64.urlsafe_b64decode(payload).decode().rsplit("|", 1)
        if int(expires) <= time.time():
            return None
    except ValueError:
        return None
    # Changing ADMIN_USERNAME ends existing sessions.
    return username if login_configured() and username == settings.admin_username else None


def is_authenticated(request: Request) -> bool:
    header = request.headers.get("authorization", "")
    if settings.api_token and header.startswith("Bearer ") and _same(header[7:], settings.api_token):
        return True
    return session_username(request.cookies.get(SESSION_COOKIE)) is not None


class LoginThrottle:
    """Slows password guessing. One counter for the single account, kept in memory."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures = 0
        self._locked_until = 0.0

    def seconds_locked(self) -> int:
        with self._lock:
            return max(0, int(self._locked_until - time.time()) + 1) if self._locked_until > time.time() else 0

    def failed(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= MAX_FAILURES:
                self._failures = 0
                self._locked_until = time.time() + LOCK_SECONDS

    def reset(self) -> None:
        with self._lock:
            self._failures = 0
            self._locked_until = 0.0


login_throttle = LoginThrottle()
