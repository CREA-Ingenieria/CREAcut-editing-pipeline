"""Smoke tests for the desktop video-to-editor workflow."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from creacut.ui.app import StartWindow
from creacut.ui.tasks import AnalysisWorker, RenderWorker


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()


def test_start_window_requires_video_script_and_output_folder(qt_app, tmp_dir):
    video = tmp_dir / "lesson.mp4"
    script = tmp_dir / "lesson.md"
    video.write_bytes(b"not inspected by the form")
    script.write_text("# Guion", encoding="utf-8")
    output = tmp_dir / "result"
    output.mkdir()

    window = StartWindow()
    assert not window.analyze_button.isEnabled()

    window._field(window.video_path).setText(str(video))
    window._field(window.script_path).setText(str(script))
    window._field(window.output_directory).setText(str(output))
    qt_app.processEvents()

    assert window.analyze_button.isEnabled()
    assert window.suggested_project_path() == output / "lesson.creacut.json"
    assert "lesson.creacut.json" in window.project_hint.text()

    window.close()
    window.deleteLater()
    qt_app.processEvents()


def test_analysis_worker_replaces_only_after_the_pipeline_writes_project(
    tmp_dir, monkeypatch
):
    import creacut.ui.tasks as tasks

    video = tmp_dir / "lesson.mp4"
    script = tmp_dir / "lesson.md"
    target = tmp_dir / "lesson.creacut.json"
    video.write_bytes(b"video")
    script.write_text("# Guion", encoding="utf-8")
    target.write_text("old project", encoding="utf-8")
    observed: list[tuple[Path, Path, Path]] = []

    def fake_generate(video_path, *, script, config, verbose, project_output):
        observed.append((Path(video_path), Path(script), Path(project_output)))
        # This mimics project_io.save_project's final replacement point.
        Path(project_output).write_text("new project", encoding="utf-8")
        print("=== Stage 1: Transcription ===")
        return object()

    monkeypatch.setattr(tasks, "generate_edit_project", fake_generate)
    worker = AnalysisWorker(video, script, target, allow_replace=True)
    completed: list[str] = []
    failures: list[str] = []
    progress: list[str] = []
    worker.completed.connect(completed.append)
    worker.failed.connect(failures.append)
    worker.progress.connect(progress.append)

    worker.run()

    assert not failures
    assert completed == [str(target)]
    assert observed == [(video, script, target)]
    assert target.read_text(encoding="utf-8") == "new project"
    assert any("Stage 1" in line for line in progress)


def test_render_worker_uses_saved_project_without_analysis(tmp_dir, monkeypatch):
    import creacut.ui.tasks as tasks

    project = tmp_dir / "lesson.creacut.json"
    output = tmp_dir / "lesson-final.mp4"
    project.write_text("{}", encoding="utf-8")
    calls: list[tuple[Path, Path, bool]] = []

    def fake_render(project_path, *, output, verbose):
        calls.append((Path(project_path), Path(output), verbose))
        Path(output).write_bytes(b"rendered")
        print("=== Stage 7: Cut ===")
        return Path(output)

    monkeypatch.setattr(tasks, "render_project", fake_render)
    worker = RenderWorker(project, output)
    completed: list[str] = []
    failures: list[str] = []
    worker.completed.connect(completed.append)
    worker.failed.connect(failures.append)

    worker.run()

    assert not failures
    assert completed == [str(output)]
    assert calls == [(project, output, True)]
    assert output.read_bytes() == b"rendered"
