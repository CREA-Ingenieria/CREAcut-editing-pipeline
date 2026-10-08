"""Strict, offline JSON persistence contracts for editable projects."""

from __future__ import annotations

import copy
import json

import pytest

from creacut.project import EditProject, ProjectValidationError
from creacut.project_io import ProjectFormatError, load_project, save_project
from tests.project_test_helpers import make_edit_project


def _write_json(path, payload, *, allow_nan: bool = False) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, allow_nan=allow_nan, indent=2),
        encoding="utf-8",
    )


def test_unicode_json_round_trip_preserves_manual_edits(
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    segment = project.segments[0]
    segment.select_candidate(segment.candidates[0].id)
    segment.set_source_bounds(early.start + 0.125, early.end - 0.05)
    segment.audio_offset_s = 0.18
    project.audio_offset_s = -0.42
    project.overlays.append({"title": "Explicación del año", "enabled": True})
    project.extensions["nota"] = "Revisión manual: ñ y á"

    path = tmp_dir / "subcarpeta con espacios" / "edición ñ.creacut.json"
    saved = save_project(project, path)
    loaded = load_project(saved)

    assert saved == path.resolve()
    assert loaded.to_dict() == project.to_dict()
    assert loaded.segments[0].selected_candidate_id == segment.candidates[0].id
    assert loaded.segments[0].source_start_s == pytest.approx(1.125)
    assert loaded.segments[0].source_end_s == pytest.approx(1.95)
    assert loaded.segments[0].audio_offset_s == pytest.approx(0.18)
    assert loaded.audio_offset_s == pytest.approx(-0.42)
    raw = path.read_text(encoding="utf-8")
    assert "Explicación del año" in raw
    assert "Revisión manual: ñ y á" in raw


def test_in_memory_dict_round_trip_is_exact(
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )

    payload = project.to_dict()
    restored = EditProject.from_dict(copy.deepcopy(payload))

    assert restored.to_dict() == payload
    assert json.loads(
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
    ) == payload


@pytest.mark.parametrize(
    ("mutation", "error_type", "message"),
    [
        (
            lambda payload: payload.__setitem__("schema_version", 999),
            ProjectFormatError,
            "schema_version",
        ),
        (
            lambda payload: payload.__setitem__("kind", "unknown.project"),
            ProjectFormatError,
            "kind",
        ),
        (
            lambda payload: payload.pop("source"),
            ProjectFormatError,
            "source",
        ),
        (
            lambda payload: payload["segments"][0].__setitem__(
                "selected_candidate_id", "missing-candidate"
            ),
            ProjectFormatError,
            "selected_candidate_id",
        ),
        (
            lambda payload: payload["segments"][0]["candidates"].append(
                copy.deepcopy(payload["segments"][0]["candidates"][0])
            ),
            ProjectFormatError,
            "duplicate candidate id",
        ),
    ],
)
def test_loader_rejects_unsupported_or_structurally_broken_projects(
    mutation,
    error_type,
    message,
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    payload = project.to_dict()
    mutation(payload)
    path = tmp_dir / "invalid.creacut.json"
    _write_json(path, payload)

    with pytest.raises(error_type, match=message):
        load_project(path)


@pytest.mark.parametrize("raw", ["{not json", "[]", "null"])
def test_loader_rejects_malformed_or_non_object_json(raw, tmp_dir):
    path = tmp_dir / "malformed.creacut.json"
    path.write_text(raw, encoding="utf-8")

    with pytest.raises(ProjectFormatError):
        load_project(path)


def test_loader_rejects_non_finite_json_numbers(
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    payload = project.to_dict()
    payload["audio_offset_s"] = float("nan")
    path = tmp_dir / "nan.creacut.json"
    _write_json(path, payload, allow_nan=True)

    with pytest.raises(ProjectFormatError, match="Non-finite JSON number"):
        load_project(path)


def test_loader_wraps_numbers_too_large_for_project_floats(
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    payload = project.to_dict()
    payload["audio_offset_s"] = 10 ** 400
    path = tmp_dir / "overflow.creacut.json"
    _write_json(path, payload)

    with pytest.raises(ProjectFormatError, match="must be finite"):
        load_project(path)


def test_loader_wraps_json_integers_beyond_python_conversion_limit(tmp_dir):
    path = tmp_dir / "huge-json-integer.creacut.json"
    path.write_text(
        '{"audio_offset_s": ' + ("1" * 5000) + "}",
        encoding="utf-8",
    )

    with pytest.raises(ProjectFormatError, match="Invalid JSON"):
        load_project(path)


@pytest.mark.parametrize("referenced", ["source", "script"])
def test_save_refuses_to_overwrite_referenced_inputs(
    referenced,
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, _early, _recommended, video_path = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    target = video_path if referenced == "source" else sample_script
    original = target.read_bytes()

    with pytest.raises(ProjectFormatError, match="Refusing to overwrite"):
        save_project(project, target)

    assert target.read_bytes() == original


def test_save_validates_project_before_accessing_source_paths(
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    project.source = None

    with pytest.raises(ProjectValidationError, match="SourceSnapshot"):
        save_project(project, tmp_dir / "invalid.creacut.json")


def test_loader_is_offline_and_does_not_require_referenced_media(
    tmp_dir,
    sample_script,
    sample_segments,
):
    project, _plan, _early, _recommended, video_path = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    path = save_project(project, tmp_dir / "offline.creacut.json")
    expected = project.to_dict()

    video_path.unlink()
    sample_script.unlink()
    loaded = load_project(path)

    assert loaded.to_dict() == expected
    assert loaded.source.path == str(video_path.resolve())
    assert loaded.script.path == str(sample_script.resolve())
