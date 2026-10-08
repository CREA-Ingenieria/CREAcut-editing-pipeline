"""Comprueba que el entorno instalado sirve de verdad para el backend.

El asistente de Windows y la preparacion del primer arranque en macOS lo ejecutan despues de instalar las dependencias: que pip
termine sin error no garantiza que las ruedas sean utilizables en ese equipo, y
un fallo aqui se lee mucho mejor que un traceback al abrir la aplicacion.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--expect-cuda", action="store_true")
    args = parser.parse_args()

    import torch

    # Importar es la prueba: una rueda incompatible solo falla al cargarse.
    import anthropic  # noqa: F401
    import cv2  # noqa: F401
    import moviepy  # noqa: F401
    import numpy  # noqa: F401
    import ollama  # noqa: F401
    import pptx  # noqa: F401
    import pypdfium2  # noqa: F401
    import whisper  # noqa: F401

    import creacut.config  # noqa: F401
    from creacut.media import ffmpeg_executable

    subprocess.run([ffmpeg_executable(), "-version"], check=True, capture_output=True)

    if args.expect_cuda and not torch.version.cuda:
        print("ERROR: se instalo un PyTorch sin CUDA.")
        return 1

    build = f"CUDA {torch.version.cuda}" if torch.version.cuda else "CPU"
    print(f"torch {torch.__version__} ({build})")
    if torch.version.cuda:
        # Una rueda CUDA no implica una GPU usable: el controlador puede ser
        # mas antiguo que el runtime que trae la rueda.
        name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "ninguna"
        print(f"GPU detectada: {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
