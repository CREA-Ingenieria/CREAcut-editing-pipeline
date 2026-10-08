"""Qt widgets and asynchronous media data for CREAcut's source timeline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Iterable

import numpy as np
from PySide6.QtCore import QObject, QPoint, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPen, QPolygon, QWheelEvent
from PySide6.QtWidgets import QWidget

from ..source_timeline import SourceRegion, SourceTimelineProjection
from . import theme
from .session import format_seconds


class SourceTimelineWidget(QWidget):
    """Paint a complete source-time timeline and emit user editing intents.

    The widget is deliberately stateless with respect to project mutations.
    It paints supplied domain snapshots and asks the editor controller to seek,
    select, split or move a decision boundary through Qt signals.
    """

    seekRequested = Signal(float)
    regionSelected = Signal(str)
    boundaryMoveRequested = Signal(float, float)

    _RULER_H = 25
    _THUMB_Y = 29
    _THUMB_H = 64
    _WAVE_Y = 99
    _WAVE_H = 33
    _REGION_Y = 140
    _REGION_H = 38
    _BOTTOM = 191

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._projection: SourceTimelineProjection | None = None
        self._pixels_per_second = 28.0
        self._playhead_s = 0.0
        self._selected_region_id: str | None = None
        self._drag_boundary_s: float | None = None
        self._drag_preview_s: float | None = None
        self._thumbnails: tuple[tuple[float, QImage], ...] = ()
        self._waveform: tuple[float, ...] = ()
        self.setMouseTracking(True)
        self.setMinimumHeight(self._BOTTOM)
        self.setToolTip(
            "Clic: mover playhead · Arrastra un borde: modificar corte · "
            "Ctrl+rueda: zoom"
        )
        self._update_size()
        theme.bus.changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, _mode: str) -> None:
        self.update()

    @property
    def projection(self) -> SourceTimelineProjection | None:
        return self._projection

    @property
    def pixels_per_second(self) -> float:
        return self._pixels_per_second

    @property
    def selected_region_id(self) -> str | None:
        return self._selected_region_id

    def set_projection(self, projection: SourceTimelineProjection | None) -> None:
        self._projection = projection
        if projection is None:
            self._selected_region_id = None
            self._playhead_s = 0.0
        else:
            self._playhead_s = min(self._playhead_s, projection.duration_s)
            if projection.region_by_id(self._selected_region_id or "") is None:
                self._selected_region_id = None
        self._update_size()
        self.update()

    def set_playhead(self, source_time_s: float) -> None:
        if self._projection is None:
            return
        self._playhead_s = min(max(0.0, float(source_time_s)), self._projection.duration_s)
        self.update()

    def set_selected_region(self, region_id: str | None) -> None:
        self._selected_region_id = region_id
        self.update()

    def set_media_data(
        self,
        thumbnails: Iterable[tuple[float, QImage]] = (),
        waveform: Iterable[float] = (),
    ) -> None:
        self._thumbnails = tuple(thumbnails)
        self._waveform = tuple(float(value) for value in waveform)
        self.update()

    def zoom_in(self) -> None:
        self._set_pixels_per_second(self._pixels_per_second * 1.35)

    def zoom_out(self) -> None:
        self._set_pixels_per_second(self._pixels_per_second / 1.35)

    def _set_pixels_per_second(self, value: float) -> None:
        self._pixels_per_second = min(240.0, max(3.0, value))
        self._update_size()
        self.update()

    def _update_size(self) -> None:
        duration = 0.0 if self._projection is None else self._projection.duration_s
        self.setMinimumWidth(max(700, round(duration * self._pixels_per_second) + 2))
        self.resize(self.minimumWidth(), self._BOTTOM)

    def _time_at_x(self, x: float) -> float:
        if self._projection is None:
            return 0.0
        return min(max(0.0, x / self._pixels_per_second), self._projection.duration_s)

    def _x_at_time(self, time_s: float) -> float:
        return time_s * self._pixels_per_second

    def _nearest_boundary(self, x: float) -> float | None:
        if self._projection is None:
            return None
        threshold = 6.0
        candidates = [region.end_s for region in self._projection.regions[:-1]]
        if not candidates:
            return None
        nearest = min(candidates, key=lambda value: abs(self._x_at_time(value) - x))
        return nearest if abs(self._x_at_time(nearest) - x) <= threshold else None

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        colors = theme.timeline_colors(theme.current_palette())
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), QColor(colors["bg"]))
            projection = self._projection
            if projection is None:
                painter.setPen(QColor(colors["empty_text"]))
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Línea de tiempo fuente no disponible")
                return
            self._paint_ruler(painter, projection, colors)
            self._paint_thumbnails(painter, projection, colors)
            self._paint_waveform(painter, projection, colors)
            self._paint_regions(painter, projection, colors)
            self._paint_playhead(painter, projection, colors)
        finally:
            painter.end()

    def _paint_ruler(
        self, painter: QPainter, projection: SourceTimelineProjection, colors: dict[str, str]
    ) -> None:
        painter.fillRect(0, 0, self.width(), self._RULER_H, QColor(colors["ruler_bg"]))
        painter.setPen(QPen(QColor(colors["ruler_line"]), 1))
        step = self._tick_step()
        time_s = 0.0
        while time_s <= projection.duration_s + 1e-6:
            x = round(self._x_at_time(time_s))
            painter.drawLine(x, self._RULER_H - 7, x, self._RULER_H)
            painter.drawText(x + 3, 14, format_seconds(time_s))
            time_s += step

    def _tick_step(self) -> float:
        desired = 95.0 / self._pixels_per_second
        for candidate in (0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0):
            if candidate >= desired:
                return candidate
        return 900.0

    def _paint_thumbnails(
        self, painter: QPainter, projection: SourceTimelineProjection, colors: dict[str, str]
    ) -> None:
        painter.fillRect(0, self._THUMB_Y, self.width(), self._THUMB_H, QColor(colors["thumb_bg"]))
        if not self._thumbnails:
            painter.setPen(QColor(colors["thumb_placeholder"]))
            painter.drawText(8, self._THUMB_Y + 22, "Generando miniaturas…")
            return
        target_width = max(45, int(self._THUMB_H * 16 / 9))
        for time_s, image in self._thumbnails:
            if time_s < 0.0 or time_s > projection.duration_s:
                continue
            scaled = image.scaled(
                target_width, self._THUMB_H,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = int(self._x_at_time(time_s) - scaled.width() / 2)
            painter.drawImage(x, self._THUMB_Y, scaled)

    def _paint_waveform(
        self, painter: QPainter, projection: SourceTimelineProjection, colors: dict[str, str]
    ) -> None:
        painter.fillRect(0, self._WAVE_Y, self.width(), self._WAVE_H, QColor(colors["wave_bg"]))
        painter.setPen(QColor(colors["wave_baseline"]))
        mid = self._WAVE_Y + self._WAVE_H / 2
        painter.drawLine(0, round(mid), self.width(), round(mid))
        if not self._waveform:
            painter.setPen(QColor(colors["wave_placeholder"]))
            painter.drawText(8, self._WAVE_Y + 21, "Forma de onda no disponible")
            return
        painter.setPen(QPen(QColor(colors["wave_fill"]), 1))
        total = len(self._waveform)
        for x in range(self.width()):
            time_s = self._time_at_x(x)
            index = min(total - 1, max(0, int(time_s / projection.duration_s * total)))
            amplitude = max(0.0, min(1.0, self._waveform[index]))
            radius = amplitude * (self._WAVE_H / 2 - 3)
            painter.drawLine(x, round(mid - radius), x, round(mid + radius))

    def _paint_regions(
        self, painter: QPainter, projection: SourceTimelineProjection, colors: dict[str, str]
    ) -> None:
        border = QColor(colors["region_border"])
        painter.setPen(QPen(border, 1))
        for region in projection.regions:
            x = round(self._x_at_time(region.start_s))
            width = max(1, round(region.duration_s * self._pixels_per_second))
            if region.keep:
                fill_key = "region_keep_auto" if region.origin == "automatic" else "region_keep_manual"
                text_color = colors["region_keep_text"]
            else:
                fill_key = "region_discard_auto" if region.origin == "automatic" else "region_discard_manual"
                text_color = colors["region_discard_text"]
            color = QColor(colors[fill_key])
            painter.fillRect(x, self._REGION_Y, width, self._REGION_H, color)
            if not region.keep:
                painter.setPen(QPen(QColor(255, 255, 255, 48), 1))
                for line_x in range(x - self._REGION_H, x + width, 8):
                    painter.drawLine(line_x, self._REGION_Y + self._REGION_H, line_x + self._REGION_H, self._REGION_Y)
            if region.id == self._selected_region_id:
                painter.setPen(QPen(QColor(colors["selection_outline"]), 3))
                painter.drawRect(x + 1, self._REGION_Y + 1, max(0, width - 2), self._REGION_H - 2)
            painter.setPen(QPen(border, 1))
            painter.drawLine(x, self._REGION_Y - 5, x, self._REGION_Y + self._REGION_H + 5)
            if width > 68:
                painter.setPen(QColor(text_color))
                text = "CONSERVAR" if region.keep else "DESCARTAR"
                painter.drawText(x + 5, self._REGION_Y + 24, text)
        painter.setPen(QColor(colors["footer_text"]))
        painter.drawText(5, self._REGION_Y + self._REGION_H + 12, "Decisiones de edición sobre video fuente")

    def _paint_playhead(
        self, painter: QPainter, projection: SourceTimelineProjection, colors: dict[str, str]
    ) -> None:
        value = self._drag_preview_s if self._drag_preview_s is not None else self._playhead_s
        x = round(self._x_at_time(min(max(value, 0.0), projection.duration_s)))
        playhead = QColor(colors["playhead"])
        painter.setPen(QPen(playhead, 2))
        painter.drawLine(x, 0, x, self._BOTTOM)
        painter.setBrush(playhead)
        painter.drawPolygon(QPolygon([QPoint(x - 5, 0), QPoint(x + 5, 0), QPoint(x, 8)]))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if event.button() != Qt.MouseButton.LeftButton or self._projection is None:
            return super().mousePressEvent(event)
        boundary = self._nearest_boundary(event.position().x())
        if boundary is not None and self._REGION_Y - 10 <= event.position().y() <= self._REGION_Y + self._REGION_H + 10:
            self._drag_boundary_s = boundary
            self._drag_preview_s = boundary
            event.accept()
            return
        time_s = self._time_at_x(event.position().x())
        region = self._projection.region_at(time_s)
        self._selected_region_id = region.id
        self.regionSelected.emit(region.id)
        self.seekRequested.emit(time_s)
        self.update()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if self._drag_boundary_s is not None:
            self._drag_preview_s = self._time_at_x(event.position().x())
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton and self._drag_boundary_s is not None:
            old = self._drag_boundary_s
            new = self._time_at_x(event.position().x())
            self._drag_boundary_s = None
            self._drag_preview_s = None
            if abs(old - new) > 0.001:
                self.boundaryMoveRequested.emit(old, new)
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt API
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._set_pixels_per_second(
                self._pixels_per_second * (1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
            )
            event.accept()
            return
        super().wheelEvent(event)


class _MediaSignals(QObject):
    completed = Signal(object, object)
    failed = Signal(str)


class _MediaWorker(QRunnable):
    def __init__(self, source: Path, duration_s: float, samples: int, cache_path: Path | None) -> None:
        super().__init__()
        self.source = source
        self.duration_s = duration_s
        self.samples = samples
        self.cache_path = cache_path
        self.signals = _MediaSignals()

    @Slot()
    def run(self) -> None:
        try:
            thumbnails = _make_thumbnails(self.source, self.duration_s, self.samples)
            waveform = _load_or_make_waveform(self.source, self.duration_s, self.cache_path)
        except Exception as exc:  # Never let media diagnostics crash the editor.
            try:
                self.signals.failed.emit(str(exc))
            except RuntimeError:
                # The editor can close while this optional worker is running.
                pass
            return
        try:
            self.signals.completed.emit(thumbnails, waveform)
        except RuntimeError:
            # The owner QObject was destroyed during application shutdown.
            pass


class TimelineMediaCache(QObject):
    """Generate filmstrip/waveform data off the GUI thread with a safe cache."""

    ready = Signal(object, object)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        self._active_key: str | None = None
        self._memory: dict[str, tuple[tuple[tuple[float, QImage], ...], tuple[float, ...]]] = {}
        self._workers: set[_MediaWorker] = set()
        self._pending_keys: set[str] = set()

    def request(
        self,
        source: str | Path,
        duration_s: float,
        *,
        cache_dir: str | Path | None = None,
        samples: int = 18,
    ) -> None:
        path = Path(source)
        key = _media_key(path, duration_s, samples)
        self._active_key = key
        if key in self._memory:
            thumbnails, waveform = self._memory[key]
            self.ready.emit(thumbnails, waveform)
            return
        if key in self._pending_keys:
            return
        cache_path = None
        if cache_dir is not None:
            cache_path = Path(cache_dir) / f"{key}.waveform.json"
        worker = _MediaWorker(path, duration_s, samples, cache_path)
        self._workers.add(worker)
        self._pending_keys.add(key)
        worker.signals.completed.connect(
            lambda thumbs, wave, current=key, item=worker: self._completed(current, thumbs, wave, item)
        )
        worker.signals.failed.connect(
            lambda message, current=key, item=worker: self._failed(current, message, item)
        )
        self._pool.start(worker)

    def _completed(self, key: str, thumbnails, waveform, worker: _MediaWorker) -> None:
        self._workers.discard(worker)
        self._pending_keys.discard(key)
        normalized = (tuple(thumbnails), tuple(float(value) for value in waveform))
        self._memory[key] = normalized
        if key == self._active_key:
            self.ready.emit(*normalized)

    def _failed(self, key: str, message: str, worker: _MediaWorker) -> None:
        self._workers.discard(worker)
        self._pending_keys.discard(key)
        if key == self._active_key:
            self.failed.emit(message)


def _media_key(path: Path, duration_s: float, samples: int) -> str:
    stat = path.stat()
    raw = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{duration_s:.6f}|{samples}".encode()
    return hashlib.sha256(raw).hexdigest()[:24]


def _make_thumbnails(source: Path, duration_s: float, samples: int) -> tuple[tuple[float, QImage], ...]:
    import cv2

    capture = cv2.VideoCapture(str(source))
    try:
        result: list[tuple[float, QImage]] = []
        for index in range(max(1, samples)):
            time_s = min(duration_s, (index + 0.5) / max(1, samples) * duration_s)
            capture.set(cv2.CAP_PROP_POS_MSEC, time_s * 1000)
            ok, frame = capture.read()
            if not ok:
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            height, width, channels = rgb.shape
            image = QImage(rgb.data, width, height, channels * width, QImage.Format.Format_RGB888).copy()
            result.append((time_s, image))
        return tuple(result)
    finally:
        capture.release()


def _load_or_make_waveform(
    source: Path, duration_s: float, cache_path: Path | None
) -> tuple[float, ...]:
    if cache_path is not None:
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            values = payload.get("peaks")
            if isinstance(values, list) and values:
                return tuple(float(value) for value in values)
        except (OSError, ValueError, TypeError):
            pass
    peaks = _make_waveform(source)
    if cache_path is not None and peaks:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps({"duration_s": duration_s, "peaks": peaks}), encoding="utf-8")
        except OSError:
            pass
    return peaks


def _make_waveform(source: Path, buckets: int = 1200) -> tuple[float, ...]:
    try:
        import imageio_ffmpeg

        executable = imageio_ffmpeg.get_ffmpeg_exe()
        process = subprocess.run(
            [
                executable, "-v", "error", "-i", str(source), "-map", "0:a:0",
                "-ac", "1", "-ar", "8000", "-f", "s16le", "-acodec", "pcm_s16le", "-",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=90,
        )
        data = np.frombuffer(process.stdout, dtype=np.int16)
        if not len(data):
            return ()
        values = np.abs(data.astype(np.float32)) / 32768.0
        groups = np.array_split(values, min(buckets, len(values)))
        return tuple(float(group.max()) if len(group) else 0.0 for group in groups)
    except (ImportError, OSError, subprocess.SubprocessError, ValueError):
        return ()
