"""Explainable, deterministic priority scoring (decision support only).

Severity and information confidence are kept separate: missing or uncertain fields never
lower the severity score — they are listed as ``missing_info`` and routed to human review.
The weights are configurable prototype defaults (services/settings_store.py); they are NOT
an operationally or clinically validated triage algorithm and do not decide rescue order.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .lexicon import ESCALATING_DANGERS, LIFE_THREAT_DANGERS

LABEL_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}
BASIC_NEEDS = {"food", "drinking_water", "shelter"}
URGENCY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "unknown": 0}


@dataclass
class SeverityFeatures:
    dangers: set[str] = field(default_factory=set)
    needs: set[str] = field(default_factory=set)
    medical_emergency: bool | None = None
    critical_medication: bool | None = None
    vulnerable: set[str] = field(default_factory=set)
    people_count: int | None = None
    caller_urgency: str = "unknown"
    status_claims: set[str] = field(default_factory=set)
    location_grounded: bool = False


def features_from_extraction(ext: dict) -> SeverityFeatures:
    vul = ext.get("vulnerable_people") or {}
    return SeverityFeatures(
        dangers=set(ext.get("reported_danger") or []),
        needs=set(ext.get("immediate_needs") or []),
        medical_emergency=ext.get("medical_emergency"),
        critical_medication=ext.get("critical_medication"),
        vulnerable={k for k, v in vul.items() if v},
        people_count=(ext.get("people_affected") or {}).get("count"),
        caller_urgency=ext.get("urgency") or "unknown",
        status_claims=set(ext.get("status_claims") or []),
        location_grounded=(ext.get("location") or {}).get("status") == "grounded",
    )


def label_for(score: float, thresholds: dict) -> str:
    if score >= thresholds["critical"]:
        return "critical"
    if score >= thresholds["high"]:
        return "high"
    if score >= thresholds["medium"]:
        return "medium"
    return "low"


def score(f: SeverityFeatures, cfg: dict, override_label: str | None = None) -> dict:
    """Return {score, label, computed_label, factors, missing_info, notes}."""
    w = cfg["priority"]["weights"]
    factors: list[dict] = []

    def add(key: str, label: str, detail: str, points: float | None = None) -> None:
        pts = w[key] if points is None else points
        if pts:
            factors.append({"key": key, "label": label, "points": pts, "detail": detail})

    life = sorted(f.dangers & LIFE_THREAT_DANGERS)
    if life:
        add("life_threat", "Explicit threat to life", ", ".join(life))
    if f.medical_emergency:
        add("medical_emergency", "Medical emergency described", "caller described an acute medical emergency")
    if "injured" in f.dangers:
        add("injured", "Injuries reported", "injured people mentioned")
    if f.critical_medication:
        add("critical_medication", "Critical medication / oxygen need", "insulin, oxygen or dialysis mentioned")
    if "rescue_evacuation" in f.needs:
        add("rescue_requested", "Rescue / evacuation requested", "caller asked for rescue, boat or evacuation")
    basic = sorted(f.needs & BASIC_NEEDS)
    if basic:
        add("basic_needs", "Basic needs", ", ".join(basic))
    if "fire_services" in f.needs:
        add("fire_services", "Fire services requested", "fire brigade or fire services requested")
    if "medical" in f.needs:
        add("medical_need", "Medical help requested", "medicine, doctor or ambulance requested")
    esc = sorted(f.dangers & ESCALATING_DANGERS)
    if esc:
        add("escalating_hazard", "Escalating hazard", ", ".join(esc))
    if f.vulnerable:
        pts = min(w["vulnerable_per_group"] * len(f.vulnerable), w["vulnerable_cap"])
        add("vulnerable_per_group", "Vulnerable people explicitly reported", ", ".join(sorted(f.vulnerable)), pts)
    if f.people_count is not None:
        if f.people_count >= 25:
            add("people_25_plus", "25+ people reported", f"{f.people_count} people")
        elif f.people_count >= 10:
            add("people_10_plus", "10+ people reported", f"{f.people_count} people")
    if "road_blocked" in f.dangers:
        add("access_blocked", "Access blocked", "road blocked")
    if f.caller_urgency in ("critical", "high", "medium"):
        add(f"caller_urgency_{f.caller_urgency}", f"Caller urgency: {f.caller_urgency}", "urgency words used by the caller")

    total = float(sum(x["points"] for x in factors))
    thresholds = cfg["priority"]["thresholds"]
    computed = label_for(total, thresholds)
    notes: list[str] = []
    label = computed

    says_safe = bool(f.status_claims & {"reported_safe", "reported_evacuated"})
    # When evacuation is confirmed, historical positional dangers (on_roof, trapped, surrounded)
    # are resolved — only ongoing acute dangers (medical, injury, active fire) block the cap.
    POSITIONAL_RESOLVED_BY_EVACUATION = {"on_roof", "trapped", "surrounded_by_water"}
    if says_safe and "reported_evacuated" in f.status_claims:
        unresolved_life = (f.dangers & LIFE_THREAT_DANGERS) - POSITIONAL_RESOLVED_BY_EVACUATION
        acute = bool(unresolved_life) or bool(f.medical_emergency) or "injured" in f.dangers
    else:
        acute = bool(life) or bool(f.medical_emergency) or "injured" in f.dangers
    if says_safe and not acute:
        cap = cfg["priority"]["safe_status_cap"]
        if LABEL_RANK[label] > LABEL_RANK[cap]:
            notes.append(f"Capped at '{cap}': callers report people are currently safe/evacuated")
            label = cap

    missing: list[str] = []
    if not f.location_grounded:
        missing.append("Location not grounded to a reference place")
    if f.people_count is None:
        missing.append("Number of people unknown")
    if f.caller_urgency == "unknown":
        missing.append("Caller urgency not stated")
    if not factors:
        missing.append("No specific danger or need identified")

    if override_label:
        if override_label != label:
            notes.append(f"Dispatcher set priority to '{override_label}' (computed: '{label}')")
        label = override_label

    return {
        "score": total,
        "label": label,
        "computed_label": computed,
        "factors": sorted(factors, key=lambda x: -x["points"]),
        "missing_info": missing,
        "notes": notes,
        "thresholds": thresholds,
        "disclaimer": "Prototype decision-support score; not a validated triage or rescue-ordering algorithm.",
    }


def sort_key(label: str, score_value: float) -> tuple[int, float]:
    return (LABEL_RANK.get(label, 0), score_value)
