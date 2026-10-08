"""PyInstaller-friendly desktop entry point for CREAcut."""

from creacut.ui.launcher import main


if __name__ == "__main__":  # pragma: no cover - used by PyInstaller
    raise SystemExit(main())
