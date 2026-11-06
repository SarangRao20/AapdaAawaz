# Gnani Internship Challenge Submission

> **Before submitting, replace everything marked `[TO CONFIRM]` and delete this note.**

**Project:** Aapda Awaaz: a voice assistant for disaster response, built on Gnani AI
**Builder:** `[TO CONFIRM: your registered name, or both names if you are a team of two]`
**Demo video:** `[TO CONFIRM: link]`
**Posts:** `[TO CONFIRM: LinkedIn URL]` | `[TO CONFIRM: X URL]` (live before submitting, tagging Gnani AI, with #GnaniAI and #GreatIndianAIInternshipChallenge)

---

## The problem

In a flood, emergency lines fill up. Callers are frightened, they switch between languages, and many reports describe
the same place. People wait, and dispatchers get a pile of unstructured audio.

## The users

* **People in a disaster,** who may only be able to speak, in Hindi, Marathi, English, Hinglish, or Bengali, Gujarati, Kannada, Malayalam, Punjabi, Tamil or Telugu.
* **Dispatchers,** who need to know where, what and how many people, and which report comes first.

## What it does

**Awaaz Live is a realtime voice conversation.** The caller speaks. Gnani Prisma transcribes it, and Gnani Timbre asks
aloud, in the caller's language, for only what's still missing: the place, what happened, or how many people. It then
reads the facts back to confirm them.

While that happens, a dispatcher watches the report fill in live, already ranked, with no typing. The dispatcher can
then send a **voice alert** back, spoken by Timbre in each person's own language.

The same voice flow also runs as a **Telegram bot** that takes voice notes and asks follow-up questions by text and voice.

```
Caller speaks → Prisma v3.0 streaming → facts extracted → Timbre v3.0 asks for what's missing → report
                                                                    ↓
                     Dispatcher sees it live → reviews → voice alert by Timbre in each language
```

---

## Gnani AI models used

Voice is the product here, and every word the caller hears or says goes through Gnani.

### Prisma (speech to text)
* **Realtime streaming** over WebSocket for the live conversation, using its voice activity detection to know when
  the caller has stopped.
* **Prisma v3.0 `keyterms`:** we send local village names and disaster words, so the places that matter are heard
  correctly. On our benchmark this took the village from 6/12 clips to 12/12.
* **Code-mixed speech:** Hinglish calls use v3.0's `codemix` format, keeping English words in Latin script.
* **REST** for uploaded audio and Telegram voice notes.

### Timbre (text to speech)
* **Realtime streaming** over WebSocket, so a reply starts in about a second.
* **v3.0 audio tags** for delivery, such as natural pauses between sentences, at a slightly slower speed for a
  frightened caller.
* **One voice in several languages** for the questions, the read-back and the voice alerts.

### Not used
* **Evon** isn't on Gnani's API. Questions and extraction are deterministic rules, which also means the assistant can't
  improvise a promise of rescue. An adapter exists for a self-hosted Evon, but it isn't part of this entry.
* **Agent Builder** is out of scope under the contest rules.

---

## Results

All measured against the live Gnani API on November 3, 2026, using synthetic speech only.

**Live calls:** full conversations completed in Hindi, Marathi, Hinglish and English, each producing the right place,
disaster and head count. In those calls, Prisma took about 0.2–0.5 s to transcribe a phrase, and the assistant's voice
began about 1.1–1.5 s after that started. On top of this, Prisma waits for 0.9 s of silence to know the caller has stopped.

**Noisy phone audio** (12 clips, see [docs/STT_BENCHMARK.md](docs/STT_BENCHMARK.md)). Clips with village, disaster and head count all correct:

| Audio | Prisma v2.5 | Prisma v3.0 + our hints |
|---|---:|---:|
| Clean | 6/12 | 11/12 |
| Phone quality | 6/12 | 11/12 |
| Phone + noise at 10 dB | 6/12 | 11/12 |
| Phone + noise as loud as the speech | 6/12 | 10/12 |

This is a small synthetic test, not a measure of real callers. Our own noise filter didn't improve on Prisma, so it stays off.

**Triage on the 40 synthetic sample reports:** 22 candidate incidents, 18 duplicates linked automatically, 7 possible
duplicates left for a person to decide, and 13 critical incidents.

---

## Responsible design

* **A person always decides.** Nothing is dispatched automatically, and a dispatcher chooses to send every alert.
* **It doesn't pretend.** It says it isn't an emergency service, points to 112, and never promises help is coming.
* **Fixed wording.** Questions and safety messages are written in advance, because a machine-translated safety
  instruction could be wrong. They still need checking by native speakers.
* **Uncertainty stays visible.** Unclear details are flagged for review, and unverified locations are marked as such.
* **Explainable ranking.** Each priority shows the reasons behind it.
* **Evidence is kept.** The caller's audio, the transcript and an audit trail stay with each report.
* **Private by default.** The dashboard needs a login, and reports with real voices are never on the public routes.

The main limits are in [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md). Most importantly, this is a prototype that
has been tested with synthetic speech, not real callers, and a caller can't yet interrupt the assistant.

---

## Awards this fits

`[TO CONFIRM: choose after settling solo or team. An entry can win only one award.]`

* **Real Deal:** a voice assistant for people in a disaster and the dispatchers helping them.
* **Noise Canceller:** the benchmark above, on phone-quality audio with heavy noise.
* **Mixed Vibes:** a live Hinglish conversation, with code-mixed transcription.
* **Demo Day Drop:** the 60-second demo in [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).
* **Solo Ninja or Two-Person Army:** whichever matches how the entry is registered.

---

## Contribution of each member

`[TO CONFIRM: what each person built. The contest requires this, and it must match the registration.]`

---

## Technical stack

* **Backend:** Python, FastAPI, SQLAlchemy, SQLite, WebSockets
* **Frontend:** React, TypeScript, Vite, Tailwind CSS, Leaflet
* **Gnani:** Prisma v3.0 (streaming and REST), Timbre v3.0 (streaming and REST)
* **Also:** Telegram Bot API, optional MCP server
* **Tests:** pytest and vitest (`pytest -q` in `backend/`, `npm test` in `frontend/`)

A live call needs internet access and Gnani credits. The sample data and dashboard also run without them, using a clearly
labelled mock.

## Repository

`[TO CONFIRM: public GitHub URL, or "available on request"]`. Quick start is in [README.md](README.md).

**Contest deadline:** November 10, 2026, 11:59 PM IST
