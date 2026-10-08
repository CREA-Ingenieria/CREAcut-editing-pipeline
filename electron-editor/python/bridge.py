"""Line-delimited JSON bridge between Electron and the CREAcut Python core.

The bridge owns the current :class:`EditorSession`.  It writes protocol
messages only to stdout; diagnostics and tracebacks stay inside error payloads
so Electron can present them without corrupting the stream.
"""

from __future__ import annotations

import argparse
from array import array
from concurrent.futures import Future, ThreadPoolExecutor
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
from threading import Lock
from time import monotonic
import traceback
from typing import Any, Callable
from uuid import uuid4


PROTOCOL_VERSION = 1
BACKEND_VERSION = "0.2.0-beta.1"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--repo-root", required=True)
    return parser.parse_args()


ARGS = _parse_args()
REPO_ROOT = Path(ARGS.repo_root).expanduser().resolve()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from creacut.preview import PreviewTimeline  # noqa: E402
from creacut.project import EditProject  # noqa: E402
from creacut.project_io import load_project  # noqa: E402
from creacut.config import DEFAULTS  # noqa: E402
from creacut.ui.session import EditorSession  # noqa: E402
from recovery_codec import decode_snapshot, encode_snapshot  # noqa: E402


SESSION = EditorSession()
PROJECT_UNDO: list[dict[str, Any]] = []
PROJECT_REDO: list[dict[str, Any]] = []


def _source_duration() -> float:
    project = SESSION.project
    if project is None:
        raise RuntimeError("No hay un proyecto abierto")
    duration = project.source.duration_s
    if duration is None or not math.isfinite(float(duration)) or float(duration) <= 0:
        raise ValueError("El proyecto no contiene una duración válida del video fuente")
    return float(duration)


def _resolve_document_path(stored_path: str) -> Path:
    candidate = Path(stored_path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    if SESSION.project_path is not None:
        return (SESSION.project_path.parent / candidate).resolve()
    return candidate.resolve()


def _script_snapshot() -> tuple[str | None, str | None]:
    project = SESSION.project
    if project is None:
        return None, "No hay un proyecto abierto"
    script_path = _resolve_document_path(project.script.path)
    try:
        return script_path.read_text(encoding="utf-8"), None
    except (OSError, UnicodeError) as exc:
        return None, f"No se pudo leer {script_path}: {exc}"


def _setting_value(settings: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = settings
    fallback: Any = DEFAULTS
    for key in path:
        current = current.get(key) if isinstance(current, dict) else None
        fallback = fallback.get(key) if isinstance(fallback, dict) else None
        if current is None:
            current = fallback
    return current


def _render_settings_view(project: EditProject) -> dict[str, Any]:
    settings = project.settings
    return {
        "transitionType": str(_setting_value(settings, ("transitions", "type"))),
        "crossfadeS": float(_setting_value(settings, ("transitions", "crossfade"))),
        "chromaEnabled": bool(_setting_value(settings, ("chroma", "enabled"))),
        "backgroundImage": _setting_value(settings, ("background", "image")),
        "skinCorrectionEnabled": bool(
            _setting_value(settings, ("skin_correction", "enabled"))
        ),
        "skinCorrectionStrength": float(
            _setting_value(settings, ("skin_correction", "strength"))
        ),
        "listOverlaysEnabled": bool(
            _setting_value(settings, ("overlays", "lists", "enabled"))
        ),
        "termOverlaysEnabled": bool(
            _setting_value(settings, ("overlays", "terms", "enabled"))
        ),
        "boldCardsEnabled": bool(
            _setting_value(settings, ("overlays", "bold_cards", "enabled"))
        ),
        "normalizeAudio": bool(_setting_value(settings, ("audio", "normalize"))),
    }


def _effect_ranges_view(project: EditProject) -> list[dict[str, Any]]:
    from creacut.effects import visual_effect_ranges

    return [
        {
            "id": item["id"],
            "kind": item["kind"],
            "startS": item["start_s"],
            "endS": item["end_s"],
        }
        for item in visual_effect_ranges(project.settings)
    ]


def _slides_view(project: EditProject, project_path: Path) -> dict[str, Any] | None:
    state = project.slides_state()
    return None if state is None else state.view(project_path)


def _project_view() -> dict[str, Any]:
    project = SESSION.project
    project_path = SESSION.project_path
    if project is None or project_path is None:
        raise RuntimeError("No hay un proyecto abierto")

    duration = _source_duration()
    projection = project.source_timeline(source_duration_s=duration)
    preview = PreviewTimeline.from_project(project, source_duration_s=duration)
    source_path = SESSION.source_path()
    script_text, script_error = _script_snapshot()

    return {
        "projectPath": str(project_path),
        "projectName": project_path.stem,
        "sourcePath": str(source_path) if source_path is not None else None,
        "sourceExists": bool(source_path is not None and source_path.is_file()),
        "mediaUrl": None,
        "scriptText": script_text,
        "scriptError": script_error,
        "dirty": SESSION.refresh_dirty(),
        "canUndo": bool(PROJECT_UNDO),
        "canRedo": bool(PROJECT_REDO),
        "project": project.to_dict(),
        "timeline": {
            "durationS": projection.duration_s,
            "regions": [
                {
                    "id": region.id,
                    "startS": region.start_s,
                    "endS": region.end_s,
                    "automaticKeep": region.automatic_keep,
                    "keep": region.keep,
                    "origin": region.origin,
                    "linkedSegmentIds": list(region.linked_segment_ids),
                }
                for region in projection.regions
            ],
            "cutPointsS": list(projection.cut_points_s),
        },
        "preview": {
            "durationS": preview.duration_s,
            "clips": [
                {
                    "index": clip.index,
                    "sourceStartS": clip.source_start_s,
                    "sourceEndS": clip.source_end_s,
                    "editStartS": clip.edit_start_s,
                    "editEndS": clip.edit_end_s,
                }
                for clip in preview.clips
            ],
            "cutPointsS": list(preview.cut_points_s),
        },
        "renderSettings": _render_settings_view(project),
        "effectRanges": _effect_ranges_view(project),
        "slides": _slides_view(project, project_path),
    }


def _hello(_params: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "backendVersion": BACKEND_VERSION,
        "pythonVersion": platform.python_version(),
        "pythonExecutable": sys.executable,
        "platform": platform.platform(),
    }


def _open_project(params: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(params.get("path", ""))).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"No se encontró el proyecto: {path}")
    SESSION.open(path)
    PROJECT_UNDO.clear()
    PROJECT_REDO.clear()
    return _project_view()


def _close_project(_params: dict[str, Any]) -> dict[str, Any]:
    SESSION.project = None
    SESSION.project_path = None
    SESSION.media_override = None
    SESSION.dirty = False
    SESSION._original_payload = None
    SESSION._timeline_undo.clear()
    SESSION._timeline_redo.clear()
    PROJECT_UNDO.clear()
    PROJECT_REDO.clear()
    return {"closed": True}


def _locate_media(params: dict[str, Any]) -> dict[str, Any]:
    if SESSION.project is None:
        raise RuntimeError("Primero abre un proyecto CREAcut")
    path = Path(str(params.get("path", ""))).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"No se encontró el video: {path}")
    SESSION.set_media_override(path)
    return _project_view()


def _device_status(_params: dict[str, Any]) -> dict[str, Any]:
    from creacut.transcribe import _select_whisper_device

    device, label, fp16 = _select_whisper_device()
    return {"device": device, "label": label, "fp16": fp16}


def _select_candidate(params: dict[str, Any]) -> dict[str, Any]:
    segment_id = str(params.get("segment_id", ""))
    _record_candidate_edit(
        segment_id,
        lambda: SESSION.select_candidate(segment_id, str(params.get("candidate_id", ""))),
    )
    return _project_view()


def _restore_candidate(params: dict[str, Any]) -> dict[str, Any]:
    segment_id = str(params.get("segment_id", ""))
    _record_candidate_edit(segment_id, lambda: SESSION.restore_recommended(segment_id))
    return _project_view()


def _import_slide_source(params: dict[str, Any]) -> dict[str, Any]:
    project = SESSION.project
    project_path = SESSION.project_path
    if project is None or project_path is None:
        raise RuntimeError("Primero abre un proyecto CREAcut")
    source_path = params.get("source_path")
    if not isinstance(source_path, str) or not source_path.strip():
        raise ValueError("source_path debe ser una ruta de PPTX, PDF o carpeta de imágenes")

    from creacut.slides import import_slide_source

    def operation() -> None:
        state = import_slide_source(source_path, project_path)
        project.set_slides_state(state)
        project.validate()
        SESSION.refresh_dirty()

    _record_timeline_edit(operation)
    return _project_view()


def _remove_slide_source(_params: dict[str, Any]) -> dict[str, Any]:
    project = SESSION.project
    if project is None:
        raise RuntimeError("Primero abre un proyecto CREAcut")
    from creacut.slides import SLIDES_EXTENSION_KEY

    def operation() -> None:
        project.extensions.pop(SLIDES_EXTENSION_KEY, None)
        project.validate()
        SESSION.refresh_dirty()

    _record_timeline_edit(operation)
    return _project_view()


def _recommend_slides(_params: dict[str, Any]) -> dict[str, Any]:
    project = SESSION.project
    project_path = SESSION.project_path
    source = SESSION.source_path()
    if project is None or project_path is None:
        raise RuntimeError("Primero abre un proyecto CREAcut")
    if source is None or not source.is_file():
        raise ValueError("Ubica el video fuente antes de analizar al presentador")
    state = project.slides_state()
    if state is None:
        raise ValueError("Primero importa diapositivas")
    from creacut.slides import recommend_slide_pages

    def operation() -> None:
        next_state = recommend_slide_pages(
            state,
            project_path=project_path,
            source_video=source,
            transcript_segments=project.transcript.segments,
            config=project.settings,
        )
        project.set_slides_state(next_state)
        SESSION.refresh_dirty()

    _record_timeline_edit(operation)
    return _project_view()


def _accept_slide_recommendations(_params: dict[str, Any]) -> dict[str, Any]:
    project = SESSION.project
    if project is None:
        raise RuntimeError("Primero abre un proyecto CREAcut")
    state = project.slides_state()
    if state is None:
        raise ValueError("Primero importa diapositivas")
    from creacut.slides import accept_slide_recommendations

    def operation() -> None:
        project.set_slides_state(accept_slide_recommendations(state))
        SESSION.refresh_dirty()

    _record_timeline_edit(operation)
    return _project_view()


def _update_slide_page(params: dict[str, Any]) -> dict[str, Any]:
    project = SESSION.project
    if project is None:
        raise RuntimeError("Primero abre un proyecto CREAcut")
    state = project.slides_state()
    if state is None:
        raise ValueError("Primero importa diapositivas")
    page_id = params.get("page_id")
    raw_patch = params.get("patch")
    if not isinstance(page_id, str) or not page_id:
        raise ValueError("page_id es obligatorio")
    if not isinstance(raw_patch, dict):
        raise ValueError("patch debe ser un objeto")
    name_map = {
        "startS": "start_s", "endS": "end_s", "enabled": "enabled",
        "x": "x", "y": "y", "speakerWidth": "speaker_width", "heightFraction": "height_fraction",
    }
    patch = {name_map[key]: value for key, value in raw_patch.items() if key in name_map}
    if len(patch) != len(raw_patch):
        raise ValueError("El ajuste de diapositiva contiene campos no permitidos")
    from creacut.slides import update_slide_page

    def operation() -> None:
        project.set_slides_state(update_slide_page(state, page_id, patch))
        SESSION.refresh_dirty()

    _record_timeline_edit(operation)
    return _project_view()


def _push_history(entry: dict[str, Any]) -> None:
    PROJECT_UNDO.append(entry)
    if len(PROJECT_UNDO) > 100:
        del PROJECT_UNDO[0]
    PROJECT_REDO.clear()


def _candidate_values(segment_id: str) -> dict[str, Any]:
    project = SESSION.project
    if project is None:
        raise RuntimeError("No hay un proyecto abierto")
    segment = SESSION._segment_by_id(project, segment_id)
    return {
        "selected_candidate_id": segment.selected_candidate_id,
        "source_start_s": segment.source_start_s,
        "source_end_s": segment.source_end_s,
    }


def _record_candidate_edit(segment_id: str, operation: Callable[[], Any]) -> None:
    before = _candidate_values(segment_id)
    operation()
    after = _candidate_values(segment_id)
    if before != after:
        _push_history(
            {"kind": "candidate", "segment_id": segment_id, "before": before, "after": after}
        )


def _record_timeline_edit(operation: Callable[[], Any]) -> None:
    if SESSION.project is None:
        raise RuntimeError("No hay un proyecto abierto")
    before = copy.deepcopy(SESSION.project.extensions)
    operation()
    after = copy.deepcopy(SESSION.project.extensions)
    if before != after:
        _push_history({"kind": "timeline", "before": before, "after": after})
    # The bridge owns a single history covering candidates and timeline edits.
    SESSION._timeline_undo.clear()
    SESSION._timeline_redo.clear()


_RENDER_SETTING_PATHS: dict[str, tuple[str, ...]] = {
    "transitionType": ("transitions", "type"),
    "crossfadeS": ("transitions", "crossfade"),
    "chromaEnabled": ("chroma", "enabled"),
    "backgroundImage": ("background", "image"),
    "skinCorrectionEnabled": ("skin_correction", "enabled"),
    "skinCorrectionStrength": ("skin_correction", "strength"),
    "listOverlaysEnabled": ("overlays", "lists", "enabled"),
    "termOverlaysEnabled": ("overlays", "terms", "enabled"),
    "boldCardsEnabled": ("overlays", "bold_cards", "enabled"),
    "normalizeAudio": ("audio", "normalize"),
}

_BOOLEAN_RENDER_SETTINGS = {
    "chromaEnabled",
    "skinCorrectionEnabled",
    "listOverlaysEnabled",
    "termOverlaysEnabled",
    "boldCardsEnabled",
    "normalizeAudio",
}


def _validated_render_setting(key: str, value: Any) -> Any:
    if key in _BOOLEAN_RENDER_SETTINGS:
        if not isinstance(value, bool):
            raise ValueError(f"{key} debe ser verdadero o falso")
        return value
    if key == "transitionType":
        allowed = {"cut", "dissolve", "fade_black", "wipe_left", "slide_left"}
        if not isinstance(value, str) or value not in allowed:
            raise ValueError(
                "transitionType debe ser cut, dissolve, fade_black, wipe_left o slide_left"
            )
        return value
    if key == "crossfadeS":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("crossfadeS debe ser un número")
        numeric = float(value)
        if not math.isfinite(numeric) or not 0.0 <= numeric <= 0.5:
            raise ValueError("crossfadeS debe estar entre 0 y 0.5 segundos")
        return numeric
    if key == "skinCorrectionStrength":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("skinCorrectionStrength debe ser un número")
        numeric = float(value)
        if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
            raise ValueError("skinCorrectionStrength debe estar entre 0 y 1")
        return numeric
    if key == "backgroundImage":
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("backgroundImage debe ser una ruta o null")
        path = Path(value).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"No se encontró la imagen de fondo: {path}")
        return str(path)
    raise ValueError(f"Ajuste de render desconocido: {key}")


def _set_nested_setting(settings: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    current = settings
    for key in path[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    current[path[-1]] = value


def _update_render_settings(params: dict[str, Any]) -> dict[str, Any]:
    project = SESSION.project
    if project is None:
        raise RuntimeError("No hay un proyecto abierto")
    patch = params.get("patch")
    if not isinstance(patch, dict) or not patch:
        raise ValueError("patch debe contener al menos un ajuste de render")
    unknown = sorted(set(patch) - set(_RENDER_SETTING_PATHS))
    if unknown:
        raise ValueError(f"Ajustes de render desconocidos: {', '.join(unknown)}")

    before = copy.deepcopy(project.settings)
    updated = copy.deepcopy(project.settings)
    for key, value in patch.items():
        _set_nested_setting(
            updated,
            _RENDER_SETTING_PATHS[key],
            _validated_render_setting(key, value),
        )

    project.settings = updated
    try:
        project.validate()
    except BaseException:
        project.settings = before
        raise
    if before != updated:
        _push_history({"kind": "settings", "before": before, "after": updated})
    SESSION.refresh_dirty()
    return _project_view()


def _validated_effect_interval(start: Any, end: Any) -> tuple[float, float]:
    if isinstance(start, bool) or not isinstance(start, (int, float)):
        raise ValueError("start_s debe ser un número")
    if isinstance(end, bool) or not isinstance(end, (int, float)):
        raise ValueError("end_s debe ser un número")
    duration = _source_duration()
    start_s = min(duration, max(0.0, float(start)))
    end_s = min(duration, max(0.0, float(end)))
    if end_s - start_s < 0.1:
        raise ValueError("El efecto debe durar al menos 0.1 segundos")
    return start_s, end_s


def _effect_ranges_payload(project: EditProject) -> list[dict[str, Any]]:
    from creacut.effects import visual_effect_ranges

    return copy.deepcopy(visual_effect_ranges(project.settings))


def _commit_effect_ranges(project: EditProject, ranges: list[dict[str, Any]]) -> None:
    before = copy.deepcopy(project.settings)
    updated = copy.deepcopy(project.settings)
    visual = updated.get("visual_effects")
    if not isinstance(visual, dict):
        visual = {}
        updated["visual_effects"] = visual
    visual["ranges"] = ranges
    project.settings = updated
    try:
        project.validate()
        _effect_ranges_view(project)
    except BaseException:
        project.settings = before
        raise
    if before != updated:
        _push_history({"kind": "settings", "before": before, "after": updated})
    SESSION.refresh_dirty()


def _add_effect_range(params: dict[str, Any]) -> dict[str, Any]:
    project = SESSION.project
    if project is None:
        raise RuntimeError("No hay un proyecto abierto")
    from creacut.effects import VISUAL_EFFECT_KINDS

    kind = str(params.get("kind", ""))
    if kind not in VISUAL_EFFECT_KINDS:
        raise ValueError(f"Efecto visual no compatible: {kind}")
    start_s, end_s = _validated_effect_interval(params.get("start_s"), params.get("end_s"))
    ranges = _effect_ranges_payload(project)
    ranges.append({"id": uuid4().hex, "kind": kind, "start_s": start_s, "end_s": end_s})
    _commit_effect_ranges(project, ranges)
    return _project_view()


def _update_effect_range(params: dict[str, Any]) -> dict[str, Any]:
    project = SESSION.project
    if project is None:
        raise RuntimeError("No hay un proyecto abierto")
    from creacut.effects import VISUAL_EFFECT_KINDS

    effect_id = str(params.get("effect_id", ""))
    ranges = _effect_ranges_payload(project)
    target = next((item for item in ranges if item["id"] == effect_id), None)
    if target is None:
        raise ValueError("El efecto seleccionado ya no existe")
    kind = str(params.get("kind", target["kind"]))
    if kind not in VISUAL_EFFECT_KINDS:
        raise ValueError(f"Efecto visual no compatible: {kind}")
    start_s, end_s = _validated_effect_interval(
        params.get("start_s", target["start_s"]),
        params.get("end_s", target["end_s"]),
    )
    target.update({"kind": kind, "start_s": start_s, "end_s": end_s})
    _commit_effect_ranges(project, ranges)
    return _project_view()


def _delete_effect_range(params: dict[str, Any]) -> dict[str, Any]:
    project = SESSION.project
    if project is None:
        raise RuntimeError("No hay un proyecto abierto")
    effect_id = str(params.get("effect_id", ""))
    ranges = _effect_ranges_payload(project)
    updated = [item for item in ranges if item["id"] != effect_id]
    if len(updated) == len(ranges):
        raise ValueError("El efecto seleccionado ya no existe")
    _commit_effect_ranges(project, updated)
    return _project_view()


def _apply_history(entry: dict[str, Any], state_name: str) -> None:
    project = SESSION.project
    if project is None:
        raise RuntimeError("No hay un proyecto abierto")
    state = entry[state_name]
    if entry.get("kind") == "candidate":
        segment = SESSION._segment_by_id(project, str(entry["segment_id"]))
        segment.selected_candidate_id = state["selected_candidate_id"]
        segment.source_start_s = state["source_start_s"]
        segment.source_end_s = state["source_end_s"]
    elif entry.get("kind") == "timeline":
        project.extensions = copy.deepcopy(state)
    elif entry.get("kind") == "settings":
        project.settings = copy.deepcopy(state)
    else:
        raise RuntimeError("La entrada del historial no es válida")
    project.compile_render_ranges(source_duration_s=_source_duration())
    project.validate()
    SESSION.refresh_dirty()


def _timeline_region(region_id: str):
    projection = SESSION.source_timeline(_source_duration())
    region = projection.region_by_id(region_id)
    if region is None:
        raise ValueError("La región seleccionada ya no existe")
    return region


def _timeline_mark(params: dict[str, Any]) -> dict[str, Any]:
    region = _timeline_region(str(params.get("region_id", "")))
    _record_timeline_edit(
        lambda: SESSION.mark_timeline_range(
            region.start_s,
            region.end_s,
            keep=bool(params.get("keep")),
            source_duration_s=_source_duration(),
        )
    )
    return _project_view()


def _timeline_restore(params: dict[str, Any]) -> dict[str, Any]:
    region = _timeline_region(str(params.get("region_id", "")))
    _record_timeline_edit(
        lambda: SESSION.restore_timeline_range(
            region.start_s,
            region.end_s,
            source_duration_s=_source_duration(),
        )
    )
    return _project_view()


def _timeline_split(params: dict[str, Any]) -> dict[str, Any]:
    _record_timeline_edit(
        lambda: SESSION.split_timeline(
            float(params.get("source_time_s", 0.0)),
            source_duration_s=_source_duration(),
        )
    )
    return _project_view()


def _timeline_move_boundary(params: dict[str, Any]) -> dict[str, Any]:
    _record_timeline_edit(
        lambda: SESSION.move_timeline_boundary(
            float(params.get("old_source_time_s", 0.0)),
            float(params.get("new_source_time_s", 0.0)),
            source_duration_s=_source_duration(),
        )
    )
    return _project_view()


def _timeline_undo(_params: dict[str, Any]) -> dict[str, Any]:
    if PROJECT_UNDO:
        entry = PROJECT_UNDO.pop()
        _apply_history(entry, "before")
        PROJECT_REDO.append(entry)
    return _project_view()


def _timeline_redo(_params: dict[str, Any]) -> dict[str, Any]:
    if PROJECT_REDO:
        entry = PROJECT_REDO.pop()
        _apply_history(entry, "after")
        PROJECT_UNDO.append(entry)
    return _project_view()


def _save_project(params: dict[str, Any]) -> dict[str, Any]:
    raw_path = params.get("path")
    target = None if raw_path in (None, "") else str(raw_path)
    SESSION.save(target)
    return _project_view()


def _snapshot(_params: dict[str, Any]) -> dict[str, Any]:
    if SESSION.project is None or SESSION.project_path is None:
        raise RuntimeError("No hay un proyecto abierto")
    return {
        "projectPath": str(SESSION.project_path),
        # Keep the project as an opaque Python-generated JSON string. Passing
        # the payload through JavaScript changes values such as 10.0 to 10 and
        # therefore invalidates provenance.transcript_sha256.
        "payloadJson": encode_snapshot(SESSION.project),
        "dirty": SESSION.refresh_dirty(),
    }


def _restore_snapshot(params: dict[str, Any]) -> dict[str, Any]:
    payload_json = params.get("payload_json")
    legacy_payload = params.get("payload")
    project_path = Path(str(params.get("project_path", ""))).expanduser().resolve()
    recovered = decode_snapshot(
        payload_json=payload_json,
        legacy_payload=legacy_payload,
        project_path=project_path,
    )
    if project_path.is_file():
        original_payload = load_project(project_path).to_dict()
    else:
        original_payload = {}
    SESSION.project = recovered
    SESSION.project_path = project_path
    SESSION.media_override = None
    SESSION._original_payload = original_payload
    SESSION._timeline_undo.clear()
    SESSION._timeline_redo.clear()
    PROJECT_UNDO.clear()
    PROJECT_REDO.clear()
    SESSION.refresh_dirty()
    return _project_view()


def _ffmpeg_executable() -> str:
    from creacut.media import ffmpeg_executable

    return ffmpeg_executable()


def _cache_directory(source: Path, duration_s: float) -> Path:
    stat = source.stat()
    identity = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{duration_s:.6f}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:18]
    base = SESSION.project_path.parent if SESSION.project_path else source.parent
    target = base / ".creacut-cache" / f"web-{digest}"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _thumbnail_times(duration_s: float, count: int) -> list[float]:
    bounded = max(4, min(24, count))
    if bounded == 1:
        return [duration_s / 2]
    padding = min(0.15, duration_s / 20)
    usable = max(0.0, duration_s - padding * 2)
    return [padding + usable * index / (bounded - 1) for index in range(bounded)]


def _make_thumbnails(source: Path, duration_s: float, count: int, cache: Path, warnings: list[str], deadline: float) -> list[dict[str, Any]]:
    ffmpeg = _ffmpeg_executable()
    items: list[dict[str, Any]] = []
    deadline = min(deadline, monotonic() + 60)
    for index, time_s in enumerate(_thumbnail_times(duration_s, count)):
        output = cache / f"thumb-{time_s:.6f}.jpg"
        if not output.is_file() or output.stat().st_size == 0:
            remaining = deadline - monotonic()
            if remaining <= 0:
                warnings.append("Miniaturas parciales: se alcanzó el tiempo de generación.")
                break
            temporary = cache / f"thumb-{uuid4().hex}.jpg"
            command = [
                ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{time_s:.6f}",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-vf",
                "scale=256:-2",
                "-q:v",
                "4",
                "-y",
                str(temporary),
            ]
            try:
                subprocess.run(command, check=True, capture_output=True, timeout=min(15, remaining))
                temporary.replace(output)
            except (OSError, subprocess.SubprocessError):
                warnings.append(f"No se pudo generar el fotograma de {time_s:.1f} s.")
                continue
            finally:
                temporary.unlink(missing_ok=True)
        items.append({"timeS": time_s, "path": str(output)})
    return items


def _make_waveform(source: Path, buckets: int, deadline: float) -> list[float]:
    ffmpeg = _ffmpeg_executable()
    bounded = max(160, min(1600, buckets))
    command = [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "8000",
        "-f",
        "f32le",
        "pipe:1",
    ]
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError("Se alcanzó el tiempo de generación del audio")
    completed = subprocess.run(command, check=True, capture_output=True, timeout=min(90, remaining))
    samples = array("f")
    samples.frombytes(completed.stdout[: len(completed.stdout) - len(completed.stdout) % 4])
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        return []

    chunk_size = max(1, math.ceil(len(samples) / bounded))
    peaks: list[float] = []
    for start in range(0, len(samples), chunk_size):
        chunk = samples[start : start + chunk_size]
        peaks.append(max(abs(value) for value in chunk))
    maximum = max(peaks, default=0.0)
    if maximum <= 0.0:
        return [0.0 for _ in peaks]
    return [round(min(1.0, value / maximum), 5) for value in peaks]


def _timeline_media_inputs(params: dict[str, Any]) -> dict[str, Any]:
    """Capture session-dependent values on the request thread before dispatch."""
    if SESSION.project is None:
        raise RuntimeError("Primero abre un proyecto CREAcut")
    source = SESSION.source_path()
    if source is None or not source.is_file():
        raise ValueError("El video fuente no está disponible")

    duration = _source_duration()
    return {
        **params,
        "source": str(source),
        "duration": duration,
        "cache": str(_cache_directory(source, duration)),
    }


def _timeline_media(params: dict[str, Any]) -> dict[str, Any]:
    # This worker must never read SESSION: another project may now be open.
    source = Path(params["source"])
    duration = float(params["duration"])
    sample_count = int(params.get("sample_count", 12))
    waveform_buckets = int(params.get("waveform_buckets", 900))
    cache = Path(params["cache"])
    deadline = float(params["deadline"])
    warnings: list[str] = []

    try:
        thumbnails = _make_thumbnails(source, duration, sample_count, cache, warnings, deadline)
    except (OSError, subprocess.SubprocessError) as exc:
        thumbnails = []
        warnings.append(f"No se pudieron generar las miniaturas: {exc}")

    try:
        waveform_cache = cache / f"waveform-{max(160, min(1600, waveform_buckets))}.json"
        waveform = None
        if waveform_cache.is_file():
            try:
                cached = json.loads(waveform_cache.read_text(encoding="utf-8"))
                if isinstance(cached, list) and all(isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= 1 for value in cached):
                    waveform = cached
            except (OSError, ValueError):
                pass
        if waveform is None:
            waveform = _make_waveform(source, waveform_buckets, deadline)
            temporary = cache / f"waveform-{uuid4().hex}.json"
            try:
                temporary.write_text(json.dumps(waveform), encoding="utf-8")
                temporary.replace(waveform_cache)
            except OSError:
                warnings.append("No se pudo guardar la caché de audio.")
            finally:
                temporary.unlink(missing_ok=True)
    except (OSError, subprocess.SubprocessError) as exc:
        waveform = []
        warnings.append(f"No se pudo generar la forma de onda: {exc}")

    return {
        "thumbnails": thumbnails,
        "waveform": waveform,
        "warning": " ".join(warnings) or None,
    }


def _active_slide_page(project: EditProject, time_s: float):
    """Return the enabled SlidePage covering ``time_s`` (source-time), if any."""
    state = project.slides_state()
    if state is None:
        return None
    for page in state.pages:
        if page.enabled and page.start_s is not None and page.end_s is not None and page.start_s <= time_s < page.end_s:
            return page
    return None


def _preview_effects_frame(params: dict[str, Any]) -> dict[str, Any]:
    project = SESSION.project
    project_path = SESSION.project_path
    if project is None:
        raise RuntimeError("Primero abre un proyecto CREAcut")
    source = SESSION.source_path()
    if source is None or not source.is_file():
        raise ValueError("El video fuente no está disponible")

    raw_time = params.get("source_time_s", 0.0)
    if isinstance(raw_time, bool) or not isinstance(raw_time, (int, float)):
        raise ValueError("source_time_s debe ser un número")
    duration = _source_duration()
    time_s = min(max(0.0, float(raw_time)), max(0.0, duration - 1e-3))
    chroma_enabled = bool(_setting_value(project.settings, ("chroma", "enabled")))
    active_page = _active_slide_page(project, time_s) if chroma_enabled else None
    cache = _cache_directory(source, duration)

    if active_page is not None:
        if project_path is None:
            raise RuntimeError("Primero abre un proyecto CREAcut")
        import cv2
        from creacut.chroma import extract_raw_frame, make_alpha_extractor
        from creacut.slides import resolve_project_path
        from creacut.slide_composite import load_slide_background, render_presenter_cutout

        frame = extract_raw_frame(str(source), time_s)
        height, width = frame.shape[:2]
        if width > 1280:
            preview_height = max(2, round(height * 1280 / width))
            frame = cv2.resize(frame, (1280, preview_height), interpolation=cv2.INTER_AREA)
        video_size = (frame.shape[1], frame.shape[0])

        # Split in two, unlike the generic-effects path below: the slide
        # background is stretched to the *video's* frame size, same as the
        # real render (composite_slides), and never depends on where the
        # presenter is placed. The presenter cutout never depends on where
        # it's *drawn* (only on the crop/fit fields) -- so dragging the
        # presenter around in the editor is a pure client-side reposition of
        # an already-fetched PNG, no round trip to Python per pointer move.
        # Only a fresh scrub position (different frame/pose) needs a new one.
        background_digest = hashlib.sha256(
            f"{active_page.id}:{active_page.image_path}:{video_size[0]}x{video_size[1]}".encode("utf-8")
        ).hexdigest()[:14]
        background_output = cache / f"slide-bg-{active_page.id}-{background_digest}.jpg"
        if not background_output.is_file() or background_output.stat().st_size == 0:
            image_path = resolve_project_path(active_page.image_path, project_path)
            background = load_slide_background(image_path, video_size[0], video_size[1])
            if not cv2.imwrite(str(background_output), cv2.cvtColor(background, cv2.COLOR_RGB2BGR), [int(cv2.IMWRITE_JPEG_QUALITY), 92]):
                raise OSError(f"No se pudo guardar el fondo de la diapositiva: {background_output}")

        cutout_digest = hashlib.sha256(
            json.dumps(
                {
                    "fitVersion": "fixed-camera-crop-v1",
                    "videoSize": video_size,
                    "chroma": project.settings.get("chroma", {}),
                    "cropX": active_page.crop_x, "cropY": active_page.crop_y,
                    "cropWidth": active_page.crop_width, "cropHeight": active_page.crop_height,
                    "speakerWidth": active_page.speaker_width, "heightFraction": active_page.height_fraction,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()[:14]
        cutout_output = cache / f"slide-presenter-{active_page.id}-{round(time_s * 1000):010d}-{cutout_digest}.png"
        if not cutout_output.is_file() or cutout_output.stat().st_size == 0:
            rgba = make_alpha_extractor(project.settings)(frame)
            cutout = render_presenter_cutout(active_page, rgba, video_size=video_size)
            if not cv2.imwrite(str(cutout_output), cv2.cvtColor(cutout, cv2.COLOR_RGBA2BGRA)):
                raise OSError(f"No se pudo guardar el recorte del presentador: {cutout_output}")

        return {
            "path": str(background_output),
            "presenterPath": str(cutout_output),
            "timeS": time_s,
            "slidePageId": active_page.id,
        }

    settings_digest = hashlib.sha256(
        json.dumps(project.settings, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:14]
    output = cache / f"effects-{round(time_s * 1000):010d}-{settings_digest}.jpg"

    if not output.is_file() or output.stat().st_size == 0:
        import cv2
        from creacut.chroma import extract_raw_frame, make_chroma_replacer

        frame = extract_raw_frame(str(source), time_s)
        height, width = frame.shape[:2]
        if width > 1280:
            preview_height = max(2, round(height * 1280 / width))
            frame = cv2.resize(frame, (1280, preview_height), interpolation=cv2.INTER_AREA)
        if chroma_enabled:
            frame = make_chroma_replacer(project.settings)(frame)
        from creacut.effects import apply_effects_at_source_time, visual_effect_ranges

        frame = apply_effects_at_source_time(
            frame,
            time_s,
            visual_effect_ranges(project.settings),
        )
        if bool(_setting_value(project.settings, ("skin_correction", "enabled"))):
            from creacut.skin import make_skin_corrector

            frame = make_skin_corrector(project.settings)(frame)
        if not cv2.imwrite(
            str(output),
            cv2.cvtColor(frame, cv2.COLOR_RGB2BGR),
            [int(cv2.IMWRITE_JPEG_QUALITY), 92],
        ):
            raise OSError(f"No se pudo guardar la vista previa: {output}")

    return {"path": str(output), "presenterPath": None, "timeS": time_s, "slidePageId": None}


HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "hello": _hello,
    "device_status": _device_status,
    "open_project": _open_project,
    "close_project": _close_project,
    "locate_media": _locate_media,
    "select_candidate": _select_candidate,
    "restore_candidate": _restore_candidate,
    "import_slide_source": _import_slide_source,
    "remove_slide_source": _remove_slide_source,
    "recommend_slides": _recommend_slides,
    "accept_slide_recommendations": _accept_slide_recommendations,
    "update_slide_page": _update_slide_page,
    "timeline_mark": _timeline_mark,
    "timeline_restore": _timeline_restore,
    "timeline_split": _timeline_split,
    "timeline_move_boundary": _timeline_move_boundary,
    "update_render_settings": _update_render_settings,
    "add_effect_range": _add_effect_range,
    "update_effect_range": _update_effect_range,
    "delete_effect_range": _delete_effect_range,
    "timeline_undo": _timeline_undo,
    "timeline_redo": _timeline_redo,
    "save_project": _save_project,
    "snapshot": _snapshot,
    "restore_snapshot": _restore_snapshot,
    "timeline_media": _timeline_media,
    "preview_effects_frame": _preview_effects_frame,
}


_RESPONSE_LOCK = Lock()


def _respond(payload: dict[str, Any]) -> None:
    with _RESPONSE_LOCK:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n")
        sys.stdout.flush()


def _respond_media(request_id: Any, future: Future) -> None:
    try:
        _respond({"id": request_id, "ok": True, "result": future.result()})
    except Exception as exc:
        _respond({"id": request_id, "ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}})


def main() -> int:
    media_workers = ThreadPoolExecutor(max_workers=2, thread_name_prefix="timeline-media")
    media_pending: dict[str, Future] = {}
    for raw_line in sys.stdin:
        request_id: Any = None
        try:
            request = json.loads(raw_line)
            if not isinstance(request, dict):
                raise ValueError("La solicitud debe ser un objeto JSON")
            request_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})
            if not isinstance(method, str) or method not in HANDLERS:
                raise ValueError(f"Método desconocido: {method!r}")
            if not isinstance(params, dict):
                raise ValueError("params debe ser un objeto")
            if method == "timeline_media":
                snapshot = _timeline_media_inputs(params)
                key = json.dumps(snapshot, sort_keys=True)
                media_pending = {key: future for key, future in media_pending.items() if not future.done()}
                future = media_pending.get(key)
                if future is None:
                    # Include time queued behind older projects in the budget.
                    snapshot["deadline"] = monotonic() + 150
                    future = media_workers.submit(_timeline_media, snapshot)
                    media_pending[key] = future
                future.add_done_callback(lambda done, rid=request_id: _respond_media(rid, done))
                continue
            result = HANDLERS[method](params)
            _respond({"id": request_id, "ok": True, "result": result})
        except BaseException as exc:
            _respond(
                {
                    "id": request_id,
                    "ok": False,
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc) or type(exc).__name__,
                        "detail": traceback.format_exc(limit=8),
                    },
                }
            )
    media_workers.shutdown(wait=False, cancel_futures=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
