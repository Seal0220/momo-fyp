import asyncio
import time

from fastapi.testclient import TestClient

from backend.app import app, brain
from backend.types import AudienceFeatures, PipelineStage, ServoTelemetry


client = TestClient(app)


def test_status_endpoint_returns_pipeline_and_stats():
    response = client.get("/api/status")
    assert response.status_code == 200
    payload = response.json()
    assert "pipeline" in payload
    assert "stats" in payload


def test_simulate_pipeline_returns_prompt_and_snapshot():
    async def fake_generate_tracking_line():
        brain.state.sentence_index = 3
        brain.state.set_pipeline_stage(PipelineStage.PLAYBACK)

    original = brain.generate_tracking_line
    brain.generate_tracking_line = fake_generate_tracking_line
    response = client.post("/api/control/simulate-pipeline", json={"sentence_index": 3, "event_summary": "蹲下"})
    brain.generate_tracking_line = original
    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshot"]["pipeline"]["stage"] == "PLAYBACK"


def test_update_config_returns_apply_checks():
    response = client.post("/api/config", json={"camera_width": 640})
    assert response.status_code == 200
    payload = response.json()
    assert "apply_checks" in payload
    assert isinstance(payload["apply_checks"], list)


def test_update_config_validation_failure_returns_feedback():
    response = client.post("/api/config", json={"camera_width": 100})
    assert response.status_code == 200
    payload = response.json()
    assert payload["validation_errors"]
    assert payload["apply_checks"][0]["status"] == "error"


def test_update_config_can_reapply_same_payload():
    first = client.post("/api/config", json={"camera_width": 640})
    second = client.post("/api/config", json={"camera_width": 640})
    assert first.status_code == 200
    assert second.status_code == 200
    payload = second.json()
    assert payload["validation_errors"] == []
    assert payload["apply_checks"]


def test_update_config_tts_path_no_server_error():
    response = client.post(
        "/api/config",
        json={"tts_model_path": "model/huggingface/hf_snapshots/Qwen__Qwen3-TTS-12Hz-1.7B-Base"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["validation_errors"] == []
    assert any(item["component"] == "tts" for item in payload["apply_checks"])


def test_update_config_tts_timeout_validation_failure_returns_feedback():
    response = client.post("/api/config", json={"tts_timeout_sec": 0})
    assert response.status_code == 200
    payload = response.json()
    assert "tts_timeout_sec must be >= 1" in payload["validation_errors"]


def test_speak_line_reports_tts_timeout_ms():
    original_tts = brain.tts
    original_timeout = brain.config.tts_timeout_sec

    class SlowTTS:
        loaded = False

        def synthesize(self, text: str, output_path: str) -> str:
            time.sleep(0.05)
            return output_path

    brain.tts = SlowTTS()
    brain.config.tts_timeout_sec = 0.01

    try:
        try:
            asyncio.run(brain._speak_line("測試"))
            assert False, "expected timeout"
        except RuntimeError as exc:
            assert "TTS timeout after" in str(exc)
            assert "limit 10.0 ms" in str(exc)
    finally:
        brain.tts = original_tts
        brain.config.tts_timeout_sec = original_timeout


def test_get_config_reflects_latest_applied_value():
    client.post("/api/config", json={"camera_fps": 15})
    response = client.get("/api/config")
    assert response.status_code == 200
    payload = response.json()
    assert payload["config"]["camera_fps"] == 15


def test_status_snapshot_keeps_computed_servo_angles():
    original_get_snapshot = brain.vision.get_snapshot
    brain.state.servo = ServoTelemetry(left_deg=83.5, right_deg=97.25, tracking_source="eye_midpoint")

    class FakeVisionState:
        features = AudienceFeatures(top_color="灰色")
        servo = ServoTelemetry(left_deg=90, right_deg=90, tracking_source="person_center")
        frame_jpeg = None
        frame_shape = None
        target_seen_at = None

    brain.vision.get_snapshot = lambda: FakeVisionState()
    response = client.get("/api/status")
    brain.vision.get_snapshot = original_get_snapshot
    assert response.status_code == 200
    payload = response.json()
    assert payload["servo"]["left_deg"] == 83.5
    assert payload["servo"]["right_deg"] == 97.25
