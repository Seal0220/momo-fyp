import platform

from backend.config import RuntimeConfig, build_field_catalog, validate_runtime_config


def test_default_config_is_vision_and_arduino_only():
    config = RuntimeConfig()

    assert config.camera.source == "backend"
    assert config.yolo.device_mode == "auto"
    assert config.serial.port == "auto"
    assert config.serial.baud_rate == 115200


def test_invalid_config_detected():
    config = RuntimeConfig(
        camera=RuntimeConfig.Camera(width=100),
        serial=RuntimeConfig.Serial(baud_rate=300),
    )
    errors = validate_runtime_config(config)

    assert any("camera.width" in item for item in errors)
    assert any("serial.baud_rate" in item for item in errors)


def test_device_mode_fields_expose_os_specific_enum():
    config = RuntimeConfig()
    fields = {field.key: field for field in build_field_catalog(config)}
    accelerator = "mps" if platform.system() == "Darwin" else "gpu"

    assert fields["camera.flip_vertical"].type == "boolean"
    assert fields["yolo.device_mode"].enum == ["auto", "cpu", accelerator]
    assert fields["led.min_brightness_pct"].type == "float"
    assert fields["led.max_brightness_pct"].type == "float"
    assert fields["led.midpoint_response_gain"].type == "float"
    assert fields["led.midpoint_response_gamma"].type == "float"
    assert fields["led.midpoint_deadzone_norm"].type == "float"
    assert fields["led.signal_loss_fade_out_ms"].type == "int"
    assert fields["led.brightness_output_inverted"].type == "boolean"
    assert fields["led.left_right_inverted"].type == "boolean"
    assert fields["distance.near_bbox_threshold_ratio"].type == "float"
    assert fields["distance.mid_bbox_threshold_ratio"].type == "float"
    assert fields["light.side_led_count"].value == 15
    assert fields["light.active_led_count_per_cycle"].value == 5
    assert fields["audio.full_frame_threshold_ratio"].value == 0.35
    assert fields["light.super_close_bbox_threshold_ratio"].value == 0.35
    assert fields["light.fade_min_sec"].value == 0.25
    assert fields["light.fade_max_sec"].value == 2.0
    assert fields["audio.fade_in_ms"].value == 80
    assert fields["audio.fade_out_ms"].value == 180
    assert fields["audio.reverb_enabled"].type == "boolean"
    assert fields["audio.reverb_delay_ms"].value == 70
    assert fields["audio.reverb_decay"].value == 0.28
    assert fields["audio.reverb_mix"].value == 0.22


def test_invalid_light_active_led_count_detected():
    config = RuntimeConfig(light=RuntimeConfig.Light(side_led_count=4, active_led_count_per_cycle=5))

    errors = validate_runtime_config(config)

    assert "light.active_led_count_per_cycle must be <= light.side_led_count" in errors


def test_invalid_light_fade_config_detected():
    config = RuntimeConfig(light=RuntimeConfig.Light(fade_min_sec=2.0, fade_max_sec=1.0))

    errors = validate_runtime_config(config)

    assert "light.fade_max_sec must be >= light.fade_min_sec" in errors


def test_invalid_audio_effect_config_detected():
    config = RuntimeConfig(
        audio=RuntimeConfig.Audio(
            fade_in_ms=-1,
            fade_out_ms=-1,
            reverb_delay_ms=0,
            reverb_decay=1.2,
            reverb_mix=1.5,
        )
    )

    errors = validate_runtime_config(config)

    assert "audio.fade_in_ms must be >= 0" in errors
    assert "audio.fade_out_ms must be >= 0" in errors
    assert "audio.reverb_delay_ms must be between 1 and 2000" in errors
    assert "audio.reverb_decay must be between 0 and 0.95" in errors
    assert "audio.reverb_mix must be between 0 and 1" in errors


def test_invalid_led_brightness_config_detected():
    config = RuntimeConfig(led=RuntimeConfig.Led(min_brightness_pct=90, max_brightness_pct=10))

    errors = validate_runtime_config(config)

    assert "led.min_brightness_pct must be <= led.max_brightness_pct" in errors


def test_invalid_led_signal_loss_fade_out_config_detected():
    config = RuntimeConfig(led=RuntimeConfig.Led(signal_loss_fade_out_ms=-1))

    errors = validate_runtime_config(config)

    assert "led.signal_loss_fade_out_ms must be >= 0" in errors


def test_invalid_led_midpoint_response_config_detected():
    config = RuntimeConfig(
        led=RuntimeConfig.Led(
            midpoint_response_gain=0,
            midpoint_response_gamma=0,
            midpoint_deadzone_norm=1,
        )
    )

    errors = validate_runtime_config(config)

    assert "led.midpoint_response_gain must be > 0" in errors
    assert "led.midpoint_response_gamma must be > 0" in errors
    assert "led.midpoint_deadzone_norm must be between 0 and 1 (exclusive of 1)" in errors


def test_invalid_distance_threshold_config_detected():
    config = RuntimeConfig(
        distance=RuntimeConfig.Distance(
            near_bbox_threshold_ratio=0.02,
            mid_bbox_threshold_ratio=0.03,
        )
    )

    errors = validate_runtime_config(config)

    assert "distance.mid_bbox_threshold_ratio must be < distance.near_bbox_threshold_ratio" in errors
