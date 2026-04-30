from __future__ import annotations

import random
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from backend.interaction.roi import AUDIO_REGION_STATES, AudioRegionState
from backend.types import PositionAudioSnapshot

DEFAULT_INTERACTION_AUDIO_DIR = Path(__file__).resolve().parent / "interaction_states"
SUPPORTED_AUDIO_EXTENSIONS = (".wav", ".mp3", ".m4a", ".ogg")


@dataclass(frozen=True)
class AudioTriggerResult:
    state: AudioRegionState
    status: str
    audio_path: Path | None = None
    message: str | None = None


class AudioController:
    def __init__(
        self,
        state_dir: Path | str = DEFAULT_INTERACTION_AUDIO_DIR,
        play_file: Callable[[Path], None] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.state_dir = Path(state_dir)
        self._play_file = play_file or play_audio_file_blocking
        self._rng = rng or random.Random()
        self._channels = {
            state: _AudioChannel(
                state=state,
                state_dir=self.state_dir,
                play_file=self._play_file,
                rng=self._rng,
            )
            for state in AUDIO_REGION_STATES
        }
        self.current_states: set[AudioRegionState] = {"no_one"}

    def ensure_state_directories(self) -> None:
        ensure_interaction_audio_state_directories(self.state_dir)

    def update(self, active_states: Iterable[str]) -> list[AudioTriggerResult]:
        normalized = normalize_audio_states(active_states)
        self.current_states = normalized
        results: list[AudioTriggerResult] = []
        for state in sorted(normalized):
            results.append(self._channels[state].trigger_if_idle())
        return results

    def snapshot(self) -> PositionAudioSnapshot:
        playing_states = [
            state
            for state, channel in self._channels.items()
            if channel.is_playing
        ]
        last_triggered = [
            (channel.last_triggered_at, state, channel.last_audio_file)
            for state, channel in self._channels.items()
            if channel.last_audio_file is not None
        ]
        last_triggered.sort(key=lambda item: item[0])
        last_error = next(
            (channel.last_error for channel in self._channels.values() if channel.last_error),
            None,
        )
        return PositionAudioSnapshot(
            current_state=",".join(sorted(self.current_states)),
            active_states=sorted(self.current_states),
            playing_states=sorted(playing_states),
            last_triggered_state=last_triggered[-1][1] if last_triggered else None,
            last_audio_file=last_triggered[-1][2] if last_triggered else None,
            last_error=last_error,
        )


class _AudioChannel:
    def __init__(
        self,
        *,
        state: AudioRegionState,
        state_dir: Path,
        play_file: Callable[[Path], None],
        rng: random.Random,
    ) -> None:
        self.state = state
        self.state_dir = state_dir
        self._play_file = play_file
        self._rng = rng
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self.is_playing = False
        self.last_audio_file: str | None = None
        self.last_error: str | None = None
        self.last_triggered_at = 0.0
        self._missing_reported = False

    def trigger_if_idle(self) -> AudioTriggerResult:
        with self._lock:
            if self.is_playing:
                return AudioTriggerResult(state=self.state, status="busy")
            audio_path = self._choose_audio_file()
            if audio_path is None:
                self.last_error = f"No audio file found for {self.state}"
                message = None
                if not self._missing_reported:
                    self._missing_reported = True
                    message = f"Audio cue missing for {self.state}: add a file under {self.state_dir / self.state}"
                return AudioTriggerResult(
                    state=self.state,
                    status="missing",
                    message=message,
                )
            self.is_playing = True
            self.last_audio_file = str(audio_path)
            self.last_error = None
            self.last_triggered_at = time.monotonic()
            self._missing_reported = False
            self._thread = threading.Thread(
                target=self._play_until_done,
                args=(audio_path,),
                name=f"audio-{self.state}",
                daemon=True,
            )
            self._thread.start()
        return AudioTriggerResult(
            state=self.state,
            status="started",
            audio_path=audio_path,
            message=f"Audio cue started for {self.state}",
        )

    def _choose_audio_file(self) -> Path | None:
        state_folder = self.state_dir / self.state
        candidates: list[Path] = []
        if state_folder.is_dir():
            candidates.extend(
                path
                for path in state_folder.iterdir()
                if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
            )
        candidates.extend(
            self.state_dir / f"{self.state}{extension}"
            for extension in SUPPORTED_AUDIO_EXTENSIONS
            if (self.state_dir / f"{self.state}{extension}").is_file()
        )
        if not candidates:
            return None
        return self._rng.choice(sorted(candidates))

    def _play_until_done(self, audio_path: Path) -> None:
        try:
            self._play_file(audio_path)
        except Exception as exc:
            with self._lock:
                self.last_error = str(exc)
        finally:
            with self._lock:
                self.is_playing = False


def normalize_audio_states(active_states: Iterable[str]) -> set[AudioRegionState]:
    states = {state for state in active_states if state in AUDIO_REGION_STATES}
    if not states:
        return {"no_one"}
    if "no_one" in states:
        return {"no_one"}
    if "full" in states:
        return {"full"}
    return states


def ensure_interaction_audio_state_directories(state_dir: Path | str = DEFAULT_INTERACTION_AUDIO_DIR) -> None:
    root = Path(state_dir)
    for state in AUDIO_REGION_STATES:
        (root / state).mkdir(parents=True, exist_ok=True)


def play_audio_file_blocking(path: Path) -> None:
    suffix = path.suffix.lower()
    if sys.platform == "win32" and suffix == ".wav":
        import winsound

        winsound.PlaySound(str(path), winsound.SND_FILENAME)
        return

    command = _playback_command(path)
    if command is None:
        raise RuntimeError(f"No audio playback backend available for {suffix} files")
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    process.wait()


def _playback_command(path: Path) -> list[str] | None:
    if sys.platform == "darwin":
        return _command_if_available("afplay", str(path))
    if sys.platform.startswith("linux"):
        for command in (
            _command_if_available("paplay", str(path)),
            _command_if_available("aplay", str(path)),
            _command_if_available("ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)),
        ):
            if command is not None:
                return command
    return None


def _command_if_available(executable: str, *args: str) -> list[str] | None:
    resolved = shutil.which(executable)
    if resolved is None:
        return None
    return [resolved, *args]
