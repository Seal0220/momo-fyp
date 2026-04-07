from pathlib import Path

from backend.tts.reference_selection import (
    build_fixed_reference_pair,
    choose_random_emotional_reference_pair,
    load_emotional_reference_pairs,
)


def test_load_emotional_reference_pairs_follows_manifest_order():
    manifest_names = [
        line.strip()
        for line in Path("resource/voice/emotional-ref/all-emotional.txt").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    pairs = load_emotional_reference_pairs()

    assert [pair.key for pair in pairs] == manifest_names


def test_load_emotional_reference_pairs_matches_case_insensitive_audio_suffix():
    pair_map = {pair.key: pair for pair in load_emotional_reference_pairs()}

    assert pair_map["感激與愧疚"].audio_path.endswith(".MP3")
    assert pair_map["感激與愧疚"].text_path.endswith(".txt")


def test_build_fixed_reference_pair_preserves_configured_paths():
    pair = build_fixed_reference_pair("resource/voice/ref-voice3.wav", "resource/voice/transcript3.txt")

    assert pair.audio_path == "resource/voice/ref-voice3.wav"
    assert pair.text_path == "resource/voice/transcript3.txt"
    assert pair.key == "transcript3"


def test_choose_random_emotional_reference_pair_uses_supplied_rng():
    class StubRandom:
        def choice(self, pairs):
            return pairs[-1]

    selected = choose_random_emotional_reference_pair(StubRandom())

    assert selected.key == "極度的悲慟和自責與絕望"
