from types import SimpleNamespace

from backend.tts.model_profiles import resolve_tts_model_profile
from backend.tts.qwen_clone import FishCloneTTS
from backend.tts.semantic_runtime import SemanticBenchmarkResult


class DummyBenchmarkTTS(FishCloneTTS):
    def __init__(
        self,
        model_path: str,
        ref_audio_path: str,
        ref_text_path: str,
        clone_voice_enabled: bool = True,
        device_mode: str = "auto",
        semantic_dispatch_mode: str = "single",
    ) -> None:
        self.model_path = model_path
        self.ref_audio_path = ref_audio_path
        self.ref_text_path = ref_text_path
        self.clone_voice_enabled = clone_voice_enabled
        self.device = device_mode
        self.device_backend = device_mode
        self.semantic_dispatch_mode = semantic_dispatch_mode
        self.model_profile = resolve_tts_model_profile(model_path)
        self.loaded = False


def test_benchmark_auto_profiles_logs_running_candidate(monkeypatch, capsys):
    model_path = "model/huggingface/hf_snapshots/fishaudio__fish-speech-1.5"
    plans = [
        SimpleNamespace(name="gpu", device_mode="gpu", semantic_dispatch_mode="single"),
        SimpleNamespace(name="semantic-auto-gpu", device_mode="gpu", semantic_dispatch_mode="auto"),
    ]
    results = {
        "gpu": SemanticBenchmarkResult(
            name="gpu",
            device_mode="gpu",
            semantic_dispatch_mode="single",
            elapsed_ms=1200,
            ok=True,
        ),
        "semantic-auto-gpu": SemanticBenchmarkResult(
            name="semantic-auto-gpu",
            device_mode="gpu",
            semantic_dispatch_mode="auto",
            elapsed_ms=900,
            ok=True,
        ),
    }

    monkeypatch.setattr("backend.tts.qwen_clone.benchmark_plans_for_current_host", lambda: plans)
    monkeypatch.setattr(
        "backend.tts.qwen_clone._run_benchmark_candidate_subprocess",
        lambda *, plan, **kwargs: results[plan.name],
    )

    selection = DummyBenchmarkTTS.benchmark_auto_profiles(
        model_path,
        "resource/voice/ref-voice3.wav",
        "resource/voice/transcript3.txt",
        clone_voice_enabled=True,
    )

    captured = capsys.readouterr()
    assert selection is not None
    assert selection.result.name == "semantic-auto-gpu"
    assert "[startup] tts benchmark running candidate=gpu device=gpu semantic=single" in captured.out
    assert "[startup] tts benchmark candidate=semantic-auto-gpu status=ok elapsed_ms=900 semantic=auto" in captured.out


def test_qwen_benchmark_auto_profiles_uses_device_only_candidates(monkeypatch):
    model_path = "model/huggingface/hf_snapshots/Qwen__Qwen3-TTS-12Hz-0.6B-Base"
    plans = [
        SimpleNamespace(name="gpu", device_mode="gpu", semantic_dispatch_mode="single"),
        SimpleNamespace(name="semantic-auto-gpu", device_mode="gpu", semantic_dispatch_mode="auto"),
        SimpleNamespace(name="cpu", device_mode="cpu", semantic_dispatch_mode="single"),
    ]
    seen_plan_names: list[str] = []
    results = {
        "gpu": SemanticBenchmarkResult(
            name="gpu",
            device_mode="gpu",
            semantic_dispatch_mode="single",
            elapsed_ms=800,
            ok=True,
        ),
        "cpu": SemanticBenchmarkResult(
            name="cpu",
            device_mode="cpu",
            semantic_dispatch_mode="single",
            elapsed_ms=1400,
            ok=True,
        ),
    }

    monkeypatch.setattr("backend.tts.qwen_clone.benchmark_plans_for_current_host", lambda: plans)

    def fake_runner(*, plan, **kwargs):
        seen_plan_names.append(plan.name)
        return results[plan.name]

    monkeypatch.setattr("backend.tts.qwen_clone._run_benchmark_candidate_subprocess", fake_runner)

    selection = DummyBenchmarkTTS.benchmark_auto_profiles(
        model_path,
        "resource/voice/ref-voice3.wav",
        "resource/voice/transcript3.txt",
        clone_voice_enabled=True,
    )

    assert selection is not None
    assert selection.result.name == "gpu"
    assert seen_plan_names == ["gpu", "cpu"]
