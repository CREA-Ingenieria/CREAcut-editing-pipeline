"""Pipeline contracts for generating an editable project without rendering."""

from __future__ import annotations

import copy
import json

import pytest

import creacut.pipeline as pipeline_module
from creacut.config import DEFAULTS


def _unexpected_stage(name: str):
    def fail(*args, **kwargs):
        raise AssertionError(f"project_only reached {name}")

    return fail


def test_project_only_stops_before_content_detection_and_rendering(
    monkeypatch,
    tmp_dir,
    sample_script,
    sample_segments,
):
    """Project generation must remain usable without MoviePy, FFmpeg, or LLMs."""
    video_path = tmp_dir / "clase con acento ñ.mp4"
    video_path.write_bytes(b"")
    project_path = tmp_dir / "edición propuesta.creacut.json"

    config = copy.deepcopy(DEFAULTS)
    # Leave all feature flags enabled deliberately: the early return, rather
    # than configuration, must protect project-only generation from later work.
    monkeypatch.setattr(
        pipeline_module,
        "transcribe",
        lambda *args, **kwargs: {
            "segments": copy.deepcopy(sample_segments),
            "text": " ".join(segment["text"] for segment in sample_segments),
        },
    )
    monkeypatch.setattr(
        pipeline_module,
        "patch_ghost_words",
        lambda *args, **kwargs: (copy.deepcopy(sample_segments), False),
    )

    forbidden = (
        "detect_lists",
        "extract_list_items",
        "detect_terms",
        "build_term_overlays",
        "detect_bold_cards",
        "build_cut_clip",
        "composite_overlays",
        "composite_equations",
        "composite_terms",
        "wrap_with_bookends",
        "export_clip",
        "normalize_audio",
        "merge_ranges",
        "pad_ranges",
        "split_on_word_gaps",
        "remap_to_cut",
    )
    for name in forbidden:
        monkeypatch.setattr(pipeline_module, name, _unexpected_stage(name))

    project = pipeline_module.process_video(
        str(video_path),
        script=str(sample_script),
        config=config,
        project_output=str(project_path),
        project_only=True,
    )

    assert project is not None
    assert project_path.is_file()
    payload = json.loads(project_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] >= 1
    assert payload["source"]["path"] == str(video_path.resolve())
    assert payload["script"]["path"] == str(sample_script.resolve())
    assert payload["source"]["duration_s"] is None
    assert not (tmp_dir / f"{video_path.stem}{config['output']['suffix']}.mp4").exists()


def test_output_path_collisions_are_rejected_before_writing(tmp_dir):
    source = tmp_dir / "source.mp4"
    script = tmp_dir / "script.md"
    output = tmp_dir / "output.mp4"

    with pytest.raises(SystemExit, match="overwrite the source video"):
        pipeline_module._validate_output_paths(
            source,
            script,
            output_video=None,
            json_output=None,
            project_output=str(source),
        )

    with pytest.raises(SystemExit, match="use the same path"):
        pipeline_module._validate_output_paths(
            source,
            script,
            output_video=output,
            json_output=str(output),
            project_output=None,
        )

    with pytest.raises(SystemExit, match="Whisper cache"):
        pipeline_module._validate_output_paths(
            source,
            script,
            output_video=None,
            json_output=None,
            project_output=str(source.with_suffix(".whisper.json")),
        )
