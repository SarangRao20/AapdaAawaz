"""Single background worker thread so long transcriptions never block API requests."""
from __future__ import annotations

import logging
import queue
import threading

from sqlalchemy import select

from .. import models
from ..db import SessionLocal
from .pipeline import mark_failed, process_report

log = logging.getLogger("aapda.worker")


class Worker:
    def __init__(self) -> None:
        self._q: queue.Queue[str | None] = queue.Queue()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="aapda-worker", daemon=True)
        self._thread.start()
        self._requeue_interrupted()

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            self._q.put(None)
            self._thread.join(timeout=5)

    def enqueue(self, report_id: str) -> None:
        self._q.put(report_id)

    def pending(self) -> int:
        return self._q.qsize()

    def _requeue_interrupted(self) -> None:
        db = SessionLocal()
        try:
            ids = db.scalars(select(models.Report.id).where(
                models.Report.status.in_(("queued", "transcribing", "extracting")))).all()
        finally:
            db.close()
        for rid in ids:
            log.info("re-queueing interrupted report %s", rid)
            self.enqueue(rid)

    def _loop(self) -> None:
        while True:
            rid = self._q.get()
            if rid is None:
                return
            db = SessionLocal()
            try:
                process_report(db, rid)
            except Exception as exc:  # keep the worker alive; surface the error on the report
                log.exception("processing %s failed", rid)
                db.rollback()
                mark_failed(db, rid, f"{type(exc).__name__}: {exc}")
            finally:
                db.close()


worker = Worker()
