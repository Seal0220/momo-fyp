from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
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
    person_bboxes: list[list[int]] = Field(default_factory=list)
    person_count: int = 0
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
    gpu_device: str | None = None
    gpu_name: str | None = None
    gpu_memory_allocated_mb: float | None = None
    gpu_memory_reserved_mb: float | None = None
    gpu_memory_total_mb: float | None = None
    temp_file_count: int = 0
    temp_file_size_mb: float = 0.0


class RuntimeComponentStats(BaseModel):
    requested_mode: str | None = None
    effective_device: str | None = None
    backend: str | None = None
    selection_source: str | None = None
    ram_mb: float | None = None
    vram_mb: float | None = None


class AudioSnapshot(BaseModel):
    current_state: str = "unknown"
    active_states: list[str] = Field(default_factory=list)
    playing_states: list[str] = Field(default_factory=list)
    last_triggered_state: str | None = None
    last_audio_file: str | None = None
    last_error: str | None = None


class LightSideSnapshot(BaseModel):
    state: str = "empty"
    brightness_pct: float = 0.0
    brightness_level: float = 1.0
    cycle_sec: float | None = None
    solid: bool = False
    active_led_indexes: list[int] = Field(default_factory=list)


class LightSnapshot(BaseModel):
    region: str = "no_one"
    left: LightSideSnapshot = Field(default_factory=LightSideSnapshot)
    right: LightSideSnapshot = Field(default_factory=LightSideSnapshot)
    led_values_pct: list[float] = Field(default_factory=list)


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
    audio: AudioSnapshot = Field(default_factory=AudioSnapshot)
    light: LightSnapshot = Field(default_factory=LightSnapshot)
    event_log: list[str] = Field(default_factory=list)


from backend.config import ConfigField, ConfigUpdateResponse, RuntimeConfig
