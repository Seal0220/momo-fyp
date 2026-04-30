from __future__ import annotations

from backend.interaction.roi import classify_audio_roi_states, classify_light_roi_state


def test_audio_roi_uses_left_center_right_zones_independently() -> None:
    states = classify_audio_roi_states(
        [
            [10, 10, 110, 210],
            [910, 10, 1010, 210],
            [1810, 10, 1910, 210],
        ],
        (1920, 1080),
    )

    assert states == {"left", "center", "right"}


def test_audio_roi_can_trigger_parallel_left_and_right_without_center() -> None:
    states = classify_audio_roi_states(
        [
            [10, 10, 110, 210],
            [1810, 10, 1910, 210],
        ],
        (1920, 1080),
    )

    assert states == {"left", "right"}


def test_audio_roi_full_frame_threshold_overrides_regional_state() -> None:
    states = classify_audio_roi_states(
        [[100, 50, 1900, 950]],
        (1920, 1080),
        full_frame_threshold_ratio=0.70,
    )

    assert states == {"full"}


def test_audio_roi_full_frame_can_use_combined_coverage() -> None:
    states = classify_audio_roi_states(
        [
            [0, 0, 960, 1080],
            [960, 0, 1920, 1080],
        ],
        (1920, 1080),
        full_frame_threshold_ratio=0.70,
    )

    assert states == {"full"}


def test_light_roi_keeps_left_right_classification_separate_from_audio() -> None:
    state = classify_light_roi_state(
        [
            [10, 10, 110, 210],
            [1810, 10, 1910, 210],
        ],
        (1920, 1080),
    )

    assert state.region == "full"
    assert state.left_present is True
    assert state.right_present is True
    assert state.left_super_close is False
    assert state.right_super_close is False


def test_light_roi_marks_super_close_per_intersecting_side() -> None:
    state = classify_light_roi_state(
        [[0, 0, 1500, 1080]],
        (1920, 1080),
        super_close_threshold_ratio=0.65,
    )

    assert state.region == "full"
    assert state.left_super_close is True
    assert state.right_super_close is True
