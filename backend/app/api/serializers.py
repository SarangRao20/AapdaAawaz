"""ORM -> JSON views. Datetimes are always returned as UTC ISO-8601 strings."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..services.pipeline import as_utc


def iso(dt: datetime | None) -> str | None:
    dt = as_utc(dt)
    return dt.isoformat() if dt else None


def audio_view(a: models.AudioFile) -> dict:
    return {"id": a.id, "kind": a.kind, "original_filename": a.original_filename, "mime_type": a.mime_type,
            "size_bytes": a.size_bytes, "uploaded_at": iso(a.uploaded_at),
            "url": f"/api/reports/{a.report_id}/audio/{a.id}"}


def job_view(j: models.ProcessingJob) -> dict:
    return {"id": j.id, "stage": j.stage, "provider": j.provider, "provider_mode": j.provider_mode,
            "status": j.status, "started_at": iso(j.started_at), "finished_at": iso(j.finished_at),
            "duration_ms": j.duration_ms, "error": j.error, "detail": j.detail}


def ack_view(a: models.Acknowledgement | None) -> dict | None:
    if a is None:
        return None
    return {"id": a.id, "language": a.language, "text": a.text, "provider": a.provider,
            "provider_mode": a.provider_mode, "status": a.status, "error": a.error,
            "audio_url": f"/api/reports/{a.report_id}/acknowledgement/audio" if a.audio_stored_name else None,
            "created_at": iso(a.created_at), "ai_generated_label": "Automated acknowledgement (template text"
            + (", AI-synthesised voice" if a.audio_stored_name else "") + ")"}


def suggestion_view(s: models.DuplicateSuggestion) -> dict:
    return {"id": s.id, "report_id": s.report_id, "source_incident_id": s.source_incident_id,
            "candidate_incident_id": s.candidate_incident_id, "score": s.score, "evidence": s.evidence,
            "contradictions": s.contradictions or [], "status": s.status, "created_at": iso(s.created_at),
            "resolved_at": iso(s.resolved_at), "resolved_by": s.resolved_by, "note": s.note}


def audit_view(a: models.AuditLog) -> dict:
    return {"id": a.id, "entity_type": a.entity_type, "entity_id": a.entity_id, "action": a.action,
            "field": a.field, "old_value": a.old_value, "new_value": a.new_value, "actor": a.actor,
            "note": a.note, "created_at": iso(a.created_at)}


def review_view(r: models.ReviewRecord) -> dict:
    return {"id": r.id, "incident_id": r.incident_id, "report_id": r.report_id, "reviewer": r.reviewer,
            "action": r.action, "notes": r.notes, "payload": r.payload, "created_at": iso(r.created_at)}


def report_summary(rep: models.Report, incident_id: str | None = None, pending: int = 0) -> dict:
    ext = rep.extraction_current or {}
    loc = ext.get("location") or {}
    return {
        "id": rep.id,
        "received_at": iso(rep.received_at),
        "source": rep.source,
        "is_synthetic": rep.is_synthetic,
        "synthetic_label": rep.synthetic_label,
        "fixture_id": rep.fixture_id,
        "language": ext.get("language") or rep.language_hint,
        "language_hint": rep.language_hint,
        "status": rep.status,
        "transcript": rep.transcript,
        "transcript_source": rep.transcript_source,
        "transcript_provider": rep.transcript_provider,
        "transcript_provider_mode": rep.transcript_provider_mode,
        "has_audio": bool(rep.audio_files),
        "audio": [audio_view(a) for a in rep.audio_files],
        "location_text": (loc.get("place_name") or loc.get("landmark")) if loc else None,
        "location_status": loc.get("status"),
        "location_confidence": loc.get("confidence"),
        "people_count": (ext.get("people_affected") or {}).get("count"),
        "disaster_type": ext.get("disaster_type"),
        "summary": ext.get("summary"),
        "priority_label": rep.report_priority_label,
        "priority_score": rep.report_priority_score,
        "gate_status": rep.gate_status,
        "review_reasons": rep.review_reasons or [],
        "review_resolved": rep.review_resolved,
        "dedup_outcome": rep.dedup_outcome,
        "incident_id": incident_id,
        "pending_suggestions": pending,
        "processing_ms": rep.processing_ms,
        "processed_at": iso(rep.processed_at),
        "error": rep.error or rep.stt_error,
    }


def report_detail(db: Session, rep: models.Report) -> dict:
    links = db.scalars(select(models.IncidentLink).where(models.IncidentLink.report_id == rep.id)
                       .order_by(models.IncidentLink.id)).all()
    active = next((l.incident_id for l in links if l.active), None)
    suggestions = db.scalars(select(models.DuplicateSuggestion).where(
        models.DuplicateSuggestion.report_id == rep.id).order_by(models.DuplicateSuggestion.id)).all()
    ack = db.scalars(select(models.Acknowledgement).where(models.Acknowledgement.report_id == rep.id)
                     .order_by(models.Acknowledgement.id.desc())).first()
    audit = db.scalars(select(models.AuditLog).where(models.AuditLog.entity_type == "report",
                                                     models.AuditLog.entity_id == rep.id)
                       .order_by(models.AuditLog.id)).all()
    gt = db.get(models.GroundTruth, rep.fixture_id) if rep.fixture_id else None
    out = report_summary(rep, active, sum(1 for s in suggestions if s.status == "pending"))
    out.update({
        "transcript_raw": rep.transcript_raw,
        "transcript_request_id": rep.transcript_request_id,
        "stt_error": rep.stt_error,
        "extraction_original": rep.extraction_original,
        "extraction_current": rep.extraction_current,
        "extraction_provider": rep.extraction_provider,
        "extraction_mode": rep.extraction_mode,
        "field_assessment": rep.field_assessment,
        "priority_breakdown": rep.priority_breakdown,
        "dedup_evidence": rep.dedup_evidence,
        "auto_incident_id": rep.auto_incident_id,
        "follow_up_needed": rep.follow_up_needed,
        "follow_up_questions": rep.follow_up_questions or [],
        "follow_up_missing_fields": rep.follow_up_missing_fields or [],
        "follow_up_status": rep.follow_up_status,
        "jobs": [job_view(j) for j in rep.jobs],
        "links": [{"incident_id": l.incident_id, "outcome": l.outcome, "score": l.score, "active": l.active,
                   "actor": l.actor, "created_at": iso(l.created_at), "deactivated_at": iso(l.deactivated_at)}
                  for l in links],
        "suggestions": [suggestion_view(s) for s in suggestions],
        "acknowledgement": ack_view(ack),
        "audit": [audit_view(a) for a in audit],
        "ground_truth": gt.data if gt else None,
    })
    return out


def incident_summary(inc: models.Incident) -> dict:
    return {
        "id": inc.id,
        "status": inc.status,
        "merged_into_id": inc.merged_into_id,
        "created_at": iso(inc.created_at),
        "updated_at": iso(inc.updated_at),
        "last_report_at": iso(inc.last_report_at),
        "disaster_type": inc.disaster_type,
        "location": inc.location,
        "location_status": inc.location_status,
        "latitude": inc.latitude,
        "longitude": inc.longitude,
        "coordinates_are_simulated": inc.location_status == "simulated_reference",
        "people_count": inc.people_count,
        "people_detail": inc.people_detail,
        "vulnerable": inc.vulnerable or {},
        "needs": inc.needs or [],
        "dangers": inc.dangers or [],
        "medical_emergency": inc.medical_emergency,
        "urgency": inc.urgency,
        "languages": inc.languages or [],
        "summary": inc.summary,
        "priority_score": inc.priority_score,
        "priority_label": inc.priority_label,
        "priority_breakdown": inc.priority_breakdown,
        "info_confidence": inc.info_confidence,
        "review_reasons": inc.review_reasons or [],
        "contradictions": inc.contradictions or [],
        "missing_info": inc.missing_info or [],
        "recommended_action": inc.recommended_action,
        "review_status": inc.review_status,
        "human_overrides": inc.human_overrides or {},
        "report_count": inc.report_count,
    }


def incident_detail(db: Session, inc: models.Incident) -> dict:
    links = db.scalars(select(models.IncidentLink).where(models.IncidentLink.incident_id == inc.id)
                       .order_by(models.IncidentLink.id)).all()
    report_ids = list(dict.fromkeys(l.report_id for l in links if l.active))
    reports = {r.id: r for r in db.scalars(select(models.Report).where(models.Report.id.in_(report_ids)))}
    acks = {a.report_id: a for a in db.scalars(
        select(models.Acknowledgement).where(models.Acknowledgement.report_id.in_(report_ids))
        .order_by(models.Acknowledgement.id)).all()} if report_ids else {}
    suggestions = db.scalars(select(models.DuplicateSuggestion).where(
        (models.DuplicateSuggestion.source_incident_id == inc.id)
        | (models.DuplicateSuggestion.candidate_incident_id == inc.id)).order_by(models.DuplicateSuggestion.id)).all()
    audit = db.scalars(select(models.AuditLog).where(
        ((models.AuditLog.entity_type == "incident") & (models.AuditLog.entity_id == inc.id))
        | ((models.AuditLog.entity_type == "report") & (models.AuditLog.entity_id.in_(report_ids))))
        .order_by(models.AuditLog.id)).all()
    reviews = db.scalars(select(models.ReviewRecord).where(models.ReviewRecord.incident_id == inc.id)
                         .order_by(models.ReviewRecord.id)).all()
    out = incident_summary(inc)
    members = []
    for l in links:
        if not l.active or l.report_id not in reports:
            continue
        rep = reports[l.report_id]
        m = report_summary(rep, inc.id)
        m.update({"link_outcome": l.outcome, "link_score": l.score, "link_evidence": l.evidence,
                  "linked_at": iso(l.created_at), "extraction_current": rep.extraction_current,
                  "extraction_original": rep.extraction_original, "field_assessment": rep.field_assessment,
                  "priority_breakdown": rep.priority_breakdown,
                  "acknowledgement": ack_view(acks.get(rep.id))})
        members.append(m)
    out.update({
        "reports": sorted(members, key=lambda m: m["received_at"] or ""),
        "link_history": [{"report_id": l.report_id, "outcome": l.outcome, "active": l.active, "actor": l.actor,
                          "score": l.score, "created_at": iso(l.created_at), "deactivated_at": iso(l.deactivated_at)}
                         for l in links],
        "suggestions": [suggestion_view(s) for s in suggestions],
        "audit": [audit_view(a) for a in audit],
        "reviews": [review_view(r) for r in reviews],
    })
    return out
