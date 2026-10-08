"""Asistente de modelos: Windows prepara todo; macOS solo Whisper."""

from __future__ import annotations

import sys
from pathlib import Path

PYTHON_BRIDGE_DIR = Path(__file__).parents[1] / "electron-editor" / "python"
if str(PYTHON_BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_BRIDGE_DIR))

import setup_models  # noqa: E402


def _record(monkeypatch):
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(setup_models, "prepare_whisper", lambda name: calls.append(("whisper", name)))
    monkeypatch.setattr(setup_models, "prepare_ollama", lambda name: calls.append(("ollama", name)))
    return calls


def test_solo_whisper_on_macos_skips_ollama(monkeypatch):
    calls = _record(monkeypatch)
    monkeypatch.setattr(setup_models.sys, "platform", "darwin")

    assert setup_models.main(["--solo-whisper"]) == 0
    assert [kind for kind, _ in calls] == ["whisper"]


def test_windows_without_flag_prepares_whisper_and_ollama(monkeypatch):
    calls = _record(monkeypatch)
    monkeypatch.setattr(setup_models.sys, "platform", "win32")

    assert setup_models.main([]) == 0
    assert [kind for kind, _ in calls] == ["whisper", "ollama"]


def test_macos_without_flag_still_refuses(monkeypatch, capsys):
    calls = _record(monkeypatch)
    monkeypatch.setattr(setup_models.sys, "platform", "darwin")

    assert setup_models.main([]) == 1
    assert calls == []
    assert "instalador de Windows" in capsys.readouterr().out


def test_failure_is_reported_and_returns_one(monkeypatch, capsys):
    monkeypatch.setattr(setup_models.sys, "platform", "darwin")

    def offline(_name):
        raise OSError("sin conexión")

    monkeypatch.setattr(setup_models, "prepare_whisper", offline)

    assert setup_models.main(["--solo-whisper"]) == 1
    assert "ERROR: sin conexión" in capsys.readouterr().out
