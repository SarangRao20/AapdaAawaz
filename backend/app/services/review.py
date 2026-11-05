"""Human review operations. Every change is audited with old and new values; original
transcripts and AI extractions on the reports are never modified here.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..schemas import (IncidentReopenRequest, IncidentResolveRequest, IncidentReviewRequest, MergeRequest,
                       SplitRequest, TranscriptSubmit)
from .gazetteer import load_gazetteer
from .pipeline import (PIPELINE_LOCK, active_members, audit, create_incident, pending_suggestions_for,
                       refresh_incident, update_report_gate, utcnow)
from .settings_store import get_config


class ReviewError(ValueError):
    """Invalid review request (maps to HTTP 400/409)."""


def _record(db: Session, *, incident_id=None, report_id=None, reviewer: str, action: str, notes=None, payload=None):
    db.add(models.ReviewRecord(incident_id=incident_id, report_id=report_id, reviewer=reviewer, action=action,
                               notes=notes, payload=payload))


def _active_incident(db: Session, incident_id: str) -> models.Incident:
    inc = db.get(models.Incident, incident_id)
    if inc is None:
        raise LookupError(f"incident {incident_id} not found")
    if inc.status != "active":
        raise ReviewError(f"incident {incident_id} is {inc.status}"
                          + (f" (merged into {inc.merged_into_id})" if inc.merged_into_id else ""))
    return inc


def review_incident(db: Session, incident_id: str, req: IncidentReviewRequest) -> models.Incident:
    with PIPELINE_LOCK:
        inc = _active_incident(db, incident_id)
        cfg = get_config(db)
        ov = dict(inc.human_overrides or {})
        changes: dict = {}
        who = req.reviewer

        if req.verify_location is not None:
            loc = req.verify_location
            gz = load_gazetteer()
            if loc.place_id is not None and loc.place_id not in gz.places:
                raise ReviewError(f"unknown reference place {loc.place_id}")
            if loc.place_id is None and loc.latitude is None:
                raise ReviewError("a custom place name needs coordinates confirmed by the reviewer")
            new_loc = loc.model_dump() | {"verified_by": who, "verified_at": utcnow().isoformat()}
            changes["location"] = (ov.get("location") or {"status": inc.location_status, **(inc.location or {})}, new_loc)
            ov["location"] = new_loc
        elif req.confirm_current_location:
            if inc.location_status != "simulated_reference" or not (inc.location or {}).get("place_id"):
                raise ReviewError("only a reference-matched location can be confirmed as-is; "
                                  "choose a place or enter coordinates instead")
            new_loc = {"place_id": inc.location["place_id"], "place_name": inc.location.get("place_name"),
                       "landmark": inc.location.get("landmark"), "latitude": None, "longitude": None,
                       "verified_by": who, "verified_at": utcnow().isoformat()}
            changes["location"] = ({"status": inc.location_status, **inc.location}, new_loc)
            ov["location"] = new_loc

        if req.people_count is not None and req.clear_people_count:
            raise ReviewError("set people_count or clear_people_count, not both")
        if req.people_count is not None:
            changes["people_count"] = (inc.people_count, req.people_count)
            ov["people_count"] = req.people_count
            ov.pop("people_count_cleared", None)
        elif req.clear_people_count:
            changes["people_count"] = (inc.people_count, None)
            ov.pop("people_count", None)
            ov["people_count_cleared"] = True

        if req.urgency is not None:
            if req.urgency == "unknown":
                changes["priority_label"] = (ov.get("priority_label"), None)
                ov.pop("priority_label", None)
            else:
                changes["priority_label"] = (inc.priority_label, req.urgency)
                ov["priority_label"] = req.urgency
        if req.disaster_type is not None:
            changes["disaster_type"] = (inc.disaster_type, req.disaster_type)
            ov["disaster_type"] = req.disaster_type

        if req.mark_reviewed:
            ov["reviewed_at"] = utcnow().isoformat()
            ov["reviewed_by"] = who
            changes["review_status"] = (inc.review_status, "reviewed")
        if not changes and not req.notes:
            raise ReviewError("nothing to change: provide a correction, mark_reviewed, or notes")

        for fieldname, (old, new) in changes.items():
            audit(db, "incident", inc.id, "human_correction" if fieldname != "review_status" else "marked_reviewed",
                  field=fieldname, old=old, new=new, actor=who, note=req.notes)
        if req.notes and not changes:
            audit(db, "incident", inc.id, "note_added", actor=who, note=req.notes)
        _record(db, incident_id=inc.id, reviewer=who, action="review", notes=req.notes,
                payload={k: {"old": o, "new": n} for k, (o, n) in changes.items()})

        inc.human_overrides = ov
        refresh_incident(db, inc, cfg)
        if req.mark_reviewed:
            ov["acknowledged_contradictions"] = list(inc.contradictions or [])
            inc.human_overrides = dict(ov)
            for _, rep in active_members(db, inc.id):
                rep.review_resolved = True
            refresh_incident(db, inc, cfg)
        db.commit()
        return inc


def resolve_incident(db: Session, incident_id: str, req: IncidentResolveRequest) -> models.Incident:
    """Close an incident (e.g. responders reached everyone). Reports stay linked and everything is audited,
    so it can be reopened; it simply stops competing for attention on the live board."""
    with PIPELINE_LOCK:
        inc = _active_incident(db, incident_id)
        resolution = {"reason": req.reason, "by": req.reviewer, "at": utcnow().isoformat(), "notes": req.notes}
        overrides = dict(inc.human_overrides or {})
        overrides["resolution"] = resolution
        inc.human_overrides = overrides
        audit(db, "incident", inc.id, "resolved", field="status", old="active", new="closed",
              actor=req.reviewer, note=f"{req.reason}: {req.notes}" if req.notes else req.reason)
        _record(db, incident_id=inc.id, reviewer=req.reviewer, action="resolve", notes=req.notes,
                payload={"reason": req.reason})
        inc.status, inc.updated_at = "closed", utcnow()
        for s in pending_suggestions_for(db, inc.id):
            s.status, s.resolved_at, s.resolved_by = "obsolete", utcnow(), req.reviewer
            s.note = f"incident {inc.id} was resolved ({req.reason})"
        db.commit()
        return inc


def reopen_incident(db: Session, incident_id: str, req: IncidentReopenRequest) -> models.Incident:
    with PIPELINE_LOCK:
        inc = db.get(models.Incident, incident_id)
        if inc is None:
            raise LookupError(f"incident {incident_id} not found")
        if inc.status != "closed":
            raise ReviewError(f"incident {incident_id} is {inc.status}, only a closed incident can be reopened")
        overrides = dict(inc.human_overrides or {})
        overrides.pop("resolution", None)
        inc.human_overrides = overrides
        inc.status = "active"
        audit(db, "incident", inc.id, "reopened", field="status", old="closed", new="active",
              actor=req.reviewer, note=req.notes)
        _record(db, incident_id=inc.id, reviewer=req.reviewer, action="reopen", notes=req.notes)
        refresh_incident(db, inc, get_config(db))
        db.commit()
        return inc


def _move_report(db: Session, report_id: str, target: models.Incident, outcome: str, actor: str,
                 evidence: dict | None = None) -> str | None:
    old_link = db.scalar(select(models.IncidentLink).where(
        models.IncidentLink.report_id == report_id, models.IncidentLink.active.is_(True)))
    old_incident = None
    if old_link is not None:
        if old_link.incident_id == target.id:
            return None
        old_link.active, old_link.deactivated_at = False, utcnow()
        old_incident = old_link.incident_id
    db.add(models.IncidentLink(incident_id=target.id, report_id=report_id, outcome=outcome, actor=actor,
                               evidence=evidence))
    audit(db, "report", report_id, outcome, field="incident", old=old_incident, new=target.id, actor=actor)
    return old_incident


def decide_suggestion(db: Session, suggestion_id: int, confirm: bool, reviewer: str, notes: str | None):
    with PIPELINE_LOCK:
        s = db.get(models.DuplicateSuggestion, suggestion_id)
        if s is None:
            raise LookupError(f"suggestion {suggestion_id} not found")
        if s.status != "pending":
            raise ReviewError(f"suggestion {suggestion_id} is already {s.status}")
        cfg = get_config(db)
        s.resolved_at, s.resolved_by, s.note = utcnow(), reviewer, notes
        touched = {s.source_incident_id, s.candidate_incident_id}
        report = db.get(models.Report, s.report_id)
        if confirm:
            target = _active_incident(db, s.candidate_incident_id)
            s.status = "confirmed"
            old = _move_report(db, s.report_id, target, "duplicate_confirmed", reviewer, s.evidence)
            if old:
                touched.add(old)
                src = db.get(models.Incident, old)
                if src is not None and not [1 for _, r in active_members(db, old) if r.id != s.report_id]:
                    src.merged_into_id = target.id
            for other in db.scalars(select(models.DuplicateSuggestion).where(
                    models.DuplicateSuggestion.report_id == s.report_id,
                    models.DuplicateSuggestion.status == "pending", models.DuplicateSuggestion.id != s.id)):
                other.status, other.resolved_at, other.resolved_by = "obsolete", utcnow(), reviewer
                other.note = f"report confirmed as duplicate of {target.id}"
                touched.add(other.candidate_incident_id)
        else:
            s.status = "rejected"
        audit(db, "suggestion", str(s.id), "duplicate_confirmed" if confirm else "duplicate_rejected",
              old="pending", new=s.status, actor=reviewer, note=notes)
        _record(db, incident_id=s.candidate_incident_id, report_id=s.report_id, reviewer=reviewer,
                action="confirm_duplicate" if confirm else "reject_duplicate", notes=notes,
                payload={"suggestion_id": s.id, "score": s.score})
        db.flush()
        for iid in touched:
            inc = db.get(models.Incident, iid)
            if inc is not None:
                refresh_incident(db, inc, cfg)
        if report is not None:
            update_report_gate(db, report)
        db.commit()
        return s


def merge_incidents(db: Session, target_id: str, req: MergeRequest) -> models.Incident:
    with PIPELINE_LOCK:
        target = _active_incident(db, target_id)
        sources = []
        for sid in dict.fromkeys(req.source_incident_ids):
            if sid == target_id:
                raise ReviewError("an incident cannot be merged into itself")
            sources.append(_active_incident(db, sid))
        cfg = get_config(db)
        moved = []
        for src in sources:
            for _, rep in active_members(db, src.id):
                _move_report(db, rep.id, target, "manual_merge", req.reviewer)
                moved.append(rep.id)
            src.merged_into_id = target.id
            audit(db, "incident", src.id, "merged", field="merged_into", new=target.id, actor=req.reviewer,
                  note=req.notes)
            for s in db.scalars(select(models.DuplicateSuggestion).where(
                    models.DuplicateSuggestion.status == "pending",
                    ((models.DuplicateSuggestion.source_incident_id == src.id)
                     & (models.DuplicateSuggestion.candidate_incident_id == target.id))
                    | ((models.DuplicateSuggestion.source_incident_id == target.id)
                       & (models.DuplicateSuggestion.candidate_incident_id == src.id)))):
                s.status, s.resolved_at, s.resolved_by, s.note = "confirmed", utcnow(), req.reviewer, "manual merge"
        _record(db, incident_id=target.id, reviewer=req.reviewer, action="merge", notes=req.notes,
                payload={"sources": [s.id for s in sources], "reports_moved": moved})
        db.flush()
        for src in sources:
            refresh_incident(db, src, cfg)
        refresh_incident(db, target, cfg)
        for rid in moved:
            rep = db.get(models.Report, rid)
            update_report_gate(db, rep)
        db.commit()
        return target


def split_incident(db: Session, incident_id: str, req: SplitRequest) -> models.Incident:
    with PIPELINE_LOCK:
        inc = _active_incident(db, incident_id)
        members = {rep.id for _, rep in active_members(db, inc.id)}
        wanted = list(dict.fromkeys(req.report_ids))
        missing = [r for r in wanted if r not in members]
        if missing:
            raise ReviewError(f"reports not in incident {incident_id}: {', '.join(missing)}")
        if len(wanted) >= len(members):
            raise ReviewError("at least one report must stay in the original incident")
        cfg = get_config(db)
        new_inc = create_incident(db)
        for rid in wanted:
            _move_report(db, rid, new_inc, "manual_split", req.reviewer)
        audit(db, "incident", inc.id, "split", field="reports", old=sorted(members), new={new_inc.id: wanted},
              actor=req.reviewer, note=req.notes)
        _record(db, incident_id=inc.id, reviewer=req.reviewer, action="split", notes=req.notes,
                payload={"new_incident": new_inc.id, "reports": wanted})
        db.flush()
        refresh_incident(db, inc, cfg)
        refresh_incident(db, new_inc, cfg)
        db.commit()
        return new_inc


def submit_transcript(db: Session, report_id: str, req: TranscriptSubmit) -> models.Report:
    with PIPELINE_LOCK:
        rep = db.get(models.Report, report_id)
        if rep is None:
            raise LookupError(f"report {report_id} not found")
        old = {"text": rep.transcript, "source": rep.transcript_source, "provider": rep.transcript_provider}
        if rep.transcript and rep.transcript_raw is None and rep.transcript_source != "manual_entry":
            rep.transcript_raw = {"previous_transcript": rep.transcript, "previous_source": rep.transcript_source}
        rep.transcript = req.text.strip()
        rep.transcript_source, rep.transcript_provider, rep.transcript_provider_mode = "manual_entry", req.reviewer, "human"
        if req.language_hint:
            rep.language_hint = req.language_hint
        rep.status = "queued" if req.process else "received"
        audit(db, "report", rep.id, "transcript_entered", field="transcript", old=old, new=rep.transcript,
              actor=req.reviewer)
        _record(db, report_id=rep.id, reviewer=req.reviewer, action="transcript_entered")
        db.commit()
        return rep
