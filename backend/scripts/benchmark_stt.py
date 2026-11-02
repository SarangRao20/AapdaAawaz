"""Measure Prisma on synthetic disaster reports. Everything here is synthetic, as the contest rules require.

Timbre speaks the Hindi, Marathi and Hinglish reports, and the bundled clips add English. Each clip can
be degraded to phone quality and mixed with noise, then Prisma transcribes it and the normal extraction
runs on the result. The score is the outcome that matters to a dispatcher: did the village, the disaster
type and the head count come out right?

Answers are cached in var/, so re-running spends no credits unless a clip or setting changed.

    python scripts/benchmark_stt.py --conditions clean --variants v2.5 v3 v3-codemix v3-hints
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.providers.base import ProviderError  # noqa: E402
from app.providers.prisma import PrismaSTT  # noqa: E402
from app.providers.timbre import TimbreTTS  # noqa: E402
from app.services.audio_prep import preprocess_audio  # noqa: E402
from app.services.extraction import extract  # noqa: E402
from app.services.stt_hints import disaster_keyterms  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"
CLIPS = DATA / "audio" / "benchmark"
CACHE = settings.var_dir / "benchmark_cache"
RATE = 16000
TIMBRE_CLIPS_PER_LANGUAGE = {"hi": 3, "mr": 3, "mixed": 3}

VARIANTS = {
    "v2.5": dict(model="prisma-v2.5", fmt="verbatim", keyterms=()),
    "v3": dict(model="prisma-v3.0", fmt="verbatim", keyterms=()),
    "v3-codemix": dict(model="prisma-v3.0", fmt="codemix", keyterms=()),
    "v3-hints": dict(model="prisma-v3.0", fmt="verbatim", keyterms=None),
    "v3-codemix-hints": dict(model="prisma-v3.0", fmt="codemix", keyterms=None),
}


@dataclass
class Clip:
    report_id: str
    language: str
    path: Path
    truth: dict


def _report_is_usable(report: dict) -> bool:
    """A clip counts only if extraction gets every field right from the written text.

    That leaves speech recognition as the only thing being measured. It removes reports whose label comes
    from their incident group rather than their words, and ones with markers like [noise] a voice can't say.
    The rule runs before any audio is heard, so it can't favour a result.
    """
    truth = report.get("ground_truth") or {}
    text = report["transcript"]
    if not (truth.get("place_id") and truth.get("disaster_type")) or len(text) >= 260 or "[" in text:
        return False
    return all(_marks(extract(text, report["language_hint"]).model_dump(), truth).values())


def load_clips() -> list[Clip]:
    reports = json.loads((DATA / "synthetic_reports.json").read_text(encoding="utf-8"))["reports"]
    clips = [Clip(r["id"], r["language_hint"], DATA / "audio" / r["audio_fixture"], r["ground_truth"])
             for r in reports if r.get("audio_fixture") and (DATA / "audio" / r["audio_fixture"]).is_file()
             and _report_is_usable(r)]
    CLIPS.mkdir(parents=True, exist_ok=True)
    tts = None
    for language, count in TIMBRE_CLIPS_PER_LANGUAGE.items():
        chosen = [r for r in reports if r["language_hint"] == language and not r.get("audio_fixture")
                  and _report_is_usable(r)][:count]
        for report in chosen:
            path = CLIPS / f"{report['id'].lower()}.wav"
            if not path.is_file():
                tts = tts or TimbreTTS()
                path.write_bytes(tts.synthesize(report["transcript"], language).audio)
            clips.append(Clip(report["id"], language, path, report["ground_truth"]))
    return clips


def read_mono(path: Path) -> np.ndarray:
    # Timbre's WAV header carries a placeholder length, which soundfile reads up to the real end of the file.
    samples, rate = sf.read(path, dtype="float32", always_2d=True)
    mono = samples[:, 0]
    return mono if rate == RATE else resample_poly(mono, RATE, rate).astype(np.float32)


def phone_quality(x: np.ndarray) -> np.ndarray:
    """Down to 8 kHz and through mu-law, as on a voice call."""
    narrow = np.clip(resample_poly(x, 1, 2), -1, 1)
    mu = 255.0
    coded = np.round(np.sign(narrow) * np.log1p(mu * np.abs(narrow)) / np.log1p(mu) * 127) / 127
    decoded = np.sign(coded) * (np.power(1 + mu, np.abs(coded)) - 1) / mu
    return resample_poly(decoded, 2, 1).astype(np.float32)


def add_noise(x: np.ndarray, snr_db: float, seed: int) -> np.ndarray:
    """Pink-ish noise, closer to wind, rain and crowds than pure hiss. Seeded so every run hears the same."""
    rng = np.random.default_rng(seed)
    white = rng.standard_normal(len(x))
    spectrum = np.fft.rfft(white)
    spectrum[1:] /= np.sqrt(np.arange(1, len(spectrum)))
    noise = np.fft.irfft(spectrum, n=len(x))
    signal_power = np.mean(x ** 2) or 1e-9
    noise *= np.sqrt(signal_power / (10 ** (snr_db / 10)) / (np.mean(noise ** 2) or 1e-9))
    return np.clip(x + noise, -1, 1).astype(np.float32)


def degrade(x: np.ndarray, condition: str, seed: int) -> np.ndarray:
    if condition == "clean":
        return x
    if condition == "phone":
        return phone_quality(x)
    if condition.startswith("phone+noise"):
        return add_noise(phone_quality(x), float(condition.removeprefix("phone+noise")), seed)
    raise ValueError(f"unknown condition {condition}")


def transcribe(clip: Clip, condition: str, variant: str, denoise: bool) -> str | None:
    settings_for = VARIANTS[variant]
    keyterms = settings_for["keyterms"]
    keyterms = disaster_keyterms() if keyterms is None else keyterms
    samples = degrade(read_mono(clip.path), condition, seed=int(hashlib.sha256(clip.report_id.encode()).hexdigest()[:8], 16))
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "clip.wav"
        sf.write(wav, samples, RATE, subtype="PCM_16")
        if denoise:
            wav = preprocess_audio(wav) or wav
        audio = wav.read_bytes()
        key = hashlib.sha256(audio + json.dumps([settings_for["model"], settings_for["fmt"], list(keyterms),
                                                 clip.language]).encode()).hexdigest()
        cached = CACHE / f"{key}.json"
        if cached.is_file():
            return json.loads(cached.read_text(encoding="utf-8"))["transcript"]
        result = PrismaSTT(model=settings_for["model"], fmt=settings_for["fmt"], keyterms=keyterms).transcribe(
            wav, "audio/wav", clip.language)
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps({"transcript": result.transcript}, ensure_ascii=False), encoding="utf-8")
    return result.transcript


def _marks(found: dict, truth: dict) -> dict:
    place = (found.get("location") or {}).get("place_id")
    people = (found.get("people_affected") or {}).get("count")
    return {"place": place == truth.get("place_id"), "disaster": found.get("disaster_type") == truth.get("disaster_type"),
            "people": people == truth.get("people_count")}


def score(clip: Clip, transcript: str) -> dict:
    return _marks(extract(transcript or "", clip.language).model_dump(), clip.truth)


def run(conditions: list[str], variants: list[str], denoise_options: list[bool], show: bool) -> list[dict]:
    clips = load_clips()
    counts = {language: sum(c.language == language for c in clips) for language in {c.language for c in clips}}
    print(f"{len(clips)} clips: {counts}\n")
    print(f"{'condition':18}{'variant':19}{'denoise':9}{'village':>9}{'disaster':>10}{'people':>8}{'all 3':>8}")
    rows = []
    for condition in conditions:
        for variant in variants:
            for denoise in denoise_options:
                marks, by_language, failed = [], {}, 0
                for clip in clips:
                    try:
                        transcript = transcribe(clip, condition, variant, denoise)
                    except ProviderError as exc:
                        failed += 1
                        print(f"  {clip.report_id} failed: {exc}")
                        if exc.status_code == 403:
                            raise SystemExit("Stopping: Gnani refused the key or the credits have run out.") from exc
                        continue
                    mark = score(clip, transcript)
                    marks.append(mark)
                    by_language.setdefault(clip.language, []).append(all(mark.values()))
                    if show:
                        print(f"  {clip.report_id} {clip.language:5} {mark} {str(transcript)[:110]}")
                n = len(marks) or 1
                row = {"condition": condition, "variant": variant, "denoise": denoise, "clips": len(marks), "failed": failed,
                       "village": sum(m["place"] for m in marks), "disaster": sum(m["disaster"] for m in marks),
                       "people": sum(m["people"] for m in marks), "all": sum(all(m.values()) for m in marks),
                       "all_by_language": {k: f"{sum(v)}/{len(v)}" for k, v in sorted(by_language.items())}}
                rows.append(row)
                print(f"{condition:18}{variant:19}{'yes' if denoise else 'no':9}{row['village']:>6}/{n}{row['disaster']:>7}/{n}"
                      f"{row['people']:>5}/{n}{row['all']:>5}/{n}  {row['all_by_language']}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conditions", nargs="+", default=["clean"])
    parser.add_argument("--variants", nargs="+", default=["v2.5", "v3-hints"], choices=sorted(VARIANTS))
    parser.add_argument("--denoise", action="store_true", help="also run each case through the noise gate")
    parser.add_argument("--show", action="store_true", help="print each transcript")
    parser.add_argument("--out", type=Path, help="write the results as JSON")
    args = parser.parse_args()
    rows = run(args.conditions, args.variants, [False, True] if args.denoise else [False], args.show)
    if args.out:
        args.out.write_text(json.dumps(rows, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
