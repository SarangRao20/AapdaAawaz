"""Gnani's realtime voice: Prisma and Timbre over WebSocket.

    Prisma  wss://{host}/stt/v3/stream    https://docs.gnani.ai/api/STT/stt-websocket
      Headers carry the settings. Audio goes up as raw 16-bit mono PCM in frames of exactly 1,024 bytes.
      Events come back as speech_start, processing (end of speech detected), then transcript.
    Timbre  wss://{host}/api/v1/tts       https://docs.gnani.ai/api/TTS/tts-websocket
      One JSON request per sentence. Audio comes back as base64 chunks, ending with complete.
"""
from __future__ import annotations

import base64
import json
import logging
from collections.abc import AsyncIterator

import websockets

from ..config import TIMBRE_LANGUAGE_CODES, settings
from ..services.stt_hints import disaster_keyterms
from .base import ProviderError, ProviderUnavailable
from .prisma import PrismaSTT

log = logging.getLogger("aapda.providers.gnani_stream")

SAMPLE_RATE = 16000
FRAME_BYTES = 1024
# Long enough to span the assistant speaking, when no speech reaches Prisma.
IDLE_TIMEOUT_S = 300
# A caller in distress pauses mid-sentence, and the default of 500 ms would cut them off.
END_OF_SPEECH_SILENCE_MS = 900


def _websocket_url(path: str) -> str:
    return settings.gnani_base_url.replace("https://", "wss://").replace("http://", "ws://").rstrip("/") + path


class PrismaStream:
    """One live transcription session. `events()` yields Prisma's messages as dicts."""

    def __init__(self, language: str | None):
        if not settings.gnani_api_key:
            raise ProviderUnavailable("GNANI_API_KEY is not configured")
        self.model = settings.prisma_model
        rest = PrismaSTT(model=self.model)
        codes = rest.request_language(language)
        self._headers = {
            "x-api-key-id": settings.gnani_api_key,
            "language_code": codes.split(",")[0],
            "x-sample-rate": str(SAMPLE_RATE),
            "format": "codemix" if language == "mixed" and rest.is_v3 else settings.prisma_format,
            "x-min-silence-ms": str(END_OF_SPEECH_SILENCE_MS),
            "x-idle-timeout-sec": str(IDLE_TIMEOUT_S),
        }
        if "," in codes:
            # The live API refuses several codes in language_code, unlike REST, and asks for this header.
            self._headers["multi_lang_codes"] = codes
        if rest.is_v3:
            self._headers["model"] = self.model
            # Headers must be ASCII. Gnani's docs recommend a JSON array with \u escapes for Indian scripts.
            self._headers["keyterms"] = json.dumps(list(disaster_keyterms()))
        self._ws = None
        self._pending = b""

    async def __aenter__(self) -> PrismaStream:
        try:
            self._ws = await websockets.connect(_websocket_url("/stt/v3/stream"), additional_headers=self._headers,
                                                open_timeout=15, max_size=None)
        except (OSError, websockets.WebSocketException, TimeoutError) as exc:
            # The exception text can repeat request headers, and they hold the API key.
            raise ProviderError(f"could not connect to Prisma: {type(exc).__name__}", transient=True) from None
        return self

    async def __aexit__(self, *_exc) -> None:
        if self._ws is not None:
            await self._ws.close()

    async def send(self, pcm: bytes) -> None:
        """Prisma expects frames of exactly 1,024 bytes, and browsers don't send that size."""
        self._pending += pcm
        while len(self._pending) >= FRAME_BYTES:
            await self._ws.send(self._pending[:FRAME_BYTES])
            self._pending = self._pending[FRAME_BYTES:]

    async def commit(self) -> None:
        """The caller says they have finished, so close the open utterance now."""
        await self._ws.send(json.dumps({"type": "commit"}))

    async def events(self) -> AsyncIterator[dict]:
        try:
            async for message in self._ws:
                if isinstance(message, str):
                    yield json.loads(message)
        except websockets.ConnectionClosed as exc:
            log.info("Prisma stream closed: %s", exc.code)


async def speak_stream(text: str, language: str) -> AsyncIterator[bytes]:
    """Speak `text` with Timbre, yielding raw 16 kHz 16-bit mono PCM as it arrives."""
    if not settings.gnani_api_key:
        raise ProviderUnavailable("GNANI_API_KEY is not configured")
    request = {
        "text": text,
        "model": settings.live_timbre_model,
        "voice": settings.live_timbre_voice,
        "language": TIMBRE_LANGUAGE_CODES.get(language, "hi-IN"),
        "speed": 0.95,  # slightly slower, for someone frightened on a poor connection
        "audio_config": {"sample_rate": SAMPLE_RATE, "num_channels": 1, "sample_width": 2,
                         "encoding": "linear_pcm", "container": "raw"},
    }
    leftover = b""
    try:
        async with websockets.connect(_websocket_url("/api/v1/tts"), open_timeout=15, max_size=None,
                                      additional_headers={"X-API-Key-ID": settings.gnani_api_key}) as ws:
            await ws.send(json.dumps(request, ensure_ascii=False))
            async for raw in ws:
                message = json.loads(raw)
                kind = message.get("type")
                if kind == "audio" and message["data"].get("audio"):
                    # A chunk can end halfway through a sample, and playing that as-is makes a loud crackle.
                    data = leftover + base64.b64decode(message["data"]["audio"])
                    usable = len(data) - len(data) % 2
                    leftover = data[usable:]
                    if usable:
                        yield data[:usable]
                elif kind == "complete":
                    return
                elif kind == "error":
                    raise ProviderError(f"Timbre: {str(message.get('message'))[:200]}")
    except (OSError, websockets.WebSocketException, TimeoutError) as exc:
        raise ProviderError(f"Timbre stream failed: {type(exc).__name__}", transient=True) from None
