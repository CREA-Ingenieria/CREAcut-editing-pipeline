"""Batch processing: analyze several (video, script) pairs in one queue.

Reuses AnalysisWorker (the same entry point StartWindow uses for a single
video) one pair at a time — Whisper is heavy on CPU/GPU, so pairs are
processed sequentially rather than in parallel. Each pair gets its own
self-contained folder under the chosen base directory:

    <carpeta_base>/<nombre_video>/
        <video>              (copia del original)
        <guion>.md           (copia del original)
        <video>.whisper.json (generado por transcribe(), cacheable)
        <video>.creacut.json (proyecto editable)

The exported final MP4 is NOT produced here — per-project export stays a
manual step in EditorWindow (File → Exportar MP4…), which already suggests
the project's own folder as the default destination, so it lands alongside
the rest without any extra wiring.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from .tasks import AnalysisWorker


VIDEO_FILTER = "Video (*.mp4 *.mov *.mkv *.m4v *.avi *.webm);;Todos los archivos (*)"
SCRIPT_FILTER = "Guion Markdown (*.md *.markdown);;Todos los archivos (*)"


class BatchDialog(QDialog):
    """Queue several (video, script) pairs and process them one at a time."""

    def __init__(self, open_project_callback: Callable[[str], None], parent=None) -> None:
        super().__init__(parent)
        self._open_project_callback = open_project_callback
        self._pairs: list[tuple[Path, Path]] = []
        self._queue: list[tuple[Path, Path]] = []
        self._generated_projects: list[Path] = []
        self._failed: list[tuple[Path, str]] = []
        self._thread: QThread | None = None
        self._processing = False
        self._output_directory: Path | None = None

        self.setWindowTitle("Procesar varios videos")
        self.setMinimumSize(640, 560)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Agrega pares de video + guion. Cada uno se analiza por separado "
            "(con su propia caché de Whisper) y queda organizado en su propia "
            "carpeta dentro de la carpeta base que elijas: video, guion, "
            "whisper.json y el proyecto editable. El video exportado se agrega "
            "a esa misma carpeta cuando lo exportes desde el editor."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        layout.addWidget(QLabel("Pares a procesar:"))
        self.pairs_list = QListWidget()
        layout.addWidget(self.pairs_list, 1)

        pair_buttons = QHBoxLayout()
        add_button = QPushButton("Agregar par…")
        add_button.clicked.connect(self._add_pair)
        pair_buttons.addWidget(add_button)
        remove_button = QPushButton("Quitar seleccionado")
        remove_button.clicked.connect(self._remove_selected_pair)
        pair_buttons.addWidget(remove_button)
        pair_buttons.addStretch(1)
        layout.addLayout(pair_buttons)

        output_row = QHBoxLayout()
        self.output_directory_label = QLabel("Carpeta base: (sin elegir)")
        self.output_directory_label.setWordWrap(True)
        output_row.addWidget(self.output_directory_label, 1)
        choose_output_button = QPushButton("Elegir carpeta base…")
        choose_output_button.clicked.connect(self._choose_output_directory)
        output_row.addWidget(choose_output_button)
        layout.addLayout(output_row)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(140)
        layout.addWidget(self.log)

        layout.addWidget(QLabel("Proyectos generados:"))
        self.results_list = QListWidget()
        layout.addWidget(self.results_list, 1)
        open_button = QPushButton("Abrir proyecto seleccionado")
        open_button.clicked.connect(self._open_selected_result)
        layout.addWidget(open_button)

        action_row = QHBoxLayout()
        self.start_button = QPushButton("Procesar todos")
        self.start_button.setDefault(True)
        self.start_button.clicked.connect(self._start_batch)
        action_row.addWidget(self.start_button)
        action_row.addStretch(1)
        self.close_button = QPushButton("Cerrar")
        self.close_button.clicked.connect(self.reject)
        action_row.addWidget(self.close_button)
        layout.addLayout(action_row)

    # --- pair list -------------------------------------------------

    def _add_pair(self) -> None:
        video, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar video", str(Path.cwd()), VIDEO_FILTER
        )
        if not video:
            return
        script, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar guion Markdown", video, SCRIPT_FILTER
        )
        if not script:
            return
        video_path = Path(video)
        script_path = Path(script)
        self._pairs.append((video_path, script_path))
        self.pairs_list.addItem(QListWidgetItem(f"{video_path.name}  +  {script_path.name}"))

    def _remove_selected_pair(self) -> None:
        if self._processing:
            return
        row = self.pairs_list.currentRow()
        if row < 0:
            return
        self.pairs_list.takeItem(row)
        del self._pairs[row]

    def _choose_output_directory(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta base", str(Path.cwd()))
        if path:
            self._output_directory = Path(path)
            self.output_directory_label.setText(f"Carpeta base: {path}")

    def _append_log(self, message: str) -> None:
        self.log.append(message)

    # --- queue processing --------------------------------------------

    def _start_batch(self) -> None:
        if self._processing:
            return
        if not self._pairs:
            QMessageBox.warning(
                self, "Nada para procesar", "Agrega al menos un par de video y guion."
            )
            return
        if self._output_directory is None or not self._output_directory.is_dir():
            QMessageBox.warning(
                self, "Carpeta base requerida", "Elige una carpeta base válida antes de procesar."
            )
            return
        self._queue = list(self._pairs)
        self._generated_projects = []
        self._failed = []
        self.results_list.clear()
        self._processing = True
        self.start_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.log.clear()
        self._append_log(f"Procesando {len(self._queue)} video(s)…")
        self._process_next()

    def _process_next(self) -> None:
        if not self._queue:
            self._processing = False
            self.start_button.setEnabled(True)
            self.close_button.setEnabled(True)
            self._append_log(
                f"— Listo: {len(self._generated_projects)} proyecto(s) generado(s), "
                f"{len(self._failed)} con error. —"
            )
            return
        video_path, script_path = self._queue.pop(0)
        try:
            video_folder = self._unique_folder(self._output_directory / video_path.stem)
            video_folder.mkdir(parents=True)
            copied_video = video_folder / video_path.name
            copied_script = video_folder / script_path.name
            shutil.copy2(video_path, copied_video)
            shutil.copy2(script_path, copied_script)
            project_path = video_folder / f"{video_path.stem}.creacut.json"
        except OSError as exc:
            self._failed.append((video_path, str(exc)))
            self._append_log(f"✗ {video_path.name}: no se pudo preparar la carpeta ({exc})")
            self._process_next()
            return

        self._append_log(f"▶ {video_path.name} → {video_folder.name}/")
        thread = QThread(self)
        worker = AnalysisWorker(copied_video, copied_script, project_path)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._append_log)
        worker.completed.connect(lambda path, v=video_path: self._item_completed(v, path))
        worker.failed.connect(lambda message, v=video_path: self._item_failed(v, message))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._process_next)
        self._thread = thread
        thread.start()

    def _item_completed(self, video_path: Path, project_path: str) -> None:
        self._generated_projects.append(Path(project_path))
        self._append_log(f"✓ {video_path.name}: proyecto listo")
        self.results_list.addItem(QListWidgetItem(video_path.stem))

    def _item_failed(self, video_path: Path, message: str) -> None:
        self._failed.append((video_path, message))
        self._append_log(f"✗ {video_path.name}: {message}")

    @staticmethod
    def _unique_folder(base: Path) -> Path:
        if not base.exists():
            return base
        n = 2
        while True:
            candidate = base.parent / f"{base.name}-{n}"
            if not candidate.exists():
                return candidate
            n += 1

    # --- results -------------------------------------------------------

    def _open_selected_result(self) -> None:
        row = self.results_list.currentRow()
        if row < 0 or row >= len(self._generated_projects):
            return
        project_path = self._generated_projects[row]
        self._open_project_callback(str(project_path))
        self.accept()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._processing:
            event.ignore()
            QMessageBox.information(
                self, "Procesando",
                "Espera a que termine el video actual antes de cerrar.",
            )
            return
        event.accept()
