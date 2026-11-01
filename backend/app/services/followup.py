"""Agentic follow-up: detect missing critical fields and generate targeted questions via Evon.

When a caller reports a disaster but omits location, disaster type, or people count, the system
generates 1-2 polite follow-up questions in the caller's own language. These are embedded into
the TTS acknowledgement so the caller hears them automatically.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings
from ..providers.base import ProviderError, ProviderUnavailable

log = logging.getLogger("aapda.followup")

# Fields that are critical for dispatching — missing any triggers follow-up
_CRITICAL_CHECKS = [
    ("location_missing",  "Location not stated"),
    ("disaster_unknown",  "Disaster type unknown"),
    ("people_unknown",    "People count unknown"),
]

STATIC_PROVIDER = "followup-templates-v1"
STATIC_MODE = "template"

# Language name for the Evon prompt
_LANG_NAMES = {
    "mr": "Marathi", "hi": "Hindi", "en": "English",
    "mixed": "Hinglish (Hindi-English mix)", "unknown": "Hindi",
}

# Brief follow-up templates per language as hard fallback (used when Evon is unavailable)
_FALLBACK_QUESTIONS: dict[str, dict[str, str]] = {
    "location_missing": {
        "hi": "आप किस जगह से बोल रहे हैं? गाँव या शहर का नाम बताएँ।",
        "mr": "तुम्ही कोणत्या ठिकाणाहून बोलत आहात? गावाचे किंवा शहराचे नाव सांगा।",
        "en": "Where are you calling from? Please give the village or town name.",
        "mixed": "Aap kahan se bol rahe hain? Gaon ya sheher ka naam batayein.",
    },
    "disaster_unknown": {
        "hi": "क्या हो रहा है वहाँ — बाढ़, भूकंप, आग, या कुछ और?",
        "mr": "तिथे काय होत आहे — पूर, भूकंप, आग की इतर काही?",
        "en": "What is happening there — flood, earthquake, fire, or something else?",
        "mixed": "Wahan kya ho raha hai — baadh, earthquake, aag, ya kuch aur?",
    },
    "people_unknown": {
        "hi": "कितने लोग फंसे या प्रभावित हैं?",
        "mr": "किती लोक अडकले आहेत किंवा प्रभावित आहेत?",
        "en": "How many people are trapped or affected?",
        "mixed": "Kitne log phansey hain ya prabhavit hain?",
    },
}


def missing_fields(ext: dict) -> list[str]:
    """Return list of missing critical field keys for a given extraction dict."""
    missing: list[str] = []
    loc = ext.get("location") or {}
    if loc.get("status") == "missing" or not (loc.get("place_name") or loc.get("landmark")):
        missing.append("location_missing")
    if ext.get("disaster_type", "unknown") == "unknown":
        missing.append("disaster_unknown")
    ppl = ext.get("people_affected") or {}
    if ppl.get("count") is None:
        missing.append("people_unknown")
    return missing


def needs_followup(ext: dict) -> bool:
    """True when at least one critical field is missing."""
    return bool(missing_fields(ext))


def generate_questions(ext: dict, language: str) -> tuple[list[str], str, str]:
    """Generate follow-up questions, returning ``(questions, provider, mode)``.

    Uses Evon only when it is the configured extraction provider, and falls back to static
    templates on any Evon failure: a follow-up question must never fail the report.
    Returns at most 2 questions (most critical first); provider/mode say what really produced them.
    """
    missing = missing_fields(ext)
    if not missing:
        return [], STATIC_PROVIDER, STATIC_MODE

    if settings.extraction_provider == "evon":
        try:
            from ..providers.evon import EvonExtractor
            evon = EvonExtractor()
            questions = _evon_followup(evon, ext, missing, language)
            if questions:
                log.info("followup: evon generated %d question(s) for lang=%s missing=%s",
                         len(questions), language, missing)
                return questions[:2], evon.name, evon.mode
        except (ProviderUnavailable, ProviderError, httpx.HTTPError, ValueError) as exc:
            log.warning("followup: evon failed (%s), using static templates", exc)

    # Fallback: pick static templates for the first 2 missing fields
    lang = language if language in ("hi", "mr", "en", "mixed") else "hi"
    questions = []
    for field in missing[:2]:
        q = _FALLBACK_QUESTIONS[field].get(lang) or _FALLBACK_QUESTIONS[field]["hi"]
        questions.append(q)
    log.info("followup: using static templates for lang=%s missing=%s", lang, missing)
    return questions, STATIC_PROVIDER, STATIC_MODE


def _evon_followup(evon, ext: dict, missing: list[str], language: str) -> list[str]:
    """Call Evon to generate contextual follow-up questions."""
    import json
    lang_name = _LANG_NAMES.get(language, "Hindi")

    known_parts = []
    loc = ext.get("location") or {}
    if loc.get("place_name"):
        known_parts.append(f"location: {loc['place_name']}")
    if ext.get("disaster_type") not in ("unknown", None):
        known_parts.append(f"disaster: {ext['disaster_type']}")
    ppl = ext.get("people_affected") or {}
    if ppl.get("count"):
        known_parts.append(f"people: {ppl['count']}")
    if ext.get("urgency") not in ("unknown", None):
        known_parts.append(f"urgency: {ext['urgency']}")

    missing_desc = {
        "location_missing": "exact location (village/town name)",
        "disaster_unknown": "type of disaster (flood/earthquake/fire/etc.)",
        "people_unknown": "number of people affected or trapped",
    }
    missing_str = ", ".join(missing_desc[m] for m in missing if m in missing_desc)

    prompt = (
        f"An emergency caller reported a disaster in India. "
        f"Known info: {', '.join(known_parts) or 'almost nothing'}. "
        f"Missing critical info: {missing_str}. "
        f"Generate exactly {min(len(missing), 2)} short, urgent follow-up question(s) in {lang_name} "
        f"to ask the caller for the missing info. "
        f"Each question must be 1 sentence, direct, and gentle — the caller is in distress. "
        f"Reply ONLY with a JSON array of question strings, like: [\"question1\", \"question2\"]. "
        f"Do not include any explanation or extra text."
    )

    url = f"{evon.base_url}/chat/completions"
    payload = {
        "model": evon.model,
        "temperature": 0.4,
        "messages": [
            {"role": "system",
             "content": "You generate short emergency follow-up questions for Indian disaster callers."},
            {"role": "user", "content": prompt},
        ],
    }
    with httpx.Client(timeout=evon.timeout_s, transport=evon._transport) as client:
        resp = client.post(url, headers=evon._build_headers(), json=payload)

    if resp.status_code != 200:
        raise ProviderError(f"Evon followup HTTP {resp.status_code}")

    content = evon._extract_content(resp).strip()
    # Strip markdown fences
    if content.startswith("```"):
        lines = [l for l in content.splitlines() if not l.strip().startswith("```")]
        content = "\n".join(lines).strip()

    parsed = json.loads(content)
    if isinstance(parsed, list):
        return [str(q) for q in parsed if q and isinstance(q, str)]
    raise ValueError("expected JSON array")
