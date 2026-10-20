"""Audio preprocessing — unit tests with synthetic in-memory WAV data."""
from __future__ import annotations

import io
import struct
import wave
from pathlib import Path

import pytest


def _make_wav(tmp_path: Path, duration_s: float = 1.0, sample_rate: int = 16000,
              channels: int = 1, noise_amplitude: float = 0.1) -> Path:
    """Write a synthetic sine + noise WAV for preprocessing tests."""
    try:
        import numpy as np
    except ImportError:
        pytest.skip("numpy not installed")

    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    signal = np.sin(2 * np.pi * 440 * t) * 0.5
    rng = np.random.default_rng(42)
    signal += rng.normal(0, noise_amplitude, len(t))
    signal = np.clip(signal, -1.0, 1.0)
    pcm = (signal * 32767).astype(np.int16)

    p = tmp_path / "test_input.wav"
    with wave.open(str(p), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return p


def test_preprocess_audio_produces_valid_wav(tmp_path):
    pytest.importorskip("soundfile")
    pytest.importorskip("noisereduce")

    src = _make_wav(tmp_path)
    from app.services.audio_prep import preprocess_audio

    out = preprocess_audio(src)
    assert out.exists()
    assert out.suffix == ".wav"

    with wave.open(str(out), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getnframes() > 0


def test_preprocess_audio_stereo_converted_to_mono(tmp_path):
    pytest.importorskip("soundfile")
    pytest.importorskip("noisereduce")

    src = _make_wav(tmp_path, channels=2)
    from app.services.audio_prep import preprocess_audio

    out = preprocess_audio(src)
    with wave.open(str(out), "rb") as wf:
        assert wf.getnchannels() == 1


def test_preprocess_audio_silence_does_not_raise(tmp_path):
    pytest.importorskip("soundfile")
    pytest.importorskip("noisereduce")

    try:
        import numpy as np
        import soundfile as sf
    except ImportError:
        pytest.skip("required libs not installed")

    silent = np.zeros(16000, dtype=np.float32)
    src = tmp_path / "silence.wav"
    sf.write(str(src), silent, 16000, subtype="PCM_16")

    from app.services.audio_prep import preprocess_audio
    out = preprocess_audio(src)
    assert out.suffix == ".wav"


def test_preprocess_audio_falls_back_on_bad_file(tmp_path):
    """A corrupt file must not propagate an exception; original path returned."""
    corrupt = tmp_path / "bad.wav"
    corrupt.write_bytes(b"not a wav file at all")

    from app.services.audio_prep import preprocess_audio
    result = preprocess_audio(corrupt)
    assert result == corrupt
