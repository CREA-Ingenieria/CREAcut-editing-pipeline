"""Pure tests for the optional editor document layer."""

from __future__ import annotations

from dataclasses import replace

import pytest

from creacut.decisions import AlignmentCandidate
from creacut.project_io import load_project, save_project
from creacut.preview import PreviewTimeline
from creacut.ui.playback import PreviewSeekGuard, next_preview_transition
from creacut.ui.session import (
    EditorSession,
    EditorSessionError,
    format_seconds,
    segment_label,
)
from tests.project_test_helpers import make_edit_project


def test_time_and_segment_labels_are_stable(
    tmp_dir, sample_script, sample_segments
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )

    assert format_seconds(None) == "--:--.---"
    assert format_seconds(5.004) == "00:05.004"
    assert format_seconds(3_661.25) == "01:01:01.250"
    assert "00:05.000–00:06.300" in segment_label(project.segments[0], 1)
    assert "94%" in segment_label(project.segments[0], 1)
    assert "sin toma" in segment_label(project.segments[1], 2)


def test_session_opens_relative_media_from_project_directory(
    tmp_dir, sample_script, sample_segments
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    project_dir = tmp_dir / "editor"
    media_dir = project_dir / "media"
    media_dir.mkdir(parents=True)
    relocated = media_dir / "clase.mp4"
    relocated.write_bytes(b"video")
    project.source = replace(project.source, path="media/clase.mp4")
    project_path = save_project(project, project_dir / "clase.creacut.json")

    session = EditorSession()
    restored = session.open(project_path)

    assert session.is_open
    assert restored.project_id == project.project_id
    assert session.source_path() == relocated.resolve()
    assert not session.dirty


def test_media_override_is_ephemeral_and_has_priority(
    tmp_dir, sample_script, sample_segments
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    project_path = save_project(project, tmp_dir / "clase.creacut.json")
    alternate = tmp_dir / "alternate.mp4"
    alternate.write_bytes(b"alternate")
    session = EditorSession()
    session.open(project_path)

    stored_path = session.project.source.path
    session.set_media_override(alternate)

    assert session.source_path() == alternate.resolve()
    assert session.project.source.path == stored_path
    assert not session.refresh_dirty()


def test_session_tracks_and_saves_model_changes(
    tmp_dir, sample_script, sample_segments
):
    project, _plan, early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    project_path = save_project(project, tmp_dir / "clase.creacut.json")
    session = EditorSession()
    session.open(project_path)

    session.project.segments[0].select_candidate(
        next(
            candidate.id
            for candidate in session.project.segments[0].candidates
            if candidate.source_start_s == early.start
        )
    )

    assert session.refresh_dirty()
    saved = session.save()
    assert saved == project_path.resolve()
    assert not session.dirty
    assert load_project(saved).segments[0].source_start_s == early.start


def test_session_refuses_save_without_project():
    with pytest.raises(EditorSessionError, match="No hay un proyecto"):
        EditorSession().save()


def test_session_selects_take_by_stable_id_and_restores_recommendation(
    tmp_dir, sample_script, sample_segments
):
    project, _plan, early, recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    project_path = save_project(project, tmp_dir / "clase.creacut.json")
    session = EditorSession()
    session.open(project_path)
    live_project = session.project
    live_segment = session.project.segments[0]
    segment_id = session.project.segments[0].id
    automatic_id = session.project.segments[0].automatic_selection.recommended_candidate_id
    alternative_id = next(
        candidate.id
        for candidate in session.project.segments[0].candidates
        if candidate.source_start_s == early.start
    )

    selected = session.select_candidate(segment_id, alternative_id)

    assert selected.id == segment_id
    assert session.project is live_project
    assert selected is live_segment
    assert selected.selected_candidate_id == alternative_id
    assert selected.source_start_s == early.start
    assert selected.source_end_s == early.end
    assert selected.automatic_selection.recommended_candidate_id == automatic_id
    assert session.dirty

    restored = session.restore_recommended(segment_id)

    assert restored.selected_candidate_id == automatic_id
    assert session.project is live_project
    assert restored is live_segment
    assert restored.source_start_s == recommended.start
    assert restored.source_end_s == recommended.end
    assert not session.dirty


def test_reselecting_active_take_is_noop_and_preserves_manual_trims(
    tmp_dir, sample_script, sample_segments
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    project_path = save_project(project, tmp_dir / "clase.creacut.json")
    session = EditorSession()
    session.open(project_path)
    segment = session.project.segments[0]
    active_id = segment.selected_candidate_id
    segment.set_source_bounds(5.1, 6.2)

    same_selection = session.select_candidate(segment.id, active_id)
    same_recommendation = session.restore_recommended(segment.id)

    assert same_selection is segment
    assert same_recommendation is segment
    assert (segment.source_start_s, segment.source_end_s) == (5.1, 6.2)
    assert session.dirty


def test_selected_take_survives_session_save_and_reload(
    tmp_dir, sample_script, sample_segments
):
    project, _plan, early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    project_path = save_project(project, tmp_dir / "persisted-take.creacut.json")
    session = EditorSession()
    session.open(project_path)
    segment = session.project.segments[0]
    alternative_id = next(
        candidate.id
        for candidate in segment.candidates
        if candidate.source_start_s == early.start
    )

    session.select_candidate(segment.id, alternative_id)
    session.save()
    restored = EditorSession()
    restored.open(project_path)

    restored_segment = restored.project.segments[0]
    assert restored_segment.selected_candidate_id == alternative_id
    assert restored_segment.source_start_s == early.start
    assert not restored.dirty


def test_invalid_take_change_rolls_back_entire_project(
    tmp_dir, sample_script, sample_segments
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    later_segment = project.segments[1]
    regressing = AlignmentCandidate(
        id="p0:s1:manual-regressing",
        source_start_s=4.0,
        source_end_s=4.5,
        score=0.75,
        transcript_text="Alternativa fuera de orden.",
        segment_start_idx=1,
        segment_end_idx=1,
    )
    later = AlignmentCandidate(
        id="p0:s1:manual-recommended",
        source_start_s=7.0,
        source_end_s=8.0,
        score=0.90,
        transcript_text="Toma cronológica.",
        segment_start_idx=3,
        segment_end_idx=3,
    )
    later_segment.candidates = (regressing, later)
    later_segment.automatic_selection = replace(
        later_segment.automatic_selection,
        recommended_candidate_id=later.id,
    )
    later_segment.select_candidate(later.id)
    project_path = save_project(project, tmp_dir / "orden.creacut.json")
    session = EditorSession()
    session.open(project_path)
    live_project = session.project
    live_segment = session.project.segments[1]
    original_payload = live_project.to_dict()
    original_selection = (
        live_segment.selected_candidate_id,
        live_segment.source_start_s,
        live_segment.source_end_s,
    )

    with pytest.raises(EditorSessionError, match="chronological source order"):
        session.select_candidate(later_segment.id, regressing.id)

    assert session.project is live_project
    assert session.project.segments[1] is live_segment
    assert (
        live_segment.selected_candidate_id,
        live_segment.source_start_s,
        live_segment.source_end_s,
    ) == original_selection
    assert session.project.to_dict() == original_payload
    assert not session.dirty


def test_failed_candidate_lookup_preserves_existing_dirty_state(
    tmp_dir, sample_script, sample_segments
):
    project, _plan, early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    project_path = save_project(project, tmp_dir / "clase.creacut.json")
    session = EditorSession()
    session.open(project_path)
    segment = session.project.segments[0]
    alternative_id = next(
        candidate.id
        for candidate in segment.candidates
        if candidate.source_start_s == early.start
    )
    session.select_candidate(segment.id, alternative_id)
    dirty_payload = session.project.to_dict()

    with pytest.raises(EditorSessionError, match="unknown candidate"):
        session.select_candidate(segment.id, "candidate-inexistente")

    assert session.project.to_dict() == dirty_payload
    assert session.dirty


def test_take_selection_requires_open_project_and_known_segment():
    with pytest.raises(EditorSessionError, match="No hay un proyecto"):
        EditorSession().select_candidate("p0:s0", "take")

    session = EditorSession(project=None)
    with pytest.raises(EditorSessionError, match="No hay un proyecto"):
        session.restore_recommended("p0:s0")


def test_preview_seek_guard_rejects_stale_position_after_backward_jump():
    guard = PreviewSeekGuard()
    guard.arm()

    # The player may still emit a queued position from the later clip.
    assert not guard.accepts(12.0, 2.0, 4.0)
    assert guard.pending

    # A position inside the requested earlier clip settles the seek.
    assert guard.accepts(2.0, 2.0, 4.0)
    assert not guard.pending
    assert guard.accepts(4.1, 2.0, 4.0)


def test_preview_transition_keeps_sub_millisecond_cut_exact():
    timeline = PreviewTimeline.from_ranges(((0.0, 3.0004), (5.0, 6.0)))

    transition = next_preview_transition(timeline, timeline.clips[0])

    incoming, boundary_s = transition
    assert incoming is timeline.clips[1]
    assert boundary_s == 3.0004
    # Projecting the boundary to the millisecond slider would still point to
    # the outgoing clip, which is why playback advances by clip identity.
    assert timeline.clip_at(round(boundary_s * 1000) / 1000) is timeline.clips[0]
