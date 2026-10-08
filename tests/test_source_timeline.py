"""Contracts for the full-source decision layer."""

from __future__ import annotations

from dataclasses import replace

import pytest

from creacut.preview import PreviewTimeline
from creacut.project import ProjectValidationError
from creacut.project_io import load_project, save_project
from creacut.source_timeline import SourceTimelineState, apply_overrides
from creacut.ui.session import EditorSession
from tests.project_test_helpers import make_edit_project


def _with_duration(project, duration_s: float):
    project.source = replace(project.source, duration_s=duration_s)
    project.validate()
    return project


def test_source_timeline_covers_full_video_and_preserves_legacy_keeps(
    tmp_dir, sample_script, sample_segments
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    _with_duration(project, 20.0)

    projection = project.source_timeline()

    assert projection.regions[0].start_s == pytest.approx(0.0)
    assert projection.regions[-1].end_s == pytest.approx(20.0)
    assert any(not region.keep for region in projection.regions)
    assert list(projection.keep_ranges) == project.compile_clean_ranges()


def test_timeline_layer_distinguishes_original_ia_from_changed_candidate(
    tmp_dir, sample_script, sample_segments
):
    project, _plan, early, recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    _with_duration(project, 20.0)
    project.segments[0].select_candidate(project.segments[0].candidates[0].id)

    projection = project.source_timeline()

    early_region = projection.region_at(early.start + 0.2)
    recommended_region = projection.region_at(recommended.start + 0.2)
    assert early_region.keep
    assert early_region.origin == "segment"
    assert recommended_region.automatic_keep


def test_manual_overrides_change_preview_and_restore_without_mutating_candidates(
    tmp_dir, sample_script, sample_segments
):
    project, _plan, _early, recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    _with_duration(project, 20.0)
    original_candidate = project.segments[0].selected_candidate_id
    state = SourceTimelineState.empty(20.0)
    state.set_override(1.0, 2.0, True)
    project.set_source_timeline_state(state)

    timeline = PreviewTimeline.from_project(project)
    assert timeline.edit_time_at(1.5) is not None
    assert timeline.edit_time_at(recommended.start) is not None
    assert project.segments[0].selected_candidate_id == original_candidate

    state.restore(1.0, 2.0)
    project.set_source_timeline_state(state)
    restored = project.source_timeline()
    assert not restored.region_at(1.5).keep
    assert project.segments[0].selected_candidate_id == original_candidate


def test_manual_timeline_round_trip_and_session_undo_redo(
    tmp_dir, sample_script, sample_segments
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    _with_duration(project, 20.0)
    project_path = save_project(project, tmp_dir / "timeline.creacut.json")
    session = EditorSession()
    session.open(project_path)

    session.mark_timeline_range(0.5, 1.5, keep=True, source_duration_s=20.0)
    assert session.source_timeline(20.0).region_at(1.0).keep
    assert session.dirty
    assert session.can_undo_timeline

    assert session.undo_timeline()
    assert not session.source_timeline(20.0).region_at(1.0).keep
    assert session.redo_timeline()
    assert session.source_timeline(20.0).region_at(1.0).keep

    saved = session.save()
    loaded = load_project(saved)
    assert loaded.source_timeline().region_at(1.0).keep

    session.restore_timeline_range(0.5, 1.5, source_duration_s=20.0)
    assert "creacut.source_timeline" not in session.project.extensions


def test_session_can_split_and_drag_an_automatic_cut(
    tmp_dir, sample_script, sample_segments
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    _with_duration(project, 20.0)
    project_path = save_project(project, tmp_dir / "drag.creacut.json")
    session = EditorSession()
    session.open(project_path)
    initial = session.source_timeline(20.0)
    automatic_cut = initial.cut_points_s[0]

    session.move_timeline_boundary(
        automatic_cut, automatic_cut - 0.2, source_duration_s=20.0
    )
    moved = session.source_timeline(20.0)
    assert moved.region_at(automatic_cut - 0.1).keep

    session.split_timeline(2.0, source_duration_s=20.0)
    split = session.source_timeline(20.0)
    assert any(region.end_s == pytest.approx(2.0) for region in split.regions)


def test_overrides_and_manual_boundaries_are_validated_and_normalized():
    state = SourceTimelineState.empty(10.0)
    state.set_override(1.0, 9.0, True)
    state.set_override(3.0, 5.0, False)
    effective = apply_overrides([(6.0, 7.0)], state)

    assert effective == ((1.0, 3.0), (5.0, 9.0))
    state.restore(3.0, 5.0)
    assert apply_overrides([(6.0, 7.0)], state) == ((1.0, 3.0), (5.0, 9.0))


def test_full_source_timeline_requires_real_media_duration(
    tmp_dir, sample_script, sample_segments
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )

    with pytest.raises(ProjectValidationError, match="required to build a full source timeline"):
        project.source_timeline()
