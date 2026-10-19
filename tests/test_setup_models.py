"""Asistente de modelos: Windows prepara todo; macOS solo Whisper."""

from __future__ import annotations

import ssl
import sys
from pathlib import Path
from urllib.error import URLError

import pytest

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


def _subjects(context: ssl.SSLContext) -> set[str]:
    return {
        value
        for cert in context.get_ca_certs()
        for rdn in cert["subject"]
        for key, value in rdn
        if key == "commonName"
    }


def test_downloads_trust_certifi_roots_even_if_windows_lacks_them():
    # Windows solo guarda las raíces que ya necesitó; ISRG Root X1 (Let's
    # Encrypt, detras de las descargas de GitHub) puede faltar en un equipo nuevo.
    assert {"ISRG Root X1", "GTS Root R1"} <= _subjects(setup_models.tls_context())


def test_download_uses_the_combined_context(monkeypatch, tmp_path):
    seen = {}

    def refuse(request, timeout, context):
        seen["context"] = context
        raise URLError("sin conexión")

    monkeypatch.setattr(setup_models, "urlopen", refuse)

    with pytest.raises(URLError):
        setup_models.download("https://ollama.com/download/OllamaSetup.exe", tmp_path / "OllamaSetup.exe")
    assert "ISRG Root X1" in _subjects(seen["context"])


def test_certificate_failure_explains_itself_and_cleans_up(monkeypatch, tmp_path):
    def untrusted(request, timeout, context):
        reason = ssl.SSLCertVerificationError(1, "certificate verify failed")
        reason.verify_message = "unable to get local issuer certificate"
        raise URLError(reason)

    monkeypatch.setattr(setup_models, "urlopen", untrusted)

    with pytest.raises(RuntimeError, match="unable to get local issuer certificate") as raised:
        setup_models.download("https://ollama.com/download/OllamaSetup.exe", tmp_path / "OllamaSetup.exe")
    assert "OllamaSetup.exe" in str(raised.value)
    assert list(tmp_path.iterdir()) == []
