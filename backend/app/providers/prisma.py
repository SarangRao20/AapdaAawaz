"""Gnani Prisma speech-to-text adapter (REST).

Implements only what is documented at https://docs.gnani.ai/api/STT/speech-to-text :

    POST {base}/stt/v3   multipart/form-data
      audio_file      file    (WAV, MP3, OGG, FLAC, AAC, M4A; documented max 30 s per request)
      language_code   string  (bn-IN, en-IN, gu-IN, hi-IN, kn-IN, ml-IN, mr-IN, pa-IN, ta-IN, te-IN)
      format          "verbatim" (default) - we keep verbatim so quantities/names are not rewritten
    Header: X-API-Key-ID
    200 -> {"success": true, "request_id": "...", "timestamp": "...", "transcript": "..."}
    400 invalid params / audio, 403 key/credits, 429 rate limit, 500/503 retry with backoff.

The provider transcript is stored exactly as returned (``raw``); nothing is corrected.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import httpx

from ..config import PRISMA_LANGUAGE_CODES, settings
from .base import ProviderError, ProviderUnavailable, TranscriptionResult

log = logging.getLogger("aapda.providers.prisma")

SUPPORTED_LANGUAGE_CODES = {"bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "pa-IN", "ta-IN", "te-IN"}
TRANSIENT_STATUS = {429, 500, 502, 503, 504}


class PrismaSTT:
    name = "gnani-prisma-v2.5"
    mode = "real"

    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 timeout_s: float | None = None, max_retries: int | None = None,
                 transport: httpx.BaseTransport | None = None):
        self._api_key = api_key if api_key is not None else settings.gnani_api_key
        self.base_url = (base_url or settings.gnani_base_url).rstrip("/")
        self.timeout_s = timeout_s if timeout_s is not None else settings.prisma_timeout_s
        self.max_retries = max_retries if max_retries is not None else settings.prisma_max_retries
        self._transport = transport
        if not self._api_key:
            raise ProviderUnavailable("GNANI_API_KEY is not configured")

    def language_code(self, language: str | None) -> str:
        code = PRISMA_LANGUAGE_CODES.get(language or "", settings.prisma_default_language)
        if code not in SUPPORTED_LANGUAGE_CODES:
            raise ProviderError(f"language code {code!r} is not supported by Prisma")
        return code

    def transcribe(self, audio_path: Path, mime_type: str, language: str | None) -> TranscriptionResult:
        code = self.language_code(language)
        url = f"{self.base_url}/stt/v3"
        attempt = 0
        with httpx.Client(timeout=self.timeout_s, transport=self._transport) as client:
            while True:
                attempt += 1
                try:
                    with audio_path.open("rb") as fh:
                        resp = client.post(
                            url,
                            headers={"X-API-Key-ID": self._api_key},
                            data={"language_code": code, "format": "verbatim"},
                            files={"audio_file": (audio_path.name, fh, mime_type)},
                        )
                except httpx.TimeoutException as exc:
                    err = ProviderError(f"Prisma request timed out after {self.timeout_s}s", transient=True)
                    err.__cause__ = exc
                except httpx.HTTPError as exc:
                    err = ProviderError(f"Prisma network error: {type(exc).__name__}", transient=True)
                    err.__cause__ = exc
                else:
                    if resp.status_code == 200:
                        return self._parse(resp, code)
                    err = ProviderError(self._error_message(resp), transient=resp.status_code in TRANSIENT_STATUS,
                                        status_code=resp.status_code)
                log.warning("prisma attempt %d failed: %s", attempt, err)
                if not err.transient or attempt > self.max_retries:
                    raise err
                time.sleep(min(1.0 * (1.5 ** (attempt - 1)), 5.0))

    def _parse(self, resp: httpx.Response, code: str) -> TranscriptionResult:
        try:
            body = resp.json()
        except ValueError as exc:
            raise ProviderError("Prisma returned a non-JSON response") from exc
        if not isinstance(body, dict) or body.get("success") is not True:
            raise ProviderError("Prisma response did not report success")
        transcript = body.get("transcript")
        if not isinstance(transcript, str):
            raise ProviderError("Prisma response has no transcript field")
        return TranscriptionResult(
            transcript=transcript,
            provider=self.name,
            mode=self.mode,
            language_code=code,
            request_id=body.get("request_id"),
            raw=body,
        )

    @staticmethod
    def _error_message(resp: httpx.Response) -> str:
        detail = ""
        try:
            body = resp.json()
            if isinstance(body, dict):
                e = body.get("error") or body.get("detail") or body.get("message")
                detail = e.get("message", "") if isinstance(e, dict) else str(e or "")
        except ValueError:
            pass
        hint = {400: "invalid parameters or unsupported audio (max 30 s)",
                403: "check API key, organisation status or credits",
                429: "rate limit exceeded"}.get(resp.status_code, "provider error")
        return f"Prisma HTTP {resp.status_code}: {hint}" + (f" — {detail[:200]}" if detail else "")
