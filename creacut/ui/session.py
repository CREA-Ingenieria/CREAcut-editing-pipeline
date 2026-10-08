"""Qt-independent document state used by the local editor."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
import os
from pathlib import Path

from ..project import EditProject, EditSegment, ProjectValidationError
from ..project_io import load_project, save_project
from ..source_timeline import (
    SourceTimelineError,
    SourceTimelineState,
    TIMELINE_EXTENSION_KEY,
)


class EditorSessionError(RuntimeError):
    """The requested editor operation has no valid document target."""


def format_seconds(value: float | None) -> str:
    """Format seconds for editor controls without losing sub-second detail."""
    if value is None:
        return "--:--.---"
    milliseconds = max(0, round(float(value) * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


def segment_label(segment: EditSegment, ordinal: int) -> str:
    """Return the compact, stable label shown in the segment list."""
    if segment.source_start_s is None or segment.source_end_s is None:
        range_text = "sin toma"
        score_text = "--"
    else:
        range_text = (
            f"{format_seconds(segment.source_start_s)}–"
            f"{format_seconds(segment.source_end_s)}"
        )
        score = segment.alignment_score
        score_text = "--" if score is None else f"{score:.0%}"
    modified = " • editado" if segment.is_modified else ""
    return f"{ordinal:03d}  {range_text}  {score_text}{modified}\n{segment.script_text}"


@dataclass
class EditorSession:
    """Loaded project plus editor-only state.

    ``media_override`` is deliberately not persisted.  It lets a user locate
    a moved source video without silently changing the project's provenance.
    """

    project: EditProject | None = None
    project_path: Path | None = None
    media_override: Path | None = None
    dirty: bool = False
    _original_payload: dict | None = field(default=None, repr=False)
    _timeline_undo: list[dict[str, object]] = field(default_factory=list, repr=False)
    _timeline_redo: list[dict[str, object]] = field(default_factory=list, repr=False)

    @property
    def is_open(self) -> bool:
        return self.project is not None

    @property
    def can_undo_timeline(self) -> bool:
        return bool(self._timeline_undo)

    @property
    def can_redo_timeline(self) -> bool:
        return bool(self._timeline_redo)

    def open(self, path: str | Path) -> EditProject:
        project_path = Path(path).expanduser().resolve()
        project = load_project(project_path)
        self.project = project
        self.project_path = project_path
        self.media_override = None
        self.dirty = False
        self._original_payload = project.to_dict()
        self._timeline_undo.clear()
        self._timeline_redo.clear()
        return project

    def save(self, path: str | Path | None = None) -> Path:
        if self.project is None:
            raise EditorSessionError("No hay un proyecto abierto para guardar")
        target = Path(path).expanduser() if path is not None else self.project_path
        if target is None:
            raise EditorSessionError("El proyecto todavía no tiene una ruta de guardado")
        saved = save_project(self.project, target)
        self.project_path = saved
        self.dirty = False
        self._original_payload = self.project.to_dict()
        return saved

    def refresh_dirty(self) -> bool:
        if self.project is None:
            self.dirty = False
        else:
            self.dirty = self._original_payload != self.project.to_dict()
        return self.dirty

    def select_candidate(
        self,
        segment_id: str,
        candidate_id: str,
    ) -> EditSegment:
        """Select a take by stable IDs and commit only a compilable edit.

        Selecting the candidate that is already active is a true no-op.  In
        particular, it does not reset source bounds that may have been trimmed
        manually by a later editor stage.
        """
        if not isinstance(candidate_id, str) or not candidate_id:
            raise EditorSessionError(
                "La toma debe identificarse con un candidate_id válido"
            )
        return self._select_candidate_transaction(segment_id, candidate_id)

    def restore_recommended(self, segment_id: str) -> EditSegment:
        """Restore CREAcut's automatic recommendation for one segment.

        An unmatched sentence can legitimately have no recommendation; in
        that case restoring it clears the current take.  As with
        :meth:`select_candidate`, an already-active recommendation is not
        re-applied, so existing trims are preserved.
        """
        project = self._require_project()
        segment = self._segment_by_id(project, segment_id)
        return self._select_candidate_transaction(
            segment_id,
            segment.automatic_selection.recommended_candidate_id,
        )

    def _select_candidate_transaction(
        self,
        segment_id: str,
        candidate_id: str | None,
    ) -> EditSegment:
        project = self._require_project()
        current = self._segment_by_id(project, segment_id)

        if current.selected_candidate_id == candidate_id:
            # Keep manually adjusted bounds intact while ensuring dirty is
            # accurate even when callers modified the model directly first.
            self.refresh_dirty()
            return current

        # Candidate selection mutates exactly these three scalar fields.  Keep
        # their values instead of cloning the full project (whose Whisper word
        # snapshot can be very large), then restore them verbatim on failure.
        previous_dirty = self.refresh_dirty()
        previous_selection = (
            current.selected_candidate_id,
            current.source_start_s,
            current.source_end_s,
        )
        try:
            current.select_candidate(candidate_id)
            # compile_clean_ranges() enters through to_matches(), which
            # validates the whole project before deriving render ranges.
            project.compile_clean_ranges()
        except (ProjectValidationError, KeyError, TypeError, ValueError) as exc:
            (
                current.selected_candidate_id,
                current.source_start_s,
                current.source_end_s,
            ) = previous_selection
            self.dirty = previous_dirty
            raise EditorSessionError(
                f"No se pudo cambiar la toma de {segment_id}: {exc}"
            ) from exc

        self.refresh_dirty()
        return current

    def trim_segment(
        self, segment_id: str, start_s: float, end_s: float
    ) -> EditSegment:
        """Commit a candidate-bound trim only when legacy ordering remains valid."""
        project = self._require_project()
        segment = self._segment_by_id(project, segment_id)
        previous_dirty = self.refresh_dirty()
        previous_bounds = (segment.source_start_s, segment.source_end_s)
        try:
            segment.set_source_bounds(start_s, end_s)
            project.compile_clean_ranges()
        except (ProjectValidationError, KeyError, TypeError, ValueError) as exc:
            segment.source_start_s, segment.source_end_s = previous_bounds
            self.dirty = previous_dirty
            raise EditorSessionError(
                f"No se pudo ajustar el corte de {segment_id}: {exc}"
            ) from exc
        self.refresh_dirty()
        return segment

    # --- full source timeline ---------------------------------------

    def source_timeline(self, source_duration_s: float):
        """Return the complete keep/discard projection for a known media duration."""
        project = self._require_project()
        try:
            return project.source_timeline(source_duration_s=source_duration_s)
        except (ProjectValidationError, SourceTimelineError, ValueError) as exc:
            raise EditorSessionError(
                f"No se pudo construir la línea de tiempo fuente: {exc}"
            ) from exc

    def mark_timeline_range(
        self,
        start_s: float,
        end_s: float,
        *,
        keep: bool,
        source_duration_s: float,
    ) -> None:
        """Non-destructively mark a source interval for keeping or discarding."""
        state = self._editable_timeline_state(source_duration_s)
        try:
            state.set_override(start_s, end_s, keep)
        except SourceTimelineError as exc:
            raise EditorSessionError(f"No se pudo modificar la región: {exc}") from exc
        self._commit_timeline_state(state)

    def restore_timeline_range(
        self, start_s: float, end_s: float, *, source_duration_s: float
    ) -> None:
        """Remove manual decisions in an interval and reveal CREAcut's proposal."""
        state = self._editable_timeline_state(source_duration_s)
        try:
            state.restore(start_s, end_s)
        except SourceTimelineError as exc:
            raise EditorSessionError(
                f"No se pudo restaurar la recomendación: {exc}"
            ) from exc
        self._commit_timeline_state(state)

    def split_timeline(self, source_time_s: float, *, source_duration_s: float) -> None:
        state = self._editable_timeline_state(source_duration_s)
        try:
            state.split(source_time_s)
        except SourceTimelineError as exc:
            raise EditorSessionError(f"No se pudo dividir la región: {exc}") from exc
        self._commit_timeline_state(state)

    def move_timeline_boundary(
        self,
        old_source_time_s: float,
        new_source_time_s: float,
        *,
        source_duration_s: float,
    ) -> None:
        projection = self.source_timeline(source_duration_s)
        pair = next(
            (
                (left, right)
                for left, right in zip(projection.regions, projection.regions[1:])
                if abs(right.start_s - old_source_time_s) <= 0.02
            ),
            None,
        )
        if pair is None:
            raise EditorSessionError("El borde seleccionado ya no existe en la línea de tiempo")
        state = self._editable_timeline_state(source_duration_s)
        try:
            state.move_boundary(
                old_source_time_s,
                new_source_time_s,
                left_keep=pair[0].keep,
                right_keep=pair[1].keep,
            )
        except SourceTimelineError as exc:
            raise EditorSessionError(f"No se pudo mover el corte: {exc}") from exc
        self._commit_timeline_state(state)

    def undo_timeline(self) -> bool:
        if not self._timeline_undo:
            return False
        project = self._require_project()
        current = copy.deepcopy(project.extensions)
        previous = self._timeline_undo.pop()
        project.extensions = copy.deepcopy(previous)
        try:
            project.validate()
        except ProjectValidationError as exc:  # Defensive: snapshots are validated on commit.
            project.extensions = current
            self._timeline_undo.append(previous)
            raise EditorSessionError(f"No se pudo deshacer el cambio: {exc}") from exc
        self._timeline_redo.append(current)
        self.refresh_dirty()
        return True

    def redo_timeline(self) -> bool:
        if not self._timeline_redo:
            return False
        project = self._require_project()
        current = copy.deepcopy(project.extensions)
        following = self._timeline_redo.pop()
        project.extensions = copy.deepcopy(following)
        try:
            project.validate()
        except ProjectValidationError as exc:
            project.extensions = current
            self._timeline_redo.append(following)
            raise EditorSessionError(f"No se pudo rehacer el cambio: {exc}") from exc
        self._timeline_undo.append(current)
        self.refresh_dirty()
        return True

    def _editable_timeline_state(self, source_duration_s: float) -> SourceTimelineState:
        project = self._require_project()
        try:
            duration = float(source_duration_s)
            current = project.source_timeline_state()
            if current is None:
                return SourceTimelineState.empty(duration)
            if abs(current.source_duration_s - duration) > 0.1:
                raise EditorSessionError(
                    "La duración del archivo localizado no coincide con la del proyecto editable"
                )
            return current.copy()
        except (ProjectValidationError, SourceTimelineError, TypeError, ValueError) as exc:
            if isinstance(exc, EditorSessionError):
                raise
            raise EditorSessionError(
                f"No se pudo preparar la línea de tiempo: {exc}"
            ) from exc

    def _commit_timeline_state(self, state: SourceTimelineState) -> None:
        project = self._require_project()
        previous_extensions = copy.deepcopy(project.extensions)
        try:
            # Returning every manual range and split to the derived baseline
            # removes the optional extension entirely, preserving an exact v1
            # payload for projects that end up unedited.
            if not state.overrides and not state.manual_boundaries_s:
                project.extensions.pop(TIMELINE_EXTENSION_KEY, None)
            else:
                project.set_source_timeline_state(state)
            # Compile immediately so no malformed timeline is saved or sent to
            # preview/render.  This keeps the mutation transactional.
            project.compile_render_ranges(source_duration_s=state.source_duration_s)
            project.validate()
        except (ProjectValidationError, SourceTimelineError, KeyError, TypeError, ValueError) as exc:
            project.extensions = previous_extensions
            raise EditorSessionError(
                f"No se pudo guardar la decisión de línea de tiempo: {exc}"
            ) from exc
        self._timeline_undo.append(previous_extensions)
        self._timeline_redo.clear()
        self.refresh_dirty()

    def _require_project(self) -> EditProject:
        if self.project is None:
            raise EditorSessionError("No hay un proyecto abierto para editar")
        return self.project

    @staticmethod
    def _segment_by_id(project: EditProject, segment_id: str) -> EditSegment:
        if not isinstance(segment_id, str) or not segment_id:
            raise EditorSessionError(
                "El segmento debe identificarse con un segment_id válido"
            )
        segment = next(
            (item for item in project.segments if item.id == segment_id),
            None,
        )
        if segment is None:
            raise EditorSessionError(f"No existe el segmento {segment_id!r}")
        return segment

    def set_media_override(self, path: str | Path | None) -> None:
        self.media_override = (
            None if path is None else Path(path).expanduser().resolve()
        )

    def source_candidates(self) -> tuple[Path, ...]:
        """Return source candidates in deterministic lookup order."""
        if self.project is None:
            return ()
        candidates: list[Path] = []
        if self.media_override is not None:
            candidates.append(self.media_override)

        stored = Path(self.project.source.path).expanduser()
        if stored.is_absolute():
            candidates.append(stored.resolve())
        else:
            if self.project_path is not None:
                candidates.append((self.project_path.parent / stored).resolve())
            candidates.append(stored.resolve())

        unique: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            # Respect the host filesystem's case rules: normcase folds on
            # Windows but leaves distinct case-sensitive POSIX paths intact.
            key = os.path.normcase(os.path.normpath(str(candidate)))
            if key not in seen:
                seen.add(key)
                unique.append(candidate)
        return tuple(unique)

    def source_path(self) -> Path | None:
        """Return the first existing source, or the preferred missing path."""
        candidates = self.source_candidates()
        return next((path for path in candidates if path.is_file()), None) or (
            candidates[0] if candidates else None
        )
