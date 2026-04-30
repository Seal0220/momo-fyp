from __future__ import annotations

from pathlib import Path

from backend.audio.position_audio import (
    POSITION_AUDIO_STATE_KEYS,
    PositionAudioPlayer,
    ensure_audio_state_directories,
    should_trigger_audio,
)


def test_audio_state_directories_cover_all_nine_states(tmp_path: Path) -> None:
    ensure_audio_state_directories(tmp_path)

    assert set(POSITION_AUDIO_STATE_KEYS) == {
        "far_left",
        "far_center",
        "far_right",
        "mid_left",
        "mid_center",
        "mid_right",
        "near_left",
        "near_center",
        "near_right",
    }
    assert all((tmp_path / state_key).is_dir() for state_key in POSITION_AUDIO_STATE_KEYS)


def test_should_trigger_audio_only_for_mid_and_near_states() -> None:
    assert should_trigger_audio("far_left") is False
    assert should_trigger_audio("mid_left") is True
    assert should_trigger_audio("near_right") is True


def test_position_audio_player_ignores_far_states_even_when_file_exists(tmp_path: Path) -> None:
    audio_file = tmp_path / "far_left" / "cue.wav"
    audio_file.parent.mkdir()
    audio_file.write_bytes(b"not-real-audio")
    played: list[Path] = []
    player = PositionAudioPlayer(tmp_path, play_file=played.append)

    result = player.handle_state("far_left")

    assert result.status == "ignored"
    assert played == []


def test_position_audio_player_plays_first_mid_or_near_audio_file(tmp_path: Path) -> None:
    state_dir = tmp_path / "mid_center"
    state_dir.mkdir()
    later = state_dir / "b.wav"
    first = state_dir / "a.wav"
    later.write_bytes(b"later")
    first.write_bytes(b"first")
    played: list[Path] = []
    player = PositionAudioPlayer(tmp_path, play_file=played.append)

    result = player.handle_state("mid_center")

    assert result.status == "played"
    assert result.triggered is True
    assert played == [first]
    assert player.snapshot().last_triggered_state == "mid_center"


def test_position_audio_player_does_not_replay_same_state_without_a_transition(tmp_path: Path) -> None:
    state_dir = tmp_path / "near_left"
    state_dir.mkdir()
    audio_file = state_dir / "cue.wav"
    audio_file.write_bytes(b"cue")
    played: list[Path] = []
    player = PositionAudioPlayer(tmp_path, play_file=played.append)

    first = player.handle_state("near_left")
    second = player.handle_state("near_left")

    assert first.status == "played"
    assert second.status == "unchanged"
    assert played == [audio_file]
