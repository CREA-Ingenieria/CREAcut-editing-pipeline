"""Device selection and CUDA VRAM behaviour for Whisper transcription."""

from __future__ import annotations

from types import SimpleNamespace
import sys

from creacut.transcribe import transcribe


def _result():
    return {
        "text": " Hola mundo.",
        "segments": [
            {
                "start": 0.0,
                "end": 1.0,
                "text": " Hola mundo.",
                "no_speech_prob": 0.01,
                "words": [{"word": " Hola", "start": 0.0, "end": 0.5}],
            }
        ],
    }


def _config(model: str = "large-v3") -> dict:
    return {"whisper": {"model": model, "language": "es", "prompt": ""}}


def test_transcribe_selects_cuda_and_preserves_word_timestamps(
    tmp_dir, monkeypatch, capsys
):
    video = tmp_dir / "lesson.mp4"
    video.write_bytes(b"placeholder")
    monkeypatch.setattr("creacut.transcribe._load_audio", lambda path: "AUDIO")
    calls: list[tuple[str, str]] = []
    transcribe_calls: list[dict] = []

    class Model:
        def transcribe(self, audio, **kwargs):
            transcribe_calls.append({"audio": audio, **kwargs})
            return _result()

    def load_model(name, *, device):
        calls.append((name, device))
        return Model()

    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(
            is_available=lambda: True,
            get_device_name=lambda index: "NVIDIA Test GPU",
            empty_cache=lambda: None,
        )
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "whisper", SimpleNamespace(load_model=load_model))

    result = transcribe(video, _config(), verbose=True)

    assert calls == [("large-v3", "cuda")]
    assert transcribe_calls[0]["audio"] == "AUDIO"
    assert transcribe_calls[0]["fp16"] is True
    assert transcribe_calls[0]["word_timestamps"] is True
    assert result["segments"][0]["words"][0]["word"] == " Hola"
    assert "Whisper device: CUDA - NVIDIA Test GPU" in capsys.readouterr().out


def test_transcribe_uses_cpu_fp32_only_when_cuda_is_unavailable(
    tmp_dir, monkeypatch, capsys
):
    video = tmp_dir / "lesson.mp4"
    video.write_bytes(b"placeholder")
    monkeypatch.setattr("creacut.transcribe._load_audio", lambda path: "AUDIO")
    calls: list[tuple[str, str]] = []
    received_fp16: list[bool] = []

    class Model:
        def transcribe(self, _path, **kwargs):
            received_fp16.append(kwargs["fp16"])
            return _result()

    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)),
    )
    monkeypatch.setitem(
        sys.modules,
        "whisper",
        SimpleNamespace(
            load_model=lambda name, *, device: calls.append((name, device)) or Model()
        ),
    )

    transcribe(video, _config(), verbose=True)

    assert calls == [("large-v3", "cpu")]
    assert received_fp16 == [False]
    output = capsys.readouterr().out
    assert "Whisper device: CPU - CUDA unavailable" in output
    assert "Whisper precision: FP32" in output


def test_large_model_vram_oom_retries_medium_on_cuda(tmp_dir, monkeypatch, capsys):
    video = tmp_dir / "lesson.mp4"
    video.write_bytes(b"placeholder")
    monkeypatch.setattr("creacut.transcribe._load_audio", lambda path: "AUDIO")
    load_calls: list[tuple[str, str]] = []
    emptied: list[bool] = []

    class Model:
        def transcribe(self, _path, **kwargs):
            return _result()

    def load_model(name, *, device):
        load_calls.append((name, device))
        if name == "large-v3":
            raise RuntimeError("CUDA out of memory")
        return Model()

    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(
            cuda=SimpleNamespace(
                is_available=lambda: True,
                get_device_name=lambda index: "NVIDIA Test GPU",
                empty_cache=lambda: emptied.append(True),
            )
        ),
    )
    monkeypatch.setitem(sys.modules, "whisper", SimpleNamespace(load_model=load_model))

    transcribe(video, _config(), verbose=True)

    assert load_calls == [("large-v3", "cuda"), ("medium", "cuda")]
    assert emptied == [True]
    output = capsys.readouterr().out
    assert "retrying on CUDA with medium" in output
    assert "Whisper active model: medium" in output
