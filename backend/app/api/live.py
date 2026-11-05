"""Awaaz Live: a realtime voice call between a browser, Prisma and Timbre.

Browser to server:  binary 16 kHz 16-bit mono PCM from the microphone
                    {"type": "start", "language": "hi"}  first message
                    {"type": "playback_done"}  the browser finished playing the assistant's audio
                    {"type": "commit"}  the caller pressed "done speaking"
                    {"type": "end"}  the caller hung up
Server to browser:  binary 16 kHz 16-bit mono PCM of the assistant's voice
                    {"type": "state" | "caller" | "assistant" | "facts" | "metrics" | "audio_start" | "audio_end" | "done" | "error"}

The session is half duplex: the microphone is ignored while the assistant speaks, so the assistant can
never transcribe its own voice. Gnani's TTS stream has no cancel message, so talking over it isn't supported.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..auth import WS_TICKET_SECONDS, create_ws_ticket, is_authenticated, valid_ws_ticket
from ..config import settings
from ..providers.base import ProviderError, ProviderUnavailable
from ..providers.gnani_stream import SAMPLE_RATE, PrismaStream, speak_stream
from ..services.live_call import CallBrain, Turn, calls, save_call_audio
from ..services.live_guard import LiveGuard

log = logging.getLogger("aapda.live")
router = APIRouter(prefix="/api/live", tags=["live call"])

LANGUAGES = {"hi", "mr", "en", "mixed"}
SETTLE_S = 0.3  # on top of the silence Prisma already waits for, in case the caller is still going
SILENCE_S = 12.0  # ask again after this much quiet
MAX_CALL_S = 300.0  # a call is capped so a forgotten tab can't keep spending credits
MAX_CALLER_AUDIO_BYTES = 9 * 1024 * 1024  # inside the 10 MB upload limit
PLAYBACK_GRACE_S = 3.0  # how long past the audio's length to wait for playback_done
FIRST_MESSAGE_S = 10.0  # an idle public socket must not hold a capacity slot
TAG = re.compile(r"<[a-z ]+>\s*")

# Replaced in tests.
stream_factory = PrismaStream
speak = speak_stream
guard = LiveGuard(settings.live_max_concurrent, settings.live_max_per_ip, settings.live_max_per_hour)

# A public caller gets a readable reason before the socket closes, not a silent 403.
REFUSALS = {
    "busy": "Awaaz Live is busy right now. Please try again in a minute.",
    "already_calling": "A call is already open from this device. End it before starting another.",
    "hourly_limit": "This device has started too many calls. Please try again later.",
}
# The caller APK's WebView is http://localhost. Dashboard origins come from CORS_ORIGINS.
APP_ORIGINS = {"http://localhost", "https://localhost", "capacitor://localhost"}


def prisma_latency_ms(event: dict) -> float | None:
    """Prisma reports `latency` in milliseconds on each transcript (457 for 8.7 s of speech in a live test)."""
    value = event.get("latency", (event.get("data") or {}).get("latency"))
    return float(value) if isinstance(value, (int, float)) else None


def visible_text(text: str) -> str:
    """Audio tags steer Timbre's delivery, and aren't for reading."""
    return TAG.sub("", text).strip()


class LiveSession:
    def __init__(self, ws: WebSocket, language: str):
        self.ws = ws
        self.language = language
        self.brain = CallBrain(language)
        self.call_id = calls.start(language)
        self.stream = None
        self.state = "connecting"
        self.heard: list[str] = []
        self.caller_audio = bytearray()
        self.caller_talking = False
        self.last_activity = time.monotonic()
        self.prisma_ms: float | None = None
        self.transcribed_at: float | None = None
        self.settle_task: asyncio.Task | None = None
        self.turn_task: asyncio.Task | None = None
        self.playback_done = asyncio.Event()
        self.finished = asyncio.Event()
        self.send_lock = asyncio.Lock()

    async def send_json(self, payload: dict) -> None:
        async with self.send_lock:
            await self.ws.send_json(payload)

    async def set_state(self, state: str) -> None:
        self.state = state
        calls.update(self.call_id, state=state)
        await self.send_json({"type": "state", "state": state})

    async def run(self) -> None:
        try:
            async with stream_factory(self.language) as stream:
                self.stream = stream
                tasks = [asyncio.create_task(t) for t in (self._client_loop(), self._prisma_loop(), self._watch_silence())]
                self._begin_turn(self._greet())
                done, pending = await asyncio.wait(
                    [*tasks, asyncio.create_task(self.finished.wait())], return_when=asyncio.FIRST_COMPLETED)
                for task in (*pending, self.settle_task, self.turn_task):
                    if task:
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError, Exception):
                            await task
                for task in done:
                    if not task.cancelled() and (exc := task.exception()) and not isinstance(exc, WebSocketDisconnect):
                        log.warning("live call task failed: %s", type(exc).__name__)
        except (ProviderError, ProviderUnavailable) as exc:
            log.warning("live call could not reach Gnani: %s", exc)
            with contextlib.suppress(Exception):
                await self.send_json({"type": "error", "message": f"Could not reach Gnani: {exc}"})
        finally:
            await self._close()

    async def _close(self) -> None:
        calls.end(self.call_id)
        report_id = self.brain.report_id
        if report_id and self.caller_audio:
            await asyncio.to_thread(save_call_audio, report_id, bytes(self.caller_audio), SAMPLE_RATE)
        with contextlib.suppress(Exception):
            await self.send_json({"type": "done", "report_id": report_id})
        with contextlib.suppress(Exception):
            await self.ws.close()

    def _begin_turn(self, coroutine) -> None:
        self.turn_task = asyncio.create_task(coroutine)

    # ---- speaking --------------------------------------------------------------------------
    async def _greet(self) -> None:
        await self._say(self.brain.greeting())
        await self._listen()

    async def _listen(self) -> None:
        self.last_activity = time.monotonic()
        await self.set_state("listening")

    async def _say(self, text: str) -> None:
        """Send the words first, so a Timbre failure still leaves the caller with something to read."""
        words = visible_text(text)
        calls.add_turn(self.call_id, "assistant", words)
        await self.send_json({"type": "assistant", "text": words})
        await self.set_state("speaking")
        self.playback_done.clear()
        audio_bytes = 0
        started = False
        try:
            async for chunk in speak(text, self.language):
                if not started:
                    started = True
                    await self.send_json({"type": "audio_start", "sample_rate": SAMPLE_RATE})
                    self._report_timing()
                async with self.send_lock:
                    await self.ws.send_bytes(chunk)
                audio_bytes += len(chunk)
        except (ProviderError, ProviderUnavailable) as exc:
            log.warning("Timbre failed during a call: %s", exc)
            await self.send_json({"type": "notice", "message": "The voice reply failed. Please read the question."})
        if started:
            await self.send_json({"type": "audio_end"})
            seconds = audio_bytes / (SAMPLE_RATE * 2)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.playback_done.wait(), seconds + PLAYBACK_GRACE_S)

    def _report_timing(self) -> None:
        """Prisma's own transcription time, then our time from its text to Timbre's first sound.

        This leaves out the silence Prisma waits for to know the caller has stopped (END_OF_SPEECH_SILENCE_MS),
        so a caller waits that much longer than `total_ms`. Prisma doesn't report when speech ended.
        """
        if self.transcribed_at is None:
            return
        reply_ms = round((time.monotonic() - self.transcribed_at) * 1000)
        prisma_ms = self.prisma_ms or 0
        self.transcribed_at = self.prisma_ms = None
        total_ms = round(prisma_ms + reply_ms)
        calls.update(self.call_id, last_response_ms=total_ms)
        asyncio.ensure_future(self.send_json({"type": "metrics", "prisma_ms": round(prisma_ms), "reply_ms": reply_ms,
                                              "total_ms": total_ms}))

    # ---- turns -----------------------------------------------------------------------------
    async def _take_turn(self) -> None:
        await asyncio.sleep(SETTLE_S)
        text = " ".join(self.heard).strip()
        self.heard.clear()
        if not text:
            return
        await self.set_state("thinking")
        calls.add_turn(self.call_id, "caller", text)
        await self.send_json({"type": "caller", "text": text})
        turn: Turn = await asyncio.to_thread(self.brain.hear, text)
        await self._publish_facts()
        await self._finish_turn(turn)

    async def _finish_turn(self, turn: Turn) -> None:
        await self._say(turn.reply)
        if turn.done:
            self.finished.set()
        else:
            await self._listen()

    async def _publish_facts(self) -> None:
        calls.update(self.call_id, facts=self.brain.facts, asking_for=self.brain.pending)
        await self.send_json({"type": "facts", "facts": self.brain.facts, "asking_for": self.brain.pending})

    async def _watch_silence(self) -> None:
        started = time.monotonic()
        while True:
            await asyncio.sleep(0.25)
            now = time.monotonic()
            if now - started > MAX_CALL_S:
                self.finished.set()
                return
            idle = (self.state == "listening" and not self.caller_talking and not self.heard
                    and now - self.last_activity > SILENCE_S)
            if idle and (self.turn_task is None or self.turn_task.done()):
                self._begin_turn(self._finish_turn(self.brain.nudge()))

    # ---- events ----------------------------------------------------------------------------
    async def _prisma_loop(self) -> None:
        async for event in self.stream.events():
            kind = event.get("type")
            if kind == "error":  # checked first: an error matters whatever the call is doing
                log.warning("Prisma reported an error during a call: %s", str(event.get("message"))[:300])
                continue
            if self.state != "listening":
                continue  # the caller's audio isn't being sent, so this is left over from before
            if kind == "speech_start":
                self.caller_talking = True
                self.last_activity = time.monotonic()
                if self.settle_task:
                    self.settle_task.cancel()
            elif kind == "transcript":
                self.caller_talking = False
                self.last_activity = time.monotonic()
                text = (event.get("text") or (event.get("data") or {}).get("text") or "").strip()
                if text:
                    self.transcribed_at = time.monotonic()
                    self.prisma_ms = prisma_latency_ms(event)
                    self.heard.append(text)
                if self.heard:
                    self.settle_task = asyncio.create_task(self._take_turn())
                    self._begin_turn(self._await_settle(self.settle_task))
        # Prisma closed the stream, so nothing more can be heard.
        await self.send_json({"type": "notice", "message": "The speech service ended the session."})
        self.finished.set()

    @staticmethod
    async def _await_settle(task: asyncio.Task) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _client_loop(self) -> None:
        while True:
            message = await self.ws.receive()
            if message["type"] == "websocket.disconnect":
                self.finished.set()
                return
            if message.get("bytes") is not None:
                if self.state == "listening":
                    pcm = message["bytes"]
                    if len(self.caller_audio) + len(pcm) <= MAX_CALLER_AUDIO_BYTES:
                        self.caller_audio += pcm
                    await self.stream.send(pcm)
                continue
            try:
                kind = json.loads(message.get("text") or "{}").get("type")
            except ValueError:
                continue
            if kind == "playback_done":
                self.playback_done.set()
            elif kind == "commit" and self.state == "listening":
                await self.stream.commit()
            elif kind == "end":
                self.finished.set()
                return


def client_address(ws: WebSocket) -> str:
    """Who is calling. Behind a trusted proxy that is the first X-Forwarded-For entry, not the proxy itself."""
    if settings.trust_proxy:
        forwarded = ws.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return ws.client.host if ws.client else "unknown"


@router.post("/ticket", summary="A one-minute pass for opening the live-call WebSocket (needs a login)")
def live_ticket():
    return {"ticket": create_ws_ticket(), "expires_in": WS_TICKET_SECONDS}


async def _refuse(ws: WebSocket, message: str, code: int = 4429) -> None:
    """Accept first so the caller app can show the reason instead of a generic handshake failure."""
    await ws.accept()
    with contextlib.suppress(Exception):
        await ws.send_json({"type": "error", "message": message})
        await ws.close(code=code)


async def _admit(ws: WebSocket) -> tuple[bool, str | None]:
    """Who may start a call. Returns (allowed, address to release), and closes refused sockets."""
    # HTTP middleware doesn't run on WebSockets, and a call spends credits and stores a voice, so check here.
    # A ticket comes from POST /api/live/ticket, which needs a login, so it counts the same as the cookie.
    if is_authenticated(ws) or valid_ws_ticket(ws.query_params.get("ticket")):
        return True, None
    if not settings.live_public:
        await ws.close(code=4401)
        return False, None
    # A browser on another site could otherwise spend our credits from its visitors' addresses.
    origin = ws.headers.get("origin")
    if origin and origin not in APP_ORIGINS and origin not in settings.cors_origins:
        log.info("public live call refused for origin %s", origin)
        await _refuse(ws, "This app version is not allowed to start a call. Please update it.", code=4403)
        return False, None
    address = client_address(ws)
    refusal = guard.allow(address)
    if refusal is None:
        return True, address
    log.info("public live call refused for %s: %s", address, refusal)
    await _refuse(ws, REFUSALS.get(refusal, "Awaaz Live is unavailable."))
    return False, None


@router.websocket("/call")
async def live_call(ws: WebSocket):
    allowed, address = await _admit(ws)
    if not allowed:
        return
    try:
        await ws.accept()
        try:
            first = json.loads(await asyncio.wait_for(ws.receive_text(), FIRST_MESSAGE_S))
        except (ValueError, WebSocketDisconnect, TimeoutError):
            await ws.close(code=1008)
            return
        language = first.get("language")
        if first.get("type") != "start" or language not in LANGUAGES:
            await ws.send_json({"type": "error", "message": "Choose hi, mr, en or mixed."})
            await ws.close(code=1008)
            return
        await LiveSession(ws, language).run()
    finally:
        if address:
            guard.release(address)


@router.get("/calls")
def live_calls():
    """Calls in progress and just finished, for the dispatcher's screen."""
    return {"items": calls.snapshot(), "voice": {"prisma": settings.prisma_model, "timbre": settings.live_timbre_model}}
