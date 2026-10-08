"""Regression coverage for Electron recovery snapshots."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

from creacut.project_io import save_project
from tests.project_test_helpers import make_edit_project


PYTHON_BRIDGE_DIR = Path(__file__).parents[1] / "electron-editor" / "python"
if str(PYTHON_BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_BRIDGE_DIR))

from recovery_codec import decode_snapshot, encode_snapshot  # noqa: E402


def _javascript_normalize(value):
    """Approximate JSON.parse/stringify numeric normalization in old snapshots."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [_javascript_normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _javascript_normalize(item) for key, item in value.items()}
    return value


def test_current_snapshot_round_trip_preserves_transcript_hash(
    tmp_dir, sample_script, sample_segments
):
    project, *_ = make_edit_project(tmp_dir, sample_script, sample_segments)

    encoded = encode_snapshot(project)
    recovered = decode_snapshot(
        payload_json=encoded,
        legacy_payload=None,
        project_path=tmp_dir / "recovery.creacut.json",
    )

    assert '"start":0.0' in encoded
    assert recovered.to_dict() == project.to_dict()


def test_legacy_snapshot_repairs_only_equivalent_saved_transcript(
    tmp_dir, sample_script, sample_segments
):
    project, *_ = make_edit_project(tmp_dir, sample_script, sample_segments)
    project_path = tmp_dir / "saved.creacut.json"
    save_project(project, project_path)
    legacy = _javascript_normalize(project.to_dict())

    recovered = decode_snapshot(
        payload_json=None,
        legacy_payload=legacy,
        project_path=project_path,
    )

    assert recovered.transcript.to_dict() == project.transcript.to_dict()


def test_legacy_snapshot_rejects_a_different_transcript(
    tmp_dir, sample_script, sample_segments
):
    project, *_ = make_edit_project(tmp_dir, sample_script, sample_segments)
    project_path = tmp_dir / "saved.creacut.json"
    save_project(project, project_path)
    legacy = _javascript_normalize(copy.deepcopy(project.to_dict()))
    legacy["transcript"]["segments"][0]["words"][0]["word"] = " alterado"

    with pytest.raises(ValueError, match="transcripción diferente"):
        decode_snapshot(
            payload_json=None,
            legacy_payload=legacy,
            project_path=project_path,
        )


def test_current_snapshot_rejects_invalid_json(tmp_dir):
    with pytest.raises(ValueError, match="JSON inválido"):
        decode_snapshot(
            payload_json="{",
            legacy_payload=None,
            project_path=tmp_dir / "missing.creacut.json",
        )
