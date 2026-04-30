from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path

from backend.config import RuntimeConfig


ULTRALYTICS_ASSET_BASE = "https://github.com/ultralytics/assets/releases/latest/download"


def ensure_runtime_models(config: RuntimeConfig) -> list[dict[str, str]]:
    return [
        _ensure_yolo_asset(config.yolo.model_path),
    ]


def _ensure_yolo_asset(target_path: str) -> dict[str, str]:
    target = Path(target_path)
    if target.exists():
        return {
            "component": "vision-model",
            "status": "ok",
            "message": f"YOLO model ready at {target}.",
        }

    if target.suffix != ".pt":
        raise ValueError(f"YOLO model path must point to a .pt file: {target}")

    target.parent.mkdir(parents=True, exist_ok=True)
    download_url = f"{ULTRALYTICS_ASSET_BASE}/{target.name}"
    _download_file(download_url, target)
    return {
        "component": "vision-model",
        "status": "ok",
        "message": f"Downloaded YOLO model to {target}.",
    }


def _download_file(url: str, target: Path) -> None:
    with urllib.request.urlopen(url) as response, target.open("wb") as handle:
        shutil.copyfileobj(response, handle)
