"""UTF-8 JSON persistence for :mod:`creacut.project`."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .project import EditProject, ProjectValidationError


class ProjectFormatError(ValueError):
    """A project file is unreadable or violates the supported schema."""


def _reject_non_finite(token: str):
    raise ProjectFormatError(f"Non-finite JSON number is not allowed: {token}")


def _same_local_path(first: str | Path, second: str | Path) -> bool:
    return os.path.normcase(str(Path(first).resolve())) == os.path.normcase(
        str(Path(second).resolve())
    )


def save_project(project: EditProject, path: str | Path) -> Path:
    """Validate and atomically save a project as UTF-8 JSON."""
    if not isinstance(project, EditProject):
        raise TypeError("project must be an EditProject")
    payload = project.to_dict()
    destination = Path(path).resolve()
    for role, referenced_path in (
        ("source video", project.source.path),
        ("script", project.script.path),
    ):
        if _same_local_path(destination, referenced_path):
            raise ProjectFormatError(
                f"Refusing to overwrite project {role}: {destination}"
            )
    encoded = json.dumps(
        payload, ensure_ascii=False, indent=2, allow_nan=False
    ) + "\n"
    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", delete=False,
            dir=destination.parent,
            prefix=f".{destination.name}.", suffix=".tmp",
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, destination)
    except Exception:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    return destination


def load_project(path: str | Path) -> EditProject:
    """Load and validate a project without resolving or opening its media paths."""
    source = Path(path)
    try:
        raw = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ProjectFormatError(f"Cannot read project {source}: {exc}") from exc
    try:
        payload = json.loads(raw, parse_constant=_reject_non_finite)
    except ProjectFormatError:
        raise
    except ValueError as exc:
        raise ProjectFormatError(
            f"Invalid JSON in project {source}: {exc}"
        ) from exc
    try:
        return EditProject.from_dict(payload)
    except (ProjectValidationError, TypeError, KeyError) as exc:
        raise ProjectFormatError(f"Invalid CREAcut project {source}: {exc}") from exc
