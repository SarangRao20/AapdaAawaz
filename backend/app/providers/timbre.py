"""Gnani Timbre text-to-speech adapter (REST).

Implements only what is documented at https://docs.gnani.ai/api/TTS/tts-inference :

    POST {base}/api/v1/tts/inference   application/json
      {"text", "model": "timbre-v2.5", "voice", "language", "speed",
       "audio_config": {"sample_rate", "num_channels", "sample_width", "encoding", "container"}}
    Header: X-API-Key-ID
    200 -> raw binary audio (audio/wav for container=wav)
    errors -> {"success": false, "error": {"type", "message"}}
"""
from __future__ import annotations

import logging
import time

import httpx

from ..config import TIMBRE_LANGUAGE_CODES, settings
from .base import ProviderError, ProviderUnavailable, SpeechResult

log = logging.getLogger("aapda.providers.timbre")

TRANSIENT_STATUS = {429, 500, 502, 503, 504}


class TimbreTTS:
    name = "gnani-timbre-v2.5"
    mode = "real"

    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 timeout_s: float | None = None, max_retries: int | None = None,
                 transport: httpx.BaseTransport | None = None):
        self._api_key = api_key if api_key is not None else settings.gnani_api_key
        self.base_url = (base_url or settings.gnani_base_url).rstrip("/")
        self.timeout_s = timeout_s if timeout_s is not None else settings.timbre_timeout_s
        self.max_retries = max_retries if max_retries is not None else settings.timbre_max_retries
        self._transport = transport
        if not self._api_key:
            raise ProviderUnavailable("GNANI_API_KEY is not configured")

    def synthesize(self, text: str, language: str) -> SpeechResult:
        lang_code = TIMBRE_LANGUAGE_CODES.get(language)
        voice = settings.timbre_voices.get(language)
        if not lang_code or not voice:
            raise ProviderError(f"no Timbre voice configured for language {language!r}")
        payload = {
            "text": text,
            "model": settings.timbre_model,
            "voice": voice,
            "language": lang_code,
            "speed": 1.0,
            "audio_config": {"sample_rate": 16000, "num_channels": 1, "sample_width": 2,
                             "encoding": "linear_pcm", "container": "wav"},
        }
        attempt = 0
        with httpx.Client(timeout=self.timeout_s, transport=self._transport) as client:
            while True:
                attempt += 1
                try:
                    resp = client.post(f"{self.base_url}/api/v1/tts/inference",
                                       headers={"X-API-Key-ID": self._api_key}, json=payload)
                except httpx.TimeoutException as exc:
                    err = ProviderError(f"Timbre request timed out after {self.timeout_s}s", transient=True)
                    err.__cause__ = exc
                except httpx.HTTPError as exc:
                    err = ProviderError(f"Timbre network error: {type(exc).__name__}", transient=True)
                    err.__cause__ = exc
                else:
                    ctype = resp.headers.get("content-type", "").split(";")[0].strip()
                    if resp.status_code == 200 and ctype.startswith("audio/"):
                        if not resp.content:
                            raise ProviderError("Timbre returned empty audio")
                        return SpeechResult(audio=resp.content, content_type=ctype, provider=self.name,
                                            mode=self.mode, voice=voice, language_code=lang_code)
                    msg = ""
                    try:
                        body = resp.json()
                        detail = body.get("error") or body.get("message") or body.get("detail") or ""
                        if isinstance(detail, dict):
                            detail = ": ".join(str(detail[k]) for k in ("type", "message") if detail.get(k))
                        msg = str(detail)[:300]
                    except (ValueError, AttributeError):
                        pass
                    err = ProviderError(
                        f"Timbre HTTP {resp.status_code} {msg}".strip(),
                        status_code=resp.status_code,
                        transient=resp.status_code in TRANSIENT_STATUS,
                    )
                log.warning("timbre attempt %d failed: %s", attempt, err)
                if not err.transient or attempt > self.max_retries:
                    raise err
                time.sleep(min(1.0 * (1.5 ** (attempt - 1)), 5.0))
