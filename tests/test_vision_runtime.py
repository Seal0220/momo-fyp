from __future__ import annotations

import time

from backend.types import RuntimeConfig
from backend.vision.runtime import VisionRuntime


def test_browser_mode_never_opens_local_capture(monkeypatch):
    runtime = VisionRuntime(RuntimeConfig(camera_source="browser"))
    opened = False

    class FakeCapture:
        def release(self) -> None:
            return None

    runtime.capture = FakeCapture()

    def fake_open_capture():
        nonlocal opened
        opened = True
        return FakeCapture()

    def fake_sleep(_: float) -> None:
        runtime.running = False

    monkeypatch.setattr(runtime, "_open_capture", fake_open_capture)
    monkeypatch.setattr(time, "sleep", fake_sleep)

    runtime.running = True
    runtime._loop()

    assert opened is False
    assert runtime.capture is None
