"""Background tasks used by the desktop CREAcut workflow.

The pipeline deliberately stays Qt-independent.  This module is the narrow
bridge between the GUI and the existing public analysis/render entry points.
"""

from __future__ import annotations

from contextlib import redirect_stdout
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Signal, Slot

from ..config import load_config
from ..pipeline import generate_edit_project, render_project


class _ProgressStream:
    """Turn pipeline ``print`` calls into thread-safe Qt progress signals."""

    def __init__(self, report: Callable[[str], None]) -> None:
        self._report = report
        self._pending = ""

    def write(self, text: str) -> int:
        self._pending += str(text)
        lines = self._pending.splitlines(keepends=True)
        self._pending = ""
        for line in lines:
            if line.endswith(("\n", "\r")):
                message = line.strip()
                if message:
                    self._report(message)
            else:
                self._pending = line
        return len(text)

    def flush(self) -> None:
        message = self._pending.strip()
        self._pending = ""
        if message:
            self._report(message)


class AnalysisWorker(QObject):
    """Generate an editable project from a source video and Markdown script."""

    progress = Signal(str)
    completed = Signal(str)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        video_path: str | Path,
        script_path: str | Path,
        project_path: str | Path,
        *,
        config_path: str | Path | None = None,
        background_image: str | Path | None = None,
        allow_replace: bool = False,
    ) -> None:
        super().__init__()
        self.video_path = Path(video_path).expanduser().resolve()
        self.script_path = Path(script_path).expanduser().resolve()
        self.project_path = Path(project_path).expanduser().resolve()
        self.config_path = (
            None
            if config_path is None
            else Path(config_path).expanduser().resolve()
        )
        self.background_image = (
            None
            if background_image is None
            else Path(background_image).expanduser().resolve()
        )
        self.allow_replace = allow_replace

    @Slot()
    def run(self) -> None:
        stream = _ProgressStream(self.progress.emit)
        try:
            if not self.video_path.is_file():
                raise ValueError(f"No se encontró el video: {self.video_path}")
            if not self.script_path.is_file():
                raise ValueError(f"No se encontró el guion Markdown: {self.script_path}")
            if self.project_path.exists() and not self.allow_replace:
                raise ValueError(
                    "Ya existe un proyecto con ese nombre. Elige otra carpeta "
                    "o confirma su reemplazo antes de analizar."
                )
            self.project_path.parent.mkdir(parents=True, exist_ok=True)
            config = load_config(str(self.config_path) if self.config_path else None)
            if self.background_image is not None:
                # Persisted into project.settings by generate_edit_project() below,
                # so render_project() picks it up automatically at export time
                # without any separate wiring (see creacut/pipeline.py).
                config["background"]["image"] = str(self.background_image)
            with redirect_stdout(stream):
                self.progress.emit("Preparando análisis de video y guion…")
                generate_edit_project(
                    str(self.video_path),
                    script=str(self.script_path),
                    config=config,
                    verbose=True,
                    project_output=str(self.project_path),
                )
                stream.flush()
            self.completed.emit(str(self.project_path))
        except BaseException as exc:  # The GUI must surface errors from native media libraries.
            self.failed.emit(str(exc) or type(exc).__name__)
        finally:
            self.finished.emit()


class RenderWorker(QObject):
    """Render a previously approved project without repeating analysis."""

    progress = Signal(str)
    completed = Signal(str)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, project_path: str | Path, output_path: str | Path) -> None:
        super().__init__()
        self.project_path = Path(project_path).expanduser().resolve()
        self.output_path = Path(output_path).expanduser().resolve()

    @Slot()
    def run(self) -> None:
        stream = _ProgressStream(self.progress.emit)
        try:
            if not self.project_path.is_file():
                raise ValueError(f"No se encontró el proyecto: {self.project_path}")
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            with redirect_stdout(stream):
                self.progress.emit("Preparando render final…")
                result = render_project(
                    self.project_path,
                    output=self.output_path,
                    verbose=True,
                )
                stream.flush()
            self.completed.emit(str(result))
        except BaseException as exc:  # The GUI must surface errors from native media libraries.
            self.failed.emit(str(exc) or type(exc).__name__)
        finally:
            self.finished.emit()
