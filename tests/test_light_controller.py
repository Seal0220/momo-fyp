from __future__ import annotations

import random
from dataclasses import dataclass

from backend.interaction.roi import LightRoiState
from backend.lighting.controller import (
    LightController,
    breathing_brightness_pct,
    brightness_level_to_pct,
    fade_duration_for_cycle,
    map_present_elapsed,
)


@dataclass
class FakeLightConfig:
    side_led_count: int = 15
    active_led_count_per_cycle: int = 5
    empty_cycle_sec: float = 4.0
    empty_brightness_level: float = 1.0
    present_start_after_sec: float = 3.0
    present_full_after_sec: float = 7.0
    present_start_cycle_sec: float = 2.0
    present_min_cycle_sec: float = 0.5
    present_start_brightness_level: float = 2.0
    present_max_brightness_level: float = 8.0
    super_close_brightness_level: float = 10.0
    fade_min_sec: float = 0.25
    fade_max_sec: float = 2.0


def test_present_elapsed_mapping_clamps_to_requested_curve() -> None:
    assert map_present_elapsed(0.0) == (2.0, 2.0)
    assert map_present_elapsed(3.0) == (2.0, 2.0)
    assert map_present_elapsed(5.0) == (1.25, 5.0)
    assert map_present_elapsed(7.0) == (0.5, 8.0)
    assert map_present_elapsed(12.0) == (0.5, 8.0)


def test_breathing_brightness_uses_cycle_scaled_fade() -> None:
    assert fade_duration_for_cycle(0.5) == 0.25
    assert fade_duration_for_cycle(2.0) == 1.0
    assert fade_duration_for_cycle(4.0) == 2.0
    assert fade_duration_for_cycle(8.0) == 2.0
    assert breathing_brightness_pct(0.0, 2.0, 8.0) == 0.0
    assert breathing_brightness_pct(0.5, 2.0, 8.0) == brightness_level_to_pct(8.0) / 2
    assert breathing_brightness_pct(1.0, 2.0, 8.0) == brightness_level_to_pct(8.0)
    assert breathing_brightness_pct(1.5, 2.0, 8.0) == brightness_level_to_pct(8.0) / 2
    assert breathing_brightness_pct(2.0, 2.0, 8.0) == 0.0


def test_light_cycle_fade_starts_from_zero_at_cycle_start() -> None:
    controller = LightController(FakeLightConfig(empty_brightness_level=10.0), rng=random.Random(7))
    frame = controller.update(
        LightRoiState(
            region="no_one",
            left_present=False,
            right_present=False,
            left_super_close=False,
            right_super_close=False,
        ),
        now=10.3,
    )

    assert frame.left.brightness_pct == 0.0
    assert frame.right.brightness_pct == 0.0
    assert all(value == 0.0 for value in frame.led_values_pct)


def test_light_controller_outputs_30_values_with_five_active_per_side() -> None:
    controller = LightController(FakeLightConfig(), rng=random.Random(7))
    controller.update(
        LightRoiState(
            region="left",
            left_present=True,
            right_present=False,
            left_super_close=False,
            right_super_close=False,
        ),
        now=10.0,
    )
    frame = controller.update(
        LightRoiState(
            region="left",
            left_present=True,
            right_present=False,
            left_super_close=False,
            right_super_close=False,
        ),
        now=11.0,
    )

    assert frame.left.state == "present"
    assert frame.right.state == "empty"
    assert len(frame.led_values_pct) == 30
    assert len(frame.left.active_led_indexes) == 5
    assert len(frame.right.active_led_indexes) == 5
    assert sum(1 for value in frame.led_values_pct[:15] if value > 0) == 5
    assert sum(1 for value in frame.led_values_pct[15:] if value > 0) == 5


def test_next_light_cycle_chooses_from_previous_unlit_indexes() -> None:
    controller = LightController(FakeLightConfig(), rng=random.Random(3))
    first = controller.update(
        LightRoiState(
            region="left",
            left_present=True,
            right_present=False,
            left_super_close=False,
            right_super_close=False,
        ),
        now=0.0,
    )
    second = controller.update(
        LightRoiState(
            region="left",
            left_present=True,
            right_present=False,
            left_super_close=False,
            right_super_close=False,
        ),
        now=2.1,
    )

    assert set(second.left.active_led_indexes).isdisjoint(first.left.active_led_indexes)


def test_present_elapsed_is_measured_even_when_presence_starts_at_zero() -> None:
    controller = LightController(FakeLightConfig())
    controller.update(
        LightRoiState(
            region="left",
            left_present=True,
            right_present=False,
            left_super_close=False,
            right_super_close=False,
        ),
        now=0.0,
    )
    frame = controller.update(
        LightRoiState(
            region="left",
            left_present=True,
            right_present=False,
            left_super_close=False,
            right_super_close=False,
        ),
        now=5.0,
    )

    assert frame.left.elapsed_present_sec == 5.0
    assert frame.left.cycle_sec == 1.25
    assert frame.left.brightness_level == 5.0


def test_super_close_latches_until_side_is_empty() -> None:
    controller = LightController(FakeLightConfig())
    first = controller.update(
        LightRoiState(
            region="left",
            left_present=True,
            right_present=False,
            left_super_close=True,
            right_super_close=False,
        ),
        now=1.0,
    )
    still_latched = controller.update(
        LightRoiState(
            region="left",
            left_present=True,
            right_present=False,
            left_super_close=False,
            right_super_close=False,
        ),
        now=2.0,
    )
    empty = controller.update(
        LightRoiState(
            region="no_one",
            left_present=False,
            right_present=False,
            left_super_close=False,
            right_super_close=False,
        ),
        now=3.0,
    )

    assert first.left.state == "super_close"
    assert first.left.solid is True
    assert first.left.brightness_pct == 100.0
    assert first.left.led_values_pct == [100.0] * 15
    assert still_latched.left.state == "super_close"
    assert empty.left.state == "empty"
