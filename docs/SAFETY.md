# Safety, human oversight and data policy

## What this system is — and is not

* **Is:** a decision-support prototype that organises synthetic voice reports so a human dispatcher
  can see what may need attention first, why, and what is uncertain.
* **Is not:** a dispatch system, an emergency service, a triage standard, or a substitute for
  official emergency channels. It never contacts responders, victims or emergency numbers, and its
  acknowledgements never promise rescue, arrival times or resolution.

The banner on every page and the API description say this explicitly.

## Human oversight by design

| Mechanism | Where |
|---|---|
| Every recommendation is phrased as a *suggested next human action* | `aggregation.recommend` |
| Field-level confidence gate routes uncertain reports to a review queue with reasons | `services/gate.py`, Human Review page |
| Possible duplicates are **never** merged automatically; a person confirms or rejects | `matching.py` caps, `duplicate_suggestions` |
| Contradictory reports (counts ×2+, "safe" vs threat-to-life, different hazards) are kept apart and flagged | `matching.py`, `aggregation.py` |
| Dispatcher can verify/correct location, count, hazard and priority; mark reviewed; merge; split | `/api/incidents/{id}/review|merge|split` |
| Corrections are overrides with an audit trail (old value, new value, reviewer, note); transcripts and AI extractions are never edited | `audit_log`, `extraction_original`, `human_overrides` |
| New information after a review re-opens it (`rereview_needed`) | `pipeline.refresh_incident` |

## Uncertainty handling

* **Unknown stays unknown.** Missing counts, vulnerable groups or medical status are shown as
  "unknown / not mentioned", never as 0, "none" or "safe".
* **Severity is independent of confidence.** A noisy or ungrounded report that describes a threat to
  life is still scored *critical*; its uncertainty is shown separately ("Info confidence: low") and
  sent to review.
* **No invented locations.** Free text is never geocoded. Coordinates come only from the simulated
  reference gazetteer (exact single-place match) or from a dispatcher. Reference matches are drawn
  with a *dashed* ring and labelled "simulated reference · unverified"; only dispatcher-verified
  locations get a solid ring. Ambiguous, conflicting, unmapped or missing locations are listed below
  the map instead of being plotted.
* **No manufactured confidence.** Numeric "evidence levels" are documented ordinal rule scores
  (docs/ARCHITECTURE.md), labelled as "not probabilities". No LLM self-reported confidence is used.
* **Provider provenance is always visible.** Every transcript and stage shows whether it came from a
  real provider, the **mock** fixture lookup, an authored synthetic fixture, the rule engine, or a human.
  Mock output is never counted as transcription accuracy.
* **No fabricated audio.** If Timbre is unavailable the acknowledgement is text-only and says so.

## Synthetic data policy

* All 52 reports (40 development + 12 hold-out) were written by hand for this prototype. They are
  labelled `SYNTHETIC` in the data files, the database (`is_synthetic`, `synthetic_label`) and the UI.
* All 10 places and 14 landmarks are **fictional** (`backend/data/simulated_gazetteer.json`). Their
  coordinates are arbitrary points placed in the Sahyadri foothills west of Pune only so the basemap
  is not empty; they do not describe real villages, and nothing in this repository describes a real
  emergency.
* The four WAV fixtures are computer-generated (Windows built-in English TTS) renderings of the
  authored transcripts — not recordings of people.
* Do not load real distress recordings, real names, phone numbers or addresses into this prototype.

## Security notes

* API keys only come from environment variables; they are never logged, returned by the API or sent
  to the browser (`/api/health` reports only whether a key is configured).
* Uploads: magic-byte type sniffing, size limit, WAV duration limit, random server-side file names,
  served only with an audio media type and `X-Content-Type-Options: nosniff`.
* CORS is restricted to an explicit list of local origins; only GET/POST/PUT and `Content-Type` are allowed.
* React escapes all text; the only HTML strings (Leaflet tooltips) pass caller-derived text through
  `escapeHtml`.
* There is **no authentication** — this is a local prototype; do not expose it on a network.

## Limitations that matter for safety

See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md). In particular the hold-out evaluation shows the
rule-based extractor **under-triages** reports that use words outside its lexicon ("stranded",
"chest pain", "old lady"). A human must read every transcript; the score is an aid, not a gate.
