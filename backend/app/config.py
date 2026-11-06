"""Application configuration loaded from environment variables.

Secrets (API keys) are read here and never returned by any API endpoint or log line.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"

# Precedence: real environment variables > backend/.env > repo-root .env
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(REPO_ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    v = _env(name, "").lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no"):
        return False
    return default


@dataclass(frozen=True)
class Settings:
    var_dir: Path
    database_url: str
    upload_dir: Path
    tts_dir: Path
    cors_origins: list[str]
    max_upload_mb: int
    log_level: str

    # Gnani (vachana.ai) — documented at https://docs.gnani.ai
    gnani_api_key: str = field(repr=False)
    gnani_base_url: str
    stt_provider: str  # auto | prisma | mock
    tts_provider: str  # auto | timbre | none
    extraction_provider: str  # rules | evon
    prisma_model: str
    prisma_format: str
    prisma_default_language: str
    prisma_timeout_s: float
    prisma_max_retries: int
    timbre_model: str
    timbre_voices: dict[str, str]
    timbre_timeout_s: float
    # Live calls use audio tags, which only work on timbre-v3.0.
    live_timbre_model: str
    live_timbre_voice: str
    timbre_max_retries: int

    # Awaaz Live from the public caller app. Off unless switched on, and capped
    # because every call spends Gnani credits in real time.
    live_public: bool            # LIVE_PUBLIC
    live_max_concurrent: int     # LIVE_MAX_CONCURRENT — calls at once across all devices
    live_max_per_ip: int         # LIVE_MAX_PER_IP — calls at once from one address
    live_max_per_hour: int       # LIVE_MAX_PER_HOUR — calls started per address in an hour

    # Evon LLM extraction (OpenAI-compatible chat endpoint)
    evon_base_url: str          # EVON_BASE_URL
    evon_model: str             # EVON_MODEL
    evon_timeout_s: float       # EVON_TIMEOUT_S
    evon_max_retries: int       # EVON_MAX_RETRIES
    evon_api_key: str = field(repr=False)  # EVON_API_KEY — separate key for Evon/Groq (falls back to GNANI_API_KEY)

    # Optional enrichment
    geocoding_enabled: bool     # GEOCODING_ENABLED — Nominatim/OSM geocode for unmapped places
    audio_preprocessing_enabled: bool  # AUDIO_PREPROCESSING — spectral gate + RMS normalise before STT

    # Telegram intake (optional; the bot only starts when a token is set)
    telegram_bot_token: str = field(repr=False)
    telegram_api_base: str
    telegram_allowed_chat_ids: frozenset[int]  # empty = anyone who finds the bot
    telegram_followup_interval_s: int
    telegram_followup_max_attempts: int
    telegram_voice_replies: bool

    # Dashboard login (see app/auth.py). No password means nobody can log in.
    admin_username: str
    admin_password: str = field(repr=False)
    session_secret: str = field(repr=False)
    api_token: str = field(repr=False)
    cookie_secure: bool

    # Twilio Telephony (PSTN emergency voice call intake)
    twilio_account_sid: str = field(repr=False)  # TWILIO_ACCOUNT_SID
    twilio_auth_token: str = field(repr=False)   # TWILIO_AUTH_TOKEN
    twilio_phone_number: str                     # TWILIO_PHONE_NUMBER

    # Behind a reverse proxy (Caddy, nginx, a tunnel) every client looks like the proxy's address, which would make
    # the per-address live-call limits count everyone as one person. Only set this when a proxy you run is in front.
    trust_proxy: bool = False  # TRUST_PROXY

    @property
    def gnani_key_configured(self) -> bool:
        return bool(self.gnani_api_key)

    @property
    def twilio_configured(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_auth_token)


# Dashboard dev server, caller-app dev server, caller APK WebView, and the production domain
DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:5174", "http://127.0.0.1:5174",
    "http://localhost",
    "https://aapdaawaaz.duckdns.org",
)


def load_settings() -> Settings:
    var_dir = Path(_env("AAPDA_VAR_DIR", str(BACKEND_DIR / "var"))).resolve()
    db_url = _env("DATABASE_URL", f"sqlite:///{(var_dir / 'aapda.db').as_posix()}")
    origins = [o.strip() for o in _env(
        "CORS_ORIGINS", ",".join(DEFAULT_CORS_ORIGINS)).split(",") if o.strip()]
    return Settings(
        var_dir=var_dir,
        database_url=db_url,
        upload_dir=var_dir / "uploads",
        tts_dir=var_dir / "tts",
        cors_origins=origins,
        max_upload_mb=_env_int("MAX_UPLOAD_MB", 10),
        log_level=_env("LOG_LEVEL", "INFO").upper(),
        gnani_api_key=_env("GNANI_API_KEY"),
        gnani_base_url=_env("GNANI_BASE_URL", "https://api.vachana.ai").rstrip("/"),
        stt_provider=_env("STT_PROVIDER", "auto").lower(),
        tts_provider=_env("TTS_PROVIDER", "auto").lower(),
        extraction_provider=_env("EXTRACTION_PROVIDER", "rules").lower(),
        prisma_model=_env("PRISMA_MODEL", "prisma-v3.0"),
        prisma_format=_env("PRISMA_FORMAT", "verbatim"),
        prisma_default_language=_env("PRISMA_DEFAULT_LANGUAGE", "hi-IN"),
        prisma_timeout_s=_env_float("PRISMA_TIMEOUT_S", 30.0),
        prisma_max_retries=_env_int("PRISMA_MAX_RETRIES", 3),
        timbre_model=_env("TIMBRE_MODEL", "timbre-v3.0"),
        # Voices from the Timbre v3.0 catalog (all of them speak every supported
        # language). The v2.5 names — Nalini, Ishaan, Kaveri, Poorvi — are rejected
        # by v3.0 with HTTP 400, so do not copy them here.
        timbre_voices={
            "mr": _env("TIMBRE_VOICE_MR", "Shivani"),
            "hi": _env("TIMBRE_VOICE_HI", "Shivani"),
            "en": _env("TIMBRE_VOICE_EN", "Shivani"),
            "mixed": _env("TIMBRE_VOICE_MIXED", "Shivani"),
            **{c: _env(f"TIMBRE_VOICE_{c.upper()}", "Shivani") for c in ("bn", "gu", "kn", "ml", "pa", "ta", "te")},
        },
        timbre_timeout_s=_env_float("TIMBRE_TIMEOUT_S", 30.0),
        live_timbre_model=_env("LIVE_TIMBRE_MODEL", "timbre-v3.0"),
        live_timbre_voice=_env("LIVE_TIMBRE_VOICE", "Shivani"),
        timbre_max_retries=_env_int("TIMBRE_MAX_RETRIES", 3),
        live_public=_env_bool("LIVE_PUBLIC", False),
        live_max_concurrent=max(_env_int("LIVE_MAX_CONCURRENT", 6), 1),
        live_max_per_ip=max(_env_int("LIVE_MAX_PER_IP", 1), 1),
        live_max_per_hour=max(_env_int("LIVE_MAX_PER_HOUR", 10), 1),
        evon_base_url=_env("EVON_BASE_URL", "https://api.vachana.ai/v1").rstrip("/"),
        evon_model=_env("EVON_MODEL", "evon-v3.3"),
        evon_timeout_s=_env_float("EVON_TIMEOUT_S", 60.0),
        evon_max_retries=_env_int("EVON_MAX_RETRIES", 3),
        evon_api_key=_env("EVON_API_KEY"),  # if set, used instead of gnani_api_key for Evon/Groq
        geocoding_enabled=_env_bool("GEOCODING_ENABLED", False),
        audio_preprocessing_enabled=_env_bool("AUDIO_PREPROCESSING", False),
        telegram_bot_token=_env("TELEGRAM_BOT_TOKEN"),
        telegram_api_base=_env("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/"),
        telegram_allowed_chat_ids=frozenset(
            int(c) for c in _env("TELEGRAM_ALLOWED_CHAT_IDS").split(",") if c.strip().lstrip("-").isdigit()),
        telegram_followup_interval_s=max(_env_int("TELEGRAM_FOLLOWUP_INTERVAL_S", 120), 10),
        telegram_followup_max_attempts=max(_env_int("TELEGRAM_FOLLOWUP_MAX_ATTEMPTS", 3), 1),
        telegram_voice_replies=_env_bool("TELEGRAM_VOICE_REPLIES", True),
        admin_username=_env("ADMIN_USERNAME", "admin"),
        admin_password=_env("ADMIN_PASSWORD"),
        session_secret=_env("SESSION_SECRET"),
        api_token=_env("API_TOKEN"),
        cookie_secure=_env_bool("COOKIE_SECURE", False),
        twilio_account_sid=_env("TWILIO_ACCOUNT_SID"),
        twilio_auth_token=_env("TWILIO_AUTH_TOKEN"),
        twilio_phone_number=_env("TWILIO_PHONE_NUMBER", "+17372508034"),
        trust_proxy=_env_bool("TRUST_PROXY", False),
    )


# Internal language -> Gnani BCP-47 codes (docs.gnani.ai/api/STT/speech-to-text, /api/TTS/tts-inference).
# Prisma has no Hinglish code; mixed Hindi-English speech is sent as hi-IN.
from .services.languages import PRISMA_CODES as PRISMA_LANGUAGE_CODES, TIMBRE_CODES as TIMBRE_LANGUAGE_CODES  # noqa: E402,F401

settings = load_settings()
