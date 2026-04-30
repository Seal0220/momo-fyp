from __future__ import annotations

import pytest

from backend.vision.features import classify_distance, classify_horizontal_position, combine_position_state


@pytest.mark.parametrize(
    ("area_ratio", "expected"),
    [
        (0.31, "near"),
        (0.12, "near"),
        (0.08, "mid"),
        (0.05, "far"),
    ],
)
def test_classify_distance_returns_three_interaction_ranges(area_ratio: float, expected: str) -> None:
    assert classify_distance(area_ratio, near_threshold=0.12) == expected


@pytest.mark.parametrize(
    ("center_x_norm", "expected"),
    [
        (0.1, "left"),
        (1.0 / 3.0, "center"),
        (0.5, "center"),
        (2.0 / 3.0, "center"),
        (0.9, "right"),
    ],
)
def test_classify_horizontal_position_splits_frame_into_thirds(center_x_norm: float, expected: str) -> None:
    assert classify_horizontal_position(center_x_norm) == expected


def test_combine_position_state_uses_english_state_key() -> None:
    assert combine_position_state("near", "left") == "near_left"
    assert combine_position_state("mid", "center") == "mid_center"
    assert combine_position_state("far", "right") == "far_right"
