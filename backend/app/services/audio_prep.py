"""Audio preprocessing step inserted before Prisma STT.

Applies: stereo → mono, spectral noise gate (noisereduce), RMS loudness normalisation to -20 dBFS.
Returns a new .prep.wav file alongside the original; the caller passes this to stt.transcribe().

Requires: numpy, scipy, noisereduce, soundfile (all listed in requirements.txt).
Enabled by setting AUDIO_PREPROCESSING=true.
"""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

_TARGET_DBFS = -20.0


def preprocess_audio(src_path: Path) -> Path:
    """Return path to a preprocessed 16kHz mono WAV written next to the original.

    If preprocessing fails for any reason the original path is returned unchanged
    so the pipeline can still attempt transcription.
    """
    try:
        import numpy as np
        import soundfile as sf
        import noisereduce as nr
    except ImportError as exc:
        log.warning("audio_prep: required library not installed (%s); skipping", exc)
        return src_path

    out_path = src_path.with_suffix(".prep.wav")
    try:
        data, sr = sf.read(str(src_path), always_2d=False)
        if data.ndim > 1:
            data = data.mean(axis=1)
        data = data.astype("float32")
        data = nr.reduce_noise(y=data, sr=sr)
        rms = float(np.sqrt(np.mean(data ** 2)))
        if rms > 1e-9:
            target_rms = 10 ** (_TARGET_DBFS / 20.0)
            data = np.clip(data * (target_rms / rms), -1.0, 1.0)
        sf.write(str(out_path), data, sr, subtype="PCM_16")
        log.debug("audio_prep: wrote %s (sr=%d)", out_path.name, sr)
        return out_path
    except Exception as exc:
        log.warning("audio_prep: preprocessing failed (%s); using original file", exc)
        return src_path
