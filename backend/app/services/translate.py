"""Machine translation of a transcript into English, used only to read facts out of EXTRA-language reports.

It never produces anything a caller hears: spoken prompts and safety alerts are fixed text. Gnani has no
translation API, so this tries free public endpoints in turn. Any of them can fail or be rate limited (Google's
returns 429 for a busy address), so every failure falls through to the next, and when all fail the result is
None and the report simply goes to a person with the original transcript.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Callable

import httpx

log = logging.getLogger("aapda.translate")

TIMEOUT_S = 6.0
MYMEMORY_MAX_CHARS = 450  # MyMemory refuses queries over 500 characters
_HEADERS = {"User-Agent": "Mozilla/5.0 (AapdaAwaaz translation)"}


def _google_clients5(text: str, source: str) -> str:
    resp = httpx.get("https://clients5.google.com/translate_a/t", headers=_HEADERS, timeout=TIMEOUT_S,
                     params={"client": "dict-chrome-ex", "sl": source, "tl": "en", "q": text})
    resp.raise_for_status()
    data = resp.json()
    first = data[0] if data else ""
    return (first[0] if isinstance(first, list) else first).strip()


def _google_gtx(text: str, source: str) -> str:
    resp = httpx.get("https://translate.googleapis.com/translate_a/single", headers=_HEADERS, timeout=TIMEOUT_S,
                     params={"client": "gtx", "sl": source, "tl": "en", "dt": "t", "q": text})
    resp.raise_for_status()
    return "".join(part[0] for part in resp.json()[0] if part and part[0]).strip()


def _chunks(text: str, size: int) -> list[str]:
    out, current = [], ""
    for sentence in re.split(r"(?<=[.!?।॥])\s+|\n+", text):
        if current and len(current) + len(sentence) + 1 > size:
            out.append(current)
            current = ""
        current = f"{current} {sentence}".strip()
    return out + ([current] if current else [])


def _mymemory(text: str, source: str) -> str:
    pieces = []
    for chunk in _chunks(text, MYMEMORY_MAX_CHARS):
        resp = httpx.get("https://api.mymemory.translated.net/get", headers=_HEADERS, timeout=TIMEOUT_S,
                         params={"q": chunk, "langpair": f"{source}|en"})
        resp.raise_for_status()
        body = resp.json()
        if body.get("quotaFinished") or body.get("responseStatus") not in (200, "200"):
            raise ValueError("MyMemory refused the request")
        pieces.append(body["responseData"]["translatedText"])
    return " ".join(pieces).strip()


PROVIDERS: list[tuple[str, Callable[[str, str], str]]] = [
    ("google-clients5", _google_clients5), ("google-gtx", _google_gtx), ("mymemory", _mymemory),
]


_cache: dict[tuple[str, str], str] = {}  # successes only: a failure must be tried again next time


def to_english(text: str, source: str) -> str | None:
    text = (text or "").strip()
    if not text:
        return None
    if (source, text) in _cache:
        return _cache[(source, text)]
    for name, translate in PROVIDERS:
        try:
            translated = translate(text, source)
        except (httpx.HTTPError, ValueError, IndexError, KeyError, TypeError) as exc:
            log.warning("translation via %s from %s failed: %s", name, source, type(exc).__name__)
            continue
        if translated:
            if len(_cache) >= 256:
                _cache.pop(next(iter(_cache)))
            _cache[(source, text)] = translated
            return translated
    return None
