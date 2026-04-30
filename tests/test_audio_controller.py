from __future__ import annotations

import time
from pathlib import Path
from threading import Event

from backend.audio.interaction_audio import (
    AudioController,
    ensure_interaction_audio_state_directories,
    normalize_audio_states,
)


def test_interaction_audio_directories_cover_five_states(tmp_path: Path) -> None:
    ensure_interaction_audio_state_directories(tmp_path)

    assert all((tmp_path / state).is_dir() for state in ("no_one", "left", "center", "right", "full"))


def test_normalize_audio_states_keeps_parallel_regions_but_full_is_exclusive() -> None:
    assert normalize_audio_states(["left", "center", "right"]) == {"left", "center", "right"}
    assert normalize_audio_states(["left", "full"]) == {"full"}
    assert normalize_audio_states([]) == {"no_one"}


def test_audio_controller_does_not_overlap_same_state_while_playing(tmp_path: Path) -> None:
    audio_file = tmp_path / "left" / "cue.wav"
    audio_file.parent.mkdir()
    audio_file.write_bytes(b"cue")
    release = Event()
    played: list[Path] = []

    def play_file(path: Path) -> None:
        played.append(path)
        release.wait(timeout=1)

    controller = AudioController(tmp_path, play_file=play_file)

    first = controller.update({"left"})
    second = controller.update({"left"})
    _wait_for(lambda: len(played) == 1)
    release.set()

    assert first[0].status == "started"
    assert second[0].status == "busy"
    assert played == [audio_file]


def test_audio_controller_can_play_left_center_right_in_parallel(tmp_path: Path) -> None:
    for state in ("left", "center", "right"):
        audio_file = tmp_path / state / "cue.wav"
        audio_file.parent.mkdir()
        audio_file.write_bytes(b"cue")
    release = Event()
    played: list[str] = []

    def play_file(path: Path) -> None:
        played.append(path.parent.name)
        release.wait(timeout=1)

    controller = AudioController(tmp_path, play_file=play_file)
    results = controller.update({"left", "center", "right"})
    _wait_for(lambda: len(played) == 3)
    release.set()

    assert {result.status for result in results} == {"started"}
    assert set(played) == {"left", "center", "right"}


def test_audio_controller_can_retrigger_after_file_finishes(tmp_path: Path) -> None:
    audio_file = tmp_path / "no_one" / "cue.wav"
    audio_file.parent.mkdir()
    audio_file.write_bytes(b"cue")
    played: list[Path] = []

    def play_file(path: Path) -> None:
        played.append(path)

    controller = AudioController(tmp_path, play_file=play_file)

    first = controller.update({"no_one"})
    deadline = time.monotonic() + 1.0
    while controller.snapshot().playing_states and time.monotonic() < deadline:
        time.sleep(0.01)
    second = controller.update({"no_one"})

    assert first[0].status == "started"
    assert second[0].status == "started"
    assert played == [audio_file, audio_file]


def _wait_for(predicate) -> None:
    deadline = time.monotonic() + 1.0
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.01)
