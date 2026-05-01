from __future__ import annotations

import threading
import time

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
pytest.importorskip("ultralytics")

from backend.config import RuntimeConfig
from backend.types import AudienceFeatures, ServoTelemetry
from backend.vision.runtime import VisionRuntime, VisionState


def test_browser_mode_never_opens_local_capture(monkeypatch):
    runtime = VisionRuntime(RuntimeConfig(camera=RuntimeConfig.Camera(source="browser")))
    opened = False

    class FakeCapture:
        def release(self) -> None:
            return None

    runtime.capture = FakeCapture()

    def fake_open_capture():
        nonlocal opened
        opened = True
        return FakeCapture()

    def fake_take_pending_browser_frame(*, timeout: float) -> None:
        assert timeout in {0.2, 0.5}
        runtime.running = False

    monkeypatch.setattr(runtime, "_open_capture", fake_open_capture)
    monkeypatch.setattr(runtime, "_take_pending_browser_frame", fake_take_pending_browser_frame)

    runtime.running = True
    runtime._loop()

    assert opened is False
    assert runtime.capture is None


def test_open_capture_falls_back_to_next_windows_backend(monkeypatch):
    runtime = VisionRuntime(RuntimeConfig(camera=RuntimeConfig.Camera(source="backend")))
    dshow_backend = getattr(cv2, "CAP_DSHOW", cv2.CAP_ANY)
    msmf_backend = getattr(cv2, "CAP_MSMF", cv2.CAP_ANY)
    if dshow_backend == msmf_backend:
        pytest.skip("OpenCV build does not expose distinct Windows camera backends")
    created: list[int | None] = []

    class FakeCapture:
        def __init__(self, api_backend: int | None) -> None:
            self.api_backend = api_backend
            self.released = False

        def isOpened(self) -> bool:
            return True

        def set(self, *_):
            return True

        def read(self):
            if self.api_backend == msmf_backend:
                return True, np.zeros((2, 2, 3), dtype=np.uint8)
            return False, None

        def release(self) -> None:
            self.released = True

    monkeypatch.setattr("backend.vision.runtime.platform.system", lambda: "Windows")

    def fake_create_video_capture(device_index: int, api_backend: int | None = None):
        assert device_index == 0
        created.append(api_backend)
        return FakeCapture(api_backend)

    monkeypatch.setattr(runtime, "_create_video_capture", fake_create_video_capture)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    capture = runtime._open_capture()

    assert capture.api_backend == msmf_backend
    assert created[:2] == [dshow_backend, msmf_backend]


def test_list_cameras_scans_past_first_five_indices(monkeypatch):
    runtime = VisionRuntime(RuntimeConfig(camera=RuntimeConfig.Camera(source="backend")))

    class FakeCapture:
        def set(self, *_):
            return True

        def get(self, *_):
            return 640

        def release(self) -> None:
            return None

    def fake_open_capture_for_index(device_index: int, *, require_frame: bool):
        assert require_frame is True
        if device_index == 5:
            return "fake", FakeCapture()
        return None, None

    monkeypatch.setattr(runtime, "_camera_scan_limit", lambda: 6)
    monkeypatch.setattr(runtime, "_open_capture_for_index", fake_open_capture_for_index)

    cameras = runtime.list_cameras()

    assert cameras[0]["device_id"] == "5"
    assert cameras[0]["capture_backend"] == "fake"


def test_camera_disabled_state_retries_after_cooldown(monkeypatch):
    runtime = VisionRuntime(RuntimeConfig(camera=RuntimeConfig.Camera(source="backend")))
    sleeps: list[float] = []

    class ClosedCapture:
        def isOpened(self) -> bool:
            return False

        def release(self) -> None:
            return None

    def fake_open_capture():
        runtime.running = False
        return ClosedCapture()

    monkeypatch.setattr(runtime, "_open_capture", fake_open_capture)
    monkeypatch.setattr(time, "sleep", lambda seconds: sleeps.append(seconds))

    runtime.camera_disabled = True
    runtime.running = True
    runtime._loop()

    assert 5 in sleeps
    assert runtime.camera_disabled is False


def test_apply_camera_orientation_supports_horizontal_vertical_and_both_flips():
    frame = np.array(
        [
            [[1, 0, 0], [2, 0, 0]],
            [[3, 0, 0], [4, 0, 0]],
        ],
        dtype=np.uint8,
    )

    horizontal = VisionRuntime(RuntimeConfig(camera=RuntimeConfig.Camera(mirror_preview=True, flip_vertical=False)))
    vertical = VisionRuntime(RuntimeConfig(camera=RuntimeConfig.Camera(mirror_preview=False, flip_vertical=True)))
    both = VisionRuntime(RuntimeConfig(camera=RuntimeConfig.Camera(mirror_preview=True, flip_vertical=True)))

    np.testing.assert_array_equal(horizontal._apply_camera_orientation(frame), frame[:, ::-1])
    np.testing.assert_array_equal(vertical._apply_camera_orientation(frame), frame[::-1, :])
    np.testing.assert_array_equal(both._apply_camera_orientation(frame), frame[::-1, ::-1])


def test_submit_jpeg_frame_processes_oriented_frame(monkeypatch):
    runtime = VisionRuntime(
        RuntimeConfig(camera=RuntimeConfig.Camera(source="browser", mirror_preview=True, flip_vertical=True))
    )
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


def test_running_browser_mode_queues_uploaded_frame_without_inline_processing(monkeypatch):
    runtime = VisionRuntime(RuntimeConfig(camera=RuntimeConfig.Camera(source="browser")))
    processed: list[bytes] = []

    def fake_process(jpeg_bytes: bytes) -> VisionState:
        processed.append(jpeg_bytes)
        return VisionState(features=AudienceFeatures(track_id=9), servo=ServoTelemetry())

    monkeypatch.setattr(runtime, "_process_submitted_jpeg_frame", fake_process)
    runtime.running = True

    state = runtime.submit_jpeg_frame(b"frame-a")

    assert processed == []
    assert state.features.track_id is None
    assert runtime._pending_browser_frame == b"frame-a"


def test_browser_loop_processes_only_latest_uploaded_frame(monkeypatch):
    runtime = VisionRuntime(RuntimeConfig(camera=RuntimeConfig.Camera(source="browser")))
    processed: list[bytes] = []

    def fake_process(jpeg_bytes: bytes) -> VisionState:
        processed.append(jpeg_bytes)
        runtime.running = False
        return VisionState(features=AudienceFeatures(track_id=1), servo=ServoTelemetry())

    monkeypatch.setattr(runtime, "_process_submitted_jpeg_frame", fake_process)
    runtime.running = True
    runtime.submit_jpeg_frame(b"frame-old")
    runtime.submit_jpeg_frame(b"frame-new")

    worker = threading.Thread(target=runtime._loop, daemon=True)
    worker.start()
    worker.join(timeout=1)

    assert processed == [b"frame-new"]


def test_detect_fps_reports_recent_processing_rate(monkeypatch):
    runtime = VisionRuntime(RuntimeConfig(camera=RuntimeConfig.Camera(source="browser")))
    now = 100.0
    monkeypatch.setattr(time, "monotonic", lambda: now)
    with runtime.lock:
        runtime._processed_frame_times.extend([99.0, 99.2, 99.4, 99.6, 99.8, 100.0])

    assert runtime.detect_fps() == 5.0


def test_detect_fps_drops_to_zero_when_stale(monkeypatch):
    runtime = VisionRuntime(RuntimeConfig(camera=RuntimeConfig.Camera(source="browser")))
    now = 103.5
    monkeypatch.setattr(time, "monotonic", lambda: now)
    with runtime.lock:
        runtime._processed_frame_times.extend([100.0, 100.5, 101.0])

    assert runtime.detect_fps() == 0.0


def test_backend_capture_loop_processes_oriented_frame(monkeypatch):
    runtime = VisionRuntime(
        RuntimeConfig(camera=RuntimeConfig.Camera(source="backend", mirror_preview=True, flip_vertical=True))
    )
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
