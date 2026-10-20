"""Provider selection and status reporting (never exposes secret values)."""
from __future__ import annotations

from ..config import settings
from .base import ProviderUnavailable, SpeechToText, TextToSpeech
from .mock_stt import MockFixtureSTT
from .prisma import PrismaSTT
from .timbre import TimbreTTS


def get_stt(mode_override: str | None = None) -> SpeechToText:
    """auto: Prisma when GNANI_API_KEY is set, otherwise the clearly-labelled mock."""
    mode = (mode_override or settings.stt_provider or "auto").lower()
    if mode == "mock":
        return MockFixtureSTT()
    if mode == "prisma":
        return PrismaSTT()  # raises ProviderUnavailable without a key
    try:
        return PrismaSTT()
    except ProviderUnavailable:
        return MockFixtureSTT()


def get_tts(mode_override: str | None = None) -> TextToSpeech | None:
    """Returns None when no real TTS is available; callers must show a text-only state."""
    mode = (mode_override or settings.tts_provider or "auto").lower()
    if mode == "none":
        return None
    try:
        return TimbreTTS()
    except ProviderUnavailable:
        return None


def provider_status(stt_mode: str | None = None, tts_mode: str | None = None) -> dict:
    key = settings.gnani_key_configured
    stt = get_stt(stt_mode) if (stt_mode or settings.stt_provider) != "prisma" or key else None
    tts = get_tts(tts_mode)
    return {
        "gnani_api_key_configured": key,
        "gnani_base_url": settings.gnani_base_url,
        "speech_to_text": {
            "active": stt.name if stt else None,
            "mode": stt.mode if stt else "unavailable",
            "prisma_available": key,
            "note": None if key else "No GNANI_API_KEY: mock STT only recognises bundled synthetic fixture audio.",
        },
        "extraction": {
            "active": "gnani-evon-v3.3" if (key and settings.extraction_provider == "evon") else "rule-based-v1",
            "mode": "real" if (key and settings.extraction_provider == "evon") else "rule_based",
            "evon_available": key and settings.extraction_provider == "evon",
            "note": (
                None if (key and settings.extraction_provider == "evon")
                else "Set EXTRACTION_PROVIDER=evon (and GNANI_API_KEY) to use Gnani Evon v3.3 extraction."
            ),
        },
        "text_to_speech": {
            "active": tts.name if tts else None,
            "mode": tts.mode if tts else "unavailable",
            "timbre_available": key,
            "note": None if tts else "No TTS provider: acknowledgements are text-only; no audio is fabricated.",
        },
    }
