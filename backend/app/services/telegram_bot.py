"""Telegram intake: a caller reports by voice, text or GPS, and the bot chases missing fields itself.

Uses long polling, so no public URL is needed. Telegram bots cannot place phone or voice calls, so the
"automated call" is the bot messaging the person first: it sends each missing question as text and a
voice note, then repeats it on a timer until it is answered, skipped or the attempts run out.

Every report goes through the normal pipeline, so it appears in the dashboard like any other.
The bot token is a secret: it is part of every Telegram URL, so URLs and HTTP exceptions are never logged.
"""
from __future__ import annotations

import io
import logging
import struct
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..db import SessionLocal
from ..providers.base import ProviderError, ProviderUnavailable
from ..providers.registry import get_stt, get_tts
from .acknowledgement import TEMPLATES, ack_language
from .extraction import extract
from .followup import _FALLBACK_QUESTIONS, missing_fields
from .pipeline import as_utc, audit, mark_failed, new_report_id, process_report, utcnow
from .settings_store import get_config
from .storage import MAX_SECONDS, UploadError, store_audio
from .text_utils import normalize, tokenize

log = logging.getLogger("aapda.telegram")

OFFSET_KEY = "telegram_offset"
ADD_DETAILS_WINDOW = timedelta(minutes=60)  # later messages start a new report
POLL_TIMEOUT_S = 10  # also how often reminders are checked
LANG_BUTTONS = {"हिंदी": "hi", "मराठी": "mr", "English": "en", "Hinglish": "mixed"}

TEXT: dict[str, dict[str, str]] = {
    "welcome": {
        "hi": "आपदा आवाज़: यह एक प्रोटोटाइप है, आधिकारिक आपातकालीन सेवा नहीं। जान का खतरा हो तो तुरंत 112 पर कॉल करें।\n\n"
              "बोलकर (वॉइस नोट) या लिखकर बताएं: क्या हुआ, कहाँ, और कितने लोग प्रभावित हैं। आप अपनी लोकेशन भी भेज सकते हैं।",
        "mr": "आपदा आवाज: हा एक प्रोटोटाइप आहे, अधिकृत आपत्कालीन सेवा नाही. जिवाला धोका असल्यास लगेच 112 वर कॉल करा.\n\n"
              "बोलून (व्हॉइस नोट) किंवा लिहून सांगा: काय झाले, कुठे, आणि किती लोक प्रभावित आहेत. तुम्ही तुमचे लोकेशनही पाठवू शकता.",
        "en": "Aapda Awaaz: this is a prototype, not an official emergency service. If life is in danger, call 112 now.\n\n"
              "Tell me by voice note or text: what happened, where, and how many people are affected. "
              "You can also share your location.",
        "mixed": "Aapda Awaaz: yeh ek prototype hai, official emergency service nahi. Jaan ka khatra ho to turant 112 par call karein.\n\n"
                 "Voice note ya text mein batayein: kya hua, kahan, aur kitne log affected hain. Aap apni location bhi bhej sakte hain.",
    },
    "describe": {
        "hi": "कृपया बताएं: क्या हुआ, कहाँ, और कितने लोग प्रभावित हैं।",
        "mr": "कृपया सांगा: काय झाले, कुठे, आणि किती लोक प्रभावित आहेत.",
        "en": "Please tell me what happened, where, and how many people are affected.",
        "mixed": "Please batayein: kya hua, kahan, aur kitne log affected hain.",
    },
    "location_saved": {
        "hi": "आपकी लोकेशन मिल गई है।", "mr": "तुमचे लोकेशन मिळाले आहे.",
        "en": "Got your location.", "mixed": "Aapki location mil gayi hai.",
    },
    "share_location": {
        "hi": "📍 लोकेशन भेजें", "mr": "📍 लोकेशन पाठवा", "en": "📍 Share location", "mixed": "📍 Location bhejein",
    },
    "dont_know": {"hi": "पता नहीं", "mr": "माहीत नाही", "en": "Don't know", "mixed": "Pata nahi"},
    "location_tip": {
        "hi": "आप नीचे का बटन दबाकर अपनी लोकेशन भी भेज सकते हैं।",
        "mr": "तुम्ही खालचे बटण दाबून तुमचे लोकेशनही पाठवू शकता.",
        "en": "You can also tap the button below to share your location.",
        "mixed": "Aap neeche ka button dabakar apni location bhi bhej sakte hain.",
    },
    "reminder": {
        "hi": "अभी भी यह जानकारी चाहिए:", "mr": "अजूनही ही माहिती हवी आहे:",
        "en": "We still need this:", "mixed": "Abhi bhi yeh jaankari chahiye:",
    },
    "unheard": {
        "hi": "आपकी आवाज़ समझ नहीं आई। कृपया लिखकर बताएं, या दोबारा वॉइस नोट भेजें।",
        "mr": "तुमचा आवाज समजला नाही. कृपया लिहून सांगा, किंवा पुन्हा व्हॉइस नोट पाठवा.",
        "en": "I couldn't understand that audio. Please type it, or send the voice note again.",
        "mixed": "Aapki awaaz samajh nahi aayi. Please likh kar batayein, ya voice note dobara bhejein.",
    },
    "too_long": {
        "hi": f"वॉइस नोट {MAX_SECONDS} सेकंड से छोटा रखें।", "mr": f"व्हॉइस नोट {MAX_SECONDS} सेकंदांपेक्षा लहान ठेवा.",
        "en": f"Please keep voice notes under {MAX_SECONDS} seconds.",
        "mixed": f"Voice note {MAX_SECONDS} second se chhota rakhein.",
    },
    "complete": {
        "hi": "धन्यवाद, आपकी रिपोर्ट दर्ज हो गई है और एक डिस्पैचर इसकी समीक्षा करेगा। इससे मदद पहुँचने की गारंटी नहीं है, कृपया 112 पर भी कॉल करें।",
        "mr": "धन्यवाद, तुमचा अहवाल नोंदवला आहे आणि डिस्पॅचर त्याचे पुनरावलोकन करेल. यामुळे मदत मिळण्याची हमी नाही, कृपया 112 वरही कॉल करा.",
        "en": "Thank you, your report is recorded and a dispatcher will review it. This does not guarantee help, so please also call 112.",
        "mixed": "Dhanyavaad, aapki report record ho gayi hai aur dispatcher ise review karega. Isse madad ki guarantee nahi hai, please 112 par bhi call karein.",
    },
    "gave_up": {
        "hi": "जवाब नहीं मिला, इसलिए हम दोबारा नहीं पूछेंगे। जो जानकारी मिली है वह दर्ज है। जब चाहें जवाब भेज सकते हैं। कृपया 112 पर भी कॉल करें।",
        "mr": "उत्तर मिळाले नाही, म्हणून आम्ही पुन्हा विचारणार नाही. मिळालेली माहिती नोंदवली आहे. केव्हाही उत्तर पाठवू शकता. कृपया 112 वरही कॉल करा.",
        "en": "No reply, so I'll stop asking. What you told me is recorded, and you can still reply any time. Please also call 112.",
        "mixed": "Jawab nahi mila, isliye hum dobara nahi poochhenge. Jo jaankari mili hai woh record hai. Kabhi bhi jawab bhej sakte hain. Please 112 par bhi call karein.",
    },
    "error": {
        "hi": "कुछ गड़बड़ हो गई। कृपया दोबारा भेजें, और जान का खतरा हो तो 112 पर कॉल करें।",
        "mr": "काहीतरी चूक झाली. कृपया पुन्हा पाठवा, आणि जिवाला धोका असल्यास 112 वर कॉल करा.",
        "en": "Something went wrong. Please send that again, and call 112 if life is in danger.",
        "mixed": "Kuch gadbad ho gayi. Please dobara bhejein, aur jaan ka khatra ho to 112 par call karein.",
    },
    "summary_title": {"hi": "दर्ज जानकारी:", "mr": "नोंदवलेली माहिती:", "en": "Recorded:", "mixed": "Record ki gayi jaankari:"},
    "summary_type": {"hi": "घटना", "mr": "घटना", "en": "Type", "mixed": "Type"},
    "summary_place": {"hi": "स्थान", "mr": "ठिकाण", "en": "Place", "mixed": "Jagah"},
    "summary_people": {"hi": "लोग", "mr": "लोक", "en": "People", "mixed": "Log"},
    "summary_unknown": {"hi": "पता नहीं", "mr": "माहीत नाही", "en": "not known", "mixed": "pata nahi"},
    "summary_gps": {"hi": "आपकी भेजी लोकेशन", "mr": "तुम्ही पाठवलेले लोकेशन", "en": "your shared location", "mixed": "aapki bheji location"},
    "summary_id": {"hi": "रिपोर्ट नंबर", "mr": "अहवाल क्रमांक", "en": "Report ID", "mixed": "Report ID"},
}
_DONT_KNOW = {normalize(w) for w in (
    *TEXT["dont_know"].values(), "dont know", "don't know", "do not know", "not sure", "no idea", "skip", "unknown",
    "pata nahi", "pata nahin", "nahi pata", "मालूम नहीं", "पता नहीं", "नहीं पता", "माहित नाही", "माहीत नाही",
)}
# Added to a bare answer ("25", "Kesarwadi") so the extractor can read it as a count or a place.
_PEOPLE_SUFFIX = {"hi": "लोग", "mr": "लोक", "en": "people", "mixed": "log"}
_PLACE_SUFFIX = {"hi": "गांव", "mr": "गाव", "en": "gaon", "mixed": "gaon"}


class TelegramError(Exception):
    """Telegram call failed. The message never contains the URL, because the URL contains the token."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class TelegramClient:
    def __init__(self, token: str, base_url: str = "https://api.telegram.org",
                 transport: httpx.BaseTransport | None = None):
        self._api = f"{base_url.rstrip('/')}/bot{token}"
        self._files = f"{base_url.rstrip('/')}/file/bot{token}"
        self._http = httpx.Client(timeout=POLL_TIMEOUT_S + 20, transport=transport)

    def _call(self, method: str, **kwargs) -> dict | list | bool:
        try:
            resp = self._http.post(f"{self._api}/{method}", **kwargs)
        except httpx.HTTPError as exc:
            raise TelegramError(f"{method}: {type(exc).__name__}") from None
        try:
            body = resp.json()
        except ValueError:
            raise TelegramError(f"{method}: HTTP {resp.status_code}, not JSON", resp.status_code) from None
        if not body.get("ok"):
            raise TelegramError(f"{method}: {body.get('description', resp.status_code)}", resp.status_code)
        return body["result"]

    def get_me(self) -> dict:
        return self._call("getMe")

    def get_updates(self, offset: int | None, timeout: int = POLL_TIMEOUT_S) -> list[dict]:
        return self._call("getUpdates", json={"offset": offset, "timeout": timeout, "allowed_updates": ["message"]})

    def send_message(self, chat_id: int, text: str, reply_markup: dict | None = None) -> None:
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        self._call("sendMessage", json=payload)

    def send_voice(self, chat_id: int, ogg: bytes) -> None:
        self._call("sendVoice", data={"chat_id": chat_id}, files={"voice": ("reply.ogg", ogg, "audio/ogg")})

    def download_file(self, file_id: str) -> bytes:
        path = self._call("getFile", json={"file_id": file_id})["file_path"]
        try:
            resp = self._http.get(f"{self._files}/{path}")
        except httpx.HTTPError as exc:
            raise TelegramError(f"download: {type(exc).__name__}") from None
        if resp.status_code != 200:
            raise TelegramError(f"download: HTTP {resp.status_code}", resp.status_code)
        return resp.content


def wav_to_ogg_opus(wav: bytes) -> bytes | None:
    """Telegram voice notes must be OGG Opus; Timbre returns WAV. None if conversion is not possible."""
    try:
        import soundfile as sf
    except ImportError:
        log.warning("soundfile is not installed; sending text without a voice note")
        return None
    try:
        i = wav.find(b"data")
        if wav[:4] == b"RIFF" and i > 0:  # Timbre streams WAV, so its header holds placeholder sizes
            wav = (b"RIFF" + struct.pack("<I", len(wav) - 8) + wav[8:i + 4]
                   + struct.pack("<I", len(wav) - i - 8) + wav[i + 8:])
        samples, rate = sf.read(io.BytesIO(wav), always_2d=False)
        out = io.BytesIO()
        sf.write(out, samples, rate, format="OGG", subtype="OPUS")
        return out.getvalue()
    except Exception as exc:  # a voice note is a bonus: the text has already been sent
        log.warning("could not convert reply to a voice note: %s", type(exc).__name__)
        return None


def required_missing(ext: dict) -> list[str]:
    """Fields the bot must chase. A possible match or generic landmark still needs a real place."""
    missing = [f for f in missing_fields(ext) if f != "location_missing"]
    loc = ext.get("location") or {}
    if not ext.get("caller_gps") and loc.get("status") not in ("grounded", "unmapped"):
        missing.insert(0, "location_missing")
    return missing


def _lang(conv: models.TelegramConversation) -> str:
    return ack_language(conv.language)


def _text(key: str, conv: models.TelegramConversation) -> str:
    return TEXT[key][_lang(conv)]


def question_for(field_key: str, conv: models.TelegramConversation) -> str:
    q = _FALLBACK_QUESTIONS[field_key][_lang(conv)]
    return f"{q}\n{_text('location_tip', conv)}" if field_key == "location_missing" else q


@dataclass
class TelegramBot:
    client: TelegramClient
    followup_interval_s: int = 120
    max_attempts: int = 3
    voice_replies: bool = True
    allowed_chat_ids: frozenset[int] = frozenset()
    _voice_cache: dict[tuple[str, str], bytes] = field(default_factory=dict)  # reminders reuse paid audio

    # ---- sending ------------------------------------------------------------------------
    def _keyboard(self, conv: models.TelegramConversation, field_key: str | None) -> dict:
        if field_key is None:
            return {"keyboard": [[{"text": _text("share_location", conv), "request_location": True}]],
                    "resize_keyboard": True}
        rows = []
        if field_key == "location_missing":
            rows.append([{"text": _text("share_location", conv), "request_location": True}])
        rows.append([{"text": _text("dont_know", conv)}])
        return {"keyboard": rows, "resize_keyboard": True, "one_time_keyboard": True}

    def _send_voice(self, db: Session, chat_id: int, text: str, language: str) -> None:
        """Best effort: a failed voice note must never block the conversation."""
        if not self.voice_replies:
            return
        ogg = self._voice_cache.get((language, text))
        if ogg is None:
            tts = get_tts(get_config(db)["providers"]["tts"])
            if tts is None:
                return
            try:
                ogg = wav_to_ogg_opus(tts.synthesize(text, language).audio)
            except ProviderError as exc:
                log.warning("voice note failed: %s", exc)
                return
            if ogg is None:
                return
            if len(self._voice_cache) >= 64:
                self._voice_cache.clear()
            self._voice_cache[(language, text)] = ogg
        try:
            self.client.send_voice(chat_id, ogg)
        except TelegramError as exc:
            log.warning("could not send voice note: %s", exc)

    def _ask(self, db: Session, conv: models.TelegramConversation, intro: str | None = None) -> None:
        question = question_for(conv.pending_field, conv)
        text = f"{intro}\n\n{question}" if intro else question
        self.client.send_message(conv.chat_id, text, self._keyboard(conv, conv.pending_field))
        spoken = _FALLBACK_QUESTIONS[conv.pending_field][_lang(conv)]
        self._send_voice(db, conv.chat_id, f"{intro} {spoken}" if intro else spoken, _lang(conv))
        conv.next_followup_at = utcnow() + timedelta(seconds=self.followup_interval_s)

    # ---- conversation state -------------------------------------------------------------
    @staticmethod
    def _current(db: Session, chat_id: int) -> models.TelegramConversation | None:
        return db.scalars(select(models.TelegramConversation).where(models.TelegramConversation.chat_id == chat_id)
                          .order_by(models.TelegramConversation.id.desc())).first()

    def _start_new(self, db: Session, chat_id: int, language: str, locked: bool) -> models.TelegramConversation:
        conv = models.TelegramConversation(chat_id=chat_id, language=language, language_locked=locked, state="new",
                                           attempts=0, skipped_fields=[])
        db.add(conv)
        db.flush()
        return conv

    def _conversation(self, db: Session, chat_id: int, sender_language: str | None) -> models.TelegramConversation:
        conv = self._current(db, chat_id)
        stale = (conv is not None and conv.state in ("complete", "incomplete") and conv.report_id
                 and utcnow() - as_utc(conv.updated_at) > ADD_DETAILS_WINDOW)
        if conv is None or stale:
            language = conv.language if conv and conv.language_locked else (
                sender_language if sender_language in ("hi", "mr", "en") else "hi")
            conv = self._start_new(db, chat_id, language, bool(conv and conv.language_locked))
        return conv

    # ---- after the pipeline has run -----------------------------------------------------
    def _advance(self, db: Session, conv: models.TelegramConversation, report: models.Report,
                 intro: str | None = None) -> None:
        if report.status in ("needs_transcript", "failed"):
            conv.state, conv.pending_field, conv.next_followup_at = "needs_text", None, None
            self.client.send_message(conv.chat_id, _text("unheard", conv), self._keyboard(conv, None))
            return
        ext = report.extraction_current or {}
        if not conv.language_locked and ext.get("language") in TEMPLATES:
            conv.language = ext["language"]
        if intro == "ack":
            intro = TEMPLATES[_lang(conv)]
        skipped = set(conv.skipped_fields or [])
        missing = [f for f in required_missing(ext) if f not in skipped]
        if missing:
            if missing[0] != conv.pending_field:
                conv.attempts = 0
            conv.state, conv.pending_field = "collecting", missing[0]
            report.follow_up_status = "pending"
            self._ask(db, conv, intro)
            return
        conv.state, conv.pending_field, conv.next_followup_at = "complete", None, None
        report.follow_up_status = "answered"
        parts = [intro] if intro else []
        parts += [self._summary(conv, report), _text("complete", conv)]
        self.client.send_message(conv.chat_id, "\n\n".join(parts), {"remove_keyboard": True})

    @staticmethod
    def _summary(conv: models.TelegramConversation, report: models.Report) -> str:
        ext = report.extraction_current or {}
        unknown = _text("summary_unknown", conv)
        loc = ext.get("location") or {}
        place = loc.get("place_name") if loc.get("status") in ("grounded", "unmapped") else None
        if ext.get("caller_gps"):
            place = f"{place} ({_text('summary_gps', conv)})" if place else _text("summary_gps", conv)
        count = (ext.get("people_affected") or {}).get("count")
        hazard = ext.get("disaster_type")
        return "\n".join([
            _text("summary_title", conv),
            f"{_text('summary_type', conv)}: {hazard if hazard not in (None, 'unknown') else unknown}",
            f"{_text('summary_place', conv)}: {place or unknown}",
            f"{_text('summary_people', conv)}: {count if count is not None else unknown}",
            f"{_text('summary_id', conv)}: {report.id}",
        ])

    def _process(self, db: Session, report: models.Report) -> None:
        db.commit()
        try:
            process_report(db, report.id)
        except Exception as exc:  # same contract as the worker: surface the failure on the report
            log.exception("processing %s failed", report.id)
            db.rollback()
            mark_failed(db, report.id, f"{type(exc).__name__}: {exc}")

    # ---- creating and extending reports -------------------------------------------------
    def _new_report(self, db: Session, conv: models.TelegramConversation, transcript: str | None,
                    audio: bytes | None) -> models.Report | None:
        report = models.Report(id=new_report_id(), source="telegram", is_synthetic=False, language_hint=_lang(conv),
                               status="queued", review_reasons=[], caller_latitude=conv.pending_latitude,
                               caller_longitude=conv.pending_longitude,
                               caller_location_accuracy_m=conv.pending_accuracy_m)
        if audio is not None:
            try:
                stored = store_audio(audio)
            except UploadError as exc:
                log.info("rejected Telegram audio: %s", exc)
                self.client.send_message(conv.chat_id, _text("unheard", conv))
                return None
            db.add(report)
            db.flush()
            db.add(models.AudioFile(report_id=report.id, kind="caller_audio", original_filename="telegram-voice.ogg",
                                    stored_name=stored.stored_name, mime_type=stored.mime_type,
                                    size_bytes=stored.size_bytes, sha256=stored.sha256))
        else:
            report.transcript = transcript
            report.transcript_source, report.transcript_provider, report.transcript_provider_mode = (
                "manual_entry", "telegram", "human")
            db.add(report)
            db.flush()
        audit(db, "report", report.id, "created", new={"source": "telegram", "has_audio": audio is not None})
        conv.report_id = report.id
        conv.pending_latitude = conv.pending_longitude = conv.pending_accuracy_m = None
        return report

    def _transcribe_answer(self, db: Session, conv: models.TelegramConversation, report: models.Report,
                           audio: bytes) -> str | None:
        """Keeps the follow-up recording on the report and returns its text, or None if it can't be read."""
        try:
            stored = store_audio(audio)
        except UploadError as exc:
            log.info("rejected Telegram audio: %s", exc)
            return None
        db.add(models.AudioFile(report_id=report.id, kind="caller_followup", original_filename="telegram-answer.ogg",
                                stored_name=stored.stored_name, mime_type=stored.mime_type,
                                size_bytes=stored.size_bytes, sha256=stored.sha256))
        try:
            stt = get_stt(get_config(db)["providers"]["stt"])
            result = stt.transcribe(settings.upload_dir / stored.stored_name, stored.mime_type, _lang(conv))
        except (ProviderError, ProviderUnavailable) as exc:
            log.warning("could not transcribe a Telegram answer: %s", exc)
            return None
        return (result.transcript or "").strip() or None

    @staticmethod
    def _merge_answer(report: models.Report, answer: str, pending: str | None, language: str) -> tuple[str, bool]:
        """(new transcript, whether the pending field is now filled). Adds a noun to a bare answer if needed."""
        base = f"{report.transcript}\n{answer}" if report.transcript else answer
        options = [base]
        if pending == "people_unknown":
            options.append(f"{base} {_PEOPLE_SUFFIX.get(language, 'log')}")
        elif pending == "location_missing":
            options.append(f"{base} {_PLACE_SUFFIX.get(language, 'gaon')}")
        for option in options:
            ext = extract(option, report.language_hint).model_dump()
            if report.caller_latitude is not None:
                ext["caller_gps"] = {"latitude": report.caller_latitude, "longitude": report.caller_longitude}
            if pending is None or pending not in required_missing(ext):
                return option, True
        return base, False

    def _on_content(self, db: Session, conv: models.TelegramConversation, text: str | None, audio: bytes | None) -> None:
        report = db.get(models.Report, conv.report_id) if conv.report_id else None

        if report is None or report.status in ("needs_transcript", "failed"):
            if report is None and text is not None and self._is_small_talk(text):
                self.client.send_message(conv.chat_id, _text("describe", conv), self._keyboard(conv, None))
                return
            if report is None:
                report = self._new_report(db, conv, text, audio)
                if report is None:
                    return
            else:  # the first attempt could not be read; this is a retry of the same report
                answer = text if text is not None else self._transcribe_answer(db, conv, report, audio)
                if answer is None:
                    self.client.send_message(conv.chat_id, _text("unheard", conv))
                    return
                report.transcript = answer
                report.transcript_source, report.transcript_provider, report.transcript_provider_mode = (
                    "manual_entry", "telegram", "human")
            self._process(db, report)
            self._advance(db, conv, db.get(models.Report, report.id), intro="ack")
            return

        answer = text if text is not None else self._transcribe_answer(db, conv, report, audio)
        if answer is None:
            conv.next_followup_at = utcnow() + timedelta(seconds=self.followup_interval_s)
            self.client.send_message(conv.chat_id, _text("unheard", conv))
            return

        pending = conv.pending_field
        if pending and normalize(answer.strip()) in _DONT_KNOW:
            self._skip_pending(db, conv, report)
            return
        merged, filled = self._merge_answer(report, answer, pending, _lang(conv))
        audit(db, "report", report.id, "telegram_answer", field=pending, new=answer[:500])
        report.transcript = merged
        self._process(db, report)
        report = db.get(models.Report, report.id)
        if pending and not filled and report.status == "processed":
            conv.attempts += 1
            if conv.attempts >= self.max_attempts:
                self._skip_pending(db, conv, report)
                return
        self._advance(db, conv, report)

    def _skip_pending(self, db: Session, conv: models.TelegramConversation, report: models.Report) -> None:
        conv.skipped_fields = [*(conv.skipped_fields or []), conv.pending_field]
        conv.pending_field, conv.attempts = None, 0
        self._advance(db, conv, report)

    @staticmethod
    def _is_small_talk(text: str) -> bool:
        tokens = tokenize(text)
        if len(tokens) >= 4:
            return False
        ext = extract(text, None)
        return (ext.disaster_type == "unknown" and not ext.reported_danger and not ext.immediate_needs
                and ext.location.status == "missing")

    def _on_location(self, db: Session, conv: models.TelegramConversation, location: dict) -> None:
        lat, lon, acc = location["latitude"], location["longitude"], location.get("horizontal_accuracy")
        report = db.get(models.Report, conv.report_id) if conv.report_id else None
        if report is None:
            conv.pending_latitude, conv.pending_longitude, conv.pending_accuracy_m = lat, lon, acc
            self.client.send_message(conv.chat_id, f"{_text('location_saved', conv)}\n\n{_text('describe', conv)}")
            return
        report.caller_latitude, report.caller_longitude, report.caller_location_accuracy_m = lat, lon, acc
        audit(db, "report", report.id, "telegram_location", new={"accuracy_m": acc})
        if report.transcript:  # otherwise the audio could not be read yet; keep waiting for text
            self._process(db, report)
            report = db.get(models.Report, report.id)
        self._advance(db, conv, report, intro=_text("location_saved", conv))

    # ---- entry points -------------------------------------------------------------------
    def handle_update(self, db: Session, update: dict) -> None:
        msg = update.get("message") or {}
        chat = msg.get("chat") or {}
        if chat.get("type") != "private":
            return
        chat_id = chat["id"]
        if self.allowed_chat_ids and chat_id not in self.allowed_chat_ids:
            log.info("ignored a message from a chat that is not on the allowlist")
            return
        sender_language = (msg.get("from") or {}).get("language_code")
        text = (msg.get("text") or "").strip()

        if text in ("/start", "/new") or text.startswith("/start "):
            previous = self._current(db, chat_id)
            locked = bool(previous and previous.language_locked)
            language = previous.language if locked else (sender_language if sender_language in ("hi", "mr", "en") else "hi")
            conv = self._start_new(db, chat_id, language, locked)
            keyboard = {"keyboard": [[{"text": b} for b in LANG_BUTTONS],
                                     [{"text": _text("share_location", conv), "request_location": True}]],
                        "resize_keyboard": True}
            self.client.send_message(chat_id, _text("welcome", conv), keyboard)
            db.commit()
            return

        conv = self._conversation(db, chat_id, sender_language)
        if text in LANG_BUTTONS:
            conv.language, conv.language_locked = LANG_BUTTONS[text], True
            if conv.pending_field:
                self._ask(db, conv)
            else:
                self.client.send_message(chat_id, _text("describe", conv), self._keyboard(conv, None))
            db.commit()
            return

        location = msg.get("location")
        if location:
            self._on_location(db, conv, location)
            db.commit()
            return

        media = msg.get("voice") or msg.get("audio")
        if media:
            if (media.get("duration") or 0) > MAX_SECONDS:
                self.client.send_message(chat_id, _text("too_long", conv))
                db.commit()
                return
            self._on_content(db, conv, None, self.client.download_file(media["file_id"]))
        elif text and not text.startswith("/"):
            self._on_content(db, conv, text, None)
        else:
            self.client.send_message(chat_id, _text("describe", conv), self._keyboard(conv, None))
        db.commit()

    def send_due_followups(self, db: Session, now: datetime | None = None) -> int:
        """The automated follow-up: repeat each unanswered question, then stop after max_attempts."""
        now = now or utcnow()
        due = db.scalars(select(models.TelegramConversation).where(
            models.TelegramConversation.state == "collecting",
            models.TelegramConversation.next_followup_at.is_not(None))).all()
        sent = 0
        for conv in due:
            if as_utc(conv.next_followup_at) > now:
                continue
            conv.attempts += 1
            try:
                if conv.attempts >= self.max_attempts:
                    report = db.get(models.Report, conv.report_id)
                    report.follow_up_status = "unanswered"
                    audit(db, "report", report.id, "telegram_followup_unanswered", field=conv.pending_field)
                    conv.state, conv.next_followup_at = "incomplete", None
                    self.client.send_message(conv.chat_id, _text("gave_up", conv), {"remove_keyboard": True})
                else:
                    self._ask(db, conv, _text("reminder", conv))
                sent += 1
            except TelegramError as exc:
                log.warning("follow-up not delivered: %s", exc)
                conv.next_followup_at = now + timedelta(seconds=self.followup_interval_s)
            db.commit()
        return sent


class TelegramRunner:
    """Background long-polling thread. Starts only when TELEGRAM_BOT_TOKEN is set."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.username: str | None = None
        self.state = "not_configured"

    def status(self) -> dict:
        return {"configured": bool(settings.telegram_bot_token), "state": self.state, "username": self.username}

    def start(self) -> None:
        if not settings.telegram_bot_token or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self.state = "starting"
        self._thread = threading.Thread(target=self._loop, name="aapda-telegram", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=POLL_TIMEOUT_S + 5)
        self.state = "stopped" if settings.telegram_bot_token else "not_configured"

    def _loop(self) -> None:
        client = TelegramClient(settings.telegram_bot_token, settings.telegram_api_base)
        bot = TelegramBot(client, settings.telegram_followup_interval_s, settings.telegram_followup_max_attempts,
                          settings.telegram_voice_replies, settings.telegram_allowed_chat_ids)
        try:
            self.username = client.get_me().get("username")
        except TelegramError as exc:
            self.state = "error"
            log.error("Telegram bot not started: %s. Check TELEGRAM_BOT_TOKEN.", exc)
            return
        self.state = "running"
        log.info("Telegram bot running as @%s", self.username)
        backoff = 1
        while not self._stop.is_set():
            try:
                self._poll_once(client, bot)
                backoff, self.state = 1, "running"
            except TelegramError as exc:
                self.state = "error"
                hint = " (another copy of this bot is running)" if exc.status_code == 409 else ""
                log.warning("Telegram polling failed: %s%s", exc, hint)
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 60)
            except Exception:
                log.exception("Telegram loop error")
                self._stop.wait(5)

    def _poll_once(self, client: TelegramClient, bot: TelegramBot) -> None:
        db = SessionLocal()
        try:
            row = db.get(models.AppSetting, OFFSET_KEY)
            updates = client.get_updates(row.value if row else None)
            for update in updates:
                try:
                    bot.handle_update(db, update)
                except Exception as exc:
                    # Message content can be personal, so log only the error type and tell the caller.
                    log.exception("Telegram update failed: %s", type(exc).__name__)
                    db.rollback()
                    self._apologise(client, db, update)
                row = db.get(models.AppSetting, OFFSET_KEY)
                if row is None:
                    db.add(models.AppSetting(key=OFFSET_KEY, value=update["update_id"] + 1))
                else:
                    row.value = update["update_id"] + 1
                db.commit()  # saved per update, so a restart never replays a report
            bot.send_due_followups(db)
        finally:
            db.close()

    @staticmethod
    def _apologise(client: TelegramClient, db: Session, update: dict) -> None:
        chat_id = ((update.get("message") or {}).get("chat") or {}).get("id")
        if chat_id is None:
            return
        conv = TelegramBot._current(db, chat_id)
        language = ack_language(conv.language) if conv else "en"
        try:
            client.send_message(chat_id, TEXT["error"][language])
        except TelegramError:
            pass


telegram_runner = TelegramRunner()
