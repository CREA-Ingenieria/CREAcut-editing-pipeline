"""Full-source timeline decisions used by the semi-automatic editor.

This module deliberately has no Qt or media-backend dependency.  It models a
complete source clock (``0`` through the media duration) and a non-destructive
manual decision layer placed over CREAcut's automatic keep ranges.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
import math
from typing import Any, Iterable, Mapping, Sequence
import uuid


TIMELINE_EXTENSION_KEY = "creacut.source_timeline"
TIMELINE_STATE_VERSION = 1
_EPSILON_S = 1e-6


class SourceTimelineError(ValueError):
    """The source-timeline state is malformed or cannot be represented."""


def _finite(value: Any, path: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SourceTimelineError(f"{path}: expected a number")
    result = float(value)
    if not math.isfinite(result):
        raise SourceTimelineError(f"{path}: must be finite")
    if result < minimum:
        raise SourceTimelineError(f"{path}: must be >= {minimum}")
    return result


def _bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise SourceTimelineError(f"{path}: expected a boolean")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise SourceTimelineError(f"{path}: expected a non-empty string")
    return value


def _validate_range(start_s: Any, end_s: Any, path: str) -> tuple[float, float]:
    start = _finite(start_s, f"{path}.start_s")
    end = _finite(end_s, f"{path}.end_s")
    if end <= start:
        raise SourceTimelineError(f"{path}: end_s must be greater than start_s")
    return start, end


def _range_contains(ranges: Sequence[tuple[float, float]], value: float) -> bool:
    """Return whether ``value`` is inside one of sorted, non-overlapping ranges."""
    starts = [item[0] for item in ranges]
    index = bisect_right(starts, value) - 1
    if index < 0:
        return False
    start, end = ranges[index]
    return start - _EPSILON_S <= value < end - _EPSILON_S


def normalize_ranges(
    ranges: Iterable[tuple[float, float]], *, duration_s: float
) -> tuple[tuple[float, float], ...]:
    """Clamp and union source ranges without silently accepting invalid input."""
    duration = _finite(duration_s, "duration_s")
    ordered: list[tuple[float, float]] = []
    for index, item in enumerate(ranges):
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise SourceTimelineError(f"ranges[{index}]: expected a (start, end) pair")
        start, end = _validate_range(item[0], item[1], f"ranges[{index}]")
        if start >= duration - _EPSILON_S:
            continue
        ordered.append((max(0.0, start), min(duration, end)))
    ordered.sort()

    merged: list[tuple[float, float]] = []
    for start, end in ordered:
        if end <= start + _EPSILON_S:
            continue
        if merged and start <= merged[-1][1] + _EPSILON_S:
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return tuple(merged)


def apply_overrides(
    base_keep_ranges: Iterable[tuple[float, float]],
    state: "SourceTimelineState",
) -> tuple[tuple[float, float], ...]:
    """Overlay the persisted manual decisions onto source keep ranges."""
    state.validate()
    duration = state.source_duration_s
    base = normalize_ranges(base_keep_ranges, duration_s=duration)
    points = {0.0, duration}
    for start, end in base:
        points.add(start)
        points.add(end)
    for item in state.overrides:
        points.add(item.start_s)
        points.add(item.end_s)
    result: list[tuple[float, float]] = []
    ordered = sorted(points)
    for start, end in zip(ordered, ordered[1:]):
        if end <= start + _EPSILON_S:
            continue
        midpoint = start + (end - start) / 2
        override = next(
            (
                item
                for item in state.overrides
                if item.start_s - _EPSILON_S <= midpoint < item.end_s - _EPSILON_S
            ),
            None,
        )
        keep = _range_contains(base, midpoint) if override is None else override.keep
        if keep:
            result.append((start, end))
    return normalize_ranges(result, duration_s=duration)


@dataclass(frozen=True)
class TimelineOverride:
    """A manual keep/discard decision in source-media coordinates."""

    id: str
    start_s: float
    end_s: float
    keep: bool

    def validate(self, *, duration_s: float | None = None, path: str = "override") -> None:
        _string(self.id, f"{path}.id")
        start, end = _validate_range(self.start_s, self.end_s, path)
        _bool(self.keep, f"{path}.keep")
        if duration_s is not None and end > duration_s + _EPSILON_S:
            raise SourceTimelineError(f"{path}.end_s: exceeds source duration")
        if start < 0:
            raise SourceTimelineError(f"{path}.start_s: must be >= 0")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "id": self.id,
            "start_s": self.start_s,
            "end_s": self.end_s,
            "keep": self.keep,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], path: str) -> "TimelineOverride":
        if not isinstance(data, Mapping):
            raise SourceTimelineError(f"{path}: expected an object")
        result = cls(
            id=_string(data.get("id"), f"{path}.id"),
            start_s=_finite(data.get("start_s"), f"{path}.start_s"),
            end_s=_finite(data.get("end_s"), f"{path}.end_s"),
            keep=_bool(data.get("keep"), f"{path}.keep"),
        )
        result.validate(path=path)
        return result


@dataclass
class SourceTimelineState:
    """Persisted manual layer; automatic regions remain derived evidence.

    Overrides are ordered and non-overlapping.  The separate boundary list
    records a deliberate split even when both neighbouring regions currently
    have the same keep state.
    """

    source_duration_s: float
    overrides: list[TimelineOverride] = field(default_factory=list)
    manual_boundaries_s: list[float] = field(default_factory=list)
    version: int = TIMELINE_STATE_VERSION

    def validate(self, path: str = "source_timeline") -> None:
        if self.version != TIMELINE_STATE_VERSION:
            raise SourceTimelineError(
                f"{path}.version: unsupported version {self.version}"
            )
        duration = _finite(self.source_duration_s, f"{path}.source_duration_s")
        if duration <= 0.0:
            raise SourceTimelineError(f"{path}.source_duration_s: must be greater than zero")
        if not isinstance(self.overrides, list):
            raise SourceTimelineError(f"{path}.overrides: expected an array")
        previous_end = 0.0
        seen_ids: set[str] = set()
        for index, override in enumerate(self.overrides):
            item_path = f"{path}.overrides[{index}]"
            if not isinstance(override, TimelineOverride):
                raise SourceTimelineError(f"{item_path}: expected TimelineOverride")
            override.validate(duration_s=duration, path=item_path)
            if override.id in seen_ids:
                raise SourceTimelineError(f"{item_path}.id: duplicate override id")
            if index and override.start_s < previous_end - _EPSILON_S:
                raise SourceTimelineError(f"{item_path}: overrides must not overlap")
            seen_ids.add(override.id)
            previous_end = override.end_s
        if not isinstance(self.manual_boundaries_s, list):
            raise SourceTimelineError(f"{path}.manual_boundaries_s: expected an array")
        previous_boundary = 0.0
        for index, boundary in enumerate(self.manual_boundaries_s):
            value = _finite(boundary, f"{path}.manual_boundaries_s[{index}]")
            if not _EPSILON_S < value < duration - _EPSILON_S:
                raise SourceTimelineError(
                    f"{path}.manual_boundaries_s[{index}]: must be inside source duration"
                )
            if index and value <= previous_boundary + _EPSILON_S:
                raise SourceTimelineError(
                    f"{path}.manual_boundaries_s: must be ordered and unique"
                )
            previous_boundary = value

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "version": self.version,
            "source_duration_s": self.source_duration_s,
            "overrides": [item.to_dict() for item in self.overrides],
            "manual_boundaries_s": list(self.manual_boundaries_s),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SourceTimelineState":
        if not isinstance(data, Mapping):
            raise SourceTimelineError("source_timeline: expected an object")
        version = data.get("version")
        if isinstance(version, bool) or not isinstance(version, int):
            raise SourceTimelineError("source_timeline.version: expected an integer")
        overrides_data = data.get("overrides", [])
        boundaries_data = data.get("manual_boundaries_s", [])
        if not isinstance(overrides_data, list):
            raise SourceTimelineError("source_timeline.overrides: expected an array")
        if not isinstance(boundaries_data, list):
            raise SourceTimelineError(
                "source_timeline.manual_boundaries_s: expected an array"
            )
        result = cls(
            version=version,
            source_duration_s=_finite(
                data.get("source_duration_s"), "source_timeline.source_duration_s"
            ),
            overrides=[
                TimelineOverride.from_dict(item, f"source_timeline.overrides[{index}]")
                for index, item in enumerate(overrides_data)
            ],
            manual_boundaries_s=[
                _finite(value, f"source_timeline.manual_boundaries_s[{index}]")
                for index, value in enumerate(boundaries_data)
            ],
        )
        result.validate()
        return result

    @classmethod
    def empty(cls, source_duration_s: float) -> "SourceTimelineState":
        result = cls(source_duration_s=float(source_duration_s))
        result.validate()
        return result

    def copy(self) -> "SourceTimelineState":
        return SourceTimelineState(
            source_duration_s=self.source_duration_s,
            overrides=list(self.overrides),
            manual_boundaries_s=list(self.manual_boundaries_s),
            version=self.version,
        )

    def set_override(self, start_s: float, end_s: float, keep: bool) -> None:
        """Replace manual decisions in an interval with one explicit decision."""
        self.validate()
        start, end = _validate_range(start_s, end_s, "override")
        duration = self.source_duration_s
        if start < -_EPSILON_S or end > duration + _EPSILON_S:
            raise SourceTimelineError("override: range exceeds source duration")
        start, end = max(0.0, start), min(duration, end)
        replacement: list[TimelineOverride] = []
        for item in self.overrides:
            if item.end_s <= start + _EPSILON_S or item.start_s >= end - _EPSILON_S:
                replacement.append(item)
                continue
            if item.start_s < start - _EPSILON_S:
                replacement.append(TimelineOverride(str(uuid.uuid4()), item.start_s, start, item.keep))
            if item.end_s > end + _EPSILON_S:
                replacement.append(TimelineOverride(str(uuid.uuid4()), end, item.end_s, item.keep))
        replacement.append(TimelineOverride(str(uuid.uuid4()), start, end, bool(keep)))
        self.overrides = _coalesce_overrides(replacement)
        self.manual_boundaries_s = _normalise_boundaries(
            [*self.manual_boundaries_s, start, end], duration
        )
        self.validate()

    def restore(self, start_s: float, end_s: float) -> None:
        """Remove overrides in an interval, restoring the derived decision layer."""
        self.validate()
        start, end = _validate_range(start_s, end_s, "restore")
        duration = self.source_duration_s
        if start < -_EPSILON_S or end > duration + _EPSILON_S:
            raise SourceTimelineError("restore: range exceeds source duration")
        restored: list[TimelineOverride] = []
        for item in self.overrides:
            if item.end_s <= start + _EPSILON_S or item.start_s >= end - _EPSILON_S:
                restored.append(item)
                continue
            if item.start_s < start - _EPSILON_S:
                restored.append(TimelineOverride(str(uuid.uuid4()), item.start_s, start, item.keep))
            if item.end_s > end + _EPSILON_S:
                restored.append(TimelineOverride(str(uuid.uuid4()), end, item.end_s, item.keep))
        self.overrides = _coalesce_overrides(restored)
        self.manual_boundaries_s = _normalise_boundaries(
            [value for value in self.manual_boundaries_s if not start - _EPSILON_S <= value <= end + _EPSILON_S],
            duration,
        )
        self.validate()

    def split(self, source_time_s: float) -> None:
        self.validate()
        value = _finite(source_time_s, "split.source_time_s")
        if not _EPSILON_S < value < self.source_duration_s - _EPSILON_S:
            raise SourceTimelineError("split.source_time_s: must be inside source duration")
        self.manual_boundaries_s = _normalise_boundaries(
            [*self.manual_boundaries_s, value], self.source_duration_s
        )
        self.validate()

    def move_boundary(
        self,
        old_source_time_s: float,
        new_source_time_s: float,
        *,
        left_keep: bool,
        right_keep: bool,
    ) -> None:
        """Move a state boundary by applying the appropriate narrow override."""
        self.validate()
        old = _finite(old_source_time_s, "move_boundary.old_source_time_s")
        new = _finite(new_source_time_s, "move_boundary.new_source_time_s")
        if not _EPSILON_S < old < self.source_duration_s - _EPSILON_S:
            raise SourceTimelineError("move_boundary.old_source_time_s: outside source duration")
        if not _EPSILON_S < new < self.source_duration_s - _EPSILON_S:
            raise SourceTimelineError("move_boundary.new_source_time_s: outside source duration")
        if abs(new - old) <= _EPSILON_S:
            return
        if new > old and left_keep != right_keep:
            self.set_override(old, new, left_keep)
        elif new < old and left_keep != right_keep:
            self.set_override(new, old, right_keep)
        self.manual_boundaries_s = _normalise_boundaries(
            [
                new if abs(value - old) <= _EPSILON_S else value
                for value in self.manual_boundaries_s
            ] + [new],
            self.source_duration_s,
        )
        self.validate()


def _coalesce_overrides(
    overrides: Iterable[TimelineOverride],
) -> list[TimelineOverride]:
    ordered = sorted(overrides, key=lambda item: (item.start_s, item.end_s, item.id))
    result: list[TimelineOverride] = []
    for item in ordered:
        if item.end_s <= item.start_s + _EPSILON_S:
            continue
        if (
            result
            and result[-1].keep == item.keep
            and item.start_s <= result[-1].end_s + _EPSILON_S
        ):
            previous = result[-1]
            result[-1] = TimelineOverride(previous.id, previous.start_s, max(previous.end_s, item.end_s), previous.keep)
        else:
            result.append(item)
    return result


def _normalise_boundaries(values: Iterable[float], duration_s: float) -> list[float]:
    result: list[float] = []
    for value in sorted(float(item) for item in values):
        if not _EPSILON_S < value < duration_s - _EPSILON_S:
            continue
        if not result or value > result[-1] + _EPSILON_S:
            result.append(value)
    return result


@dataclass(frozen=True)
class SourceRegion:
    """One visible source-time interval in the editor timeline."""

    id: str
    start_s: float
    end_s: float
    automatic_keep: bool
    keep: bool
    origin: str
    linked_segment_ids: tuple[str, ...] = ()

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s

    @property
    def is_modified(self) -> bool:
        return self.origin == "manual" or self.keep != self.automatic_keep


@dataclass(frozen=True)
class SourceTimelineProjection:
    """A complete, display-ready partition of a source video."""

    duration_s: float
    regions: tuple[SourceRegion, ...]

    def __post_init__(self) -> None:
        duration = _finite(self.duration_s, "duration_s")
        if duration <= 0.0:
            raise SourceTimelineError("duration_s: must be greater than zero")
        if not self.regions:
            raise SourceTimelineError("regions: must cover the complete source duration")
        previous_end = 0.0
        for index, region in enumerate(self.regions):
            if region.start_s < previous_end - _EPSILON_S:
                raise SourceTimelineError(f"regions[{index}]: overlaps the previous region")
            if abs(region.start_s - previous_end) > _EPSILON_S:
                raise SourceTimelineError(f"regions[{index}]: leaves a gap in source coverage")
            if region.end_s <= region.start_s:
                raise SourceTimelineError(f"regions[{index}]: end_s must be greater than start_s")
            previous_end = region.end_s
        if abs(previous_end - duration) > _EPSILON_S:
            raise SourceTimelineError("regions: do not end at source duration")

    @classmethod
    def build(
        cls,
        *,
        duration_s: float,
        automatic_keep_ranges: Iterable[tuple[float, float]],
        effective_keep_ranges: Iterable[tuple[float, float]],
        state: SourceTimelineState | None = None,
        segment_ranges: Iterable[tuple[str, float, float]] = (),
    ) -> "SourceTimelineProjection":
        duration = _finite(duration_s, "duration_s")
        if duration <= 0.0:
            raise SourceTimelineError("duration_s: must be greater than zero")
        automatic = normalize_ranges(automatic_keep_ranges, duration_s=duration)
        effective = normalize_ranges(effective_keep_ranges, duration_s=duration)
        overrides = () if state is None else tuple(state.overrides)
        if state is not None:
            state.validate()
            if abs(state.source_duration_s - duration) > 0.1:
                raise SourceTimelineError(
                    "source_timeline.source_duration_s: does not match the loaded source duration"
                )
        links = tuple(segment_ranges)
        points = {0.0, duration}
        for ranges in (automatic, effective):
            for start, end in ranges:
                points.add(start)
                points.add(end)
        for override in overrides:
            points.add(override.start_s)
            points.add(override.end_s)
        if state is not None:
            points.update(state.manual_boundaries_s)
        ordered = sorted(points)
        regions: list[SourceRegion] = []
        for index, (start, end) in enumerate(zip(ordered, ordered[1:])):
            if end <= start + _EPSILON_S:
                continue
            midpoint = start + (end - start) / 2
            automatic_keep = _range_contains(automatic, midpoint)
            keep = _range_contains(effective, midpoint)
            manual = any(
                override.start_s - _EPSILON_S <= midpoint < override.end_s - _EPSILON_S
                for override in overrides
            )
            linked_ids = tuple(
                segment_id
                for segment_id, segment_start, segment_end in links
                if segment_start < end - _EPSILON_S and segment_end > start + _EPSILON_S
            )
            origin = "manual" if manual else (
                "automatic" if keep == automatic_keep else "segment"
            )
            regions.append(SourceRegion(
                id=f"r-{index}-{round(start * 1000)}-{round(end * 1000)}",
                start_s=start,
                end_s=end,
                automatic_keep=automatic_keep,
                keep=keep,
                origin=origin,
                linked_segment_ids=linked_ids,
            ))
        return cls(duration, tuple(regions))

    @property
    def keep_ranges(self) -> tuple[tuple[float, float], ...]:
        return normalize_ranges(
            [(region.start_s, region.end_s) for region in self.regions if region.keep],
            duration_s=self.duration_s,
        )

    @property
    def cut_points_s(self) -> tuple[float, ...]:
        return tuple(
            right.start_s
            for left, right in zip(self.regions, self.regions[1:])
            if left.keep != right.keep
        )

    def region_at(self, source_time_s: float) -> SourceRegion:
        value = _finite(source_time_s, "source_time_s")
        if value > self.duration_s + _EPSILON_S:
            raise SourceTimelineError("source_time_s: exceeds source duration")
        if value >= self.duration_s:
            return self.regions[-1]
        starts = [region.start_s for region in self.regions]
        return self.regions[max(0, bisect_right(starts, value) - 1)]

    def region_by_id(self, region_id: str) -> SourceRegion | None:
        return next((item for item in self.regions if item.id == region_id), None)
