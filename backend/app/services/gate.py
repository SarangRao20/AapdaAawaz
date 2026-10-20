"""Field-level confidence gate.

Each field is assessed on its own (location, people count, transcript, urgency, internal
consistency) instead of trusting one overall score. Known information is always kept; the
gate only decides whether a human must look at the report and records why.
"""
from __future__ import annotations

from .lexicon import LIFE_THREAT_DANGERS
from .priority import LABEL_RANK

LOCATION_REASONS = {
    "missing": ("location_missing", "No location stated"),
    "ambiguous": ("location_ambiguous", "Location ambiguous (generic landmark, no village)"),
    "conflicting": ("location_conflicting", "Several places mentioned"),
    "unmapped": ("location_unmapped", "Place not in the reference dataset"),
    "landmark_only": ("location_landmark_only", "Only a landmark named; village not stated"),
}


def reason(code: str, field: str, message: str) -> dict:
    return {"code": code, "field": field, "message": message}


def assess(ext: dict, priority_label: str, cfg: dict) -> tuple[dict, list[dict]]:
    g = cfg["gate"]
    reasons: list[dict] = []
    fields: dict[str, dict] = {}

    loc = ext.get("location") or {}
    lstatus = loc.get("status", "missing")
    lconf = float(loc.get("confidence") or 0.0)
    loc_ok = lstatus == "grounded" and lconf >= g["min_location_confidence"]
    fields["location"] = {
        "status": "ok" if loc_ok else "review",
        "location_status": lstatus,
        "evidence_level": lconf,
        "basis": loc.get("confidence_basis"),
        "verified": False,
    }
    if lstatus in LOCATION_REASONS:
        code, msg = LOCATION_REASONS[lstatus]
        reasons.append(reason(code, "location", f"{msg}: {loc.get('confidence_basis', '')}".rstrip(": ")))
    elif not loc_ok:
        reasons.append(reason("location_low_confidence", "location",
                              f"Location evidence {lconf:.2f} below threshold {g['min_location_confidence']}"))

    pa = ext.get("people_affected") or {}
    count, pconf = pa.get("count"), float(pa.get("confidence") or 0.0)
    review_at = g["unknown_people_review_at"]
    unknown_matters = review_at != "never" and LABEL_RANK.get(priority_label, 0) >= LABEL_RANK[review_at]
    if count is None:
        fields["people_count"] = {"status": "review" if unknown_matters else "unknown", "evidence_level": 0.0,
                                  "basis": pa.get("confidence_basis")}
        if unknown_matters:
            msg = (f"{pa['families']} families stated but number of people unknown" if pa.get("families")
                   else "Number of people unknown for a high-priority report")
            reasons.append(reason("people_count_unknown", "people_count", msg))
    else:
        ok = pconf >= g["min_people_confidence"]
        fields["people_count"] = {"status": "ok" if ok else "review", "evidence_level": pconf,
                                  "basis": pa.get("confidence_basis")}
        if not ok:
            reasons.append(reason("people_count_low_confidence", "people_count",
                                  f"People count evidence {pconf:.2f} below threshold: {pa.get('confidence_basis')}"))

    quality = ext.get("transcript_quality", "unknown")
    fields["transcript"] = {"status": "review" if quality == "low" else "ok", "quality": quality,
                            "basis": ext.get("transcript_quality_basis")}
    if quality == "low" and g["flag_low_quality_transcript"]:
        reasons.append(reason("low_quality_transcript", "transcript",
                              f"Low-quality transcript: {ext.get('transcript_quality_basis')}"))

    urgency = ext.get("urgency", "unknown")
    has_signal = bool(ext.get("reported_danger") or ext.get("immediate_needs") or ext.get("medical_emergency"))
    unclear = urgency == "unknown" and not has_signal and not ext.get("status_claims")
    fields["urgency"] = {"status": "review" if unclear else ("ok" if urgency != "unknown" else "unknown"),
                         "caller_urgency": urgency, "basis": ext.get("urgency_basis")}
    if unclear and g["flag_unclear_urgency"]:
        reasons.append(reason("urgency_unclear", "urgency",
                              "No urgency, danger or need could be identified — situation unclear"))

    fields["disaster_type"] = {"status": "ok" if ext.get("disaster_type") != "unknown" else "unknown",
                               "value": ext.get("disaster_type"), "basis": ext.get("disaster_basis")}

    dangers = set(ext.get("reported_danger") or [])
    says_safe = bool(set(ext.get("status_claims") or []) & {"reported_safe", "reported_evacuated"})
    if says_safe and dangers & LIFE_THREAT_DANGERS:
        reasons.append(reason("inconsistent_fields", "status",
                              "Report says people are safe but also describes a threat to life"))
    if len(ext.get("disaster_types_mentioned") or []) > 1:
        reasons.append(reason("inconsistent_fields", "disaster_type",
                              f"Several hazards mentioned: {', '.join(ext['disaster_types_mentioned'])}"))
    return fields, reasons


def incident_reasons(fields: dict, pending_suggestions: list[dict], all_low_quality: bool,
                     acknowledged: list[str], cfg: dict) -> list[dict]:
    """Review reasons for an incident, evaluated on the aggregate (not a union of report flags)."""
    g = cfg["gate"]
    out: list[dict] = []
    status = fields["location_status"]
    if status not in ("simulated_reference", "human_verified"):
        msg = {"ambiguous": "Location ambiguous or conflicting across reports",
               "caller_stated_unmapped": "Caller-stated place is not in the reference dataset",
               }.get(status, "No usable location")
        out.append(reason(f"location_{status}", "location", msg))
    review_at = g["unknown_people_review_at"]
    if (fields["people_count"] is None and review_at != "never"
            and LABEL_RANK.get(fields["priority_label"], 0) >= LABEL_RANK[review_at]):
        out.append(reason("people_count_unknown", "people_count", "Number of people unknown for a high-priority incident"))
    if all_low_quality and g["flag_low_quality_transcript"]:
        out.append(reason("low_quality_transcript", "transcript", "All linked transcripts are low quality"))
    for c in fields["contradictions"]:
        if c not in acknowledged:
            out.append(reason("conflicting_reports", "reports", c))
    for s in pending_suggestions:
        out.append(reason("possible_duplicate", "deduplication",
                          f"Possible duplicate of {s['other_incident_id']} (score {s['score']:.2f}"
                          + (f"; {'; '.join(s['contradictions'])}" if s.get("contradictions") else "") + ")"))
    if not fields["priority_breakdown"]["factors"] and g["flag_unclear_urgency"] and not fields.get("status_claims"):
        out.append(reason("urgency_unclear", "urgency", "No danger, need or urgency identified"))
    return out
