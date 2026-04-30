from __future__ import annotations

import sys
from types import SimpleNamespace

from backend.telemetry.system_stats import get_device_memory_stats


def test_cuda_device_memory_stats_exposes_name_reserved_allocated_and_total(monkeypatch):
    class FakeCuda:
        @staticmethod
        def is_available() -> bool:
            return True

        @staticmethod
        def get_device_properties(index: int):
            assert index == 0
            return SimpleNamespace(total_memory=8 * 1024 * 1024 * 1024)

        @staticmethod
        def get_device_name(index: int) -> str:
            assert index == 0
            return "NVIDIA Test GPU"

        @staticmethod
        def memory_allocated(index: int) -> int:
            assert index == 0
            return 256 * 1024 * 1024

        @staticmethod
        def memory_reserved(index: int) -> int:
            assert index == 0
            return 512 * 1024 * 1024

    fake_torch = SimpleNamespace(
        cuda=FakeCuda(),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False)),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    stats = get_device_memory_stats()

    assert stats.device == "cuda:0"
    assert stats.name == "NVIDIA Test GPU"
    assert stats.allocated_mb == 256
    assert stats.reserved_mb == 512
    assert stats.total_mb == 8192
