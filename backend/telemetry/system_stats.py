from __future__ import annotations

from pathlib import Path

import psutil

from backend.types import SystemStats


def get_system_stats(tmp_dir: str = "tmp") -> SystemStats:
    process = psutil.Process()
    info = process.memory_info()
    temp_files = list(Path(tmp_dir).glob("*"))
    temp_size = sum(item.stat().st_size for item in temp_files if item.is_file())
    return SystemStats(
        memory_rss_mb=round(info.rss / (1024 * 1024), 2),
        memory_vms_mb=round(info.vms / (1024 * 1024), 2),
        gpu_memory_mb=None,
        temp_file_count=len(temp_files),
        temp_file_size_mb=round(temp_size / (1024 * 1024), 2),
    )

