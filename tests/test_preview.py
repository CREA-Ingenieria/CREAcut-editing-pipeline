"""Pure virtual-preview timeline contracts."""

from __future__ import annotations

from dataclasses import replace
import math

import pytest

from creacut.preview import (
    PreviewClip,
    PreviewTimeline,
    PreviewTimelineError,
    build_preview_timeline,
)
from tests.project_test_helpers import make_edit_project


def test_timeline_builds_contiguous_edit_clips_and_metadata():
    timeline = PreviewTimeline.from_ranges(
        [(2.0, 5.0), (10.0, 12.0), (20.0, 20.5)],
        source_video="clase.mp4",
        project_id="proyecto-1",
        source_duration_s=30.0,
    )

    assert timeline.source_video == "clase.mp4"
    assert timeline.project_id == "proyecto-1"
    assert timeline.duration_s == pytest.approx(5.5)
    assert timeline.cut_points_s == pytest.approx((3.0, 5.0))
    assert timeline.is_empty is False
    assert timeline.clips == (
        PreviewClip(0, 2.0, 5.0, 0.0, 3.0),
        PreviewClip(1, 10.0, 12.0, 3.0, 5.0),
        PreviewClip(2, 20.0, 20.5, 5.0, 5.5),
    )


def test_edit_to_source_mapping_uses_incoming_clip_at_exact_cut():
    timeline = PreviewTimeline.from_ranges([(2.0, 5.0), (10.0, 12.0)])

    assert timeline.source_time_at(0.0) == pytest.approx(2.0)
    assert timeline.source_time_at(1.5) == pytest.approx(3.5)
    assert timeline.clip_at(2.999).index == 0
    assert timeline.source_time_at(3.0) == pytest.approx(10.0)
    assert timeline.clip_at(3.0).index == 1
    assert timeline.source_time_at(4.25) == pytest.approx(11.25)
    assert timeline.source_time_at(5.0) == pytest.approx(12.0)
    assert timeline.clip_at(5.0).index == 1


def test_source_to_edit_mapping_reports_removed_times_and_boundary_semantics():
    timeline = PreviewTimeline.from_ranges(
        [(2.0, 5.0), (10.0, 12.0), (12.0, 13.0)]
    )

    assert timeline.edit_time_at(1.99) is None
    assert timeline.edit_time_at(2.0) == pytest.approx(0.0)
    assert timeline.edit_time_at(3.5) == pytest.approx(1.5)
    # A retained range end remains a useful seek target even though the inverse
    # edit boundary maps to the incoming range.
    assert timeline.edit_time_at(5.0) == pytest.approx(3.0)
    assert timeline.edit_time_at(7.0) is None
    assert timeline.edit_time_at(10.0) == pytest.approx(3.0)
    # Touching source ranges assign their shared boundary to the incoming clip.
    assert timeline.edit_time_at(12.0) == pytest.approx(5.0)
    assert timeline.edit_time_at(13.0) == pytest.approx(6.0)
    assert timeline.edit_time_at(14.0) is None


def test_cut_navigation_is_strict_and_stays_within_internal_boundaries():
    timeline = PreviewTimeline.from_ranges(
        [(2.0, 5.0), (10.0, 12.0), (20.0, 21.0)]
    )

    assert timeline.previous_cut(0.0) is None
    assert timeline.next_cut(0.0) == pytest.approx(3.0)
    assert timeline.next_cut(2.9) == pytest.approx(3.0)
    assert timeline.next_cut(3.0) == pytest.approx(5.0)
    assert timeline.previous_cut(3.0) is None
    assert timeline.previous_cut(3.001) == pytest.approx(3.0)
    assert timeline.previous_cut(5.0) == pytest.approx(3.0)
    assert timeline.next_cut(timeline.duration_s) is None
    assert timeline.previous_cut(timeline.duration_s) == pytest.approx(5.0)


def test_empty_preview_is_a_valid_non_playable_state():
    timeline = PreviewTimeline.from_ranges([])

    assert timeline.clips == ()
    assert timeline.duration_s == pytest.approx(0.0)
    assert timeline.cut_points_s == ()
    assert timeline.is_empty is True
    assert timeline.clip_at(0.0) is None
    assert timeline.source_time_at(0.0) is None
    assert timeline.edit_time_at(10.0) is None
    assert timeline.next_cut(0.0) is None
    assert timeline.previous_cut(0.0) is None


def test_project_factory_uses_the_current_compiled_ranges(
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, _early, _recommended, video_path = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    expected_ranges = project.compile_clean_ranges()

    timeline = build_preview_timeline(project)

    assert timeline.source_video == str(video_path.resolve())
    assert timeline.project_id == project.project_id
    assert [
        (clip.source_start_s, clip.source_end_s) for clip in timeline.clips
    ] == expected_ranges
    assert timeline.duration_s == pytest.approx(
        sum(end - start for start, end in expected_ranges)
    )


def test_media_duration_only_trims_derived_tail_padding(
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, _early, recommended, _video_path = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    unbounded = project.compile_clean_ranges()
    assert unbounded[-1][1] > recommended.end

    media_duration = recommended.end + 0.25
    timeline = PreviewTimeline.from_project(
        project, source_duration_s=media_duration
    )

    assert timeline.source_duration_s == pytest.approx(media_duration)
    assert timeline.clips[-1].source_end_s == pytest.approx(media_duration)


def test_media_duration_does_not_silently_truncate_a_selected_edit(
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, _early, recommended, _video_path = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )

    with pytest.raises(PreviewTimelineError, match="exceeds actual source duration"):
        PreviewTimeline.from_project(
            project, source_duration_s=recommended.end - 0.1
        )


def test_media_duration_allows_one_millisecond_backend_quantization(
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, _early, recommended, _video_path = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    reported_duration = recommended.end - 0.0005

    timeline = PreviewTimeline.from_project(
        project, source_duration_s=reported_duration
    )

    # The selection is accepted within backend precision, while derived tail
    # padding is still clipped to the exact duration actually reported.
    assert timeline.clips[-1].source_end_s == pytest.approx(reported_duration)


@pytest.mark.parametrize(
    ("ranges", "message"),
    [
        ([(2.0, 2.0)], "end must be greater"),
        ([(3.0, 2.0)], "end must be greater"),
        ([(-1.0, 2.0)], "must be >="),
        ([(2.0, math.inf)], "must be finite"),
        ([(2.0, 5.0), (4.0, 6.0)], "non-overlapping"),
        ([(2.0, 5.0), (1.0, 1.5)], "non-overlapping"),
        ([(2.0,)], "start, end"),
    ],
)
def test_range_validation_rejects_ambiguous_timelines(ranges, message):
    with pytest.raises(PreviewTimelineError, match=message):
        PreviewTimeline.from_ranges(ranges)


def test_known_source_duration_and_query_bounds_are_validated():
    with pytest.raises(PreviewTimelineError, match="known source duration"):
        PreviewTimeline.from_ranges(
            [(2.0, 5.1)], source_duration_s=5.0
        )

    timeline = PreviewTimeline.from_ranges([(2.0, 5.0)])
    with pytest.raises(PreviewTimelineError, match="must be >="):
        timeline.source_time_at(-0.1)
    with pytest.raises(PreviewTimelineError, match="exceeds preview duration"):
        timeline.source_time_at(3.1)
    with pytest.raises(PreviewTimelineError, match="must be finite"):
        timeline.edit_time_at(math.nan)

    with pytest.raises(PreviewTimelineError, match="index: expected an integer"):
        PreviewTimeline((PreviewClip(True, 0.0, 1.0, 0.0, 1.0),))


def test_invalid_project_is_wrapped_as_preview_error(
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, _early, _recommended, _video_path = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    project.source = replace(project.source, duration_s=5.5)

    with pytest.raises(
        PreviewTimelineError, match="project cannot be compiled for preview"
    ):
        PreviewTimeline.from_project(project)
