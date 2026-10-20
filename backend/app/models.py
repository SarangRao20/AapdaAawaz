"""SQLAlchemy ORM models.

Raw report data (transcript, original extraction) is kept separate from the aggregated
incident representation. Merges/splits only deactivate association rows; nothing is deleted.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # synthetic_fixture | upload | recording | manual_text
    source: Mapped[str] = mapped_column(String(32))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    synthetic_label: Mapped[str | None] = mapped_column(String(200))
    fixture_id: Mapped[str | None] = mapped_column(String(40), index=True)
    language_hint: Mapped[str | None] = mapped_column(String(16))
    # received | queued | transcribing | extracting | processed | needs_transcript | failed
    status: Mapped[str] = mapped_column(String(32), default="received", index=True)

    transcript: Mapped[str | None] = mapped_column(Text)
    # synthetic_fixture | prisma | mock_fixture_lookup | manual_entry
    transcript_source: Mapped[str | None] = mapped_column(String(40))
    transcript_provider: Mapped[str | None] = mapped_column(String(60))
    transcript_provider_mode: Mapped[str | None] = mapped_column(String(20))  # real | mock | fixture | human
    transcript_request_id: Mapped[str | None] = mapped_column(String(120))
    transcript_raw: Mapped[Any | None] = mapped_column(JSON)
    stt_error: Mapped[str | None] = mapped_column(Text)

    extraction_original: Mapped[Any | None] = mapped_column(JSON)  # immutable after first processing
    extraction_current: Mapped[Any | None] = mapped_column(JSON)
    extraction_provider: Mapped[str | None] = mapped_column(String(60))
    extraction_mode: Mapped[str | None] = mapped_column(String(20))

    field_assessment: Mapped[Any | None] = mapped_column(JSON)
    review_reasons: Mapped[Any] = mapped_column(JSON, default=list)
    gate_status: Mapped[str | None] = mapped_column(String(20), index=True)  # passed | needs_review
    review_resolved: Mapped[bool] = mapped_column(Boolean, default=False)

    report_priority_score: Mapped[float | None] = mapped_column(Float)
    report_priority_label: Mapped[str | None] = mapped_column(String(16))
    priority_breakdown: Mapped[Any | None] = mapped_column(JSON)

    dedup_outcome: Mapped[str | None] = mapped_column(String(32))  # new_incident | likely_duplicate | possible_duplicate
    dedup_evidence: Mapped[Any | None] = mapped_column(JSON)
    auto_incident_id: Mapped[str | None] = mapped_column(String(40))  # incident chosen by the system (for evaluation)

    processing_ms: Mapped[int | None] = mapped_column(Integer)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)

    audio_files: Mapped[list["AudioFile"]] = relationship(back_populates="report", cascade="all, delete-orphan")
    jobs: Mapped[list["ProcessingJob"]] = relationship(back_populates="report", cascade="all, delete-orphan",
                                                       order_by="ProcessingJob.id")


class AudioFile(Base):
    __tablename__ = "audio_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="caller_audio")  # caller_audio | fixture
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(60))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    report: Mapped[Report] = relationship(back_populates="audio_files")


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active | merged | closed
    merged_into_id: Mapped[str | None] = mapped_column(String(40))

    disaster_type: Mapped[str] = mapped_column(String(20), default="unknown")
    location: Mapped[Any | None] = mapped_column(JSON)
    # human_verified | simulated_reference | caller_stated_unmapped | ambiguous | unknown
    location_status: Mapped[str] = mapped_column(String(32), default="unknown")
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    people_count: Mapped[int | None] = mapped_column(Integer)
    people_detail: Mapped[Any | None] = mapped_column(JSON)
    vulnerable: Mapped[Any | None] = mapped_column(JSON)
    needs: Mapped[Any] = mapped_column(JSON, default=list)
    dangers: Mapped[Any] = mapped_column(JSON, default=list)
    medical_emergency: Mapped[bool | None] = mapped_column(Boolean)
    urgency: Mapped[str] = mapped_column(String(16), default="unknown")
    languages: Mapped[Any] = mapped_column(JSON, default=list)
    summary: Mapped[str | None] = mapped_column(Text)

    priority_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    priority_label: Mapped[str] = mapped_column(String(16), default="low", index=True)
    priority_breakdown: Mapped[Any | None] = mapped_column(JSON)
    info_confidence: Mapped[Any | None] = mapped_column(JSON)
    review_reasons: Mapped[Any] = mapped_column(JSON, default=list)
    contradictions: Mapped[Any] = mapped_column(JSON, default=list)
    missing_info: Mapped[Any] = mapped_column(JSON, default=list)
    recommended_action: Mapped[str | None] = mapped_column(Text)
    # needs_review | reviewed | rereview_needed | no_review_required
    review_status: Mapped[str] = mapped_column(String(24), default="needs_review", index=True)
    human_overrides: Mapped[Any] = mapped_column(JSON, default=dict)
    report_count: Mapped[int] = mapped_column(Integer, default=0)
    last_report_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IncidentLink(Base):
    """Report-to-incident association. Rows are deactivated, never deleted."""
    __tablename__ = "incident_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id"), index=True)
    # new_incident | likely_duplicate | duplicate_confirmed | manual_merge | manual_split
    outcome: Mapped[str] = mapped_column(String(32))
    score: Mapped[float | None] = mapped_column(Float)
    evidence: Mapped[Any | None] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    actor: Mapped[str] = mapped_column(String(80), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DuplicateSuggestion(Base):
    __tablename__ = "duplicate_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id"), index=True)
    source_incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
    candidate_incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    score: Mapped[float] = mapped_column(Float)
    evidence: Mapped[Any | None] = mapped_column(JSON)
    contradictions: Mapped[Any] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending|confirmed|rejected|obsolete
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(80))
    note: Mapped[str | None] = mapped_column(Text)


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(32))  # transcription | extraction | confidence_gate | deduplication | priority
    provider: Mapped[str | None] = mapped_column(String(60))
    provider_mode: Mapped[str | None] = mapped_column(String(20))  # real | mock | rule_based | fixture | human
    status: Mapped[str] = mapped_column(String(16))  # running | succeeded | failed | skipped
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[Any | None] = mapped_column(JSON)

    report: Mapped[Report] = relationship(back_populates="jobs")


class ReviewRecord(Base):
    __tablename__ = "review_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str | None] = mapped_column(String(40), index=True)
    report_id: Mapped[str | None] = mapped_column(String(40), index=True)
    reviewer: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[Any | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(20), index=True)  # report | incident | suggestion | system
    entity_id: Mapped[str] = mapped_column(String(40), index=True)
    action: Mapped[str] = mapped_column(String(40))
    field: Mapped[str | None] = mapped_column(String(80))
    old_value: Mapped[Any | None] = mapped_column(JSON)
    new_value: Mapped[Any | None] = mapped_column(JSON)
    actor: Mapped[str] = mapped_column(String(80), default="system")
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GroundTruth(Base):
    """Labels for SYNTHETIC evaluation reports only."""
    __tablename__ = "ground_truth"

    fixture_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    data: Mapped[Any] = mapped_column(JSON)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class Acknowledgement(Base):
    __tablename__ = "acknowledgements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    language: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(60))
    provider_mode: Mapped[str | None] = mapped_column(String(20))
    audio_stored_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20))  # text_only | audio_ready | audio_failed
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    results: Mapped[Any] = mapped_column(JSON)
