"""Project-render entry point contracts."""

from __future__ import annotations

from dataclasses import replace

import pytest

import creacut.pipeline as pipeline_module
from creacut.project_io import save_project
from creacut.source_timeline import SourceTimelineState
from tests.project_test_helpers import make_edit_project


def test_render_project_dry_run_uses_manual_effective_ranges(
    tmp_dir, sample_script, sample_segments, monkeypatch
):
    project, _plan, _early, _recommended, _video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    project.source = replace(project.source, duration_s=20.0)
    state = SourceTimelineState.empty(20.0)
    state.set_override(0.5, 1.5, True)
    project.set_source_timeline_state(state)
    project_path = save_project(project, tmp_dir / "aprobado.creacut.json")
    monkeypatch.setattr(pipeline_module, "probe_media_duration", lambda _path: 20.0)

    ranges = pipeline_module.render_project(project_path, dry_run=True)

    assert ranges[0] == pytest.approx((0.5, 1.5))
    assert any(start <= 5.0 <= end for start, end in ranges)


def test_render_project_refuses_changed_source_by_default(
    tmp_dir, sample_script, sample_segments, monkeypatch
):
    project, _plan, _early, _recommended, video = make_edit_project(
        tmp_dir, sample_script, sample_segments
    )
    before = video.stat()
    project.source = replace(
        project.source, size_bytes=before.st_size, mtime_ns=before.st_mtime_ns
    )
    project_path = save_project(project, tmp_dir / "verificar.creacut.json")
    video.write_bytes(b"different source")
    monkeypatch.setattr(pipeline_module, "probe_media_duration", lambda _path: None)

    with pytest.raises(ValueError, match="no coincide con el snapshot"):
        pipeline_module.render_project(project_path, dry_run=True)
