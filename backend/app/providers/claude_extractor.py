"""Claude (Anthropic) structured-extraction adapter.

Reuses the prompt infrastructure from providers/evon.py — same system message,
user message builder, JSON parser, and schema mapper. The only difference is
the API call: native Anthropic SDK instead of the OpenAI-compatible endpoint.

Set CLAUDE_API_KEY and EXTRACTION_PROVIDER=claude in .env to activate.
The model defaults to claude-sonnet-4-5 (CLAUDE_MODEL to override).
"""
from __future__ import annotations

import logging

import anthropic

from ..config import settings
from ..schemas import ExtractionResult
from .base import ProviderError, ProviderUnavailable
from .evon import _SYSTEM_MESSAGE, _build_user_message, _parse_json, _to_extraction_result

log = logging.getLogger("aapda.providers.claude")


class ClaudeExtractor:
    """Structured extraction using the Anthropic Claude API."""

    name = "claude-sonnet"
    mode = "real"

    def __init__(self) -> None:
        if not settings.claude_api_key:
            raise ProviderUnavailable(
                "Claude extraction requires CLAUDE_API_KEY — set it and EXTRACTION_PROVIDER=claude"
            )
        self._client = anthropic.Anthropic(api_key=settings.claude_api_key)

    def extract(self, transcript: str, language_hint: str | None = None) -> ExtractionResult:
        """Call Claude, parse the JSON response, return a validated ExtractionResult."""
        log.debug(
            "claude extract  model=%s  transcript_chars=%d",
            settings.claude_model,
            len(transcript),
        )
        try:
            resp = self._client.messages.create(
                model=settings.claude_model,
                max_tokens=2048,
                system=_SYSTEM_MESSAGE,
                messages=[
                    {
                        "role": "user",
                        "content": _build_user_message(transcript, language_hint),
                    }
                ],
            )
        except anthropic.APIConnectionError as exc:
            raise ProviderError("Claude network error", transient=True) from exc
        except anthropic.RateLimitError as exc:
            raise ProviderError("Claude rate limit", transient=True) from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(
                f"Claude API error {exc.status_code}",
                transient=exc.status_code >= 500,
            ) from exc

        raw = resp.content[0].text
        log.debug("claude raw response  chars=%d", len(raw))

        try:
            data = _parse_json(raw)
        except ValueError as exc:
            raise ProviderError(f"Claude returned non-JSON content: {exc}") from exc

        result = _to_extraction_result(data, transcript, language_hint)
        # Override provider fields — evon._to_extraction_result sets provider="gnani-evon-v3.3"
        result = result.model_copy(update={"provider": "claude-sonnet", "provider_mode": "real"})
        return ExtractionResult.model_validate(result.model_dump())
