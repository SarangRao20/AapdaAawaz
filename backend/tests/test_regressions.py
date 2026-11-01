"""Regressions: schema migrations, follow-up resilience and honest provenance, preprocessed-audio MIME type."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, text

from app import db as db_module
from app.providers.base import ProviderError, TranscriptionResult
from app.services import evaluation, followup, pipeline
from tests.conftest import wait_for

FIXTURE_WAV = Path(__file__).resolve().parent.parent / "data" / "audio" / "syn-001.wav"
INCOMPLETE = {"location": {"status": "missing"}, "disaster_type": "unknown", "people_affected": {"count": None}}


@pytest.mark.parametrize(("provider", "active", "phrase"), [
    ("rules", False, "the same rule-based extractor"),
    ("evon", True, "Gnani Evon v3.3"),
])
def test_evaluation_reports_evon_only_when_it_is_really_used(cfg, monkeypatch, provider, active, phrase):
    import app.config
    monkeypatch.setattr(app.config, "settings", dataclasses.replace(
        app.config.settings, gnani_api_key="some-key", extraction_provider=provider))
    providers = evaluation.run(cfg)["providers"]
    assert providers["evon_available"] is active
    assert phrase in providers["extraction"]


def _follow_up_columns(conn) -> set[str]:
    return {r[1] for r in conn.execute(text("PRAGMA table_info(reports)")) if r[1].startswith("follow_up")}


def test_migrations_add_missing_columns_and_are_idempotent():
    engine = create_engine("sqlite://")
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE reports (id VARCHAR PRIMARY KEY)"))
        db_module._run_migrations(conn)
        assert len(_follow_up_columns(conn)) == 4
        db_module._run_migrations(conn)  # second run must not raise
        assert len(_follow_up_columns(conn)) == 4


def test_migrations_do_not_hide_real_errors():
    engine = create_engine("sqlite://")
    with engine.connect() as conn:  # no reports table at all
        with pytest.raises(Exception, match="no such table"):
            db_module._run_migrations(conn)


def _use_evon(monkeypatch, behaviour):
    """Configure Evon as the extraction provider, with `behaviour` standing in for the Evon call."""
    monkeypatch.setattr(followup, "settings", dataclasses.replace(followup.settings, extraction_provider="evon"))

    class FakeEvon:
        name, mode = "gnani-evon-v3.3", "real"

    monkeypatch.setattr("app.providers.evon.EvonExtractor", FakeEvon)
    monkeypatch.setattr(followup, "_evon_followup", behaviour)


@pytest.mark.parametrize("error", [
    httpx.ConnectError("refused"), httpx.ReadTimeout("slow"), ValueError("expected JSON array"),
    ProviderError("Evon followup HTTP 500"),
])
def test_evon_failure_falls_back_to_templates(monkeypatch, error):
    def fail(*_args):
        raise error

    _use_evon(monkeypatch, fail)
    questions, provider, mode = followup.generate_questions(INCOMPLETE, "en")
    assert len(questions) == 2
    assert (provider, mode) == (followup.STATIC_PROVIDER, followup.STATIC_MODE)


def test_evon_questions_are_labelled_as_evon(monkeypatch):
    _use_evon(monkeypatch, lambda *_args: ["Where are you?"])
    assert followup.generate_questions(INCOMPLETE, "en") == (["Where are you?"], "gnani-evon-v3.3", "real")


def test_rules_mode_never_contacts_evon(monkeypatch):
    def boom(*_args):
        raise AssertionError("Evon must not be called when extraction_provider=rules")

    monkeypatch.setattr(followup, "settings", dataclasses.replace(followup.settings, extraction_provider="rules"))
    monkeypatch.setattr(followup, "_evon_followup", boom)
    _, provider, _ = followup.generate_questions(INCOMPLETE, "en")
    assert provider == followup.STATIC_PROVIDER


def test_follow_up_job_records_the_real_provider(client):
    rid = client.post("/api/reports", json={"transcript": "please help us", "process": True}).json()["id"]
    body = wait_for(client, rid)
    assert body["status"] == "processed"
    job = next(j for j in body["jobs"] if j["stage"] == "follow_up")
    assert (job["provider"], job["provider_mode"]) == (followup.STATIC_PROVIDER, followup.STATIC_MODE)


def test_preprocessed_audio_is_sent_as_wav(client, monkeypatch, tmp_path):
    prepared = tmp_path / "x.prep.wav"
    prepared.write_bytes(FIXTURE_WAV.read_bytes())
    seen = {}

    class FakeSTT:
        name, mode = "fake-stt", "mock"

        def transcribe(self, path, mime_type, _language):
            seen.update(path=path, mime=mime_type)
            return TranscriptionResult(transcript="flood at the river", provider=self.name, mode=self.mode)

    monkeypatch.setattr(pipeline, "settings",
                        dataclasses.replace(pipeline.settings, audio_preprocessing_enabled=True))
    monkeypatch.setattr("app.services.audio_prep.preprocess_audio", lambda _path: prepared)
    monkeypatch.setattr(pipeline, "get_stt", lambda _mode: FakeSTT())
    # Stored as MP3 (ID3 magic bytes) so the original MIME type differs from the prepared WAV's.
    rid = client.post("/api/reports/upload", files={"file": ("a.mp3", b"ID3" + b"\0" * 64)}).json()["id"]
    assert wait_for(client, rid)["status"] == "processed"
    assert seen == {"path": prepared, "mime": "audio/wav"}
