from __future__ import annotations

import platform

from pydantic import ValidationError

from backend.types import ConfigField, RuntimeConfig


FIELD_DESCRIPTIONS: dict[str, tuple[str, str, str | None]] = {
    "camera_source": ("Camera Source", "Choose browser-uploaded frames or backend OpenCV capture.", None),
    "camera_device_id": ("Camera", "Camera device identifier.", None),
    "camera_width": ("Width", "Requested camera capture width.", ">=320"),
    "camera_height": ("Height", "Requested camera capture height.", ">=240"),
    "camera_fps": ("FPS", "Requested camera frame rate.", "1-60"),
    "camera_mirror_preview": ("Mirror Horizontal", "Flip the camera frame left-to-right before detection and preview.", None),
    "camera_flip_vertical": ("Flip Vertical", "Flip the camera frame top-to-bottom before detection and preview.", None),
    "yolo_model_path": ("YOLO Model Path", "YOLO person detection model path.", None),
    "yolo_device_mode": ("YOLO Device", "Device mode for person detection: auto, cpu, or accelerator for this OS.", None),
    "lock_bbox_threshold_ratio": ("Lock Threshold", "Person bbox area ratio required to enter lock mode.", "0.01-0.95"),
    "unlock_bbox_threshold_ratio": ("Unlock Threshold", "Person bbox area ratio required to remain locked.", "0.01-0.95"),
    "enter_debounce_ms": ("Enter Debounce", "Continuous time above threshold before locking.", ">=0"),
    "exit_debounce_ms": ("Exit Debounce", "Continuous time below threshold before reconnecting.", ">=0"),
    "lost_timeout_ms": ("Lost Timeout", "Time window to reconnect the same audience.", ">=0"),
    "serial_port": ("Serial Port", "Serial device path or auto detection.", None),
    "serial_baud_rate": ("Baud Rate", "UART speed for ESP32 serial communication.", ">=1200"),
    "servo_left_zero_deg": ("Left Zero", "Neutral angle for the left eye servo.", "0-180"),
    "servo_right_zero_deg": ("Right Zero", "Neutral angle for the right eye servo.", "0-180"),
    "servo_output_inverted": ("Invert Output", "Mirror left and right servo output around each servo zero angle.", None),
    "servo_left_trim_deg": ("Left Trim", "Fixed angle offset applied after left servo scaling.", "-90-90"),
    "servo_right_trim_deg": ("Right Trim", "Fixed angle offset applied after right servo scaling.", "-90-90"),
    "servo_left_gain": ("Left Gain", "Multiplier applied to the left servo delta from its zero angle.", ">0"),
    "servo_right_gain": ("Right Gain", "Multiplier applied to the right servo delta from its zero angle.", ">0"),
    "servo_eye_spacing_cm": ("Eye Spacing", "Distance between the two servo eyes used by the aiming geometry.", ">=1"),
    "servo_left_min_deg": ("Left Min", "Left servo lower clamp.", "0-180"),
    "servo_left_max_deg": ("Left Max", "Left servo upper clamp.", "0-180"),
    "servo_right_min_deg": ("Right Min", "Right servo lower clamp.", "0-180"),
    "servo_right_max_deg": ("Right Max", "Right servo upper clamp.", "0-180"),
    "led_min_brightness_pct": ("LED Min", "Minimum LED brightness percentage sent to all four strips.", "0-100"),
    "led_max_brightness_pct": ("LED Max", "Maximum LED brightness percentage sent to all four strips.", "0-100"),
    "led_midpoint_response_gain": ("LED Midpoint Gain", "Multiplier applied to midpoint offset from screen center before LED mapping.", ">0"),
    "led_midpoint_response_gamma": ("LED Midpoint Gamma", "Curve applied to midpoint offset after gain.", ">0"),
    "led_midpoint_deadzone_norm": ("LED Midpoint Deadzone", "Center deadzone for midpoint offset.", "0-0.99"),
    "led_signal_loss_fade_out_ms": ("LED Signal Loss Fade", "Fade-out time in milliseconds used by the ESP32 after serial tracking updates stop.", ">=0"),
    "led_brightness_output_inverted": ("LED Invert", "Invert LED brightness output so 100% becomes 0% and 0% becomes 100%.", None),
    "led_left_right_inverted": ("LED Swap Left/Right", "Swap left and right LED response to the tracked midpoint.", None),
    "servo_smoothing_alpha": ("Servo Smoothing", "One-pole smoothing factor for servo motion.", "0-1"),
    "servo_max_speed_deg_per_sec": ("Servo Max Speed", "Servo speed cap.", ">=1"),
}

FIELD_GROUPS: dict[str, str] = {
    "camera_source": "camera",
    "camera_device_id": "camera",
    "camera_width": "camera",
    "camera_height": "camera",
    "camera_fps": "camera",
    "camera_mirror_preview": "camera",
    "camera_flip_vertical": "camera",
    "yolo_model_path": "vision",
    "yolo_device_mode": "vision",
    "lock_bbox_threshold_ratio": "vision",
    "unlock_bbox_threshold_ratio": "vision",
    "enter_debounce_ms": "vision",
    "exit_debounce_ms": "vision",
    "lost_timeout_ms": "vision",
    "serial_port": "serial",
    "serial_baud_rate": "serial",
    "servo_left_zero_deg": "servo",
    "servo_right_zero_deg": "servo",
    "servo_output_inverted": "servo",
    "servo_left_trim_deg": "servo",
    "servo_right_trim_deg": "servo",
    "servo_left_gain": "servo",
    "servo_right_gain": "servo",
    "servo_eye_spacing_cm": "servo",
    "servo_left_min_deg": "servo",
    "servo_left_max_deg": "servo",
    "servo_right_min_deg": "servo",
    "servo_right_max_deg": "servo",
    "led_min_brightness_pct": "led",
    "led_max_brightness_pct": "led",
    "led_midpoint_response_gain": "led",
    "led_midpoint_response_gamma": "led",
    "led_midpoint_deadzone_norm": "led",
    "led_signal_loss_fade_out_ms": "led",
    "led_brightness_output_inverted": "led",
    "led_left_right_inverted": "led",
    "servo_smoothing_alpha": "servo",
    "servo_max_speed_deg_per_sec": "servo",
}


def build_field_catalog(config: RuntimeConfig) -> list[ConfigField]:
    fields: list[ConfigField] = []
    defaults = RuntimeConfig()
    for key, field_info in RuntimeConfig.model_fields.items():
        label, description, valid_range = FIELD_DESCRIPTIONS.get(
            key,
            (key.replace("_", " ").title(), f"Runtime config for {key}.", None),
        )
        value = getattr(config, key)
        if key == "unlock_bbox_threshold_ratio" and value is None:
            value = config.lock_bbox_threshold_ratio
        default = getattr(defaults, key)
        field_type = _infer_type(value if value is not None else default)
        fields.append(
            ConfigField(
                key=key,
                label=label,
                description=description,
                type=field_type,
                default=default,
                value=value,
                valid_range=valid_range,
                enum=_enum_for_field(key),
                applies_to=FIELD_GROUPS.get(key, "general"),
            )
        )
    return fields


def _infer_type(value: object) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, list):
        return "string[]"
    return "string"


def _enum_for_field(key: str) -> list[str] | None:
    if key == "camera_source":
        return ["browser", "backend"]
    if key == "yolo_device_mode":
        accelerator = "mps" if platform.system() == "Darwin" else "gpu"
        return ["auto", "cpu", accelerator]
    return None


def validate_runtime_config(candidate: RuntimeConfig) -> list[str]:
    errors: list[str] = []
    if candidate.camera_source not in {"browser", "backend"}:
        errors.append("camera_source must be one of ['browser', 'backend']")
    if candidate.camera_width < 320:
        errors.append("camera_width must be >= 320")
    if candidate.camera_height < 240:
        errors.append("camera_height must be >= 240")
    if not 1 <= candidate.camera_fps <= 60:
        errors.append("camera_fps must be between 1 and 60")
    if not 0.01 <= candidate.lock_bbox_threshold_ratio <= 0.95:
        errors.append("lock_bbox_threshold_ratio must be between 0.01 and 0.95")
    unlock = (
        candidate.unlock_bbox_threshold_ratio
        if candidate.unlock_bbox_threshold_ratio is not None
        else candidate.lock_bbox_threshold_ratio
    )
    if not 0.01 <= unlock <= 0.95:
        errors.append("unlock_bbox_threshold_ratio must be between 0.01 and 0.95")
    if candidate.enter_debounce_ms < 0:
        errors.append("enter_debounce_ms must be >= 0")
    if candidate.exit_debounce_ms < 0:
        errors.append("exit_debounce_ms must be >= 0")
    if candidate.lost_timeout_ms < 0:
        errors.append("lost_timeout_ms must be >= 0")

    accelerator = "mps" if platform.system() == "Darwin" else "gpu"
    allowed_device_modes = {"auto", "cpu", accelerator}
    if candidate.yolo_device_mode not in allowed_device_modes:
        errors.append(f"yolo_device_mode must be one of {sorted(allowed_device_modes)}")
    if candidate.serial_baud_rate < 1200:
        errors.append("serial_baud_rate must be >= 1200")
    if candidate.servo_left_gain <= 0:
        errors.append("servo_left_gain must be > 0")
    if candidate.servo_right_gain <= 0:
        errors.append("servo_right_gain must be > 0")
    if candidate.servo_eye_spacing_cm < 1:
        errors.append("servo_eye_spacing_cm must be >= 1")
    if not 0 <= candidate.servo_left_min_deg <= candidate.servo_left_max_deg <= 180:
        errors.append("servo_left_min_deg and servo_left_max_deg must be ordered within 0-180")
    if not 0 <= candidate.servo_right_min_deg <= candidate.servo_right_max_deg <= 180:
        errors.append("servo_right_min_deg and servo_right_max_deg must be ordered within 0-180")
    if not 0 <= candidate.led_min_brightness_pct <= 100:
        errors.append("led_min_brightness_pct must be between 0 and 100")
    if not 0 <= candidate.led_max_brightness_pct <= 100:
        errors.append("led_max_brightness_pct must be between 0 and 100")
    if candidate.led_min_brightness_pct > candidate.led_max_brightness_pct:
        errors.append("led_min_brightness_pct must be <= led_max_brightness_pct")
    if candidate.led_midpoint_response_gain <= 0:
        errors.append("led_midpoint_response_gain must be > 0")
    if candidate.led_midpoint_response_gamma <= 0:
        errors.append("led_midpoint_response_gamma must be > 0")
    if not 0 <= candidate.led_midpoint_deadzone_norm < 1:
        errors.append("led_midpoint_deadzone_norm must be between 0 and 1 (exclusive of 1)")
    if candidate.led_signal_loss_fade_out_ms < 0:
        errors.append("led_signal_loss_fade_out_ms must be >= 0")
    if not 0 <= candidate.servo_smoothing_alpha <= 1:
        errors.append("servo_smoothing_alpha must be between 0 and 1")
    if candidate.servo_max_speed_deg_per_sec < 1:
        errors.append("servo_max_speed_deg_per_sec must be >= 1")
    return errors


def merge_config(current: RuntimeConfig, payload: dict) -> RuntimeConfig:
    try:
        merged = current.model_copy(update=payload)
        return RuntimeConfig.model_validate(merged.model_dump())
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
