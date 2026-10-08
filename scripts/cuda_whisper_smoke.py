"""Run one CREAcut Whisper transcription for a local CUDA smoke check.

It intentionally uses the project's public transcription function so the
reported device, FP16 handling, timestamps and cache path are the same ones
used by the desktop application and CLI.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from creacut.transcribe import transcribe


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Comprueba una transcripción CREAcut/Whisper con CUDA."
    )
    parser.add_argument("audio", type=Path, help="Audio o video de prueba")
    parser.add_argument(
        "--model", default="base", help="Modelo Whisper para la comprobación"
    )
    args = parser.parse_args()
    source = args.audio.expanduser().resolve()
    if not source.is_file():
        parser.error(f"No se encontró el archivo: {source}")
    result = transcribe(
        source,
        {"whisper": {"model": args.model, "language": "es", "prompt": ""}},
        verbose=True,
    )
    print(f"Whisper smoke test: {len(result.get('segments', []))} segmento(s)")
    return 0


if __name__ == "__main__":  # pragma: no cover - operational helper
    raise SystemExit(main())
