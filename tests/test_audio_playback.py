from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from backend.audio.playback import (
    AudioPlaybackSettings,
    apply_audio_effects,
    apply_fade,
    apply_reverb,
    decode_audio_file,
)


def test_apply_fade_shapes_start_and_end() -> None:
    samples = np.ones((100, 2), dtype=np.float32)

    faded = apply_fade(samples, 1000, fade_in_ms=10, fade_out_ms=20)

    assert faded[0, 0] == 0.0
    assert faded[10, 0] == 1.0
    assert faded[-1, 0] == 0.0


def test_apply_reverb_adds_tail() -> None:
    samples = np.zeros((20, 1), dtype=np.float32)
    samples[0, 0] = 1.0

    reverbed = apply_reverb(samples, 1000, delay_ms=5, decay=0.5, mix=0.5)

    assert len(reverbed) > len(samples)
    assert reverbed[0, 0] == 1.0
    assert reverbed[5, 0] > 0.0


def test_apply_audio_effects_limits_peak_after_reverb() -> None:
    samples = np.ones((40, 2), dtype=np.float32)
    settings = AudioPlaybackSettings(
        fade_in_ms=0,
        fade_out_ms=0,
        reverb_enabled=True,
        reverb_delay_ms=1,
        reverb_decay=0.8,
        reverb_mix=1.0,
    )

    processed = apply_audio_effects(samples, 1000, settings)

    assert float(np.max(np.abs(processed))) <= 1.0


def test_decode_wav_file_returns_float_stereo(tmp_path: Path) -> None:
    wav_path = tmp_path / "cue.wav"
    samples = np.array([0, 32767, -32768, 0], dtype="<i2")
    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(44100)
        wav_file.writeframes(samples.tobytes())

    decoded = decode_audio_file(wav_path, sample_rate=44100, channels=2)

    assert decoded.shape == (4, 2)
    assert decoded.dtype == np.float32
    assert decoded[1, 0] > 0.9
    assert decoded[2, 0] <= -1.0
