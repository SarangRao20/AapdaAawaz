"""Synthetic demo data: repeatable seeding, single-report injection, and full reset.

All seeded reports are labelled SYNTHETIC. Received times are placed on a scenario clock
(``offset_minutes`` before "now") so the feed has a realistic order; processing happens in
that order, which makes the clustering result deterministic.
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import timedelta
from functools import lru_cache

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models
from ..config import DATA_DIR, settings
from .pipeline import PIPELINE_LOCK, audit, process_report, utcnow
from .settings_store import reset_config
from .storage import store_audio

log = logging.getLogger("aapda.demo")
AUDIO_DIR = DATA_DIR / "audio"
SCENARIO_SPAN_MIN = 100


@lru_cache(maxsize=1)
def load_fixtures() -> dict:
    return json.loads((DATA_DIR / "synthetic_reports.json").read_text(encoding="utf-8"))


def fixtures_by_id() -> dict[str, dict]:
    return {f["id"]: f for f in load_fixtures()["reports"]}


def report_id_for(fixture_id: str) -> str:
    return f"R-{fixture_id}"


def ensure_ground_truth(db: Session) -> None:
    existing = set(db.scalars(select(models.GroundTruth.fixture_id)))
    for fx in load_fixtures()["reports"]:
        if fx["id"] not in existing:
            db.add(models.GroundTruth(fixture_id=fx["id"], data=fx["ground_truth"], is_synthetic=True))


def _attach_fixture_audio(db: Session, report: models.Report, filename: str) -> bool:
    path = AUDIO_DIR / filename
    if not path.is_file():
        return False
    stored = store_audio(path.read_bytes())
    db.add(models.AudioFile(report_id=report.id, kind="fixture", original_filename=filename,
                            stored_name=stored.stored_name, mime_type=stored.mime_type,
                            size_bytes=stored.size_bytes, sha256=stored.sha256))
    return True


def _create_fixture_report(db: Session, fx: dict, received_at, use_audio: bool) -> models.Report:
    rep = models.Report(
        id=report_id_for(fx["id"]), received_at=received_at, source="synthetic_fixture", is_synthetic=True,
        synthetic_label=load_fixtures()["label"], fixture_id=fx["id"], language_hint=fx["language_hint"],
        status="received", review_reasons=[],
    )
    db.add(rep)
    db.flush()
    has_audio = bool(use_audio and fx.get("audio_fixture") and _attach_fixture_audio(db, rep, fx["audio_fixture"]))
    if not has_audio:
        # Authored text fixture: stored as a transcript but never labelled as speech-recognition output.
        rep.transcript = fx["transcript"]
        rep.transcript_source, rep.transcript_provider, rep.transcript_provider_mode = (
            "synthetic_fixture", "synthetic-dataset", "fixture")
    return rep


def seed(db: Session, mode: str = "remaining") -> dict:
    with PIPELINE_LOCK:
        ensure_ground_truth(db)
        existing = set(db.scalars(select(models.Report.fixture_id).where(models.Report.fixture_id.is_not(None))))
        fixtures = sorted(load_fixtures()["reports"], key=lambda f: f["offset_minutes"])
        if mode == "all" and existing:
            raise ValueError("demo data already present; reset first or use mode='remaining'")
        start = utcnow() - timedelta(minutes=SCENARIO_SPAN_MIN)
        created = []
        for fx in fixtures:
            if fx["id"] in existing:
                continue
            rep = _create_fixture_report(db, fx, start + timedelta(minutes=fx["offset_minutes"]), use_audio=True)
            created.append(rep.id)
        audit(db, "system", "demo", "seeded", new={"mode": mode, "count": len(created)})
        db.commit()
    # Process in scenario order (synchronously, so the response reflects the final state).
    for rid in created:
        process_report(db, rid)
    statuses = dict.fromkeys(created)
    for rid in created:
        statuses[rid] = db.get(models.Report, rid).status
    return {"created": len(created), "skipped_existing": len(existing),
            "statuses": {s: sum(1 for v in statuses.values() if v == s) for s in set(statuses.values())}}


def inject(db: Session, fixture_id: str, use_audio: bool) -> models.Report:
    fx = fixtures_by_id().get(fixture_id)
    if fx is None:
        raise LookupError(f"unknown fixture {fixture_id}")
    with PIPELINE_LOCK:
        if db.get(models.Report, report_id_for(fixture_id)) is not None:
            raise ValueError(f"{fixture_id} is already loaded; reset the demo to inject it again")
        ensure_ground_truth(db)
        rep = _create_fixture_report(db, fx, utcnow(), use_audio)
        rep.status = "queued"
        audit(db, "system", "demo", "injected", new={"fixture": fixture_id, "audio": bool(rep.audio_files)})
        db.commit()
        return rep


def reset(db: Session, reset_settings: bool = False) -> dict:
    with PIPELINE_LOCK:
        counts = {}
        for model in (models.DuplicateSuggestion, models.IncidentLink, models.ReviewRecord, models.Acknowledgement,
                      models.ProcessingJob, models.AudioFile, models.Incident, models.Report, models.AuditLog,
                      models.EvaluationRun):
            counts[model.__tablename__] = db.execute(delete(model)).rowcount
        if reset_settings:
            reset_config(db)
        audit(db, "system", "demo", "reset", new=counts)
        db.commit()
    for d in (settings.upload_dir, settings.tts_dir):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
    return counts
