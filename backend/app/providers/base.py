"""Provider interfaces shared by the speech, extraction and TTS adapters.

Every result carries ``provider`` and ``mode`` so the UI and evaluation can always tell
real model output (``real``) apart from mock / fixture / human output.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


class ProviderError(Exception):
    """A provider call failed. ``transient`` failures may be retried."""

    def __init__(self, message: str, *, transient: bool = False, status_code: int | None = None):
        super().__init__(message)
        self.transient = transient
        self.status_code = status_code


class ProviderUnavailable(ProviderError):
    """The provider cannot be used (no credentials, no documented API, disabled)."""


@dataclass
class TranscriptionResult:
    transcript: str | None
    provider: str
    mode: str  # real | mock
    language_code: str | None = None
    request_id: str | None = None
    raw: dict[str, Any] | None = None
    note: str | None = None


@dataclass
class SpeechResult:
    audio: bytes
    content_type: str
    provider: str
    mode: str
    voice: str
    language_code: str
    detail: dict[str, Any] = field(default_factory=dict)


class SpeechToText(Protocol):
    name: str
    mode: str

    def transcribe(self, audio_path: Path, mime_type: str, language: str | None) -> TranscriptionResult: ...


class TextToSpeech(Protocol):
    name: str
    mode: str

    def synthesize(self, text: str, language: str) -> SpeechResult: ...
