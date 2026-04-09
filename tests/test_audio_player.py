from backend.audio.player import AudioPlayer


def test_virtual_default_output_falls_back_to_physical_device(monkeypatch):
    player = AudioPlayer()

    monkeypatch.setattr(
        "backend.audio.player.sd.query_devices",
        lambda kind="output": {"index": 1, "name": "ianapp101", "max_output_channels": 2}
        if kind == "output"
        else [
            {"name": "Mic", "max_output_channels": 0},
            {"name": "ianapp101", "max_output_channels": 2},
            {"name": "MacBook Air Speakers", "max_output_channels": 2},
        ],
    )

    devices = [
        {"id": "1", "name": "ianapp101"},
        {"id": "4", "name": "MacBook Air Speakers"},
    ]
    monkeypatch.setattr(player, "list_output_devices", lambda: devices)

    assert player._resolve_output_device("default") == 4


def test_non_default_output_device_passes_through():
    player = AudioPlayer()
    assert player._resolve_output_device("6") == 6


def test_virtual_routing_keeps_system_default_output_even_if_virtual(monkeypatch):
    player = AudioPlayer()
    player.set_routed_playback(True)

    monkeypatch.setattr(
        "backend.audio.player.sd.query_devices",
        lambda kind="output": {"index": 1, "name": "BlackHole 2ch", "max_output_channels": 2}
        if kind == "output"
        else [
            {"name": "Mic", "max_output_channels": 0},
            {"name": "BlackHole 2ch", "max_output_channels": 2},
            {"name": "MacBook Air Speakers", "max_output_channels": 2},
        ],
    )

    assert player._resolve_output_device("default") == 1


def test_default_output_prefers_native_player_on_macos(monkeypatch):
    player = AudioPlayer()
    monkeypatch.setattr("backend.audio.player.platform.system", lambda: "Darwin")
    monkeypatch.setattr("backend.audio.player.shutil.which", lambda name: "/usr/bin/afplay" if name == "afplay" else None)

    player.set_output_device("default")

    assert player._use_native_default_player() is True


def test_explicit_device_keeps_sounddevice_backend(monkeypatch):
    player = AudioPlayer()
    monkeypatch.setattr("backend.audio.player.platform.system", lambda: "Darwin")
    monkeypatch.setattr("backend.audio.player.shutil.which", lambda name: "/usr/bin/afplay" if name == "afplay" else None)

    player.set_output_device("4")

    assert player._use_native_default_player() is False


def test_virtual_routing_disables_native_default_player_on_macos(monkeypatch):
    player = AudioPlayer()
    player.set_routed_playback(True)
    monkeypatch.setattr("backend.audio.player.platform.system", lambda: "Darwin")
    monkeypatch.setattr("backend.audio.player.shutil.which", lambda name: "/usr/bin/afplay" if name == "afplay" else None)

    player.set_output_device("default")

    assert player._use_native_default_player() is False
