"""Evaluation against the labelled SYNTHETIC dataset.

The pipeline is replayed in memory with the same pure functions the live system uses
(extraction -> priority -> gate -> matching -> aggregation), in scenario order, using the
current runtime configuration. Nothing in the database is touched.

What is (and is not) measured:
* Extraction/priority/dedup metrics measure the deterministic RULE-BASED components on
  authored text fixtures. The lexicon was written together with this dataset, so these
  numbers are optimistic and say nothing about real-world calls.
* Speech-to-text is only measured when a real provider (Prisma) is configured AND the
  caller asks for it; the mock STT is a hash lookup and is never reported as accuracy.
"""
from __future__ import annotations

import csv
import io
import json
import statistics
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from ..config import DATA_DIR
from . import gate, matching
from . import priority as prio
from .aggregation import Member, aggregate
from .demo import AUDIO_DIR, load_fixtures
from .extraction import extract


@lru_cache(maxsize=1)
def load_holdout() -> dict:
    return json.loads((DATA_DIR / "holdout_reports.json").read_text(encoding="utf-8"))


SPLITS = {
    "development": ("40 reports written together with the rule lexicon (also used for the demo). "
                    "Scores here mostly show the rules do what they were written to do."),
    "holdout": ("12 reports written after the lexicon was frozen and never used to tune it. "
                "Closer to — but still not — real-world performance."),
}

LABELS = ["critical", "high", "medium", "low"]
VUL_GROUPS = ["elderly", "children", "infants", "pregnant_people", "people_with_disabilities"]


def _prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f1 = 2 * p * r / (p + r) if p and r else None
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f1}


def _abstain_breakdown(rows: list[dict], key: str) -> dict:
    """correct / wrong / missed (gt known, pred None) / false_value (gt None, pred value) / correct_unknown."""
    out = {"correct": 0, "correct_unknown": 0, "wrong": 0, "missed": 0, "false_value": 0}
    for r in rows:
        gt, pred = r[f"gt_{key}"], r[f"pred_{key}"]
        if gt is None and pred is None:
            out["correct_unknown"] += 1
        elif gt is None:
            out["false_value"] += 1
        elif pred is None:
            out["missed"] += 1
        elif gt == pred:
            out["correct"] += 1
        else:
            out["wrong"] += 1
    n = len(rows)
    out["n"] = n
    out["accuracy"] = (out["correct"] + out["correct_unknown"]) / n if n else None
    return out


def replay(cfg: dict, fixtures: list[dict] | None = None) -> tuple[list[dict], dict[str, list[str]]]:
    fixtures = sorted(fixtures if fixtures is not None else load_fixtures()["reports"],
                      key=lambda f: f["offset_minutes"])
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    incidents: dict[str, list[Member]] = {}
    profiles: dict[str, matching.Profile] = {}
    rows: list[dict] = []
    for fx in fixtures:
        t0 = time.perf_counter()
        received = base + timedelta(minutes=fx["offset_minutes"])
        ext = extract(fx["transcript"], fx["language_hint"]).model_dump()
        pr = prio.score(prio.features_from_extraction(ext), cfg)
        _fields, reasons = gate.assess(ext, pr["label"], cfg)
        decision = matching.decide(matching.report_profile(ext, received, fx["transcript"]), profiles, cfg)
        if decision.outcome == "likely_duplicate":
            iid = decision.incident_id
        else:
            iid = f"EVAL-{len(incidents) + 1:03d}"
            incidents[iid] = []
        incidents[iid].append(Member(fx["id"], ext, received, fx["transcript"], reasons, False))
        profiles[iid] = aggregate(incidents[iid], {}, cfg)["profile"]
        latency = (time.perf_counter() - t0) * 1000

        gt = fx["ground_truth"]
        loc = ext["location"]
        rows.append({
            "fixture_id": fx["id"],
            "language_hint": fx["language_hint"],
            "scenario_tags": "|".join(fx["scenario_tags"]),
            "gt_group": gt["incident_group"],
            "pred_incident": iid,
            "dedup_outcome": decision.outcome,
            "suggested_incidents": "|".join(s.incident_id for s in decision.suggestions),
            "gt_place": gt["place_id"],
            "pred_place": loc["place_id"] if loc["status"] == "grounded" else None,
            "pred_location_status": loc["status"],
            "gt_people": gt["people_count"],
            "pred_people": ext["people_affected"]["count"],
            "gt_disaster": gt["disaster_type"],
            "pred_disaster": None if ext["disaster_type"] == "unknown" else ext["disaster_type"],
            "gt_language": gt["language"],
            "pred_language": ext["language"],
            "gt_medical": gt["medical_emergency"],
            "pred_medical": bool(ext["medical_emergency"]),
            "gt_priority": gt["priority"],
            "pred_priority": pr["label"],
            "priority_score": pr["score"],
            "needs_review": bool(reasons) or decision.outcome == "possible_duplicate",
            "review_reasons": "|".join(sorted({r["code"] for r in reasons}
                                              | ({"possible_duplicate"} if decision.outcome == "possible_duplicate" else set()))),
            "transcript_quality": ext["transcript_quality"],
            "latency_ms": round(latency, 3),
            **{f"gt_{g}": bool(gt["vulnerable"][g]) for g in VUL_GROUPS},
            **{f"pred_{g}": ext["vulnerable_people"][g] is not None for g in VUL_GROUPS},
        })
    return rows, {iid: [m.id for m in ms] for iid, ms in incidents.items()}


def _pairs(groups: dict[str, list[str]]) -> set[frozenset]:
    out = set()
    for members in groups.values():
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                out.add(frozenset((a, b)))
    return out


def compute_metrics(rows: list[dict], clusters: dict[str, list[str]]) -> dict:
    n = len(rows)
    loc = _abstain_breakdown(rows, "place")
    ppl = _abstain_breakdown(rows, "people")
    dis = _abstain_breakdown(rows, "disaster")

    vul = {}
    for g in VUL_GROUPS:
        tp = sum(r[f"gt_{g}"] and r[f"pred_{g}"] for r in rows)
        fp = sum((not r[f"gt_{g}"]) and r[f"pred_{g}"] for r in rows)
        fn = sum(r[f"gt_{g}"] and not r[f"pred_{g}"] for r in rows)
        vul[g] = _prf(tp, fp, fn) | {"support": sum(r[f"gt_{g}"] for r in rows)}
    all_tp = sum(v["tp"] for v in vul.values())
    all_fp = sum(v["fp"] for v in vul.values())
    all_fn = sum(v["fn"] for v in vul.values())

    med = _prf(sum(r["gt_medical"] and r["pred_medical"] for r in rows),
               sum((not r["gt_medical"]) and r["pred_medical"] for r in rows),
               sum(r["gt_medical"] and not r["pred_medical"] for r in rows))

    confusion = {gt: {pl: 0 for pl in LABELS} for gt in LABELS}
    for r in rows:
        confusion[r["gt_priority"]][r["pred_priority"]] += 1
    per_class = {lbl: _prf(confusion[lbl][lbl], sum(confusion[g][lbl] for g in LABELS if g != lbl),
                           sum(confusion[lbl][p] for p in LABELS if p != lbl)) for lbl in LABELS}
    rank = prio.LABEL_RANK
    under = [r["fixture_id"] for r in rows if rank[r["pred_priority"]] < rank[r["gt_priority"]]]
    over = [r["fixture_id"] for r in rows if rank[r["pred_priority"]] > rank[r["gt_priority"]]]

    lang_conf: dict[str, dict[str, int]] = {}
    for r in rows:
        lang_conf.setdefault(r["gt_language"], {}).setdefault(r["pred_language"], 0)
        lang_conf[r["gt_language"]][r["pred_language"]] += 1

    gt_groups: dict[str, list[str]] = {}
    for r in rows:
        gt_groups.setdefault(r["gt_group"], []).append(r["fixture_id"])
    gt_pairs, pred_pairs = _pairs(gt_groups), _pairs(clusters)
    dedup = _prf(len(gt_pairs & pred_pairs), len(pred_pairs - gt_pairs), len(gt_pairs - pred_pairs))
    group_of = {r["fixture_id"]: r["gt_group"] for r in rows}
    incident_group = {iid: {group_of[m] for m in ms} for iid, ms in clusters.items()}
    sugg_true = sugg_false = 0
    for r in rows:
        for iid in filter(None, r["suggested_incidents"].split("|")):
            if r["gt_group"] in incident_group[iid]:
                sugg_true += 1
            else:
                sugg_false += 1

    reason_counts: dict[str, int] = {}
    for r in rows:
        for code in filter(None, r["review_reasons"].split("|")):
            reason_counts[code] = reason_counts.get(code, 0) + 1
    lat = [r["latency_ms"] for r in rows]

    return {
        "n_reports": n,
        "location": loc | {"definition": "predicted reference place (only when exactly one reference place is "
                                         "named) vs labelled place; 'correct_unknown' = correctly refused to ground"},
        "people_count": ppl | {"definition": "exact match of the stated count (upper bound for ranges)"},
        "disaster_type": dis | {"definition": "hazard named in the transcript vs scenario hazard; 'missed' means the "
                                              "report never names the hazard"},
        "vulnerable": {"per_group": vul, "micro": _prf(all_tp, all_fp, all_fn)},
        "medical_emergency": med | {"support": sum(r["gt_medical"] for r in rows)},
        "priority": {"accuracy": sum(confusion[g][g] for g in LABELS) / n if n else None,
                     "confusion": confusion, "per_class": per_class, "labels": LABELS,
                     "under_triaged": under, "over_triaged": over},
        "language": {"accuracy": sum(r["gt_language"] == r["pred_language"] for r in rows) / n if n else None,
                     "confusion": lang_conf},
        "deduplication": {
            "pairwise": dedup,
            "definition": "pairs of reports auto-linked into the same incident vs pairs in the same labelled group",
            "gt_incidents": len(gt_groups),
            "predicted_incidents": len(clusters),
            "possible_duplicate_suggestions": {"total": sugg_true + sugg_false, "true_duplicate": sugg_true,
                                               "not_duplicate": sugg_false},
        },
        "human_review": {"rate": sum(r["needs_review"] for r in rows) / n if n else None,
                         "count": sum(r["needs_review"] for r in rows), "reasons": reason_counts},
        "latency_ms": {"mean": statistics.fmean(lat) if lat else None,
                       "p95": sorted(lat)[max(int(len(lat) * 0.95) - 1, 0)] if lat else None,
                       "note": "in-process rule-based pipeline time per report (no network calls)"},
    }


def _cer(ref: str, hyp: str) -> float:
    a = unicodedata.normalize("NFC", ref.lower())
    b = unicodedata.normalize("NFC", hyp.lower())
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] / max(len(a), 1)


def stt_benchmark(run_real: bool) -> dict:
    """Transcription quality is only measured with a REAL provider on the synthetic audio fixtures."""
    from ..providers.base import ProviderError, ProviderUnavailable
    from ..providers.prisma import PrismaSTT

    fixtures = [f for f in load_fixtures()["reports"] if f.get("audio_fixture") and (AUDIO_DIR / f["audio_fixture"]).is_file()]
    out = {"audio_fixtures": len(fixtures), "measured": False, "provider": None, "samples": []}
    if not run_real:
        out["note"] = "Not run. Speech-to-text accuracy is only measured against a real provider (Prisma)."
        return out
    try:
        stt = PrismaSTT()
    except ProviderUnavailable as exc:
        out["note"] = f"Not measured: {exc}. The mock STT is a fixture lookup and has no accuracy to report."
        return out
    out["provider"] = stt.name
    ok = 0
    for f in fixtures:
        try:
            res = stt.transcribe(AUDIO_DIR / f["audio_fixture"], "audio/wav", f["language_hint"])
            cer = _cer(f["transcript"], res.transcript or "")
            ok += 1
            out["samples"].append({"fixture_id": f["id"], "success": True, "cer": cer, "transcript": res.transcript})
        except ProviderError as exc:
            out["samples"].append({"fixture_id": f["id"], "success": False, "error": str(exc)})
    out["measured"] = True
    out["success_rate"] = ok / len(fixtures) if fixtures else None
    cers = [s["cer"] for s in out["samples"] if s.get("success")]
    out["mean_cer"] = statistics.fmean(cers) if cers else None
    out["note"] = ("Reference transcripts are the authored fixture texts that were synthesised to audio with a "
                   "local text-to-speech voice; CER here reflects synthetic audio, not real callers.")
    return out


def run(cfg: dict, run_stt: bool = False) -> dict:
    from ..config import settings as _settings
    # True only when live calls really use Evon. A Gnani key alone does not enable it.
    evon_available = _settings.extraction_provider == "evon" and bool(_settings.evon_api_key or _settings.gnani_api_key)
    extraction_label = (
        "rule-based-v1 (deterministic; used for evaluation reproducibility; live calls use "
        + ("Gnani Evon v3.3)" if evon_available else "the same rule-based extractor)")
    )
    splits = {}
    for name, fixtures in (("development", load_fixtures()["reports"]), ("holdout", load_holdout()["reports"])):
        rows, clusters = replay(cfg, fixtures)
        for r in rows:
            r["split"] = name
        splits[name] = {"description": SPLITS[name], "n_reports": len(rows),
                        "metrics": compute_metrics(rows, clusters), "rows": rows, "clusters": clusters}
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {"label": "SYNTHETIC — fictional scenario, not a real emergency",
                    "version": load_fixtures()["dataset_version"],
                    "n_reports": sum(s["n_reports"] for s in splits.values()), "synthetic": True},
        "providers": {"extraction": extraction_label, "evon_available": evon_available,
                      "transcripts": "authored synthetic text fixtures (not speech-recognition output)"},
        "caveats": [
            "All data is synthetic and was written for this prototype.",
            "The keyword lexicon was developed alongside the development split, so its scores are optimistic. "
            "The small hold-out split is a better (still synthetic, still tiny) indication; neither is evidence "
            "of real-world performance.",
            "Priority labels are the dataset author's judgement under the rubric in synthetic_reports.json, "
            "not operational triage outcomes.",
            "Mock speech-to-text output is never counted as transcription accuracy.",
        ],
        "splits": splits,
        "stt": stt_benchmark(run_stt),
    }


def to_csv(results: dict) -> str:
    rows = [r for split in results["splits"].values() for r in split["rows"]]
    buf = io.StringIO()
    if not rows:
        return ""
    fields = ["split"] + [k for k in rows[0] if k != "split"]
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()
