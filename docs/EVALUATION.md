# Evaluation methodology

Run it from the **Evaluation Lab** page, `POST /api/evaluation/run`, or
`backend\.venv\Scripts\python backend\scripts\manage.py evaluate`. Results are stored in
`evaluation_runs` and exportable as CSV (`/api/evaluation/export.csv`).

## Method

The pipeline is replayed **in memory** with the same pure functions the live system uses —
`extract → priority → gate → matching.decide → aggregate` — in scenario order (`offset_minutes`),
with the current runtime configuration. The database is not touched, so the result does not depend
on what a dispatcher did in the UI.

## Datasets (all synthetic)

| Split | n | How it was made | What its scores mean |
|---|---|---|---|
| **development** (`synthetic_reports.json`) | 40 | Written together with the keyword lexicon; also used for the demo | Mostly that the rules do what they were written to do. **Optimistic.** |
| **hold-out** (`holdout_reports.json`) | 12 | Written after the lexicon was frozen; never used to tune it | A slightly fairer — still synthetic, still tiny — check |

Each report carries a ground-truth label: incident group, hazard, language, reference place (or
null), people count (explicit count; upper bound for ranges; families not converted; null when not
stated), vulnerable-group mentions, medical emergency, and priority under the rubric in
`synthetic_reports.json` (`ground_truth_rubric`). Labels are the author's judgement, not
operational outcomes.

## Metrics

| Metric | Definition |
|---|---|
| Location accuracy | Predicted reference place (only when exactly one reference place is named) vs label. "Correctly unknown" counts as correct; *invented* = a place where the label is null; *missed* = null where a place is labelled |
| People-count accuracy | Exact match of the stated count, same breakdown |
| Hazard type | Hazard named in the transcript vs scenario hazard; reports that never name the hazard appear as *missed* |
| Vulnerable-person detection | Per group TP/FP/FN, precision/recall/F1, plus micro-average. Mention-level |
| Medical emergency | Precision/recall of the medical-emergency flag |
| Priority | Accuracy, 4×4 confusion matrix, per-class P/R/F1, and the list of **under-triaged** (predicted lower than label) and over-triaged reports |
| Language | Accuracy and confusion matrix (mr / hi / en / mixed) |
| Duplicate detection | Pairwise: pairs of reports auto-linked into one incident vs pairs in the same labelled group (precision/recall/F1); predicted vs labelled incident counts; how many *possible-duplicate suggestions* pointed at a true duplicate |
| Human-review rate | Share of reports with at least one gate reason or a possible-duplicate suggestion, with reason counts |
| Latency | In-process time per report for the rule-based pipeline (mean, p95). Live processing time is shown on the dashboard |
| Speech-to-text | Only measured with a **real** provider: success rate and character error rate of Prisma on the 4 synthetic WAVs vs their authored text. The mock STT is a hash lookup and is reported as "not measured" |

Every metric is shown with its sample size.

## Results at the time of writing (default configuration)

| Metric | Development (n=40) | Hold-out (n=12) |
|---|---|---|
| Location accuracy | 100% | 100% |
| People-count accuracy | 100% | 92% (1 missed) |
| Hazard type accuracy | 67.5% (13 never named) | 42% (7 never named) |
| Vulnerable micro-F1 | 100% (24 mentions) | 88% |
| Medical emergency recall | 100% (6) | **100%** (1/1) |
| Priority accuracy | 100% | **92%** (11/12) |
| Duplicate pairs precision / recall | 100% / 77.5% | 100% / 100% (1 pair) |
| Human-review rate | 52.5% | 50% |
| Speech-to-text | not measured (mock mode) | — |

Re-run the evaluation to get current numbers — they change if you edit thresholds on the Settings page.

### Why development recall for duplicates is 77.5%

Nine labelled same-incident pairs are deliberately *not* auto-linked: a noisy transcript (SYN-005),
contradictory counts or status at the Sonarwadi tank (SYN-022/023/024), and two reports about the
same unnamed bridge (SYN-025/026). They are sent to a human as possible-duplicate suggestions
instead. That trade-off (no wrong auto-merges, more human work) is intentional.

### What the hold-out errors show

* *Stranded / of us* — "around 12 of us are stranded" matches neither the trapped lexicon nor the
  people-noun pattern → count missed and the report under-triaged as *medium*.
* *Chest pain / old lady* — English medical and elderly phrasing absent from the lexicon.
* *Fire with nobody inside* — fire-brigade requests carry no priority weight → *low* instead of *medium*.
* *Fragmentary call* — "Dongarwadi … pani …" has no recognised danger → *low*.
* *Past-tense rescue* — "everyone was taken off the roof by boat" still matches "roof" and "boat" →
  over-triaged as *critical* (tense is not modelled).
* *"पचास से ज्यादा लोग" (more than fifty)* — the comparative breaks the count pattern.

These are **not** patched in the lexicon, so the hold-out split stays honest. Real deployment would
need a much larger, independently labelled, real-speech dataset and a learned or LLM extractor with
calibrated uncertainty.

## Known weaknesses of the evaluation itself

* Tiny samples (12 hold-out reports; several classes have support < 5) — confidence intervals would
  be enormous.
* Same author for data, labels and rules → systematic blind spots are shared.
* Transcripts are clean authored text; real ASR errors on noisy, dialectal speech are not represented.
* No inter-annotator agreement for the priority labels.
