"""Gnani Prisma speech-to-text adapter (REST).

Implements only what is documented at https://docs.gnani.ai/api/STT/speech-to-text :

    POST {base}/stt/v3   multipart/form-data
      audio_file      file    (WAV, MP3, OGG, FLAC, AAC, M4A; documented max 30 s per request)
      language_code   string  (bn-IN, en-IN, gu-IN, hi-IN, kn-IN, ml-IN, mr-IN, pa-IN, ta-IN, te-IN)
      format          "verbatim" (default) - we keep verbatim so quantities/names are not rewritten
    Prisma v3.0 adds (https://docs.gnani.ai/api/STT/models/prisma-v3):
      model           "prisma-v3.0" (v2.5 is used when this is left out)
      language_code   also accepts several codes, which are hints and not a lock
      keyterms        words to listen for, such as village names (up to 200)
    Header: X-API-Key-ID
    200 -> {"success": true, "request_id": "...", "timestamp": "...", "transcript": "..."}
    400 invalid params / audio, 403 key/credits, 429 rate limit, 500/503 retry with backoff.

The provider transcript is stored exactly as returned (``raw``); nothing is corrected.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from pathlib import Path

import httpx

from ..config import PRISMA_LANGUAGE_CODES, settings
from ..services.languages import EXTRA
from ..services.stt_hints import disaster_keyterms
from .base import ProviderError, ProviderUnavailable, TranscriptionResult

log = logging.getLogger("aapda.providers.prisma")

SUPPORTED_LANGUAGE_CODES = {"bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "pa-IN", "ta-IN", "te-IN"}
TRANSIENT_STATUS = {429, 500, 502, 503, 504}
V3_LANGUAGE_HINTS = {"mixed": "hi-IN,en-IN", None: "hi-IN,mr-IN,en-IN", "": "hi-IN,mr-IN,en-IN"}


class PrismaSTT:
    mode = "real"

    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 timeout_s: float | None = None, max_retries: int | None = None,
                 transport: httpx.BaseTransport | None = None, model: str | None = None,
                 fmt: str | None = None, keyterms: Sequence[str] | None = None):
        self._api_key = api_key if api_key is not None else settings.gnani_api_key
        self.base_url = (base_url or settings.gnani_base_url).rstrip("/")
        self.timeout_s = timeout_s if timeout_s is not None else settings.prisma_timeout_s
        self.max_retries = max_retries if max_retries is not None else settings.prisma_max_retries
        self._transport = transport
        self.model = model or settings.prisma_model
        self.fmt = fmt or settings.prisma_format
        self.keyterms = disaster_keyterms() if keyterms is None and self.is_v3 else (keyterms or ())
        if not self._api_key:
            raise ProviderUnavailable("GNANI_API_KEY is not configured")

    @property
    def name(self) -> str:
        return f"gnani-{self.model}"

    @property
    def is_v3(self) -> bool:
        return self.model.startswith("prisma-v3")

    def language_code(self, language: str | None) -> str:
        code = PRISMA_LANGUAGE_CODES.get(language or "", settings.prisma_default_language)
        if code not in SUPPORTED_LANGUAGE_CODES:
            raise ProviderError(f"language code {code!r} is not supported by Prisma")
        return code

    def request_language(self, language: str | None) -> str:
        """v3 takes several codes as hints, which suits a caller who switches language or hasn't said."""
        if self.is_v3 and language in V3_LANGUAGE_HINTS:
            return V3_LANGUAGE_HINTS[language]
        return self.language_code(language)

    def request_fields(self, language: str | None) -> dict[str, str]:
        fields = {"language_code": self.request_language(language), "format": self.fmt}
        if self.is_v3:
            fields["model"] = self.model
            # The keyterms are Hindi/Marathi/English place and hazard words: for other languages they pull
            # the transcript towards Hindi (seen with Gujarati, Kannada and Punjabi), so they are left out.
            if self.keyterms and language not in EXTRA:
                fields["keyterms"] = ",".join(self.keyterms)
        return fields

    def transcribe(self, audio_path: Path, mime_type: str, language: str | None) -> TranscriptionResult:
        fields = self.request_fields(language)
        code = fields["language_code"]
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
                            data=fields,
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
            language_code=body.get("detected_language_code") or code,
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
