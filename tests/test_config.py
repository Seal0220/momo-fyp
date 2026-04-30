import platform

from backend.config import build_field_catalog, validate_runtime_config
from backend.types import RuntimeConfig


def test_default_config_is_vision_and_arduino_only():
    config = RuntimeConfig()

    assert config.camera_source == "backend"
    assert config.yolo_device_mode == "auto"
    assert config.serial_port == "auto"
    assert config.serial_baud_rate == 115200


def test_invalid_config_detected():
    config = RuntimeConfig(camera_width=100, serial_baud_rate=300)
    errors = validate_runtime_config(config)

    assert any("camera_width" in item for item in errors)
    assert any("serial_baud_rate" in item for item in errors)


def test_device_mode_fields_expose_os_specific_enum():
    config = RuntimeConfig()
    fields = {field.key: field for field in build_field_catalog(config)}
    accelerator = "mps" if platform.system() == "Darwin" else "gpu"

    assert fields["camera_flip_vertical"].type == "boolean"
    assert fields["yolo_device_mode"].enum == ["auto", "cpu", accelerator]
    assert fields["led_min_brightness_pct"].type == "float"
    assert fields["led_max_brightness_pct"].type == "float"
    assert fields["led_midpoint_response_gain"].type == "float"
    assert fields["led_midpoint_response_gamma"].type == "float"
    assert fields["led_midpoint_deadzone_norm"].type == "float"
    assert fields["led_signal_loss_fade_out_ms"].type == "int"
    assert fields["led_brightness_output_inverted"].type == "boolean"
    assert fields["led_left_right_inverted"].type == "boolean"


def test_invalid_led_brightness_config_detected():
    config = RuntimeConfig(led_min_brightness_pct=90, led_max_brightness_pct=10)

    errors = validate_runtime_config(config)

    assert "led_min_brightness_pct must be <= led_max_brightness_pct" in errors


def test_invalid_led_signal_loss_fade_out_config_detected():
    config = RuntimeConfig(led_signal_loss_fade_out_ms=-1)

    errors = validate_runtime_config(config)

    assert "led_signal_loss_fade_out_ms must be >= 0" in errors


def test_invalid_led_midpoint_response_config_detected():
    config = RuntimeConfig(
        led_midpoint_response_gain=0,
        led_midpoint_response_gamma=0,
        led_midpoint_deadzone_norm=1,
    )

    errors = validate_runtime_config(config)

    assert "led_midpoint_response_gain must be > 0" in errors
    assert "led_midpoint_response_gamma must be > 0" in errors
    assert "led_midpoint_deadzone_norm must be between 0 and 1 (exclusive of 1)" in errors
