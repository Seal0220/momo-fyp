from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SystemMode(str, Enum):
    IDLE = "IDLE"
    ACQUIRING = "ACQUIRING"
    TRACKING = "TRACKING"
    RECONNECTING = "RECONNECTING"


class PipelineStage(str, Enum):
    IDLE = "IDLE"
    VISION = "VISION"
    ERROR = "ERROR"


class AudienceFeatures(BaseModel):
    track_id: int | None = None
    person_bbox: list[int] | None = None
    bbox_area_ratio: float = 0.0
    center_x_norm: float = 0.5
    center_y_norm: float = 0.5
    distance_class: str = "unknown"
    horizontal_class: str = "unknown"
    position_state: str = "unknown"
    height_class: str = "unknown"
    build_class: str = "unknown"
    top_color: str = "unknown"
    bottom_color: str = "unknown"


class PipelineStatus(BaseModel):
    stage: PipelineStage = PipelineStage.IDLE
    started_at: str | None = None
    elapsed_ms: int = 0
    last_error: str | None = None


class ServoTelemetry(BaseModel):
    left_deg: float = 90.0
    right_deg: float = 90.0
    tracking_source: str = "none"


class SerialMonitorEntry(BaseModel):
    ts: str = Field(default_factory=utc_now_iso)
    direction: str
    message: str


class SerialMonitorSnapshot(BaseModel):
    port: str | None = None
    baud_rate: int | None = None
    last_tx: str | None = None
    last_tx_at: str | None = None
    last_rx: str | None = None
    last_rx_at: str | None = None
    last_error: str | None = None
    last_error_at: str | None = None
    entries: list[SerialMonitorEntry] = Field(default_factory=list)


class SystemStats(BaseModel):
    memory_rss_mb: float = 0.0
    memory_vms_mb: float = 0.0
    gpu_memory_mb: float | None = None
    temp_file_count: int = 0
    temp_file_size_mb: float = 0.0


class RuntimeComponentStats(BaseModel):
    requested_mode: str | None = None
    effective_device: str | None = None
    backend: str | None = None
    selection_source: str | None = None
    ram_mb: float | None = None
    vram_mb: float | None = None


class PositionAudioSnapshot(BaseModel):
    current_state: str = "unknown"
    last_triggered_state: str | None = None
    last_audio_file: str | None = None
    last_error: str | None = None


class StatusSnapshot(BaseModel):
    ts: str = Field(default_factory=utc_now_iso)
    mode: SystemMode = SystemMode.IDLE
    pipeline: PipelineStatus = Field(default_factory=PipelineStatus)
    locked_track_id: int | None = None
    audience: AudienceFeatures = Field(default_factory=AudienceFeatures)
    servo: ServoTelemetry = Field(default_factory=ServoTelemetry)
    serial_monitor: SerialMonitorSnapshot = Field(default_factory=SerialMonitorSnapshot)
    stats: SystemStats = Field(default_factory=SystemStats)
    camera_device_id: str | None = None
    camera_mode: str | None = None
    serial_connected: bool = False
    yolo_detect_fps: float = 0.0
    yolo_person_runtime: RuntimeComponentStats = Field(default_factory=RuntimeComponentStats)
    position_audio: PositionAudioSnapshot = Field(default_factory=PositionAudioSnapshot)
    event_log: list[str] = Field(default_factory=list)


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
    camera_source: str = "backend"
    camera_device_id: str = "default"
    camera_width: int = 640
    camera_height: int = 480
    camera_fps: int = 30
    camera_mirror_preview: bool = False
    camera_flip_vertical: bool = True
    yolo_model_path: str = "model/yolo/yolo26n.pt"
    yolo_device_mode: str = "auto"
    lock_bbox_threshold_ratio: float = 0.12
    unlock_bbox_threshold_ratio: float | None = None
    enter_debounce_ms: int = 1000
    exit_debounce_ms: int = 500
    lost_timeout_ms: int = 5000
    serial_port: str = "auto"
    serial_baud_rate: int = 115200
    servo_left_zero_deg: float = 87.0
    servo_right_zero_deg: float = 96.0
    servo_output_inverted: bool = False
    servo_left_trim_deg: float = 0.0
    servo_right_trim_deg: float = 0.0
    servo_left_gain: float = 2.5
    servo_right_gain: float = 2.5
    servo_eye_spacing_cm: int = 13
    servo_left_min_deg: float = 45.0
    servo_left_max_deg: float = 135.0
    servo_right_min_deg: float = 45.0
    servo_right_max_deg: float = 135.0
    led_min_brightness_pct: float = 0.0
    led_max_brightness_pct: float = 100.0
    led_midpoint_response_gain: float = 2.5
    led_midpoint_response_gamma: float = 0.75
    led_midpoint_deadzone_norm: float = 0.0
    led_signal_loss_fade_out_ms: int = 3000
    led_brightness_output_inverted: bool = False
    led_left_right_inverted: bool = False
    servo_smoothing_alpha: float = 0.25
    servo_max_speed_deg_per_sec: float = 180.0


class ConfigUpdateResponse(BaseModel):
    applied_config: RuntimeConfig
    validation_errors: list[str]
    effective_changes: list[str]
    apply_checks: list[dict[str, str]] = Field(default_factory=list)
    requires_pipeline_restart: bool
