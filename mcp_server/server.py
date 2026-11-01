"""Aapda Awaaz MCP Server — exposes the disaster-triage pipeline as agent tools.

Any MCP-compatible agent (Claude, etc.) can call:
  submit_report      — submit a text report and get back a report ID
  get_report         — poll processing status + extracted facts for a report
  list_incidents     — list active/all incidents with optional filters
  get_incident       — full details for one incident
  get_system_health  — pipeline provider status

Run:
  python server.py                          # uses AAPDA_API_URL env var
  AAPDA_API_URL=http://localhost:8000 python server.py
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

BASE_URL = os.environ.get("AAPDA_API_URL", "http://localhost:8000").rstrip("/")

mcp = FastMCP(
    "aapda-awaaz",
    instructions=(
        "Aapda Awaaz is a disaster voice-triage system for India. "
        "It ingests emergency calls in Hindi, Marathi and English, "
        "transcribes them with Gnani Prisma STT, extracts structured facts "
        "with Gnani Evon LLM, deduplicates against existing incidents, "
        "prioritises by urgency, and sends a voice acknowledgement back to "
        "the caller via Gnani Timbre TTS. Use submit_report to start the "
        "pipeline, get_report to poll until processed, and list_incidents / "
        "get_incident to read the output."
    ),
)


def _client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=30)


def _ok(resp: httpx.Response) -> dict[str, Any]:
    resp.raise_for_status()
    return resp.json()


# ── Tools ──────────────────────────────────────────────────────────────────


@mcp.tool()
def submit_report(
    transcript: str,
    language_hint: str = "hi",
) -> dict:
    """Submit a disaster report as text and start the Gnani AI pipeline.

    Args:
        transcript: The caller's words, verbatim, in Hindi / Marathi / English.
        language_hint: ISO-639-1 code — 'hi' Hindi, 'mr' Marathi, 'en' English,
                       'mixed' Hinglish. Default 'hi'.

    Returns a dict with:
      id          — report ID to pass to get_report
      status      — initial status (usually 'received' or 'queued')
      pipeline    — 'started'
    """
    with _client() as c:
        data = _ok(c.post("/api/reports", json={
            "transcript": transcript,
            "language_hint": language_hint,
            "process": True,
        }))
    return {"id": data["id"], "status": data["status"], "pipeline": "started"}


@mcp.tool()
def get_report(report_id: str) -> dict:
    """Get the current processing status and extracted facts for a report.

    Poll every few seconds until status is 'processed', 'failed', or
    'needs_transcript'. Once processed, the response includes:
      status            — 'processed' when done
      transcript        — transcribed text
      disaster_type     — flood / earthquake / fire / landslide / etc.
      location_text     — place name stated by caller
      people_count      — number of people affected (or null)
      priority_label    — critical / high / medium / low
      priority_score    — numeric score (0–120+)
      incident_id       — the deduplicated incident this was grouped into
      follow_up_needed  — True if key info was missing and a question was asked
      follow_up_questions — list of questions embedded in the TTS reply
      acknowledgement   — text sent back to the caller (+ audio_url if ready)
    """
    with _client() as c:
        data = _ok(c.get(f"/api/reports/{report_id}"))
    ext = data.get("extraction_current") or {}
    loc = ext.get("location") or {}
    people = ext.get("people_affected") or {}
    ack = data.get("acknowledgement") or {}
    return {
        "id": data["id"],
        "status": data["status"],
        "transcript": data.get("transcript"),
        "language": ext.get("language") or data.get("language_hint"),
        "disaster_type": ext.get("disaster_type"),
        "location_text": loc.get("place_name") or loc.get("landmark"),
        "people_count": people.get("count"),
        "urgency": ext.get("urgency"),
        "medical_emergency": ext.get("medical_emergency"),
        "immediate_needs": ext.get("immediate_needs", []),
        "priority_label": data.get("priority_label"),
        "priority_score": data.get("priority_score"),
        "incident_id": data.get("incident_id"),
        "dedup_outcome": data.get("dedup_outcome"),
        "follow_up_needed": data.get("follow_up_needed", False),
        "follow_up_questions": data.get("follow_up_questions", []),
        "acknowledgement_text": ack.get("text"),
        "acknowledgement_audio_url": ack.get("audio_url"),
        "error": data.get("error"),
    }


@mcp.tool()
def list_incidents(
    status: str = "active",
    limit: int = 20,
    priority: str | None = None,
    disaster_type: str | None = None,
) -> dict:
    """List incidents currently tracked by the system.

    Args:
        status:        'active', 'merged', 'closed', or 'all'. Default 'active'.
        limit:         Max results to return (1–100). Default 20.
        priority:      Filter by priority label — 'critical', 'high', 'medium', 'low'.
        disaster_type: Filter by type — 'flood', 'earthquake', 'fire', 'landslide', etc.

    Returns a list of incident summaries, each with id, disaster_type, location,
    people_count, priority_label, urgency, report_count, and created_at.
    """
    params: dict[str, Any] = {"limit": min(max(1, limit), 100)}
    if status != "all":
        params["status"] = status
    with _client() as c:
        data = _ok(c.get("/api/incidents", params=params))
    items = data.get("items", [])
    if priority:
        items = [i for i in items if i.get("priority_label") == priority]
    if disaster_type:
        items = [i for i in items if i.get("disaster_type") == disaster_type]
    return {
        "total": len(items),
        "incidents": [
            {
                "id": i["id"],
                "disaster_type": i.get("disaster_type"),
                "location": (i.get("location") or {}).get("place_name") or (i.get("location") or {}).get("unmapped_name"),
                "latitude": i.get("latitude"),
                "longitude": i.get("longitude"),
                "people_count": i.get("people_count"),
                "priority_label": i.get("priority_label"),
                "priority_score": i.get("priority_score"),
                "urgency": i.get("urgency"),
                "medical_emergency": i.get("medical_emergency"),
                "report_count": i.get("report_count", 1),
                "status": i.get("status"),
                "created_at": i.get("created_at"),
                "updated_at": i.get("updated_at"),
            }
            for i in items
        ],
    }


@mcp.tool()
def get_incident(incident_id: str) -> dict:
    """Get full details for one incident, including all linked caller reports.

    Returns the incident's location (with coordinates if mappable), people
    count, danger types, immediate needs, priority breakdown, all reports
    grouped under it, and recommended action.
    """
    with _client() as c:
        data = _ok(c.get(f"/api/incidents/{incident_id}"))
    loc = data.get("location") or {}
    return {
        "id": data["id"],
        "status": data.get("status"),
        "disaster_type": data.get("disaster_type"),
        "location": {
            "place_name": loc.get("place_name") or loc.get("unmapped_name"),
            "district": loc.get("district"),
            "state": loc.get("state"),
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
        },
        "people_count": data.get("people_count"),
        "vulnerable": data.get("vulnerable") or {},
        "needs": data.get("needs", []),
        "dangers": data.get("dangers", []),
        "medical_emergency": data.get("medical_emergency"),
        "urgency": data.get("urgency"),
        "priority_label": data.get("priority_label"),
        "priority_score": data.get("priority_score"),
        "summary": data.get("summary"),
        "recommended_action": data.get("recommended_action"),
        "report_count": data.get("report_count", 1),
        "languages": data.get("languages", []),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "reports": [
            {
                "id": r["id"],
                "language": r.get("language"),
                "transcript": r.get("transcript"),
                "disaster_type": r.get("disaster_type"),
                "priority_label": r.get("priority_label"),
                "received_at": r.get("received_at"),
            }
            for r in data.get("reports", [])
        ],
    }


@mcp.tool()
def get_system_health() -> dict:
    """Check the live status of the Gnani AI pipeline providers.

    Returns whether Prisma STT, Evon LLM, and Timbre TTS are reachable,
    plus configuration details (models, endpoints).
    """
    with _client() as c:
        data = _ok(c.get("/api/system/health"))
    return data


if __name__ == "__main__":
    mcp.run(transport="stdio")
