"""PySide6 implementation of the local CREAcut project inspector.

This module is the only place in CREAcut that imports Qt.  It previews the
original media directly and the proposed edit as a virtual hard-cut timeline;
it does not render chroma, overlays, crossfades, or final audio processing.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QSignalBlocker, QThread, QTimer, Qt, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QFont, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..preview import PreviewClip, PreviewTimeline, PreviewTimelineError
from ..project import EditSegment
from ..project_io import ProjectFormatError
from ..source_timeline import SourceRegion, SourceTimelineProjection
from . import theme
from .playback import PreviewSeekGuard, next_preview_transition
from .progress import TaskProgressDialog
from .session import EditorSession, EditorSessionError, format_seconds
from .tasks import RenderWorker
from .timeline import SourceTimelineWidget, TimelineMediaCache


ORIGINAL_MODE = 0
EDIT_MODE = 1

# How often the editor checks for unsaved changes and, if any, saves them
# through the same session.save() manual "Guardar" already uses — no new
# file format, just an automatic periodic call to the existing save path.
_AUTOSAVE_INTERVAL_MS = 60_000

# QSettings key remembering the last project opened/saved, so StartWindow can
# offer to resume it without repeating the video/script/output-folder wizard.
_LAST_PROJECT_SETTINGS_KEY = "lastProject/path"

# CREA brand palette: see theme.py for the full light/dark token set and QSS
# builders. Names below are kept as a thin compatibility shim (bound to the
# *current* mode at import time) for code that only ever reads the brand
# hues, which never change between light/dark.
_palette = theme.current_palette()
_ACCENT = _palette["accent"]              # CREA magenta — primary actions, CTAs, focus
_ACCENT_HOVER = _palette["accent_hover"]  # CREA purple — hover/pressed depth on _ACCENT
_ACCENT_TEXT = _palette["accent_text"]
_FRAME = _palette["frame"]                # CREA cyan — frame/selection accent (never with white text)
_FRAME_TEXT = _palette["frame_text"]      # mandatory pairing for any _FRAME fill
_BORDER = _palette["border"]
_TEXT_MUTED = _palette["text_muted"]
_SUCCESS = _palette["ink_cyan"]


def _label(text: str = "—") -> QLabel:
    widget = QLabel(text)
    widget.setWordWrap(True)
    widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return widget


class EditorWindow(QMainWindow):
    """Minimal editor shell for inspection and fast cut preview."""

    def __init__(self, initial_project: str | Path | None = None) -> None:
        super().__init__()
        self.session = EditorSession()
        self.timeline: PreviewTimeline | None = None
        self.source_timeline: SourceTimelineProjection | None = None
        self._active_preview_clip: PreviewClip | None = None
        # The inspector still works with one editable script segment, while
        # the left dock now navigates the raw Whisper transcript instead of
        # repeating each script sentence in a long list.
        self._selected_edit_segment_id: str | None = None
        self._active_transcript_index: int | None = None
        # Edited time remains a float; milliseconds are only a UI projection.
        # This avoids choosing the outgoing clip when a cut falls between ms.
        self._current_edit_s = 0.0
        self._slider_dragging = False
        self._media_available = False
        self._media_seekable = False
        self._media_size_mismatch = False
        self._preview_error: str | None = None
        self._preview_seek_guard = PreviewSeekGuard()
        self._timeline_media_cache = TimelineMediaCache(self)
        self._render_thread: QThread | None = None
        self._render_dialog: TaskProgressDialog | None = None
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(_AUTOSAVE_INTERVAL_MS)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start()

        self.setWindowTitle("CREAcut Editor")
        self.setMinimumSize(1100, 680)
        self.resize(1450, 850)
        self.setStyleSheet(theme.build_stylesheet(theme.current_palette()))
        theme.bus.changed.connect(self._on_theme_changed)

        self._build_player()
        self._build_segment_dock()
        self._build_inspector_dock()
        self._build_actions()
        self._connect_player()
        self._set_document_controls(False)
        self.statusBar().showMessage("Abre un proyecto .creacut.json para comenzar")

        if initial_project is not None:
            self.open_project(initial_project)

    # --- theme ----------------------------------------------------------

    def _on_theme_changed(self, _mode: str) -> None:
        colors = theme.current_palette()
        self.setStyleSheet(theme.build_stylesheet(colors))
        self.media_notice.setStyleSheet(theme.danger_notice_style(colors))
        self._update_preview_notice()
        self.theme_toggle_button.setChecked(_mode == "dark")
        self.theme_toggle_button.setText("☀" if _mode == "dark" else "🌙")
        self.theme_toggle_button.setToolTip(
            "Cambiar a modo claro" if _mode == "dark" else "Cambiar a modo oscuro"
        )

    def _toggle_theme(self) -> None:
        theme.toggle_mode()

    # --- construction -------------------------------------------------

    def _build_player(self) -> None:
        central = QWidget(self)
        # Named so the stylesheet can paint its background without a blanket
        # QWidget selector, which previously also matched QVideoWidget below
        # and broke its native video rendering (a known Qt/QSS interaction).
        central.setObjectName("editorCentral")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Vista previa:"))
        self.preview_mode = QComboBox()
        self.preview_mode.addItem("Video original")
        self.preview_mode.addItem("Edición propuesta (cortes rápidos)")
        self.preview_mode.setToolTip(
            "La edición propuesta salta entre rangos del video fuente sin renderizar."
        )
        mode_row.addWidget(self.preview_mode)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)

        self.preview_notice = QLabel(
            "Preview rápido: muestra los cortes seleccionados; todavía no incluye "
            "chroma, overlays, crossfades, offsets ni procesamiento final de audio."
        )
        self.preview_notice.setWordWrap(True)
        self.preview_notice.setStyleSheet(theme.warning_notice_style(theme.current_palette()))
        self.preview_notice.hide()
        layout.addWidget(self.preview_notice)

        self.media_notice = QLabel()
        self.media_notice.setWordWrap(True)
        self.media_notice.setStyleSheet(theme.danger_notice_style(theme.current_palette()))
        self.media_notice.hide()
        layout.addWidget(self.media_notice)

        self.video_widget = QVideoWidget()
        # Do not reserve a fixed 640×360 area. When a dock is widened or the
        # preview notice appears, that constraint made the vertical layout
        # allocate overlapping geometries, letting the native video surface
        # paint on top of the transport controls. The video takes the spare
        # space instead and can shrink safely with the window.
        self.video_widget.setMinimumSize(0, 0)
        self.video_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Ignored,
        )
        layout.addWidget(self.video_widget, 1)

        transport = QHBoxLayout()
        self.previous_cut_button = QPushButton("◀ Corte anterior")
        self.play_button = QPushButton("Reproducir")
        self.play_button.setMinimumWidth(105)
        self.next_cut_button = QPushButton("Corte siguiente ▶")
        transport.addStretch(1)
        transport.addWidget(self.previous_cut_button)
        transport.addWidget(self.play_button)
        transport.addWidget(self.next_cut_button)
        transport.addStretch(1)
        layout.addLayout(transport)

        seek_row = QHBoxLayout()
        self.current_time_label = QLabel(format_seconds(0.0))
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.total_time_label = QLabel(format_seconds(0.0))
        seek_row.addWidget(self.current_time_label)
        seek_row.addWidget(self.seek_slider, 1)
        seek_row.addWidget(self.total_time_label)
        layout.addLayout(seek_row)

        timeline_actions = QGridLayout()
        timeline_actions.setHorizontalSpacing(6)
        timeline_actions.setVerticalSpacing(4)
        timeline_actions.addWidget(QLabel("Línea de tiempo"), 0, 0)
        self.timeline_zoom_out_button = QPushButton("−")
        self.timeline_zoom_out_button.setToolTip("Alejar línea de tiempo")
        self.timeline_zoom_in_button = QPushButton("+")
        self.timeline_zoom_in_button.setToolTip("Acercar línea de tiempo")
        self.timeline_split_button = QPushButton("Dividir")
        self.timeline_split_button.setToolTip("Divide la región en la posición actual del playhead")
        self.timeline_keep_button = QPushButton("Conservar")
        self.timeline_keep_button.setToolTip("Incluye la región seleccionada en el montaje final")
        self.timeline_discard_button = QPushButton("Descartar")
        self.timeline_discard_button.setToolTip("Excluye la región seleccionada del montaje final")
        self.timeline_restore_button = QPushButton("Restaurar")
        self.timeline_restore_button.setToolTip("Elimina el ajuste manual de la región")
        self.timeline_undo_button = QPushButton("↶")
        self.timeline_undo_button.setToolTip("Deshacer el último cambio de línea de tiempo (Ctrl+Z)")
        self.timeline_redo_button = QPushButton("↷")
        self.timeline_redo_button.setToolTip("Rehacer el último cambio de línea de tiempo (Ctrl+Shift+Z)")
        for button in (self.timeline_zoom_out_button, self.timeline_zoom_in_button):
            button.setMinimumWidth(42)
        for button in (self.timeline_undo_button, self.timeline_redo_button):
            button.setMinimumWidth(42)
        self.timeline_keep_button.setProperty("class", "success")
        self.timeline_discard_button.setProperty("class", "danger")
        timeline_actions.addWidget(self.timeline_zoom_out_button, 0, 1)
        timeline_actions.addWidget(self.timeline_zoom_in_button, 0, 2)
        timeline_actions.addWidget(self.timeline_split_button, 0, 3)
        timeline_actions.addWidget(self.timeline_keep_button, 1, 0, 1, 2)
        timeline_actions.addWidget(self.timeline_discard_button, 1, 2, 1, 2)
        timeline_actions.addWidget(self.timeline_restore_button, 1, 4)
        timeline_actions.addWidget(self.timeline_undo_button, 0, 4)
        timeline_actions.addWidget(self.timeline_redo_button, 0, 5)
        timeline_actions.setColumnStretch(6, 1)
        layout.addLayout(timeline_actions)

        self.source_timeline_widget = SourceTimelineWidget()
        self.source_timeline_scroll = QScrollArea()
        self.source_timeline_scroll.setObjectName("sourceTimelineScroll")
        self.source_timeline_scroll.setWidgetResizable(False)
        self.source_timeline_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.source_timeline_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.source_timeline_scroll.setWidget(self.source_timeline_widget)
        self.source_timeline_scroll.setMinimumHeight(215)
        layout.addWidget(self.source_timeline_scroll)

        self.setCentralWidget(central)

        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.85)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)

    def _build_segment_dock(self) -> None:
        dock = QDockWidget("Texto", self)
        dock.setObjectName("segmentsDock")
        dock.setMinimumWidth(340)

        self.text_tabs = QTabWidget()
        self.text_tabs.setObjectName("textTabs")

        transcript_page = QWidget()
        transcript_layout = QVBoxLayout(transcript_page)
        transcript_layout.setContentsMargins(8, 8, 8, 8)
        transcript_layout.setSpacing(6)
        transcript_hint = QLabel(
            "Contenido de Whisper. La frase activa se resalta al reproducir el audio."
        )
        transcript_hint.setObjectName("transcriptHint")
        transcript_hint.setWordWrap(True)
        transcript_layout.addWidget(transcript_hint)
        self.transcript_list = QListWidget()
        self.transcript_list.setObjectName("transcriptList")
        self.transcript_list.setAlternatingRowColors(True)
        self.transcript_list.setWordWrap(True)
        self.transcript_list.setToolTip(
            "Selecciona una frase para revisar su decisión; haz doble clic para ir a ese punto del audio."
        )
        transcript_layout.addWidget(self.transcript_list, 1)

        script_page = QWidget()
        script_layout = QVBoxLayout(script_page)
        script_layout.setContentsMargins(8, 8, 8, 8)
        script_layout.setSpacing(6)
        self.script_hint = QLabel("Guion original")
        self.script_hint.setObjectName("scriptHint")
        self.script_hint.setWordWrap(True)
        script_layout.addWidget(self.script_hint)
        self.script_view = QTextEdit()
        self.script_view.setObjectName("scriptView")
        self.script_view.setReadOnly(True)
        self.script_view.setPlaceholderText("Abre un proyecto para ver el guion.")
        self.script_view.setToolTip("Contenido completo del archivo de guion usado para el proyecto.")
        script_layout.addWidget(self.script_view, 1)

        self.text_tabs.addTab(transcript_page, "Transcripción")
        self.text_tabs.setTabToolTip(
            0, "Transcripción conservada desde whisper.json y sincronizada con el audio"
        )
        self.text_tabs.addTab(script_page, "Guion")
        self.text_tabs.setTabToolTip(1, "Archivo de guion completo usado para crear el proyecto")
        dock.setWidget(self.text_tabs)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _build_inspector_dock(self) -> None:
        dock = QDockWidget("Inspector de decisión", self)
        dock.setObjectName("inspectorDock")
        dock.setMinimumWidth(390)
        container = QWidget()
        layout = QVBoxLayout(container)

        form = QFormLayout()
        self.segment_id_value = _label()
        self.source_range_value = _label()
        self.edit_range_value = _label()
        self.score_value = _label()
        self.recommendation_value = _label()
        self.selection_reason_value = _label()
        self.offset_value = _label()
        self.timeline_region_value = _label()
        form.addRow("Oración:", self.segment_id_value)
        form.addRow("Rango fuente:", self.source_range_value)
        form.addRow("Posición en edición:", self.edit_range_value)
        form.addRow("Score:", self.score_value)
        form.addRow("Recomendación:", self.recommendation_value)
        form.addRow("Motivo automático:", self.selection_reason_value)
        form.addRow("Offset de audio:", self.offset_value)
        form.addRow("Región timeline:", self.timeline_region_value)
        layout.addLayout(form)

        layout.addWidget(QLabel("Guion"))
        self.script_text = QTextEdit()
        self.script_text.setReadOnly(True)
        self.script_text.setMaximumHeight(95)
        layout.addWidget(self.script_text)

        layout.addWidget(QLabel("Transcripción de la toma seleccionada"))
        self.transcript_text = QTextEdit()
        self.transcript_text.setReadOnly(True)
        self.transcript_text.setMaximumHeight(95)
        layout.addWidget(self.transcript_text)

        layout.addWidget(QLabel("Tomas candidatas"))
        self.candidate_table = QTableWidget(0, 6)
        self.candidate_table.setHorizontalHeaderLabels(
            ["Toma", "Estado", "Inicio", "Fin", "Score", "Transcripción"]
        )
        self.candidate_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.candidate_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.candidate_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.candidate_table.verticalHeader().setVisible(False)
        header = self.candidate_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.candidate_table, 1)

        candidate_actions = QHBoxLayout()
        self.use_candidate_button = QPushButton("Usar toma seleccionada")
        self.use_candidate_button.setToolTip(
            "Sustituye la toma actual por la fila seleccionada. También puedes "
            "hacer doble clic sobre una toma."
        )
        self.restore_recommended_button = QPushButton("Restaurar recomendación")
        self.restore_recommended_button.setToolTip(
            "Vuelve a la toma que CREAcut recomendó automáticamente."
        )
        self.use_candidate_button.setEnabled(False)
        self.restore_recommended_button.setEnabled(False)
        candidate_actions.addWidget(self.use_candidate_button)
        candidate_actions.addWidget(self.restore_recommended_button)
        layout.addLayout(candidate_actions)

        self.diagnostic_value = _label()
        layout.addWidget(QLabel("Diagnóstico"))
        layout.addWidget(self.diagnostic_value)

        dock.setWidget(container)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def _build_actions(self) -> None:
        file_menu = self.menuBar().addMenu("&Archivo")

        self.open_action = QAction("&Abrir proyecto…", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.choose_project)
        file_menu.addAction(self.open_action)

        self.save_action = QAction("&Guardar", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self.save_project)
        file_menu.addAction(self.save_action)

        self.save_as_action = QAction("Guardar &como…", self)
        self.save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.save_as_action.triggered.connect(self.save_project_as)
        file_menu.addAction(self.save_as_action)

        self.export_action = QAction("&Exportar MP4…", self)
        self.export_action.setShortcut("Ctrl+E")
        self.export_action.setToolTip(
            "Renderiza el proyecto aprobado sin volver a ejecutar Whisper ni la alineación"
        )
        self.export_action.triggered.connect(self.export_project)
        file_menu.addAction(self.export_action)

        self.background_preview_action = QAction("Vista previa con &fondo…", self)
        self.background_preview_action.setToolTip(
            "Compone el fotograma actual con la imagen de fondo del proyecto "
            "(mismo motor de chroma que usa la exportación final)"
        )
        self.background_preview_action.triggered.connect(self._show_background_preview)
        file_menu.addAction(self.background_preview_action)

        file_menu.addSeparator()
        self.locate_media_action = QAction("&Ubicar video fuente…", self)
        self.locate_media_action.triggered.connect(self.choose_source_media)
        file_menu.addAction(self.locate_media_action)

        file_menu.addSeparator()
        exit_action = QAction("&Salir", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

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
        self.theme_toggle_button.clicked.connect(self._toggle_theme)
        self.menuBar().setCornerWidget(self.theme_toggle_button)

    def _connect_player(self) -> None:
        self.play_button.clicked.connect(self.toggle_playback)
        self.previous_cut_button.clicked.connect(self.go_to_previous_cut)
        self.next_cut_button.clicked.connect(self.go_to_next_cut)
        self.preview_mode.currentIndexChanged.connect(self.change_preview_mode)
        self.seek_slider.sliderPressed.connect(self._slider_pressed)
        self.seek_slider.sliderReleased.connect(self._slider_released)
        self.seek_slider.sliderMoved.connect(self._slider_moved)
        self.player.positionChanged.connect(self._position_changed)
        self.player.durationChanged.connect(self._duration_changed)
        self.player.seekableChanged.connect(self._seekable_changed)
        self.player.playbackStateChanged.connect(self._playback_state_changed)
        self.player.errorOccurred.connect(self._player_error)
        self.transcript_list.currentItemChanged.connect(self._transcript_selected)
        self.transcript_list.itemActivated.connect(self._transcript_activated)
        self.candidate_table.itemSelectionChanged.connect(
            self._update_candidate_actions
        )
        self.candidate_table.itemDoubleClicked.connect(
            self._candidate_activated
        )
        self.use_candidate_button.clicked.connect(self._use_selected_candidate)
        self.restore_recommended_button.clicked.connect(
            self._restore_recommended_candidate
        )
        self.source_timeline_widget.seekRequested.connect(self._timeline_seek_requested)
        self.source_timeline_widget.regionSelected.connect(self._timeline_region_selected)
        self.source_timeline_widget.boundaryMoveRequested.connect(
            self._timeline_boundary_move_requested
        )
        self.timeline_zoom_out_button.clicked.connect(self.source_timeline_widget.zoom_out)
        self.timeline_zoom_in_button.clicked.connect(self.source_timeline_widget.zoom_in)
        self.timeline_split_button.clicked.connect(self._split_timeline_at_playhead)
        self.timeline_keep_button.clicked.connect(lambda: self._set_selected_region_keep(True))
        self.timeline_discard_button.clicked.connect(lambda: self._set_selected_region_keep(False))
        self.timeline_restore_button.clicked.connect(self._restore_selected_timeline_region)
        self.timeline_undo_button.clicked.connect(self._undo_timeline)
        self.timeline_redo_button.clicked.connect(self._redo_timeline)
        # Keyboard shortcuts mirroring the undo/redo buttons above.
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._undo_timeline)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self._redo_timeline)
        self._timeline_media_cache.ready.connect(self._timeline_media_ready)
        self._timeline_media_cache.failed.connect(self._timeline_media_failed)

    # --- project lifecycle --------------------------------------------

    def choose_project(self) -> None:
        if not self._confirm_discard_changes():
            return
        start = (
            str(self.session.project_path.parent)
            if self.session.project_path is not None
            else str(Path.cwd())
        )
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir proyecto CREAcut",
            start,
            "Proyecto CREAcut (*.creacut.json *.json);;JSON (*.json)",
        )
        if path:
            self.open_project(path, changes_confirmed=True)

    def open_project(
        self, path: str | Path, *, changes_confirmed: bool = False
    ) -> bool:
        if not changes_confirmed and not self._confirm_discard_changes():
            return False
        try:
            project = self.session.open(path)
        except (OSError, ProjectFormatError, ValueError) as exc:
            QMessageBox.critical(
                self, "No se pudo abrir el proyecto", str(exc)
            )
            return False
        try:
            self.timeline = PreviewTimeline.from_project(project)
            self._preview_error = None
        except PreviewTimelineError as exc:
            # A project with an invalid edited ordering is still useful for
            # inspection and repair; only its proposed preview is unavailable.
            self.timeline = None
            self._preview_error = str(exc)

        self._populate_segments()
        self._refresh_source_timeline()
        self._load_source_media()
        self._set_document_controls(True)
        self.preview_mode.setCurrentIndex(ORIGINAL_MODE)
        self._configure_timeline_controls()
        self._update_preview_notice()
        self._update_document_title()
        selected_count = sum(
            segment.selected_candidate_id is not None for segment in project.segments
        )
        self.statusBar().showMessage(
            f"{len(project.segments)} oraciones · {selected_count} con toma · "
            f"{len(project.segments) - selected_count} sin toma"
        )
        self._remember_last_project(self.session.project_path)
        return True

    def save_project(self) -> bool:
        try:
            path = self.session.save()
        except EditorSessionError:
            return self.save_project_as()
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "No se pudo guardar", str(exc))
            return False
        self._update_document_title()
        self.statusBar().showMessage(f"Proyecto guardado en {path}", 5000)
        self._remember_last_project(path)
        return True

    def _autosave(self) -> None:
        """Silently save pending changes; never interrupts editing with a dialog."""
        if not self.session.is_open or not self.session.refresh_dirty():
            return
        try:
            path = self.session.save()
        except (EditorSessionError, OSError, ValueError):
            # A brand-new, never-saved document or a transient I/O issue: the
            # existing "cambios sin guardar" prompt on close still protects the
            # user, so a failed background save stays quiet instead of popping
            # a dialog mid-edit.
            return
        self._update_document_title()
        self.statusBar().showMessage(f"Guardado automático · {path.name}", 3000)
        self._remember_last_project(path)

    @staticmethod
    def _remember_last_project(path: str | Path | None) -> None:
        if path is None:
            return
        QSettings().setValue(_LAST_PROJECT_SETTINGS_KEY, str(Path(path).resolve()))

    def save_project_as(self) -> bool:
        if not self.session.is_open:
            return False
        suggested = (
            str(self.session.project_path)
            if self.session.project_path is not None
            else str(Path.cwd() / "proyecto.creacut.json")
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar proyecto CREAcut",
            suggested,
            "Proyecto CREAcut (*.creacut.json);;JSON (*.json)",
        )
        if not path:
            return False
        try:
            saved = self.session.save(path)
        except (OSError, ValueError, EditorSessionError) as exc:
            QMessageBox.critical(self, "No se pudo guardar", str(exc))
            return False
        self._update_document_title()
        self.statusBar().showMessage(f"Proyecto guardado en {saved}", 5000)
        return True

    def _show_background_preview(self) -> None:
        """Compose the frame at the current playhead with the project's background
        image, using the same chroma engine export_project() uses at render time.

        Deliberately a single still frame, not real-time playback: the preview
        player above shows the raw source directly (see the module docstring),
        and rendering every frame through the chroma engine while scrubbing
        would not keep up. This reuses that same engine for one frame instead.
        """
        if not self.session.is_open or self.session.project is None:
            return
        settings = self.session.project.settings
        bg_path = settings.get("background", {}).get("image")
        if not bg_path:
            QMessageBox.information(
                self,
                "Sin imagen de fondo",
                "Este proyecto no tiene una imagen de fondo configurada. "
                "Elígela en la pantalla inicial al crear el proyecto para "
                "poder usar esta vista previa.",
            )
            return
        source = self.session.source_path()
        if source is None or not source.is_file():
            QMessageBox.warning(
                self, "Video fuente no disponible",
                "No se encontró el video fuente para componer la vista previa.",
            )
            return
        time_s = self.player.position() / 1000
        try:
            from ..chroma import extract_raw_frame, make_chroma_replacer

            frame = extract_raw_frame(str(source), time_s)
            replace = make_chroma_replacer(settings)
            composed = replace(frame)
        except Exception as exc:  # native codecs/OpenCV can fail in many ways
            QMessageBox.critical(
                self, "No se pudo generar la vista previa", str(exc)
            )
            return
        height, width, _ = composed.shape
        image = QImage(
            composed.tobytes(), width, height, width * 3, QImage.Format.Format_RGB888
        ).copy()
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Vista previa con fondo · {format_seconds(time_s)}")
        dialog_layout = QVBoxLayout(dialog)
        preview_label = QLabel()
        preview_label.setPixmap(
            QPixmap.fromImage(image).scaled(
                900, 900,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        dialog_layout.addWidget(preview_label)
        close_button = QPushButton("Cerrar")
        close_button.clicked.connect(dialog.accept)
        dialog_layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)
        dialog.exec()

    def export_project(self) -> None:
        """Save the editable decisions and start final rendering in the background."""
        if not self.session.is_open:
            return
        if self._render_thread is not None:
            QMessageBox.information(
                self, "Render en curso", "Ya hay una exportación en curso."
            )
            return
        if self.session.media_override is not None:
            QMessageBox.warning(
                self,
                "Video fuente temporal",
                "El video se localizó temporalmente desde otra ruta. Para preservar "
                "la procedencia del proyecto, la exportación usa la ruta original. "
                "Vuelve a colocar el archivo allí antes de exportar.",
            )
            return
        if self.session.refresh_dirty() and not self.save_project():
            return
        if self.session.project_path is None or self.session.project is None:
            return
        source = self.session.source_path()
        default_name = "video-final.mp4"
        if source is not None:
            default_name = f"{source.stem}_edited.mp4"
        suggested = str(self.session.project_path.parent / default_name)
        output, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar MP4 final",
            suggested,
            "Video MP4 (*.mp4)",
        )
        if not output:
            return
        output_path = Path(output).expanduser()
        if output_path.suffix.lower() != ".mp4":
            output_path = output_path.with_suffix(".mp4")
        if output_path.exists():
            answer = QMessageBox.question(
                self,
                "Archivo existente",
                f"{output_path.name} ya existe. ¿Quieres reemplazarlo?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._start_render(output_path)

    def _start_render(self, output_path: Path) -> None:
        project_path = self.session.project_path
        if project_path is None:
            return
        dialog = TaskProgressDialog(
            "Exportando MP4", "Preparando render final…", self
        )
        self._render_dialog = dialog
        thread = QThread(self)
        worker = RenderWorker(project_path, output_path)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(dialog.append_progress)
        worker.completed.connect(self._render_completed)
        worker.failed.connect(self._render_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._render_thread_finished)
        self._render_thread = thread
        thread.start()
        dialog.exec()

    def _render_completed(self, output_path: str) -> None:
        if self._render_dialog is not None:
            self._render_dialog.accept()
        self.statusBar().showMessage(f"Exportación terminada: {output_path}", 8000)
        QMessageBox.information(
            self, "Exportación terminada", f"El MP4 final se guardó en:\n{output_path}"
        )

    def _render_failed(self, message: str) -> None:
        if self._render_dialog is not None:
            self._render_dialog.reject()
        QMessageBox.critical(
            self,
            "No se pudo exportar",
            f"El proyecto sigue intacto; no fue necesario repetir el análisis.\n\n{message}",
        )

    def _render_thread_finished(self) -> None:
        self._render_thread = None
        self._render_dialog = None

    def _confirm_discard_changes(self) -> bool:
        if not self.session.is_open or not self.session.refresh_dirty():
            return True
        self._update_document_title()
        answer = QMessageBox.question(
            self,
            "Cambios sin guardar",
            "El proyecto tiene cambios sin guardar. ¿Quieres guardarlos?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self.save_project()
        return True

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt API)
        if self._confirm_discard_changes():
            # Release the multimedia backend explicitly. On Windows it may
            # otherwise keep the source file locked until QObject deletion or
            # process shutdown, which also makes reopening/moving media brittle.
            self.player.stop()
            self.player.setSource(QUrl())
            event.accept()
        else:
            event.ignore()

    # --- project display ----------------------------------------------

    def _set_document_controls(self, enabled: bool) -> None:
        self.save_action.setEnabled(enabled)
        self.save_as_action.setEnabled(enabled)
        self.export_action.setEnabled(enabled)
        self.background_preview_action.setEnabled(enabled)
        self.locate_media_action.setEnabled(enabled)
        self.preview_mode.setEnabled(enabled)
        self.text_tabs.setEnabled(enabled)
        self.source_timeline_scroll.setEnabled(enabled)
        if not enabled:
            self.play_button.setEnabled(False)
            self.previous_cut_button.setEnabled(False)
            self.next_cut_button.setEnabled(False)
            self.seek_slider.setEnabled(False)
            self.use_candidate_button.setEnabled(False)
            self.restore_recommended_button.setEnabled(False)
            self.timeline_zoom_out_button.setEnabled(False)
            self.timeline_zoom_in_button.setEnabled(False)
            self.timeline_split_button.setEnabled(False)
            self.timeline_keep_button.setEnabled(False)
            self.timeline_discard_button.setEnabled(False)
            self.timeline_restore_button.setEnabled(False)
            self.timeline_undo_button.setEnabled(False)
            self.timeline_redo_button.setEnabled(False)

    def _update_document_title(self) -> None:
        """Reflect the current path and dirty state in a platform-stable title."""
        if self.session.project_path is None:
            self.setWindowTitle("CREAcut Editor")
            self.setWindowModified(False)
            return
        # Session mutations and saves keep this flag current. Avoid
        # serializing the full Whisper snapshot again just to repaint a title.
        dirty = self.session.dirty
        self.setWindowTitle(
            f"{self.session.project_path.name}[*] — CREAcut Editor"
        )
        self.setWindowModified(dirty)

    def _populate_segments(self, *, selected_segment_id: str | None = None) -> None:
        project = self.session.project
        if project is None:
            self._active_transcript_index = None
            self._selected_edit_segment_id = None
            with QSignalBlocker(self.transcript_list):
                self.transcript_list.clear()
            self.script_view.clear()
            self.script_hint.setText("Guion original")
            self._clear_inspector()
            return

        self._active_transcript_index = None
        with QSignalBlocker(self.transcript_list):
            self.transcript_list.clear()
            for index, transcript_segment in enumerate(project.transcript.segments):
                start_s = float(transcript_segment["start"])
                end_s = float(transcript_segment["end"])
                text = str(transcript_segment.get("text", "")).strip()
                if not text:
                    text = "(Sin texto reconocido)"
                item = QListWidgetItem(
                    f"{index + 1:03d}  {format_seconds(start_s)}–"
                    f"{format_seconds(end_s)}\n{text}"
                )
                item.setData(Qt.ItemDataRole.UserRole, index)
                item.setToolTip(
                    f"{format_seconds(start_s)} – {format_seconds(end_s)}\n\n{text}"
                )
                self.transcript_list.addItem(item)

        self._load_script_view()
        visible_ids = {segment.id for segment in project.segments}
        target_id = selected_segment_id or self._selected_edit_segment_id
        if target_id not in visible_ids:
            target_id = project.segments[0].id if project.segments else None
        self._select_edit_segment(target_id)

    def _load_script_view(self) -> None:
        """Load the complete original script without making it a project dependency."""
        project = self.session.project
        if project is None:
            self.script_view.clear()
            self.script_hint.setText("Guion original")
            return
        script_path = Path(project.script.path).expanduser()
        try:
            text = script_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            self.script_hint.setText("Guion original no disponible")
            self.script_view.setPlainText(
                "No se pudo leer el archivo de guion asociado a este proyecto.\n\n"
                f"Ruta: {script_path}\n\nDetalle: {exc}"
            )
            self.script_view.setToolTip(str(script_path))
            return
        self.script_hint.setText(f"Guion original · {script_path.name}")
        self.script_view.setPlainText(text)
        self.script_view.setToolTip(str(script_path))

    def _select_edit_segment(self, segment_id: str | None) -> None:
        project = self.session.project
        if project is None or segment_id is None:
            self._selected_edit_segment_id = None
            self._clear_inspector()
            return
        segment = next(
            (item for item in project.segments if item.id == segment_id), None
        )
        if segment is None:
            self._selected_edit_segment_id = None
            self._clear_inspector()
            return
        self._selected_edit_segment_id = segment.id
        self._show_segment(segment)

    def _current_segment(self) -> EditSegment | None:
        project = self.session.project
        if project is None or self._selected_edit_segment_id is None:
            return None
        return next(
            (
                segment
                for segment in project.segments
                if segment.id == self._selected_edit_segment_id
            ),
            None,
        )

    def _transcript_selected(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        index = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(index, int):
            return
        self._active_transcript_index = index
        segment = self._edit_segment_for_transcript_index(index)
        if segment is not None:
            self._select_edit_segment(segment.id)

    def _transcript_activated(self, item: QListWidgetItem) -> None:
        project = self.session.project
        if project is None:
            return
        index = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(index, int) or not 0 <= index < len(project.transcript.segments):
            return
        self._seek_source_time(float(project.transcript.segments[index]["start"]))

    def _edit_segment_for_transcript_index(self, transcript_index: int) -> EditSegment | None:
        """Return the script decision associated with one Whisper segment."""
        project = self.session.project
        if project is None or not 0 <= transcript_index < len(project.transcript.segments):
            return None

        # A selected candidate reflects the actual current edit. If a user is
        # auditing another retake, fall back to all candidates so the inspector
        # still exposes the relevant script decision.
        for selected_only in (True, False):
            for segment in project.segments:
                candidates = (
                    (segment.selected_candidate,)
                    if selected_only
                    else segment.candidates
                )
                for candidate in candidates:
                    if (
                        candidate is not None
                        and candidate.segment_start_idx is not None
                        and candidate.segment_end_idx is not None
                        and candidate.segment_start_idx
                        <= transcript_index
                        <= candidate.segment_end_idx
                    ):
                        return segment

        raw_segment = project.transcript.segments[transcript_index]
        midpoint_s = (float(raw_segment["start"]) + float(raw_segment["end"])) / 2
        return next(
            (
                segment
                for segment in project.segments
                if segment.source_start_s is not None
                and segment.source_end_s is not None
                and segment.source_start_s <= midpoint_s <= segment.source_end_s
            ),
            None,
        )

    def _transcript_index_at(self, source_time_s: float) -> int | None:
        project = self.session.project
        if project is None:
            return None
        segments = project.transcript.segments
        for index, segment in enumerate(segments):
            start_s = float(segment["start"])
            end_s = float(segment["end"])
            if start_s <= source_time_s < end_s:
                return index
            if index == len(segments) - 1 and source_time_s == end_s:
                return index
        return None

    def _sync_transcript_to_source_position(self, source_time_s: float) -> None:
        """Highlight and center only the Whisper phrase currently being heard."""
        transcript_index = self._transcript_index_at(source_time_s)
        if transcript_index == self._active_transcript_index:
            return
        self._active_transcript_index = transcript_index
        with QSignalBlocker(self.transcript_list):
            if transcript_index is None:
                self.transcript_list.setCurrentRow(-1)
            else:
                self.transcript_list.setCurrentRow(transcript_index)
                item = self.transcript_list.item(transcript_index)
                if item is not None:
                    self.transcript_list.scrollToItem(
                        item,
                        QAbstractItemView.ScrollHint.PositionAtCenter,
                    )
        if transcript_index is not None:
            segment = self._edit_segment_for_transcript_index(transcript_index)
            if segment is not None:
                self._select_edit_segment(segment.id)

    def _seek_source_time(self, source_time_s: float) -> None:
        """Navigate from a raw transcript item without hiding removed footage."""
        if self.preview_mode.currentIndex() == EDIT_MODE and self.timeline is not None:
            edit_time = self.timeline.edit_time_at(source_time_s)
            if edit_time is not None:
                self._seek_edit_s(edit_time)
                return
        if self.preview_mode.currentIndex() == EDIT_MODE:
            self.preview_mode.setCurrentIndex(ORIGINAL_MODE)
            self.statusBar().showMessage(
                "Auditando la transcripción en el video fuente", 5000
            )
        self.player.setPosition(round(source_time_s * 1000))

    def _show_segment(self, segment: EditSegment) -> None:
        self.segment_id_value.setText(
            f"{segment.id} (párrafo {segment.paragraph_idx + 1}, "
            f"oración {segment.sentence_idx + 1})"
        )
        if segment.source_start_s is None or segment.source_end_s is None:
            self.source_range_value.setText("Sin toma seleccionada")
        else:
            self.source_range_value.setText(
                f"{format_seconds(segment.source_start_s)} – "
                f"{format_seconds(segment.source_end_s)} "
                f"({segment.duration_s:.3f} s)"
            )
        self.edit_range_value.setText(self._edit_range_text(segment))
        score = segment.alignment_score
        self.score_value.setText("—" if score is None else f"{score:.3f} ({score:.1%})")
        recommended = segment.automatic_selection.recommended_candidate_id
        selected = segment.selected_candidate_id
        if recommended is None:
            recommendation = "Sin recomendación automática"
        elif selected == recommended:
            recommendation = "Seleccionada (recomendación automática)"
        else:
            recommendation = "La selección actual difiere de la recomendada"
        self.recommendation_value.setText(recommendation)
        self.selection_reason_value.setText(
            segment.automatic_selection.selection_reason
        )
        global_offset = (
            0.0 if self.session.project is None else self.session.project.audio_offset_s
        )
        self.offset_value.setText(
            f"segmento {segment.audio_offset_s:+.3f} s · "
            f"global {global_offset:+.3f} s"
        )
        region = self._selected_timeline_region()
        if region is None:
            self.timeline_region_value.setText("—")
        else:
            origin = {
                "automatic": "automática",
                "manual": "manual",
                "segment": "cambio de toma o ajuste de segmento",
            }.get(region.origin, region.origin)
            disposition = "conservar" if region.keep else "descartar"
            self.timeline_region_value.setText(
                f"{disposition} · {format_seconds(region.start_s)} – "
                f"{format_seconds(region.end_s)} · {origin}"
            )
        self.script_text.setPlainText(segment.script_text)
        self.transcript_text.setPlainText(segment.transcript_text or "—")

        rejected = {
            rejection.candidate_id: ", ".join(rejection.reasons)
            for rejection in segment.automatic_selection.rejected_candidates
        }
        selected_row: int | None = None
        with QSignalBlocker(self.candidate_table):
            self.candidate_table.setRowCount(len(segment.candidates))
            for row, candidate in enumerate(segment.candidates):
                states: list[str] = []
                if candidate.id == selected:
                    states.append("seleccionada")
                    selected_row = row
                if candidate.id == recommended:
                    states.append("recomendada")
                if candidate.id in rejected:
                    states.append("descartada")
                values = (
                    f"Toma {self._take_name(row)}",
                    " + ".join(states) or "alternativa",
                    format_seconds(candidate.source_start_s),
                    format_seconds(candidate.source_end_s),
                    f"{candidate.score:.3f}",
                    candidate.transcript_text,
                )
                for column, value in enumerate(values):
                    cell = QTableWidgetItem(value)
                    cell.setData(Qt.ItemDataRole.UserRole, candidate.id)
                    cell.setToolTip(
                        f"ID: {candidate.id}"
                        + (
                            f"\nMotivo de descarte: {rejected[candidate.id]}"
                            if candidate.id in rejected
                            else ""
                        )
                    )
                    if candidate.id == selected:
                        font = QFont(cell.font())
                        font.setBold(True)
                        cell.setFont(font)
                    self.candidate_table.setItem(row, column, cell)
            if selected_row is not None:
                self.candidate_table.selectRow(selected_row)
            elif segment.candidates:
                self.candidate_table.selectRow(0)
        self._update_candidate_actions()
        auto = segment.automatic_selection
        diagnostics = [
            f"Piso aplicado: {auto.applied_floor_s:.3f} s",
            f"Piso cronológico: {auto.chronological_floor_s:.3f} s",
            f"Fallback: {'sí' if auto.fallback_used else 'no'}",
            f"Alternativas detectadas: {len(segment.candidates)}",
        ]
        if auto.retake_floor_s is not None:
            diagnostics.append(f"Piso por retoma: {auto.retake_floor_s:.3f} s")
        self.diagnostic_value.setText(" · ".join(diagnostics))

    @staticmethod
    def _take_name(index: int) -> str:
        """Return spreadsheet-like names: A..Z, AA.. for visible takes."""
        result = ""
        value = index + 1
        while value:
            value, remainder = divmod(value - 1, 26)
            result = chr(ord("A") + remainder) + result
        return result

    def _edit_range_text(self, segment: EditSegment) -> str:
        if segment.source_start_s is None or segment.source_end_s is None:
            return "No incluida en la edición"
        if self.timeline is None:
            return "No disponible (preview inválido)"
        edit_start = self.timeline.edit_time_at(segment.source_start_s)
        edit_end = self.timeline.edit_time_at(segment.source_end_s)
        if edit_start is None or edit_end is None:
            return "No disponible"
        return (
            f"{format_seconds(edit_start)} – {format_seconds(edit_end)} "
            f"({edit_end - edit_start:.3f} s)"
        )

    def _candidate_id_at_row(self, row: int) -> str | None:
        if row < 0:
            return None
        item = self.candidate_table.item(row, 0)
        if item is None:
            return None
        candidate_id = item.data(Qt.ItemDataRole.UserRole)
        return candidate_id if isinstance(candidate_id, str) else None

    def _update_candidate_actions(self) -> None:
        segment = self._current_segment()
        candidate_id = self._candidate_id_at_row(
            self.candidate_table.currentRow()
        )
        self.use_candidate_button.setEnabled(
            segment is not None
            and candidate_id is not None
            and candidate_id != segment.selected_candidate_id
        )
        self.restore_recommended_button.setEnabled(
            segment is not None
            and segment.selected_candidate_id
            != segment.automatic_selection.recommended_candidate_id
        )

    def _candidate_activated(self, item: QTableWidgetItem) -> None:
        self.candidate_table.selectRow(item.row())
        self._use_selected_candidate()

    def _use_selected_candidate(self) -> None:
        segment = self._current_segment()
        candidate_id = self._candidate_id_at_row(
            self.candidate_table.currentRow()
        )
        if segment is None or candidate_id is None:
            return
        try:
            updated = self.session.select_candidate(segment.id, candidate_id)
        except EditorSessionError as exc:
            QMessageBox.warning(self, "No se pudo cambiar la toma", str(exc))
            return
        self._refresh_after_candidate_change(updated.id, "Toma seleccionada")

    def _restore_recommended_candidate(self) -> None:
        segment = self._current_segment()
        if segment is None:
            return
        try:
            updated = self.session.restore_recommended(segment.id)
        except EditorSessionError as exc:
            QMessageBox.warning(
                self, "No se pudo restaurar la recomendación", str(exc)
            )
            return
        self._refresh_after_candidate_change(
            updated.id, "Recomendación automática restaurada"
        )

    def _refresh_after_candidate_change(
        self, segment_id: str, status_message: str
    ) -> None:
        """Refresh all projections after the session commits a model change."""
        project = self.session.project
        if project is None:
            return
        self.player.pause()
        self._active_preview_clip = None
        self._preview_seek_guard.reset()
        source_duration_s = (
            self.player.duration() / 1000
            if self._media_available and self.player.duration() > 0
            else None
        )
        try:
            self.timeline = PreviewTimeline.from_project(
                project, source_duration_s=source_duration_s
            )
            self._preview_error = None
        except PreviewTimelineError as exc:
            self.timeline = None
            self._preview_error = str(exc)

        self._refresh_source_timeline()
        self._populate_segments(selected_segment_id=segment_id)
        self._update_document_title()
        self._configure_timeline_controls()
        self._update_preview_notice()

        updated = next(
            (segment for segment in project.segments if segment.id == segment_id),
            None,
        )
        if updated is not None and updated.source_start_s is not None:
            if self.preview_mode.currentIndex() == EDIT_MODE:
                edit_time = (
                    None
                    if self.timeline is None
                    else self.timeline.edit_time_at(updated.source_start_s)
                )
                if edit_time is not None:
                    self._seek_edit_s(edit_time)
            else:
                self.player.setPosition(round(updated.source_start_s * 1000))
        self.statusBar().showMessage(status_message, 5000)

    # --- source timeline ---------------------------------------------

    def _known_source_duration_s(self) -> float | None:
        if self.player.duration() > 0:
            return self.player.duration() / 1000
        project = self.session.project
        if project is None:
            return None
        state = project.source_timeline_state()
        if state is not None:
            return state.source_duration_s
        return project.source.duration_s

    def _refresh_source_timeline(self) -> None:
        duration = self._known_source_duration_s()
        if self.session.project is None or duration is None or duration <= 0.0:
            self.source_timeline = None
            self.source_timeline_widget.set_projection(None)
            self._configure_timeline_edit_actions()
            return
        try:
            self.source_timeline = self.session.source_timeline(duration)
        except EditorSessionError as exc:
            self.source_timeline = None
            self.source_timeline_widget.set_projection(None)
            self.statusBar().showMessage(str(exc), 7000)
        else:
            self.source_timeline_widget.set_projection(self.source_timeline)
            self.source_timeline_widget.set_playhead(self.player.position() / 1000)
            source = self.session.source_path()
            # Start expensive frame/audio decoding only after Qt has confirmed
            # that the located media has a real duration.  A placeholder or
            # corrupt file can still be inspected as a project without noisy
            # decoder work in the background.
            if source is not None and source.is_file() and self.player.duration() > 0:
                cache_dir = (
                    None
                    if self.session.project_path is None
                    else self.session.project_path.parent / ".creacut-cache"
                )
                self._timeline_media_cache.request(
                    source, duration, cache_dir=cache_dir
                )
        self._configure_timeline_edit_actions()

    def _configure_timeline_edit_actions(self) -> None:
        region = self._selected_timeline_region()
        available = self.source_timeline is not None
        self.timeline_zoom_out_button.setEnabled(available)
        self.timeline_zoom_in_button.setEnabled(available)
        self.timeline_split_button.setEnabled(
            available and self._media_seekable and self._media_available
        )
        self.timeline_keep_button.setEnabled(available and region is not None and not region.keep)
        self.timeline_discard_button.setEnabled(available and region is not None and region.keep)
        self.timeline_restore_button.setEnabled(
            available and region is not None and region.is_modified
        )
        self.timeline_undo_button.setEnabled(self.session.can_undo_timeline)
        self.timeline_redo_button.setEnabled(self.session.can_redo_timeline)

    def _selected_timeline_region(self) -> SourceRegion | None:
        projection = self.source_timeline
        if projection is None:
            return None
        return projection.region_by_id(self.source_timeline_widget.selected_region_id or "")

    def _timeline_region_selected(self, region_id: str) -> None:
        region = None if self.source_timeline is None else self.source_timeline.region_by_id(region_id)
        self.source_timeline_widget.set_selected_region(region_id)
        if region is not None and region.linked_segment_ids:
            project = self.session.project
            if project is not None:
                segment_id = region.linked_segment_ids[0]
                self._select_edit_segment(segment_id)
        elif region is not None:
            self.timeline_region_value.setText(
                f"{'conservar' if region.keep else 'descartar'} · "
                f"{format_seconds(region.start_s)} – {format_seconds(region.end_s)}"
            )
        self._configure_timeline_edit_actions()

    def _timeline_seek_requested(self, source_time_s: float) -> None:
        region = None if self.source_timeline is None else self.source_timeline.region_at(source_time_s)
        if self.preview_mode.currentIndex() == EDIT_MODE and self.timeline is not None:
            edit_time = self.timeline.edit_time_at(source_time_s)
            if edit_time is not None:
                self._seek_edit_s(edit_time)
                return
            # Removed material has no edited-time coordinate.  Audit it using
            # the original source rather than pretending it belongs to the cut.
            self.preview_mode.setCurrentIndex(ORIGINAL_MODE)
            self.statusBar().showMessage("Auditando material descartado en el video fuente", 5000)
        if region is not None:
            self.source_timeline_widget.set_playhead(source_time_s)
        self.player.setPosition(round(source_time_s * 1000))

    def _timeline_boundary_move_requested(self, old_s: float, new_s: float) -> None:
        duration = self._known_source_duration_s()
        if duration is None:
            return
        new_s = self._snap_to_word_time(new_s)
        try:
            self.session.move_timeline_boundary(
                old_s, new_s, source_duration_s=duration
            )
        except EditorSessionError as exc:
            QMessageBox.warning(self, "No se pudo mover el corte", str(exc))
            return
        self._refresh_after_timeline_change("Corte manual actualizado")

    def _split_timeline_at_playhead(self) -> None:
        duration = self._known_source_duration_s()
        if duration is None:
            return
        try:
            self.session.split_timeline(
                self.player.position() / 1000,
                source_duration_s=duration,
            )
        except EditorSessionError as exc:
            QMessageBox.warning(self, "No se pudo dividir", str(exc))
            return
        self._refresh_after_timeline_change("Región dividida en el playhead")

    def _set_selected_region_keep(self, keep: bool) -> None:
        region = self._selected_timeline_region()
        duration = self._known_source_duration_s()
        if region is None or duration is None:
            return
        try:
            self.session.mark_timeline_range(
                region.start_s, region.end_s, keep=keep, source_duration_s=duration
            )
        except EditorSessionError as exc:
            QMessageBox.warning(self, "No se pudo editar la región", str(exc))
            return
        self._refresh_after_timeline_change(
            "Región marcada para conservar" if keep else "Región marcada para descartar"
        )

    def _restore_selected_timeline_region(self) -> None:
        region = self._selected_timeline_region()
        duration = self._known_source_duration_s()
        if region is None or duration is None:
            return
        try:
            self.session.restore_timeline_range(
                region.start_s, region.end_s, source_duration_s=duration
            )
        except EditorSessionError as exc:
            QMessageBox.warning(self, "No se pudo restaurar", str(exc))
            return
        self._refresh_after_timeline_change("Recomendación automática restaurada")

    def _undo_timeline(self) -> None:
        try:
            changed = self.session.undo_timeline()
        except EditorSessionError as exc:
            QMessageBox.warning(self, "No se pudo deshacer", str(exc))
            return
        if changed:
            self._refresh_after_timeline_change("Cambio de línea de tiempo deshecho")

    def _redo_timeline(self) -> None:
        try:
            changed = self.session.redo_timeline()
        except EditorSessionError as exc:
            QMessageBox.warning(self, "No se pudo rehacer", str(exc))
            return
        if changed:
            self._refresh_after_timeline_change("Cambio de línea de tiempo rehecho")

    def _refresh_after_timeline_change(self, status_message: str) -> None:
        project = self.session.project
        if project is None:
            return
        duration = self._known_source_duration_s()
        try:
            self.timeline = PreviewTimeline.from_project(
                project, source_duration_s=duration
            )
            self._preview_error = None
        except PreviewTimelineError as exc:
            self.timeline = None
            self._preview_error = str(exc)
        self._refresh_source_timeline()
        current = self._current_segment()
        if current is not None:
            self._show_segment(current)
        self._configure_timeline_controls()
        self._update_preview_notice()
        self._update_document_title()
        self.statusBar().showMessage(status_message, 5000)

    def _snap_to_word_time(self, source_time_s: float) -> float:
        """Use nearby Whisper word edges when available, otherwise keep the drag time."""
        project = self.session.project
        if project is None:
            return source_time_s
        candidates: list[float] = []
        for segment in project.transcript.segments:
            for word in segment.get("words", []):
                for key in ("start", "end"):
                    value = word.get(key)
                    if isinstance(value, (int, float)):
                        candidates.append(float(value))
        if not candidates:
            return source_time_s
        nearest = min(candidates, key=lambda value: abs(value - source_time_s))
        return nearest if abs(nearest - source_time_s) <= 0.12 else source_time_s

    def _timeline_media_ready(self, thumbnails, waveform) -> None:
        self.source_timeline_widget.set_media_data(thumbnails, waveform)

    def _timeline_media_failed(self, message: str) -> None:
        # Filmstrip/waveform are optional diagnostics; a failure must not make
        # source edits or playback unavailable.
        self.statusBar().showMessage(f"No se pudo generar la caché visual: {message}", 5000)

    def _clear_inspector(self) -> None:
        for widget in (
            self.segment_id_value,
            self.source_range_value,
            self.edit_range_value,
            self.score_value,
            self.recommendation_value,
            self.selection_reason_value,
            self.offset_value,
            self.timeline_region_value,
            self.diagnostic_value,
        ):
            widget.setText("—")
        self.script_text.clear()
        self.transcript_text.clear()
        self.candidate_table.setRowCount(0)
        self._update_candidate_actions()

    # --- media --------------------------------------------------------

    def choose_source_media(self) -> None:
        current = self.session.source_path()
        start = str(current.parent if current is not None else Path.cwd())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Ubicar video fuente",
            start,
            "Video (*.mp4 *.mov *.mkv *.m4v *.avi);;Todos los archivos (*)",
        )
        if path:
            self.session.set_media_override(path)
            self._load_source_media()

    def _load_source_media(self) -> None:
        self.player.stop()
        self.player.setSource(QUrl())
        self._media_available = False
        self._media_seekable = False
        self._media_size_mismatch = False
        self._preview_seek_guard.reset()
        # Discard duration learned from a previously located file. The new
        # backend duration will be applied by _duration_changed.
        if self.session.project is not None:
            try:
                self.timeline = PreviewTimeline.from_project(self.session.project)
                self._preview_error = None
            except PreviewTimelineError as exc:
                self.timeline = None
                self._preview_error = str(exc)
        self._refresh_source_timeline()
        source = self.session.source_path()
        if source is None or not source.is_file():
            self._media_available = False
            missing = "—" if source is None else str(source)
            self.media_notice.setText(
                f"No se encontró el video fuente: {missing}\n"
                "Usa Archivo → Ubicar video fuente para previsualizarlo."
            )
            self.media_notice.show()
            self._configure_timeline_controls()
            self._update_preview_notice()
            return
        self._media_available = True
        expected_size = (
            None
            if self.session.project is None
            else self.session.project.source.size_bytes
        )
        try:
            actual_size = source.stat().st_size
        except OSError as exc:
            self._media_available = False
            self.media_notice.setText(
                f"El video fuente dejó de estar disponible: {source}\n{exc}"
            )
            self.media_notice.show()
            self._configure_timeline_controls()
            return
        self._media_size_mismatch = (
            expected_size is not None and actual_size != expected_size
        )
        if self._media_size_mismatch:
            self.media_notice.setText(
                "Advertencia: el tamaño del video localizado no coincide con el "
                "registrado en el proyecto. Verifica que sea la fuente correcta."
            )
            self.media_notice.show()
        else:
            self.media_notice.hide()
        self.player.setSource(QUrl.fromLocalFile(str(source)))
        self._configure_timeline_controls()
        self.statusBar().showMessage(f"Video fuente: {source}", 5000)

    def _player_error(self, _error: QMediaPlayer.Error, error_string: str) -> None:
        if not error_string:
            error_string = self.player.errorString()
        self.media_notice.setText(
            "El backend multimedia no pudo reproducir el video. "
            f"Detalle: {error_string or 'error desconocido'}"
        )
        self.media_notice.show()
        self._media_available = False
        self._media_seekable = False
        self._configure_timeline_controls()

    # --- transport and virtual preview -------------------------------

    def change_preview_mode(self, mode: int) -> None:
        self.player.pause()
        self._update_preview_notice()
        self._active_preview_clip = None
        self._preview_seek_guard.reset()
        if mode == EDIT_MODE:
            self._seek_edit_s(0.0)
        self._configure_timeline_controls()

    def _configure_timeline_controls(self) -> None:
        edit_mode = self.preview_mode.currentIndex() == EDIT_MODE
        if edit_mode:
            duration_ms = (
                0 if self.timeline is None else round(self.timeline.duration_s * 1000)
            )
            position_ms = min(round(self._current_edit_s * 1000), duration_ms)
        else:
            duration_ms = max(0, self.player.duration())
            position_ms = min(max(0, self.player.position()), duration_ms)
        with QSignalBlocker(self.seek_slider):
            self.seek_slider.setRange(0, duration_ms)
            self.seek_slider.setValue(position_ms)
        self.current_time_label.setText(format_seconds(position_ms / 1000))
        self.total_time_label.setText(format_seconds(duration_ms / 1000))
        can_play = self._media_available and (
            not edit_mode
            or (
                self._media_seekable
                and self.timeline is not None
                and bool(self.timeline.clips)
            )
        )
        self.play_button.setEnabled(can_play)
        self.seek_slider.setEnabled(
            can_play
            if edit_mode
            else self._media_available and self._media_seekable
        )
        can_cut = can_play and edit_mode and self.timeline is not None
        self.previous_cut_button.setEnabled(can_cut)
        self.next_cut_button.setEnabled(can_cut)
        self._configure_timeline_edit_actions()

    def _update_preview_notice(self) -> None:
        if self.preview_mode.currentIndex() != EDIT_MODE:
            self.preview_notice.hide()
            return
        colors = theme.current_palette()
        if self._preview_error is not None:
            self.preview_notice.setText(
                "No se puede construir el preview de la edición propuesta: "
                f"{self._preview_error}"
            )
            self.preview_notice.setStyleSheet(theme.danger_notice_style(colors))
        elif (
            self._media_available
            and self.player.duration() > 0
            and not self._media_seekable
        ):
            self.preview_notice.setText(
                "El backend multimedia puede reproducir este archivo, pero no permite "
                "seek. El preview por cortes necesita un medio seekable."
            )
            self.preview_notice.setStyleSheet(theme.danger_notice_style(colors))
        else:
            self.preview_notice.setText(
                "Preview rápido: muestra los cortes seleccionados; todavía no "
                "incluye chroma, overlays, crossfades, offsets ni procesamiento "
                "final de audio."
            )
            self.preview_notice.setStyleSheet(theme.warning_notice_style(colors))
        self.preview_notice.show()

    def toggle_playback(self) -> None:
        if not self._media_available:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            return
        if self.preview_mode.currentIndex() == EDIT_MODE:
            if self.timeline is None or not self.timeline.clips:
                return
            if self._current_edit_s >= self.timeline.duration_s - 1e-9:
                self._seek_edit_s(0.0)
            elif self._active_preview_clip is None:
                self._seek_edit_s(self._current_edit_s)
        self.player.play()

    def _playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        self.play_button.setText(
            "Pausar"
            if state == QMediaPlayer.PlaybackState.PlayingState
            else "Reproducir"
        )

    def _duration_changed(self, duration_ms: int) -> None:
        project = self.session.project
        if duration_ms > 0 and project is not None:
            old_position_s = self._current_edit_s
            try:
                self.timeline = PreviewTimeline.from_project(
                    project, source_duration_s=duration_ms / 1000
                )
                self._preview_error = None
                if self._media_available and not self._media_size_mismatch:
                    self.media_notice.hide()
                if self.preview_mode.currentIndex() == EDIT_MODE:
                    self._seek_edit_s(
                        min(old_position_s, self.timeline.duration_s)
                    )
            except PreviewTimelineError as exc:
                # This differs from harmless derived tail padding, which the
                # timeline factory trims. It means an actual selected range is
                # outside the located media or the edit cannot be compiled.
                self.timeline = None
                self._active_preview_clip = None
                self._preview_error = str(exc)
                self.player.pause()
                self.media_notice.setText(
                    "El preview editado no coincide con el video localizado. "
                    f"Comprueba el archivo fuente. Detalle: {exc}"
                )
                self.media_notice.show()
        self._refresh_source_timeline()
        current_segment = self._current_segment()
        if current_segment is not None:
            self.edit_range_value.setText(
                self._edit_range_text(current_segment)
            )
        self._update_preview_notice()
        self._configure_timeline_controls()

    def _seekable_changed(self, seekable: bool) -> None:
        self._media_seekable = bool(seekable)
        self._update_preview_notice()
        self._configure_timeline_controls()

    def _position_changed(self, source_position_ms: int) -> None:
        if self.preview_mode.currentIndex() != EDIT_MODE:
            source_s = source_position_ms / 1000
            self.source_timeline_widget.set_playhead(source_s)
            self._sync_transcript_to_source_position(source_s)
            if not self._slider_dragging:
                with QSignalBlocker(self.seek_slider):
                    self.seek_slider.setValue(source_position_ms)
                self.current_time_label.setText(
                    format_seconds(source_s)
                )
            return

        clip = self._active_preview_clip
        if clip is None or self.timeline is None:
            return
        source_s = source_position_ms / 1000
        self.source_timeline_widget.set_playhead(source_s)
        # A seek can emit queued notifications from the previously active
        # clip. Ignore all out-of-range values until the backend confirms a
        # position inside the new clip (important for backward cut jumps).
        if not self._preview_seek_guard.accepts(
            source_s, clip.source_start_s, clip.source_end_s
        ):
            return
        self._sync_transcript_to_source_position(source_s)
        if source_s >= clip.source_end_s - 0.015:
            # Seeking while paused should not unexpectedly jump to another
            # take merely because the backend landed near this clip's end.
            if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self._current_edit_s = min(
                    clip.edit_end_s,
                    clip.edit_start_s + max(0.0, source_s - clip.source_start_s),
                )
                self._update_edit_position_display()
                return
            transition = next_preview_transition(self.timeline, clip)
            if transition is None:
                self._current_edit_s = self.timeline.duration_s
                self.player.pause()
                self._update_edit_position_display()
            else:
                next_clip, exact_boundary_s = transition
                # Use the clip index and exact boundary, never a rounded ms,
                # or a sub-ms cut could resolve back to the outgoing clip.
                self._seek_edit_s(exact_boundary_s, clip=next_clip)
            return
        edit_s = clip.edit_start_s + max(0.0, source_s - clip.source_start_s)
        self._current_edit_s = min(edit_s, clip.edit_end_s)
        self._update_edit_position_display()

    def _seek_edit_ms(self, edit_position_ms: int) -> None:
        self._seek_edit_s(edit_position_ms / 1000)

    def _seek_edit_s(
        self, edit_position_s: float, *, clip: PreviewClip | None = None
    ) -> None:
        if self.timeline is None:
            return
        edit_s = max(0.0, min(edit_position_s, self.timeline.duration_s))
        clip = self.timeline.clip_at(edit_s) if clip is None else clip
        if clip is None:
            source_s = None
        elif edit_s == self.timeline.duration_s:
            source_s = clip.source_end_s
        else:
            source_s = clip.source_start_s + (edit_s - clip.edit_start_s)
        self._active_preview_clip = clip
        self._current_edit_s = edit_s
        if source_s is not None:
            self._preview_seek_guard.arm()
            self.player.setPosition(round(source_s * 1000))
            self.source_timeline_widget.set_playhead(source_s)
        self._update_edit_position_display()

    def _update_edit_position_display(self) -> None:
        if not self._slider_dragging:
            with QSignalBlocker(self.seek_slider):
                self.seek_slider.setValue(round(self._current_edit_s * 1000))
        self.current_time_label.setText(
            format_seconds(self._current_edit_s)
        )

    def _slider_pressed(self) -> None:
        self._slider_dragging = True

    def _slider_released(self) -> None:
        self._slider_dragging = False
        self._seek_from_slider(self.seek_slider.value())

    def _slider_moved(self, position_ms: int) -> None:
        self.current_time_label.setText(format_seconds(position_ms / 1000))

    def _seek_from_slider(self, position_ms: int) -> None:
        if self.preview_mode.currentIndex() == EDIT_MODE:
            self._seek_edit_ms(position_ms)
        else:
            self.player.setPosition(position_ms)

    def go_to_next_cut(self) -> None:
        if self.timeline is None:
            return
        cut = self.timeline.next_cut(self._current_edit_s)
        destination = self.timeline.duration_s if cut is None else cut
        self._seek_edit_s(destination)

    def go_to_previous_cut(self) -> None:
        if self.timeline is None:
            return
        cut = self.timeline.previous_cut(self._current_edit_s)
        self._seek_edit_s(0.0 if cut is None else cut)
