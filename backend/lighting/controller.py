from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Literal, Protocol

from backend.interaction.roi import LightRoiState

LightSide = Literal["left", "right"]
LightSideStateName = Literal["empty", "present", "super_close"]
DEFAULT_FADE_MIN_SEC = 0.25
DEFAULT_FADE_MAX_SEC = 2.0


class LightConfig(Protocol):
    side_led_count: int
    active_led_count_per_cycle: int
    empty_cycle_sec: float
    empty_brightness_level: float
    present_start_after_sec: float
    present_full_after_sec: float
    present_start_cycle_sec: float
    present_min_cycle_sec: float
    present_start_brightness_level: float
    present_max_brightness_level: float
    super_close_brightness_level: float
    fade_min_sec: float
    fade_max_sec: float


@dataclass(frozen=True)
class LightSideOutput:
    side: LightSide
    state: LightSideStateName
    elapsed_present_sec: float
    cycle_sec: float | None
    brightness_level: float
    brightness_pct: float
    solid: bool
    led_values_pct: list[float]
    active_led_indexes: list[int]


@dataclass(frozen=True)
class LightFrame:
    region: str
    left: LightSideOutput
    right: LightSideOutput
    led_values_pct: list[float]

    @property
    def left_pct(self) -> float:
        return self.left.brightness_pct

    @property
    def right_pct(self) -> float:
        return self.right.brightness_pct


class LightController:
    def __init__(self, config: LightConfig, rng: random.Random | None = None) -> None:
        self.config = config
        self._rng = rng or random.Random()
        self._left = _LightSideController("left", self._rng)
        self._right = _LightSideController("right", self._rng)
        self.latest_frame: LightFrame | None = None

    def reconfigure(self, config: LightConfig) -> None:
        self.config = config

    def update(self, roi_state: LightRoiState, now: float | None = None) -> LightFrame:
        now = time.monotonic() if now is None else now
        left = self._left.update(
            is_present=roi_state.left_present,
            is_super_close=roi_state.left_super_close,
            config=self.config,
            now=now,
        )
        right = self._right.update(
            is_present=roi_state.right_present,
            is_super_close=roi_state.right_super_close,
            config=self.config,
            now=now,
        )
        side_count = max(1, int(self.config.side_led_count))
        frame = LightFrame(
            region=roi_state.region,
            left=left,
            right=right,
            led_values_pct=_resize_values(left.led_values_pct, side_count) + _resize_values(right.led_values_pct, side_count),
        )
        self.latest_frame = frame
        return frame


class _LightSideController:
    def __init__(self, side: LightSide, rng: random.Random) -> None:
        self.side = side
        self._rng = rng
        self.state: LightSideStateName = "empty"
        self.present_since: float | None = None
        self.cycle_started_at: float | None = None
        self.active_led_indexes: set[int] = set()

    def update(
        self,
        *,
        is_present: bool,
        is_super_close: bool,
        config: LightConfig,
        now: float,
    ) -> LightSideOutput:
        next_state = self._next_state(is_present=is_present, is_super_close=is_super_close)
        if next_state != self.state:
            self.state = next_state
            self.present_since = now if next_state == "present" else None
            self._reset_cycle()

        side_led_count = max(1, int(config.side_led_count))
        active_count = min(max(1, int(config.active_led_count_per_cycle)), side_led_count)
        if self.state == "super_close":
            level = config.super_close_brightness_level
            led_values = [brightness_level_to_pct(level)] * side_led_count
            return LightSideOutput(
                side=self.side,
                state=self.state,
                elapsed_present_sec=0.0,
                cycle_sec=None,
                brightness_level=level,
                brightness_pct=brightness_level_to_pct(level),
                solid=True,
                led_values_pct=led_values,
                active_led_indexes=list(range(side_led_count)),
            )

        if self.state == "present":
            present_since = self.present_since if self.present_since is not None else now
            elapsed = now - present_since
            cycle_sec, level = map_present_elapsed(
                elapsed,
                start_after_sec=config.present_start_after_sec,
                full_after_sec=config.present_full_after_sec,
                start_cycle_sec=config.present_start_cycle_sec,
                min_cycle_sec=config.present_min_cycle_sec,
                start_brightness_level=config.present_start_brightness_level,
                max_brightness_level=config.present_max_brightness_level,
            )
            active_indexes = self._active_indexes_for_cycle(now, cycle_sec, side_led_count, active_count)
            brightness_pct = breathing_brightness_pct(
                self._elapsed_in_current_cycle(now),
                cycle_sec,
                level,
                fade_min_sec=config.fade_min_sec,
                fade_max_sec=config.fade_max_sec,
            )
            return LightSideOutput(
                side=self.side,
                state=self.state,
                elapsed_present_sec=round(elapsed, 3),
                cycle_sec=cycle_sec,
                brightness_level=level,
                brightness_pct=brightness_pct,
                solid=False,
                led_values_pct=_values_for_active_indexes(side_led_count, active_indexes, brightness_pct),
                active_led_indexes=sorted(active_indexes),
            )

        cycle_sec = config.empty_cycle_sec
        level = config.empty_brightness_level
        active_indexes = self._active_indexes_for_cycle(now, cycle_sec, side_led_count, active_count)
        brightness_pct = breathing_brightness_pct(
            self._elapsed_in_current_cycle(now),
            cycle_sec,
            level,
            fade_min_sec=config.fade_min_sec,
            fade_max_sec=config.fade_max_sec,
        )
        return LightSideOutput(
            side=self.side,
            state=self.state,
            elapsed_present_sec=0.0,
            cycle_sec=cycle_sec,
            brightness_level=level,
            brightness_pct=brightness_pct,
            solid=False,
            led_values_pct=_values_for_active_indexes(side_led_count, active_indexes, brightness_pct),
            active_led_indexes=sorted(active_indexes),
        )

    def _next_state(self, *, is_present: bool, is_super_close: bool) -> LightSideStateName:
        if is_super_close:
            return "super_close"
        if is_present:
            return "present"
        return "empty"

    def _active_indexes_for_cycle(
        self,
        now: float,
        cycle_sec: float,
        side_led_count: int,
        active_count: int,
    ) -> set[int]:
        cycle_sec = max(0.001, cycle_sec)
        if self.cycle_started_at is None or not self.active_led_indexes:
            self.cycle_started_at = now
            self.active_led_indexes = self._choose_next_indexes(side_led_count, active_count)
            return set(self.active_led_indexes)

        while now - self.cycle_started_at >= cycle_sec:
            self.cycle_started_at += cycle_sec
            self.active_led_indexes = self._choose_next_indexes(side_led_count, active_count)
        return set(self.active_led_indexes)

    def _choose_next_indexes(self, side_led_count: int, active_count: int) -> set[int]:
        all_indexes = set(range(side_led_count))
        candidates = sorted(all_indexes - self.active_led_indexes)
        if len(candidates) < active_count:
            candidates = sorted(all_indexes)
        return set(self._rng.sample(candidates, active_count))

    def _reset_cycle(self) -> None:
        self.cycle_started_at = None
        self.active_led_indexes.clear()

    def _elapsed_in_current_cycle(self, now: float) -> float:
        if self.cycle_started_at is None:
            return 0.0
        return max(0.0, now - self.cycle_started_at)


def map_present_elapsed(
    elapsed_sec: float,
    *,
    start_after_sec: float = 3.0,
    full_after_sec: float = 7.0,
    start_cycle_sec: float = 2.0,
    min_cycle_sec: float = 0.5,
    start_brightness_level: float = 2.0,
    max_brightness_level: float = 8.0,
) -> tuple[float, float]:
    if full_after_sec <= start_after_sec:
        progress = 1.0
    else:
        progress = (elapsed_sec - start_after_sec) / (full_after_sec - start_after_sec)
    progress = min(max(progress, 0.0), 1.0)
    cycle_sec = lerp(start_cycle_sec, min_cycle_sec, progress)
    brightness_level = lerp(start_brightness_level, max_brightness_level, progress)
    return round(cycle_sec, 3), round(brightness_level, 3)


def breathing_brightness_pct(
    cycle_elapsed_sec: float,
    cycle_sec: float,
    brightness_level: float,
    *,
    fade_min_sec: float = DEFAULT_FADE_MIN_SEC,
    fade_max_sec: float = DEFAULT_FADE_MAX_SEC,
) -> float:
    cycle_sec = max(0.001, cycle_sec)
    cycle_elapsed_sec = cycle_elapsed_sec % cycle_sec
    fade_sec = fade_duration_for_cycle(
        cycle_sec,
        fade_min_sec=fade_min_sec,
        fade_max_sec=fade_max_sec,
    )
    if fade_sec <= 0:
        return brightness_level_to_pct(brightness_level)

    if cycle_elapsed_sec < fade_sec:
        progress = cycle_elapsed_sec / fade_sec
    elif cycle_elapsed_sec > cycle_sec - fade_sec:
        progress = (cycle_sec - cycle_elapsed_sec) / fade_sec
    else:
        progress = 1.0

    fade = smoothstep(min(max(progress, 0.0), 1.0))
    return round(brightness_level_to_pct(brightness_level) * fade, 2)


def fade_duration_for_cycle(
    cycle_sec: float,
    *,
    fade_min_sec: float = DEFAULT_FADE_MIN_SEC,
    fade_max_sec: float = DEFAULT_FADE_MAX_SEC,
) -> float:
    cycle_sec = max(0.001, cycle_sec)
    fade_min_sec = max(0.0, fade_min_sec)
    fade_max_sec = max(fade_min_sec, fade_max_sec)
    fade_sec = min(max(cycle_sec / 2.0, fade_min_sec), fade_max_sec)
    return round(min(fade_sec, cycle_sec / 2.0), 3)


def brightness_level_to_pct(level: float) -> float:
    return round(min(max(level, 1.0), 10.0) * 10.0, 2)


def lerp(start: float, end: float, progress: float) -> float:
    return start + ((end - start) * progress)


def smoothstep(progress: float) -> float:
    return progress * progress * (3.0 - (2.0 * progress))


def _values_for_active_indexes(side_led_count: int, active_indexes: set[int], brightness_pct: float) -> list[float]:
    return [
        brightness_pct if index in active_indexes else 0.0
        for index in range(side_led_count)
    ]


def _resize_values(values: list[float], expected_count: int) -> list[float]:
    if len(values) == expected_count:
        return values
    if len(values) > expected_count:
        return values[:expected_count]
    return values + ([0.0] * (expected_count - len(values)))
