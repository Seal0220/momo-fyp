from backend.config import validate_runtime_config
from backend.types import RuntimeConfig


def test_default_ollama_timeout_is_600():
    config = RuntimeConfig()
    assert config.ollama_timeout_sec == 600
    assert config.ollama_model == "qwen3.5:2b"


def test_invalid_config_detected():
    config = RuntimeConfig(camera_width=100, history_max_sentences=9)
    errors = validate_runtime_config(config)
    assert any("camera_width" in item for item in errors)
    assert any("history_max_sentences" in item for item in errors)
