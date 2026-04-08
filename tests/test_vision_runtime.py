from __future__ import annotations

import time

import cv2
import numpy as np

from backend.types import AudienceFeatures, RuntimeConfig, ServoTelemetry
from backend.vision.runtime import VisionRuntime


def test_browser_mode_never_opens_local_capture(monkeypatch):
    runtime = VisionRuntime(RuntimeConfig(camera_source="browser"))
    opened = False

    class FakeCapture:
        def release(self) -> None:
            return None

    runtime.capture = FakeCapture()

    def fake_open_capture():
        nonlocal opened
        opened = True
        return FakeCapture()

    def fake_sleep(_: float) -> None:
        runtime.running = False

    monkeypatch.setattr(runtime, "_open_capture", fake_open_capture)
    monkeypatch.setattr(time, "sleep", fake_sleep)

    runtime.running = True
    runtime._loop()

    assert opened is False
    assert runtime.capture is None


def test_apply_camera_orientation_supports_horizontal_vertical_and_both_flips():
    frame = np.array(
        [
            [[1, 0, 0], [2, 0, 0]],
            [[3, 0, 0], [4, 0, 0]],
        ],
        dtype=np.uint8,
    )

    horizontal = VisionRuntime(RuntimeConfig(camera_mirror_preview=True))
    vertical = VisionRuntime(RuntimeConfig(camera_flip_vertical=True))
    both = VisionRuntime(RuntimeConfig(camera_mirror_preview=True, camera_flip_vertical=True))

    np.testing.assert_array_equal(horizontal._apply_camera_orientation(frame), frame[:, ::-1])
    np.testing.assert_array_equal(vertical._apply_camera_orientation(frame), frame[::-1, :])
    np.testing.assert_array_equal(both._apply_camera_orientation(frame), frame[::-1, ::-1])


def test_submit_jpeg_frame_processes_oriented_frame(monkeypatch):
    runtime = VisionRuntime(RuntimeConfig(camera_source="browser", camera_mirror_preview=True, camera_flip_vertical=True))
    raw = np.array(
        [
            [[0, 0, 10], [0, 0, 20], [0, 0, 30]],
            [[0, 0, 40], [0, 0, 50], [0, 0, 60]],
        ],
        dtype=np.uint8,
    )
    ok, encoded = cv2.imencode(".png", raw)
    assert ok
    seen: list[np.ndarray] = []

    def fake_process_frame(frame: np.ndarray) -> tuple[AudienceFeatures, ServoTelemetry]:
        seen.append(frame.copy())
        return AudienceFeatures(), ServoTelemetry()

    monkeypatch.setattr(runtime, "_process_frame", fake_process_frame)
    monkeypatch.setattr(runtime, "_annotate", lambda frame, *_: frame)
    monkeypatch.setattr(runtime, "_encode_person_crop", lambda *_: None)

    runtime.submit_jpeg_frame(encoded.tobytes())

    assert len(seen) == 1
    np.testing.assert_array_equal(seen[0], raw[::-1, ::-1])


def test_backend_capture_loop_processes_oriented_frame(monkeypatch):
    runtime = VisionRuntime(RuntimeConfig(camera_source="backend", camera_mirror_preview=True, camera_flip_vertical=True))
    raw = np.array(
        [
            [[10, 0, 0], [20, 0, 0]],
            [[30, 0, 0], [40, 0, 0]],
        ],
        dtype=np.uint8,
    )
    seen: list[np.ndarray] = []

    class FakeCapture:
        def isOpened(self) -> bool:
            return True

        def read(self) -> tuple[bool, np.ndarray]:
            return True, raw.copy()

        def release(self) -> None:
            return None

    def fake_process_frame(frame: np.ndarray) -> tuple[AudienceFeatures, ServoTelemetry]:
        seen.append(frame.copy())
        runtime.running = False
        return AudienceFeatures(), ServoTelemetry()

    runtime.capture = FakeCapture()
    monkeypatch.setattr(runtime, "_process_frame", fake_process_frame)
    monkeypatch.setattr(runtime, "_annotate", lambda frame, *_: frame)
    monkeypatch.setattr(runtime, "_encode_person_crop", lambda *_: None)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    runtime.running = True
    runtime._loop()

    assert len(seen) == 1
    np.testing.assert_array_equal(seen[0], raw[::-1, ::-1])
