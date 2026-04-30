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
        fade_min_sec: float = 0.25
        fade_max_sec: float = 2.0

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
    "camera": "攝影機",
    "yolo": "YOLO",
    "tracking": "追蹤",
    "distance": "距離判定",
    "audio": "聲音",
    "light": "燈光",
    "serial": "序列埠",
    "servo_calibration": "伺服校正",
    "servo_motion": "伺服動作",
    "led": "LED",
    "general": "一般",
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
    "light.fade_min_sec": ("light", "fade_min_sec"),
    "light.fade_max_sec": ("light", "fade_max_sec"),
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
    "light.fade_min_sec",
    "light.fade_max_sec",
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
    "camera.source": ("影像來源", "選擇瀏覽器上傳影像或後端 OpenCV 攝影機擷取。", None),
    "camera.device_id": ("攝影機", "攝影機裝置識別名稱。", None),
    "camera.width": ("寬度", "攝影機擷取寬度。", ">=320"),
    "camera.height": ("高度", "攝影機擷取高度。", ">=240"),
    "camera.fps": ("FPS", "攝影機擷取影格率。", "1-60"),
    "camera.mirror_preview": ("水平鏡像", "偵測與預覽前，將畫面左右翻轉。", None),
    "camera.flip_vertical": ("垂直翻轉", "偵測與預覽前，將畫面上下翻轉。", None),
    "yolo.model_path": ("YOLO 模型路徑", "YOLO 人物偵測模型檔案路徑。", None),
    "yolo.device_mode": ("YOLO 執行裝置", "人物偵測使用的裝置模式：auto、cpu 或此系統可用的加速器。", None),
    "tracking.lock_bbox_threshold_ratio": ("鎖定門檻", "人物 BBox 佔畫面比例達到此值後進入鎖定模式。", "0.01-0.95"),
    "tracking.unlock_bbox_threshold_ratio": ("維持鎖定門檻", "人物 BBox 佔畫面比例需達到此值才維持鎖定。", "0.01-0.95"),
    "distance.near_bbox_threshold_ratio": ("近距離門檻", "人物 BBox 佔畫面比例達到此值時判定為近。", "0.001-0.95"),
    "distance.mid_bbox_threshold_ratio": ("中距離門檻", "人物 BBox 佔畫面比例達到此值時判定為中。", "0.001-0.95"),
    "audio.state_dir": ("聲音狀態資料夾", "包含 no_one、left、center、right、full 子資料夾的音檔根目錄。", None),
    "audio.full_frame_threshold_ratio": ("聲音全畫面門檻", "單一人物 BBox 佔畫面比例達到此值時觸發聲音全狀態。", "0.01-0.99"),
    "light.side_led_count": ("單側 LED 數量", "左右單側各自可控制的 LED 數量。", ">=1"),
    "light.active_led_count_per_cycle": ("每週期亮燈數", "每次閃爍週期中，單側隨機亮起的 LED 數量。", "1-單側數量"),
    "light.super_close_bbox_threshold_ratio": ("超近門檻", "單一人物 BBox 佔畫面比例達到此值時，燈光進入全狀態並恆亮 10A。", "0.01-0.99"),
    "light.empty_cycle_sec": ("無人週期", "該側無人時的閃爍週期秒數。", ">0"),
    "light.empty_brightness_level": ("無人亮度", "該側無人時的呼吸亮度等級。", "1A-10A"),
    "light.present_start_after_sec": ("有人起算時間", "人停留多久後開始套用有人狀態映射。", ">=0"),
    "light.present_full_after_sec": ("有人最大時間", "人停留多久後達到最快週期與最高有人亮度。", "> 起算時間"),
    "light.present_start_cycle_sec": ("有人起始週期", "到達起算時間時使用的閃爍週期。", ">0"),
    "light.present_min_cycle_sec": ("有人最短週期", "持續有人後可達到的最快閃爍週期。", ">0"),
    "light.present_start_brightness_level": ("有人起始亮度", "到達起算時間時的亮度等級。", "1A-10A"),
    "light.present_max_brightness_level": ("有人最高亮度", "持續有人後可達到的最高亮度等級。", "1A-10A"),
    "light.super_close_brightness_level": ("超近亮度", "超近鎖定時的恆亮亮度等級。", "1A-10A"),
    "light.fade_min_sec": ("最短淡入淡出", "閃爍週期內單段淡入或淡出的最短秒數。", ">=0"),
    "light.fade_max_sec": ("最長淡入淡出", "閃爍週期內單段淡入或淡出的最長秒數。", ">= 最短淡入淡出"),
    "tracking.enter_debounce_ms": ("進入防抖", "連續高於門檻多久後才進入鎖定。", ">=0 ms"),
    "tracking.exit_debounce_ms": ("離開防抖", "連續低於門檻多久後才重新尋找目標。", ">=0 ms"),
    "tracking.lost_timeout_ms": ("遺失等待時間", "允許重新連回同一觀眾的等待時間。", ">=0 ms"),
    "serial.port": ("序列埠", "序列埠路徑或 auto 自動偵測。", None),
    "serial.baud_rate": ("Baud Rate", "ESP32 序列通訊的 UART 速度。", ">=1200"),
    "servo_calibration.left_zero_deg": ("左眼歸零角度", "左眼 servo 的中立角度。", "0-180"),
    "servo_calibration.right_zero_deg": ("右眼歸零角度", "右眼 servo 的中立角度。", "0-180"),
    "servo_calibration.output_inverted": ("輸出反向", "以各自歸零角度為中心反轉左右 servo 輸出。", None),
    "servo_calibration.left_trim_deg": ("左眼微調", "左眼 servo 縮放後額外加上的固定角度。", "-90-90"),
    "servo_calibration.right_trim_deg": ("右眼微調", "右眼 servo 縮放後額外加上的固定角度。", "-90-90"),
    "servo_calibration.left_gain": ("左眼增益", "左眼 servo 相對歸零角度的位移倍率。", ">0"),
    "servo_calibration.right_gain": ("右眼增益", "右眼 servo 相對歸零角度的位移倍率。", ">0"),
    "servo_calibration.eye_spacing_cm": ("眼距", "雙眼 servo 之間的距離，用於瞄準幾何計算。", ">=1 cm"),
    "servo_calibration.left_min_deg": ("左眼最小角度", "左眼 servo 輸出下限。", "0-180"),
    "servo_calibration.left_max_deg": ("左眼最大角度", "左眼 servo 輸出上限。", "0-180"),
    "servo_calibration.right_min_deg": ("右眼最小角度", "右眼 servo 輸出下限。", "0-180"),
    "servo_calibration.right_max_deg": ("右眼最大角度", "右眼 servo 輸出上限。", "0-180"),
    "led.min_brightness_pct": ("LED 最低亮度", "送到 ESP32 的 LED 最低亮度百分比。", "0-100"),
    "led.max_brightness_pct": ("LED 最高亮度", "送到 ESP32 的 LED 最高亮度百分比。", "0-100"),
    "led.midpoint_response_gain": ("LED 中點增益", "人物中心偏移量進入 LED 映射前的倍率。", ">0"),
    "led.midpoint_response_gamma": ("LED 中點曲線", "偏移量套用增益後的 gamma 曲線。", ">0"),
    "led.midpoint_deadzone_norm": ("LED 中點死區", "人物中心偏移量的中央死區。", "0-0.99"),
    "led.signal_loss_fade_out_ms": ("LED 斷訊淡出", "ESP32 停止收到序列追蹤更新後的淡出時間。", ">=0 ms"),
    "led.brightness_output_inverted": ("LED 亮度反向", "反轉 LED 亮度輸出，100% 變 0%，0% 變 100%。", None),
    "led.left_right_inverted": ("LED 左右交換", "交換依人物中點計算出的左右 LED 反應。", None),
    "servo_motion.smoothing_alpha": ("Servo 平滑", "Servo 動作的一階平滑係數。", "0-1"),
    "servo_motion.max_speed_deg_per_sec": ("Servo 最高速度", "Servo 角速度上限。", ">=1"),
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
    if candidate.light.fade_min_sec < 0:
        errors.append("light.fade_min_sec must be >= 0")
    if candidate.light.fade_max_sec < candidate.light.fade_min_sec:
        errors.append("light.fade_max_sec must be >= light.fade_min_sec")
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
