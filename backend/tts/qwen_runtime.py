from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from backend.device_utils import backend_label_for_device, get_tts_device
from backend.tts.semantic_runtime import cleanup_torch_memory
from backend.tts.model_profiles import resolve_tts_model_profile


def _ensure_wav_ref(ref_audio: Path) -> Path:
    suffix = ref_audio.suffix.lower()
    if suffix not in {".m4a", ".aac", ".mp4", ".mp3"}:
        return ref_audio
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return ref_audio
    output = Path("tmp") / "qwen_ref_voice.wav"
    output.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(ref_audio),
            "-ar",
            "24000",
            "-ac",
            "1",
            "-f",
            "wav",
            str(output),
        ],
        capture_output=True,
        check=False,
        timeout=120,
    )
    if result.returncode == 0 and output.exists():
        return output
    return ref_audio


class QwenVoiceCloneTTS:
    def __init__(
        self,
        model_path: str,
        ref_audio_path: str,
        ref_text_path: str,
        clone_voice_enabled: bool = True,
        device_mode: str = "auto",
    ) -> None:
        self.model_path = model_path
        self.ref_audio_path = ref_audio_path
        self.ref_text_path = ref_text_path
        self.clone_voice_enabled = clone_voice_enabled
        self.semantic_dispatch_mode = "single"
        self.model_profile = resolve_tts_model_profile(model_path)
        self.loaded = False
        self._model = None
        self._clone_prompt = None
        self.device = get_tts_device(device_mode)
        self.device_backend = backend_label_for_device(self.device)

    @property
    def available(self) -> bool:
        model_ready = Path(self.model_path).exists()
        if not self.clone_voice_enabled:
            return model_ready
        return model_ready and Path(self.ref_audio_path).exists() and Path(self.ref_text_path).exists()

    def preload(self) -> None:
        self._ensure_model()

    def synthesize(self, text: str, output_path: str, *, request_overrides: dict | None = None) -> str:
        self._ensure_model()
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        kwargs = dict(request_overrides or {})
        if self._clone_prompt is not None:
            wavs, sr = self._model.generate_voice_clone(
                text=text,
                language="Chinese",
                voice_clone_prompt=self._clone_prompt,
                **kwargs,
            )
        else:
            ref_audio = str(_ensure_wav_ref(Path(self.ref_audio_path)))
            ref_text = Path(self.ref_text_path).read_text(encoding="utf-8").strip() or None
            wavs, sr = self._model.generate_voice_clone(
                text=text,
                language="Chinese",
                ref_audio=ref_audio,
                ref_text=ref_text,
                x_vector_only_mode=not bool(ref_text),
                **kwargs,
            )
        raw = wavs[0] if isinstance(wavs, (list, tuple)) else wavs
        if hasattr(raw, "detach"):
            raw = raw.detach().cpu().float().numpy()
        audio = np.asarray(raw, dtype=np.float32)
        if audio.ndim > 1:
            audio = np.mean(audio, axis=-1) if audio.shape[-1] <= 4 else audio.reshape(-1)
        else:
            audio = np.squeeze(audio)
        audio = np.clip(audio.astype(np.float32, copy=False), -1.0, 1.0)
        sample_rate = int(np.asarray(sr).reshape(-1)[0])
        sf.write(str(output), audio, sample_rate)
        return str(output)

    def set_reference_paths(self, ref_audio_path: str, ref_text_path: str) -> None:
        self.ref_audio_path = ref_audio_path
        self.ref_text_path = ref_text_path
        self._clone_prompt = None

    def format_emotion_text(self, text: str, emotion: str) -> str:
        return text

    @property
    def emotion_tags(self) -> tuple[str, ...]:
        return ()

    def unload(self) -> None:
        model = self._model
        self._clone_prompt = None
        self._model = None
        self.loaded = False
        if model is not None and hasattr(model, "to"):
            try:
                model.to("cpu")
            except Exception:
                pass
        del model
        cleanup_torch_memory()

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        if not self.available:
            raise FileNotFoundError("Qwen TTS model or reference files are missing")
        try:
            import torch
            from qwen_tts import Qwen3TTSModel
        except ImportError as exc:
            raise RuntimeError("qwen-tts is required for Qwen3-TTS runtime. Run `uv sync`.") from exc

        for device_map, dtype in self._load_attempts(torch):
            try:
                self._model = Qwen3TTSModel.from_pretrained(
                    self.model_path,
                    device_map=device_map,
                    dtype=dtype,
                    attn_implementation="sdpa",
                )
                break
            except Exception:
                self._model = None
        if self._model is None:
            raise RuntimeError("Failed to load Qwen3-TTS on any available device")

        if self.clone_voice_enabled:
            ref_audio = str(_ensure_wav_ref(Path(self.ref_audio_path)))
            ref_text = Path(self.ref_text_path).read_text(encoding="utf-8").strip() or None
            self._clone_prompt = self._model.create_voice_clone_prompt(
                ref_audio=ref_audio,
                ref_text=ref_text,
                x_vector_only_mode=not bool(ref_text),
            )
        self.loaded = True

    def _load_attempts(self, torch) -> list[tuple[str | dict[str, str], object]]:
        if self.device.startswith("cuda"):
            return [("cuda:0", torch.float16), ("cpu", torch.float32)]
        if self.device == "mps":
            return [("mps", torch.float32), ({"": "mps"}, torch.float32), ("cpu", torch.float32)]
        return [("cpu", torch.float32)]
