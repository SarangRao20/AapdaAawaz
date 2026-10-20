"""Caller acknowledgements: reviewed wording — never promises rescue or arrival times.

Text is always produced. When Evon is configured, the text is personalised from the extracted
fields (location, people count, urgency) in the caller's language. Falls back to a static
template if Evon is unavailable or returns forbidden phrases.

Audio is only produced by a real TTS provider (Gnani Timbre); when none is available the
acknowledgement stays text-only and no audio is fabricated.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..providers.base import ProviderError, ProviderUnavailable
from ..providers.registry import get_tts

log = logging.getLogger("aapda.ack")

TEMPLATES = {
    "mr": "आपला संदेश मिळाला आहे. आपण दिलेली महत्त्वाची माहिती नोंदवली जात आहे. "
          "कृपया अधिकृत आपत्कालीन सेवांशीही संपर्क साधा.",
    "hi": "आपका संदेश मिल गया है। आपकी दी हुई ज़रूरी जानकारी दर्ज की जा रही है। "
          "कृपया आधिकारिक आपातकालीन सेवाओं से भी संपर्क करें।",
    "en": "Your message has been received. The important information you shared is being recorded. "
          "Please also contact official emergency services.",
    "mixed": "Aapka sandesh receive hua hai. Zaroori jaankari note ki ja rahi hai. "
             "Kripya official emergency services se bhi sampark karein.",
}
FORBIDDEN_PHRASES = ("guarantee", "on its way", "will arrive", "resolved", "पहुंच रही", "येत आहे")


def ack_language(language: str | None) -> str:
    return language if language in TEMPLATES else "mixed"


def _generate_evon_ack(ext: dict, language: str) -> str | None:
    """Try to generate a personalised acknowledgement via Evon. Returns None on any failure."""
    from ..providers.evon import EvonExtractor
    try:
        evon = EvonExtractor()
    except ProviderUnavailable:
        return None
    loc = ext.get("location") or {}
    location = loc.get("place_name") or loc.get("landmark")
    people = ext.get("people_affected") or {}
    people_count = people.get("count")
    urgency = ext.get("urgency", "unknown")
    summary = ext.get("summary") or ext.get("disaster_type", "disaster")
    try:
        text = evon.generate_ack(
            summary=summary,
            location=location,
            people_count=people_count,
            urgency=urgency,
            language=language,
        )
    except (ProviderError, ProviderUnavailable) as exc:
        log.debug("evon ack generation failed: %s", exc)
        return None
    if any(phrase.lower() in text.lower() for phrase in FORBIDDEN_PHRASES):
        log.warning("evon ack contained forbidden phrase; falling back to template")
        return None
    return text or None


def create_text_ack(
    db: Session,
    report: models.Report,
    language: str | None,
    ext: dict | None = None,
) -> models.Acknowledgement:
    lang = ack_language(language)
    text = TEMPLATES[lang]
    provider = "template"
    provider_mode = "template"

    if ext is not None and settings.gnani_key_configured and settings.extraction_provider == "evon":
        evon_text = _generate_evon_ack(ext, lang)
        if evon_text:
            text = evon_text
            provider = "gnani-evon-v3.3"
            provider_mode = "real"

    ack = models.Acknowledgement(
        report_id=report.id,
        language=lang,
        text=text,
        provider=provider,
        provider_mode=provider_mode,
        status="text_only",
    )
    db.add(ack)
    db.flush()
    return ack


def synthesize_audio(db: Session, ack: models.Acknowledgement, tts_mode: str | None = None) -> models.Acknowledgement:
    tts = get_tts(tts_mode)
    if tts is None:
        ack.status = "text_only"
        ack.error = "No text-to-speech provider configured (GNANI_API_KEY missing); no audio generated."
        return ack
    try:
        result = tts.synthesize(ack.text, ack.language)
    except ProviderError as exc:
        log.warning("timbre synthesis failed for %s: %s", ack.report_id, exc)
        ack.status, ack.error, ack.provider, ack.provider_mode = "audio_failed", str(exc), tts.name, tts.mode
        return ack
    settings.tts_dir.mkdir(parents=True, exist_ok=True)
    name = f"ack-{uuid.uuid4().hex}.wav"
    (settings.tts_dir / name).write_bytes(result.audio)
    ack.audio_stored_name = name
    ack.status, ack.error = "audio_ready", None
    ack.provider, ack.provider_mode = result.provider, result.mode
    return ack
