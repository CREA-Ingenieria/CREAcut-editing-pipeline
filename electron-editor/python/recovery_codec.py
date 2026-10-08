"""Pure recovery serialization used by the Electron bridge.

Keeping this module free of Electron/session state lets us verify recovery
without starting the long-running line-delimited JSON bridge.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from creacut.project import EditProject, TranscriptSnapshot
from creacut.project_io import load_project


def encode_snapshot(project: EditProject) -> str:
    """Encode in Python so integral floats retain the representation hashed by CREAcut."""
    return json.dumps(
        project.to_dict(),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def decode_snapshot(
    *,
    payload_json: Any,
    legacy_payload: Any,
    project_path: Path,
) -> EditProject:
    """Validate a current or legacy recovery payload and return the project."""
    if isinstance(payload_json, str):
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError as exc:
            raise ValueError("La recuperación contiene un JSON inválido") from exc
    elif isinstance(legacy_payload, dict):
        # Old snapshots crossed JavaScript as objects. JSON.stringify changed
        # values such as 10.0 to 10, invalidating transcript_sha256 even though
        # the transcript was semantically unchanged.
        if not project_path.is_file():
            raise ValueError(
                "La recuperación antigua no puede verificarse porque el proyecto guardado no existe"
            )
        original = load_project(project_path)
        recovered_transcript = TranscriptSnapshot.from_dict(
            legacy_payload.get("transcript", {})
        )
        if recovered_transcript.to_dict() != original.transcript.to_dict():
            raise ValueError(
                "La recuperación pertenece a una transcripción diferente del proyecto guardado"
            )
        payload = copy.deepcopy(legacy_payload)
        provenance = payload.get("provenance")
        if not isinstance(provenance, dict):
            raise ValueError("La recuperación no contiene procedencia válida")
        provenance["transcript_sha256"] = hashlib.sha256(
            json.dumps(
                recovered_transcript.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
    else:
        raise ValueError("La recuperación no contiene un proyecto válido")

    if not isinstance(payload, dict):
        raise ValueError("La recuperación no contiene un objeto de proyecto")
    return EditProject.from_dict(payload)
