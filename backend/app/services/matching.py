"""Transparent, deterministic duplicate detection between a new report and existing incidents.

Every feature that contributes to the score is returned as evidence so a dispatcher can see
exactly why two reports were (or were not) linked. Outcomes:

* ``likely_duplicate``   — score >= likely threshold, no contradictions, grounded locations,
                           readable transcript: the report is linked automatically.
* ``possible_duplicate`` — score >= possible threshold (or a likely match that was capped):
                           kept as a separate incident plus a suggestion for human review.
* ``distinct``           — kept separate.

Semantic text similarity (character trigram overlap) is only a small optional bonus; the
decision is driven by place, landmark, hazard, facts, counts and time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .gazetteer import haversine_km, load_gazetteer
from .lexicon import LIFE_THREAT_DANGERS
from .text_utils import char_ngrams, jaccard, normalize

GROUNDED = {"grounded", "verified"}


@dataclass
class Profile:
    """Comparable view of one report or one incident (aggregate of its reports)."""
    place_id: str | None = None
    location_status: str = "missing"  # grounded | verified | ambiguous | conflicting | unmapped | landmark_only | missing
    candidates: set[str] = field(default_factory=set)
    unmapped_name: str | None = None
    landmark_ids: set[str] = field(default_factory=set)
    landmark_types: set[str] = field(default_factory=set)
    coords: tuple[float, float] | None = None  # human-verified custom coordinates only
    disaster_type: str = "unknown"
    facts: set[str] = field(default_factory=set)
    people_counts: list[int] = field(default_factory=list)
    families: list[int] = field(default_factory=list)
    says_safe: bool = False
    life_threat: bool = False
    times: list[datetime] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    low_quality: bool = False


def facts_of(ext: dict) -> set[str]:
    vul = ext.get("vulnerable_people") or {}
    facts = set(ext.get("reported_danger") or []) | set(ext.get("immediate_needs") or [])
    facts |= {f"vulnerable:{k}" for k, v in vul.items() if v}
    if ext.get("medical_emergency"):
        facts.add("medical_emergency")
    if ext.get("critical_medication"):
        facts.add("critical_medication")
    return facts


def report_profile(ext: dict, received_at: datetime, transcript: str | None) -> Profile:
    loc = ext.get("location") or {}
    pa = ext.get("people_affected") or {}
    status = loc.get("status", "missing")
    return Profile(
        place_id=loc.get("place_id") if status == "grounded" else None,
        location_status=status,
        candidates=set(loc.get("candidates") or []),
        unmapped_name=normalize(loc["place_name"]) if status == "unmapped" and loc.get("place_name") else None,
        landmark_ids={loc["landmark_id"]} if loc.get("landmark_id") else set(),
        landmark_types=set(loc.get("landmark_types") or []),
        disaster_type=ext.get("disaster_type", "unknown"),
        facts=facts_of(ext),
        people_counts=[pa["count"]] if pa.get("count") is not None else [],
        families=[pa["families"]] if pa.get("families") is not None else [],
        says_safe=bool(set(ext.get("status_claims") or []) & {"reported_safe", "reported_evacuated"}),
        life_threat=bool(set(ext.get("reported_danger") or []) & LIFE_THREAT_DANGERS),
        times=[received_at],
        texts=[transcript] if transcript else [],
        low_quality=ext.get("transcript_quality") == "low",
    )


@dataclass
class MatchResult:
    incident_id: str
    score: float
    outcome: str
    evidence: list[dict]
    contradictions: list[str]
    caps: list[str]

    def to_dict(self) -> dict:
        return {"incident_id": self.incident_id, "score": self.score, "outcome": self.outcome,
                "evidence": self.evidence, "contradictions": self.contradictions, "caps": self.caps}


def _place_name(pid: str) -> str:
    p = load_gazetteer().places.get(pid)
    return p.name if p else pid


def score_pair(r: Profile, inc: Profile, incident_id: str, cfg: dict) -> MatchResult:
    d = cfg["dedup"]
    w = d["weights"]
    ev: list[dict] = []
    contra: list[str] = []

    def add(feature: str, detail: str, points: float | None = None) -> None:
        ev.append({"feature": feature, "points": round(w[feature] if points is None else points, 3), "detail": detail})

    # --- place -------------------------------------------------------------
    if r.place_id and inc.place_id:
        if r.place_id == inc.place_id:
            add("same_place", f"both name {_place_name(r.place_id)}")
        else:
            add("different_place", f"{_place_name(r.place_id)} vs {_place_name(inc.place_id)}")
    elif r.place_id and inc.coords:
        gp = load_gazetteer().places[r.place_id]
        km = haversine_km(gp.latitude, gp.longitude, *inc.coords)
        if km <= d["coords_near_km"]:
            add("coords_near", f"verified incident position {km:.2f} km from {gp.name} reference point")
        elif km >= d["coords_far_km"]:
            add("coords_far", f"verified incident position {km:.1f} km away")
    elif r.place_id and r.place_id in inc.candidates:
        add("candidate_place", f"{_place_name(r.place_id)} is one of the incident's possible places")
    elif inc.place_id and inc.place_id in r.candidates:
        add("candidate_place", f"{_place_name(inc.place_id)} is one of the report's possible places")
    elif r.unmapped_name and inc.unmapped_name:
        if r.unmapped_name == inc.unmapped_name:
            add("same_unmapped_place_name", f"both name '{r.unmapped_name}' (not in reference data)")
        else:
            add("different_unmapped_place_name", f"'{r.unmapped_name}' vs '{inc.unmapped_name}'")

    # --- landmark ----------------------------------------------------------
    if r.landmark_ids and inc.landmark_ids:
        common = r.landmark_ids & inc.landmark_ids
        if common:
            add("same_landmark", f"same reference landmark ({', '.join(sorted(common))})")
        else:
            add("different_landmark", f"{', '.join(sorted(r.landmark_ids))} vs {', '.join(sorted(inc.landmark_ids))}")
    elif r.landmark_types & inc.landmark_types:
        add("landmark_type_overlap", f"both mention a {', '.join(sorted(r.landmark_types & inc.landmark_types))}")

    # --- hazard ------------------------------------------------------------
    if r.disaster_type != "unknown" and inc.disaster_type != "unknown":
        if r.disaster_type == inc.disaster_type:
            add("same_hazard", r.disaster_type)
        else:
            add("different_hazard", f"{r.disaster_type} vs {inc.disaster_type}")
            contra.append(f"Hazard differs ({r.disaster_type} vs {inc.disaster_type})")

    # --- reported facts ----------------------------------------------------
    if r.facts and inc.facts:
        j = jaccard(r.facts, inc.facts)
        if j > 0:
            add("fact_overlap", f"{len(r.facts & inc.facts)} shared facts: {', '.join(sorted(r.facts & inc.facts))}",
                w["fact_overlap"] * j)
        else:
            add("facts_disjoint", "no reported danger/need/vulnerable group in common")

    # --- counts --------------------------------------------------------------
    if r.people_counts and inc.people_counts:
        rc, ic = max(r.people_counts), max(inc.people_counts)
        ratio = max(rc, ic) / min(rc, ic)
        if ratio <= 1.2:
            add("same_people_count", f"{rc} vs {ic} people")
        elif ratio >= 2:
            contra.append(f"People count differs ({rc} vs {ic})")
    elif r.families and inc.families and max(r.families) == max(inc.families):
        add("same_people_count", f"{max(r.families)} families in both")

    # --- status --------------------------------------------------------------
    if (r.says_safe and inc.life_threat) or (r.life_threat and inc.says_safe):
        contra.append("One side says people are safe/evacuated, the other describes a threat to life")

    # --- time ----------------------------------------------------------------
    if r.times and inc.times:
        gap = min(abs((r.times[0] - t).total_seconds()) for t in inc.times) / 60
        if gap > d["time_window_minutes"]:
            add("outside_time_window", f"{gap:.0f} min apart (window {d['time_window_minutes']} min)")

    # --- optional text similarity ------------------------------------------
    if r.texts and inc.texts:
        sim = max(jaccard(char_ngrams(r.texts[0]), char_ngrams(t)) for t in inc.texts)
        if sim >= 0.05:
            add("text_similarity", f"transcript character-trigram overlap {sim:.2f}", w["text_similarity"] * sim)

    total = round(sum(e["points"] for e in ev), 3)
    caps: list[str] = []
    if r.location_status not in GROUNDED:
        caps.append("report location is not grounded")
    if inc.location_status not in GROUNDED:
        caps.append("incident location is not grounded")
    if r.low_quality:
        caps.append("report transcript is low quality")

    if total >= d["likely_threshold"]:
        outcome = "possible_duplicate" if (contra or caps) else "likely_duplicate"
    elif total >= d["possible_threshold"]:
        outcome = "possible_duplicate"
    else:
        outcome = "distinct"
    return MatchResult(incident_id, total, outcome, ev, contra, caps)


@dataclass
class Decision:
    outcome: str  # likely_duplicate | possible_duplicate | new_incident
    incident_id: str | None
    best: MatchResult | None
    suggestions: list[MatchResult]
    considered: int

    def to_dict(self) -> dict:
        return {"outcome": self.outcome, "incident_id": self.incident_id,
                "best": self.best.to_dict() if self.best else None,
                "suggestions": [s.to_dict() for s in self.suggestions], "considered": self.considered}


def decide(r: Profile, incidents: dict[str, Profile], cfg: dict) -> Decision:
    results = sorted((score_pair(r, p, iid, cfg) for iid, p in incidents.items()),
                     key=lambda m: (-m.score, m.incident_id))
    best = results[0] if results else None
    if best and best.outcome == "likely_duplicate":
        return Decision("likely_duplicate", best.incident_id, best, [], len(results))
    sugg = [m for m in results if m.outcome == "possible_duplicate"][: cfg["dedup"]["max_suggestions"]]
    return Decision("possible_duplicate" if sugg else "new_incident", None, best, sugg, len(results))
