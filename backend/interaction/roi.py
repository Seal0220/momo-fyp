from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias

BBox: TypeAlias = Sequence[int]
FrameShape = tuple[int, int] | tuple[int, int, int]
AudioRegionState = Literal["no_one", "left", "center", "right", "full"]
LightRegionStateName = Literal["no_one", "left", "right", "left_right", "full"]

AUDIO_REGION_STATES: tuple[AudioRegionState, ...] = ("no_one", "left", "center", "right", "full")
LIGHT_REGION_STATES: tuple[LightRegionStateName, ...] = ("no_one", "left", "right", "left_right", "full")


@dataclass(frozen=True)
class LightRoiState:
    region: LightRegionStateName
    left_present: bool
    right_present: bool
    left_super_close: bool
    right_super_close: bool


def classify_audio_roi_states(
    person_bboxes: Sequence[BBox],
    frame_shape: FrameShape | None,
    *,
    full_frame_threshold_ratio: float = 0.70,
) -> set[AudioRegionState]:
    if not person_bboxes:
        return {"no_one"}

    width, height = _frame_dimensions(frame_shape)
    states: set[AudioRegionState] = set()
    max_area_ratio = 0.0
    for bbox in person_bboxes:
        area_ratio = bbox_area_ratio(bbox, width, height)
        max_area_ratio = max(max_area_ratio, area_ratio)
        center_x = bbox_center_x_norm(bbox, width)
        if center_x < 1.0 / 3.0:
            states.add("left")
        elif center_x > 2.0 / 3.0:
            states.add("right")
        else:
            states.add("center")

    if max_area_ratio >= full_frame_threshold_ratio:
        return {"full"}
    return states or {"no_one"}


def classify_light_roi_state(
    person_bboxes: Sequence[BBox],
    frame_shape: FrameShape | None,
    *,
    super_close_threshold_ratio: float = 0.65,
    side_overlap_threshold_ratio: float = 0.05,
) -> LightRoiState:
    if not person_bboxes:
        return LightRoiState(
            region="no_one",
            left_present=False,
            right_present=False,
            left_super_close=False,
            right_super_close=False,
        )

    width, height = _frame_dimensions(frame_shape)
    left_present = False
    right_present = False
    left_super_close = False
    right_super_close = False
    full_frame_person = False
    for bbox in person_bboxes:
        area_ratio = bbox_area_ratio(bbox, width, height)
        if area_ratio >= super_close_threshold_ratio:
            full_frame_person = True
        intersects_left = bbox_x_overlap_ratio(bbox, width, 0.0, 0.5) >= side_overlap_threshold_ratio
        intersects_right = bbox_x_overlap_ratio(bbox, width, 0.5, 1.0) >= side_overlap_threshold_ratio
        left_present = left_present or intersects_left
        right_present = right_present or intersects_right
        if area_ratio >= super_close_threshold_ratio:
            left_super_close = left_super_close or intersects_left
            right_super_close = right_super_close or intersects_right

    if full_frame_person:
        region: LightRegionStateName = "full"
        left_present = True
        right_present = True
        left_super_close = True
        right_super_close = True
    elif left_present and right_present:
        region = "left_right"
    elif left_present:
        region = "left"
    elif right_present:
        region = "right"
    else:
        region = "no_one"

    return LightRoiState(
        region=region,
        left_present=left_present,
        right_present=right_present,
        left_super_close=left_super_close,
        right_super_close=right_super_close,
    )


def bbox_area_ratio(bbox: BBox, frame_width: int, frame_height: int) -> float:
    x1, y1, x2, y2 = bbox
    width = max(0, min(frame_width, x2) - max(0, x1))
    height = max(0, min(frame_height, y2) - max(0, y1))
    return (width * height) / max(1, frame_width * frame_height)


def bbox_center_x_norm(bbox: BBox, frame_width: int) -> float:
    x1, _, x2, _ = bbox
    return min(max(((x1 + x2) / 2.0) / max(1, frame_width), 0.0), 1.0)


def bbox_x_overlap_ratio(bbox: BBox, frame_width: int, left_norm: float, right_norm: float) -> float:
    x1, _, x2, _ = bbox
    bbox_width = max(1, x2 - x1)
    roi_left = int(frame_width * left_norm)
    roi_right = int(frame_width * right_norm)
    overlap = max(0, min(x2, roi_right) - max(x1, roi_left))
    return overlap / bbox_width


def _frame_dimensions(frame_shape: FrameShape | None) -> tuple[int, int]:
    if frame_shape is None:
        return 1920, 1080
    if len(frame_shape) == 3:
        return max(1, int(frame_shape[1])), max(1, int(frame_shape[0]))
    if len(frame_shape) >= 2:
        return max(1, int(frame_shape[0])), max(1, int(frame_shape[1]))
    return 1920, 1080
