from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("cv2")

from backend.vision.features import classify_colors, smooth_color_labels


def test_classify_colors_prefers_torso_over_background() -> None:
    frame = np.full((480, 640, 3), 210, dtype=np.uint8)
    bbox = [100, 60, 540, 460]

    # hoodie region in dark blue-ish BGR
    frame[230:380, 190:450] = (150, 85, 35)
    # trousers region
    frame[380:450, 200:440] = (55, 55, 55)
    # skin-toned upper region
    frame[90:220, 230:410] = (170, 190, 220)

    top, bottom = classify_colors(frame, bbox)
    assert top == "碧藍色"
    assert bottom in {"黑色", "灰色"}


def test_classify_colors_keeps_neutral_gray_under_warm_cast() -> None:
    frame = np.full((480, 640, 3), 230, dtype=np.uint8)
    bbox = [100, 60, 540, 460]

    # Warm-lit neutral gray shirt.
    frame[235:380, 180:460] = (92, 88, 84)
    frame[90:220, 230:410] = (170, 190, 220)

    top, _ = classify_colors(frame, bbox)
    assert top == "灰色"


def test_classify_colors_detects_lake_green_torso() -> None:
    frame = np.full((480, 640, 3), 228, dtype=np.uint8)
    bbox = [100, 60, 540, 460]

    frame[235:380, 180:460] = (170, 150, 70)
    frame[90:220, 230:410] = (170, 190, 220)

    top, _ = classify_colors(frame, bbox)
    assert top == "湖水綠"


def test_smooth_color_labels_prefers_recent_consensus() -> None:
    labels = ["藍色", "深青藍", "深藍色", "深藍色", "深藍色"]
    assert smooth_color_labels(labels) == "深藍色"
