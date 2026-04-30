from __future__ import annotations

if __name__ == "__main__" and __package__ is None:
    # Keep direct file execution from shadowing stdlib modules with backend/types.py.
    import sys as _sys
    from pathlib import Path as _Path

    _backend_dir = _Path(__file__).resolve().parent
    _project_root = _backend_dir.parent
    _sys.path = [
        path
        for path in _sys.path
        if _Path(path or ".").resolve() != _backend_dir
    ]
    _sys.path.insert(0, str(_project_root))

import argparse
import asyncio
import contextlib
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.audio.interaction_audio import AudioController
from backend.config import (
    CONFIG_FIELD_PATHS,
    CONFIG_GROUP_LABELS,
    LIVE_EDITABLE_CONFIG_KEYS,
    ConfigUpdateResponse,
    RuntimeConfig,
    build_field_catalog,
    get_config_value,
    merge_config,
    validate_runtime_config,
)
from backend.device_utils import backend_label_for_device, expected_accelerator_label, expected_vision_backend_label
from backend.interaction.roi import BBox, classify_audio_roi_states, classify_light_roi_state
from backend.lighting.controller import LightController
from backend.model_manager import ensure_runtime_models
from backend.runtime_shutdown import clear_shutdown_request, install_shutdown_signal_bridge, request_shutdown
from backend.serial.esp32_link import ESP32Link
from backend.servo.geometry import compute_servo_angles
from backend.state_machine import RuntimeState
from backend.storage.csv_logger import append_audience_snapshot
from backend.telemetry.system_stats import capture_process_footprint, diff_process_footprint, get_system_stats
from backend.types import (
    AudienceFeatures,
    LightSideSnapshot,
    LightSnapshot,
    PipelineStage,
    RuntimeComponentStats,
    ServoTelemetry,
    SystemMode,
)
from backend.vision.features import (
    POSITION_HORIZONTAL_CLASSES,
    classify_distance,
    classify_horizontal_position,
    combine_position_state,
    normalize_position_distance,
)
from backend.vision.runtime import VisionRuntime

SERIAL_REFRESH_INTERVAL_SEC = 2.0
STATUS_STREAM_INTERVAL_SEC = 0.5
WEB_DIR = Path(__file__).resolve().parent / "web"


class Brain:
    def __init__(self) -> None:
        self.config = RuntimeConfig()
        self.state = RuntimeState()
        self.serial = ESP32Link(self.config.serial.port, self.config.serial.baud_rate)
        self.vision = VisionRuntime(self.config)
        self.audio_controller = AudioController(self.config.audio.state_dir)
        self.light_controller = LightController(self.config.light)
        self.yolo_person_runtime = RuntimeComponentStats(
            requested_mode=self.config.yolo.device_mode,
            effective_device=self.vision.detector.device,
            backend=backend_label_for_device(self.vision.detector.device),
            selection_source="default",
        )
        self.last_target_seen = 0.0
        self.lock_started_at: float | None = None
        self.background_tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        clear_shutdown_request()
        self.audio_controller.ensure_state_directories()
        if should_prepare_models():
            await asyncio.to_thread(self._prepare_vision_models)
        await self._print_startup_diagnostics()
        self.vision.start()
        self.background_tasks = [
            asyncio.create_task(self.vision_loop()),
            asyncio.create_task(self.serial_refresh_loop()),
        ]

    async def stop(self) -> None:
        request_shutdown()
        for task in self.background_tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self.vision.stop()
        self.serial.close()

    def _prepare_vision_models(self) -> None:
        ensure_runtime_models(self.config)
        self.vision = VisionRuntime(self.config)
        self._refresh_vision_runtime_stats()

    async def _print_startup_diagnostics(self) -> None:
        for line in await self._collect_startup_diagnostics():
            print(line, flush=True)

    async def _collect_startup_diagnostics(self) -> list[str]:
        expected = expected_accelerator_label()
        vision_expected = expected_vision_backend_label(self.config.yolo.device_mode)
        lines = [
            f"[startup] expected_accelerator={expected}",
            f"[startup] expected_vision_backend={vision_expected}",
        ]
        try:
            await asyncio.to_thread(self._refresh_vision_runtime_stats)
            person_backend = self.yolo_person_runtime.backend or "unknown"
            lines.append(
                "[startup] yolo "
                f"person={person_backend} target={vision_expected} "
                f"ok={person_backend == vision_expected}"
            )
        except Exception as exc:
            lines.append(f"[startup] yolo error={exc}")
        return lines

    def _refresh_vision_runtime_stats(self) -> None:
        person_device = getattr(self.vision.detector, "device", "cpu")

        person_before = capture_process_footprint(person_device)
        person_backend = self.vision.detector.warmup()
        person_after = capture_process_footprint(person_device)
        person_ram_mb, person_vram_mb = diff_process_footprint(person_before, person_after)

        self.yolo_person_runtime = RuntimeComponentStats(
            requested_mode=self.config.yolo.device_mode,
            effective_device=person_device,
            backend=person_backend,
            selection_source="default",
            ram_mb=person_ram_mb,
            vram_mb=person_vram_mb,
        )

    def snapshot(self):
        vision = self.vision.get_snapshot()
        features = self._prepare_position_features(vision.features)
        self.state.audience = features
        self.state.servo = self._compute_servo_from_features(features, vision.servo.tracking_source)
        snap = self.state.snapshot()
        snap.stats = get_system_stats("tmp")
        snap.serial_connected = self.serial.connected
        snap.serial_monitor = self.serial.snapshot()
        snap.camera_device_id = self.config.camera.device_id
        snap.camera_mode = f"{self.config.camera.width}x{self.config.camera.height}@{self.config.camera.fps}"
        snap.yolo_detect_fps = self.vision.detect_fps()
        snap.yolo_person_runtime = self.yolo_person_runtime
        snap.position_audio = self.audio_controller.snapshot()
        snap.light = self._light_snapshot()
        return snap

    def send_servo_for_features(
        self,
        features: AudienceFeatures,
        tracking_source: str,
        frame_shape: tuple[int, int] | None = None,
        now: float | None = None,
    ) -> None:
        servo = (
            self._compute_servo_from_features(features, tracking_source)
            if features.track_id is not None
            else ServoTelemetry(
                left_deg=self.config.servo_calibration.left_zero_deg,
                right_deg=self.config.servo_calibration.right_zero_deg,
                tracking_source="none",
            )
        )
        self.state.servo = servo
        light_frame = self._compute_light_frame(features, frame_shape, now)
        self.serial.send_servo_command(
            servo.left_deg,
            servo.right_deg,
            mode="track" if features.track_id is not None else "idle_scan",
            tracking_source=servo.tracking_source,
            led_left_pct=light_frame.left_pct,
            led_right_pct=light_frame.right_pct,
            led_values_pct=light_frame.led_values_pct,
            led_signal_loss_fade_out_ms=self.config.led.signal_loss_fade_out_ms,
        )

    async def serial_refresh_loop(self) -> None:
        while True:
            self.serial.refresh_connection()
            await asyncio.sleep(SERIAL_REFRESH_INTERVAL_SEC)

    async def vision_loop(self) -> None:
        while True:
            try:
                self.state.set_pipeline_stage(PipelineStage.VISION)
                self._update_mode_from_vision()
                append_audience_snapshot("tmp/audience.csv", self.snapshot())
                self.state.set_pipeline_stage(PipelineStage.IDLE)
            except Exception as exc:
                self.state.set_pipeline_stage(PipelineStage.ERROR, error=str(exc))
                self.state.event_log = [f"vision loop error: {exc}", *self.state.event_log][:20]
            await asyncio.sleep(max(0.02, 1.0 / max(1, self.config.camera.fps)))

    def _update_mode_from_vision(self) -> None:
        now = time.monotonic()
        vision = self.vision.get_snapshot()
        features = self._prepare_position_features(vision.features)
        self.state.audience = features
        self.send_servo_for_features(features, vision.servo.tracking_source, vision.frame_shape, now)
        self._update_position_audio_for_features(features, vision.frame_shape)

        lock_threshold = self.config.tracking.lock_bbox_threshold_ratio
        unlock_threshold = self.config.tracking.unlock_bbox_threshold_ratio or lock_threshold
        threshold = unlock_threshold if self.state.mode in {SystemMode.TRACKING, SystemMode.RECONNECTING} else lock_threshold

        if features.track_id is None or features.bbox_area_ratio < threshold:
            if self.state.mode == SystemMode.TRACKING and now - self.last_target_seen <= self.config.tracking.lost_timeout_ms / 1000:
                self.state.set_mode(SystemMode.RECONNECTING, "Target temporarily lost")
            elif now - self.last_target_seen > self.config.tracking.lost_timeout_ms / 1000:
                self.state.set_mode(SystemMode.IDLE)
                self.state.locked_track_id = None
                self.lock_started_at = None
            return

        self.last_target_seen = now
        if self.lock_started_at is None:
            self.lock_started_at = now
            self.state.set_mode(SystemMode.ACQUIRING)
            return
        if now - self.lock_started_at < self.config.tracking.enter_debounce_ms / 1000:
            self.state.set_mode(SystemMode.ACQUIRING)
            return

        if self.state.mode != SystemMode.TRACKING:
            self.state.set_mode(SystemMode.TRACKING, "Locked target acquired")
        self.state.locked_track_id = features.track_id

    def _prepare_position_features(self, features: AudienceFeatures) -> AudienceFeatures:
        if features.track_id is None:
            return features.model_copy(update={"horizontal_class": "unknown", "position_state": "unknown"})

        distance = normalize_position_distance(features.distance_class)
        if distance == "unknown":
            distance = classify_distance(
                features.bbox_area_ratio,
                self.config.distance.near_bbox_threshold_ratio,
                self.config.distance.mid_bbox_threshold_ratio,
            )
        horizontal = features.horizontal_class
        if horizontal not in POSITION_HORIZONTAL_CLASSES:
            horizontal = classify_horizontal_position(features.center_x_norm)
        position_state = combine_position_state(distance, horizontal)

        return features.model_copy(
            update={
                "distance_class": distance,
                "horizontal_class": horizontal,
                "position_state": position_state,
            }
        )

    def _update_position_audio_for_features(
        self,
        features: AudienceFeatures,
        frame_shape: tuple[int, int] | None,
    ) -> None:
        person_bboxes = self._person_bboxes_for_roi(features)
        audio_states = classify_audio_roi_states(
            person_bboxes,
            frame_shape or self._configured_frame_shape(),
            full_frame_threshold_ratio=self.config.audio.full_frame_threshold_ratio,
        )
        results = self.audio_controller.update(audio_states)
        messages = [result.message for result in results if result.message]
        if messages:
            self.state.event_log = [*messages, *self.state.event_log][:20]

    def _compute_servo_from_features(self, features, tracking_source: str):
        servo = compute_servo_angles(
            target_x_norm=features.center_x_norm,
            bbox_area_ratio=features.bbox_area_ratio,
            left_zero_deg=self.config.servo_calibration.left_zero_deg,
            right_zero_deg=self.config.servo_calibration.right_zero_deg,
            eye_spacing_cm=self.config.servo_calibration.eye_spacing_cm,
            left_limits=(self.config.servo_calibration.left_min_deg, self.config.servo_calibration.left_max_deg),
            right_limits=(self.config.servo_calibration.right_min_deg, self.config.servo_calibration.right_max_deg),
        )
        servo.left_deg = self._apply_servo_output_calibration(
            angle=servo.left_deg,
            zero_deg=self.config.servo_calibration.left_zero_deg,
            min_deg=self.config.servo_calibration.left_min_deg,
            max_deg=self.config.servo_calibration.left_max_deg,
            gain=self.config.servo_calibration.left_gain,
            trim_deg=self.config.servo_calibration.left_trim_deg,
        )
        servo.right_deg = self._apply_servo_output_calibration(
            angle=servo.right_deg,
            zero_deg=self.config.servo_calibration.right_zero_deg,
            min_deg=self.config.servo_calibration.right_min_deg,
            max_deg=self.config.servo_calibration.right_max_deg,
            gain=self.config.servo_calibration.right_gain,
            trim_deg=self.config.servo_calibration.right_trim_deg,
        )
        servo.tracking_source = tracking_source
        return servo

    def _compute_light_frame(
        self,
        features: AudienceFeatures,
        frame_shape: tuple[int, int] | None = None,
        now: float | None = None,
    ):
        person_bboxes = self._person_bboxes_for_roi(features)
        roi_state = classify_light_roi_state(
            person_bboxes,
            frame_shape or self._configured_frame_shape(),
            super_close_threshold_ratio=self.config.light.super_close_bbox_threshold_ratio,
        )
        return self.light_controller.update(roi_state, now)

    def _person_bboxes_for_roi(self, features: AudienceFeatures) -> list[BBox]:
        return cast(list[BBox], features.person_bboxes)

    def _configured_frame_shape(self) -> tuple[int, int]:
        return self.config.camera.width, self.config.camera.height

    def _light_snapshot(self) -> LightSnapshot:
        frame = self.light_controller.latest_frame
        if frame is None:
            return LightSnapshot()
        return LightSnapshot(
            region=frame.region,
            left=LightSideSnapshot(
                state=frame.left.state,
                brightness_pct=frame.left.brightness_pct,
                brightness_level=frame.left.brightness_level,
                cycle_sec=frame.left.cycle_sec,
                solid=frame.left.solid,
                active_led_indexes=frame.left.active_led_indexes,
            ),
            right=LightSideSnapshot(
                state=frame.right.state,
                brightness_pct=frame.right.brightness_pct,
                brightness_level=frame.right.brightness_level,
                cycle_sec=frame.right.cycle_sec,
                solid=frame.right.solid,
                active_led_indexes=frame.right.active_led_indexes,
            ),
            led_values_pct=frame.led_values_pct,
        )

    def _compute_led_brightness_from_features(self, features) -> tuple[float, float]:
        midpoint_x = features.center_x_norm
        midpoint_x = min(max(midpoint_x, 0.0), 1.0)
        if self.config.servo_calibration.output_inverted:
            midpoint_x = 1.0 - midpoint_x
        if self.config.led.left_right_inverted:
            midpoint_x = 1.0 - midpoint_x

        centered_midpoint = (midpoint_x - 0.5) * 2.0
        midpoint_sign = -1.0 if centered_midpoint < 0 else 1.0
        midpoint_magnitude = abs(centered_midpoint)
        deadzone = self.config.led.midpoint_deadzone_norm
        if midpoint_magnitude <= deadzone:
            midpoint_magnitude = 0.0
        else:
            midpoint_magnitude = (midpoint_magnitude - deadzone) / (1.0 - deadzone)

        midpoint_magnitude = min(midpoint_magnitude * self.config.led.midpoint_response_gain, 1.0)
        midpoint_magnitude = midpoint_magnitude ** self.config.led.midpoint_response_gamma
        midpoint_x = 0.5 + ((midpoint_sign * midpoint_magnitude) / 2.0)

        brightness_span = self.config.led.max_brightness_pct - self.config.led.min_brightness_pct
        left_pct = self.config.led.min_brightness_pct + ((1.0 - midpoint_x) * brightness_span)
        right_pct = self.config.led.min_brightness_pct + (midpoint_x * brightness_span)

        if self.config.led.brightness_output_inverted:
            brightness_total = self.config.led.min_brightness_pct + self.config.led.max_brightness_pct
            left_pct = brightness_total - left_pct
            right_pct = brightness_total - right_pct

        return round(min(max(left_pct, 0.0), 100.0), 2), round(min(max(right_pct, 0.0), 100.0), 2)

    def _apply_servo_output_calibration(
        self,
        *,
        angle: float,
        zero_deg: float,
        min_deg: float,
        max_deg: float,
        gain: float,
        trim_deg: float,
    ) -> float:
        delta = angle - zero_deg
        if self.config.servo_calibration.output_inverted:
            delta = -delta
        calibrated = zero_deg + (delta * gain) + trim_deg
        return round(min(max(calibrated, min_deg), max_deg), 2)


brain = Brain()


def should_prepare_models() -> bool:
    return os.getenv("MOMO_SKIP_MODEL_BOOTSTRAP") != "1"


async def build_apply_checks(payload: dict, config: RuntimeConfig) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    changed = set(_expand_config_payload_keys(payload))

    if changed & {"camera.source", "camera.device_id", "camera.width", "camera.height", "camera.fps", "camera.mirror_preview", "camera.flip_vertical"}:
        orientation = f"hflip={'on' if config.camera.mirror_preview else 'off'}, vflip={'on' if config.camera.flip_vertical else 'off'}"
        if config.camera.source == "browser":
            checks.append(
                {
                    "component": "vision",
                    "status": "ok",
                    "message": (
                        f"Browser camera config staged: {config.camera.width}x{config.camera.height}@{config.camera.fps}, "
                        f"{orientation}. Applies on next uploaded frame."
                    ),
                }
            )
        else:
            checks.append(
                {
                    "component": "vision",
                    "status": "ok",
                    "message": (
                        f"Backend capture reconfigured to device {config.camera.device_id} at "
                        f"{config.camera.width}x{config.camera.height}@{config.camera.fps}, {orientation}."
                    ),
                }
            )

    if changed & {"yolo.model_path", "yolo.device_mode"}:
        checks.append({"component": "vision-model", "status": "ok", "message": f"YOLO model paths updated and verified. Device mode is {config.yolo.device_mode}."})

    if changed & {"serial.port", "serial.baud_rate"}:
        if config.serial.port == "auto":
            message = f"Serial reconfigured to auto detect at {config.serial.baud_rate} baud."
            status = "ok" if brain.serial.connected else "warning"
        else:
            message = f"Serial reconfigured to {config.serial.port} at {config.serial.baud_rate} baud."
            status = "ok" if brain.serial.connected else "warning"
            if not brain.serial.connected:
                message += " Port not connected right now."
        checks.append({"component": "serial", "status": status, "message": message})

    if changed & {
        "servo_calibration.left_zero_deg",
        "servo_calibration.right_zero_deg",
        "servo_calibration.output_inverted",
        "servo_calibration.left_trim_deg",
        "servo_calibration.right_trim_deg",
        "servo_calibration.left_gain",
        "servo_calibration.right_gain",
        "servo_calibration.eye_spacing_cm",
        "servo_calibration.left_min_deg",
        "servo_calibration.left_max_deg",
        "servo_calibration.right_min_deg",
        "servo_calibration.right_max_deg",
        "servo_motion.smoothing_alpha",
        "servo_motion.max_speed_deg_per_sec",
    }:
        checks.append({"component": "servo", "status": "ok", "message": "Servo math config updated and will apply on next tracking update."})

    if changed & {
        "led.min_brightness_pct",
        "led.max_brightness_pct",
        "led.midpoint_response_gain",
        "led.midpoint_response_gamma",
        "led.midpoint_deadzone_norm",
        "led.signal_loss_fade_out_ms",
        "led.brightness_output_inverted",
        "led.left_right_inverted",
    }:
        checks.append({"component": "led", "status": "ok", "message": "LED response config updated and will apply on next tracking update."})

    if changed & {
        "audio.state_dir",
        "audio.full_frame_threshold_ratio",
    }:
        checks.append({"component": "audio", "status": "ok", "message": "Audio ROI and cue folder config updated."})

    if changed & {
        "light.side_led_count",
        "light.active_led_count_per_cycle",
        "light.super_close_bbox_threshold_ratio",
        "light.empty_cycle_sec",
        "light.empty_brightness_level",
        "light.present_start_after_sec",
        "light.present_full_after_sec",
        "light.present_start_cycle_sec",
        "light.present_min_cycle_sec",
        "light.present_start_brightness_level",
        "light.present_max_brightness_level",
        "light.super_close_brightness_level",
    }:
        checks.append({"component": "light", "status": "ok", "message": "Independent light ROI, random LED cycle, and breathing config updated."})

    if changed & {
        "tracking.lock_bbox_threshold_ratio",
        "tracking.unlock_bbox_threshold_ratio",
        "distance.near_bbox_threshold_ratio",
        "distance.mid_bbox_threshold_ratio",
        "tracking.enter_debounce_ms",
        "tracking.exit_debounce_ms",
        "tracking.lost_timeout_ms",
    }:
        checks.append({"component": "vision-rules", "status": "ok", "message": "Person detection thresholds updated."})

    if not checks:
        checks.append({"component": "config", "status": "ok", "message": "No runtime changes detected."})
    return checks


def _expand_config_payload_keys(payload: dict) -> list[str]:
    keys: list[str] = []
    for key, value in payload.items():
        if key in CONFIG_FIELD_PATHS:
            keys.append(key)
            continue
        if key in RuntimeConfig.model_fields and isinstance(value, dict):
            keys.extend(f"{key}.{field}" for field in value if f"{key}.{field}" in CONFIG_FIELD_PATHS)
    return keys


def _changed_config_keys(current: RuntimeConfig, payload: dict) -> list[str]:
    changed: list[str] = []
    for key, value in payload.items():
        if key in CONFIG_FIELD_PATHS:
            if get_config_value(current, key) != value:
                changed.append(key)
            continue
        if key in RuntimeConfig.model_fields and isinstance(value, dict):
            for field, nested_value in value.items():
                nested_key = f"{key}.{field}"
                if nested_key in CONFIG_FIELD_PATHS and get_config_value(current, nested_key) != nested_value:
                    changed.append(nested_key)
    return changed


@asynccontextmanager
async def lifespan(_: FastAPI):
    restore_signal_handlers = install_shutdown_signal_bridge()
    try:
        await brain.start()
        yield
    finally:
        request_shutdown()
        try:
            await brain.stop()
        finally:
            restore_signal_handlers()
            clear_shutdown_request()


app = FastAPI(title="Momo Vision Backend", version="0.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/monitor/assets", StaticFiles(directory=WEB_DIR / "assets"), name="monitor_assets")


@app.get("/")
async def root_monitor():
    return FileResponse(WEB_DIR / "index.html", media_type="text/html")


@app.get("/monitor")
async def monitor():
    return FileResponse(WEB_DIR / "index.html", media_type="text/html")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
async def get_status():
    return brain.snapshot()


@app.websocket("/api/status/ws")
async def websocket_status(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(brain.snapshot().model_dump(mode="json"))
            await asyncio.sleep(STATUS_STREAM_INTERVAL_SEC)
    except WebSocketDisconnect:
        return


@app.get("/api/config")
async def get_config():
    return {
        "config": brain.config,
        "fields": build_field_catalog(brain.config),
        "groups": CONFIG_GROUP_LABELS,
        "editable_keys": sorted(LIVE_EDITABLE_CONFIG_KEYS),
    }


@app.post("/api/config", response_model=ConfigUpdateResponse)
async def update_config(payload: dict):
    try:
        merged = merge_config(brain.config, payload)
    except ValueError as exc:
        return ConfigUpdateResponse(
            applied_config=brain.config,
            validation_errors=[str(exc)],
            effective_changes=[],
            apply_checks=[{"component": "config", "status": "error", "message": "Payload merge failed."}],
            requires_pipeline_restart=False,
        )

    errors = validate_runtime_config(merged)
    if errors:
        return ConfigUpdateResponse(
            applied_config=brain.config,
            validation_errors=errors,
            effective_changes=[],
            apply_checks=[{"component": "config", "status": "error", "message": "Validation failed. Nothing was applied."}],
            requires_pipeline_restart=False,
        )

    if should_prepare_models():
        try:
            await asyncio.to_thread(ensure_runtime_models, merged)
        except Exception as exc:
            return ConfigUpdateResponse(
                applied_config=brain.config,
                validation_errors=[str(exc)],
                effective_changes=[],
                apply_checks=[{"component": "model-download", "status": "error", "message": f"Model preparation failed: {exc}"}],
                requires_pipeline_restart=False,
            )

    changed = _changed_config_keys(brain.config, payload)
    changed_keys = set(changed)
    brain.config = merged

    if changed_keys & {"audio.state_dir"}:
        brain.audio_controller = AudioController(brain.config.audio.state_dir)
        brain.audio_controller.ensure_state_directories()

    if any(key.startswith("light.") for key in changed_keys):
        brain.light_controller.reconfigure(brain.config.light)

    if changed_keys & {"serial.port", "serial.baud_rate"}:
        previous_serial = brain.serial
        previous_serial.close()
        brain.serial = ESP32Link(brain.config.serial.port, brain.config.serial.baud_rate)

    if changed_keys & {
        "camera.source",
        "camera.device_id",
        "camera.width",
        "camera.height",
        "camera.fps",
        "camera.mirror_preview",
        "camera.flip_vertical",
        "yolo.model_path",
        "yolo.device_mode",
    }:
        brain.vision.reconfigure(brain.config)

    if changed_keys & {"yolo.model_path", "yolo.device_mode"}:
        try:
            await asyncio.to_thread(brain._refresh_vision_runtime_stats)
        except Exception as exc:
            brain.state.event_log = [f"YOLO warmup failed after config change: {exc}", *brain.state.event_log][:20]

    apply_checks = await build_apply_checks(payload, brain.config)
    return ConfigUpdateResponse(
        applied_config=brain.config,
        validation_errors=[],
        effective_changes=changed,
        apply_checks=apply_checks,
        requires_pipeline_restart=False,
    )


@app.get("/api/cameras")
async def get_cameras():
    return brain.vision.list_cameras()


@app.get("/api/camera/frame.jpg")
async def get_camera_frame():
    frame = brain.vision.get_snapshot().frame_jpeg
    if frame is None:
        raise HTTPException(status_code=404, detail="No frame available")
    return Response(content=frame, media_type="image/jpeg")


async def camera_frame_stream():
    boundary = b"--frame"
    interval_sec = 1.0 / min(max(brain.config.camera.fps, 1), 15)
    while True:
        frame = brain.vision.get_snapshot().frame_jpeg
        if frame is not None:
            yield (
                boundary
                + b"\r\nContent-Type: image/jpeg\r\nCache-Control: no-store\r\n\r\n"
                + frame
                + b"\r\n"
            )
        await asyncio.sleep(interval_sec)


@app.get("/api/camera/stream.mjpg")
async def stream_camera_frames():
    return StreamingResponse(
        camera_frame_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store",
            "Connection": "keep-alive",
        },
    )


@app.websocket("/api/camera/ws")
async def websocket_camera_frames(websocket: WebSocket):
    await websocket.accept()
    interval_sec = 1.0 / min(max(brain.config.camera.fps, 1), 15)
    try:
        while True:
            frame = brain.vision.get_snapshot().frame_jpeg
            if frame is not None:
                await websocket.send_bytes(frame)
            await asyncio.sleep(interval_sec)
    except WebSocketDisconnect:
        return


@app.post("/api/camera/frame")
async def post_camera_frame(request: Request):
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="empty frame")
    try:
        state = brain.vision.submit_jpeg_frame(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    features = brain._prepare_position_features(state.features)
    if brain.config.camera.source == "browser":
        now = time.monotonic()
        brain.send_servo_for_features(features, state.servo.tracking_source, state.frame_shape, now)
        brain._update_position_audio_for_features(features, state.frame_shape)
    return {
        "track_id": features.track_id,
        "position_state": features.position_state,
        "tracking_source": state.servo.tracking_source,
    }


@app.get("/api/serial/ports")
async def get_serial_ports():
    return ESP32Link.list_ports()


@app.post("/api/control/recenter-servos")
async def recenter_servos():
    payload = brain.serial.send_servo_command(
        brain.config.servo_calibration.left_zero_deg,
        brain.config.servo_calibration.right_zero_deg,
        mode="idle_scan",
        tracking_source="manual",
        led_signal_loss_fade_out_ms=brain.config.led.signal_loss_fade_out_ms,
    )
    return {"command": payload}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the Momo vision backend.")
    parser.add_argument("--host", default=os.getenv("MOMO_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MOMO_PORT", "8000")))
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args(argv)
    uvicorn.run("backend.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main(sys.argv[1:])
