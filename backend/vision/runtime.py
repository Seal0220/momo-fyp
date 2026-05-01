from __future__ import annotations

import os
import platform
import threading
import time
import contextlib
from collections import deque
from dataclasses import dataclass

import cv2
import numpy as np

from backend.config import RuntimeConfig
from backend.types import AudienceFeatures, ServoTelemetry
from backend.vision.features import (
    classify_body_shape,
    classify_colors,
    classify_distance,
    classify_horizontal_position,
    combine_position_state,
    smooth_color_labels,
)
from backend.vision.person_detector import PersonDetector

DEFAULT_CAMERA_SCAN_LIMIT = 10


@dataclass
class VisionState:
    features: AudienceFeatures
    servo: ServoTelemetry
    frame_jpeg: bytes | None = None
    person_crop_jpeg: bytes | None = None
    frame_shape: tuple[int, int] | None = None
    target_seen_at: float | None = None


class VisionRuntime:
    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config
        self.detector = PersonDetector(config.yolo.model_path, device_mode=config.yolo.device_mode)
        self.top_color_history: deque[str] = deque(maxlen=6)
        self.bottom_color_history: deque[str] = deque(maxlen=6)
        self._processed_frame_times: deque[float] = deque(maxlen=60)
        self.capture: cv2.VideoCapture | None = None
        self.thread: threading.Thread | None = None
        self.running = False
        self.lock = threading.Lock()
        self._browser_frame_lock = threading.Lock()
        self._browser_frame_ready = threading.Event()
        self._pending_browser_frame: bytes | None = None
        self.failed_open_count = 0
        self.camera_disabled = False
        self.external_frame_at: float | None = None
        self.latest_state = VisionState(
            features=AudienceFeatures(),
            servo=ServoTelemetry(),
            frame_jpeg=None,
            person_crop_jpeg=None,
            frame_shape=None,
            target_seen_at=None,
        )

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.running = False
        self._browser_frame_ready.set()
        if self.thread:
            self.thread.join(timeout=2)
        if self.capture:
            self._release_capture()
        self._clear_pending_browser_frame()
        with self.lock:
            self._processed_frame_times.clear()

    def reconfigure(self, config: RuntimeConfig) -> None:
        self.config = config
        self.detector = PersonDetector(config.yolo.model_path, device_mode=config.yolo.device_mode)
        self.failed_open_count = 0
        self.camera_disabled = False
        self.top_color_history.clear()
        self.bottom_color_history.clear()
        self._clear_pending_browser_frame()
        with self.lock:
            self._processed_frame_times.clear()
        self.stop()
        self.start()

    def get_snapshot(self) -> VisionState:
        with self.lock:
            return VisionState(
                features=self.latest_state.features.model_copy(deep=True),
                servo=self.latest_state.servo.model_copy(deep=True),
                frame_jpeg=self.latest_state.frame_jpeg,
                person_crop_jpeg=self.latest_state.person_crop_jpeg,
                frame_shape=self.latest_state.frame_shape,
                target_seen_at=self.latest_state.target_seen_at,
            )

    def detect_fps(self) -> float:
        with self.lock:
            timestamps = list(self._processed_frame_times)
        if len(timestamps) < 2:
            return 0.0
        latest = timestamps[-1]
        if time.monotonic() - latest > 2.0:
            return 0.0
        span = latest - timestamps[0]
        if span <= 0:
            return 0.0
        return round((len(timestamps) - 1) / span, 2)

    def list_cameras(self) -> list[dict]:
        if self.config.camera.source == "browser":
            return [
                {
                    "device_id": self.config.camera.device_id,
                    "device_name": "Browser Camera",
                    "modes": [{"width": self.config.camera.width, "height": self.config.camera.height, "fps": self.config.camera.fps}],
                }
            ]
        cameras: list[dict] = []
        for index in range(self._camera_scan_limit()):
            api_name, cap = self._open_capture_for_index(index, require_frame=True)
            if cap is None:
                continue
            modes = []
            for width, height, fps in [(640, 480, 30), (1280, 720, 30), (1920, 1080, 30), (1280, 720, 60)]:
                try:
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                    cap.set(cv2.CAP_PROP_FPS, fps)
                    got_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    got_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    got_fps = int(round(cap.get(cv2.CAP_PROP_FPS) or fps))
                except cv2.error:
                    continue
                mode = {"width": got_w, "height": got_h, "fps": got_fps}
                if mode not in modes:
                    modes.append(mode)
            cameras.append(
                {
                    "device_id": str(index),
                    "device_name": f"Camera {index}",
                    "capture_backend": api_name,
                    "modes": modes,
                }
            )
            self._release_video_capture(cap)
        if not cameras:
            cameras.append(
                {
                    "device_id": "0",
                    "device_name": "Default Camera",
                    "modes": [{"width": self.config.camera.width, "height": self.config.camera.height, "fps": self.config.camera.fps}],
                }
            )
        return cameras

    def _open_capture(self) -> cv2.VideoCapture:
        os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")
        device_index = self._camera_device_index()
        _, capture = self._open_capture_for_index(device_index, require_frame=True)
        if capture is None:
            capture = self._create_video_capture(device_index)
            self._configure_capture(capture)
        return capture

    def _camera_device_index(self) -> int:
        if self.config.camera.device_id == "default":
            return 0
        try:
            return int(self.config.camera.device_id)
        except ValueError:
            return 0

    def _camera_scan_limit(self) -> int:
        try:
            return max(1, int(os.getenv("MOMO_CAMERA_SCAN_LIMIT", str(DEFAULT_CAMERA_SCAN_LIMIT))))
        except ValueError:
            return DEFAULT_CAMERA_SCAN_LIMIT

    def _capture_api_candidates(self) -> list[tuple[str, int | None]]:
        if platform.system() == "Windows":
            candidates = [
                ("dshow", getattr(cv2, "CAP_DSHOW", cv2.CAP_ANY)),
                ("msmf", getattr(cv2, "CAP_MSMF", cv2.CAP_ANY)),
                ("any", cv2.CAP_ANY),
            ]
            unique: list[tuple[str, int | None]] = []
            seen: set[int | None] = set()
            for name, api_backend in candidates:
                if api_backend in seen:
                    continue
                seen.add(api_backend)
                unique.append((name, api_backend))
            return unique
        return [("default", None)]

    def _create_video_capture(self, device_index: int, api_backend: int | None = None) -> cv2.VideoCapture:
        if api_backend is None:
            return cv2.VideoCapture(device_index)
        return cv2.VideoCapture(device_index, api_backend)

    def _open_capture_for_index(self, device_index: int, *, require_frame: bool) -> tuple[str | None, cv2.VideoCapture | None]:
        for api_name, api_backend in self._capture_api_candidates():
            capture = self._create_video_capture(device_index, api_backend)
            self._configure_capture(capture)
            if not self._is_capture_opened(capture):
                self._release_video_capture(capture)
                continue
            if require_frame and not self._probe_capture_frame(capture):
                self._release_video_capture(capture)
                continue
            return api_name, capture
        return None, None

    def _configure_capture(self, capture: cv2.VideoCapture) -> None:
        with contextlib.suppress(cv2.error):
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.camera.width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.camera.height)
            capture.set(cv2.CAP_PROP_FPS, self.config.camera.fps)

    def _probe_capture_frame(self, capture: cv2.VideoCapture, attempts: int = 3) -> bool:
        for _ in range(attempts):
            ok, frame = self._read_capture_frame_from(capture)
            if ok and frame is not None:
                return True
            time.sleep(0.03)
        return False

    def _is_capture_opened(self, capture: cv2.VideoCapture) -> bool:
        try:
            return capture.isOpened()
        except cv2.error:
            return False

    def _release_capture(self) -> None:
        if self.capture is None:
            return
        self._release_video_capture(self.capture)
        self.capture = None

    def _release_video_capture(self, capture: cv2.VideoCapture) -> None:
        with contextlib.suppress(cv2.error):
            capture.release()

    def _read_capture_frame(self) -> tuple[bool, np.ndarray | None]:
        if self.capture is None:
            return False, None
        return self._read_capture_frame_from(self.capture)

    def _read_capture_frame_from(self, capture: cv2.VideoCapture) -> tuple[bool, np.ndarray | None]:
        try:
            return capture.read()
        except cv2.error:
            return False, None

    def _loop(self) -> None:
        while self.running:
            if self.config.camera.source == "browser":
                if self.capture:
                    self._release_capture()
                timeout = 0.2 if self.external_frame_at and time.monotonic() - self.external_frame_at < 2.0 else 0.5
                frame_bytes = self._take_pending_browser_frame(timeout=timeout)
                if frame_bytes is not None:
                    try:
                        self._process_submitted_jpeg_frame(frame_bytes)
                    except ValueError:
                        continue
                continue
            if self.camera_disabled:
                self._release_capture()
                time.sleep(5)
                self.failed_open_count = 0
                self.camera_disabled = False
                continue
            if not self.capture:
                self.capture = self._open_capture()
            if not self._is_capture_opened(self.capture):
                self.failed_open_count += 1
                self._release_capture()
                if self.failed_open_count >= 3:
                    self.camera_disabled = True
                    time.sleep(5)
                    continue
                time.sleep(2)
                continue
            ok, frame = self._read_capture_frame()
            if not ok or frame is None:
                self.failed_open_count += 1
                if self.failed_open_count >= 3:
                    self.camera_disabled = True
                    self._release_capture()
                time.sleep(0.05)
                continue
            self.failed_open_count = 0
            frame = self._apply_camera_orientation(frame)
            features, servo = self._process_frame(frame)
            annotated = self._annotate(frame.copy(), features)
            ok_jpg, encoded = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
            person_crop = self._encode_person_crop(frame, features.person_bbox)
            with self.lock:
                self.latest_state = VisionState(
                    features=features,
                    servo=servo,
                    frame_jpeg=encoded.tobytes() if ok_jpg else None,
                    person_crop_jpeg=person_crop,
                    frame_shape=(frame.shape[1], frame.shape[0]),
                    target_seen_at=time.monotonic() if features.track_id is not None else self.latest_state.target_seen_at,
                )
                self._processed_frame_times.append(time.monotonic())
            time.sleep(max(0.0, 1.0 / max(1, self.config.camera.fps) * 0.5))

    def submit_jpeg_frame(self, jpeg_bytes: bytes) -> VisionState:
        if self.running and self.config.camera.source == "browser":
            self.external_frame_at = time.monotonic()
            self._queue_browser_frame(jpeg_bytes)
            return self.get_snapshot()
        return self._process_submitted_jpeg_frame(jpeg_bytes)

    def _process_submitted_jpeg_frame(self, jpeg_bytes: bytes) -> VisionState:
        array = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("invalid jpeg frame")
        frame = self._apply_camera_orientation(frame)
        features, servo = self._process_frame(frame)
        annotated = self._annotate(frame.copy(), features)
        ok_jpg, encoded = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
        person_crop = self._encode_person_crop(frame, features.person_bbox)
        state = VisionState(
            features=features,
            servo=servo,
            frame_jpeg=encoded.tobytes() if ok_jpg else jpeg_bytes,
            person_crop_jpeg=person_crop,
            frame_shape=(frame.shape[1], frame.shape[0]),
            target_seen_at=time.monotonic() if features.track_id is not None else self.latest_state.target_seen_at,
        )
        with self.lock:
            self.latest_state = state
            self.external_frame_at = time.monotonic()
            self._processed_frame_times.append(time.monotonic())
        return state

    def _queue_browser_frame(self, jpeg_bytes: bytes) -> None:
        with self._browser_frame_lock:
            self._pending_browser_frame = jpeg_bytes
        self._browser_frame_ready.set()

    def _take_pending_browser_frame(self, timeout: float) -> bytes | None:
        if not self._browser_frame_ready.wait(timeout):
            return None
        with self._browser_frame_lock:
            frame_bytes = self._pending_browser_frame
            self._pending_browser_frame = None
            self._browser_frame_ready.clear()
            return frame_bytes

    def _clear_pending_browser_frame(self) -> None:
        with self._browser_frame_lock:
            self._pending_browser_frame = None
        self._browser_frame_ready.clear()

    def _apply_camera_orientation(self, frame: np.ndarray) -> np.ndarray:
        if self.config.camera.mirror_preview and self.config.camera.flip_vertical:
            return cv2.flip(frame, -1)
        if self.config.camera.mirror_preview:
            return cv2.flip(frame, 1)
        if self.config.camera.flip_vertical:
            return cv2.flip(frame, 0)
        return frame

    def _process_frame(self, frame: np.ndarray) -> tuple[AudienceFeatures, ServoTelemetry]:
        detections = self.detector.detect(frame)
        if not detections:
            self.top_color_history.clear()
            self.bottom_color_history.clear()
            return AudienceFeatures(), ServoTelemetry()
        person = max(detections, key=lambda item: item.bbox_area_ratio)
        person_bboxes = [detection.bbox for detection in detections]
        top_color, bottom_color = classify_colors(frame, person.bbox)
        self.top_color_history.append(top_color)
        self.bottom_color_history.append(bottom_color)
        top_color = smooth_color_labels(list(self.top_color_history), top_color)
        bottom_color = smooth_color_labels(list(self.bottom_color_history), bottom_color)
        height_class, build_class = classify_body_shape(person.bbox, frame.shape)
        distance = classify_distance(
            person.bbox_area_ratio,
            self.config.distance.near_bbox_threshold_ratio,
            self.config.distance.mid_bbox_threshold_ratio,
        )
        horizontal = classify_horizontal_position(person.center_x_norm)
        features = AudienceFeatures(
            track_id=person.track_id if person.track_id >= 0 else 1,
            person_bbox=person.bbox,
            person_bboxes=person_bboxes,
            person_count=len(detections),
            bbox_area_ratio=person.bbox_area_ratio,
            center_x_norm=person.center_x_norm,
            center_y_norm=person.center_y_norm,
            distance_class=distance,
            horizontal_class=horizontal,
            position_state=combine_position_state(distance, horizontal),
            height_class=height_class,
            build_class=build_class,
            top_color=top_color,
            bottom_color=bottom_color,
        )
        return features, ServoTelemetry(tracking_source="person_center")

    def _encode_person_crop(self, frame: np.ndarray, bbox: list[int] | None) -> bytes | None:
        if bbox is None:
            return None
        x1, y1, x2, y2 = bbox
        height, width = frame.shape[:2]
        x1 = max(0, min(x1, width - 1))
        y1 = max(0, min(y1, height - 1))
        x2 = max(x1 + 1, min(x2, width))
        y2 = max(y1 + 1, min(y2, height))
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        ok_jpg, encoded = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok_jpg:
            return None
        return encoded.tobytes()

    def _annotate(self, frame: np.ndarray, features: AudienceFeatures) -> np.ndarray:
        for bbox in features.person_bboxes:
            if bbox != features.person_bbox:
                self._draw_box(frame, bbox, (90, 210, 120), "Person")
        if features.person_bbox:
            self._draw_box(frame, features.person_bbox, (88, 166, 255), "Person")
        cv2.putText(
            frame,
            f"track={features.track_id} pos={features.position_state} area={features.bbox_area_ratio:.3f}",
            (20, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
        )
        return frame

    def _draw_box(self, frame: np.ndarray, bbox: list[int], color: tuple[int, int, int], label: str) -> None:
        x1, y1, x2, y2 = bbox
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, label, (x1, max(18, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
