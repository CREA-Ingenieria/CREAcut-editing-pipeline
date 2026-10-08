"""Desktop entry point: create a project, review it, then export it."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QThread, Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .progress import TaskProgressDialog
from .qt import EditorWindow
from .batch import BatchDialog
from .tasks import AnalysisWorker


VIDEO_FILTER = "Video (*.mp4 *.mov *.mkv *.m4v *.avi *.webm);;Todos los archivos (*)"
SCRIPT_FILTER = "Guion Markdown (*.md *.markdown);;Todos los archivos (*)"
IMAGE_FILTER = "Imagen (*.png *.jpg *.jpeg *.bmp *.webp);;Todos los archivos (*)"

# Must match _LAST_PROJECT_SETTINGS_KEY in .qt — EditorWindow writes this key
# every time a project is opened or (auto)saved; StartWindow only reads it.
_LAST_PROJECT_SETTINGS_KEY = "lastProject/path"


class StartWindow(QMainWindow):
    """Simple first screen for the normal CREAcut desktop workflow."""

    def __init__(self) -> None:
        super().__init__()
        self._analysis_thread: QThread | None = None
        self._analysis_dialog: TaskProgressDialog | None = None
        self._editor: EditorWindow | None = None
        self._last_project_path: Path | None = None

        self.setWindowTitle("CREAcut")
        # 720x390/780x440 fit the original 3-field form; the resume banner
        # and Whisper-cache hint added since then need real headroom or
        # QVBoxLayout starts compressing rows (labels overlapping fields).
        self.setMinimumSize(760, 540)
        self.resize(820, 640)
        self.setStyleSheet(theme.build_start_stylesheet(theme.current_palette()))
        theme.bus.changed.connect(self._on_theme_changed)
        self._build()

    def _on_theme_changed(self, mode: str) -> None:
        colors = theme.current_palette()
        self.setStyleSheet(theme.build_start_stylesheet(colors))
        self.resume_banner.setStyleSheet(theme.resume_banner_style(colors))
        self.header_line.setStyleSheet(
            f"background-color: {colors['border']}; max-height: 1px; border: none;"
        )
        self.theme_toggle_button.setChecked(mode == "dark")
        self.theme_toggle_button.setText("☀" if mode == "dark" else "🌙")
        self.theme_toggle_button.setToolTip(
            "Cambiar a modo claro" if mode == "dark" else "Cambiar a modo oscuro"
        )
        self._update_whisper_cache_hint(Path(self._field(self.video_path).text()).expanduser())

    def _build(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(34, 28, 34, 28)
        layout.setSpacing(16)

        header_row = QHBoxLayout()
        title = QLabel("CREAcut")
        title.setStyleSheet("font-size: 28px; font-weight: 650;")
        header_row.addWidget(title)
        header_row.addStretch(1)
        is_dark = theme.get_mode() == "dark"
        self.theme_toggle_button = QPushButton("☀" if is_dark else "🌙")
        self.theme_toggle_button.setObjectName("themeToggleButton")
        self.theme_toggle_button.setCheckable(True)
        self.theme_toggle_button.setChecked(is_dark)
        self.theme_toggle_button.setFixedSize(34, 34)
        self.theme_toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_toggle_button.setToolTip(
            "Cambiar a modo claro" if is_dark else "Cambiar a modo oscuro"
        )
        self.theme_toggle_button.clicked.connect(theme.toggle_mode)
        header_row.addWidget(self.theme_toggle_button)
        layout.addLayout(header_row)
        description = QLabel(
            "Crea una propuesta de edición a partir de un video y su guion. "
            "Después podrás revisar los cortes antes de exportar el MP4 final."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self.resume_banner = QFrame()
        self.resume_banner.setStyleSheet(theme.resume_banner_style(theme.current_palette()))
        resume_layout = QHBoxLayout(self.resume_banner)
        self.resume_label = QLabel("")
        self.resume_label.setWordWrap(True)
        resume_layout.addWidget(self.resume_label, 1)
        self.resume_continue_button = QPushButton("Continuar")
        self.resume_continue_button.setObjectName("resumeContinueButton")
        self.resume_continue_button.clicked.connect(self._continue_last_project)
        resume_layout.addWidget(self.resume_continue_button)
        self.resume_dismiss_button = QPushButton("Descartar")
        self.resume_dismiss_button.setObjectName("resumeDismissButton")
        self.resume_dismiss_button.clicked.connect(self._dismiss_resume_banner)
        resume_layout.addWidget(self.resume_dismiss_button)
        self.resume_banner.hide()
        layout.addWidget(self.resume_banner)

        self.header_line = QFrame()
        self.header_line.setFrameShape(QFrame.Shape.HLine)
        self.header_line.setFrameShadow(QFrame.Shadow.Plain)
        self.header_line.setStyleSheet(
            f"background-color: {theme.current_palette()['border']}; max-height: 1px; border: none;"
        )
        layout.addWidget(self.header_line)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.video_path = self._path_field("Seleccionar video…", self._choose_video)
        self.script_path = self._path_field("Seleccionar guion…", self._choose_script)
        self.output_directory = self._path_field("Seleccionar carpeta…", self._choose_output_directory)
        self.background_image_path = self._path_field(
            "Seleccionar imagen…", self._choose_background_image, clearable=True
        )
        form.addRow("Video fuente:", self.video_path)
        form.addRow("Guion Markdown:", self.script_path)
        form.addRow("Carpeta de salida:", self.output_directory)
        form.addRow("Imagen de fondo (opcional):", self.background_image_path)
        layout.addLayout(form)

        background_hint = QLabel(
            "Si eliges una imagen, se usa para reemplazar el fondo verde (chroma key) "
            "al exportar. En el editor podrás ver un preview de un fotograma con ese fondo aplicado."
        )
        background_hint.setWordWrap(True)
        background_hint.setProperty("class", "muted")
        layout.addWidget(background_hint)

        self.project_hint = QLabel("Se creará: —")
        self.project_hint.setProperty("class", "muted")
        self.project_hint.setWordWrap(True)
        layout.addWidget(self.project_hint)

        self.whisper_cache_hint = QLabel("")
        self.whisper_cache_hint.setWordWrap(True)
        layout.addWidget(self.whisper_cache_hint)

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        self.batch_button = QPushButton("Procesar varios videos…")
        self.batch_button.setMinimumHeight(38)
        self.batch_button.clicked.connect(self._open_batch_dialog)
        action_row.addWidget(self.batch_button)
        self.analyze_button = QPushButton("Analizar y abrir editor")
        self.analyze_button.setDefault(True)
        self.analyze_button.setMinimumHeight(38)
        self.analyze_button.clicked.connect(self.start_analysis)
        action_row.addWidget(self.analyze_button)
        layout.addLayout(action_row)

        hint = QLabel(
            "Whisper se ejecuta localmente. La primera vez puede descargar el "
            "modelo configurado; necesitas conexión a Internet solo si aún no está en caché."
        )
        hint.setWordWrap(True)
        hint.setProperty("class", "muted")
        layout.addWidget(hint)
        self.setCentralWidget(central)
        self._refresh_controls()
        self._refresh_resume_banner()

    def _path_field(self, button_text: str, action, *, clearable: bool = False) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        field = QLineEdit()
        field.setReadOnly(True)
        field.textChanged.connect(self._refresh_controls)
        button = QPushButton(button_text)
        button.clicked.connect(action)
        row.addWidget(field, 1)
        row.addWidget(button)
        if clearable:
            clear_button = QPushButton("Quitar")
            clear_button.clicked.connect(lambda: field.setText(""))
            row.addWidget(clear_button)
        container.path_field = field  # type: ignore[attr-defined]
        return container

    @staticmethod
    def _field(container: QWidget) -> QLineEdit:
        return container.path_field  # type: ignore[attr-defined,no-any-return]

    def _choose_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar video fuente", str(Path.cwd()), VIDEO_FILTER)
        if path:
            self._field(self.video_path).setText(path)
            if not self._field(self.output_directory).text():
                self._field(self.output_directory).setText(str(Path(path).parent))

    def _choose_script(self) -> None:
        start = self._field(self.video_path).text() or str(Path.cwd())
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar guion Markdown", start, SCRIPT_FILTER)
        if path:
            self._field(self.script_path).setText(path)

    def _choose_output_directory(self) -> None:
        start = self._field(self.output_directory).text() or str(Path.cwd())
        path = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de salida", start)
        if path:
            self._field(self.output_directory).setText(path)

    def _choose_background_image(self) -> None:
        start = self._field(self.video_path).text() or str(Path.cwd())
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar imagen de fondo", start, IMAGE_FILTER)
        if path:
            self._field(self.background_image_path).setText(path)

    def suggested_project_path(self) -> Path | None:
        video = self._field(self.video_path).text().strip()
        output = self._field(self.output_directory).text().strip()
        if not video or not output:
            return None
        return Path(output).expanduser() / f"{Path(video).stem}.creacut.json"

    def _refresh_controls(self) -> None:
        video = Path(self._field(self.video_path).text()).expanduser()
        script = Path(self._field(self.script_path).text()).expanduser()
        output = Path(self._field(self.output_directory).text()).expanduser()
        target = self.suggested_project_path()
        self.analyze_button.setEnabled(video.is_file() and script.is_file() and output.is_dir())
        self.project_hint.setText(
            f"Se creará: {target}" if target is not None else "Se creará: —"
        )
        self._update_whisper_cache_hint(video)

    def _update_whisper_cache_hint(self, video: Path) -> None:
        # Mirrors the cache path transcribe() checks (creacut/transcribe.py):
        # video_path.resolve().with_suffix(".whisper.json"). Purely informational —
        # does not read or touch the cache file, only checks whether it exists.
        if not video.is_file():
            self.whisper_cache_hint.setText("")
            return
        cache_path = video.resolve().with_suffix(".whisper.json")
        if cache_path.is_file():
            self.whisper_cache_hint.setStyleSheet(f"color: {theme.current_palette()['ink_cyan']};")
            self.whisper_cache_hint.setText(
                f"✓ Transcripción en caché encontrada ({cache_path.name}): Whisper no "
                "se ejecutará de nuevo, el análisis será más rápido."
            )
        else:
            self.whisper_cache_hint.setStyleSheet(f"color: {theme.current_palette()['text_muted']};")
            self.whisper_cache_hint.setText(
                "Sin transcripción en caché: Whisper transcribirá el video completo "
                "(puede tardar varios minutos)."
            )

    def _refresh_resume_banner(self) -> None:
        raw_path = QSettings().value(_LAST_PROJECT_SETTINGS_KEY, "", type=str)
        path = Path(raw_path) if raw_path else None
        if path is None or not path.is_file():
            self._last_project_path = None
            self.resume_banner.hide()
            return
        self._last_project_path = path
        self.resume_label.setText(
            f"Tienes un proyecto sin terminar: {path.name} — ¿quieres continuarlo?"
        )
        self.resume_banner.show()

    def _continue_last_project(self) -> None:
        if self._last_project_path is not None:
            self._open_existing_project(self._last_project_path)

    def _dismiss_resume_banner(self) -> None:
        # Hides the offer for the rest of this run without touching the
        # QSettings pointer or the project file itself — fully reversible.
        self.resume_banner.hide()

    def start_analysis(self) -> None:
        target = self.suggested_project_path()
        video = Path(self._field(self.video_path).text()).expanduser()
        script = Path(self._field(self.script_path).text()).expanduser()
        if target is None or not video.is_file() or not script.is_file() or not target.parent.is_dir():
            QMessageBox.warning(self, "Datos incompletos", "Selecciona un video, un guion Markdown y una carpeta de salida válida.")
            return
        replace_existing = target.exists()
        if replace_existing:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle("Proyecto existente")
            box.setText(f"Ya existe {target.name}. ¿Qué quieres hacer?")
            box.setInformativeText(
                "Abrir tal cual no repite el análisis (alineación, detección de "
                "contenido, etc.) ni pierde ediciones manuales previas. Reemplazar "
                "vuelve a correr todo el análisis, aunque la transcripción de "
                "Whisper siga viniendo de la caché si ya existe."
            )
            open_button = box.addButton("Abrir tal cual", QMessageBox.ButtonRole.AcceptRole)
            replace_button = box.addButton(
                "Reemplazar (nuevo análisis)", QMessageBox.ButtonRole.DestructiveRole
            )
            box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(open_button)
            box.exec()
            clicked = box.clickedButton()
            if clicked is open_button:
                self._open_existing_project(target)
                return
            if clicked is not replace_button:
                return
        self.analyze_button.setEnabled(False)
        dialog = TaskProgressDialog("Analizando video", "Iniciando Whisper y alineación…", self)
        self._analysis_dialog = dialog
        thread = QThread(self)
        background_image = self._field(self.background_image_path).text().strip() or None
        worker = AnalysisWorker(
            video, script, target,
            background_image=background_image,
            allow_replace=replace_existing,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(dialog.append_progress)
        worker.completed.connect(self._analysis_completed)
        worker.failed.connect(self._analysis_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._analysis_thread_finished)
        self._analysis_thread = thread
        thread.start()
        dialog.exec()

    def _analysis_completed(self, project_path: str) -> None:
        if self._analysis_dialog is not None:
            self._analysis_dialog.accept()
        self.statusBar().showMessage("Análisis terminado. Abriendo editor…", 5000)
        self._show_editor(project_path)

    def _open_existing_project(self, project_path: str | Path) -> None:
        """Open an already-analyzed .creacut.json without touching the pipeline."""
        self.statusBar().showMessage("Abriendo proyecto existente…", 5000)
        self._show_editor(project_path)

    def _open_batch_dialog(self) -> None:
        dialog = BatchDialog(self._show_editor, self)
        dialog.exec()

    def _show_editor(self, project_path: str | Path) -> None:
        self._editor = EditorWindow(project_path)
        self._editor.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._editor.destroyed.connect(self._editor_closed)
        self._editor.show()
        self.hide()

    def _analysis_failed(self, message: str) -> None:
        if self._analysis_dialog is not None:
            self._analysis_dialog.reject()
        QMessageBox.critical(
            self,
            "No se pudo analizar el video",
            f"CREAcut no pudo crear el proyecto editable.\n\n{message}\n\n"
            "Comprueba que Whisper esté instalado y que haya conexión si el modelo aún no se descargó.",
        )

    def _analysis_thread_finished(self) -> None:
        self._analysis_thread = None
        self._analysis_dialog = None
        self._refresh_controls()

    def _editor_closed(self, *_args) -> None:
        self._editor = None
        self.show()
        self.raise_()
        self._refresh_resume_banner()


def run_application(initial_project: str | Path | None = None) -> int:
    """Run either the welcome screen or a requested existing project."""
    if QApplication.instance() is not None:
        raise RuntimeError("CREAcut necesita controlar el event loop de Qt")
    app = QApplication([sys.argv[0]])
    app.setApplicationName("CREAcut")
    app.setOrganizationName("CREAcut")
    window: QMainWindow
    if initial_project is None:
        window = StartWindow()
    else:
        window = EditorWindow(initial_project)
    window.show()
    return app.exec()
