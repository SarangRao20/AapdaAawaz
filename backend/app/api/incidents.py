from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..schemas import IncidentReviewRequest, MergeRequest, SplitRequest, SuggestionDecision
from ..services import priority as prio
from ..services import review as review_svc
from .serializers import incident_detail, incident_summary, suggestion_view

router = APIRouter(prefix="/api", tags=["incidents"])

VERIFICATION = {
    "verified": {"human_verified"},
    "reference": {"simulated_reference", "caller_gps"},
    "ungrounded": {"ambiguous", "caller_stated_unmapped", "unknown"},
}
SORTS = {"priority", "recent", "reports", "confidence"}


def _csv(v: str | None) -> list[str]:
    return [x for x in (v or "").split(",") if x]


@router.get("/incidents")
def list_incidents(
    db: Session = Depends(get_db),
    priority: str | None = Query(None, description="comma-separated: critical,high,medium,low"),
    status: str = Query("active", description="active | merged | closed | all"),
    review_status: str | None = Query(None, description="comma-separated review statuses"),
    disaster_type: str | None = None,
    language: str | None = None,
    verification: str | None = Query(None, description="verified | reference | ungrounded"),
    sort: str = Query("priority"),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    if sort not in SORTS:
        raise HTTPException(422, f"sort must be one of {sorted(SORTS)}")
    if verification and verification not in VERIFICATION:
        raise HTTPException(422, f"verification must be one of {sorted(VERIFICATION)}")
    stmt = select(models.Incident)
    if status != "all":
        stmt = stmt.where(models.Incident.status == status)
    if status == "active":
        stmt = stmt.where(models.Incident.report_count > 0)
    if priority:
        stmt = stmt.where(models.Incident.priority_label.in_(_csv(priority)))
    if review_status:
        stmt = stmt.where(models.Incident.review_status.in_(_csv(review_status)))
    if disaster_type:
        stmt = stmt.where(models.Incident.disaster_type.in_(_csv(disaster_type)))
    if verification:
        stmt = stmt.where(models.Incident.location_status.in_(VERIFICATION[verification]))
    rows = db.scalars(stmt).all()
    if language:
        rows = [i for i in rows if language in (i.languages or [])]
    conf_rank = {"high": 2, "medium": 1, "low": 0}
    if sort == "priority":
        rows.sort(key=lambda i: (prio.sort_key(i.priority_label, i.priority_score), i.report_count), reverse=True)
    elif sort == "recent":
        rows.sort(key=lambda i: (i.last_report_at is not None, i.last_report_at or i.created_at), reverse=True)
    elif sort == "reports":
        rows.sort(key=lambda i: (i.report_count, i.priority_score), reverse=True)
    else:
        rows.sort(key=lambda i: conf_rank.get((i.info_confidence or {}).get("overall"), 0))
    total = len(rows)
    return {"total": total, "limit": limit, "offset": offset,
            "items": [incident_summary(i) for i in rows[offset:offset + limit]]}


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str, db: Session = Depends(get_db)):
    inc = db.get(models.Incident, incident_id)
    if inc is None:
        raise HTTPException(404, f"incident {incident_id} not found")
    return incident_detail(db, inc)


def _run(fn, *args):
    try:
        return fn(*args)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except review_svc.ReviewError as exc:
        raise HTTPException(409 if "is merged" in str(exc) or "already" in str(exc) else 400, str(exc)) from exc


@router.post("/incidents/{incident_id}/review")
def review(incident_id: str, body: IncidentReviewRequest, db: Session = Depends(get_db)):
    inc = _run(review_svc.review_incident, db, incident_id, body)
    return incident_detail(db, inc)


@router.post("/incidents/{incident_id}/merge", summary="Merge other incidents (and all their reports) into this one")
def merge(incident_id: str, body: MergeRequest, db: Session = Depends(get_db)):
    inc = _run(review_svc.merge_incidents, db, incident_id, body)
    return incident_detail(db, inc)


@router.post("/incidents/{incident_id}/split", summary="Move selected reports into a new incident")
def split(incident_id: str, body: SplitRequest, db: Session = Depends(get_db)):
    new_inc = _run(review_svc.split_incident, db, incident_id, body)
    return {"original": incident_detail(db, db.get(models.Incident, incident_id)),
            "new_incident": incident_detail(db, new_inc)}


@router.get("/suggestions")
def list_suggestions(status: str = Query("pending"), db: Session = Depends(get_db)):
    stmt = select(models.DuplicateSuggestion)
    if status != "all":
        stmt = stmt.where(models.DuplicateSuggestion.status == status)
    rows = db.scalars(stmt.order_by(models.DuplicateSuggestion.score.desc())).all()
    incident_ids = {s.source_incident_id for s in rows} | {s.candidate_incident_id for s in rows}
    incidents = {i.id: i for i in db.scalars(select(models.Incident).where(models.Incident.id.in_(incident_ids)))}
    reports = {r.id: r for r in db.scalars(select(models.Report).where(
        models.Report.id.in_({s.report_id for s in rows})))}
    items = []
    for s in rows:
        v = suggestion_view(s)
        rep = reports.get(s.report_id)
        v["report"] = {"id": rep.id, "transcript": rep.transcript, "language": (rep.extraction_current or {}).get("language"),
                       "summary": (rep.extraction_current or {}).get("summary")} if rep else None
        for key, iid in (("source_incident", s.source_incident_id), ("candidate_incident", s.candidate_incident_id)):
            inc = incidents.get(iid)
            v[key] = incident_summary(inc) if inc else None
        items.append(v)
    pending = db.scalar(select(func.count()).select_from(models.DuplicateSuggestion).where(
        models.DuplicateSuggestion.status == "pending"))
    return {"total": len(items), "pending": pending, "items": items}


@router.post("/suggestions/{suggestion_id}/confirm", summary="Confirm a possible duplicate: move the report")
def confirm(suggestion_id: int, body: SuggestionDecision, db: Session = Depends(get_db)):
    return suggestion_view(_run(review_svc.decide_suggestion, db, suggestion_id, True, body.reviewer, body.notes))


@router.post("/suggestions/{suggestion_id}/reject", summary="Reject an incorrect duplicate suggestion")
def reject(suggestion_id: int, body: SuggestionDecision, db: Session = Depends(get_db)):
    return suggestion_view(_run(review_svc.decide_suggestion, db, suggestion_id, False, body.reviewer, body.notes))
