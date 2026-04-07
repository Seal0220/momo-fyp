from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path


EMOTIONAL_REFERENCE_DIR = Path("resource/voice/emotional-ref")
EMOTIONAL_REFERENCE_LIST_PATH = EMOTIONAL_REFERENCE_DIR / "all-emotional.txt"
_AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".aac", ".mp4"}


@dataclass(frozen=True)
class ReferencePair:
    key: str
    audio_path: str
    text_path: str


def build_fixed_reference_pair(audio_path: str, text_path: str) -> ReferencePair:
    key = Path(text_path).stem or Path(audio_path).stem or "fixed"
    return ReferencePair(key=key, audio_path=audio_path, text_path=text_path)


def load_emotional_reference_pairs(
    ref_dir: Path = EMOTIONAL_REFERENCE_DIR,
    manifest_path: Path = EMOTIONAL_REFERENCE_LIST_PATH,
) -> list[ReferencePair]:
    root = Path(ref_dir)
    manifest = Path(manifest_path)
    if not root.exists():
        raise FileNotFoundError(f"emotional reference directory not found: {root}")
    if not manifest.exists():
        raise FileNotFoundError(f"emotional reference manifest not found: {manifest}")

    names = [line.strip() for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not names:
        raise RuntimeError(f"emotional reference manifest is empty: {manifest}")

    audio_by_stem: dict[str, Path] = {}
    text_by_stem: dict[str, Path] = {}
    for entry in root.iterdir():
        if not entry.is_file():
            continue
        stem_key = entry.stem.casefold()
        suffix = entry.suffix.lower()
        if suffix in _AUDIO_SUFFIXES and stem_key not in audio_by_stem:
            audio_by_stem[stem_key] = entry
        if suffix == ".txt" and entry.resolve() != manifest.resolve() and stem_key not in text_by_stem:
            text_by_stem[stem_key] = entry

    pairs: list[ReferencePair] = []
    missing: list[str] = []
    for name in names:
        key = name.casefold()
        audio = audio_by_stem.get(key)
        text = text_by_stem.get(key)
        if audio is None or text is None:
            missing.append(name)
            continue
        pairs.append(ReferencePair(key=name, audio_path=str(audio), text_path=str(text)))

    if missing:
        raise FileNotFoundError(
            "emotional reference library is incomplete for: " + ", ".join(missing)
        )
    return pairs


def emotional_reference_pair_map(
    ref_dir: Path = EMOTIONAL_REFERENCE_DIR,
    manifest_path: Path = EMOTIONAL_REFERENCE_LIST_PATH,
) -> dict[str, ReferencePair]:
    return {pair.key: pair for pair in load_emotional_reference_pairs(ref_dir, manifest_path)}


def choose_random_emotional_reference_pair(
    rng: random.Random | None = None,
    ref_dir: Path = EMOTIONAL_REFERENCE_DIR,
    manifest_path: Path = EMOTIONAL_REFERENCE_LIST_PATH,
) -> ReferencePair:
    pairs = load_emotional_reference_pairs(ref_dir, manifest_path)
    picker = rng or random
    return picker.choice(pairs)
