"""Runtime-configurable thresholds and weights (persisted in the app_settings table).

All rules are deterministic and documented in docs/ARCHITECTURE.md. These numbers are
prototype defaults chosen against the synthetic dataset; they are NOT operationally or
clinically validated.
"""
from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.orm import Session

from .. import models

DEFAULTS: dict[str, Any] = {
    "gate": {
        # Rule-evidence level (0-1, see extraction.py lookup table) below which a field needs review.
        "min_location_confidence": 0.7,
        "min_people_confidence": 0.5,
        # Unknown people count triggers review when the priority is at or above this label
        # ("critical" | "high" | "medium" | "low" | "never").
        "unknown_people_review_at": "high",
        "flag_low_quality_transcript": True,
        "flag_unclear_urgency": True,
    },
    "dedup": {
        "likely_threshold": 0.7,
        "possible_threshold": 0.4,
        "time_window_minutes": 360,
        "max_suggestions": 3,
        "weights": {
            "same_place": 0.5,
            "different_place": -0.6,
            "candidate_place": 0.2,
            "same_unmapped_place_name": 0.35,
            "different_unmapped_place_name": -0.3,
            "coords_near": 0.5,
            "coords_far": -0.6,
            "same_landmark": 0.25,
            "different_landmark": -0.4,
            "landmark_type_overlap": 0.1,
            "same_hazard": 0.15,
            "different_hazard": -0.35,
            "fact_overlap": 0.2,
            "facts_disjoint": -0.15,
            "same_people_count": 0.1,
            "outside_time_window": -0.5,
            "text_similarity": 0.1,
        },
        "coords_near_km": 0.5,
        "coords_far_km": 5.0,
    },
    "priority": {
        "weights": {
            "life_threat": 55,  # an explicit threat to life alone reaches "critical"
            "medical_emergency": 45,
            "injured": 25,
            "critical_medication": 25,
            "rescue_requested": 20,
            "basic_needs": 12,
            "medical_need": 10,
            "escalating_hazard": 10,
            "vulnerable_per_group": 6,
            "vulnerable_cap": 18,
            "people_10_plus": 5,
            "people_25_plus": 10,
            "access_blocked": 3,
            "caller_urgency_critical": 10,
            "caller_urgency_high": 6,
            "caller_urgency_medium": 2,
        },
        "thresholds": {"critical": 55, "high": 25, "medium": 10},
        # A report/incident where callers say everyone is safe (and nothing contradicts it)
        # is capped at this label.
        "safe_status_cap": "medium",
    },
    "providers": {"stt": "auto", "tts": "auto"},
}

_ALLOWED_STT = {"auto", "mock", "prisma"}
_ALLOWED_TTS = {"auto", "none"}
_LABELS = ("critical", "high", "medium", "low", "never")


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _merge(out[k], v)
        elif k in out:
            out[k] = v
    return out


def get_config(db: Session | None) -> dict[str, Any]:
    if db is None:
        return copy.deepcopy(DEFAULTS)
    row = db.get(models.AppSetting, "runtime_config")
    return _merge(DEFAULTS, row.value if row else {})


def validate_update(section: str, values: dict) -> dict:
    """Validate a partial update for one section; raises ValueError with a readable message."""
    if section not in DEFAULTS:
        raise ValueError(f"unknown settings section {section!r}")
    merged = _merge(DEFAULTS[section], values)
    if section == "gate":
        for k in ("min_location_confidence", "min_people_confidence"):
            if not 0.0 <= float(merged[k]) <= 1.0:
                raise ValueError(f"gate.{k} must be between 0 and 1")
        if merged["unknown_people_review_at"] not in _LABELS:
            raise ValueError(f"gate.unknown_people_review_at must be one of {_LABELS}")
    elif section == "dedup":
        lk, ps = float(merged["likely_threshold"]), float(merged["possible_threshold"])
        if not 0 < ps < lk <= 2:
            raise ValueError("dedup thresholds must satisfy 0 < possible < likely <= 2")
        if int(merged["time_window_minutes"]) < 1:
            raise ValueError("dedup.time_window_minutes must be positive")
    elif section == "priority":
        t = merged["thresholds"]
        if not 0 < float(t["medium"]) < float(t["high"]) < float(t["critical"]):
            raise ValueError("priority thresholds must satisfy 0 < medium < high < critical")
        for k, v in merged["weights"].items():
            if not isinstance(v, (int, float)) or v < 0:
                raise ValueError(f"priority weight {k} must be a non-negative number")
        if merged["safe_status_cap"] not in ("critical", "high", "medium", "low"):
            raise ValueError("priority.safe_status_cap must be a priority label")
    elif section == "providers":
        if merged["stt"] not in _ALLOWED_STT:
            raise ValueError(f"providers.stt must be one of {sorted(_ALLOWED_STT)}")
        if merged["tts"] not in _ALLOWED_TTS:
            raise ValueError(f"providers.tts must be one of {sorted(_ALLOWED_TTS)}")
    return merged


def update_config(db: Session, changes: dict[str, dict], actor: str = "dispatcher") -> dict[str, Any]:
    row = db.get(models.AppSetting, "runtime_config")
    stored = dict(row.value) if row else {}
    for section, values in changes.items():
        if values is None:
            continue
        merged = validate_update(section, values)
        old = stored.get(section)
        stored[section] = merged
        db.add(models.AuditLog(entity_type="system", entity_id="settings", action="settings_updated",
                               field=section, old_value=old, new_value=merged, actor=actor))
    if row is None:
        db.add(models.AppSetting(key="runtime_config", value=stored))
    else:
        row.value = stored
    db.flush()
    return get_config(db)


def reset_config(db: Session) -> None:
    row = db.get(models.AppSetting, "runtime_config")
    if row is not None:
        db.delete(row)
