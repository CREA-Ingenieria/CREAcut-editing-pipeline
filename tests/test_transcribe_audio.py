"""Whisper must not depend on an ``ffmpeg`` command on PATH."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest

from creacut import transcribe as transcribe_module


def test_load_audio_decodes_with_creacut_ffmpeg(monkeypatch):
    captured: dict = {}
    pcm = np.array([0, 16384, -32768], dtype=np.int16).tobytes()

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout=pcm, stderr=b"")

    monkeypatch.setattr(transcribe_module, "ffmpeg_executable", lambda: "/opt/ffmpeg-bin")
    monkeypatch.setattr(transcribe_module.subprocess, "run", fake_run)

    audio = transcribe_module._load_audio(Path("clase.mp4"))

    assert captured["command"] == [
        "/opt/ffmpeg-bin", "-nostdin", "-threads", "0", "-i", "clase.mp4",
        "-f", "s16le", "-ac", "1", "-acodec", "pcm_s16le", "-ar", "16000", "-",
    ]
    assert captured["kwargs"]["capture_output"] is True
    assert captured["kwargs"]["check"] is True
    assert audio.dtype == np.float32
    assert audio.tolist() == [0.0, 0.5, -1.0]


def test_load_audio_reports_ffmpeg_failure_in_spanish(monkeypatch):
    def failing_run(command, **kwargs):
        raise subprocess.CalledProcessError(1, command, output=b"", stderr=b"moov atom not found")

    monkeypatch.setattr(transcribe_module, "ffmpeg_executable", lambda: "ffmpeg")
    monkeypatch.setattr(transcribe_module.subprocess, "run", failing_run)

    with pytest.raises(RuntimeError, match=r"FFmpeg no pudo leer el audio de dañado\.mp4: moov atom not found"):
        transcribe_module._load_audio("dañado.mp4")
