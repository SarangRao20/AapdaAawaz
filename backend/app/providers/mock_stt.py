"""Offline MOCK speech-to-text.

This performs **no speech recognition**. It only recognises the synthetic fixture audio
files shipped in ``backend/data/audio`` by their SHA-256 hash and returns the *authored*
fixture transcript for that file. Any other audio returns ``transcript=None`` so the
report is routed to manual transcription instead of receiving invented text.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from ..config import DATA_DIR
from .base import TranscriptionResult

AUDIO_DIR = DATA_DIR / "audio"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@lru_cache(maxsize=1)
def fixture_audio_index() -> dict[str, dict]:
    """sha256 -> {fixture_id, transcript, file} for every fixture audio file present on disk."""
    raw = json.loads((DATA_DIR / "synthetic_reports.json").read_text(encoding="utf-8"))
    index: dict[str, dict] = {}
    for rep in raw["reports"]:
        name = rep.get("audio_fixture")
        if not name:
            continue
        path = AUDIO_DIR / name
        if path.is_file():
            index[sha256_file(path)] = {"fixture_id": rep["id"], "transcript": rep["transcript"], "file": name}
    return index


class MockFixtureSTT:
    name = "mock-fixture-lookup"
    mode = "mock"

    def transcribe(self, audio_path: Path, mime_type: str, language: str | None) -> TranscriptionResult:
        digest = sha256_file(audio_path)
        hit = fixture_audio_index().get(digest)
        if hit is None:
            return TranscriptionResult(
                transcript=None, provider=self.name, mode=self.mode,
                note="Mock STT cannot transcribe unknown audio. Configure GNANI_API_KEY for Prisma, "
                     "or enter the transcript manually.",
            )
        return TranscriptionResult(
            transcript=hit["transcript"], provider=self.name, mode=self.mode,
            raw={"matched_fixture": hit["fixture_id"], "fixture_file": hit["file"], "sha256": digest},
            note=f"MOCK: audio hash matched synthetic fixture {hit['fixture_id']}; returned its authored "
                 "transcript. No speech recognition was performed.",
        )
