"""Optional offscreen smoke tests for the PySide6 editor window."""

from __future__ import annotations

from dataclasses import replace
import os

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from creacut.decisions import AlignmentCandidate
from creacut.project_io import save_project
from creacut.ui.qt import EDIT_MODE, EditorWindow
from tests.project_test_helpers import make_edit_project


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()


def test_editor_window_constructs_without_a_document(qt_app):
    window = EditorWindow()

    assert window.windowTitle() == "CREAcut Editor"
    assert window.preview_mode.count() == 2
    assert not window.play_button.isEnabled()
    assert not window.seek_slider.isEnabled()

    window.close()
    window.deleteLater()
    qt_app.processEvents()


def test_text_tabs_show_whisper_transcript_full_script_and_follow_audio(
    qt_app,
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    project_path = save_project(project, tmp_dir / "text-tabs.creacut.json")
    window = EditorWindow()

    assert window.open_project(project_path)
    assert window.text_tabs.count() == 2
    assert window.text_tabs.tabText(0) == "Transcripción"
    assert window.text_tabs.tabText(1) == "Guion"
    assert window.transcript_list.count() == len(project.transcript.segments)
    assert window.transcript_list.item(2).text().startswith("003  00:05.000")
    assert window.script_view.toPlainText() == sample_script.read_text(encoding="utf-8")

    # Position 5.3s belongs to the third Whisper segment. The list tracks it
    # and makes its corresponding editable script sentence current.
    window._position_changed(5300)
    assert window.transcript_list.currentRow() == 2
    assert window._current_segment() is window.session.project.segments[0]

    window.close()
    window.deleteLater()
    qt_app.processEvents()


def test_text_tabs_keep_project_open_when_script_was_moved(
    qt_app,
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    project_path = save_project(project, tmp_dir / "moved-script.creacut.json")
    sample_script.unlink()
    window = EditorWindow()

    assert window.open_project(project_path)
    assert window.transcript_list.count() == len(project.transcript.segments)
    assert window.script_hint.text() == "Guion original no disponible"
    assert "No se pudo leer el archivo de guion" in window.script_view.toPlainText()

    window.close()
    window.deleteLater()
    qt_app.processEvents()


def test_constrained_preview_keeps_video_above_transport_controls(
    qt_app,
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    project_path = save_project(project, tmp_dir / "constrained-preview.creacut.json")
    window = EditorWindow()
    window.resize(1100, 680)
    window.show()

    assert window.open_project(project_path)
    window.preview_mode.setCurrentIndex(EDIT_MODE)
    qt_app.processEvents()

    video = window.video_widget.geometry()
    central = window.centralWidget().contentsRect()
    assert video.width() > 0
    assert video.height() > 0
    assert video.right() <= central.right()
    assert video.bottom() < window.previous_cut_button.geometry().top()

    window.close()
    window.deleteLater()
    qt_app.processEvents()


def test_source_timeline_shows_full_media_and_commits_region_decisions(
    qt_app,
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    project.source = replace(project.source, duration_s=20.0)
    project_path = save_project(project, tmp_dir / "source-timeline.creacut.json")
    window = EditorWindow()

    assert window.open_project(project_path)
    assert window.source_timeline is not None
    assert window.source_timeline.regions[0].start_s == pytest.approx(0.0)
    assert window.source_timeline.regions[-1].end_s == pytest.approx(20.0)

    discarded = window.source_timeline.region_at(1.0)
    assert not discarded.keep
    window._timeline_region_selected(discarded.id)
    assert window.timeline_keep_button.isEnabled()
    window.timeline_keep_button.click()
    qt_app.processEvents()

    assert window.source_timeline.region_at(1.0).keep
    assert window.session.dirty
    window.session.save()
    window.close()
    window.deleteLater()
    qt_app.processEvents()


def test_missing_source_keeps_project_inspectable_and_transport_disabled(
    qt_app,
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, _early, _recommended, video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    project_path = save_project(project, tmp_dir / "missing.creacut.json")
    video.unlink()
    window = EditorWindow()

    assert window.open_project(project_path)
    assert window.transcript_list.count() == len(project.transcript.segments)
    assert window.media_notice.isVisibleTo(window)
    assert not window.play_button.isEnabled()
    assert not window.seek_slider.isEnabled()

    window.preview_mode.setCurrentIndex(EDIT_MODE)
    assert window.preview_notice.isVisibleTo(window)
    assert not window.play_button.isEnabled()
    assert not window.previous_cut_button.isEnabled()
    assert not window.next_cut_button.isEnabled()

    # Project edits remain available even when only the media preview is
    # offline. Restore afterwards so closing cannot open a save prompt.
    segment = window.session.project.segments[0]
    alternative_id = next(
        candidate.id
        for candidate in segment.candidates
        if candidate.id != segment.selected_candidate_id
    )
    alternative_row = next(
        row
        for row in range(window.candidate_table.rowCount())
        if window.candidate_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        == alternative_id
    )
    window.candidate_table.selectRow(alternative_row)
    window.use_candidate_button.click()
    qt_app.processEvents()
    assert window.session.dirty
    assert not window.play_button.isEnabled()
    window.restore_recommended_button.click()
    qt_app.processEvents()
    assert not window.session.dirty

    window.close()
    window.deleteLater()
    qt_app.processEvents()


def test_media_duration_clamps_only_derived_preview_tail(
    qt_app,
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, _early, recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    project_path = save_project(project, tmp_dir / "duration.creacut.json")
    window = EditorWindow()

    assert window.open_project(project_path)
    media_duration_s = recommended.end + 0.25
    window._duration_changed(round(media_duration_s * 1000))

    assert window.timeline is not None
    assert window._preview_error is None
    assert window.timeline.clips[-1].source_end_s == pytest.approx(
        media_duration_s
    )

    window.close()
    window.deleteLater()
    qt_app.processEvents()


def test_inspector_switches_take_and_restores_automatic_recommendation(
    qt_app,
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, early, recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    project_path = save_project(project, tmp_dir / "takes.creacut.json")
    window = EditorWindow()

    assert window.open_project(project_path)
    original_segment = window.session.project.segments[0]
    assert window.candidate_table.rowCount() == 2
    assert window.candidate_table.horizontalHeaderItem(0).text() == "Toma"
    assert window.candidate_table.item(0, 0).text() == "Toma A"
    assert "No disponible" not in window.edit_range_value.text()

    early_candidate = next(
        candidate
        for candidate in original_segment.candidates
        if candidate.source_start_s == pytest.approx(early.start)
    )
    early_row = next(
        row
        for row in range(window.candidate_table.rowCount())
        if window.candidate_table.item(row, 0).data(
            Qt.ItemDataRole.UserRole
        )
        == early_candidate.id
    )
    # SelectRows updates the action state just as a real row click does.
    window.candidate_table.selectRow(early_row)
    qt_app.processEvents()
    assert window.use_candidate_button.isEnabled()

    window.use_candidate_button.click()
    qt_app.processEvents()

    edited_segment = window.session.project.segments[0]
    assert edited_segment.selected_candidate_id == early_candidate.id
    assert edited_segment.source_start_s == pytest.approx(early.start)
    assert window._current_segment() is edited_segment
    assert window.isWindowModified()
    assert window.restore_recommended_button.isEnabled()
    assert not window.use_candidate_button.isEnabled()
    assert window.timeline is not None
    assert window.timeline.edit_time_at(early.start) is not None

    window.restore_recommended_button.click()
    qt_app.processEvents()

    restored_segment = window.session.project.segments[0]
    assert restored_segment.selected_candidate_id == (
        restored_segment.automatic_selection.recommended_candidate_id
    )
    assert restored_segment.source_start_s == pytest.approx(recommended.start)
    assert not window.isWindowModified()
    assert not window.restore_recommended_button.isEnabled()

    window.close()
    window.deleteLater()
    qt_app.processEvents()


def test_invalid_take_from_button_preserves_document_and_preview(
    qt_app,
    tmp_dir,
    sample_script,
    sample_segments,
    monkeypatch,
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    segment = project.segments[1]
    regressing = AlignmentCandidate(
        id="p0:s1:regressing-ui",
        source_start_s=4.0,
        source_end_s=4.5,
        score=0.75,
        transcript_text="Alternativa fuera de orden.",
        segment_start_idx=1,
        segment_end_idx=1,
    )
    chronological = AlignmentCandidate(
        id="p0:s1:chronological-ui",
        source_start_s=7.0,
        source_end_s=8.0,
        score=0.90,
        transcript_text="Toma cronológica.",
        segment_start_idx=3,
        segment_end_idx=3,
    )
    segment.candidates = (regressing, chronological)
    segment.automatic_selection = replace(
        segment.automatic_selection,
        recommended_candidate_id=chronological.id,
    )
    segment.select_candidate(chronological.id)
    project_path = save_project(project, tmp_dir / "invalid-ui.creacut.json")
    window = EditorWindow()
    assert window.open_project(project_path)
    window._select_edit_segment(segment.id)
    qt_app.processEvents()

    regressing_row = next(
        row
        for row in range(window.candidate_table.rowCount())
        if window.candidate_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        == regressing.id
    )
    window.candidate_table.selectRow(regressing_row)
    before_payload = window.session.project.to_dict()
    before_timeline = window.timeline
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append((args, kwargs))
        or QMessageBox.StandardButton.Ok,
    )

    window.use_candidate_button.click()
    qt_app.processEvents()

    assert warnings
    assert window.session.project.to_dict() == before_payload
    assert window.timeline is before_timeline
    assert not window.session.dirty
    assert not window.isWindowModified()

    window.close()
    window.deleteLater()
    qt_app.processEvents()


def test_restore_without_automatic_recommendation_clears_manual_take(
    qt_app,
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    segment = project.segments[1]
    manual = AlignmentCandidate(
        id="p0:s1:manual-without-recommendation",
        source_start_s=7.0,
        source_end_s=8.0,
        score=0.80,
        transcript_text="Toma elegida manualmente.",
        segment_start_idx=3,
        segment_end_idx=3,
    )
    segment.candidates = (manual,)
    segment.select_candidate(manual.id)
    project_path = save_project(project, tmp_dir / "no-recommendation.creacut.json")
    window = EditorWindow()
    assert window.open_project(project_path)
    window._select_edit_segment(segment.id)
    qt_app.processEvents()

    assert window.restore_recommended_button.isEnabled()
    window.restore_recommended_button.click()
    qt_app.processEvents()

    restored = window.session.project.segments[1]
    assert restored.automatic_selection.recommended_candidate_id is None
    assert restored.selected_candidate_id is None
    assert restored.source_start_s is None
    assert restored.source_end_s is None

    # Reapply the saved manual state so closing remains non-interactive.
    window.candidate_table.selectRow(0)
    window.use_candidate_button.click()
    qt_app.processEvents()
    assert not window.session.dirty

    window.close()
    window.deleteLater()
    qt_app.processEvents()
