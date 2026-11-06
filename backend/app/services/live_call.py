"""Awaaz Live: the conversation behind a realtime voice call.

`CallBrain` decides what to say next. `calls` is what the dispatcher's screen reads while a call runs.
The questions are fixed and only ever ask for facts, so the assistant can never improvise a promise of
rescue, and it never decides priority: that stays with the same explainable rules as every other report.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
import wave
from dataclasses import dataclass, field
from io import BytesIO

from .. import models
from ..config import settings
from ..db import SessionLocal
from ..services.pipeline import audit, mark_failed, new_report_id, process_report
from .acknowledgement import ack_language
from .extraction import extract, normalize
from .followup import _FALLBACK_QUESTIONS
from .storage import UploadError, store_audio
from .telegram_bot import _DONT_KNOW, TEXT, TelegramBot, required_missing

log = logging.getLogger("aapda.live")

SOURCE = "live_call"
MAX_ANSWER_ATTEMPTS = 2  # asks again once if an answer doesn't fill the field, then moves on
MAX_NUDGES = 2  # silence: repeats the question this many times, then ends the call
KEEP_FINISHED_S = 120  # how long a finished call stays on the dispatcher's screen

SPOKEN: dict[str, dict[str, str]] = {
    "greeting": {
        "hi": "आपदा आवाज़। जान का खतरा हो तो 112 पर भी कॉल करें। <pauses> बताइए, क्या हुआ, कहाँ, और कितने लोग हैं?",
        "mr": "आपदा आवाज. जिवाला धोका असल्यास 112 वरही कॉल करा. <pauses> सांगा, काय झाले, कुठे, आणि किती लोक आहेत?",
        "en": "Aapda Awaaz. If life is in danger, please also call 112. <pauses> Tell me what happened, where, and how many people.",
        "mixed": "Aapda Awaaz. Jaan ka khatra ho to 112 par bhi call karein. <pauses> Bataiye, kya hua, kahan, aur kitne log hain?",
    },
    "okay": {"hi": "ठीक है।", "mr": "ठीक आहे.", "en": "Okay.", "mixed": "Theek hai."},
    "again": {
        "hi": "माफ़ कीजिए, समझ नहीं आया।", "mr": "माफ करा, समजले नाही.",
        "en": "Sorry, I didn't catch that.", "mixed": "Maaf kijiye, samajh nahi aaya.",
    },
    "still_there": {
        "hi": "क्या आप सुन पा रहे हैं?", "mr": "तुम्हाला ऐकू येत आहे का?",
        "en": "Can you hear me?", "mixed": "Kya aap sun pa rahe hain?",
    },
    "recap": {"hi": "मैंने नोट किया:", "mr": "मी नोंदवले:", "en": "I have noted:", "mixed": "Maine note kiya:"},
    "ended_silent": {
        "hi": "जवाब नहीं मिला। जो जानकारी मिली है वह दर्ज है। कृपया 112 पर कॉल करें।",
        "mr": "उत्तर मिळाले नाही. मिळालेली माहिती नोंदवली आहे. कृपया 112 वर कॉल करा.",
        "en": "I didn't hear a reply. What you told me is recorded. Please call 112.",
        "mixed": "Jawab nahi mila. Jo jaankari mili hai woh record hai. Please 112 par call karein.",
    },
}
HAZARD_WORDS: dict[str, dict[str, str]] = {
    "flood": {"hi": "बाढ़", "mr": "पूर", "en": "flood", "mixed": "baadh"},
    "landslide": {"hi": "भूस्खलन", "mr": "दरड", "en": "landslide", "mixed": "landslide"},
    "earthquake": {"hi": "भूकंप", "mr": "भूकंप", "en": "earthquake", "mixed": "bhukamp"},
    "fire": {"hi": "आग", "mr": "आग", "en": "fire", "mixed": "aag"},
}

from .phrases_extra import HAZARD_WORDS as _HAZ_EXTRA, SPOKEN as _SPOKEN_EXTRA  # noqa: E402

for _key, _by_lang in _SPOKEN_EXTRA.items():
    SPOKEN[_key].update(_by_lang)
for _key, _by_lang in _HAZ_EXTRA.items():
    HAZARD_WORDS[_key].update(_by_lang)


def spoken(key: str, language: str) -> str:
    return SPOKEN[key][ack_language(language)]


@dataclass
class Turn:
    """What the assistant says next, and whether the call is over after it."""
    reply: str
    done: bool = False


def _facts(report: models.Report | None) -> dict:
    if report is None:
        return {"place": None, "disaster": None, "people": None, "priority": None, "score": None,
                "report_id": None, "needs_review": False}
    ext = report.extraction_current or {}
    location = ext.get("location") or {}
    disaster = ext.get("disaster_type")
    return {
        "place": location.get("place_name") if location.get("status") in ("grounded", "unmapped") else None,
        "disaster": disaster if disaster != "unknown" else None,
        "people": (ext.get("people_affected") or {}).get("count"),
        "priority": report.report_priority_label,
        "score": report.report_priority_score,
        "report_id": report.id,
        "needs_review": report.gate_status == "needs_review",
    }


@dataclass
class CallBrain:
    language: str
    report_id: str | None = None
    pending: str | None = None
    attempts: int = 0
    nudges: int = 0
    skipped: list[str] = field(default_factory=list)
    facts: dict = field(default_factory=lambda: _facts(None))

    def greeting(self) -> str:
        return spoken("greeting", self.language)

    def _question(self) -> str:
        return _FALLBACK_QUESTIONS[self.pending][ack_language(self.language)]

    def hear(self, text: str) -> Turn:
        """The caller said `text`. Runs the normal pipeline and picks the next question."""
        self.nudges = 0
        with SessionLocal() as db:
            report = db.get(models.Report, self.report_id) if self.report_id else None
            if report is None:
                if TelegramBot._is_small_talk(text):  # "hello?" isn't a report yet
                    return Turn(TEXT["describe"][ack_language(self.language)])
                report = self._create_report(db, text)
                filled = True
            else:
                if self.pending and normalize(text.strip()) in _DONT_KNOW:
                    self.skipped.append(self.pending)
                    self.pending = None
                    self.attempts = 0
                    return self._next(db, report, understood=True)
                merged, filled = TelegramBot._merge_answer(report, text, self.pending, ack_language(self.language))
                audit(db, "report", report.id, "live_call_answer", field=self.pending, new=text[:500])
                report.transcript = merged
            report = self._process(db, report)
            if self.pending and not filled:
                self.attempts += 1
                if self.attempts >= MAX_ANSWER_ATTEMPTS:
                    self.skipped.append(self.pending)
                    self.pending = None
                    self.attempts = 0
                    filled = True
            return self._next(db, report, understood=filled)

    def nudge(self) -> Turn:
        """The caller has gone quiet."""
        self.nudges += 1
        if self.nudges > MAX_NUDGES:
            return Turn(spoken("ended_silent", self.language), done=True)
        question = self._question() if self.pending else TEXT["describe"][ack_language(self.language)]
        return Turn(f"{spoken('still_there', self.language)} <pauses> {question}")

    def _create_report(self, db, text: str) -> models.Report:
        report = models.Report(id=new_report_id(), source=SOURCE, is_synthetic=False, status="queued",
                               language_hint=ack_language(self.language), review_reasons=[], transcript=text,
                               transcript_source="prisma_stream", transcript_provider=f"gnani-{settings.prisma_model}",
                               transcript_provider_mode="real")
        db.add(report)
        db.flush()
        audit(db, "report", report.id, "created", new={"source": SOURCE})
        self.report_id = report.id
        return report

    @staticmethod
    def _process(db, report: models.Report) -> models.Report:
        report_id = report.id
        db.commit()
        try:
            process_report(db, report_id)
        except Exception as exc:  # same contract as the worker: the failure shows on the report
            log.exception("processing %s failed", report_id)
            db.rollback()
            mark_failed(db, report_id, f"{type(exc).__name__}: {exc}")
        return db.get(models.Report, report_id)

    def _next(self, db, report: models.Report, understood: bool) -> Turn:
        self.facts = _facts(report)
        ext = report.extraction_current or {}
        missing = [f for f in required_missing(ext) if f not in self.skipped]
        if missing:
            if missing[0] != self.pending:
                self.attempts = 0
            self.pending = missing[0]
            report.follow_up_status = "pending"
            db.commit()
            lead = spoken("okay" if understood else "again", self.language)
            return Turn(f"{lead} <pauses> {self._question()}")
        self.pending = None
        report.follow_up_status = "answered"
        db.commit()
        return Turn(f"{self._recap()} <pauses> {TEXT['complete'][ack_language(self.language)]}", done=True)

    def _recap(self) -> str:
        language = ack_language(self.language)
        unknown = TEXT["summary_unknown"][language]
        hazard = HAZARD_WORDS.get(self.facts["disaster"] or "", {}).get(language) or unknown
        people = self.facts["people"] if self.facts["people"] is not None else unknown
        return (f"{spoken('recap', language)} {TEXT['summary_place'][language]}: {self.facts['place'] or unknown}. "
                f"{TEXT['summary_type'][language]}: {hazard}. {TEXT['summary_people'][language]}: {people}.")


def pcm_to_wav(pcm: bytes, rate: int) -> bytes:
    out = BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return out.getvalue()


def save_call_audio(report_id: str, pcm: bytes, rate: int) -> None:
    """Keep what the caller said with the report, like every other source. A failure here must not lose the report."""
    if not pcm:
        return
    try:
        stored = store_audio(pcm_to_wav(pcm, rate))
    except UploadError as exc:
        log.warning("could not keep the audio of %s: %s", report_id, exc)
        return
    with SessionLocal() as db:
        db.add(models.AudioFile(report_id=report_id, kind="caller_audio", original_filename="live-call.wav",
                                stored_name=stored.stored_name, mime_type=stored.mime_type,
                                size_bytes=stored.size_bytes, sha256=stored.sha256))
        db.commit()


class CallRegistry:
    """The calls happening right now, for the dispatcher's screen. Kept in memory: a finished call is a report."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls: dict[str, dict] = {}

    def start(self, language: str) -> str:
        call_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._calls[call_id] = {"id": call_id, "language": language, "state": "connecting", "started_at": time.time(),
                                    "ended_at": None, "turns": [], "facts": _facts(None), "asking_for": None,
                                    "last_response_ms": None}
        return call_id

    def update(self, call_id: str, **changes) -> None:
        with self._lock:
            if call_id in self._calls:
                self._calls[call_id].update(changes)

    def add_turn(self, call_id: str, speaker: str, text: str) -> None:
        with self._lock:
            if call_id in self._calls:
                self._calls[call_id]["turns"].append({"speaker": speaker, "text": text, "at": time.time()})

    def end(self, call_id: str) -> None:
        self.update(call_id, state="ended", ended_at=time.time())

    def snapshot(self) -> list[dict]:
        now = time.time()
        with self._lock:
            for call_id in [c["id"] for c in self._calls.values()
                            if c["ended_at"] and now - c["ended_at"] > KEEP_FINISHED_S]:
                del self._calls[call_id]
            return sorted(({**c, "turns": list(c["turns"])} for c in self._calls.values()),
                          key=lambda c: c["started_at"], reverse=True)

    def clear(self) -> None:
        with self._lock:
            self._calls.clear()


calls = CallRegistry()


__all__ = ["CallBrain", "Turn", "calls", "extract", "pcm_to_wav", "save_call_audio", "spoken"]
