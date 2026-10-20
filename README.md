# Aapda Awaaz — Voice Intelligence for Disaster Response

> **Prototype · synthetic data only · decision support.** Aapda Awaaz does not dispatch responders,
> contact emergency services or guarantee any outcome. Every action stays with a human dispatcher.
> All reports, people and places in this repository are fictional.

Aapda Awaaz turns chaotic emergency voice reports (Marathi, Hindi, Hinglish, English) into a
prioritised, deduplicated, uncertainty-aware incident picture:

```
voice note → speech-to-text → structured extraction → field-level confidence gate
           → duplicate detection / clustering → explainable priority → map + queue → human review
```

It runs fully offline on a laptop. Without a Gnani API key it uses a **clearly labelled mock**
speech-to-text that only recognises the bundled synthetic audio, and it never presents mock output
as real model output.

---

## What works today

| Area | Status |
|---|---|
| Ingestion: audio upload (WAV/MP3/M4A/AAC/OGG/FLAC), browser recording (→16 kHz WAV), typed transcript, synthetic demo injection | ✅ |
| Background processing worker with per-stage job records (provider, mode, timing, errors) | ✅ |
| Gnani **Prisma** speech-to-text adapter (documented REST API, retries, timeouts) | ✅ code + tests + **live API verified (Oct 30, 2026)** |
| Gnani **Timbre** text-to-speech acknowledgements | ✅ code + tests + **live API verified (Oct 30, 2026)** |
| Gnani **Evon** extraction | ⚠️ Evon v3.3 is **Hugging Face open weights only** (not API). Complete OpenAI-compatible adapter implemented for self-hosted deployment, but contest submission uses rule-based extraction |
| Rule-based extraction (location vs simulated gazetteer, people, vulnerable groups, needs, dangers, urgency, language, transcript quality) | ✅ |
| Field-level confidence gate + human-review reasons | ✅ |
| Deterministic duplicate detection (likely / possible / distinct) with evidence | ✅ |
| Explainable priority score (severity separate from information confidence) | ✅ |
| Human review: verify/correct location, people count, priority, hazard; confirm/reject duplicates; merge; split; notes; full audit log | ✅ |
| Command Center: live KPIs, Leaflet map with clustering + offline fallback, filters, queue, live feed | ✅ |
| Evaluation Lab: development + hold-out splits, confusion matrices, P/R, CSV export | ✅ |
| Tests: 76 backend (pytest) + 5 frontend (vitest); production build | ✅ |

See [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) before relying on anything.

---

## Quick start (Windows)

Prerequisites: **Python 3.11+** (verified on 3.13) and **Node.js 18+** (verified on 22.x).
If your system Node is older, unpack a portable Node into `.tools\node\` — the scripts use it automatically.

```powershell
# one-time setup (venv, pip install, npm install, create .env, init database)
powershell -ExecutionPolicy Bypass -File setup.ps1

# terminal 1 — API on http://127.0.0.1:8000  (Swagger UI: http://127.0.0.1:8000/docs)
powershell -ExecutionPolicy Bypass -File run-backend.ps1

# terminal 2 — UI on http://127.0.0.1:5173
powershell -ExecutionPolicy Bypass -File run-frontend.ps1
```

Manual equivalent:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

cd ..\frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173 and use the **Demo** buttons on the Command Center (see
[docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)).

### Configuration

Copy `.env.example` to `.env` (repo root or `backend/`). Real environment variables win over
`backend/.env`, which wins over the root `.env`.

| Variable | Default | Meaning |
|---|---|---|
| `GNANI_API_KEY` | *(empty)* | Enables Prisma STT and Timbre TTS. Never logged or returned by the API. |
| `GNANI_BASE_URL` | `https://api.vachana.ai` | Gnani API base URL |
| `STT_PROVIDER` | `auto` | `auto` (Prisma if key, else mock) · `prisma` · `mock` |
| `TTS_PROVIDER` | `auto` | `auto` (Timbre if key) · `none` |
| `EXTRACTION_PROVIDER` | `rules` | `rules` (keyword-based, offline) · `evon` (Gnani Evon v3.3 LLM, requires key) |
| `PRISMA_DEFAULT_LANGUAGE` | `hi-IN` | Used when no language hint is given |
| `PRISMA_TIMEOUT_S` / `PRISMA_MAX_RETRIES` | `30` / `2` | Retries only on 429/5xx/network errors |
| `EVON_BASE_URL` | `https://api.vachana.ai/v1` | Evon LLM endpoint (OpenAI-compatible) |
| `EVON_MODEL` | `evon-v3.3` | Evon model name |
| `EVON_TIMEOUT_S` / `EVON_MAX_RETRIES` | `60` / `2` | Timeout and retries for Evon calls |
| `TIMBRE_MODEL`, `TIMBRE_VOICE_*` | `timbre-v3.0`, Ishaan/Nalini/Kaveri/Poorvi | Voice per language |
| `AAPDA_VAR_DIR` | `backend/var` | SQLite DB, uploads, generated audio |
| `DATABASE_URL` | `sqlite:///<var>/aapda.db` | |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Explicit list, no wildcard |
| `MAX_UPLOAD_MB` | `10` | Upload size limit |

Runtime thresholds (confidence gate, dedup, priority labels, provider mode) are edited on the
**Settings** page and stored in the database.

### Database

SQLite at `backend/var/aapda.db`; tables are created on startup and data survives restarts.

```powershell
cd backend
.\.venv\Scripts\python scripts\manage.py init-db          # create tables
.\.venv\Scripts\python scripts\manage.py seed             # load synthetic reports not yet loaded
.\.venv\Scripts\python scripts\manage.py reset --reseed   # wipe reports/incidents/audit, reload demo
.\.venv\Scripts\python scripts\manage.py evaluate         # print evaluation metrics
```

Stop the API before running `reset` from the command line (or use the Reset button in the UI).

### Tests and build

```powershell
cd backend;  .\.venv\Scripts\python -m pytest -q          # 47 tests
cd frontend; npm test; npm run build                       # 5 tests + typecheck + production build
```

---

## Architecture (short)

```
frontend/ (React + TS + Vite + Tailwind + Leaflet + Recharts)
   │  polls /api every 2–4 s (no fake live connection)
backend/app/
   api/        FastAPI routes (thin) + serializers
   services/   extraction · gate · priority · matching · aggregation   ← pure, deterministic
               pipeline · worker · review · demo · evaluation · stats  ← DB orchestration
   providers/  prisma (STT) · timbre (TTS) · evon (stub) · mock_stt · registry
   models.py   SQLAlchemy (reports, incidents, links, suggestions, jobs, reviews, audit, ground truth…)
backend/data/  simulated gazetteer · 40 synthetic reports · 12 hold-out reports · 4 synthetic WAVs
```

Full details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · API: [docs/API.md](docs/API.md) ·
Safety: [docs/SAFETY.md](docs/SAFETY.md) · Evaluation: [docs/EVALUATION.md](docs/EVALUATION.md).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| UI shows "API offline" / "Backend unreachable" | Start the backend on port 8000; the Vite dev server proxies `/api` to it (`VITE_API_TARGET` overrides). |
| `npm` errors about syntax / very old npm | Your system Node is too old. Put Node 18+ on `PATH` or in `.tools\node\`. |
| Map is grey with a yellow banner | OpenStreetMap tiles could not load (offline). Markers still render at their simulated positions. |
| Uploaded audio ends in "needs transcript" | Expected without `GNANI_API_KEY`: the mock STT only knows the 4 bundled fixture WAVs. Type the transcript on the report page. |
| Upload rejected "accepts at most 30 s" | Prisma's documented per-request limit; trim the clip. |
| Reset from CLI fails with "database is locked" | Stop the API server first, or use the UI Reset button. |
| Want a clean demo | Command Center → **Reset** (click twice to confirm) → **1 · Incoming call** → **2 · Load all synthetic reports**. |

---

## Repository layout

```
.env.example  .gitignore  setup.ps1  run-backend.ps1  run-frontend.ps1  README.md
backend/  app/ (api, providers, services, config.py, db.py, models.py, schemas.py, main.py)
          data/ (simulated_gazetteer.json, synthetic_reports.json, holdout_reports.json, audio/*.wav)
          scripts/ (manage.py, make_audio_fixtures.ps1)  tests/  requirements.txt
frontend/ src/ (pages, components, lib)  package.json  vite.config.ts  tailwind.config.js
docs/     ARCHITECTURE.md API.md SAFETY.md EVALUATION.md DEMO_SCRIPT.md KNOWN_LIMITATIONS.md
```
