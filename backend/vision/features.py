from __future__ import annotations

from collections import Counter

import cv2
import numpy as np


COLOR_TABLE = {
    "黑色": np.array([40, 40, 40]),
    "白色": np.array([220, 220, 220]),
    "灰色": np.array([128, 128, 128]),
    "紅色": np.array([60, 60, 190]),
    "粉色": np.array([180, 140, 220]),
    "藍色": np.array([180, 90, 60]),
    "綠色": np.array([70, 150, 70]),
    "黃色": np.array([60, 190, 210]),
}


def focus_score(frame: np.ndarray, bbox: list[int]) -> float:
    x1, y1, x2, y2 = bbox
    roi = frame[max(0, y1):max(y1 + 1, y2), max(0, x1):max(x1 + 1, x2)]
    if roi.size == 0:
        return 0.0
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var() / 1000.0)


def classify_colors(frame: np.ndarray, bbox: list[int]) -> tuple[str, str]:
    x1, y1, x2, y2 = bbox
    roi = frame[max(0, y1):max(y1 + 1, y2), max(0, x1):max(x1 + 1, x2)]
    if roi.size == 0:
        return "unknown", "unknown"
    height = roi.shape[0]
    top = roi[: max(1, height // 2), :]
    bottom = roi[max(0, height // 2):, :]
    return _nearest_color(top), _nearest_color(bottom)


def classify_body_shape(bbox: list[int], frame_shape: tuple[int, int, int]) -> tuple[str, str]:
    x1, y1, x2, y2 = bbox
    width = max(1, x2 - x1)
    height = max(1, y2 - y1)
    aspect = width / height
    height_ratio = height / max(1, frame_shape[0])
    if height_ratio > 0.7:
        height_class = "tall"
    elif height_ratio < 0.45:
        height_class = "short"
    else:
        height_class = "medium"
    if aspect > 0.55:
        build_class = "broad"
    elif aspect < 0.38:
        build_class = "slim"
    else:
        build_class = "average"
    return height_class, build_class


def classify_distance(area_ratio: float, near_threshold: float, defocus_threshold: float) -> str:
    if area_ratio >= defocus_threshold:
        return "too_close"
    if area_ratio >= near_threshold:
        return "near"
    if area_ratio >= near_threshold / 2:
        return "mid"
    return "far"


def _nearest_color(roi: np.ndarray) -> str:
    sample = roi.reshape(-1, 3)
    if len(sample) > 4000:
        sample = sample[:: max(1, len(sample) // 4000)]
    mean = sample.mean(axis=0)
    scores = {
        name: float(np.linalg.norm(mean - bgr))
        for name, bgr in COLOR_TABLE.items()
    }
    return min(scores, key=scores.get)

