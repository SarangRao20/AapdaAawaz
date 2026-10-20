"""Dashboard statistics — every number is computed from the database at request time."""
from __future__ import annotations

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models


def dashboard(db: Session) -> dict:
    reports = db.scalars(select(models.Report)).all()
    incidents = db.scalars(select(models.Incident).where(models.Incident.status == "active",
                                                         models.Incident.report_count > 0)).all()
    pending_by_report = Counter(db.scalars(select(models.DuplicateSuggestion.report_id).where(
        models.DuplicateSuggestion.status == "pending")).all())
    linked = db.scalar(select(func.count()).select_from(models.IncidentLink).join(
        models.Incident, models.Incident.id == models.IncidentLink.incident_id).where(
        models.IncidentLink.active.is_(True), models.Incident.status == "active")) or 0
    processed = [r for r in reports if r.status == "processed"]
    needs_verification = [r for r in processed if (r.review_reasons and not r.review_resolved)
                          or pending_by_report.get(r.id)]
    times = [r.processing_ms for r in processed if r.processing_ms is not None]
    open_review = ("needs_review", "rereview_needed")
    modes = Counter((r.transcript_provider_mode or "none") for r in reports)
    return {
        "total_reports": len(reports),
        "processed_reports": len(processed),
        "unique_incidents": len(incidents),
        "critical_awaiting_review": sum(1 for i in incidents if i.priority_label == "critical"
                                        and i.review_status in open_review),
        "critical_incidents": sum(1 for i in incidents if i.priority_label == "critical"),
        "reports_needing_verification": len(needs_verification),
        "duplicates_linked": max(linked - len(incidents), 0),
        "possible_duplicates_pending": sum(pending_by_report.values()),
        "avg_processing_ms": (sum(times) / len(times)) if times else None,
        "processing_sample": len(times),
        "incidents_needing_review": sum(1 for i in incidents if i.review_status in open_review),
        "by_priority": dict(Counter(i.priority_label for i in incidents)),
        "by_review_status": dict(Counter(i.review_status for i in incidents)),
        "by_location_status": dict(Counter(i.location_status for i in incidents)),
        "by_disaster": dict(Counter(i.disaster_type for i in incidents)),
        "report_status": dict(Counter(r.status for r in reports)),
        "report_languages": dict(Counter(((r.extraction_current or {}).get("language") or r.language_hint or "unknown")
                                         for r in reports)),
        "transcript_modes": dict(modes),
        "synthetic_reports": sum(1 for r in reports if r.is_synthetic),
        "people_reported_in_critical": sum(i.people_count or 0 for i in incidents if i.priority_label == "critical"),
    }
