from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from ..auth import (
    SESSION_COOKIE,
    SESSION_SECONDS,
    check_credentials,
    create_session,
    is_authenticated,
    login_configured,
    login_throttle,
    session_username,
)
from ..config import settings

log = logging.getLogger("aapda.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=500)


@router.get("/me")
def me(request: Request):
    return {
        "authenticated": is_authenticated(request),
        "username": session_username(request.cookies.get(SESSION_COOKIE)),
        "login_configured": login_configured(),
    }


@router.post("/login")
def login(body: LoginRequest, response: Response):
    if not login_configured():
        raise HTTPException(503, "Login is not set up. Add ADMIN_PASSWORD to .env and restart the backend.")
    locked = login_throttle.seconds_locked()
    if locked:
        raise HTTPException(429, f"Too many failed attempts. Try again in {locked} seconds.")
    if not check_credentials(body.username, body.password):
        login_throttle.failed()
        log.warning("failed login attempt")
        raise HTTPException(401, "Wrong username or password.")
    login_throttle.reset()
    response.set_cookie(SESSION_COOKIE, create_session(settings.admin_username), max_age=SESSION_SECONDS,
                        httponly=True, samesite="lax", secure=settings.cookie_secure, path="/")
    return {"authenticated": True, "username": settings.admin_username, "login_configured": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, httponly=True, samesite="lax", secure=settings.cookie_secure, path="/")
    return {"authenticated": False, "username": None, "login_configured": login_configured()}
