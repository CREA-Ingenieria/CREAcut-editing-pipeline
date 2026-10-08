"""Small Qt-independent state helpers for virtual preview playback."""

from __future__ import annotations

from dataclasses import dataclass

from ..preview import PreviewClip, PreviewTimeline


def next_preview_transition(
    timeline: PreviewTimeline, clip: PreviewClip
) -> tuple[PreviewClip, float] | None:
    """Return the exact incoming clip/boundary after ``clip``."""
    next_index = clip.index + 1
    if next_index >= len(timeline.clips):
        return None
    incoming = timeline.clips[next_index]
    return incoming, incoming.edit_start_s


@dataclass
class PreviewSeekGuard:
    """Reject stale media positions until a requested clip seek settles."""

    tolerance_s: float = 0.075
    pending: bool = False

    def arm(self) -> None:
        self.pending = True

    def reset(self) -> None:
        self.pending = False

    def accepts(
        self, source_time_s: float, clip_start_s: float, clip_end_s: float
    ) -> bool:
        if self.pending:
            if not (
                clip_start_s - self.tolerance_s
                <= source_time_s
                <= clip_end_s + self.tolerance_s
            ):
                return False
            self.pending = False
            return True
        return source_time_s >= clip_start_s - self.tolerance_s
