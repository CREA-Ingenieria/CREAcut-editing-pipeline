"""Dependency-light launcher for the optional Qt editor."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from creacut import __version__


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="creacut-editor",
        description="Editor local de proyectos CREAcut.",
    )
    parser.add_argument(
        "project",
        nargs="?",
        help="Proyecto .creacut.json que se abrirá al iniciar",
    )
    parser.add_argument("--version", action="version", version=f"CREAcut {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        from .app import run_application
    except ModuleNotFoundError as exc:
        if exc.name is None or not (
            exc.name == "PySide6" or exc.name.startswith("PySide6.")
        ):
            raise
        print(
            "La interfaz necesita PySide6. Desde el repositorio instala: "
            'python -m pip install -e ".[ui]"',
            file=sys.stderr,
        )
        return 2
    return run_application(args.project)


if __name__ == "__main__":  # pragma: no cover - console entry point
    raise SystemExit(main())
