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
| **Awaaz Live:** a realtime voice conversation over Gnani Prisma and Timbre streaming, in Hindi, Marathi, English and Hinglish | ✅ code + tests + **live API verified (Nov 3, 2026)** with synthetic speech |
| Gnani **Prisma v3.0** with village-name hints, over REST and streaming | ✅ code + tests + **live API verified (Nov 3, 2026)**, results in [docs/STT_BENCHMARK.md](docs/STT_BENCHMARK.md) |
| Gnani **Timbre v3.0** spoken replies, voice notes and multilingual voice alerts | ✅ code + tests + **live API verified (Nov 3, 2026)** |
| Gnani **Evon** extraction | ⚠️ Evon v3.3 is **Hugging Face open weights only** (not API). Complete OpenAI-compatible adapter implemented for self-hosted deployment, but contest submission uses rule-based extraction |
| Rule-based extraction (location vs simulated gazetteer, people, vulnerable groups, needs, dangers, urgency, language, transcript quality) | ✅ |
| Field-level confidence gate + human-review reasons | ✅ |
| Deterministic duplicate detection (likely / possible / distinct) with evidence | ✅ |
| Explainable priority score (severity separate from information confidence) | ✅ |
| Human review: verify/correct location, people count, priority, hazard; confirm/reject duplicates; merge; split; notes; full audit log | ✅ |
| Command Center: live KPIs, Leaflet map with clustering + offline fallback, filters, queue, live feed | ✅ |
| Evaluation Lab: development + hold-out splits, confusion matrices, P/R, CSV export | ✅ |
| Tests: backend (pytest), frontend (vitest), production build | ✅ |

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
| `EXTRACTION_PROVIDER` | `rules` | `rules` (keyword-based, offline) · `evon` (Evon v3.3 on your own OpenAI-compatible deployment, see `EVON_BASE_URL`) |
| `PRISMA_DEFAULT_LANGUAGE` | `hi-IN` | Used when no language hint is given |
| `PRISMA_TIMEOUT_S` / `PRISMA_MAX_RETRIES` | `30` / `2` | Retries only on 429/5xx/network errors |
| `EVON_BASE_URL` | `https://api.vachana.ai/v1` | Evon LLM endpoint (OpenAI-compatible) |
| `EVON_MODEL` | `evon-v3.3` | Evon model name |
| `EVON_TIMEOUT_S` / `EVON_MAX_RETRIES` | `60` / `2` | Timeout and retries for Evon calls |
| `PRISMA_MODEL`, `PRISMA_FORMAT` | `prisma-v3.0`, `verbatim` | Speech-to-text model and output style. v3.0 sends village-name hints |
| `TIMBRE_MODEL`, `TIMBRE_VOICE_*` | `timbre-v3.0`, `Shivani` | Voice per language (all v3.0 voices are multilingual). Model and voices must match: v2.5 voice names only work on `timbre-v2.5` |
| `AAPDA_VAR_DIR` | `backend/var` | SQLite DB, uploads, generated audio |
| `DATABASE_URL` | `sqlite:///<var>/aapda.db` | |
| `CORS_ORIGINS` | dashboard (`:5173`), caller app (`:5174`), caller APK (`http://localhost`) | Explicit list, no wildcard |
| `MAX_UPLOAD_MB` | `10` | Upload size limit |

Runtime thresholds (confidence gate, dedup, priority labels, provider mode) are edited on the
**Settings** page and stored in the database.

### Awaaz Live

Open **Awaaz Live** in the dashboard, pick a language and press **Start call**. Prisma streams what you say,
the assistant asks by voice for whatever is still missing (the place, what happened, how many people), reads
the facts back, and saves a normal report. The Situation Room shows calls as they happen.

A call needs a login, a microphone, and localhost or HTTPS. It's half duplex: the microphone is ignored while
the assistant speaks, so you can't talk over it. Calls stop after 5 minutes, and they spend Gnani credits.

`LIVE_TIMBRE_MODEL` and `LIVE_TIMBRE_VOICE` choose the voice (default `timbre-v3.0`, `Shivani`), separately from
`TIMBRE_MODEL`, because the assistant's audio tags only work on v3.0.

### Voice alerts

On an incident page, **Voice alert** plays a fixed safety message in each language, then sends it by text and
voice note to the people who reported that incident on Telegram, each in their own language. A dispatcher always
presses send. The wording is written in advance, because Gnani has no translation API and a machine-translated
safety instruction could be wrong. **Have native speakers check this wording before relying on it.**

### Measuring Prisma

`python scripts/benchmark_stt.py --conditions clean phone phone+noise10 phone+noise0 --variants v2.5 v3-hints`
(from `backend/`) scores Prisma on synthetic speech, including phone-quality and noisy audio. See
[docs/STT_BENCHMARK.md](docs/STT_BENCHMARK.md).

### Dashboard login

The landing page is at `/`, and the dashboard needs a login. Set a password in `.env`, then restart the backend:

```
ADMIN_USERNAME=admin
ADMIN_PASSWORD=choose-a-long-password
```

With no password nobody can log in. Everything under `/api` needs a login except what the public caller app
uses to send a report and hear the reply, and Telegram reports always need one. The MCP server signs in with
`API_TOKEN` in `.env`, matched by `AAPDA_API_TOKEN` in its own config. Sessions last 12 hours. Set
`COOKIE_SECURE=true` once the dashboard is served over HTTPS.

### Telegram bot

People can report by voice note, text or GPS in Telegram, with no public URL needed.

1. In Telegram, message **@BotFather**, send `/newbot` and copy the token.
2. Add `TELEGRAM_BOT_TOKEN=<token>` to `.env` and restart the backend. Never commit the token.
3. Open your bot in Telegram and send `/start`.

The bot records what the caller says, then asks for each missing required field (location, what happened,
how many people), one at a time, by text and voice note. Unanswered questions repeat every
`TELEGRAM_FOLLOWUP_INTERVAL_S` seconds (default 120), up to `TELEGRAM_FOLLOWUP_MAX_ATTEMPTS` attempts (default 3).
Telegram bots cannot place phone or voice calls, so these messages are the automated follow-up.

The **Share location** button stores the caller's real GPS, labelled separately from simulated village points.
Anyone who finds the bot can use it unless you set `TELEGRAM_ALLOWED_CHAT_IDS`. Run only one copy per token.

### 3D location view

Command Center → **3D Site**, and each incident page, fly into a tilted view of the incident. It works with no key,
using free satellite imagery and terrain. For Google's photorealistic 3D tiles, add
`VITE_GOOGLE_MAPS_API_KEY=<key>` to `frontend/.env.local`, enable the **Map Tiles API** and the
**Maps JavaScript API**, and restrict the key by HTTP referrer, since it reaches the browser. Google requires billing
to be enabled on the project.

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
cd backend;  .\.venv\Scripts\python -m pytest -q          # 76 tests
cd frontend; npm test; npm run build                       # 5 tests + typecheck + production build
```

### CI/CD

`.github/workflows/ci-cd.yml` runs on every push and pull request:

| Job | What it checks |
|---|---|
| Backend | `pip install`, byte-compile, `pytest tests` (`test_live_api.py` is excluded — it calls the paid Gnani API) |
| Frontend | `npm ci`, `tsc`, `vitest`, production build |
| Caller app | `npm ci`, `oxlint`, web build |

A push to `main` that passes all three then deploys automatically (a manual
`workflow_dispatch` on `main` does the same). The deploy job tars `backend/`,
copies it to the VM and runs `.github/scripts/remote_deploy.sh` there, which:

1. backs up the live code and snapshots the SQLite database to
   `~/aapda/.deploy/backups/` (last 5 of each kept),
2. rsyncs the new tree, leaving `venv/`, `var/` (database, uploads) and `.env` untouched,
3. installs dependencies only if `requirements.txt` changed,
4. restarts the `aapda-api` systemd unit and polls `/api/health`,
5. restores the backup and restarts if anything fails, then exits non-zero.

The live commit is recorded in `~/aapda/.deploy/DEPLOYED_SHA` and every run is
appended to `~/aapda/.deploy/deploy.log`.

Repository secrets required (Settings → Secrets and variables → Actions):
`VM_HOST`, `VM_USER`, `VM_SSH_KEY` (private key, public half in
`~/.ssh/authorized_keys` on the VM) and optionally `VM_PORT` (default 22).

---

## Architecture (short)

```
frontend/ (React + TS + Vite + Tailwind + Leaflet + Recharts)
   │  polls /api every 2–4 s (no fake live connection)
backend/app/
   api/        FastAPI routes (thin) + serializers
   services/   extraction · gate · priority · matching · aggregation   ← pure, deterministic
               pipeline · worker · review · demo · evaluation · stats  ← DB orchestration
   providers/  prisma (STT) · timbre (TTS) · evon (optional, self-hosted) · mock_stt · registry
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
