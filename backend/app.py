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

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.audio.position_audio import PositionAudioPlayer
from backend.config import build_field_catalog, merge_config, validate_runtime_config
from backend.device_utils import backend_label_for_device, expected_accelerator_label, expected_vision_backend_label
from backend.model_manager import ensure_runtime_models
from backend.runtime_shutdown import clear_shutdown_request, install_shutdown_signal_bridge, request_shutdown
from backend.serial.esp32_link import ESP32Link
from backend.servo.geometry import compute_servo_angles
from backend.state_machine import RuntimeState
from backend.storage.csv_logger import append_audience_snapshot
from backend.telemetry.system_stats import capture_process_footprint, diff_process_footprint, get_system_stats
from backend.types import AudienceFeatures, ConfigUpdateResponse, PipelineStage, RuntimeComponentStats, RuntimeConfig, SystemMode
from backend.vision.features import (
    POSITION_HORIZONTAL_CLASSES,
    classify_distance,
    classify_horizontal_position,
    combine_position_state,
    normalize_position_distance,
)
from backend.vision.runtime import VisionRuntime

SERIAL_REFRESH_INTERVAL_SEC = 2.0
WEB_DIR = Path(__file__).resolve().parent / "web"


class Brain:
    def __init__(self) -> None:
        self.config = RuntimeConfig()
        self.state = RuntimeState()
        self.serial = ESP32Link(self.config.serial_port, self.config.serial_baud_rate)
        self.vision = VisionRuntime(self.config)
        self.position_audio = PositionAudioPlayer()
        self.yolo_person_runtime = RuntimeComponentStats(
            requested_mode=self.config.yolo_device_mode,
            effective_device=self.vision.detector.device,
            backend=backend_label_for_device(self.vision.detector.device),
            selection_source="default",
        )
        self.last_target_seen = 0.0
        self.lock_started_at: float | None = None
        self.background_tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        clear_shutdown_request()
        self.position_audio.ensure_state_directories()
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
        vision_expected = expected_vision_backend_label(self.config.yolo_device_mode)
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
            requested_mode=self.config.yolo_device_mode,
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
        snap.camera_device_id = self.config.camera_device_id
        snap.camera_mode = f"{self.config.camera_width}x{self.config.camera_height}@{self.config.camera_fps}"
        snap.yolo_detect_fps = self.vision.detect_fps()
        snap.yolo_person_runtime = self.yolo_person_runtime
        snap.position_audio = self.position_audio.snapshot()
        return snap

    def send_servo_for_features(self, features, tracking_source: str) -> None:
        servo = self._compute_servo_from_features(features, tracking_source)
        self.state.servo = servo
        if features.track_id is None:
            return
        led_left_pct, led_right_pct = self._compute_led_brightness_from_features(features)
        self.serial.send_servo_command(
            servo.left_deg,
            servo.right_deg,
            mode="track",
            tracking_source=servo.tracking_source,
            led_left_pct=led_left_pct,
            led_right_pct=led_right_pct,
            led_signal_loss_fade_out_ms=self.config.led_signal_loss_fade_out_ms,
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
            await asyncio.sleep(max(0.02, 1.0 / max(1, self.config.camera_fps)))

    def _update_mode_from_vision(self) -> None:
        now = time.monotonic()
        vision = self.vision.get_snapshot()
        features = self._prepare_position_features(vision.features)
        self.state.audience = features
        self.send_servo_for_features(features, vision.servo.tracking_source)
        self._update_position_audio_for_features(features)

        lock_threshold = self.config.lock_bbox_threshold_ratio
        unlock_threshold = self.config.unlock_bbox_threshold_ratio or lock_threshold
        threshold = unlock_threshold if self.state.mode in {SystemMode.TRACKING, SystemMode.RECONNECTING} else lock_threshold

        if features.track_id is None or features.bbox_area_ratio < threshold:
            if self.state.mode == SystemMode.TRACKING and now - self.last_target_seen <= self.config.lost_timeout_ms / 1000:
                self.state.set_mode(SystemMode.RECONNECTING, "Target temporarily lost")
            elif now - self.last_target_seen > self.config.lost_timeout_ms / 1000:
                self.state.set_mode(SystemMode.IDLE)
                self.state.locked_track_id = None
                self.lock_started_at = None
            return

        self.last_target_seen = now
        if self.lock_started_at is None:
            self.lock_started_at = now
            self.state.set_mode(SystemMode.ACQUIRING)
            return
        if now - self.lock_started_at < self.config.enter_debounce_ms / 1000:
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
            distance = classify_distance(features.bbox_area_ratio, self.config.lock_bbox_threshold_ratio)
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

    def _update_position_audio_for_features(self, features: AudienceFeatures) -> None:
        result = self.position_audio.handle_state(features.position_state)
        if result.message:
            self.state.event_log = [result.message, *self.state.event_log][:20]

    def _compute_servo_from_features(self, features, tracking_source: str):
        servo = compute_servo_angles(
            target_x_norm=features.center_x_norm,
            bbox_area_ratio=features.bbox_area_ratio,
            left_zero_deg=self.config.servo_left_zero_deg,
            right_zero_deg=self.config.servo_right_zero_deg,
            eye_spacing_cm=self.config.servo_eye_spacing_cm,
            left_limits=(self.config.servo_left_min_deg, self.config.servo_left_max_deg),
            right_limits=(self.config.servo_right_min_deg, self.config.servo_right_max_deg),
        )
        servo.left_deg = self._apply_servo_output_calibration(
            angle=servo.left_deg,
            zero_deg=self.config.servo_left_zero_deg,
            min_deg=self.config.servo_left_min_deg,
            max_deg=self.config.servo_left_max_deg,
            gain=self.config.servo_left_gain,
            trim_deg=self.config.servo_left_trim_deg,
        )
        servo.right_deg = self._apply_servo_output_calibration(
            angle=servo.right_deg,
            zero_deg=self.config.servo_right_zero_deg,
            min_deg=self.config.servo_right_min_deg,
            max_deg=self.config.servo_right_max_deg,
            gain=self.config.servo_right_gain,
            trim_deg=self.config.servo_right_trim_deg,
        )
        servo.tracking_source = tracking_source
        return servo

    def _compute_led_brightness_from_features(self, features) -> tuple[float, float]:
        midpoint_x = features.center_x_norm
        midpoint_x = min(max(midpoint_x, 0.0), 1.0)
        if self.config.servo_output_inverted:
            midpoint_x = 1.0 - midpoint_x
        if self.config.led_left_right_inverted:
            midpoint_x = 1.0 - midpoint_x

        centered_midpoint = (midpoint_x - 0.5) * 2.0
        midpoint_sign = -1.0 if centered_midpoint < 0 else 1.0
        midpoint_magnitude = abs(centered_midpoint)
        deadzone = self.config.led_midpoint_deadzone_norm
        if midpoint_magnitude <= deadzone:
            midpoint_magnitude = 0.0
        else:
            midpoint_magnitude = (midpoint_magnitude - deadzone) / (1.0 - deadzone)

        midpoint_magnitude = min(midpoint_magnitude * self.config.led_midpoint_response_gain, 1.0)
        midpoint_magnitude = midpoint_magnitude ** self.config.led_midpoint_response_gamma
        midpoint_x = 0.5 + ((midpoint_sign * midpoint_magnitude) / 2.0)

        brightness_span = self.config.led_max_brightness_pct - self.config.led_min_brightness_pct
        left_pct = self.config.led_min_brightness_pct + ((1.0 - midpoint_x) * brightness_span)
        right_pct = self.config.led_min_brightness_pct + (midpoint_x * brightness_span)

        if self.config.led_brightness_output_inverted:
            brightness_total = self.config.led_min_brightness_pct + self.config.led_max_brightness_pct
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
        if self.config.servo_output_inverted:
            delta = -delta
        calibrated = zero_deg + (delta * gain) + trim_deg
        return round(min(max(calibrated, min_deg), max_deg), 2)


brain = Brain()


def should_prepare_models() -> bool:
    return os.getenv("MOMO_SKIP_MODEL_BOOTSTRAP") != "1"


async def build_apply_checks(payload: dict, config: RuntimeConfig) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    changed = set(payload.keys())

    if changed & {"camera_source", "camera_device_id", "camera_width", "camera_height", "camera_fps", "camera_mirror_preview", "camera_flip_vertical"}:
        orientation = f"hflip={'on' if config.camera_mirror_preview else 'off'}, vflip={'on' if config.camera_flip_vertical else 'off'}"
        if config.camera_source == "browser":
            checks.append(
                {
                    "component": "vision",
                    "status": "ok",
                    "message": (
                        f"Browser camera config staged: {config.camera_width}x{config.camera_height}@{config.camera_fps}, "
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
                        f"Backend capture reconfigured to device {config.camera_device_id} at "
                        f"{config.camera_width}x{config.camera_height}@{config.camera_fps}, {orientation}."
                    ),
                }
            )

    if changed & {"yolo_model_path", "yolo_device_mode"}:
        checks.append({"component": "vision-model", "status": "ok", "message": f"YOLO model paths updated and verified. Device mode is {config.yolo_device_mode}."})

    if changed & {"serial_port", "serial_baud_rate"}:
        if config.serial_port == "auto":
            message = f"Serial reconfigured to auto detect at {config.serial_baud_rate} baud."
            status = "ok" if brain.serial.connected else "warning"
        else:
            message = f"Serial reconfigured to {config.serial_port} at {config.serial_baud_rate} baud."
            status = "ok" if brain.serial.connected else "warning"
            if not brain.serial.connected:
                message += " Port not connected right now."
        checks.append({"component": "serial", "status": status, "message": message})

    if changed & {
        "servo_left_zero_deg",
        "servo_right_zero_deg",
        "servo_output_inverted",
        "servo_left_trim_deg",
        "servo_right_trim_deg",
        "servo_left_gain",
        "servo_right_gain",
        "servo_eye_spacing_cm",
        "servo_left_min_deg",
        "servo_left_max_deg",
        "servo_right_min_deg",
        "servo_right_max_deg",
        "servo_smoothing_alpha",
        "servo_max_speed_deg_per_sec",
    }:
        checks.append({"component": "servo", "status": "ok", "message": "Servo math config updated and will apply on next tracking update."})

    if changed & {
        "led_min_brightness_pct",
        "led_max_brightness_pct",
        "led_midpoint_response_gain",
        "led_midpoint_response_gamma",
        "led_midpoint_deadzone_norm",
        "led_signal_loss_fade_out_ms",
        "led_brightness_output_inverted",
        "led_left_right_inverted",
    }:
        checks.append({"component": "led", "status": "ok", "message": "LED response config updated and will apply on next tracking update."})

    if changed & {
        "lock_bbox_threshold_ratio",
        "unlock_bbox_threshold_ratio",
        "enter_debounce_ms",
        "exit_debounce_ms",
        "lost_timeout_ms",
    }:
        checks.append({"component": "vision-rules", "status": "ok", "message": "Person detection thresholds updated."})

    if not checks:
        checks.append({"component": "config", "status": "ok", "message": "No runtime changes detected."})
    return checks


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


@app.get("/api/config")
async def get_config():
    return {"config": brain.config, "fields": build_field_catalog(brain.config)}


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

    changed = [key for key, value in payload.items() if getattr(brain.config, key) != value]
    changed_keys = set(changed)
    brain.config = merged

    if changed_keys & {"serial_port", "serial_baud_rate"}:
        previous_serial = brain.serial
        previous_serial.close()
        brain.serial = ESP32Link(brain.config.serial_port, brain.config.serial_baud_rate)

    if changed_keys & {
        "camera_source",
        "camera_device_id",
        "camera_width",
        "camera_height",
        "camera_fps",
        "camera_mirror_preview",
        "camera_flip_vertical",
        "yolo_model_path",
        "yolo_device_mode",
    }:
        brain.vision.reconfigure(brain.config)

    if changed_keys & {"yolo_model_path", "yolo_device_mode"}:
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
    if brain.config.camera_source == "browser":
        brain.send_servo_for_features(features, state.servo.tracking_source)
        brain._update_position_audio_for_features(features)
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
        brain.config.servo_left_zero_deg,
        brain.config.servo_right_zero_deg,
        mode="idle_scan",
        tracking_source="manual",
        led_signal_loss_fade_out_ms=brain.config.led_signal_loss_fade_out_ms,
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
