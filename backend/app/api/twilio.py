"""Twilio PSTN voice intake for Aapda Awaaz.

Flow (inbound call):
    caller dials the Twilio number
      -> Twilio POSTs /api/twilio/voice        (TwiML: greet + record)
      -> Twilio POSTs /api/twilio/recording    (download WAV, create report, queue pipeline)
      -> Gnani Prisma transcribes, extraction/priority/dedup run as for any other report

The optional /api/twilio/call endpoint starts an outbound call to a citizen (useful on a
Twilio trial, where a caller cannot dial an Indian number) and points it at the same TwiML.
"""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..db import get_db
from ..services.pipeline import audit, new_report_id
from ..services.storage import UploadError, store_audio
from ..services.worker import worker

log = logging.getLogger("aapda.twilio")

router = APIRouter(prefix="/api/twilio", tags=["twilio"])

# Twilio <Say> only ships a fixed set of voices; mr is read with the Hindi voice.
_GREETING = {
    "hi": (
        "hi-IN",
        "आपदा आवाज़ आपातकालीन सेवा में आपका स्वागत है। कृपया अपनी आपातकालीन स्थिति, "
        "स्थान और फंसे हुए लोगों की संख्या बताएं।",
    ),
    "en": (
        "en-IN",
        "Welcome to Aapda Awaaz emergency service. Please describe your emergency, "
        "your location, and how many people are trapped.",
    ),
}
_EMPTY_RECORDING = {
    "hi": ("hi-IN", "हमें कोई आवाज़ नहीं मिली। यदि जान का खतरा है, तो कृपया तुरंत 112 पर कॉल करें।"),
    "en": ("en-IN", "We did not receive any audio. If a life is in danger, please call 112 now."),
}
_THANKS = {
    "hi": ("hi-IN", "आपकी आपातकालीन रिपोर्ट दर्ज कर ली गई है। आपदा नियंत्रण कक्ष को सूचित कर दिया गया है।"),
    "en": ("en-IN", "Your emergency report has been recorded and the disaster control room has been notified."),
}


def _language(value: str | None) -> str:
    return value if value in _GREETING else "hi"


def _twiml_response(content: str) -> Response:
    return Response(content=content, media_type="application/xml")


def _xml_attr(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


class OutboundCallRequest(BaseModel):
    to_phone: str
    language: str = "hi"


@router.api_route("/voice", methods=["GET", "POST"])
@router.api_route("/incoming", methods=["GET", "POST"])
async def incoming_voice_call(request: Request, lang: str | None = None):
    """Twilio webhook: greet the caller and record one voice report."""
    language = _language(lang)
    say_lang, greeting = _GREETING[language]
    empty_lang, empty_text = _EMPTY_RECORDING[language]
    recording_action = _xml_attr(
        f"{str(request.base_url).rstrip('/')}/api/twilio/recording?lang={language}")

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="{say_lang}">{greeting}</Say>
    <Pause length="1"/>
    <Record action="{recording_action}" method="POST" maxLength="30" playBeep="true" trim="trim-silence" timeout="4"/>
    <Say language="{empty_lang}">{empty_text}</Say>
    <Hangup/>
</Response>
"""
    return _twiml_response(twiml)


@router.post("/recording")
async def handle_recording(
    RecordingUrl: str = Form(...),
    RecordingDuration: str = Form("0"),
    From: str = Form(""),
    CallSid: str = Form(""),
    To: str = Form(""),
    lang: str | None = None,
    db: Session = Depends(get_db),
):
    """Twilio webhook: download the recording, store it, and queue the AI pipeline."""
    log.info("twilio recording from=%s call=%s duration=%ss", From, CallSid, RecordingDuration)
    language = _language(lang)

    auth = None
    if settings.twilio_account_sid and settings.twilio_auth_token:
        auth = (settings.twilio_account_sid, settings.twilio_auth_token)

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(f"{RecordingUrl}.wav", auth=auth)
            resp.raise_for_status()
            audio_data = resp.content
    except Exception as exc:
        log.error("failed to download twilio recording %s: %s", RecordingUrl, exc)
        raise HTTPException(status_code=502, detail=f"Failed to fetch audio recording: {exc}")

    try:
        stored = store_audio(audio_data)
    except UploadError as exc:
        log.error("failed to store twilio audio: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))

    rep = models.Report(
        id=new_report_id(),
        source="twilio",
        caller_phone=From or None,
        is_synthetic=False,
        language_hint=language,
        status="queued",
        review_reasons=[],
    )
    db.add(rep)
    db.flush()
    db.add(models.AudioFile(
        report_id=rep.id,
        kind="caller_audio",
        original_filename=f"twilio_{CallSid or rep.id}.wav",
        stored_name=stored.stored_name,
        mime_type=stored.mime_type,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
    ))
    audit(db, "report", rep.id, "twilio_call_ingested", new={
        "from": From, "to": To, "call_sid": CallSid,
        "duration_seconds": RecordingDuration, "recording_url": RecordingUrl,
    })
    db.commit()

    worker.enqueue(rep.id)
    log.info("twilio report queued: %s (caller %s)", rep.id, From)

    say_lang, thanks = _THANKS[language]
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="{say_lang}">{thanks}</Say>
    <Hangup/>
</Response>
"""
    return _twiml_response(twiml)


@router.post("/call")
async def place_outbound_call(body: OutboundCallRequest, request: Request):
    """Start an outbound call that runs the same emergency intake when answered."""
    if not settings.twilio_configured:
        raise HTTPException(status_code=503,
                            detail="Twilio credentials (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN) not configured.")

    language = _language(body.language)
    voice_url = f"{str(request.base_url).rstrip('/')}/api/twilio/voice?lang={language}"
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Calls.json"
    data = {"To": body.to_phone, "From": settings.twilio_phone_number, "Url": voice_url}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, data=data,
                                     auth=(settings.twilio_account_sid, settings.twilio_auth_token))
            if resp.status_code not in (200, 201):
                raise HTTPException(status_code=resp.status_code,
                                    detail=f"Twilio API error: {resp.text[:300]}")
            call_data = resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to place Twilio call: {exc}")

    return {
        "status": "call_initiated",
        "call_sid": call_data.get("sid"),
        "to": body.to_phone,
        "from": settings.twilio_phone_number,
    }


@router.api_route("/status", methods=["GET", "POST"])
async def call_status_callback(
    CallSid: str = Form(""),
    CallStatus: str = Form(""),
    CallDuration: str = Form("0"),
):
    """Twilio call status callback (ringing, answered, completed)."""
    log.info("twilio call %s status=%s duration=%ss", CallSid, CallStatus, CallDuration)
    return {"status": "ok", "call_sid": CallSid}
