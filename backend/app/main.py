"""FastAPI application entry point.

Run (from backend/):  .venv\\Scripts\\python -m uvicorn app.main:app --reload --port 8000
Interactive API docs: http://localhost:8000/docs
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import auth as auth_rules
from .api import auth, incidents, live, reports, system, twilio
from .config import settings
from .db import init_db
from .services.telegram_bot import telegram_runner
from .services.worker import worker

logging.basicConfig(level=settings.log_level,
                    format='{"t":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
log = logging.getLogger("aapda")
# httpx logs full request URLs at INFO, and Telegram URLs contain the bot token.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    worker.start()
    telegram_runner.start()
    log.info("started; gnani key configured=%s", settings.gnani_key_configured)
    if not auth_rules.login_configured():
        log.warning("ADMIN_PASSWORD is not set: nobody can log in to the dashboard")
    yield
    telegram_runner.stop()
    worker.stop()


app = FastAPI(
    title="Aapda Awaaz API",
    version="0.1.0",
    description="Decision-support prototype for triaging SYNTHETIC disaster voice reports. "
                "It does not dispatch responders or contact emergency services.",
    lifespan=lifespan,
)


@app.middleware("http")
async def require_login(request: Request, call_next):
    # scope["path"] is exactly what the router matches, so the two cannot disagree.
    path, method = request.scope["path"], request.method
    request.state.authenticated = auth_rules.is_authenticated(request)
    if (path.startswith("/api") and method != "OPTIONS" and not request.state.authenticated
            and not auth_rules.is_public(method, path)):
        return JSONResponse(status_code=401, content={"detail": "Log in to continue."})
    return await call_next(request)


# Added after require_login so it runs first and refusals keep their CORS headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(RequestValidationError)
async def validation_handler(_req: Request, exc: RequestValidationError):
    errors = [{"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]} for e in exc.errors()]
    summary = "; ".join(f"{e['field'] or 'request'}: {e['message']}" for e in errors)
    return JSONResponse(status_code=422, content={"detail": summary, "errors": errors})


app.include_router(auth.router)
app.include_router(live.router)
app.include_router(system.router)
app.include_router(reports.router)
app.include_router(incidents.router)
app.include_router(twilio.router)


# Optional offline basemap: drop a z/x/y PNG tile pack (plus manifest.json) into var/tiles.
_tiles = settings.var_dir / "tiles"
if _tiles.is_dir():
    app.mount("/tiles", StaticFiles(directory=_tiles), name="tiles")
