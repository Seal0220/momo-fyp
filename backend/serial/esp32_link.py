from __future__ import annotations

import json
import threading

import serial
from serial.tools import list_ports


class ESP32Link:
    def __init__(self, port: str, baud_rate: int) -> None:
        self.port = port
        self.baud_rate = baud_rate
        self.connected = False
        self.serial_port: serial.Serial | None = None
        self._lock = threading.Lock()
        self.connect()

    @staticmethod
    def list_ports() -> list[dict[str, str]]:
        return [
            {"path": p.device, "description": p.description}
            for p in list_ports.comports()
        ] or [{"path": "auto", "description": "Auto detect"}]

    def connect(self) -> None:
        with self._lock:
            if self.serial_port and self.serial_port.is_open:
                self.connected = True
                return
            try:
                target = self.port
                if target == "auto":
                    candidates = list_ports.comports()
                    for item in candidates:
                        if "usb" in item.device.lower() or "wch" in item.description.lower() or "cp210" in item.description.lower():
                            target = item.device
                            break
                    else:
                        target = candidates[0].device if candidates else ""
                if target:
                    self.serial_port = serial.Serial(target, self.baud_rate, timeout=0.1)
                    self.port = target
                    self.connected = True
                else:
                    self.connected = False
            except Exception:
                self.connected = False

    def build_servo_command(
        self,
        left_deg: float,
        right_deg: float,
        mode: str = "track",
        tracking_source: str = "eye_midpoint",
    ) -> str:
        return json.dumps(
            {
                "type": "servo",
                "mode": mode,
                "left_deg": round(left_deg, 2),
                "right_deg": round(right_deg, 2),
                "tracking_source": tracking_source,
            },
            ensure_ascii=False,
        )

    def send_servo_command(self, left_deg: float, right_deg: float, mode: str = "track", tracking_source: str = "eye_midpoint") -> str:
        payload = self.build_servo_command(left_deg, right_deg, mode=mode, tracking_source=tracking_source)
        with self._lock:
            if not self.connected:
                self.connect()
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.write((payload + "\n").encode("utf-8"))
        return payload
