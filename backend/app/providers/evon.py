"""Gnani Evon v3.3 structured-extraction adapter (LLM, OpenAI-compatible chat endpoint).

Evon is Gnani's own 30B-parameter MoE reasoning model with 11 Indian languages and 128K context.
It replaces the keyword-rule extractor when ``EXTRACTION_PROVIDER=evon`` is set, giving the
pipeline all three Gnani models: Prisma (STT) → Evon (extraction) → Timbre (TTS).

API contract assumed (OpenAI-compatible):
    POST {EVON_BASE_URL}/chat/completions
    Authorization: Bearer {GNANI_API_KEY}
    Content-Type: application/json
    body: { model, messages, temperature, response_format: {type: "json_object"} }
    200 → { choices: [{ message: { content: "<json string>" } }] }
    400 bad request, 403 key/credits, 429 rate limit, 500/503 retry with backoff.

If the endpoint or response format differs, adjust _call() and _parse() — nothing else changes.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from ..config import settings
from ..schemas import (
    Evidence,
    ExtractedLocation,
    ExtractionResult,
    PeopleAffected,
    VulnerableMention,
    VulnerablePeople,
)
from .base import ProviderError, ProviderUnavailable

log = logging.getLogger("aapda.providers.evon")

TRANSIENT_STATUS = {429, 500, 502, 503, 504}

# Valid enum values — used to filter Evon output so a bad value never crashes the validator.
_DISASTER_TYPES = {"flood", "earthquake", "landslide", "fire", "other", "unknown"}
_URGENCY_LEVELS = {"critical", "high", "medium", "low", "unknown"}
_LANGUAGES = {"mr", "hi", "en", "mixed", "unknown"}
_TRANSCRIPT_QUALITY = {"ok", "low", "unknown"}
_NEED_TYPES = {"rescue_evacuation", "medical", "food", "drinking_water", "shelter", "fire_services"}
_DANGER_TYPES = {
    "trapped", "surrounded_by_water", "on_roof", "water_rising", "flooding_inside_home",
    "swept_away", "drowning", "structure_collapse", "under_debris", "injured", "unconscious",
    "active_fire", "missing_person", "road_blocked",
}
_VULNERABLE_GROUPS = {"elderly", "children", "infants", "pregnant_people", "people_with_disabilities"}

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------
_SYSTEM_MESSAGE = (
    "You are a structured data extraction assistant for Indian emergency call triage. "
    "You receive transcripts of voice reports from disaster-affected callers. "
    "Callers may speak in Marathi, Hindi, English, or a mix (Hinglish, Tanglish). "
    "Extract the information and respond ONLY with a valid JSON object — "
    "no explanation, no markdown fences, no extra text."
)

_FEW_SHOT_1_TRANSCRIPT = (
    "Haan, mera naam Ramesh hai, main Khadakwasla se bol raha hoon. "
    "Yahan bahut zyada paani aa gaya hai, kaafi log phaansey hue hain, "
    "kareeb pachaas log hain. Ek budha aadmi ko dil ka dora pad gaya hai. "
    "Bahut urgent hai, please jaldi bhejo."
)
_FEW_SHOT_1_OUTPUT = {
    "disaster_type": "flood",
    "location_place": "Khadakwasla",
    "location_landmark": None,
    "people_count": 50,
    "people_approximate": True,
    "vulnerable_groups": ["elderly"],
    "immediate_needs": ["rescue_evacuation", "medical"],
    "reported_dangers": ["trapped"],
    "medical_emergency": True,
    "urgency": "critical",
    "language": "hi",
    "transcript_quality": "ok",
    "summary": "Flood at Khadakwasla with approximately 50 people trapped; elderly person with cardiac emergency; urgent rescue and medical help needed.",
    "uncertainties": ["Exact number of people trapped is approximate (50 stated)"],
    "rationale": {
        "disaster_type": "bahut zyada paani aa gaya hai",
        "location_place": "Khadakwasla se bol raha hoon",
        "people_count": "kareeb pachaas log hain",
        "urgency": "Bahut urgent hai, please jaldi bhejo",
        "medical_emergency": "Ek budha aadmi ko dil ka dora pad gaya hai",
        "vulnerable_groups": "budha aadmi",
        "reported_dangers": "kaafi log phaansey hue hain",
        "immediate_needs": "please jaldi bhejo",
    },
}

_FEW_SHOT_2_TRANSCRIPT = (
    "Hello, me Sangli madhun bolte ahe. Aamchya gaavaat dond aala ahe, "
    "don-teen ghari pani shiralay. Lahaan mulay ahet ghari, "
    "pan aata koni nahi ahe aamucha madatila. Please koni patha."
)
_FEW_SHOT_2_OUTPUT = {
    "disaster_type": "flood",
    "location_place": "Sangli",
    "location_landmark": None,
    "people_count": None,
    "people_approximate": False,
    "vulnerable_groups": ["children"],
    "immediate_needs": ["rescue_evacuation"],
    "reported_dangers": ["flooding_inside_home"],
    "medical_emergency": None,
    "urgency": "high",
    "language": "mr",
    "transcript_quality": "ok",
    "summary": "Flood in Sangli with water entering two or three homes; children present, no one available to help; rescue needed.",
    "uncertainties": ["Number of people affected not stated", "Exact number of houses flooded unclear"],
    "rationale": {
        "disaster_type": "dond aala ahe",
        "location_place": "Sangli madhun bolte ahe",
        "reported_dangers": "don-teen ghari pani shiralay",
        "vulnerable_groups": "Lahaan mulay ahet ghari",
        "immediate_needs": "Please koni patha",
        "urgency": "koni nahi ahe aamucha madatila",
    },
}


def _build_user_message(transcript: str, language_hint: str | None) -> str:
    hint_str = language_hint or "unknown"
    few_shot_block = (
        "--- Example 1 ---\n"
        f'Transcript: "{_FEW_SHOT_1_TRANSCRIPT}"\n'
        f"Output: {json.dumps(_FEW_SHOT_1_OUTPUT, ensure_ascii=False)}\n\n"
        "--- Example 2 ---\n"
        f'Transcript: "{_FEW_SHOT_2_TRANSCRIPT}"\n'
        f"Output: {json.dumps(_FEW_SHOT_2_OUTPUT, ensure_ascii=False)}\n"
    )
    schema_block = """Return a JSON object with exactly these keys:
{
  "disaster_type": one of flood|earthquake|landslide|fire|other|unknown,
  "location_place": village/town name stated by caller, or null if not stated,
  "location_landmark": specific named landmark or null,
  "people_count": integer count of people affected, or null,
  "people_approximate": true if count is approximate or a range, false otherwise,
  "vulnerable_groups": array, allowed values: elderly children infants pregnant_people people_with_disabilities,
  "immediate_needs": array, allowed values: rescue_evacuation medical food drinking_water shelter fire_services,
  "reported_dangers": array, allowed values: trapped surrounded_by_water on_roof water_rising flooding_inside_home swept_away drowning structure_collapse under_debris injured unconscious active_fire missing_person road_blocked,
  "medical_emergency": true if caller explicitly describes a medical emergency, null if not mentioned,
  "urgency": one of critical|high|medium|low|unknown — based on caller's tone and words,
  "language": one of mr|hi|en|mixed|unknown,
  "transcript_quality": ok if clear and complete, low if inaudible/fragmented/very short, unknown,
  "summary": one concise English sentence describing the situation,
  "uncertainties": list of strings describing what the caller did not state clearly (empty list if none),
  "rationale": object mapping each extracted field to the exact phrase or clause from the transcript that supports it — copy the text verbatim from the transcript, do not paraphrase; omit a key if the field was not stated in the transcript
}

Rules:
- Use null for unknown values, never guess or fabricate
- Only include values from the allowed lists for array fields; ignore any other values
- people_count must be an integer (not a string); use the largest count if multiple mentioned
- medical_emergency is true only if the caller explicitly mentions injury, cardiac event, unconscious person, or similar — not just "help needed"
- transcript_quality is "low" if there are inaudible markers like "[inaudible]", "...", or fewer than 5 words
- rationale values must be exact substrings of the transcript; they are shown to dispatchers as evidence"""

    return (
        f"Extract disaster information from this emergency call transcript.\n\n"
        f"Language hint: {hint_str}\n"
        f'Transcript: "{transcript}"\n\n'
        f"{schema_block}\n\n"
        f"Study these examples before answering:\n{few_shot_block}\n"
        f"Now extract from the transcript above and return only the JSON object."
    )


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------
UNAVAILABLE_REASON = "Evon extraction requires GNANI_API_KEY — set it and EXTRACTION_PROVIDER=evon"


class EvonExtractor:
    name = "gnani-evon-v3.3"
    mode = "real"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_s: float | None = None,
        max_retries: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.gnani_api_key
        self.base_url = (base_url or settings.evon_base_url).rstrip("/")
        self.model = model or settings.evon_model
        self.timeout_s = timeout_s if timeout_s is not None else settings.evon_timeout_s
        self.max_retries = max_retries if max_retries is not None else settings.evon_max_retries
        self._transport = transport
        # For self-hosted vLLM (Camber, local), we don't need API key
        # Only require it if base_url looks like Gnani API or if explicitly tested
        if not self._api_key:
            raise ProviderUnavailable(UNAVAILABLE_REASON)
    
    def _build_headers(self) -> dict[str, str]:
        """Build HTTP headers, omitting Authorization for self-hosted endpoints."""
        headers = {"Content-Type": "application/json"}
        # Only send API key if we have one (self-hosted vLLM doesn't need it)
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def generate_ack(
        self,
        summary: str,
        location: str | None,
        people_count: int | None,
        urgency: str,
        language: str,
    ) -> str:
        """Generate a personalised 2-sentence acknowledgement in the caller's language.

        Does not retry — callers must fall back to the static template on ProviderError.
        """
        lang_name = {"mr": "Marathi", "hi": "Hindi", "en": "English", "mixed": "Hinglish"}.get(
            language, "Hindi"
        )
        parts = [f"report: {summary}"]
        if location:
            parts.append(f"location: {location}")
        if people_count is not None:
            parts.append(f"people affected: approximately {people_count}")
        if urgency and urgency != "unknown":
            parts.append(f"urgency: {urgency}")
        context = "; ".join(parts)

        user_msg = (
            f"Write a 2-sentence acknowledgement for an emergency caller in {lang_name}. "
            f"Context: {context}. "
            "Confirm the report was received, then mention the location and/or people count if known. "
            "Do NOT promise rescue, arrival times, or government action. "
            "Reply with only the acknowledgement text."
        )
        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": 0.3,
            "messages": [
                {
                    "role": "system",
                    "content": "You write short, warm emergency call acknowledgements for Indian disaster callers.",
                },
                {"role": "user", "content": user_msg},
            ],
        }
        try:
            with httpx.Client(timeout=self.timeout_s, transport=self._transport) as client:
                resp = client.post(
                    url,
                    headers=self._build_headers(),
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"Evon ack timed out after {self.timeout_s}s", transient=True
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Evon ack network error: {type(exc).__name__}", transient=True
            ) from exc
        if resp.status_code != 200:
            raise ProviderError(
                self._error_message(resp),
                transient=resp.status_code in TRANSIENT_STATUS,
                status_code=resp.status_code,
            )
        return self._extract_content(resp).strip()

    def extract(self, transcript: str, language_hint: str | None = None) -> ExtractionResult:
        """Call Evon, parse the JSON response, return a validated ExtractionResult."""
        raw = self._call(transcript, language_hint)
        try:
            data = _parse_json(raw)
        except ValueError as exc:
            raise ProviderError(f"Evon returned non-JSON content: {exc}") from exc
        return _to_extraction_result(data, transcript, language_hint)

    # ------------------------------------------------------------------
    def _call(self, transcript: str, language_hint: str | None) -> str:
        """POST to the chat completions endpoint with retry on transient errors."""
        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _SYSTEM_MESSAGE},
                {"role": "user", "content": _build_user_message(transcript, language_hint)},
            ],
        }
        attempt = 0
        with httpx.Client(timeout=self.timeout_s, transport=self._transport) as client:
            while True:
                attempt += 1
                try:
                    resp = client.post(
                        url,
                        headers=self._build_headers(),
                        json=payload,
                    )
                except httpx.TimeoutException as exc:
                    err: ProviderError = ProviderError(
                        f"Evon request timed out after {self.timeout_s}s", transient=True
                    )
                    err.__cause__ = exc
                except httpx.HTTPError as exc:
                    err = ProviderError(f"Evon network error: {type(exc).__name__}", transient=True)
                    err.__cause__ = exc
                else:
                    if resp.status_code == 200:
                        return self._extract_content(resp)
                    err = ProviderError(
                        self._error_message(resp),
                        transient=resp.status_code in TRANSIENT_STATUS,
                        status_code=resp.status_code,
                    )
                log.warning("evon attempt %d/%d failed: %s", attempt, self.max_retries + 1, err)
                if not err.transient or attempt > self.max_retries:
                    raise err
                time.sleep(min(1.0 * (1.5 ** (attempt - 1)), 5.0))

    @staticmethod
    def _extract_content(resp: httpx.Response) -> str:
        try:
            body = resp.json()
        except ValueError as exc:
            raise ProviderError("Evon returned a non-JSON response envelope") from exc
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                f"Evon response missing choices[0].message.content: {str(exc)[:100]}"
            ) from exc
        if not isinstance(content, str):
            raise ProviderError("Evon response content is not a string")
        return content

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
        hint = {
            400: "invalid request or unsupported parameters",
            403: "check API key, organisation status or credits",
            429: "rate limit exceeded",
        }.get(resp.status_code, "provider error")
        return f"Evon HTTP {resp.status_code}: {hint}" + (f" — {detail[:200]}" if detail else "")


# ---------------------------------------------------------------------------
# JSON parsing + mapping
# ---------------------------------------------------------------------------

def _parse_json(raw: str) -> dict:
    """Parse the JSON string returned by Evon, stripping accidental markdown fences."""
    text = raw.strip()
    # Strip ```json ... ``` wrappers if the model ignored the instruction
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(
            line for line in lines if not line.strip().startswith("```")
        ).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON decode error: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected a JSON object, got {type(parsed).__name__}")
    return parsed


def _safe_str(data: dict, key: str, allowed: set[str], default: str) -> str:
    v = data.get(key)
    if isinstance(v, str) and v in allowed:
        return v
    if v is not None:
        log.debug("evon returned unexpected value for %r: %r — using %r", key, v, default)
    return default


def _safe_list(data: dict, key: str, allowed: set[str]) -> list[str]:
    v = data.get(key)
    if not isinstance(v, list):
        return []
    return [x for x in v if isinstance(x, str) and x in allowed]


def _safe_int(data: dict, key: str) -> int | None:
    v = data.get(key)
    if isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 100_000:
        return v
    if isinstance(v, float) and v == int(v) and 1 <= int(v) <= 100_000:
        return int(v)
    return None


def _to_extraction_result(
    data: dict, transcript: str, language_hint: str | None
) -> ExtractionResult:
    """Map Evon's flat JSON to the full ExtractionResult schema."""
    disaster_type = _safe_str(data, "disaster_type", _DISASTER_TYPES, "unknown")
    urgency = _safe_str(data, "urgency", _URGENCY_LEVELS, "unknown")
    language = _safe_str(data, "language", _LANGUAGES, language_hint or "unknown")
    quality = _safe_str(data, "transcript_quality", _TRANSCRIPT_QUALITY, "unknown")
    immediate_needs = _safe_list(data, "immediate_needs", _NEED_TYPES)
    reported_dangers = _safe_list(data, "reported_dangers", _DANGER_TYPES)
    vulnerable_groups = _safe_list(data, "vulnerable_groups", _VULNERABLE_GROUPS)
    people_count = _safe_int(data, "people_count")
    people_approx = bool(data.get("people_approximate")) if people_count is not None else False
    med_raw = data.get("medical_emergency")
    medical_emergency = True if med_raw is True else None
    urgency_evidence_text: str | None = None  # filled after rationale is built

    # Evidence list — use exact transcript quotes from the rationale field where available
    raw_rationale = data.get("rationale")
    rationale: dict[str, str] = {}
    if isinstance(raw_rationale, dict):
        for k, v in raw_rationale.items():
            if isinstance(k, str) and isinstance(v, str) and v.strip():
                # Only keep if the phrase actually appears in the transcript (case-insensitive)
                if v.strip().lower() in transcript.lower():
                    rationale[k] = v.strip()
                else:
                    rationale[k] = v.strip()  # keep anyway — display as label even if not exact match

    def _ev_text(key: str, fallback: str) -> str:
        return rationale.get(key) or fallback

    ev: list[Evidence] = []
    if disaster_type != "unknown":
        ev.append(Evidence(field="disaster_type", text=_ev_text("disaster_type", disaster_type)))
    if people_count is not None:
        ev.append(Evidence(field="people_affected.count", text=_ev_text("people_count", str(people_count))))
    for d in reported_dangers:
        ev.append(Evidence(field=f"danger.{d}", text=_ev_text("reported_dangers", d)))
    for n in immediate_needs:
        ev.append(Evidence(field=f"need.{n}", text=_ev_text("immediate_needs", n)))
    if medical_emergency:
        ev.append(Evidence(field="medical_emergency", text=_ev_text("medical_emergency", "medical emergency described")))
    if urgency != "unknown":
        urgency_evidence_text = _ev_text("urgency", urgency)
        ev.append(Evidence(field="urgency", text=urgency_evidence_text))

    # Location
    loc_place = data.get("location_place")
    loc_landmark = data.get("location_landmark")
    if isinstance(loc_place, str) and loc_place.strip():
        location = ExtractedLocation(
            place_name=loc_place.strip(),
            landmark=loc_landmark.strip() if isinstance(loc_landmark, str) and loc_landmark.strip() else None,
            source="caller_stated",
            status="unmapped",  # Evon cannot verify against the reference gazetteer
            confidence=0.4,
            confidence_basis=f"evon extracted place name '{loc_place}'; not matched to reference dataset",
            stated_text=[loc_place.strip()],
        )
        ev.append(Evidence(field="location", text=_ev_text("location_place", loc_place.strip())))
    elif isinstance(loc_landmark, str) and loc_landmark.strip():
        location = ExtractedLocation(
            landmark=loc_landmark.strip(),
            source="caller_stated",
            status="landmark_only",
            confidence=0.3,
            confidence_basis=f"evon extracted landmark '{loc_landmark}' but no village name",
            stated_text=[loc_landmark.strip()],
        )
        ev.append(Evidence(field="location", text=_ev_text("location_landmark", loc_landmark.strip())))
    else:
        location = ExtractedLocation(
            source="unknown",
            status="missing",
            confidence=0.0,
            confidence_basis="evon found no location information",
        )

    # People affected
    if people_count is not None:
        people = PeopleAffected(
            count=people_count,
            approximate=people_approx,
            confidence=0.7 if people_approx else 0.85,
            confidence_basis=f"evon extracted count {people_count}" + (" (approximate)" if people_approx else ""),
        )
    else:
        people = PeopleAffected(confidence_basis="evon: no people count stated")

    # Vulnerable people
    vp = VulnerablePeople()
    for group in vulnerable_groups:
        if hasattr(vp, group):
            vg_text = _ev_text("vulnerable_groups", group)
            setattr(vp, group, VulnerableMention(count=None, evidence=vg_text))
            ev.append(Evidence(field=f"vulnerable.{group}", text=vg_text))

    # Uncertainties
    raw_unc = data.get("uncertainties")
    uncertainties: list[str] = [
        str(u) for u in (raw_unc if isinstance(raw_unc, list) else [])
        if u and isinstance(u, str)
    ]

    # Summary — prefer Evon's natural-language summary, fall back to template
    evon_summary = data.get("summary")
    summary = evon_summary.strip() if isinstance(evon_summary, str) and evon_summary.strip() else ""

    result = ExtractionResult(
        disaster_type=disaster_type,
        disaster_types_mentioned=[disaster_type] if disaster_type != "unknown" else [],
        disaster_basis=f"evon extraction: {disaster_type}",
        location=location,
        people_affected=people,
        vulnerable_people=vp,
        immediate_needs=immediate_needs,
        reported_danger=reported_dangers,
        medical_emergency=medical_emergency,
        medical_need=True if "medical" in immediate_needs else None,
        critical_medication=None,
        urgency=urgency,
        urgency_basis=f"evon: {urgency_evidence_text or urgency}",
        status_claims=[],
        language=language,
        transcript_quality=quality,
        transcript_quality_basis=f"evon: {quality}",
        uncertainties=uncertainties,
        requires_human_review=bool(uncertainties) or location.status in ("missing", "unmapped"),
        evidence=ev,
        provider="gnani-evon-v3.3",
        provider_mode="real",
        summary=summary,
    )
    # Round-trip through validation so every field is correct before storage.
    return ExtractionResult.model_validate(result.model_dump())
