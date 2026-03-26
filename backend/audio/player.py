from __future__ import annotations

import threading
import time
from pathlib import Path

import sounddevice as sd
import soundfile as sf


class AudioPlayer:
    def __init__(self) -> None:
        self.current_file: str | None = None
        self._lock = threading.Lock()
        self._started_at: float | None = None
        self._duration: float = 0.0
        self.last_error: str | None = None

    def play(self, wav_path: str, volume: float = 1.0) -> str:
        data, sr = sf.read(wav_path, dtype="float32")
        if volume != 1.0:
            data = data * volume
        with self._lock:
            self.current_file = wav_path
            self._started_at = time.monotonic()
            self._duration = len(data) / max(1, sr)
        threading.Thread(target=self._playback_thread, args=(data, sr), daemon=True).start()
        return wav_path

    @staticmethod
    def list_output_devices() -> list[dict[str, str]]:
        devices = []
        for index, device in enumerate(sd.query_devices()):
            max_out = int(device.get("max_output_channels", 0))
            if max_out > 0:
                devices.append({"id": str(index), "name": str(device.get("name", f"Device {index}"))})
        return devices or [{"id": "default", "name": "System Default"}]

    def set_output_device(self, device_id: str) -> None:
        if device_id == "default":
            sd.default.device = None
            return
        try:
            current = sd.default.device
            if isinstance(current, (list, tuple)) and len(current) == 2:
                sd.default.device = (current[0], int(device_id))
            else:
                sd.default.device = (None, int(device_id))
        except Exception as exc:
            self.last_error = str(exc)

    def _playback_thread(self, data, sr) -> None:
        try:
            sd.play(data, sr)
            sd.wait()
        except Exception as exc:
            self.last_error = str(exc)
        finally:
            with self._lock:
                self.current_file = None
                self._started_at = None
                self._duration = 0.0

    def is_playing(self) -> bool:
        with self._lock:
            return self.current_file is not None and Path(self.current_file).exists()

    def progress(self) -> float:
        with self._lock:
            if self.current_file is None or self._started_at is None or self._duration <= 0:
                return 0.0
            return max(0.0, min(1.0, (time.monotonic() - self._started_at) / self._duration))
