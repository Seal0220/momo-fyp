from __future__ import annotations

import csv
from pathlib import Path

from backend.types import StatusSnapshot


AUDIENCE_HEADERS = [
    "ts_iso",
    "mode",
    "track_id",
    "person_count",
    "bbox_area_ratio",
    "center_x_norm",
    "center_y_norm",
    "distance_class",
    "horizontal_class",
    "position_state",
    "height_class",
    "build_class",
    "top_color",
    "bottom_color",
    "left_servo_deg",
    "right_servo_deg",
]


def append_audience_snapshot(path: str, snapshot: StatusSnapshot) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not file_path.exists()
    with file_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUDIENCE_HEADERS)
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "ts_iso": snapshot.ts,
                "mode": snapshot.mode.value,
                "track_id": snapshot.audience.track_id,
                "person_count": snapshot.audience.person_count,
                "bbox_area_ratio": snapshot.audience.bbox_area_ratio,
                "center_x_norm": snapshot.audience.center_x_norm,
                "center_y_norm": snapshot.audience.center_y_norm,
                "distance_class": snapshot.audience.distance_class,
                "horizontal_class": snapshot.audience.horizontal_class,
                "position_state": snapshot.audience.position_state,
                "height_class": snapshot.audience.height_class,
                "build_class": snapshot.audience.build_class,
                "top_color": snapshot.audience.top_color,
                "bottom_color": snapshot.audience.bottom_color,
                "left_servo_deg": snapshot.servo.left_deg,
                "right_servo_deg": snapshot.servo.right_deg,
            }
        )
