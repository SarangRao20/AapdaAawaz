# API reference

Base URL `http://127.0.0.1:8000`. Interactive docs (Swagger UI): **`/docs`**; OpenAPI JSON: `/openapi.json`.
All bodies are JSON unless noted. Datetimes are UTC ISO-8601. Validation errors return **422** with
`{"detail": "<field>: <message>; …", "errors": [{field, message}]}`; missing objects **404**;
invalid state transitions **409**; rejected uploads / bad review requests **400**.

## System

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | DB check, worker queue length, provider status (no secrets) |
| GET | `/api/dashboard/stats` | Live KPIs and breakdowns computed from the database |
| GET | `/api/settings` | Runtime config (gate, dedup, priority, providers) + provider status |
| PUT | `/api/settings?actor=name` | Partial update, validated; audited. Body: `{"gate": {...}, "dedup": {...}, "priority": {...}, "providers": {...}}` |
| GET | `/api/gazetteer` | The SIMULATED reference places/landmarks (for the map and location verification) |
| GET | `/api/audit?limit=&entity_type=` | Recent audit entries |

## Reports

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/reports?status=&language=&needs_review=&source=&q=&limit=&offset=` | Paginated feed, newest first |
| POST | `/api/reports` | Create from text: `{"transcript": "...", "language_hint": "mr", "process": true}` (201) |
| POST | `/api/reports/upload` | multipart `file`, `language_hint`, `source=upload|recording` → new report, queued (201) |
| POST | `/api/reports/{id}/audio` | multipart `file`, `process` → attach audio to an existing report |
| GET | `/api/reports/{id}` | Full detail: audio, transcript provenance, jobs, original & current extraction, gate, priority, links, suggestions, acknowledgement, audit, synthetic ground truth |
| POST | `/api/reports/{id}/process` | (Re)process in the background (202) |
| POST | `/api/reports/{id}/transcript` | `{"text", "reviewer", "language_hint"?, "process": true}` — manual/corrected transcript; previous value kept in the audit log |
| GET | `/api/reports/{id}/audio/{audio_id}` | Stream stored audio (`X-Content-Type-Options: nosniff`) |
| POST | `/api/reports/{id}/acknowledgement?synthesize=true` | Ensure a template acknowledgement exists; synthesise audio with Timbre if available |
| GET | `/api/reports/{id}/acknowledgement/audio` | Synthesised acknowledgement audio (404 if none — never fabricated) |

Upload validation: content is sniffed by magic bytes (WAV, MP3, M4A, AAC, OGG, FLAC), size ≤
`MAX_UPLOAD_MB`, WAV duration ≤ 30 s (Prisma limit). Files are stored under random names and only
served back with their audio media type.

## Incidents and review

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/incidents?priority=critical,high&status=active&review_status=&disaster_type=&language=&verification=verified|reference|ungrounded&sort=priority|recent|reports|confidence&limit=&offset=` | Queue |
| GET | `/api/incidents/{id}` | Detail with member reports, link history, suggestions, audit, review records |
| POST | `/api/incidents/{id}/review` | Human verification (see body below) |
| POST | `/api/incidents/{id}/merge` | `{"source_incident_ids": ["INC-0005"], "reviewer", "notes"?}` — moves all reports in; sources become `merged` |
| POST | `/api/incidents/{id}/split` | `{"report_ids": ["R-…"], "reviewer", "notes"?}` — moves reports to a new incident (at least one must stay) |
| GET | `/api/suggestions?status=pending|confirmed|rejected|obsolete|all` | Duplicate suggestions with both incidents and the report |
| POST | `/api/suggestions/{id}/confirm` | `{"reviewer", "notes"?}` — move the report into the candidate incident |
| POST | `/api/suggestions/{id}/reject` | `{"reviewer", "notes"?}` — keep separate |

Review body (all optional except `reviewer`):

```json
{
  "reviewer": "op-anita",
  "notes": "Caller re-contacted; bridge is in Karanjkhed",
  "verify_location": {"place_id": "P08"},
  "confirm_current_location": false,
  "people_count": 2,
  "clear_people_count": false,
  "urgency": "critical",
  "disaster_type": "flood",
  "mark_reviewed": true
}
```

`verify_location` also accepts `{"place_name": "...", "latitude": 18.6, "longitude": 73.5}` for a
place outside the reference list (coordinates must be confirmed by the reviewer). `urgency` sets the
dispatcher priority label (`"unknown"` removes the override).

## Evaluation

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/evaluation` | Latest stored run (runs one if none) |
| POST | `/api/evaluation/run?include_stt=false` | Replay both synthetic splits with the current config; `include_stt=true` also calls real Prisma on the fixture WAVs (requires key) |
| GET | `/api/evaluation/export.csv` | Per-report ground truth vs prediction (both splits) |

## Demo

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/demo/fixtures` | Synthetic fixtures and whether each is loaded |
| POST | `/api/demo/inject` | `{"fixture_id": "SYN-001", "use_audio": true}` → queued report (202) |
| POST | `/api/demo/seed` | `{"mode": "remaining"|"all"}` → processes fixtures synchronously in scenario order |
| POST | `/api/demo/reset` | `{"reseed": false}` → deletes reports, incidents, links, suggestions, jobs, reviews, audit, evaluation runs and stored files (keeps settings) |

## Examples (PowerShell / curl)

```powershell
curl.exe -s http://127.0.0.1:8000/api/health
curl.exe -s -X POST http://127.0.0.1:8000/api/demo/seed -H "Content-Type: application/json" -d '{\"mode\":\"remaining\"}'
curl.exe -s "http://127.0.0.1:8000/api/incidents?priority=critical&verification=ungrounded"
curl.exe -s -X POST http://127.0.0.1:8000/api/reports/upload -F "file=@backend/data/audio/syn-006.wav" -F "language_hint=en"
curl.exe -s -X POST http://127.0.0.1:8000/api/reports -H "Content-Type: application/json" `
  -d '{\"transcript\":\"Kothale gaon, mandir ke paas. Delivery case hai.\",\"process\":true}'
```
