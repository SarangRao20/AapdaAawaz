"""Build the aggregated incident view from its member reports (pure function).

Reports are never modified here. Human overrides are applied last and are always visible
next to what the reports themselves said.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from . import priority as prio
from .extraction import LABELS
from .gazetteer import load_gazetteer
from .lexicon import DISASTER_TIEBREAK, LIFE_THREAT_DANGERS
from .matching import Profile, facts_of
from ..schemas import DANGER_TYPES as DANGER_ORDER, NEED_TYPES as NEED_ORDER
from .text_utils import normalize

VULNERABLE_ORDER = ("elderly", "children", "infants", "pregnant_people", "people_with_disabilities")


@dataclass
class Member:
    id: str
    ext: dict
    received_at: datetime
    transcript: str | None
    review_reasons: list[dict]
    review_resolved: bool


def _location(members: list[Member], overrides: dict, contradictions: list[str]) -> dict:
    gz = load_gazetteer()
    ov = overrides.get("location")
    landmark_ids = Counter(m.ext["location"].get("landmark_id") for m in members if m.ext["location"].get("landmark_id"))
    ltypes = sorted({t for m in members for t in m.ext["location"].get("landmark_types") or []})
    stated = [t for m in members for t in m.ext["location"].get("stated_text") or []]
    base = {"landmark_types": ltypes, "stated_text": sorted(set(stated)), "candidates": [], "unmapped_name": None,
            "district": None, "state": None, "landmark": None, "landmark_id": None, "place_id": None,
            "place_name": None, "coordinate_source": None}

    if ov:
        out = dict(base)
        out.update({k: ov.get(k) for k in ("place_id", "place_name", "landmark")})
        if ov.get("place_id"):
            p = gz.places[ov["place_id"]]
            out["place_name"] = out["place_name"] or p.name
            out["district"], out["state"] = gz.district, gz.state
        lat, lon = ov.get("latitude"), ov.get("longitude")
        if lat is None and ov.get("place_id"):
            p = gz.places[ov["place_id"]]
            lat, lon = p.latitude, p.longitude
        out["coordinate_source"] = "human_verified" if ov.get("latitude") is not None else (
            "human_verified_reference_place" if lat is not None else None)
        out["verified_by"] = ov.get("verified_by")
        return {"status": "human_verified", "lat": lat, "lon": lon, "location": out}

    grounded = Counter(m.ext["location"]["place_id"] for m in members if m.ext["location"].get("status") == "grounded")
    if len(grounded) == 1:
        pid = next(iter(grounded))
        p = gz.places[pid]
        out = dict(base, place_id=pid, place_name=p.name, district=gz.district, state=gz.state,
                   coordinate_source="simulated_reference")
        lid = next((lid for lid, _ in landmark_ids.most_common() if gz.landmarks[lid].place_id == pid), None)
        if lid:
            out["landmark_id"], out["landmark"] = lid, gz.landmarks[lid].name
        else:
            out["landmark"] = next((m.ext["location"].get("landmark") for m in members
                                    if m.ext["location"].get("landmark")), None)
        return {"status": "simulated_reference", "lat": p.latitude, "lon": p.longitude, "location": out}

    if len(grounded) > 1:
        names = [gz.places[p].name for p in grounded]
        contradictions.append(f"Linked reports name different places ({', '.join(names)})")
        return {"status": "ambiguous", "lat": None, "lon": None,
                "location": dict(base, candidates=sorted(grounded))}

    unmapped = [m.ext["location"]["place_name"] for m in members
                if m.ext["location"].get("status") == "unmapped" and m.ext["location"].get("place_name")]
    if unmapped:
        name = Counter(unmapped).most_common(1)[0][0]
        landmark = next((m.ext["location"].get("landmark") for m in members if m.ext["location"].get("landmark")), None)
        return {"status": "caller_stated_unmapped", "lat": None, "lon": None,
                "location": dict(base, place_name=name, unmapped_name=normalize(name), landmark=landmark)}

    cand_sets = [set(m.ext["location"].get("candidates") or []) for m in members
                 if m.ext["location"].get("candidates")]
    if cand_sets:
        inter = set.intersection(*cand_sets)
        cands = sorted(inter or set.union(*cand_sets))
        landmark = next((m.ext["location"].get("landmark") for m in members if m.ext["location"].get("landmark")), None)
        return {"status": "ambiguous", "lat": None, "lon": None,
                "location": dict(base, candidates=cands, landmark=landmark)}
    return {"status": "unknown", "lat": None, "lon": None, "location": base}


def _ordered(items: set[str], order: tuple[str, ...]) -> list[str]:
    return sorted(items, key=lambda x: order.index(x) if x in order else len(order))


def aggregate(members: list[Member], overrides: dict, cfg: dict) -> dict:
    overrides = overrides or {}
    contradictions: list[str] = []
    exts = [m.ext for m in members]
    loc = _location(members, overrides, contradictions)

    # hazard
    hazards = Counter(e["disaster_type"] for e in exts if e.get("disaster_type") not in (None, "unknown"))
    if overrides.get("disaster_type"):
        disaster = overrides["disaster_type"]
    elif hazards:
        top = max(hazards.values())
        disaster = next(d for d in DISASTER_TIEBREAK + ["other"] if hazards.get(d) == top)
    else:
        disaster = "unknown"
    if len(hazards) > 1:
        contradictions.append(f"Reports describe different hazards ({', '.join(sorted(hazards))})")

    # people
    per_report = []
    for m in members:
        pa = m.ext.get("people_affected") or {}
        if pa.get("count") is not None or pa.get("families") is not None:
            per_report.append({"report_id": m.id, "count": pa.get("count"), "approximate": pa.get("approximate"),
                               "range": pa.get("range"), "families": pa.get("families")})
    counts = [x["count"] for x in per_report if x["count"] is not None]
    families = [x["families"] for x in per_report if x["families"] is not None]
    people_count = max(counts) if counts else None
    people_basis = "largest count stated in linked reports" if counts else "no report states a number of people"
    if counts and max(counts) / min(counts) >= 2:
        contradictions.append(f"Reported people counts differ ({', '.join(map(str, sorted(set(counts))))})")
    if overrides.get("people_count") is not None:
        people_count, people_basis = overrides["people_count"], "corrected by dispatcher"
    elif overrides.get("people_count_cleared"):
        people_count, people_basis = None, "dispatcher marked the count as unknown"

    # vulnerable / needs / dangers
    vulnerable: dict[str, dict] = {}
    for m in members:
        for g, v in (m.ext.get("vulnerable_people") or {}).items():
            if v:
                cur = vulnerable.setdefault(g, {"count": None, "reports": [], "evidence": []})
                if v.get("count") is not None:
                    cur["count"] = max(cur["count"] or 0, v["count"])
                cur["reports"].append(m.id)
                cur["evidence"].append(v.get("evidence"))
    vulnerable = {g: vulnerable[g] for g in _ordered(set(vulnerable), VULNERABLE_ORDER)}
    needs = _ordered({n for e in exts for n in e.get("immediate_needs") or []}, NEED_ORDER)
    dangers = _ordered({d for e in exts for d in e.get("reported_danger") or []}, DANGER_ORDER)
    medical = True if any(e.get("medical_emergency") for e in exts) else None
    crit_med = True if any(e.get("critical_medication") for e in exts) else None
    urgency = max((e.get("urgency") or "unknown" for e in exts), key=lambda u: prio.URGENCY_RANK.get(u, 0),
                  default="unknown")
    status_claims = sorted({s for e in exts for s in e.get("status_claims") or []})
    says_safe = bool(set(status_claims) & {"reported_safe", "reported_evacuated"})
    life = bool(set(dangers) & LIFE_THREAT_DANGERS)
    if says_safe and life:
        contradictions.append("Some reports say people are safe/evacuated; others describe a threat to life")
    languages = sorted({e.get("language") for e in exts if e.get("language") and e.get("language") != "unknown"})

    grounded = loc["status"] in ("simulated_reference", "human_verified")
    feats = prio.SeverityFeatures(dangers=set(dangers), needs=set(needs), medical_emergency=medical,
                                  critical_medication=crit_med, vulnerable=set(vulnerable),
                                  people_count=people_count, caller_urgency=urgency,
                                  status_claims=set(status_claims), location_grounded=grounded)
    pr = prio.score(feats, cfg, overrides.get("priority_label"))

    low_q = sum(1 for e in exts if e.get("transcript_quality") == "low")
    info = _info_confidence(loc["status"], people_count, counts, overrides, len(members), languages,
                            low_q, contradictions)
    times = sorted(m.received_at for m in members)

    profile = Profile(
        place_id=loc["location"].get("place_id") if grounded else None,
        location_status=("verified" if loc["status"] == "human_verified"
                         else "grounded" if loc["status"] == "simulated_reference"
                         else "unmapped" if loc["status"] == "caller_stated_unmapped" else "ambiguous"
                         if loc["status"] == "ambiguous" else "missing"),
        candidates=set(loc["location"].get("candidates") or []),
        unmapped_name=loc["location"].get("unmapped_name"),
        landmark_ids={loc["location"]["landmark_id"]} if loc["location"].get("landmark_id") else set(),
        landmark_types=set(loc["location"].get("landmark_types") or []),
        coords=((loc["lat"], loc["lon"]) if loc["status"] == "human_verified" and loc["lat"] is not None
                and not loc["location"].get("place_id") else None),
        disaster_type=disaster,
        facts=set().union(*(facts_of(e) for e in exts)) if exts else set(),
        people_counts=[people_count] if people_count is not None else [],
        families=families,
        says_safe=says_safe and not life,
        life_threat=life,
        times=times,
        texts=[m.transcript for m in members if m.transcript],
        low_quality=bool(members) and low_q == len(members),
    )

    fields = {
        "disaster_type": disaster,
        "location": loc["location"],
        "location_status": loc["status"],
        "latitude": loc["lat"],
        "longitude": loc["lon"],
        "people_count": people_count,
        "people_detail": {"per_report": per_report, "families": max(families) if families else None,
                          "basis": people_basis},
        "vulnerable": vulnerable,
        "needs": needs,
        "dangers": dangers,
        "medical_emergency": medical,
        "urgency": urgency,
        "languages": languages,
        "priority_score": pr["score"],
        "priority_label": pr["label"],
        "priority_breakdown": pr,
        "info_confidence": info,
        "contradictions": contradictions,
        "missing_info": pr["missing_info"],
        "report_count": len(members),
        "last_report_at": times[-1] if times else None,
        "status_claims": status_claims,
        "critical_medication": crit_med,
    }
    fields["summary"] = summarize(fields)
    fields["recommended_action"] = recommend(fields)
    return {"fields": fields, "profile": profile}


def _info_confidence(lstatus: str, people_count, counts, overrides, n, languages, low_q, contradictions) -> dict:
    basis: list[str] = []
    loc_level = {"human_verified": "verified", "simulated_reference": "reference_match",
                 "caller_stated_unmapped": "unmapped", "ambiguous": "ambiguous"}.get(lstatus, "unknown")
    if overrides.get("people_count") is not None:
        ppl = "verified"
    elif people_count is None:
        ppl = "unknown"
    elif counts and max(counts) / min(counts) >= 2:
        ppl = "conflicting"
    else:
        ppl = "stated"
    if loc_level in ("ambiguous", "unknown", "unmapped"):
        basis.append(f"location {loc_level.replace('_', ' ')}")
    if contradictions:
        basis.append(f"{len(contradictions)} contradiction(s) between reports")
    if n and low_q == n:
        basis.append("all transcripts are low quality")
    if ppl == "unknown":
        basis.append("number of people unknown")
    if basis and (loc_level in ("ambiguous", "unknown", "unmapped") or contradictions or (n and low_q == n)):
        overall = "low"
    elif loc_level in ("verified", "reference_match") and ppl in ("stated", "verified") and (n >= 2 or loc_level == "verified"):
        overall = "high"
        basis.append(f"grounded location, stated count, {n} corroborating report(s)")
    else:
        overall = "medium"
        if n < 2:
            basis.append("single uncorroborated report")
    return {"overall": overall, "location": loc_level, "people_count": ppl, "reports": n,
            "languages": languages, "low_quality_transcripts": low_q, "basis": basis,
            "method": "rule-based ordinal assessment (see docs/EVALUATION.md); not a probability"}


def summarize(f: dict) -> str:
    loc = f["location"] or {}
    if f["location_status"] in ("simulated_reference", "human_verified") and loc.get("place_name"):
        where = loc["place_name"] + (f" ({loc['landmark']})" if loc.get("landmark") else "")
    elif f["location_status"] == "caller_stated_unmapped":
        where = f"'{loc.get('place_name')}' (unmapped)"
    elif loc.get("candidates"):
        gz = load_gazetteer()
        names = [gz.places[c].name for c in loc["candidates"] if c in gz.places]
        kind = "/".join(t.replace("_", " ") for t in loc.get("landmark_types") or [])
        near = f"near a {kind} ('{loc['landmark']}'), " if loc.get("landmark") and kind else ""
        where = f"{near}location unclear (could be {' / '.join(names)})"
    elif loc.get("landmark"):
        where = f"near '{loc['landmark']}' (village unclear)"
    else:
        where = "unknown location"
    hazard = f["disaster_type"].capitalize() if f["disaster_type"] != "unknown" else "Incident (hazard not stated)"
    parts = [f"{hazard} — {where}."]
    if f["dangers"]:
        parts.append(", ".join(LABELS.get(d, d) for d in f["dangers"][:4]).capitalize() + ".")
    if f["people_count"] is not None:
        parts.append(f"{f['people_count']} people reported.")
    elif f["people_detail"].get("families"):
        parts.append(f"{f['people_detail']['families']} families (people count unknown).")
    if f["vulnerable"]:
        parts.append("Includes " + ", ".join(LABELS.get(v, v) for v in f["vulnerable"]) + ".")
    if f["needs"]:
        parts.append("Needs: " + ", ".join(LABELS.get(n, n) for n in f["needs"]) + ".")
    if set(f.get("status_claims") or []) & {"reported_safe", "reported_evacuated"}:
        parts.append("Caller(s) say people are safe/evacuated.")
    parts.append(f"{f['report_count']} report(s).")
    return " ".join(parts)


def recommend(f: dict) -> str:
    """Suggested next HUMAN action. Never claims that help has been or will be dispatched."""
    steps: list[str] = []
    label = f["priority_label"]
    if f["location_status"] not in ("simulated_reference", "human_verified"):
        steps.append("Verify the location (call back / local contacts) before routing any response.")
    elif f["location_status"] == "simulated_reference":
        steps.append("Confirm the exact spot; the map shows the simulated village reference point.")
    if f["contradictions"]:
        steps.append("Resolve conflicting reports before relying on counts or status.")
    if label == "critical":
        steps.append("Escalate to the duty officer now for human assessment.")
    elif label == "high":
        steps.append("Review promptly and confirm details with the caller.")
    elif label == "medium":
        steps.append("Queue for needs assessment (relief supplies).")
    else:
        steps.append("Log for situational awareness; re-check if new reports arrive.")
    if f["needs"]:
        steps.append("Possibly relevant resources (to be confirmed): " +
                     ", ".join(LABELS.get(n, n) for n in f["needs"]) + ".")
    if f["people_count"] is None and label in ("critical", "high"):
        steps.append("Ask how many people are present.")
    return " ".join(steps)
