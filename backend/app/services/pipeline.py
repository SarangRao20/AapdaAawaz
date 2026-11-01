"""Report processing pipeline (database orchestration around the pure services).

transcription -> extraction -> priority + confidence gate -> deduplication -> incident refresh
-> acknowledgement. Every stage is recorded as a ProcessingJob with provider, mode and timing.
"""
from __future__ import annotations

import logging
import secrets
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..providers.base import ProviderError, ProviderUnavailable
from ..providers.evon import EvonExtractor
from ..providers.registry import get_stt
from . import aggregation, gate, matching
from . import priority as prio
from .acknowledgement import create_text_ack
from .followup import generate_questions, missing_fields, needs_followup
from .extraction import extract
from .settings_store import get_config

log = logging.getLogger("aapda.pipeline")

# Serialises every mutation of incidents/links so concurrent requests and the worker
# cannot both create an incident for the same new report.
PIPELINE_LOCK = threading.RLock()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def new_report_id() -> str:
    return f"R-{utcnow():%Y%m%d-%H%M%S}-{secrets.token_hex(2).upper()}"


def audit(db: Session, entity_type: str, entity_id: str, action: str, *, field: str | None = None,
          old=None, new=None, actor: str = "system", note: str | None = None) -> None:
    db.add(models.AuditLog(entity_type=entity_type, entity_id=entity_id, action=action, field=field,
                           old_value=old, new_value=new, actor=actor, note=note))


def create_incident(db: Session) -> models.Incident:
    seq = (db.scalar(select(func.max(models.Incident.seq))) or 0) + 1
    inc = models.Incident(id=f"INC-{seq:04d}", seq=seq, status="active", human_overrides={},
                          needs=[], dangers=[], languages=[], review_reasons=[], contradictions=[], missing_info=[])
    db.add(inc)
    db.flush()
    audit(db, "incident", inc.id, "created")
    return inc


@contextmanager
def stage(db: Session, report: models.Report, name: str, provider: str | None = None, mode: str | None = None):
    job = models.ProcessingJob(report_id=report.id, stage=name, provider=provider, provider_mode=mode,
                               status="running", started_at=utcnow())
    db.add(job)
    db.flush()
    t0 = time.perf_counter()
    try:
        yield job
    except Exception as exc:
        job.status, job.error = "failed", str(exc)[:500]
        raise
    finally:
        job.finished_at = utcnow()
        job.duration_ms = round((time.perf_counter() - t0) * 1000, 2)
        if job.status == "running":
            job.status = "succeeded"


def _set_status(db: Session, report: models.Report, status: str) -> None:
    report.status = status
    db.commit()  # make progress visible to the polling UI


# ---------------------------------------------------------------------------
# incident refresh
# ---------------------------------------------------------------------------
def active_members(db: Session, incident_id: str) -> list[tuple[models.IncidentLink, models.Report]]:
    rows = db.execute(
        select(models.IncidentLink, models.Report)
        .join(models.Report, models.Report.id == models.IncidentLink.report_id)
        .where(models.IncidentLink.incident_id == incident_id, models.IncidentLink.active.is_(True))
        .order_by(models.Report.received_at)
    ).all()
    return [(link, rep) for link, rep in rows if rep.extraction_current]


def member_view(rep: models.Report) -> aggregation.Member:
    return aggregation.Member(rep.id, rep.extraction_current, as_utc(rep.received_at), rep.transcript,
                              rep.review_reasons or [], rep.review_resolved)


def pending_suggestions_for(db: Session, incident_id: str) -> list[models.DuplicateSuggestion]:
    return list(db.scalars(select(models.DuplicateSuggestion).where(
        models.DuplicateSuggestion.status == "pending",
        (models.DuplicateSuggestion.source_incident_id == incident_id)
        | (models.DuplicateSuggestion.candidate_incident_id == incident_id))))


def refresh_incident(db: Session, inc: models.Incident, cfg: dict) -> None:
    members = active_members(db, inc.id)
    inc.updated_at = utcnow()
    if not members:
        inc.report_count = 0
        if inc.status == "active":
            inc.status = "merged" if inc.merged_into_id else "closed"
        for s in pending_suggestions_for(db, inc.id):
            s.status, s.resolved_at, s.resolved_by = "obsolete", utcnow(), "system"
            s.note = f"incident {inc.id} no longer has reports"
        return
    if inc.status != "active":
        inc.status, inc.merged_into_id = "active", None
    overrides = dict(inc.human_overrides or {})
    agg = aggregation.aggregate([member_view(r) for _, r in members], overrides, cfg)
    f = agg["fields"]
    for key in ("disaster_type", "location", "location_status", "latitude", "longitude", "people_count",
                "people_detail", "vulnerable", "needs", "dangers", "medical_emergency", "urgency", "languages",
                "summary", "priority_score", "priority_label", "priority_breakdown", "info_confidence",
                "contradictions", "missing_info", "recommended_action", "report_count", "last_report_at"):
        setattr(inc, key, f[key])

    pending = [{"id": s.id, "score": s.score, "contradictions": s.contradictions or [],
                "created_at": as_utc(s.created_at),
                "other_incident_id": s.candidate_incident_id if s.source_incident_id == inc.id else s.source_incident_id}
               for s in pending_suggestions_for(db, inc.id)]
    all_low = all((r.extraction_current or {}).get("transcript_quality") == "low" for _, r in members)
    reasons = gate.incident_reasons(f, pending, all_low, overrides.get("acknowledged_contradictions", []), cfg)
    inc.review_reasons = reasons

    reviewed_at = overrides.get("reviewed_at")
    if reviewed_at:
        reviewed_dt = datetime.fromisoformat(reviewed_at)
        # Only information that arrived after the review re-opens it.
        newer = any(as_utc(link.created_at) > reviewed_dt and not rep.review_resolved for link, rep in members)
        new_suggestion = any(p["created_at"] and p["created_at"] > reviewed_dt for p in pending)
        inc.review_status = "rereview_needed" if (new_suggestion or (newer and reasons)) else "reviewed"
    else:
        inc.review_status = "needs_review" if reasons else "no_review_required"


def incident_profiles(db: Session, cfg: dict, exclude: set[str] | None = None) -> dict[str, matching.Profile]:
    rows = db.execute(
        select(models.IncidentLink.incident_id, models.Report, models.Incident.human_overrides)
        .join(models.Report, models.Report.id == models.IncidentLink.report_id)
        .join(models.Incident, models.Incident.id == models.IncidentLink.incident_id)
        .where(models.IncidentLink.active.is_(True), models.Incident.status == "active")
    ).all()
    grouped: dict[str, list] = {}
    overrides: dict[str, dict] = {}
    for iid, rep, ov in rows:
        if rep.extraction_current and iid not in (exclude or set()):
            grouped.setdefault(iid, []).append(member_view(rep))
            overrides[iid] = ov or {}
    return {iid: aggregation.aggregate(ms, overrides[iid], cfg)["profile"] for iid, ms in grouped.items()}


def update_report_gate(db: Session, report: models.Report) -> None:
    pending = db.scalar(select(func.count()).select_from(models.DuplicateSuggestion).where(
        models.DuplicateSuggestion.report_id == report.id, models.DuplicateSuggestion.status == "pending"))
    report.gate_status = "needs_review" if (report.review_reasons or pending) else "passed"


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------
def process_report(db: Session, report_id: str) -> models.Report | None:
    with PIPELINE_LOCK:
        report = db.get(models.Report, report_id)
        if report is None:
            return None
        cfg = get_config(db)
        t_start = time.perf_counter()
        report.error = None
        log.info("▶  pipeline start  report=%s  lang=%s", report.id, report.language_hint or "auto")

        # 1. transcription ---------------------------------------------------
        if not report.transcript:
            audio = report.audio_files[-1] if report.audio_files else None
            if audio is None:
                with stage(db, report, "transcription") as job:
                    job.status, job.detail = "skipped", {"reason": "no audio and no transcript"}
                log.info("✗  transcription   no audio and no transcript → needs_transcript")
                report.status = "needs_transcript"
                db.commit()
                return report
            log.info("   transcription   audio=%s  size=%.1f KB  stt=%s",
                     audio.original_filename, audio.size_bytes / 1024,
                     cfg["providers"]["stt"])
            _set_status(db, report, "transcribing")
            try:
                stt = get_stt(cfg["providers"]["stt"])
            except ProviderUnavailable as exc:
                with stage(db, report, "transcription", "gnani-prisma", "real") as job:
                    job.status, job.error = "failed", str(exc)
                log.info("✗  transcription   STT unavailable: %s", exc)
                report.status, report.stt_error = "failed", f"Speech-to-text unavailable: {exc}"
                db.commit()
                return report
            path = settings.upload_dir / audio.stored_name
            if settings.audio_preprocessing_enabled:
                from .audio_prep import preprocess_audio
                with stage(db, report, "audio_prep", "audio-prep-v1", "local") as prep_job:
                    path = preprocess_audio(path)
                    prep_job.detail = {"output": path.name}
            try:
                with stage(db, report, "transcription", stt.name, stt.mode) as job:
                    res = stt.transcribe(path, audio.mime_type, report.language_hint)
                    job.detail = {"note": res.note, "language_code": res.language_code, "request_id": res.request_id}
                    if not (res.transcript or "").strip():
                        job.status = "no_result"
            except ProviderError as exc:
                log.info("✗  transcription   ProviderError: %s", exc)
                report.status, report.stt_error = "failed", str(exc)
                db.commit()
                return report
            report.transcript_provider, report.transcript_provider_mode = res.provider, res.mode
            report.transcript_request_id, report.transcript_raw = res.request_id, res.raw
            if not (res.transcript or "").strip():
                log.info("✗  transcription   empty result → needs_transcript  note=%s", res.note)
                report.status = "needs_transcript"
                report.stt_error = res.note or "Speech-to-text returned no transcript"
                db.commit()
                return report
            report.transcript = res.transcript
            report.transcript_source = "prisma" if res.mode == "real" else "mock_fixture_lookup"
            report.stt_error = None
            log.info("✓  transcription   provider=%s  mode=%s  lang=%s  chars=%d",
                     res.provider, res.mode, res.language_code or "?", len(res.transcript))
        else:
            with stage(db, report, "transcription", report.transcript_source,
                       report.transcript_provider_mode) as job:
                job.status = "skipped"
                job.detail = {"reason": "transcript already present",
                              "source": report.transcript_source,
                              "note": "Authored synthetic fixture text - no speech recognition performed"
                              if report.transcript_source == "synthetic_fixture" else None}
            log.info("✓  transcription   skipped (transcript present)  source=%s  chars=%d",
                     report.transcript_source, len(report.transcript or ""))

        # 2. extraction --------------------------------------------------------
        _set_status(db, report, "extracting")
        ext = None
        if settings.extraction_provider == "evon":
            log.info("   extraction     provider=gnani-evon  mode=real  transcript_chars=%d",
                     len(report.transcript or ""))
            try:
                evon = EvonExtractor()
                with stage(db, report, "extraction", evon.name, evon.mode) as job:
                    result = evon.extract(report.transcript, report.language_hint)
                    ext = result.model_dump()
                    job.detail = {"uncertainties": len(ext["uncertainties"])}
            except ProviderUnavailable as exc:
                log.warning("evon unavailable, falling back to rules: %s", exc)
            except ProviderError as exc:
                log.warning("evon extraction failed, falling back to rules: %s", exc)

        if ext is None:  # rules path (default, or Evon fallback)
            with stage(db, report, "extraction", "rule-based-v1", "rule_based") as job:
                result = extract(report.transcript, report.language_hint)
                ext = result.model_dump()
                job.detail = {
                    "uncertainties": len(ext["uncertainties"]),
                    "evon_attempted": settings.extraction_provider == "evon",
                }

        if report.extraction_original is None:
            report.extraction_original = ext
        report.extraction_current = ext
        report.extraction_provider, report.extraction_mode = ext["provider"], ext["provider_mode"]

        _loc = (ext.get("location") or {})
        _place = _loc.get("place_name") or _loc.get("landmark") or "unknown"
        log.info("✓  extraction     provider=%s  disaster=%s  location=%s  urgency=%s  uncertainties=%d",
                 ext["provider"], ext.get("disaster_type", "?"), _place,
                 ext.get("urgency", "?"), len(ext.get("uncertainties", [])))

        # 3. priority + confidence gate --------------------------------------
        with stage(db, report, "priority", "priority-rules-v1", "rule_based") as job:
            pr = prio.score(prio.features_from_extraction(ext), cfg)
            report.report_priority_score, report.report_priority_label = pr["score"], pr["label"]
            report.priority_breakdown = pr
            job.detail = {"label": pr["label"], "score": pr["score"]}
        log.info("✓  priority        label=%s  score=%d", pr["label"], pr["score"])
        with stage(db, report, "confidence_gate", "gate-rules-v1", "rule_based") as job:
            fields, reasons = gate.assess(ext, pr["label"], cfg)
            report.field_assessment, report.review_reasons = fields, reasons
            report.review_resolved = False
            job.detail = {"reasons": [r["code"] for r in reasons]}
        log.info("   gate           review_reasons=%d", len(reasons))

        # 4. deduplication -----------------------------------------------------
        with stage(db, report, "deduplication", "matching-rules-v1", "rule_based") as job:
            touched: set[str] = set()
            for link in db.scalars(select(models.IncidentLink).where(
                    models.IncidentLink.report_id == report.id, models.IncidentLink.active.is_(True))):
                link.active, link.deactivated_at = False, utcnow()
                touched.add(link.incident_id)
                audit(db, "report", report.id, "unlinked_for_reprocessing", old=link.incident_id)
            for s in db.scalars(select(models.DuplicateSuggestion).where(
                    models.DuplicateSuggestion.report_id == report.id, models.DuplicateSuggestion.status == "pending")):
                s.status, s.resolved_at, s.resolved_by, s.note = "obsolete", utcnow(), "system", "report reprocessed"
            db.flush()
            for iid in touched:
                refresh_incident(db, db.get(models.Incident, iid), cfg)
            db.flush()

            rprof = matching.report_profile(ext, as_utc(report.received_at), report.transcript)
            decision = matching.decide(rprof, incident_profiles(db, cfg), cfg)
            if decision.outcome == "likely_duplicate":
                inc = db.get(models.Incident, decision.incident_id)
                outcome, score, evidence = "likely_duplicate", decision.best.score, decision.best.to_dict()
            else:
                inc = create_incident(db)
                outcome, score, evidence = "new_incident", None, decision.to_dict()
            db.add(models.IncidentLink(incident_id=inc.id, report_id=report.id, outcome=outcome, score=score,
                                       evidence=evidence, actor="system"))
            for s in decision.suggestions:
                db.add(models.DuplicateSuggestion(report_id=report.id, source_incident_id=inc.id,
                                                  candidate_incident_id=s.incident_id, score=s.score,
                                                  evidence=s.to_dict(), contradictions=s.contradictions))
                touched.add(s.incident_id)
            report.dedup_outcome = decision.outcome
            report.dedup_evidence = decision.to_dict()
            report.auto_incident_id = inc.id
            audit(db, "report", report.id, "linked", new={"incident": inc.id, "outcome": decision.outcome})
            job.detail = {"outcome": decision.outcome, "incident": inc.id, "considered": decision.considered,
                          "suggestions": [s.incident_id for s in decision.suggestions]}
            db.flush()
            refresh_incident(db, inc, cfg)
            for iid in touched - {inc.id}:
                other = db.get(models.Incident, iid)
                if other is not None:
                    refresh_incident(db, other, cfg)
            update_report_gate(db, report)

        log.info("✓  dedup           outcome=%s  incident=%s  considered=%d",
                 decision.outcome, inc.id, decision.considered)

        # 5. agentic follow-up — detect missing fields, generate targeted questions via Evon
        _raw_lang = ext.get("language") or report.language_hint or "hi"
        lang = _raw_lang if _raw_lang in ("hi", "mr", "en", "mixed") else "hi"
        if needs_followup(ext):
            with stage(db, report, "follow_up", "gnani-evon-v3.3", "real") as fu_job:
                missing = missing_fields(ext)
                questions = generate_questions(ext, lang)
                report.follow_up_needed = True
                report.follow_up_missing_fields = missing
                report.follow_up_questions = questions
                report.follow_up_status = "pending"
                fu_job.detail = {"missing": missing, "questions": questions}
            log.info("✓  follow_up       missing=%s  questions=%d", missing, len(questions))
        else:
            report.follow_up_needed = False
            report.follow_up_status = "none"

        # 6. acknowledgement (text only here; audio is generated on request) --
        if not db.scalar(select(func.count()).select_from(models.Acknowledgement).where(
                models.Acknowledgement.report_id == report.id)):
            create_text_ack(db, report, lang, ext=ext)
        log.info("✓  acknowledgement  lang=%s", lang)

        report.status = "processed"
        report.processed_at = utcnow()
        report.processing_ms = int(round((time.perf_counter() - t_start) * 1000))
        db.commit()
        total_ms = int(round((time.perf_counter() - t_start) * 1000))
        log.info("✔  pipeline done   report=%s  incident=%s  priority=%s  total_ms=%d",
                 report.id, inc.id, pr["label"], total_ms)
        return report


def mark_failed(db: Session, report_id: str, error: str) -> None:
    report = db.get(models.Report, report_id)
    if report is not None:
        report.status, report.error = "failed", error[:500]
        db.commit()
