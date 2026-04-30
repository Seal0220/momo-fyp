from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic

from backend.types import (
    AudienceFeatures,
    PipelineStage,
    PipelineStatus,
    ServoTelemetry,
    StatusSnapshot,
    SystemMode,
)


@dataclass
class RuntimeState:
    mode: SystemMode = SystemMode.IDLE
    locked_track_id: int | None = None
    pipeline: PipelineStatus = field(default_factory=PipelineStatus)
    audience: AudienceFeatures = field(default_factory=AudienceFeatures)
    servo: ServoTelemetry = field(default_factory=ServoTelemetry)
    event_log: list[str] = field(default_factory=list)
    _stage_started: float | None = None

    def set_mode(self, mode: SystemMode, note: str | None = None) -> None:
        self.mode = mode
        if note:
            self.event_log = [note, *self.event_log][:20]

    def set_pipeline_stage(self, stage: PipelineStage, error: str | None = None) -> None:
        self._stage_started = monotonic()
        self.pipeline = PipelineStatus(
            stage=stage,
            started_at=None,
            elapsed_ms=0,
            last_error=error,
        )

    def tick(self) -> None:
        if self._stage_started is not None:
            self.pipeline.elapsed_ms = int((monotonic() - self._stage_started) * 1000)

    def apply_detection(
        self,
        track_id: int,
        bbox_area_ratio: float,
        center_x_norm: float,
        top_color: str = "unknown",
    ) -> None:
        self.locked_track_id = track_id
        self.audience.track_id = track_id
        self.audience.bbox_area_ratio = bbox_area_ratio
        self.audience.center_x_norm = center_x_norm
        self.audience.top_color = top_color

    def snapshot(self) -> StatusSnapshot:
        self.tick()
        return StatusSnapshot(
            mode=self.mode,
            pipeline=self.pipeline,
            locked_track_id=self.locked_track_id,
            audience=self.audience,
            servo=self.servo,
            event_log=self.event_log,
        )
