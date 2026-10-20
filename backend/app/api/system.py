from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..db import SCHEMA_VERSION, get_db
from ..providers.registry import provider_status
from ..schemas import InjectRequest, ResetRequest, SeedRequest, SettingsUpdate
from ..services import demo, evaluation, stats
from ..services.gazetteer import load_gazetteer
from ..services.settings_store import get_config, update_config
from ..services.worker import worker
from .serializers import audit_view, iso, report_detail

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    cfg = get_config(db)
    return {"status": "ok", "database": "ok", "schema_version": SCHEMA_VERSION, "worker_queue": worker.pending(),
            "providers": provider_status(cfg["providers"]["stt"], cfg["providers"]["tts"])}


@router.get("/dashboard/stats")
def dashboard_stats(db: Session = Depends(get_db)):
    return stats.dashboard(db)


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    cfg = get_config(db)
    return {"config": cfg, "providers": provider_status(cfg["providers"]["stt"], cfg["providers"]["tts"]),
            "environment": {"max_upload_mb": settings.max_upload_mb, "extraction_provider": settings.extraction_provider,
                            "gnani_base_url": settings.gnani_base_url}}


@router.put("/settings")
def put_settings(body: SettingsUpdate, actor: str = Query("dispatcher", max_length=80), db: Session = Depends(get_db)):
    try:
        cfg = update_config(db, body.model_dump(exclude_none=True), actor)
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        raise HTTPException(422, f"invalid settings: {exc}") from exc
    db.commit()
    return {"config": cfg, "providers": provider_status(cfg["providers"]["stt"], cfg["providers"]["tts"]),
            "note": "New thresholds apply to reports processed from now on; use Reprocess to re-score existing ones."}


@router.get("/gazetteer")
def gazetteer():
    return load_gazetteer().to_public()


@router.get("/audit")
def audit_log(limit: int = Query(100, ge=1, le=1000), entity_type: str | None = None, db: Session = Depends(get_db)):
    stmt = select(models.AuditLog)
    if entity_type:
        stmt = stmt.where(models.AuditLog.entity_type == entity_type)
    return {"items": [audit_view(a) for a in db.scalars(stmt.order_by(models.AuditLog.id.desc()).limit(limit))]}


# ---- evaluation -------------------------------------------------------------
@router.get("/evaluation")
def get_evaluation(db: Session = Depends(get_db)):
    """Latest stored evaluation run (runs a fresh one if none exists)."""
    run = db.scalars(select(models.EvaluationRun).order_by(models.EvaluationRun.id.desc())).first()
    if run is None or "splits" not in run.results:
        return _run_evaluation(db, False)
    return run.results | {"run_id": run.id, "stored_at": iso(run.created_at)}


@router.post("/evaluation/run")
def run_evaluation(include_stt: bool = Query(False, description="also call the real STT provider on audio fixtures"),
                   db: Session = Depends(get_db)):
    return _run_evaluation(db, include_stt)


def _run_evaluation(db: Session, include_stt: bool) -> dict:
    results = evaluation.run(get_config(db), include_stt)
    run = models.EvaluationRun(results=results)
    db.add(run)
    db.commit()
    return results | {"run_id": run.id, "stored_at": iso(run.created_at)}


@router.get("/evaluation/export.csv")
def export_csv(db: Session = Depends(get_db)):
    run = db.scalars(select(models.EvaluationRun).order_by(models.EvaluationRun.id.desc())).first()
    results = run.results if run and "splits" in run.results else evaluation.run(get_config(db), False)
    return Response(evaluation.to_csv(results), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="aapda_evaluation_synthetic.csv"'})


# ---- demo -------------------------------------------------------------------
@router.get("/demo/fixtures")
def fixtures(db: Session = Depends(get_db)):
    loaded = set(db.scalars(select(models.Report.fixture_id).where(models.Report.fixture_id.is_not(None))))
    data = demo.load_fixtures()
    return {"label": data["label"], "notice": data["_notice"], "items": [
        {"id": f["id"], "language_hint": f["language_hint"], "scenario_tags": f["scenario_tags"],
         "transcript": f["transcript"], "has_audio": bool(f.get("audio_fixture")
                                                          and (demo.AUDIO_DIR / f["audio_fixture"]).is_file()),
         "loaded": f["id"] in loaded} for f in data["reports"]]}


@router.post("/demo/seed")
def seed(body: SeedRequest | None = None, db: Session = Depends(get_db)):
    try:
        result = demo.seed(db, (body or SeedRequest()).mode)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return result | {"stats": stats.dashboard(db)}


@router.post("/demo/inject", status_code=202, summary="Inject one synthetic report (processed by the worker)")
def inject(body: InjectRequest, db: Session = Depends(get_db)):
    try:
        rep = demo.inject(db, body.fixture_id, body.use_audio)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    worker.enqueue(rep.id)
    return report_detail(db, rep)


@router.post("/demo/reset")
def reset(body: ResetRequest | None = None, db: Session = Depends(get_db)):
    body = body or ResetRequest()
    counts = demo.reset(db)
    out = {"deleted": counts}
    if body.reseed:
        out["seed"] = demo.seed(db, "all")
    return out | {"stats": stats.dashboard(db)}
