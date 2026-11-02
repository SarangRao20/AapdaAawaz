# Known limitations

## Providers

* **Gnani Prisma (STT)** — adapter follows the public docs (`POST /stt/v3`, `X-API-Key-ID`,
  `audio_file` + `language_code`, verbatim format, 30 s per request, retries on 429/5xx). **Tested
  and working with live API** (Oct 30, 2026). Prisma has no Hinglish code; mixed speech is sent as
  `hi-IN`. Audio longer than 30 s is rejected (WAV) or will fail at the provider (other formats) —
  there is no chunking. Optional preprocessing (`AUDIO_PREPROCESSING=true`) applies a spectral noise
  gate + RMS loudness normalisation before the audio is sent to Prisma; requires
  numpy/scipy/noisereduce/soundfile. On any preprocessing error the original file is used unchanged.
* **Gnani Timbre (TTS)** — **tested and working with live API** (v2.5, Oct 30, 2026). Voice names
  (Ishaan, Nalini, Kaveri, Poorvi) come from the public voice catalogue.
* **Gnani Evon** — Evon v3.3 is available as **open weights on Hugging Face** (Apache 2.0), not as
  an API service. Running Evon locally is out of scope for this contest submission. The codebase
  includes a complete OpenAI-compatible adapter (`app/providers/evon.py`) that could be used with
  a self-hosted Evon deployment, but for the contest submission the system uses **Prisma STT +
  rule-based extraction + Timbre TTS** — two Gnani API models end-to-end.
* **Mock STT** — recognises only the 4 bundled WAVs by SHA-256 hash. Any other audio goes to
  `needs_transcript`. It performs no speech recognition.
* Browser recording is converted to 16 kHz mono WAV in the browser; very old browsers without
  `MediaRecorder`/`AudioContext` cannot record (upload still works).

## Extraction, dialects and language

* Keyword lexicon of a few hundred terms; misses synonyms, idioms, spelling variants and dialects it
  has not seen (see hold-out errors in EVALUATION.md: "stranded", "chest pain", "old lady",
  "पचास से ज्यादा").
* No model of tense or modality: "everyone *was* rescued from the roof" still matches "roof" → can
  over-triage; "children *may be* trapped" is treated as trapped.
* Negation is a short-window heuristic; long-distance or double negation fails.
* Romanised Marathi is barely covered; Konkani, Ahirani, Varhadi and other regional varieties are not.
* Language detection is marker-based and only distinguishes mr / hi / en / mixed.
* Hazard type is only what the transcript names (many reports never name it).
* The rule-generated summary is template text, not a natural-language summary.

## Geolocation

* Only the **fictional** 10-place reference gazetteer is used; coordinates are arbitrary simulated
  points near Pune chosen for display. A reference match marks the *village reference point*, not
  the incident's exact position.
* Places outside the reference list can optionally be geocoded via Nominatim/OSM (set
  `GEOCODING_ENABLED=true`). When enabled, the returned OSM centroid is used — still an
  approximation of the incident site. Requires internet access; adds ≤3 s latency per unmapped
  place (cached in-process after the first lookup).
* Generic landmarks ("the big bridge") produce candidate lists, not locations.
* Several incidents in one village share one point; the map clusters/spiderfies them.

## Deduplication and priority

* **Unclear reports are raised, not measured.** Reports with no danger, need or urgency identified, or with
  a low-quality transcript, rank at least `medium` (`priority.unclear_floor`) unless the caller says it is
  not urgent or people are safe. This keeps them above "low" but below real critical reports; review them
  by listening to the audio.
* **Possible misheard villages are not pinned.** A word one character away from a reference village name
  is recorded as a candidate that a person must confirm, with no coordinates.
* **Number words are partial.** English compounds work ("twenty five", "one hundred and fifty"). Hindi and
  Marathi words outside the lexicon (for example छब्बीस) leave the count unknown rather than wrong.

* Weights and thresholds are hand-set on synthetic data; not validated operationally or clinically.
* Matching compares a report with incident aggregates; a long chain of partially-overlapping reports
  could drift. Re-processing a report re-matches it but does not re-cluster everything.
* Duplicate suggestions are only created when a report is processed; incidents are not re-compared
  later when new evidence arrives.
* Priority ignores fire-brigade requests, time since report and resource availability.

## System

* No authentication or authorisation; reviewer name is free text. Local use only.
* Single-process worker thread and SQLite: fine for a demo, not for concurrent multi-user load.
* Polling (2–4 s) rather than push updates.
* Schema is created with `create_all`; there are no migration scripts yet (schema version 1).
* `Reset` deletes all reports, incidents, audit history and stored audio in the local database.
* Evaluation is on tiny synthetic datasets written by the same author as the rules (see EVALUATION.md).
