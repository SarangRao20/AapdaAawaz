"""Database engine/session setup (SQLite, persistent on disk)."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

settings.var_dir.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False, "timeout": 30},
    future=True,
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


SCHEMA_VERSION = 2

# Columns added after initial schema — applied as idempotent ALTER TABLE statements
_MIGRATIONS: list[str] = [
    # v2: agentic follow-up fields on reports
    "ALTER TABLE reports ADD COLUMN follow_up_needed BOOLEAN NOT NULL DEFAULT 0",
    "ALTER TABLE reports ADD COLUMN follow_up_questions JSON",
    "ALTER TABLE reports ADD COLUMN follow_up_missing_fields JSON",
    "ALTER TABLE reports ADD COLUMN follow_up_status VARCHAR(20) NOT NULL DEFAULT 'none'",
]


def _run_migrations(conn) -> None:
    """Apply ALTER TABLE migrations that SQLite's create_all cannot handle."""
    for sql in _MIGRATIONS:
        try:
            conn.execute(text(sql))
        except Exception as exc:
            # SQLite raises "duplicate column name" when the column already exists;
            # that is the only error we want to swallow here.
            if "duplicate column name" not in str(exc).lower():
                raise


def init_db() -> None:
    """Create tables if they do not exist. Never drops data."""
    from . import models  # noqa: F401  (register models)

    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        _run_migrations(conn)
        conn.commit()
    with session_scope() as db:
        current = db.get(models.AppSetting, "schema_version")
        if current is None:
            db.add(models.AppSetting(key="schema_version", value=SCHEMA_VERSION))
        elif current.value < SCHEMA_VERSION:
            current.value = SCHEMA_VERSION


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
