"""Safe storage of uploaded audio: type sniffing, size limit, random server-side names."""
from __future__ import annotations

import hashlib
import io
import uuid
import wave
from dataclasses import dataclass

from ..config import settings

# Formats documented for Gnani Prisma (docs.gnani.ai/api/STT/speech-to-text).
ALLOWED = {
    ".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac",
    ".ogg": "audio/ogg", ".flac": "audio/flac",
}
MAX_SECONDS = 30  # documented Prisma per-request limit


class UploadError(ValueError):
    pass


def sniff(head: bytes) -> str | None:
    """Return the extension implied by the file's magic bytes (content, not the filename)."""
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return ".wav"
    if head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xF6 == 0xF2):
        return ".mp3"
    if head[:4] == b"OggS":
        return ".ogg"
    if head[:4] == b"fLaC":
        return ".flac"
    if head[4:8] == b"ftyp":
        return ".m4a"
    if len(head) > 1 and head[0] == 0xFF and head[1] & 0xF6 == 0xF0:
        return ".aac"
    return None


@dataclass
class StoredAudio:
    stored_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    duration_s: float | None


def store_audio(data: bytes) -> StoredAudio:
    limit = settings.max_upload_mb * 1024 * 1024
    if not data:
        raise UploadError("empty file")
    if len(data) > limit:
        raise UploadError(f"file is {len(data) / 1e6:.1f} MB; the limit is {settings.max_upload_mb} MB")
    ext = sniff(data[:16])
    if ext is None:
        raise UploadError("unsupported or unrecognised audio format; use WAV, MP3, M4A, AAC, OGG or FLAC")
    duration = None
    if ext == ".wav":
        try:
            with wave.open(io.BytesIO(data)) as w:
                duration = w.getnframes() / float(w.getframerate() or 1)
        except (wave.Error, EOFError) as exc:
            raise UploadError(f"invalid WAV file: {exc}") from exc
        if duration > MAX_SECONDS:
            raise UploadError(f"recording is {duration:.0f} s; Gnani Prisma accepts at most {MAX_SECONDS} s per request")
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    (settings.upload_dir / name).write_bytes(data)
    return StoredAudio(name, ALLOWED[ext], len(data), hashlib.sha256(data).hexdigest(), duration)
