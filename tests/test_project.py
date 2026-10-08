"""Contracts for the editable project generated from alignment evidence."""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from creacut.decisions import AlignmentCandidate
from creacut.project import ProjectValidationError
from tests.project_test_helpers import make_edit_project


def test_conversion_preserves_alternatives_unmatched_and_transcript_words(
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, early, recommended, video_path = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )

    assert project.source.path == str(video_path.resolve())
    assert project.script.path == str(sample_script.resolve())
    assert project.script.identification_score == pytest.approx(0.97)
    assert len(project.segments) == 2

    selected, unmatched = project.segments
    assert [candidate.id for candidate in selected.candidates] == [
        candidate.id for candidate in _plan.decisions[0].candidates
    ]
    assert selected.automatic_selection.recommended_candidate_id == (
        _plan.decisions[0].selected_candidate_id
    )
    assert selected.selected_candidate_id == selected.automatic_selection.recommended_candidate_id
    assert selected.source_start_s == pytest.approx(recommended.start)
    assert selected.source_end_s == pytest.approx(recommended.end)
    assert selected.transcript_text == recommended.transcript_text
    assert selected.alignment_score == pytest.approx(recommended.score)
    assert selected.candidates[0].source_start_s == pytest.approx(early.start)

    # Unmatched script content remains observable instead of silently vanishing.
    assert unmatched.script_text == "Esta oración no fue pronunciada."
    assert unmatched.candidates == ()
    assert unmatched.automatic_selection.selection_reason == "no_candidate"
    assert unmatched.selected_candidate_id is None
    assert unmatched.source_start_s is None
    assert unmatched.source_end_s is None

    # Word-level Whisper evidence is copied into the offline project snapshot.
    first_snapshot = project.transcript.segments[0]
    assert first_snapshot["text"] == sample_segments[0]["text"]
    assert first_snapshot["words"][0]["word"] == sample_segments[0]["words"][0]["word"]
    assert first_snapshot["words"][0]["start"] == pytest.approx(
        sample_segments[0]["words"][0]["start"]
    )
    expected_text = " ".join(
        segment["text"].strip() for segment in sample_segments
    )
    assert project.transcript.text == expected_text


def test_recommendation_is_immutable_evidence_while_selection_and_trim_are_editable(
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, early, recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    segment = project.segments[0]
    recommendation = segment.automatic_selection.recommended_candidate_id
    alternative_id = segment.candidates[0].id

    segment.select_candidate(alternative_id)

    assert segment.automatic_selection.recommended_candidate_id == recommendation
    assert segment.selected_candidate_id == alternative_id
    assert segment.source_start_s == pytest.approx(early.start)
    assert segment.source_end_s == pytest.approx(early.end)
    assert segment.transcript_text == early.transcript_text
    assert segment.alignment_score == pytest.approx(early.score)
    assert segment.is_modified is True

    segment.set_source_bounds(early.start + 0.1, early.end - 0.1)

    assert segment.source_start_s == pytest.approx(1.1)
    assert segment.source_end_s == pytest.approx(1.9)
    # Trimming current state never mutates the candidate evidence.
    assert segment.selected_candidate.source_start_s == pytest.approx(early.start)
    assert segment.selected_candidate.source_end_s == pytest.approx(early.end)
    assert segment.automatic_selection.recommended_candidate_id == recommendation
    assert recommendation != alternative_id
    assert recommended.start == pytest.approx(5.0)


def test_offsets_are_editable_and_to_matches_preserves_legacy_projection(
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, plan, _early, recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )

    assert project.audio_offset_s == pytest.approx(0.0)
    assert all(segment.audio_offset_s == pytest.approx(0.0) for segment in project.segments)
    matches = project.to_matches()
    assert matches == list(plan.selected_matches)
    assert len(matches) == 1
    assert matches[0].transcript_text == recommended.transcript_text
    assert matches[0].segment_start_idx == recommended.segment_start_idx
    assert matches[0].refinements == recommended.refinements

    project.audio_offset_s = -0.35
    project.segments[0].audio_offset_s = 0.12
    project.validate()

    assert project.audio_offset_s == pytest.approx(-0.35)
    assert project.segments[0].audio_offset_s == pytest.approx(0.12)
    # Offsets are persisted edit metadata; source cut coordinates stay unchanged.
    assert project.to_matches()[0].start == pytest.approx(recommended.start)


def test_clean_range_compilation_matches_the_legacy_pipeline(
    tmp_dir,
    sample_script,
    sample_segments,
):
    from creacut.align import merge_ranges, pad_ranges, split_on_word_gaps

    project, plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    raw_ranges = [(match.start, match.end) for match in plan.selected_matches]
    expected = merge_ranges(raw_ranges, project.settings)
    raw_duration = sample_segments[-1]["end"]
    expected = pad_ranges(expected, raw_duration + 5.0, project.settings)
    expected = split_on_word_gaps(expected, sample_segments, project.settings)
    if expected:
        start, end = expected[-1]
        expected[-1] = (start, min(raw_duration + 5.0, end + 1.0))

    assert project.compile_clean_ranges() == expected


def test_clean_range_compilation_rejects_manual_take_order_regression(
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    later_script_segment = project.segments[1]
    earlier_take = AlignmentCandidate(
        id="p0:s1:manual-earlier-take",
        source_start_s=1.0,
        source_end_s=2.0,
        score=0.80,
        transcript_text="Toma manual anterior.",
        segment_start_idx=0,
        segment_end_idx=0,
    )
    later_script_segment.candidates = (earlier_take,)
    later_script_segment.select_candidate(earlier_take.id)

    with pytest.raises(ProjectValidationError, match="chronological source order"):
        project.compile_clean_ranges()


def test_project_validation_rejects_broken_ids_ranges_and_non_finite_offsets(
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    segment = project.segments[0]

    with pytest.raises(ProjectValidationError, match="unknown candidate"):
        segment.select_candidate("candidate-that-does-not-exist")
    with pytest.raises(ProjectValidationError, match="end must be greater than start"):
        segment.set_source_bounds(3.0, 2.0)

    segment.candidates = (segment.candidates[0], segment.candidates[0])
    with pytest.raises(ProjectValidationError, match="duplicate candidate id"):
        project.validate()

    # Restore candidates before checking the separate finite-number invariant.
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    project.audio_offset_s = math.inf
    with pytest.raises(ProjectValidationError, match="must be finite"):
        project.validate()


def test_project_validation_cross_checks_transcript_indices_and_known_duration(
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    segment = project.segments[0]
    invalid = replace(
        segment.candidates[0],
        segment_start_idx=len(project.transcript.segments),
        segment_end_idx=len(project.transcript.segments),
    )
    segment.candidates = (invalid, *segment.candidates[1:])

    with pytest.raises(ProjectValidationError, match="outside the snapshot"):
        project.validate()

    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    project.source = replace(project.source, duration_s=5.5)
    with pytest.raises(ProjectValidationError, match="known source duration"):
        project.validate()
