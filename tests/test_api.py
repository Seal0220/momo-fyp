import pytest
from fastapi.testclient import TestClient

pytest.importorskip("cv2")
pytest.importorskip("serial")
pytest.importorskip("ultralytics")

from backend.app import app, brain
from backend.types import AudienceFeatures, SerialMonitorSnapshot, ServoTelemetry
from backend.vision.runtime import VisionState

client = TestClient(app)


def test_monitor_page_is_served():
    response = client.get("/monitor")

    assert response.status_code == 200
    assert "Momo Monitor" in response.text


def test_status_endpoint_returns_vision_serial_and_stats():
    response = client.get("/api/status")

    assert response.status_code == 200
    payload = response.json()
    assert "pipeline" in payload
    assert "stats" in payload
    assert "serial_monitor" in payload
    assert "yolo_person_runtime" in payload
    assert "yolo_detect_fps" in payload


def test_status_endpoint_uses_cached_runtime_status_and_exposes_detect_fps():
    original_detect_fps = brain.vision.detect_fps
    brain.vision.detect_fps = lambda: 7.25
    try:
        response = client.get("/api/status")
        assert response.status_code == 200
        assert response.json()["yolo_detect_fps"] == 7.25
    finally:
        brain.vision.detect_fps = original_detect_fps


def test_browser_frame_upload_sends_servo_immediately():
    original_submit = brain.vision.submit_jpeg_frame
    original_serial = brain.serial
    original_config = brain.config.model_copy(deep=True)

    sent: list[tuple[float, float, str, str, float, float, int]] = []

    class FakeSerial:
        connected = False

        def send_servo_command(
            self,
            left_deg: float,
            right_deg: float,
            mode: str = "track",
            tracking_source: str = "person_center",
            led_left_pct: float = 50.0,
            led_right_pct: float = 50.0,
            led_values_pct: list[float] | None = None,
            led_signal_loss_fade_out_ms: int = 3000,
        ):
            sent.append((left_deg, right_deg, mode, tracking_source, led_left_pct, led_right_pct, led_signal_loss_fade_out_ms))
            return "ok"

        def snapshot(self):
            return SerialMonitorSnapshot()

        def close(self):
            return None

    brain.config = original_config.model_copy(
        update={"camera": original_config.camera.model_copy(update={"source": "browser"})}
    )
    brain.serial = FakeSerial()
    brain.vision.submit_jpeg_frame = lambda _: VisionState(
        features=AudienceFeatures(track_id=1, bbox_area_ratio=0.35, center_x_norm=0.72),
        servo=ServoTelemetry(tracking_source="person_center"),
        frame_jpeg=None,
        frame_shape=(640, 480),
        target_seen_at=None,
    )

    try:
        response = client.post("/api/camera/frame", content=b"jpeg-bytes", headers={"Content-Type": "image/jpeg"})
        assert response.status_code == 200
        assert sent
        assert sent[0][2] == "track"
        assert sent[0][3] == "person_center"
        assert sent[0][4] < sent[0][5]
        assert sent[0][6] == brain.config.led.signal_loss_fade_out_ms
    finally:
        brain.vision.submit_jpeg_frame = original_submit
        brain.serial = original_serial
        brain.config = original_config


def test_update_mode_attempts_send_even_when_serial_marked_disconnected():
    original_snapshot = brain.vision.get_snapshot
    original_serial = brain.serial

    sent: list[tuple[float, float, float, float, int]] = []

    class FakeSerial:
        connected = False

        def send_servo_command(
            self,
            left_deg: float,
            right_deg: float,
            mode: str = "track",
            tracking_source: str = "person_center",
            led_left_pct: float = 50.0,
            led_right_pct: float = 50.0,
            led_values_pct: list[float] | None = None,
            led_signal_loss_fade_out_ms: int = 3000,
        ):
            sent.append((left_deg, right_deg, led_left_pct, led_right_pct, led_signal_loss_fade_out_ms))
            return "ok"

        def snapshot(self):
            return SerialMonitorSnapshot()

        def close(self):
            return None

    brain.serial = FakeSerial()
    brain.vision.get_snapshot = lambda: VisionState(
        features=AudienceFeatures(track_id=1, bbox_area_ratio=0.35, center_x_norm=0.72),
        servo=ServoTelemetry(tracking_source="person_center"),
        frame_jpeg=None,
        frame_shape=(640, 480),
        target_seen_at=None,
    )

    try:
        brain._update_mode_from_vision()
        assert sent
    finally:
        brain.vision.get_snapshot = original_snapshot
        brain.serial = original_serial


def test_update_config_returns_apply_checks():
    response = client.post("/api/config", json={"camera.width": 640})

    assert response.status_code == 200
    payload = response.json()
    assert "apply_checks" in payload
    assert isinstance(payload["apply_checks"], list)


def test_update_config_validation_failure_returns_feedback():
    response = client.post("/api/config", json={"camera.width": 100})

    assert response.status_code == 200
    payload = response.json()
    assert payload["validation_errors"]
    assert payload["apply_checks"][0]["status"] == "error"


def test_update_config_can_reapply_same_payload():
    first = client.post("/api/config", json={"camera.width": 640})
    second = client.post("/api/config", json={"camera.width": 640})

    assert first.status_code == 200
    assert second.status_code == 200
    payload = second.json()
    assert payload["validation_errors"] == []
    assert payload["apply_checks"]


def test_update_config_accepts_servo_eye_spacing():
    original_config = brain.config.model_copy(deep=True)
    original_serial = brain.serial
    try:
        response = client.post("/api/config", json={"servo_calibration.eye_spacing_cm": 12})
        assert response.status_code == 200
        payload = response.json()
        assert payload["validation_errors"] == []
        assert payload["applied_config"]["servo_calibration"]["eye_spacing_cm"] == 12
    finally:
        brain.config = original_config
        brain.serial.close()
        brain.serial = original_serial


def test_update_config_accepts_servo_output_inverted():
    original_config = brain.config.model_copy(deep=True)
    original_serial = brain.serial
    try:
        response = client.post("/api/config", json={"servo_calibration.output_inverted": True})
        assert response.status_code == 200
        payload = response.json()
        assert payload["validation_errors"] == []
        assert payload["applied_config"]["servo_calibration"]["output_inverted"] is True
    finally:
        brain.config = original_config
        brain.serial.close()
        brain.serial = original_serial


def test_update_config_accepts_camera_flip_toggles():
    original_config = brain.config.model_copy(deep=True)
    original_serial = brain.serial
    try:
        response = client.post(
            "/api/config",
            json={"camera.mirror_preview": True, "camera.flip_vertical": True},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["validation_errors"] == []
        assert payload["applied_config"]["camera"]["mirror_preview"] is True
        assert payload["applied_config"]["camera"]["flip_vertical"] is True
        assert any("hflip=on, vflip=on" in item["message"] for item in payload["apply_checks"])
    finally:
        brain.config = original_config
        brain.serial.close()
        brain.serial = original_serial


def test_update_config_accepts_led_output_controls():
    original_config = brain.config.model_copy(deep=True)
    original_serial = brain.serial
    try:
        response = client.post(
            "/api/config",
            json={
                "led.min_brightness_pct": 15,
                "led.max_brightness_pct": 85,
                "led.signal_loss_fade_out_ms": 1800,
                "led.brightness_output_inverted": True,
                "led.left_right_inverted": True,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["validation_errors"] == []
        assert payload["applied_config"]["led"]["min_brightness_pct"] == 15
        assert payload["applied_config"]["led"]["max_brightness_pct"] == 85
        assert payload["applied_config"]["led"]["signal_loss_fade_out_ms"] == 1800
        assert payload["applied_config"]["led"]["brightness_output_inverted"] is True
        assert payload["applied_config"]["led"]["left_right_inverted"] is True
    finally:
        brain.config = original_config
        brain.serial.close()
        brain.serial = original_serial


def test_main_runs_uvicorn(monkeypatch):
    captured = {}

    def fake_run(target: str, **kwargs):
        captured["target"] = target
        captured.update(kwargs)

    monkeypatch.setattr("backend.app.uvicorn.run", fake_run)

    from backend.app import main

    main(["--host", "0.0.0.0", "--port", "9000", "--reload"])

    assert captured["target"] == "backend.app:app"
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 9000
    assert captured["reload"] is True
