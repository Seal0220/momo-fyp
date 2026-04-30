from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from backend.types import PositionAudioSnapshot

DEFAULT_AUDIO_STATE_DIR = Path(__file__).resolve().parent / "states"
POSITION_AUDIO_DISTANCES = ("far", "mid", "near")
POSITION_AUDIO_HORIZONTAL = ("left", "center", "right")
POSITION_AUDIO_STATE_KEYS = tuple(
    f"{distance}_{horizontal}"
    for distance in POSITION_AUDIO_DISTANCES
    for horizontal in POSITION_AUDIO_HORIZONTAL
)
TRIGGER_AUDIO_DISTANCES = {"mid", "near"}
SUPPORTED_AUDIO_EXTENSIONS = (".wav", ".mp3", ".m4a", ".ogg")


@dataclass(frozen=True)
class PositionAudioResult:
    state_key: str
    status: str
    triggered: bool = False
    audio_path: Path | None = None
    message: str | None = None


class PositionAudioPlayer:
    def __init__(
        self,
        state_dir: Path | str = DEFAULT_AUDIO_STATE_DIR,
        play_file: Callable[[Path], None] | None = None,
    ) -> None:
        self.state_dir = Path(state_dir)
        self._play_file = play_file or play_audio_file
        self.current_state = "unknown"
        self.last_triggered_state: str | None = None
        self.last_audio_file: str | None = None
        self.last_error: str | None = None
        self._last_seen_state = "unknown"
        self._missing_states_reported: set[str] = set()

    def ensure_state_directories(self) -> None:
        ensure_audio_state_directories(self.state_dir)

    def handle_state(self, state_key: str) -> PositionAudioResult:
        state_key = state_key if state_key in POSITION_AUDIO_STATE_KEYS else "unknown"
        self.current_state = state_key
        if state_key == self._last_seen_state:
            return PositionAudioResult(state_key=state_key, status="unchanged")

        self._last_seen_state = state_key
        if not should_trigger_audio(state_key):
            return PositionAudioResult(state_key=state_key, status="ignored")

        audio_path = self.find_audio_file(state_key)
        if audio_path is None:
            self.last_error = f"No audio file found for {state_key}"
            message = None
            if state_key not in self._missing_states_reported:
                self._missing_states_reported.add(state_key)
                message = f"Audio cue missing for {state_key}: add a file under {self.state_dir / state_key}"
            return PositionAudioResult(state_key=state_key, status="missing", message=message)

        try:
            self._play_file(audio_path)
        except Exception as exc:
            self.last_error = str(exc)
            return PositionAudioResult(
                state_key=state_key,
                status="error",
                audio_path=audio_path,
                message=f"Audio cue failed for {state_key}: {exc}",
            )

        self.last_triggered_state = state_key
        self.last_audio_file = str(audio_path)
        self.last_error = None
        return PositionAudioResult(
            state_key=state_key,
            status="played",
            triggered=True,
            audio_path=audio_path,
            message=f"Audio cue played for {state_key}",
        )

    def find_audio_file(self, state_key: str) -> Path | None:
        state_folder = self.state_dir / state_key
        if state_folder.is_dir():
            candidates = sorted(
                path
                for path in state_folder.iterdir()
                if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
            )
            if candidates:
                return candidates[0]

        for extension in SUPPORTED_AUDIO_EXTENSIONS:
            candidate = self.state_dir / f"{state_key}{extension}"
            if candidate.is_file():
                return candidate
        return None

    def snapshot(self) -> PositionAudioSnapshot:
        return PositionAudioSnapshot(
            current_state=self.current_state,
            last_triggered_state=self.last_triggered_state,
            last_audio_file=self.last_audio_file,
            last_error=self.last_error,
        )


def ensure_audio_state_directories(state_dir: Path | str = DEFAULT_AUDIO_STATE_DIR) -> None:
    root = Path(state_dir)
    for state_key in POSITION_AUDIO_STATE_KEYS:
        (root / state_key).mkdir(parents=True, exist_ok=True)


def should_trigger_audio(state_key: str) -> bool:
    distance, _, horizontal = state_key.partition("_")
    return distance in TRIGGER_AUDIO_DISTANCES and horizontal in POSITION_AUDIO_HORIZONTAL


def play_audio_file(path: Path) -> None:
    suffix = path.suffix.lower()
    if sys.platform == "win32" and suffix == ".wav":
        import winsound

        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        return

    command = _playback_command(path)
    if command is None:
        raise RuntimeError(f"No audio playback backend available for {suffix} files")
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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
