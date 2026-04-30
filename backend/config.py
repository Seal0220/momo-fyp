from __future__ import annotations

import platform
from typing import Any

from pydantic import BaseModel, Field, ValidationError


class ConfigField(BaseModel):
    key: str
    label: str
    description: str
    type: str
    default: Any
    value: Any
    valid_range: str | None = None
    enum: list[str] | None = None
    applies_to: str
    requires_restart: bool = False


class RuntimeConfig(BaseModel):
    class Camera(BaseModel):
        source: str = "backend"
        device_id: str = "default"
        width: int = 1920
        height: int = 1080
        fps: int = 12
        mirror_preview: bool = False
        flip_vertical: bool = False

    class Yolo(BaseModel):
        model_path: str = "model/yolo/yolo26n.pt"
        device_mode: str = "auto"

    class Tracking(BaseModel):
        lock_bbox_threshold_ratio: float = 0.12
        unlock_bbox_threshold_ratio: float | None = None
        enter_debounce_ms: int = 1000
        exit_debounce_ms: int = 500
        lost_timeout_ms: int = 5000

    class Distance(BaseModel):
        near_bbox_threshold_ratio: float = 0.40
        mid_bbox_threshold_ratio: float = 0.20

    class Audio(BaseModel):
        state_dir: str = "backend/audio/interaction_states"
        full_frame_threshold_ratio: float = 0.35

    class Light(BaseModel):
        side_led_count: int = 15
        active_led_count_per_cycle: int = 5
        super_close_bbox_threshold_ratio: float = 0.35
        empty_cycle_sec: float = 4.0
        empty_brightness_level: float = 1.0
        present_start_after_sec: float = 3.0
        present_full_after_sec: float = 7.0
        present_start_cycle_sec: float = 2.0
        present_min_cycle_sec: float = 0.5
        present_start_brightness_level: float = 2.0
        present_max_brightness_level: float = 8.0
        super_close_brightness_level: float = 10.0

    class Serial(BaseModel):
        port: str = "auto"
        baud_rate: int = 115200

    class ServoCalibration(BaseModel):
        left_zero_deg: float = 87.0
        right_zero_deg: float = 96.0
        output_inverted: bool = False
        left_trim_deg: float = 0.0
        right_trim_deg: float = 0.0
        left_gain: float = 2.5
        right_gain: float = 2.5
        eye_spacing_cm: int = 13
        left_min_deg: float = 45.0
        left_max_deg: float = 135.0
        right_min_deg: float = 45.0
        right_max_deg: float = 135.0

    class ServoMotion(BaseModel):
        smoothing_alpha: float = 0.25
        max_speed_deg_per_sec: float = 180.0

    class Led(BaseModel):
        min_brightness_pct: float = 0.0
        max_brightness_pct: float = 100.0
        midpoint_response_gain: float = 2.5
        midpoint_response_gamma: float = 0.75
        midpoint_deadzone_norm: float = 0.0
        signal_loss_fade_out_ms: int = 3000
        brightness_output_inverted: bool = False
        left_right_inverted: bool = False

    camera: Camera = Field(default_factory=Camera)
    yolo: Yolo = Field(default_factory=Yolo)
    tracking: Tracking = Field(default_factory=Tracking)
    distance: Distance = Field(default_factory=Distance)
    audio: Audio = Field(default_factory=Audio)
    light: Light = Field(default_factory=Light)
    serial: Serial = Field(default_factory=Serial)
    servo_calibration: ServoCalibration = Field(default_factory=ServoCalibration)
    servo_motion: ServoMotion = Field(default_factory=ServoMotion)
    led: Led = Field(default_factory=Led)


class ConfigUpdateResponse(BaseModel):
    applied_config: RuntimeConfig
    validation_errors: list[str]
    effective_changes: list[str]
    apply_checks: list[dict[str, str]] = Field(default_factory=list)
    requires_pipeline_restart: bool


CONFIG_GROUP_LABELS: dict[str, str] = {
    "camera": "Camera",
    "yolo": "YOLO",
    "tracking": "Tracking",
    "distance": "Distance",
    "audio": "Audio",
    "light": "Light",
    "serial": "Serial",
    "servo_calibration": "Servo Calibration",
    "servo_motion": "Servo Motion",
    "led": "LED",
    "general": "General",
}

CONFIG_FIELD_PATHS: dict[str, tuple[str, str]] = {
    "camera.source": ("camera", "source"),
    "camera.device_id": ("camera", "device_id"),
    "camera.width": ("camera", "width"),
    "camera.height": ("camera", "height"),
    "camera.fps": ("camera", "fps"),
    "camera.mirror_preview": ("camera", "mirror_preview"),
    "camera.flip_vertical": ("camera", "flip_vertical"),
    "yolo.model_path": ("yolo", "model_path"),
    "yolo.device_mode": ("yolo", "device_mode"),
    "tracking.lock_bbox_threshold_ratio": ("tracking", "lock_bbox_threshold_ratio"),
    "tracking.unlock_bbox_threshold_ratio": ("tracking", "unlock_bbox_threshold_ratio"),
    "distance.near_bbox_threshold_ratio": ("distance", "near_bbox_threshold_ratio"),
    "distance.mid_bbox_threshold_ratio": ("distance", "mid_bbox_threshold_ratio"),
    "audio.state_dir": ("audio", "state_dir"),
    "audio.full_frame_threshold_ratio": ("audio", "full_frame_threshold_ratio"),
    "light.side_led_count": ("light", "side_led_count"),
    "light.active_led_count_per_cycle": ("light", "active_led_count_per_cycle"),
    "light.super_close_bbox_threshold_ratio": ("light", "super_close_bbox_threshold_ratio"),
    "light.empty_cycle_sec": ("light", "empty_cycle_sec"),
    "light.empty_brightness_level": ("light", "empty_brightness_level"),
    "light.present_start_after_sec": ("light", "present_start_after_sec"),
    "light.present_full_after_sec": ("light", "present_full_after_sec"),
    "light.present_start_cycle_sec": ("light", "present_start_cycle_sec"),
    "light.present_min_cycle_sec": ("light", "present_min_cycle_sec"),
    "light.present_start_brightness_level": ("light", "present_start_brightness_level"),
    "light.present_max_brightness_level": ("light", "present_max_brightness_level"),
    "light.super_close_brightness_level": ("light", "super_close_brightness_level"),
    "tracking.enter_debounce_ms": ("tracking", "enter_debounce_ms"),
    "tracking.exit_debounce_ms": ("tracking", "exit_debounce_ms"),
    "tracking.lost_timeout_ms": ("tracking", "lost_timeout_ms"),
    "serial.port": ("serial", "port"),
    "serial.baud_rate": ("serial", "baud_rate"),
    "servo_calibration.left_zero_deg": ("servo_calibration", "left_zero_deg"),
    "servo_calibration.right_zero_deg": ("servo_calibration", "right_zero_deg"),
    "servo_calibration.output_inverted": ("servo_calibration", "output_inverted"),
    "servo_calibration.left_trim_deg": ("servo_calibration", "left_trim_deg"),
    "servo_calibration.right_trim_deg": ("servo_calibration", "right_trim_deg"),
    "servo_calibration.left_gain": ("servo_calibration", "left_gain"),
    "servo_calibration.right_gain": ("servo_calibration", "right_gain"),
    "servo_calibration.eye_spacing_cm": ("servo_calibration", "eye_spacing_cm"),
    "servo_calibration.left_min_deg": ("servo_calibration", "left_min_deg"),
    "servo_calibration.left_max_deg": ("servo_calibration", "left_max_deg"),
    "servo_calibration.right_min_deg": ("servo_calibration", "right_min_deg"),
    "servo_calibration.right_max_deg": ("servo_calibration", "right_max_deg"),
    "led.min_brightness_pct": ("led", "min_brightness_pct"),
    "led.max_brightness_pct": ("led", "max_brightness_pct"),
    "led.midpoint_response_gain": ("led", "midpoint_response_gain"),
    "led.midpoint_response_gamma": ("led", "midpoint_response_gamma"),
    "led.midpoint_deadzone_norm": ("led", "midpoint_deadzone_norm"),
    "led.signal_loss_fade_out_ms": ("led", "signal_loss_fade_out_ms"),
    "led.brightness_output_inverted": ("led", "brightness_output_inverted"),
    "led.left_right_inverted": ("led", "left_right_inverted"),
    "servo_motion.smoothing_alpha": ("servo_motion", "smoothing_alpha"),
    "servo_motion.max_speed_deg_per_sec": ("servo_motion", "max_speed_deg_per_sec"),
}

LIVE_EDITABLE_CONFIG_KEYS = {
    "camera.width",
    "camera.height",
    "camera.fps",
    "camera.mirror_preview",
    "camera.flip_vertical",
    "tracking.lock_bbox_threshold_ratio",
    "tracking.unlock_bbox_threshold_ratio",
    "distance.near_bbox_threshold_ratio",
    "distance.mid_bbox_threshold_ratio",
    "audio.state_dir",
    "audio.full_frame_threshold_ratio",
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
    "tracking.enter_debounce_ms",
    "tracking.exit_debounce_ms",
    "tracking.lost_timeout_ms",
    "serial.port",
    "serial.baud_rate",
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
    "led.min_brightness_pct",
    "led.max_brightness_pct",
    "led.midpoint_response_gain",
    "led.midpoint_response_gamma",
    "led.midpoint_deadzone_norm",
    "led.signal_loss_fade_out_ms",
    "led.brightness_output_inverted",
    "led.left_right_inverted",
}

FIELD_DESCRIPTIONS: dict[str, tuple[str, str, str | None]] = {
    "camera.source": ("Camera Source", "Choose browser-uploaded frames or backend OpenCV capture.", None),
    "camera.device_id": ("Camera", "Camera device identifier.", None),
    "camera.width": ("Width", "Requested camera capture width.", ">=320"),
    "camera.height": ("Height", "Requested camera capture height.", ">=240"),
    "camera.fps": ("FPS", "Requested camera frame rate.", "1-60"),
    "camera.mirror_preview": ("Mirror Horizontal", "Flip the camera frame left-to-right before detection and preview.", None),
    "camera.flip_vertical": ("Flip Vertical", "Flip the camera frame top-to-bottom before detection and preview.", None),
    "yolo.model_path": ("YOLO Model Path", "YOLO person detection model path.", None),
    "yolo.device_mode": ("YOLO Device", "Device mode for person detection: auto, cpu, or accelerator for this OS.", None),
    "tracking.lock_bbox_threshold_ratio": ("Lock Threshold", "Person bbox area ratio required to enter lock mode.", "0.01-0.95"),
    "tracking.unlock_bbox_threshold_ratio": ("Unlock Threshold", "Person bbox area ratio required to remain locked.", "0.01-0.95"),
    "distance.near_bbox_threshold_ratio": ("Near Distance", "Person bbox area ratio classified as near.", "0.001-0.95"),
    "distance.mid_bbox_threshold_ratio": ("Mid Distance", "Person bbox area ratio classified as mid distance.", "0.001-0.95"),
    "audio.state_dir": ("Audio State Dir", "Folder containing no_one, left, center, right, and full audio subfolders.", None),
    "audio.full_frame_threshold_ratio": ("Audio Full Threshold", "Single-person bbox area ratio that triggers the audio full-frame state.", "0.01-0.99"),
    "light.side_led_count": ("LEDs Per Side", "Number of independently addressed LEDs on each side.", ">=1"),
    "light.active_led_count_per_cycle": ("Active LEDs Per Cycle", "Random LEDs lit per side on each blinking cycle.", "1-side count"),
    "light.super_close_bbox_threshold_ratio": ("Super Close Threshold", "Single-person bbox area ratio that triggers full light state and solid 10A output.", "0.01-0.99"),
    "light.empty_cycle_sec": ("Empty Cycle", "Blink cycle in seconds when a side has no person.", ">0"),
    "light.empty_brightness_level": ("Empty Level", "Brightness level for empty breathing output.", "1A-10A"),
    "light.present_start_after_sec": ("Present Start Time", "Seconds before the present mapping begins.", ">=0"),
    "light.present_full_after_sec": ("Present Full Time", "Seconds where present mapping reaches maximum speed and level.", "> start"),
    "light.present_start_cycle_sec": ("Present Start Cycle", "Blink cycle when presence reaches the start time.", ">0"),
    "light.present_min_cycle_sec": ("Present Min Cycle", "Fastest blink cycle after sustained presence.", ">0"),
    "light.present_start_brightness_level": ("Present Start Level", "Brightness level when presence reaches the start time.", "1A-10A"),
    "light.present_max_brightness_level": ("Present Max Level", "Brightness level after sustained presence.", "1A-10A"),
    "light.super_close_brightness_level": ("Super Close Level", "Solid brightness level during super-close latch.", "1A-10A"),
    "tracking.enter_debounce_ms": ("Enter Debounce", "Continuous time above threshold before locking.", ">=0"),
    "tracking.exit_debounce_ms": ("Exit Debounce", "Continuous time below threshold before reconnecting.", ">=0"),
    "tracking.lost_timeout_ms": ("Lost Timeout", "Time window to reconnect the same audience.", ">=0"),
    "serial.port": ("Serial Port", "Serial device path or auto detection.", None),
    "serial.baud_rate": ("Baud Rate", "UART speed for ESP32 serial communication.", ">=1200"),
    "servo_calibration.left_zero_deg": ("Left Zero", "Neutral angle for the left eye servo.", "0-180"),
    "servo_calibration.right_zero_deg": ("Right Zero", "Neutral angle for the right eye servo.", "0-180"),
    "servo_calibration.output_inverted": ("Invert Output", "Mirror left and right servo output around each servo zero angle.", None),
    "servo_calibration.left_trim_deg": ("Left Trim", "Fixed angle offset applied after left servo scaling.", "-90-90"),
    "servo_calibration.right_trim_deg": ("Right Trim", "Fixed angle offset applied after right servo scaling.", "-90-90"),
    "servo_calibration.left_gain": ("Left Gain", "Multiplier applied to the left servo delta from its zero angle.", ">0"),
    "servo_calibration.right_gain": ("Right Gain", "Multiplier applied to the right servo delta from its zero angle.", ">0"),
    "servo_calibration.eye_spacing_cm": ("Eye Spacing", "Distance between the two servo eyes used by the aiming geometry.", ">=1"),
    "servo_calibration.left_min_deg": ("Left Min", "Left servo lower clamp.", "0-180"),
    "servo_calibration.left_max_deg": ("Left Max", "Left servo upper clamp.", "0-180"),
    "servo_calibration.right_min_deg": ("Right Min", "Right servo lower clamp.", "0-180"),
    "servo_calibration.right_max_deg": ("Right Max", "Right servo upper clamp.", "0-180"),
    "led.min_brightness_pct": ("LED Min", "Minimum LED brightness percentage sent to all four strips.", "0-100"),
    "led.max_brightness_pct": ("LED Max", "Maximum LED brightness percentage sent to all four strips.", "0-100"),
    "led.midpoint_response_gain": ("LED Midpoint Gain", "Multiplier applied to midpoint offset from screen center before LED mapping.", ">0"),
    "led.midpoint_response_gamma": ("LED Midpoint Gamma", "Curve applied to midpoint offset after gain.", ">0"),
    "led.midpoint_deadzone_norm": ("LED Midpoint Deadzone", "Center deadzone for midpoint offset.", "0-0.99"),
    "led.signal_loss_fade_out_ms": ("LED Signal Loss Fade", "Fade-out time in milliseconds used by the ESP32 after serial tracking updates stop.", ">=0"),
    "led.brightness_output_inverted": ("LED Invert", "Invert LED brightness output so 100% becomes 0% and 0% becomes 100%.", None),
    "led.left_right_inverted": ("LED Swap Left/Right", "Swap left and right LED response to the tracked midpoint.", None),
    "servo_motion.smoothing_alpha": ("Servo Smoothing", "One-pole smoothing factor for servo motion.", "0-1"),
    "servo_motion.max_speed_deg_per_sec": ("Servo Max Speed", "Servo speed cap.", ">=1"),
}


def build_field_catalog(config: RuntimeConfig) -> list[ConfigField]:
    fields: list[ConfigField] = []
    defaults = RuntimeConfig()
    for key in CONFIG_FIELD_PATHS:
        label, description, valid_range = FIELD_DESCRIPTIONS.get(
            key,
            (key.replace(".", " ").replace("_", " ").title(), f"Runtime config for {key}.", None),
        )
        value = get_config_value(config, key)
        if key == "tracking.unlock_bbox_threshold_ratio" and value is None:
            value = config.tracking.lock_bbox_threshold_ratio
        default = get_config_value(defaults, key)
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
                applies_to=CONFIG_FIELD_PATHS.get(key, ("general", ""))[0],
            )
        )
    return fields


def get_config_value(config: RuntimeConfig, key: str) -> Any:
    group, field = CONFIG_FIELD_PATHS[key]
    return getattr(getattr(config, group), field)


def _set_config_value(data: dict[str, Any], key: str, value: Any) -> None:
    group, field = CONFIG_FIELD_PATHS[key]
    data.setdefault(group, {})[field] = value


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
    if key == "camera.source":
        return ["browser", "backend"]
    if key == "yolo.device_mode":
        accelerator = "mps" if platform.system() == "Darwin" else "gpu"
        return ["auto", "cpu", accelerator]
    return None


def validate_runtime_config(candidate: RuntimeConfig) -> list[str]:
    errors: list[str] = []
    if candidate.camera.source not in {"browser", "backend"}:
        errors.append("camera.source must be one of ['browser', 'backend']")
    if candidate.camera.width < 320:
        errors.append("camera.width must be >= 320")
    if candidate.camera.height < 240:
        errors.append("camera.height must be >= 240")
    if not 1 <= candidate.camera.fps <= 60:
        errors.append("camera.fps must be between 1 and 60")
    if not 0.01 <= candidate.tracking.lock_bbox_threshold_ratio <= 0.95:
        errors.append("tracking.lock_bbox_threshold_ratio must be between 0.01 and 0.95")
    unlock = (
        candidate.tracking.unlock_bbox_threshold_ratio
        if candidate.tracking.unlock_bbox_threshold_ratio is not None
        else candidate.tracking.lock_bbox_threshold_ratio
    )
    if not 0.01 <= unlock <= 0.95:
        errors.append("tracking.unlock_bbox_threshold_ratio must be between 0.01 and 0.95")
    if not 0.001 <= candidate.distance.mid_bbox_threshold_ratio <= 0.95:
        errors.append("distance.mid_bbox_threshold_ratio must be between 0.001 and 0.95")
    if not 0.001 <= candidate.distance.near_bbox_threshold_ratio <= 0.95:
        errors.append("distance.near_bbox_threshold_ratio must be between 0.001 and 0.95")
    if candidate.distance.mid_bbox_threshold_ratio >= candidate.distance.near_bbox_threshold_ratio:
        errors.append("distance.mid_bbox_threshold_ratio must be < distance.near_bbox_threshold_ratio")
    if not 0.01 <= candidate.audio.full_frame_threshold_ratio <= 0.99:
        errors.append("audio.full_frame_threshold_ratio must be between 0.01 and 0.99")
    if candidate.light.side_led_count < 1:
        errors.append("light.side_led_count must be >= 1")
    if candidate.light.active_led_count_per_cycle < 1:
        errors.append("light.active_led_count_per_cycle must be >= 1")
    if candidate.light.active_led_count_per_cycle > candidate.light.side_led_count:
        errors.append("light.active_led_count_per_cycle must be <= light.side_led_count")
    if not 0.01 <= candidate.light.super_close_bbox_threshold_ratio <= 0.99:
        errors.append("light.super_close_bbox_threshold_ratio must be between 0.01 and 0.99")
    if candidate.light.empty_cycle_sec <= 0:
        errors.append("light.empty_cycle_sec must be > 0")
    if not 1 <= candidate.light.empty_brightness_level <= 10:
        errors.append("light.empty_brightness_level must be between 1 and 10")
    if candidate.light.present_start_after_sec < 0:
        errors.append("light.present_start_after_sec must be >= 0")
    if candidate.light.present_full_after_sec <= candidate.light.present_start_after_sec:
        errors.append("light.present_full_after_sec must be > light.present_start_after_sec")
    if candidate.light.present_start_cycle_sec <= 0:
        errors.append("light.present_start_cycle_sec must be > 0")
    if candidate.light.present_min_cycle_sec <= 0:
        errors.append("light.present_min_cycle_sec must be > 0")
    if candidate.light.present_min_cycle_sec > candidate.light.present_start_cycle_sec:
        errors.append("light.present_min_cycle_sec must be <= light.present_start_cycle_sec")
    if not 1 <= candidate.light.present_start_brightness_level <= 10:
        errors.append("light.present_start_brightness_level must be between 1 and 10")
    if not 1 <= candidate.light.present_max_brightness_level <= 10:
        errors.append("light.present_max_brightness_level must be between 1 and 10")
    if candidate.light.present_max_brightness_level < candidate.light.present_start_brightness_level:
        errors.append("light.present_max_brightness_level must be >= light.present_start_brightness_level")
    if not 1 <= candidate.light.super_close_brightness_level <= 10:
        errors.append("light.super_close_brightness_level must be between 1 and 10")
    if candidate.tracking.enter_debounce_ms < 0:
        errors.append("tracking.enter_debounce_ms must be >= 0")
    if candidate.tracking.exit_debounce_ms < 0:
        errors.append("tracking.exit_debounce_ms must be >= 0")
    if candidate.tracking.lost_timeout_ms < 0:
        errors.append("tracking.lost_timeout_ms must be >= 0")

    accelerator = "mps" if platform.system() == "Darwin" else "gpu"
    allowed_device_modes = {"auto", "cpu", accelerator}
    if candidate.yolo.device_mode not in allowed_device_modes:
        errors.append(f"yolo.device_mode must be one of {sorted(allowed_device_modes)}")
    if candidate.serial.baud_rate < 1200:
        errors.append("serial.baud_rate must be >= 1200")
    if candidate.servo_calibration.left_gain <= 0:
        errors.append("servo_calibration.left_gain must be > 0")
    if candidate.servo_calibration.right_gain <= 0:
        errors.append("servo_calibration.right_gain must be > 0")
    if candidate.servo_calibration.eye_spacing_cm < 1:
        errors.append("servo_calibration.eye_spacing_cm must be >= 1")
    if not 0 <= candidate.servo_calibration.left_min_deg <= candidate.servo_calibration.left_max_deg <= 180:
        errors.append("servo_calibration.left_min_deg and servo_calibration.left_max_deg must be ordered within 0-180")
    if not 0 <= candidate.servo_calibration.right_min_deg <= candidate.servo_calibration.right_max_deg <= 180:
        errors.append("servo_calibration.right_min_deg and servo_calibration.right_max_deg must be ordered within 0-180")
    if not 0 <= candidate.led.min_brightness_pct <= 100:
        errors.append("led.min_brightness_pct must be between 0 and 100")
    if not 0 <= candidate.led.max_brightness_pct <= 100:
        errors.append("led.max_brightness_pct must be between 0 and 100")
    if candidate.led.min_brightness_pct > candidate.led.max_brightness_pct:
        errors.append("led.min_brightness_pct must be <= led.max_brightness_pct")
    if candidate.led.midpoint_response_gain <= 0:
        errors.append("led.midpoint_response_gain must be > 0")
    if candidate.led.midpoint_response_gamma <= 0:
        errors.append("led.midpoint_response_gamma must be > 0")
    if not 0 <= candidate.led.midpoint_deadzone_norm < 1:
        errors.append("led.midpoint_deadzone_norm must be between 0 and 1 (exclusive of 1)")
    if candidate.led.signal_loss_fade_out_ms < 0:
        errors.append("led.signal_loss_fade_out_ms must be >= 0")
    if not 0 <= candidate.servo_motion.smoothing_alpha <= 1:
        errors.append("servo_motion.smoothing_alpha must be between 0 and 1")
    if candidate.servo_motion.max_speed_deg_per_sec < 1:
        errors.append("servo_motion.max_speed_deg_per_sec must be >= 1")
    return errors


def merge_config(current: RuntimeConfig, payload: dict) -> RuntimeConfig:
    try:
        merged_data = current.model_dump()
        for key, value in payload.items():
            if key in CONFIG_FIELD_PATHS:
                _set_config_value(merged_data, key, value)
                continue
            if key in RuntimeConfig.model_fields and isinstance(value, dict):
                merged_data.setdefault(key, {}).update(value)
        return RuntimeConfig.model_validate(merged_data)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
