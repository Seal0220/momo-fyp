from pathlib import Path

from backend.resource_manager import ResourceManager


def test_cleanup_keeps_latest_files(tmp_path: Path):
    manager = ResourceManager(str(tmp_path))
    for index in range(5):
        path = tmp_path / f"{index}.wav"
        path.write_bytes(b"data")
    deleted = manager.cleanup_temp_audio(keep_latest=2)
    assert len(deleted) == 3
    assert len(list(tmp_path.glob("*.wav"))) == 2
