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
    prisma_default_language: str
    prisma_timeout_s: float
    prisma_max_retries: int
    timbre_model: str
    timbre_voices: dict[str, str]
    timbre_timeout_s: float
    timbre_max_retries: int

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

    @property
    def gnani_key_configured(self) -> bool:
        return bool(self.gnani_api_key)

# Dashboard dev server, caller-app dev server, and the caller APK's WebView (http://localhost).
DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:5174", "http://127.0.0.1:5174",
    "http://localhost",
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
        prisma_default_language=_env("PRISMA_DEFAULT_LANGUAGE", "hi-IN"),
        prisma_timeout_s=_env_float("PRISMA_TIMEOUT_S", 30.0),
        prisma_max_retries=_env_int("PRISMA_MAX_RETRIES", 3),
        timbre_model=_env("TIMBRE_MODEL", "timbre-v2.5"),
        # Voice names taken from the Gnani voice catalog (docs.gnani.ai/api/TTS/available-voices);
        # these voices exist only on timbre-v2.5, each with one preferred language code (see
        # TIMBRE_LANGUAGE_CODES). timbre-v3.0 has a different voice list and rejects them with HTTP 400.
        timbre_voices={
            "mr": _env("TIMBRE_VOICE_MR", "Ishaan"),
            "hi": _env("TIMBRE_VOICE_HI", "Nalini"),
            "en": _env("TIMBRE_VOICE_EN", "Kaveri"),
            "mixed": _env("TIMBRE_VOICE_MIXED", "Poorvi"),
        },
        timbre_timeout_s=_env_float("TIMBRE_TIMEOUT_S", 30.0),
        timbre_max_retries=_env_int("TIMBRE_MAX_RETRIES", 3),
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
    )


# Internal language -> Gnani BCP-47 codes (docs.gnani.ai/api/STT/speech-to-text, /api/TTS/tts-inference).
# Prisma has no Hinglish code; mixed Hindi-English speech is sent as hi-IN.
PRISMA_LANGUAGE_CODES = {"mr": "mr-IN", "hi": "hi-IN", "en": "en-IN", "mixed": "hi-IN"}
TIMBRE_LANGUAGE_CODES = {"mr": "mr-IN", "hi": "hi-IN", "en": "en-IN", "mixed": "hi-en"}

settings = load_settings()
