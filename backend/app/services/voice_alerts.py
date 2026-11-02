"""Voice alerts: a dispatcher picks a safety message, and Timbre speaks it in each person's own language.

The messages are fixed text written in advance for each language. Gnani has no translation API, and a
machine translation of a safety instruction could say something dangerous, so nothing here is generated.
None of them promises that help is coming. A person always chooses to send: nothing goes out by itself.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..providers.base import ProviderError, ProviderUnavailable, SpeechResult
from ..providers.registry import get_tts
from .pipeline import audit
from .settings_store import get_config
from .telegram_bot import TelegramClient, TelegramError, wav_to_ogg_opus

log = logging.getLogger("aapda.alerts")

LANGUAGES = ("hi", "mr", "mixed", "en")

TEMPLATES: dict[str, dict] = {
    "move_to_high_ground": {
        "label": "Move to higher ground",
        "text": {
            "hi": "{place} के लिए सूचना। पानी बढ़ सकता है। जल्दी किसी ऊँची और सुरक्षित जगह पर जाइए। बिजली के तारों से दूर रहिए। जान का खतरा हो तो 112 पर कॉल करें।",
            "mr": "{place} साठी सूचना. पाणी वाढू शकते. लवकर उंच आणि सुरक्षित ठिकाणी जा. विजेच्या तारांपासून दूर राहा. जिवाला धोका असल्यास 112 वर कॉल करा.",
            "mixed": "{place} ke liye suchna. Paani badh sakta hai. Jaldi kisi oonchi aur surakshit jagah par jaiye. Bijli ke taaron se door rahiye. Jaan ka khatra ho to 112 par call karein.",
            "en": "Notice for {place}. Water may rise. Move quickly to higher, safe ground. Stay away from electric wires. If life is in danger, call 112.",
        },
    },
    "avoid_the_area": {
        "label": "Keep away from the area",
        "text": {
            "hi": "{place} के लिए सूचना। इस इलाके में खतरा बताया गया है। अभी उस तरफ़ मत जाइए और दूसरों को भी बताइए। जान का खतरा हो तो 112 पर कॉल करें।",
            "mr": "{place} साठी सूचना. या भागात धोका नोंदवला आहे. सध्या तिकडे जाऊ नका आणि इतरांनाही सांगा. जिवाला धोका असल्यास 112 वर कॉल करा.",
            "mixed": "{place} ke liye suchna. Is ilaake mein khatra bataya gaya hai. Abhi us taraf mat jaiye aur doosron ko bhi bataiye. Jaan ka khatra ho to 112 par call karein.",
            "en": "Notice for {place}. A danger has been reported in this area. Do not go there for now, and tell others. If life is in danger, call 112.",
        },
    },
    "report_received_keep_safe": {
        "label": "Report seen, stay safe",
        "text": {
            "hi": "{place} के बारे में आपकी रिपोर्ट एक डिस्पैचर ने देखी है। इससे मदद पहुँचने की गारंटी नहीं है। सुरक्षित जगह पर रहिए और 112 पर भी कॉल करें।",
            "mr": "{place} बद्दलचा तुमचा अहवाल डिस्पॅचरने पाहिला आहे. यामुळे मदत मिळण्याची हमी नाही. सुरक्षित ठिकाणी राहा आणि 112 वरही कॉल करा.",
            "mixed": "{place} ke baare mein aapki report ek dispatcher ne dekhi hai. Isse madad pahunchne ki guarantee nahi hai. Surakshit jagah par rahiye aur 112 par bhi call karein.",
            "en": "A dispatcher has seen your report about {place}. This does not guarantee help. Stay somewhere safe, and please also call 112.",
        },
    },
}


class AlertError(Exception):
    pass


def place_name(incident: models.Incident) -> str:
    return (incident.location or {}).get("place_name") or "your area"


def alert_text(template: str, language: str, place: str) -> str:
    try:
        return TEMPLATES[template]["text"][language].format(place=place)
    except KeyError as exc:
        raise AlertError(f"unknown alert or language: {exc}") from None


def templates_for(incident: models.Incident) -> list[dict]:
    place = place_name(incident)
    return [{"id": key, "label": value["label"], "text": {lang: alert_text(key, lang, place) for lang in LANGUAGES}}
            for key, value in TEMPLATES.items()]


@lru_cache(maxsize=64)
def _speak_cached(text: str, language: str, mode: str | None) -> SpeechResult:
    """The same words in the same language reuse audio already paid for."""
    tts = get_tts(mode)
    if tts is None:
        raise ProviderUnavailable("text to speech is off")
    return tts.synthesize(text, language)


def speak(db: Session, template: str, language: str, place: str) -> SpeechResult:
    return _speak_cached(alert_text(template, language, place), language, get_config(db)["providers"]["tts"])


def recipients(db: Session, incident_id: str) -> list[tuple[int, str]]:
    """Telegram chats that reported this incident, with each one's language. Only they have contacted us."""
    rows = db.execute(
        select(models.TelegramConversation.chat_id, models.TelegramConversation.language)
        .join(models.IncidentLink, models.IncidentLink.report_id == models.TelegramConversation.report_id)
        .where(models.IncidentLink.incident_id == incident_id, models.IncidentLink.active.is_(True))
        .order_by(models.TelegramConversation.id)
    ).all()
    chats = dict(rows)  # a later conversation's language replaces an earlier one's
    return [(chat, language if language in LANGUAGES else "hi") for chat, language in chats.items()]


def telegram_client() -> TelegramClient:
    return TelegramClient(settings.telegram_bot_token, settings.telegram_api_base)


def send(db: Session, incident: models.Incident, template: str, actor: str) -> dict:
    if template not in TEMPLATES:
        raise AlertError("unknown alert")
    chats = recipients(db, incident.id)
    if not chats:
        return {"sent": 0, "failed": 0, "voice": 0, "languages": []}
    if not settings.telegram_bot_token:
        raise AlertError("The Telegram bot isn't configured, so this alert can't be delivered.")
    client = telegram_client()
    place = place_name(incident)
    sent = failed = voice = 0
    languages: set[str] = set()
    for chat_id, language in chats:
        try:
            client.send_message(chat_id, alert_text(template, language, place))
        except TelegramError as exc:
            log.warning("could not deliver an alert: %s", exc)
            failed += 1
            continue
        sent += 1
        languages.add(language)
        # The words have arrived by now, so a failed voice note only loses the audio.
        try:
            ogg = wav_to_ogg_opus(speak(db, template, language, place).audio)
            if ogg:
                client.send_voice(chat_id, ogg)
                voice += 1
        except (ProviderError, ProviderUnavailable, TelegramError) as exc:
            log.warning("alert voice note failed: %s", exc)
    audit(db, "incident", incident.id, "voice_alert_sent", actor=actor,
          new={"template": template, "sent": sent, "failed": failed, "voice": voice})
    db.commit()
    return {"sent": sent, "failed": failed, "voice": voice, "languages": sorted(languages)}
