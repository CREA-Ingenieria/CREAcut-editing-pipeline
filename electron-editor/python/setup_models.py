"""Prepare the configured AI models in the installing user's caches."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen


# En las instalaciones de Windows y de macOS este archivo vive en
# <backend>/python/ y el paquete creacut esta en <backend>/. Los dos instaladores
# lo ejecutan como script suelto con el Python del entorno armado desde PyPI, asi
# que hay que anadir esa raiz a sys.path.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def report(message: str) -> None:
    print(message, flush=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path, expected_sha256: str | None = None) -> None:
    """Stream to a temporary file; never load model weights into RAM or VRAM."""
    if expected_sha256 and destination.is_file():
        report(f"Comprobando {destination.name}...")
        if sha256(destination) == expected_sha256:
            report(f"{destination.name}: ya disponible.")
            return
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".part", delete=False) as tmp:
        partial = Path(tmp.name)
    try:
        report(f"Descargando {destination.name}...")
        request = Request(url, headers={"User-Agent": "CREAcut-Model-Setup/0.2"})
        with urlopen(request, timeout=120) as source, partial.open("wb") as output:
            total = int(source.headers.get("Content-Length") or 0)
            completed = 0
            last_report = 0.0
            while chunk := source.read(1024 * 1024):
                output.write(chunk)
                completed += len(chunk)
                if time.monotonic() - last_report >= 2:
                    progress = f"{completed * 100 // total}%" if total else f"{completed // (1024 * 1024)} MB"
                    report(f"{destination.name}: {progress}")
                    last_report = time.monotonic()
            if total and completed != total:
                raise RuntimeError(f"Descarga incompleta: {destination.name}")
        if expected_sha256 and sha256(partial) != expected_sha256:
            raise RuntimeError(f"La verificacion SHA-256 fallo: {destination.name}. Reintenta.")
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)


def prepare_whisper(model_name: str) -> None:
    import whisper
    from creacut.transcribe import _gpu_fallback_model

    cache = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "whisper"
    names = [model_name]
    fallback = _gpu_fallback_model(model_name)
    if fallback:
        names.append(fallback)
    for name in names:
        # Use the same model URLs/checksums as the bundled Whisper loader.
        url = whisper._MODELS[name]
        download(url, cache / f"{name}.pt", url.split("/")[-2])


def find_ollama() -> str | None:
    executable = shutil.which("ollama")
    if executable:
        return executable
    local = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Ollama" / "ollama.exe"
    return str(local) if local.is_file() else None


def prepare_ollama(model_name: str) -> None:
    import ollama

    configured_host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    host = configured_host if "://" in configured_host else f"http://{configured_host}"
    if urlparse(host).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("La instalacion de modelos requiere OLLAMA_HOST local (localhost:11434).")
    client = ollama.Client(host=host, timeout=120)

    def ready() -> bool:
        try:
            client.list()
            return True
        except (ConnectionError, OSError):
            return False

    if not ready():
        executable = find_ollama()
        if not executable:
            with tempfile.TemporaryDirectory(prefix="creacut-ollama-") as directory:
                installer = Path(directory) / "OllamaSetup.exe"
                download("https://ollama.com/download/OllamaSetup.exe", installer)
                report("Instalando Ollama para esta cuenta de Windows...")
                subprocess.run(
                    [str(installer), "/VERYSILENT", "/SP-", "/SUPPRESSMSGBOXES", "/NORESTART"],
                    check=True, creationflags=subprocess.CREATE_NO_WINDOW,
                )
            executable = find_ollama()
        if not executable:
            raise RuntimeError("No se encontro Ollama tras instalarlo. Reinstala Ollama y reintenta.")
        if not ready():
            report("Iniciando Ollama en segundo plano...")
            # The server remains available to CREAcut after setup exits.
            # Its log belongs to the user, not to the read-only app directory.
            log_dir = Path(os.environ["LOCALAPPDATA"]) / "CREAcut" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            with (log_dir / "ollama-setup.log").open("ab") as log:
                subprocess.Popen(
                    [executable, "serve"], stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
                    env={**os.environ, "OLLAMA_HOST": host},
                )
            for _ in range(60):
                if ready():
                    break
                time.sleep(1)
            else:
                raise RuntimeError("Ollama no inicia. Revisa %LOCALAPPDATA%/CREAcut/logs/ollama-setup.log.")

    report(f"Preparando el modelo configurado: {model_name}")
    # Preserve an already installed model instead of silently updating its tag.
    try:
        client.show(model_name)
        report(f"{model_name}: ya disponible.")
        return
    except ollama.ResponseError as error:
        if error.status_code != 404:
            raise

    last_status = ""
    last_report = 0.0
    succeeded = False
    for progress in client.pull(model_name, stream=True):
        status = progress.status
        now = time.monotonic()
        if status != last_status or now - last_report >= 2:
            percent = f" {100 * (progress.completed or 0) // progress.total}%" if progress.total else ""
            report(f"Gemma 4: {status}{percent}")
            last_status, last_report = status, now
        succeeded = status == "success"
    if not succeeded:
        raise RuntimeError("Ollama no confirmo la descarga completa. Reintenta la instalacion.")
    client.show(model_name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepara los modelos de IA de CREAcut.")
    parser.add_argument(
        "--solo-whisper",
        action="store_true",
        help="Prepara solo Whisper. Lo usa la preparación del primer arranque en macOS.",
    )
    args = parser.parse_args(argv)
    try:
        if not args.solo_whisper and sys.platform != "win32":
            raise RuntimeError("Este asistente de modelos corresponde al instalador de Windows.")
        from creacut.config import DEFAULTS

        report("Preparando modelos de CREAcut. Mantén la conexion a Internet.")
        prepare_whisper(DEFAULTS["whisper"]["model"])
        if not args.solo_whisper:
            prepare_ollama(DEFAULTS["overlays"]["lists"]["ollama_model"])
        report("Modelos preparados. CREAcut ya puede utilizarlos.")
        return 0
    except Exception as error:
        report(f"ERROR: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
