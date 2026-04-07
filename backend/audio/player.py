from __future__ import annotations

import platform
import shutil
import subprocess
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
        self._output_device_id: str = "default"
        self._native_process: subprocess.Popen[str] | None = None
        self.last_error: str | None = None

    def play(self, wav_path: str, volume: float = 1.0) -> str:
        self.last_error = None
        self._stop_current_playback()
        if self._use_native_default_player():
            info = sf.info(wav_path)
            with self._lock:
                self.current_file = wav_path
                self._started_at = time.monotonic()
                self._duration = float(info.frames) / max(1, int(info.samplerate))
            threading.Thread(target=self._native_playback_thread, args=(wav_path, volume), daemon=True).start()
            return wav_path

        data, sr = sf.read(wav_path, dtype="float32")
        if volume != 1.0:
            data = data * volume
        with self._lock:
            self.current_file = wav_path
            self._started_at = time.monotonic()
            self._duration = len(data) / max(1, sr)
        threading.Thread(target=self._sounddevice_playback_thread, args=(data, sr), daemon=True).start()
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
        self._output_device_id = device_id
        try:
            current = sd.default.device
            input_device = current[0] if isinstance(current, (list, tuple)) and len(current) == 2 else None
            target_output = self._resolve_output_device(device_id)
            sd.default.device = (input_device, target_output)
        except Exception as exc:
            self.last_error = str(exc)

    def _sounddevice_playback_thread(self, data, sr) -> None:
        try:
            sd.play(data, sr)
            sd.wait()
        except Exception as exc:
            self.last_error = str(exc)
        finally:
            sd.stop(ignore_errors=True)
            self._clear_playback_state()

    def _native_playback_thread(self, wav_path: str, volume: float) -> None:
        try:
            system = platform.system()
            if system == "Darwin":
                command = ["afplay"]
                if 0.0 <= volume <= 1.0:
                    command.extend(["-v", f"{volume:.3f}"])
                command.append(wav_path)
                process = subprocess.Popen(command)
                with self._lock:
                    self._native_process = process
                process.wait()
                if process.returncode != 0:
                    raise RuntimeError(f"afplay exited with code {process.returncode}")
                return
            if system == "Windows":
                import winsound

                winsound.PlaySound(wav_path, winsound.SND_FILENAME)
                return
            raise RuntimeError("Native default playback is not supported on this platform")
        except Exception as exc:
            self.last_error = str(exc)
        finally:
            with self._lock:
                self._native_process = None
            self._clear_playback_state()

    def is_playing(self) -> bool:
        with self._lock:
            return self.current_file is not None and Path(self.current_file).exists()

    def progress(self) -> float:
        with self._lock:
            if self.current_file is None or self._started_at is None or self._duration <= 0:
                return 0.0
            return max(0.0, min(1.0, (time.monotonic() - self._started_at) / self._duration))

    def _use_native_default_player(self) -> bool:
        if self._output_device_id != "default":
            return False
        system = platform.system()
        if system == "Darwin":
            return shutil.which("afplay") is not None
        return system == "Windows"

    def _stop_current_playback(self) -> None:
        try:
            sd.stop(ignore_errors=True)
        except Exception:
            pass
        with self._lock:
            process = self._native_process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
        self._clear_playback_state()

    def _clear_playback_state(self) -> None:
        with self._lock:
            self.current_file = None
            self._started_at = None
            self._duration = 0.0

    def _resolve_output_device(self, device_id: str) -> int | None:
        if device_id != "default":
            return int(device_id)

        default_output = sd.query_devices(kind="output")
        default_index = int(default_output["index"])
        if not self._looks_virtual_output(str(default_output.get("name", ""))):
            return default_index

        devices = self.list_output_devices()
        preferred = self._preferred_physical_output(devices)
        return int(preferred["id"]) if preferred else default_index

    def _preferred_physical_output(self, devices: list[dict[str, str]]) -> dict[str, str] | None:
        ranked: list[dict[str, str]] = []
        for device in devices:
            name = device["name"]
            if self._looks_virtual_output(name):
                continue
            ranked.append(device)
        if not ranked:
            return None

        priority_tokens = ("speaker", "speakers", "headphone", "headphones", "airpods", "耳機", "喇叭")
        if platform.system() == "Darwin":
            priority_tokens = priority_tokens + ("macbook",)

        def score(item: dict[str, str]) -> tuple[int, str]:
            lowered = item["name"].lower()
            preferred = any(token in lowered for token in priority_tokens)
            return (0 if preferred else 1, lowered)

        ranked.sort(key=score)
        return ranked[0]

    @staticmethod
    def _looks_virtual_output(name: str) -> bool:
        lowered = name.lower()
        virtual_tokens = (
            "ndi",
            "blackhole",
            "soundflower",
            "loopback",
            "vb-audio",
            "cable",
            "obs",
            "zoomaudio",
            "zoom audio",
            "monitor of",
            "virtual",
            "null",
            "dummy",
            "ianapp",
        )
        return any(token in lowered for token in virtual_tokens)
