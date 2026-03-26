from __future__ import annotations

from pathlib import Path


class ResourceManager:
    def __init__(self, tmp_dir: str = "tmp") -> None:
        self.tmp_dir = Path(tmp_dir)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def cleanup_temp_audio(self, keep_latest: int = 3) -> list[str]:
        wavs = sorted(self.tmp_dir.glob("*.wav"), key=lambda item: item.stat().st_mtime, reverse=True)
        deleted: list[str] = []
        for item in wavs[keep_latest:]:
            item.unlink(missing_ok=True)
            deleted.append(item.name)
        return deleted

