from __future__ import annotations

import hashlib
import platform
import shutil
import subprocess
import threading
import warnings
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from backend.device_utils import backend_label_for_device, get_torch_device


class QwenCloneTTS:
    def __init__(self, model_path: str, ref_audio_path: str, ref_text_path: str) -> None:
        self.model_path = model_path
        self.ref_audio_path = ref_audio_path
        self.ref_text_path = ref_text_path
        self.loaded = False
        self._model = None
        self._prompt_cache = None
        self._lock = threading.Lock()
        self.available = Path(model_path).exists() and Path(ref_audio_path).exists() and Path(ref_text_path).exists()
        self._prepared_ref_audio: str | None = None
        self._prepared_ref_text: str | None = None
        self.device = get_torch_device()
        self.device_backend = backend_label_for_device(self.device)

    def preload(self) -> None:
        with self._lock:
            self._ensure_model()

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        if not self.available:
            raise FileNotFoundError("TTS model or reference files are missing")
        import torch
        from qwen_tts import Qwen3TTSModel

        kwargs: dict = {}
        if self.device.startswith("cuda"):
            kwargs["device_map"] = "cuda:0"
            kwargs["dtype"] = torch.bfloat16
        elif self.device == "mps":
            kwargs["device_map"] = "cpu"
            kwargs["dtype"] = torch.float32
        else:
            kwargs["device_map"] = "cpu"
            kwargs["dtype"] = torch.float32
        model = Qwen3TTSModel.from_pretrained(self.model_path, **kwargs)
        if self.device == "mps" and hasattr(model, "to"):
            model = model.to("mps")
        prepared_ref = self._prepare_reference_audio()
        ref_text = self._load_reference_text()
        prompt = model.create_voice_clone_prompt(
            ref_audio=prepared_ref,
            ref_text=ref_text,
            x_vector_only_mode=ref_text is None,
        )
        self._model = model
        self._prompt_cache = prompt
        self._prepared_ref_audio = prepared_ref
        self._prepared_ref_text = ref_text
        self.loaded = True

    def synthesize(self, text: str, output_path: str) -> str:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._ensure_model()
            wavs, sr = self._model.generate_voice_clone(
                text=text,
                language="Chinese",
                voice_clone_prompt=self._prompt_cache,
                max_new_tokens=256,
            )
        wav = np.asarray(wavs[0], dtype=np.float32)
        wav = self._polish_waveform(wav, sr)
        if self._looks_broken(wav, sr):
            if platform.system() == "Darwin":
                return self._fallback_say_tts(text, output)
        sf.write(output, wav, sr)
        return str(output)

    def _prepare_reference_audio(self) -> str:
        source = Path(self.ref_audio_path)
        output = self._reference_cache_path(source)
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            return str(output)
        wav, sr = self._load_reference_audio()
        if len(wav) > 24000 * 8:
            start = max(0, (len(wav) - (24000 * 8)) // 2)
            wav = wav[start:start + 24000 * 8]
        wav = self._normalize_waveform(wav)
        sf.write(output, wav, 24000)
        return str(output)

    def _reference_cache_path(self, source: Path) -> Path:
        resolved = source.expanduser().resolve(strict=False)
        stat = resolved.stat() if resolved.exists() else None
        fingerprint = "|".join(
            [
                str(resolved),
                str(stat.st_size if stat else 0),
                str(stat.st_mtime_ns if stat else 0),
            ]
        )
        digest = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:12]
        return Path("tmp") / f"ref_voice_{digest}_24k.wav"

    def _load_reference_audio(self) -> tuple[np.ndarray, int]:
        source = Path(self.ref_audio_path)
        if source.suffix.lower() != ".wav":
            converted = self._convert_reference_audio_with_ffmpeg(source)
            if converted is not None:
                return self._load_audio_with_librosa(str(converted))
        try:
            return self._load_audio_with_librosa(str(source))
        except Exception as exc:
            converted = self._convert_reference_audio_with_ffmpeg(source)
            if converted is None:
                raise RuntimeError(
                    "Failed to decode TTS reference audio. "
                    "On Windows, convert the reference file to WAV or install ffmpeg so .m4a can be decoded."
                ) from exc
            return self._load_audio_with_librosa(str(converted))

    def _load_audio_with_librosa(self, path: str) -> tuple[np.ndarray, int]:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=UserWarning)
            warnings.simplefilter("ignore", category=FutureWarning)
            return librosa.load(path, sr=24000, mono=True)

    def _load_reference_text(self) -> str | None:
        raw = Path(self.ref_text_path).read_text(encoding="utf-8").strip()
        if not raw:
            return None
        text = " ".join(raw.split())
        if len(text) > 180:
            return None
        ascii_ratio = sum(1 for ch in text if ch.isascii()) / max(1, len(text))
        if ascii_ratio > 0.92 and len(text) > 110:
            return None
        return text

    def _convert_reference_audio_with_ffmpeg(self, source: Path) -> Path | None:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            return None
        converted = Path("tmp/ref_voice_source.wav")
        converted.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(source),
                "-ac",
                "1",
                "-ar",
                "24000",
                str(converted),
            ],
            check=True,
            capture_output=True,
        )
        return converted if converted.exists() else None

    def _normalize_waveform(self, wav: np.ndarray) -> np.ndarray:
        wav = np.asarray(wav, dtype=np.float32)
        peak = float(np.max(np.abs(wav))) if wav.size else 0.0
        if peak > 0:
            wav = wav / peak * 0.85
        return wav

    def _polish_waveform(self, wav: np.ndarray, sr: int) -> np.ndarray:
        wav = np.asarray(wav, dtype=np.float32)
        if wav.size == 0:
            return wav

        # Remove DC offset to avoid asymmetric clicks around zero-crossings.
        wav = wav - float(np.mean(wav))

        # Soft limiting before normalization reduces sharp clipped transients.
        wav = np.tanh(wav * 1.2)
        wav = self._suppress_transient_spikes(wav)
        wav = self._normalize_waveform(wav)

        # Short fade-in/out prevents hard edge pops at playback boundaries.
        fade_samples = min(max(1, int(sr * 0.012)), wav.size // 2)
        if fade_samples > 0:
            fade_in = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)
            fade_out = np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)
            wav[:fade_samples] *= fade_in
            wav[-fade_samples:] *= fade_out
        return wav

    def _suppress_transient_spikes(self, wav: np.ndarray) -> np.ndarray:
        if wav.size < 5:
            return wav
        repaired = wav.copy()
        for _ in range(2):
            diffs = np.diff(repaired)
            median_abs = max(1e-5, float(np.median(np.abs(diffs))))
            jump_threshold = max(0.12, median_abs * 10.0)
            dev_scale = max(0.08, median_abs * 8.0)

            # Replace isolated impulse-like samples with linear interpolation.
            for idx in range(2, repaired.size - 2):
                left = repaired[idx] - repaired[idx - 1]
                right = repaired[idx + 1] - repaired[idx]
                neighborhood = np.array(
                    [repaired[idx - 2], repaired[idx - 1], repaired[idx + 1], repaired[idx + 2]],
                    dtype=np.float32,
                )
                local_median = float(np.median(neighborhood))
                local_mad = max(1e-5, float(np.median(np.abs(neighborhood - local_median))))
                if abs(left) < jump_threshold or abs(right) < jump_threshold:
                    continue
                if left * right >= 0 and abs(repaired[idx] - local_median) < max(dev_scale, local_mad * 6.0):
                    continue
                repaired[idx] = (repaired[idx - 1] + repaired[idx + 1]) * 0.5

            # Repair short two-sample bursts that still sound like clicks.
            for idx in range(2, repaired.size - 3):
                pair = repaired[idx:idx + 2]
                context = np.array(
                    [repaired[idx - 2], repaired[idx - 1], repaired[idx + 2], repaired[idx + 3]],
                    dtype=np.float32,
                )
                local_median = float(np.median(context))
                local_mad = max(1e-5, float(np.median(np.abs(context - local_median))))
                if (
                    abs(repaired[idx] - repaired[idx - 1]) > jump_threshold
                    and abs(repaired[idx + 2] - repaired[idx + 1]) > jump_threshold
                    and np.max(np.abs(pair - local_median)) > max(dev_scale, local_mad * 6.0)
                ):
                    repaired[idx] = repaired[idx - 1] * 0.67 + repaired[idx + 2] * 0.33
                    repaired[idx + 1] = repaired[idx - 1] * 0.33 + repaired[idx + 2] * 0.67
        return repaired

    def _looks_broken(self, wav: np.ndarray, sr: int) -> bool:
        duration = len(wav) / max(1, sr)
        mean_abs = float(np.mean(np.abs(wav))) if wav.size else 0.0
        peak = float(np.max(np.abs(wav))) if wav.size else 0.0
        return duration < 0.8 or mean_abs < 0.01 or peak < 0.08

    def _fallback_say_tts(self, text: str, output: Path) -> str:
        aiff_path = output.with_suffix(".aiff")
        subprocess.run(
            ["say", "-v", "Tingting", "-o", str(aiff_path), text],
            check=True,
            capture_output=True,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=UserWarning)
            warnings.simplefilter("ignore", category=FutureWarning)
            wav, sr = librosa.load(str(aiff_path), sr=24000, mono=True)
        wav = self._normalize_waveform(wav)
        sf.write(output, wav, sr)
        aiff_path.unlink(missing_ok=True)
        return str(output)
