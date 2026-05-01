from __future__ import annotations

import shutil
import subprocess
import threading
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SUPPORTED_AUDIO_EXTENSIONS = (".wav", ".mp3", ".m4a", ".ogg")
DEFAULT_SAMPLE_RATE = 44100
DEFAULT_CHANNELS = 2


@dataclass(frozen=True)
class AudioPlaybackSettings:
    fade_in_ms: int = 80
    fade_out_ms: int = 180
    reverb_enabled: bool = True
    reverb_delay_ms: int = 70
    reverb_decay: float = 0.28
    reverb_mix: float = 0.22
    sample_rate: int = DEFAULT_SAMPLE_RATE
    channels: int = DEFAULT_CHANNELS


@dataclass
class _QueuedAudio:
    samples: np.ndarray
    position: int
    done: threading.Event


class IndependentAudioOutput:
    def __init__(self, *, sample_rate: int = DEFAULT_SAMPLE_RATE, channels: int = DEFAULT_CHANNELS) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self._lock = threading.RLock()
        self._tracks: list[_QueuedAudio] = []
        self._stream = None

    def play(self, samples: np.ndarray) -> threading.Event:
        done = threading.Event()
        samples = _fit_channels(samples, self.channels).astype(np.float32, copy=False)
        if not len(samples):
            done.set()
            return done
        self._ensure_stream()
        with self._lock:
            self._tracks.append(_QueuedAudio(samples=samples, position=0, done=done))
        return done

    def close(self) -> None:
        with self._lock:
            stream = self._stream
            self._stream = None
            tracks = self._tracks
            self._tracks = []
        for track in tracks:
            track.done.set()
        if stream is not None:
            stream.stop()
            stream.close()

    def _ensure_stream(self) -> None:
        with self._lock:
            if self._stream is not None:
                return
            try:
                import sounddevice as sd
            except Exception as exc:
                raise RuntimeError("sounddevice is required for independent audio playback") from exc
            self._stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
                callback=self._callback,
            )
            self._stream.start()

    def _callback(self, outdata, frames, _time_info, _status) -> None:
        outdata.fill(0)
        finished: list[threading.Event] = []
        with self._lock:
            active: list[_QueuedAudio] = []
            for track in self._tracks:
                remaining = len(track.samples) - track.position
                if remaining <= 0:
                    finished.append(track.done)
                    continue
                count = min(frames, remaining)
                outdata[:count] += track.samples[track.position : track.position + count]
                track.position += count
                if track.position >= len(track.samples):
                    finished.append(track.done)
                else:
                    active.append(track)
            self._tracks = active
        np.clip(outdata, -1.0, 1.0, out=outdata)
        for done in finished:
            done.set()


_DEFAULT_OUTPUT = IndependentAudioOutput()


def play_audio_file_blocking(
    path: Path,
    settings: AudioPlaybackSettings | None = None,
    output: IndependentAudioOutput | None = None,
) -> None:
    playback_settings = settings or AudioPlaybackSettings()
    samples = decode_audio_file(
        path,
        sample_rate=playback_settings.sample_rate,
        channels=playback_settings.channels,
    )
    samples = apply_audio_effects(samples, playback_settings.sample_rate, playback_settings)
    done = (output or _DEFAULT_OUTPUT).play(samples)
    done.wait()


def decode_audio_file(path: Path, *, sample_rate: int = DEFAULT_SAMPLE_RATE, channels: int = DEFAULT_CHANNELS) -> np.ndarray:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_AUDIO_EXTENSIONS:
        raise RuntimeError(f"Unsupported audio extension: {suffix}")
    if suffix == ".wav":
        try:
            return _decode_wav_file(path, sample_rate=sample_rate, channels=channels)
        except (wave.Error, ValueError, OSError):
            pass
    return _decode_with_ffmpeg(path, sample_rate=sample_rate, channels=channels)


def apply_audio_effects(samples: np.ndarray, sample_rate: int, settings: AudioPlaybackSettings) -> np.ndarray:
    processed = _as_float32_audio(samples)
    if settings.reverb_enabled and settings.reverb_decay > 0 and settings.reverb_mix > 0:
        processed = apply_reverb(
            processed,
            sample_rate,
            delay_ms=settings.reverb_delay_ms,
            decay=settings.reverb_decay,
            mix=settings.reverb_mix,
        )
    processed = apply_fade(processed, sample_rate, fade_in_ms=settings.fade_in_ms, fade_out_ms=settings.fade_out_ms)
    return _limit_audio(processed)


def apply_fade(samples: np.ndarray, sample_rate: int, *, fade_in_ms: int, fade_out_ms: int) -> np.ndarray:
    faded = _as_float32_audio(samples).copy()
    frame_count = len(faded)
    if frame_count == 0:
        return faded
    fade_in_frames = min(frame_count, max(0, int(sample_rate * fade_in_ms / 1000)))
    fade_out_frames = min(frame_count, max(0, int(sample_rate * fade_out_ms / 1000)))
    if fade_in_frames:
        faded[:fade_in_frames] *= np.linspace(0.0, 1.0, fade_in_frames, dtype=np.float32)[:, None]
    if fade_out_frames:
        faded[-fade_out_frames:] *= np.linspace(1.0, 0.0, fade_out_frames, dtype=np.float32)[:, None]
    return faded


def apply_reverb(
    samples: np.ndarray,
    sample_rate: int,
    *,
    delay_ms: int,
    decay: float,
    mix: float,
) -> np.ndarray:
    dry = _as_float32_audio(samples)
    delay_frames = max(1, int(sample_rate * max(1, delay_ms) / 1000))
    decay = min(max(decay, 0.0), 0.95)
    mix = min(max(mix, 0.0), 1.0)
    echo_count = 0
    gain = decay
    while gain >= 0.02 and echo_count < 10:
        echo_count += 1
        gain *= decay
    if echo_count == 0:
        return dry.copy()

    output = np.zeros((len(dry) + (delay_frames * echo_count), dry.shape[1]), dtype=np.float32)
    output[: len(dry)] += dry
    for echo_index in range(1, echo_count + 1):
        start = delay_frames * echo_index
        end = start + len(dry)
        output[start:end] += dry * ((decay ** echo_index) * mix)
    return output


def _decode_wav_file(path: Path, *, sample_rate: int, channels: int) -> np.ndarray:
    with wave.open(str(path), "rb") as wav_file:
        source_rate = wav_file.getframerate()
        source_channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        raw = wav_file.readframes(wav_file.getnframes())
    if sample_width == 1:
        audio = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sample_width == 2:
        audio = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sample_width == 4:
        audio = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")
    audio = audio.reshape(-1, source_channels)
    audio = _fit_channels(audio, channels)
    if source_rate != sample_rate:
        audio = _resample_linear(audio, source_rate, sample_rate)
    return audio.astype(np.float32, copy=False)


def _decode_with_ffmpeg(path: Path, *, sample_rate: int, channels: int) -> np.ndarray:
    ffmpeg = _ffmpeg_executable()
    if ffmpeg is None:
        raise RuntimeError("ffmpeg or imageio-ffmpeg is required for compressed audio playback")
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-f",
        "f32le",
        "-acodec",
        "pcm_f32le",
        "-ac",
        str(channels),
        "-ar",
        str(sample_rate),
        "-",
    ]
    process = subprocess.run(command, capture_output=True, check=False)
    if process.returncode != 0:
        detail = process.stderr.decode(errors="ignore").strip() or f"exit {process.returncode}"
        raise RuntimeError(f"ffmpeg decode failed: {detail}")
    audio = np.frombuffer(process.stdout, dtype="<f4")
    if len(audio) % channels:
        audio = audio[: len(audio) - (len(audio) % channels)]
    return audio.reshape(-1, channels).astype(np.float32, copy=False)


def _ffmpeg_executable() -> str | None:
    resolved = shutil.which("ffmpeg")
    if resolved is not None:
        return resolved
    try:
        import imageio_ffmpeg
    except Exception:
        return None
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _fit_channels(samples: np.ndarray, channels: int) -> np.ndarray:
    audio = _as_float32_audio(samples)
    if audio.shape[1] == channels:
        return audio
    if channels == 1:
        return audio.mean(axis=1, keepdims=True)
    if audio.shape[1] == 1:
        return np.repeat(audio, channels, axis=1)
    if audio.shape[1] > channels:
        return audio[:, :channels]
    repeats = channels - audio.shape[1]
    return np.concatenate([audio, np.repeat(audio[:, -1:], repeats, axis=1)], axis=1)


def _resample_linear(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if len(samples) == 0 or source_rate == target_rate:
        return samples
    duration = len(samples) / source_rate
    target_length = max(1, int(round(duration * target_rate)))
    source_x = np.linspace(0.0, duration, len(samples), endpoint=False)
    target_x = np.linspace(0.0, duration, target_length, endpoint=False)
    channels = [
        np.interp(target_x, source_x, samples[:, channel]).astype(np.float32)
        for channel in range(samples.shape[1])
    ]
    return np.stack(channels, axis=1)


def _as_float32_audio(samples: np.ndarray) -> np.ndarray:
    audio = np.asarray(samples, dtype=np.float32)
    if audio.ndim == 1:
        return audio.reshape(-1, 1)
    if audio.ndim != 2:
        raise ValueError("audio samples must be a 1D or 2D array")
    return audio


def _limit_audio(samples: np.ndarray) -> np.ndarray:
    limited = _as_float32_audio(samples).astype(np.float32, copy=True)
    peak = float(np.max(np.abs(limited))) if len(limited) else 0.0
    if peak > 1.0:
        limited /= peak
    return np.clip(limited, -1.0, 1.0)
