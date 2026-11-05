"""Pydantic schemas: the structured extraction contract and API request bodies.

Conventions
-----------
* ``None`` always means **unknown / not stated** — never zero, never "safe".
* Coordinates may only be populated from a reference dataset (simulated gazetteer) or
  a human reviewer; never from free text.
* Numeric ``confidence`` values produced by the rule-based extractor are *rule evidence
  scores* from a documented lookup table (see docs/EVALUATION.md), not probabilities.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DisasterType = Literal["flood", "earthquake", "landslide", "fire", "other", "unknown"]
Urgency = Literal["critical", "high", "medium", "low", "unknown"]
Language = Literal["mr", "hi", "en", "mixed", "unknown"]
LocationSource = Literal["caller_stated", "verified_reference", "simulated", "unknown"]
TranscriptQuality = Literal["ok", "low", "unknown"]
PriorityLabel = Literal["critical", "high", "medium", "low"]

NEED_TYPES = ("rescue_evacuation", "medical", "food", "drinking_water", "shelter", "fire_services")
DANGER_TYPES = (
    "trapped", "surrounded_by_water", "on_roof", "water_rising", "flooding_inside_home",
    "swept_away", "drowning", "structure_collapse", "under_debris", "injured", "unconscious",
    "active_fire", "missing_person", "road_blocked",
)


class Evidence(BaseModel):
    field: str
    text: str
    negated: bool = False


class ExtractedLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    place_name: str | None = None
    place_id: str | None = None  # id in the simulated reference gazetteer
    landmark: str | None = None
    landmark_id: str | None = None
    landmark_types: list[str] = Field(default_factory=list)  # e.g. ["bridge"] for "near the big bridge"
    district: str | None = None
    state: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    source: LocationSource = "unknown"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_basis: str = "no location information found"
    candidates: list[str] = Field(default_factory=list)
    stated_text: list[str] = Field(default_factory=list)
    status: Literal["grounded", "landmark_only", "ambiguous", "conflicting", "unmapped", "missing"] = "missing"

    @model_validator(mode="after")
    def _coords_need_reference(self) -> "ExtractedLocation":
        has_coords = self.latitude is not None or self.longitude is not None
        if has_coords:
            if self.latitude is None or self.longitude is None:
                raise ValueError("latitude and longitude must be provided together")
            if self.source not in ("simulated", "verified_reference"):
                raise ValueError("coordinates may only come from a reference dataset or human verification")
            if self.place_id is None:
                raise ValueError("coordinates require a reference place_id")
        return self


class PeopleAffected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int | None = Field(default=None, ge=1, le=100000)
    approximate: bool = False
    range: list[int] | None = None
    all_counts_mentioned: list[int] = Field(default_factory=list)
    families: int | None = Field(default=None, ge=1)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_basis: str = "no explicit people count stated"


class VulnerableMention(BaseModel):
    count: int | None = Field(default=None, ge=1)
    evidence: str


class VulnerablePeople(BaseModel):
    """Each field is None when NOT MENTIONED (unknown) — this never means 'none present'."""
    elderly: VulnerableMention | None = None
    children: VulnerableMention | None = None
    infants: VulnerableMention | None = None
    pregnant_people: VulnerableMention | None = None
    people_with_disabilities: VulnerableMention | None = None

    def mentioned(self) -> list[str]:
        return [k for k, v in self.__dict__.items() if v is not None]


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    disaster_type: DisasterType = "unknown"
    disaster_types_mentioned: list[str] = Field(default_factory=list)
    disaster_basis: str = "no hazard keyword found"
    location: ExtractedLocation = Field(default_factory=ExtractedLocation)
    people_affected: PeopleAffected = Field(default_factory=PeopleAffected)
    vulnerable_people: VulnerablePeople = Field(default_factory=VulnerablePeople)
    immediate_needs: list[str] = Field(default_factory=list)
    reported_danger: list[str] = Field(default_factory=list)
    medical_emergency: bool | None = None  # None = not mentioned (unknown), never assumed False
    medical_need: bool | None = None
    critical_medication: bool | None = None  # insulin / oxygen / dialysis explicitly mentioned
    urgency: Urgency = "unknown"
    urgency_basis: str = "caller did not express urgency explicitly"
    status_claims: list[str] = Field(default_factory=list)  # e.g. "reported_safe", "reported_evacuated"
    language: Language = "unknown"
    transcript_quality: TranscriptQuality = "unknown"
    transcript_quality_basis: str = ""
    summary: str = ""
    uncertainties: list[str] = Field(default_factory=list)
    requires_human_review: bool = True
    evidence: list[Evidence] = Field(default_factory=list)
    provider: str = "unknown"
    provider_mode: str = "unknown"

    @field_validator("immediate_needs")
    @classmethod
    def _valid_needs(cls, v: list[str]) -> list[str]:
        bad = [x for x in v if x not in NEED_TYPES]
        if bad:
            raise ValueError(f"unknown need types: {bad}")
        return sorted(set(v), key=NEED_TYPES.index)

    @field_validator("reported_danger")
    @classmethod
    def _valid_dangers(cls, v: list[str]) -> list[str]:
        bad = [x for x in v if x not in DANGER_TYPES]
        if bad:
            raise ValueError(f"unknown danger types: {bad}")
        return sorted(set(v), key=DANGER_TYPES.index)


# ---------------------------------------------------------------------------
# API request bodies
# ---------------------------------------------------------------------------
class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcript: str | None = Field(default=None, max_length=5000)
    language_hint: Language | None = None
    source: Literal["manual_text", "upload", "recording"] = "manual_text"
    process: bool = Field(default=False, description="Start processing immediately (requires transcript)")

    @field_validator("transcript")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class TranscriptSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=5000)
    language_hint: Language | None = None
    reviewer: str = Field(default="dispatcher", min_length=1, max_length=80)
    process: bool = True


class LocationOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    place_id: str | None = Field(default=None, description="Pick a place from the reference list")
    place_name: str | None = Field(default=None, max_length=200)
    landmark: str | None = Field(default=None, max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def _need_something(self) -> "LocationOverride":
        if self.place_id is None and self.place_name is None and self.latitude is None:
            raise ValueError("provide place_id, place_name, or latitude/longitude")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        return self


class IncidentReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer: str = Field(min_length=1, max_length=80)
    notes: str | None = Field(default=None, max_length=2000)
    verify_location: LocationOverride | None = None
    confirm_current_location: bool = False
    people_count: int | None = Field(default=None, ge=1, le=100000)
    clear_people_count: bool = False
    urgency: Urgency | None = None
    disaster_type: DisasterType | None = None
    mark_reviewed: bool = False


class MergeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_incident_ids: list[str] = Field(min_length=1, max_length=50)
    reviewer: str = Field(min_length=1, max_length=80)
    notes: str | None = Field(default=None, max_length=2000)


class SplitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_ids: list[str] = Field(min_length=1, max_length=200)
    reviewer: str = Field(min_length=1, max_length=80)
    notes: str | None = Field(default=None, max_length=2000)


class IncidentResolveRequest(BaseModel):
    """Take an incident off the live board once responders have dealt with it."""
    model_config = ConfigDict(extra="forbid")

    reviewer: str = Field(min_length=1, max_length=80)
    reason: Literal["rescued", "false_alarm", "handled_elsewhere", "duplicate"] = "rescued"
    notes: str | None = Field(default=None, max_length=2000)


class IncidentReopenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer: str = Field(min_length=1, max_length=80)
    notes: str | None = Field(default=None, max_length=2000)


class SuggestionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer: str = Field(min_length=1, max_length=80)
    notes: str | None = Field(default=None, max_length=2000)


class SeedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["all", "remaining"] = "remaining"


class InjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_id: str = Field(min_length=1, max_length=40)
    use_audio: bool = True


class ResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reseed: bool = False


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate: dict | None = None
    dedup: dict | None = None
    priority: dict | None = None
    providers: dict | None = None
