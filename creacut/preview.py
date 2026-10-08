"""Pure virtual-preview timeline for editable CREAcut projects.

The preview timeline is intentionally independent from Qt and media backends.
It describes the hard-cut concatenation of ``EditProject.compile_clean_ranges``
and lets a controller translate between edited and source-video timestamps.
Render-only effects such as crossfades, chroma and overlays are not represented
here because a single-source player cannot reproduce them without rendering.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import Iterable

from .project import EditProject, ProjectValidationError


_TIME_TOLERANCE_S = 1e-9
# Media backends commonly expose duration as an integer millisecond. This
# tolerance is used only to compare selected evidence against that duration;
# derived preview ranges are still trimmed to the exact reported endpoint.
_MEDIA_DURATION_TOLERANCE_S = 0.001


class PreviewTimelineError(ValueError):
    """Raised when a virtual preview cannot be built or queried safely."""


def _finite_time(value: object, name: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PreviewTimelineError(f"{name}: expected a number")
    result = float(value)
    if not math.isfinite(result):
        raise PreviewTimelineError(f"{name}: must be finite")
    if result < minimum:
        raise PreviewTimelineError(f"{name}: must be >= {minimum}")
    return result


@dataclass(frozen=True, slots=True)
class PreviewClip:
    """One retained source range placed on the virtual edited timeline."""

    index: int
    source_start_s: float
    source_end_s: float
    edit_start_s: float
    edit_end_s: float

    @property
    def duration_s(self) -> float:
        return self.source_end_s - self.source_start_s


@dataclass(frozen=True, slots=True)
class PreviewTimeline:
    """Immutable mapping between a hard-cut edit and its source video.

    Internal edit boundaries are right-continuous: at an exact cut timestamp,
    :meth:`source_time_at` and :meth:`clip_at` select the incoming clip. The
    final edit timestamp is the sole exception and maps to the last clip end.
    This matches what a playback controller should seek to after crossing a
    cut while keeping the total-duration endpoint useful.
    """

    clips: tuple[PreviewClip, ...]
    source_video: str | None = None
    project_id: str | None = None
    source_duration_s: float | None = None
    _duration_s: float = field(init=False, repr=False, compare=False)
    _cut_points_s: tuple[float, ...] = field(
        init=False, repr=False, compare=False
    )
    _source_starts_s: tuple[float, ...] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if not isinstance(self.clips, tuple):
            raise PreviewTimelineError("clips: expected an immutable tuple")
        if self.source_video is not None and (
            not isinstance(self.source_video, str) or not self.source_video
        ):
            raise PreviewTimelineError(
                "source_video: expected a non-empty string or null"
            )
        if self.project_id is not None and (
            not isinstance(self.project_id, str) or not self.project_id
        ):
            raise PreviewTimelineError("project_id: expected a non-empty string or null")

        known_duration = None
        if self.source_duration_s is not None:
            known_duration = _finite_time(
                self.source_duration_s, "source_duration_s"
            )

        previous_source_end: float | None = None
        expected_edit_start = 0.0
        for position, clip in enumerate(self.clips):
            path = f"clips[{position}]"
            if not isinstance(clip, PreviewClip):
                raise PreviewTimelineError(f"{path}: expected PreviewClip")
            if isinstance(clip.index, bool) or not isinstance(clip.index, int):
                raise PreviewTimelineError(f"{path}.index: expected an integer")
            if clip.index != position:
                raise PreviewTimelineError(
                    f"{path}.index: expected {position}, got {clip.index}"
                )
            source_start = _finite_time(
                clip.source_start_s, f"{path}.source_start_s"
            )
            source_end = _finite_time(clip.source_end_s, f"{path}.source_end_s")
            edit_start = _finite_time(clip.edit_start_s, f"{path}.edit_start_s")
            edit_end = _finite_time(clip.edit_end_s, f"{path}.edit_end_s")
            if source_end <= source_start:
                raise PreviewTimelineError(
                    f"{path}: source_end_s must be greater than source_start_s"
                )
            if edit_end <= edit_start:
                raise PreviewTimelineError(
                    f"{path}: edit_end_s must be greater than edit_start_s"
                )
            if not math.isclose(
                source_end - source_start,
                edit_end - edit_start,
                rel_tol=0.0,
                abs_tol=_TIME_TOLERANCE_S,
            ):
                raise PreviewTimelineError(
                    f"{path}: source and edit durations must be equal"
                )
            if not math.isclose(
                edit_start,
                expected_edit_start,
                rel_tol=0.0,
                abs_tol=_TIME_TOLERANCE_S,
            ):
                raise PreviewTimelineError(
                    f"{path}.edit_start_s: clips must be contiguous from zero"
                )
            if (
                previous_source_end is not None
                and source_start < previous_source_end
            ):
                raise PreviewTimelineError(
                    f"{path}: source ranges must be chronological and non-overlapping"
                )
            if (
                known_duration is not None
                and source_end > known_duration + _TIME_TOLERANCE_S
            ):
                raise PreviewTimelineError(
                    f"{path}.source_end_s: exceeds known source duration"
                )
            previous_source_end = source_end
            expected_edit_start = edit_end

        object.__setattr__(self, "_duration_s", expected_edit_start)
        object.__setattr__(
            self,
            "_cut_points_s",
            tuple(clip.edit_start_s for clip in self.clips[1:]),
        )
        object.__setattr__(
            self,
            "_source_starts_s",
            tuple(clip.source_start_s for clip in self.clips),
        )

    @classmethod
    def from_project(
        cls,
        project: EditProject,
        *,
        source_duration_s: float | None = None,
    ) -> "PreviewTimeline":
        """Compile the current editable state into a virtual preview timeline.

        ``source_duration_s`` may be supplied by the media backend after it has
        loaded the file. It only trims derived padding/tail beyond the actual
        media end; a selected edit itself outside the media remains an error.
        When omitted, the project snapshot duration is used, if known.
        """
        if not isinstance(project, EditProject):
            raise PreviewTimelineError("project: expected EditProject")
        supplied_duration = None
        if source_duration_s is not None:
            supplied_duration = _finite_time(
                source_duration_s, "source_duration_s"
            )
        try:
            ranges = project.compile_render_ranges(
                source_duration_s=source_duration_s
            )
        except (ProjectValidationError, KeyError, TypeError, ValueError) as exc:
            raise PreviewTimelineError(
                f"project cannot be compiled for preview: {exc}"
            ) from exc
        known_duration = (
            project.source.duration_s
            if supplied_duration is None
            else supplied_duration
        )
        if known_duration is not None:
            for index, segment in enumerate(project.segments):
                if (
                    segment.source_end_s is not None
                    and segment.source_end_s
                    > known_duration + _MEDIA_DURATION_TOLERANCE_S
                ):
                    raise PreviewTimelineError(
                        "project cannot be previewed: "
                        f"segments[{index}].source_end_s exceeds actual source duration"
                    )
            ranges = [
                (start, min(end, known_duration))
                for start, end in ranges
                if start < known_duration
            ]
        return cls.from_ranges(
            ranges,
            source_video=project.source.path,
            project_id=project.project_id,
            source_duration_s=known_duration,
        )

    @classmethod
    def from_ranges(
        cls,
        ranges: Iterable[tuple[float, float]],
        *,
        source_video: str | Path | None = None,
        project_id: str | None = None,
        source_duration_s: float | None = None,
    ) -> "PreviewTimeline":
        """Build a timeline from chronological, non-overlapping source ranges."""
        try:
            iterator = iter(ranges)
        except TypeError as exc:
            raise PreviewTimelineError("ranges: expected an iterable") from exc

        clips: list[PreviewClip] = []
        edit_start = 0.0
        previous_source_end: float | None = None
        for index, raw_range in enumerate(iterator):
            path = f"ranges[{index}]"
            if not isinstance(raw_range, (tuple, list)) or len(raw_range) != 2:
                raise PreviewTimelineError(
                    f"{path}: expected a (start, end) pair"
                )
            source_start = _finite_time(raw_range[0], f"{path}[0]")
            source_end = _finite_time(raw_range[1], f"{path}[1]")
            if source_end <= source_start:
                raise PreviewTimelineError(
                    f"{path}: end must be greater than start"
                )
            if (
                previous_source_end is not None
                and source_start < previous_source_end
            ):
                raise PreviewTimelineError(
                    f"{path}: source ranges must be chronological and non-overlapping"
                )
            edit_end = edit_start + (source_end - source_start)
            clips.append(PreviewClip(
                index=index,
                source_start_s=source_start,
                source_end_s=source_end,
                edit_start_s=edit_start,
                edit_end_s=edit_end,
            ))
            previous_source_end = source_end
            edit_start = edit_end

        return cls(
            clips=tuple(clips),
            source_video=None if source_video is None else str(source_video),
            project_id=project_id,
            source_duration_s=source_duration_s,
        )

    @property
    def duration_s(self) -> float:
        return self._duration_s

    @property
    def cut_points_s(self) -> tuple[float, ...]:
        """Internal edit boundaries, excluding timeline start and end."""
        return self._cut_points_s

    @property
    def is_empty(self) -> bool:
        return not self.clips

    def _checked_edit_time(self, edit_time_s: float) -> float:
        value = _finite_time(edit_time_s, "edit_time_s")
        duration = self.duration_s
        if value > duration + _TIME_TOLERANCE_S:
            raise PreviewTimelineError(
                f"edit_time_s: {value} exceeds preview duration {duration}"
            )
        if value > duration:
            return duration
        return value

    def clip_at(self, edit_time_s: float) -> PreviewClip | None:
        """Return the clip active at an edited timestamp.

        An empty timeline accepts timestamp zero and returns ``None``.
        """
        value = self._checked_edit_time(edit_time_s)
        if not self.clips:
            return None
        if value == self.duration_s:
            return self.clips[-1]
        index = bisect_right(self.cut_points_s, value)
        return self.clips[index]

    def source_time_at(self, edit_time_s: float) -> float | None:
        """Map an edited timestamp to the source video.

        Exact internal cut points map to the incoming clip. ``None`` is
        returned only for the sole valid timestamp (zero) of an empty preview.
        """
        value = self._checked_edit_time(edit_time_s)
        clip = self.clip_at(value)
        if clip is None:
            return None
        if value == self.duration_s:
            return clip.source_end_s
        return clip.source_start_s + (value - clip.edit_start_s)

    def edit_time_at(self, source_time_s: float) -> float | None:
        """Map a retained source timestamp to edited time.

        Returns ``None`` for source timestamps removed by the edit. When source
        ranges touch, their shared boundary belongs to the incoming clip.
        """
        value = _finite_time(source_time_s, "source_time_s")
        if not self.clips:
            return None
        index = bisect_right(self._source_starts_s, value) - 1
        if index < 0:
            return None
        clip = self.clips[index]
        if value > clip.source_end_s:
            return None
        return clip.edit_start_s + (value - clip.source_start_s)

    def next_cut(self, edit_time_s: float) -> float | None:
        """Return the next strictly later internal cut, if any."""
        value = self._checked_edit_time(edit_time_s)
        cuts = self.cut_points_s
        index = bisect_right(cuts, value)
        return None if index >= len(cuts) else cuts[index]

    def previous_cut(self, edit_time_s: float) -> float | None:
        """Return the previous strictly earlier internal cut, if any."""
        value = self._checked_edit_time(edit_time_s)
        cuts = self.cut_points_s
        index = bisect_left(cuts, value) - 1
        return None if index < 0 else cuts[index]


def build_preview_timeline(
    project: EditProject,
    *,
    source_duration_s: float | None = None,
) -> PreviewTimeline:
    """Convenience facade used by UI/controller layers."""
    return PreviewTimeline.from_project(
        project, source_duration_s=source_duration_s
    )
