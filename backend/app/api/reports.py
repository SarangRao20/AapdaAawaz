from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..db import get_db
from ..schemas import Language, ReportCreate, TranscriptSubmit
from ..services import review as review_svc
from ..services.acknowledgement import create_text_ack, synthesize_audio
from ..services.pipeline import PIPELINE_LOCK, audit, new_report_id
from ..services.settings_store import get_config
from ..services.storage import UploadError, store_audio
from ..services.worker import worker
from .serializers import ack_view, report_detail, report_summary

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _get(db: Session, report_id: str) -> models.Report:
    rep = db.get(models.Report, report_id)
    if rep is None:
        raise HTTPException(404, f"report {report_id} not found")
    return rep


def _get_for_caller(request: Request, db: Session, report_id: str) -> models.Report:
    """For routes the public caller app uses. Telegram and live calls hold real voices, so they need a login."""
    rep = _get(db, report_id)
    if rep.source in ("telegram", "live_call") and not request.state.authenticated:
        raise HTTPException(404, "report not found")
    return rep


@router.get("")
def list_reports(
    db: Session = Depends(get_db),
    status: str | None = Query(None, description="comma-separated report statuses"),
    language: str | None = None,
    needs_review: bool | None = None,
    source: str | None = None,
    q: str | None = Query(None, max_length=200, description="search transcript / id"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    stmt = select(models.Report)
    if status:
        stmt = stmt.where(models.Report.status.in_(status.split(",")))
    if source:
        stmt = stmt.where(models.Report.source == source)
    if language:
        detected = func.json_extract(models.Report.extraction_current, "$.language")
        stmt = stmt.where(or_(detected == language,
                              and_(models.Report.extraction_current.is_(None), models.Report.language_hint == language)))
    if needs_review is not None:
        stmt = stmt.where(models.Report.gate_status == ("needs_review" if needs_review else "passed"))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(models.Report.transcript.like(like), models.Report.id.like(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(models.Report.received_at.desc(), models.Report.id.desc())
                      .limit(limit).offset(offset)).all()
    ids = [r.id for r in rows]
    links = dict(db.execute(select(models.IncidentLink.report_id, models.IncidentLink.incident_id).where(
        models.IncidentLink.report_id.in_(ids), models.IncidentLink.active.is_(True))).all())
    pending = dict(db.execute(select(models.DuplicateSuggestion.report_id, func.count()).where(
        models.DuplicateSuggestion.report_id.in_(ids), models.DuplicateSuggestion.status == "pending")
        .group_by(models.DuplicateSuggestion.report_id)).all())
    return {"total": total, "limit": limit, "offset": offset, "worker_queue": worker.pending(),
            "items": [report_summary(r, links.get(r.id), pending.get(r.id, 0)) for r in rows]}


@router.post("", status_code=201)
def create_report(body: ReportCreate, db: Session = Depends(get_db)):
    if body.process and not body.transcript:
        raise HTTPException(422, "process=true requires a transcript (or upload audio to the report first)")
    rep = models.Report(id=new_report_id(), source=body.source, is_synthetic=False, language_hint=body.language_hint,
                        status="queued" if body.process else "received", review_reasons=[])
    if body.transcript:
        rep.transcript = body.transcript
        rep.transcript_source, rep.transcript_provider, rep.transcript_provider_mode = (
            "manual_entry", "dispatcher", "human")
    db.add(rep)
    audit(db, "report", rep.id, "created", new={"source": body.source, "has_transcript": bool(body.transcript)})
    db.commit()
    if body.process:
        worker.enqueue(rep.id)
    return report_detail(db, rep)


@router.post("/upload", status_code=201, summary="Create a report from an audio file and start processing")
async def upload_report(
    file: UploadFile = File(...),
    language_hint: Language | None = Form(None),
    source: Literal["upload", "recording"] = Form("upload"),
    db: Session = Depends(get_db),
):
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    try:
        stored = store_audio(data)
    except UploadError as exc:
        raise HTTPException(400, str(exc)) from exc
    rep = models.Report(id=new_report_id(), source=source, is_synthetic=False, language_hint=language_hint,
                        status="queued", review_reasons=[])
    db.add(rep)
    db.flush()
    db.add(models.AudioFile(report_id=rep.id, kind="caller_audio", original_filename=(file.filename or "audio")[:255],
                            stored_name=stored.stored_name, mime_type=stored.mime_type,
                            size_bytes=stored.size_bytes, sha256=stored.sha256))
    audit(db, "report", rep.id, "audio_uploaded", new={"bytes": stored.size_bytes, "mime": stored.mime_type})
    db.commit()
    worker.enqueue(rep.id)
    return report_detail(db, rep)


@router.post("/{report_id}/audio", status_code=201, summary="Attach audio to an existing report")
async def attach_audio(report_id: str, file: UploadFile = File(...), process: bool = Form(True),
                       db: Session = Depends(get_db)):
    rep = _get(db, report_id)
    if rep.status in ("queued", "transcribing", "extracting"):
        raise HTTPException(409, "report is currently being processed")
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    try:
        stored = store_audio(data)
    except UploadError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.add(models.AudioFile(report_id=rep.id, kind="caller_audio", original_filename=(file.filename or "audio")[:255],
                            stored_name=stored.stored_name, mime_type=stored.mime_type,
                            size_bytes=stored.size_bytes, sha256=stored.sha256))
    audit(db, "report", rep.id, "audio_uploaded", new={"bytes": stored.size_bytes, "mime": stored.mime_type})
    if process and not rep.transcript:
        rep.status = "queued"
    db.commit()
    if process and not rep.transcript:
        worker.enqueue(rep.id)
    return report_detail(db, rep)


@router.get("/{report_id}")
def get_report(report_id: str, request: Request, db: Session = Depends(get_db)):
    return report_detail(db, _get_for_caller(request, db, report_id))


@router.post("/{report_id}/process", status_code=202)
def process(report_id: str, db: Session = Depends(get_db)):
    rep = _get(db, report_id)
    if rep.status in ("queued", "transcribing", "extracting"):
        raise HTTPException(409, f"report is already {rep.status}")
    if not rep.transcript and not rep.audio_files:
        raise HTTPException(422, "report has neither a transcript nor audio")
    rep.status = "queued"
    audit(db, "report", rep.id, "processing_requested")
    db.commit()
    worker.enqueue(rep.id)
    return {"id": rep.id, "status": rep.status}


@router.post("/{report_id}/transcript", summary="Enter or correct a transcript manually (keeps the old one)")
def submit_transcript(report_id: str, body: TranscriptSubmit, db: Session = Depends(get_db)):
    _get(db, report_id)
    try:
        rep = review_svc.submit_transcript(db, report_id, body)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    if body.process:
        worker.enqueue(rep.id)
    return report_detail(db, rep)


@router.get("/{report_id}/audio/{audio_id}")
def get_audio(report_id: str, audio_id: int, db: Session = Depends(get_db)):
    a = db.get(models.AudioFile, audio_id)
    if a is None or a.report_id != report_id:
        raise HTTPException(404, "audio not found")
    path = settings.upload_dir / a.stored_name
    if not path.is_file():
        raise HTTPException(410, "audio file is no longer on disk")
    return FileResponse(path, media_type=a.mime_type, headers={"X-Content-Type-Options": "nosniff",
                                                               "Content-Disposition": "inline"})


@router.post("/{report_id}/acknowledgement")
def acknowledgement(report_id: str, request: Request, synthesize: bool = Query(True), db: Session = Depends(get_db)):
    rep = _get_for_caller(request, db, report_id)
    with PIPELINE_LOCK:
        ack = db.scalars(select(models.Acknowledgement).where(models.Acknowledgement.report_id == rep.id)
                         .order_by(models.Acknowledgement.id.desc())).first()
        if ack is None:
            ack = create_text_ack(db, rep, (rep.extraction_current or {}).get("language") or rep.language_hint)
        if synthesize and not ack.audio_stored_name:
            synthesize_audio(db, ack, get_config(db)["providers"]["tts"])
        db.commit()
    return ack_view(ack)


@router.get("/{report_id}/acknowledgement/audio")
def acknowledgement_audio(report_id: str, request: Request, db: Session = Depends(get_db)):
    _get_for_caller(request, db, report_id)
    ack = db.scalars(select(models.Acknowledgement).where(models.Acknowledgement.report_id == report_id,
                                                          models.Acknowledgement.audio_stored_name.is_not(None))
                     .order_by(models.Acknowledgement.id.desc())).first()
    if ack is None:
        raise HTTPException(404, "no synthesised acknowledgement audio for this report")
    path = settings.tts_dir / ack.audio_stored_name
    if not path.is_file():
        raise HTTPException(410, "audio file is no longer on disk")
    return FileResponse(path, media_type="audio/wav", headers={"X-Content-Type-Options": "nosniff"})
