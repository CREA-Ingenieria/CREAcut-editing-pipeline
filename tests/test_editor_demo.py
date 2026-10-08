"""Offline, deterministic editor-demo generator contracts."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

from creacut.preview import build_preview_timeline
from creacut.project_io import load_project, save_project
from scripts import create_editor_demo as demo


def _fake_video_factory(path: Path, *, overwrite: bool) -> Path:
    del overwrite
    path.write_bytes(b"deterministic demo video placeholder")
    return path


def test_demo_roundtrip_and_preview_are_ready_without_whisper(tmp_dir, monkeypatch):
    monkeypatch.setattr(demo, "_create_demo_video", _fake_video_factory)
    # Any accidental optional Whisper import would fail this generation path.
    monkeypatch.setitem(sys.modules, "whisper", None)

    artifacts = demo.create_editor_demo(tmp_dir / "demo con espacios")
    project = load_project(artifacts.project_path)

    assert artifacts.video_path.is_absolute()
    assert artifacts.script_path.is_absolute()
    assert artifacts.project_path.is_absolute()
    assert project.source.path == str(artifacts.video_path)
    assert project.source.duration_s == pytest.approx(12.0)
    assert project.extensions["demo"]["whisper_was_run"] is False
    assert [segment.script_text for segment in project.segments] == [
        demo.FIRST_SENTENCE,
        demo.SECOND_SENTENCE,
    ]

    first, second = project.segments
    assert len(first.candidates) == 2
    assert first.selected_candidate_id == first.candidates[1].id
    assert first.automatic_selection.recommended_candidate_id == first.candidates[1].id
    assert second.selected_candidate_id == second.candidates[0].id

    timeline = build_preview_timeline(project)
    assert len(timeline.clips) == 2
    assert [(clip.source_start_s, clip.source_end_s) for clip in timeline.clips] == pytest.approx([
        (4.75, 7.25),
        (8.75, 12.0),
    ])
    assert artifacts.preview_duration_s == pytest.approx(timeline.duration_s)

    second_copy = tmp_dir / "roundtrip.creacut.json"
    save_project(project, second_copy)
    assert load_project(second_copy).to_dict() == project.to_dict()

    # A second invocation validates and reuses the exact fixture; it performs
    # no writes and therefore cannot replace a user's unrelated source video.
    monkeypatch.setattr(
        demo,
        "_create_demo_video",
        lambda *_args, **_kwargs: pytest.fail("valid demo should be reused"),
    )
    reused = demo.create_editor_demo(artifacts.output_dir)
    assert reused == artifacts

    # A file with the same name and size is not silently accepted as the demo
    # source: the fixture records and validates its content digest.
    original_bytes = artifacts.video_path.read_bytes()
    artifacts.video_path.write_bytes(b"x" * len(original_bytes))
    with pytest.raises(demo.DemoOutputConflictError, match="incompatibles"):
        demo.create_editor_demo(artifacts.output_dir)


def test_demo_alternative_remains_chronological_and_previewable(tmp_dir, monkeypatch):
    monkeypatch.setattr(demo, "_create_demo_video", _fake_video_factory)
    artifacts = demo.create_editor_demo(tmp_dir)
    project = load_project(artifacts.project_path)

    first = project.segments[0]
    recommended_id = first.selected_candidate_id
    alternative_id = first.candidates[0].id
    first.select_candidate(alternative_id)

    assert first.selected_candidate_id != recommended_id
    assert first.is_modified is True
    assert [match.start for match in project.to_matches()] == pytest.approx([
        0.75,
        8.75,
    ])
    timeline = build_preview_timeline(project)
    assert [(clip.source_start_s, clip.source_end_s) for clip in timeline.clips] == pytest.approx([
        (0.75, 3.25),
        (8.75, 12.0),
    ])


def test_demo_refuses_partial_existing_output_unless_force_is_explicit(
    tmp_dir,
    monkeypatch,
):
    output_dir = tmp_dir / "salida"
    output_dir.mkdir()
    existing_video = output_dir / demo.VIDEO_FILENAME
    existing_video.write_bytes(b"user media")
    monkeypatch.setattr(demo, "_create_demo_video", _fake_video_factory)

    with pytest.raises(demo.DemoOutputConflictError, match="parte de los archivos"):
        demo.create_editor_demo(output_dir)
    assert existing_video.read_bytes() == b"user media"
    assert not (output_dir / demo.SCRIPT_FILENAME).exists()
    assert not (output_dir / demo.PROJECT_FILENAME).exists()

    artifacts = demo.create_editor_demo(output_dir, force=True)
    assert artifacts.video_path.read_bytes() == b"deterministic demo video placeholder"
    assert artifacts.script_path.is_file()
    assert artifacts.project_path.is_file()
