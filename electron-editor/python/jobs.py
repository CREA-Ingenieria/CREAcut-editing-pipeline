"""Isolated long-running analysis, render and batch jobs for Electron."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import sys
import traceback
from typing import Any


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("analysis", "render", "batch"))
    parser.add_argument("--repo-root", required=True)
    return parser.parse_args()


ARGS = _args()
REPO_ROOT = Path(ARGS.repo_root).expanduser().resolve()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from creacut.config import load_config  # noqa: E402
from creacut.pipeline import generate_edit_project, render_project  # noqa: E402
from creacut.project_io import save_project  # noqa: E402
from creacut.transcribe import _select_whisper_device  # noqa: E402


def emit(kind: str, **payload: Any) -> None:
    sys.__stdout__.write(
        json.dumps({"kind": kind, **payload}, ensure_ascii=False, allow_nan=False) + "\n"
    )
    sys.__stdout__.flush()


class ProgressStream:
    def __init__(self) -> None:
        self.pending = ""

    def write(self, text: str) -> int:
        value = str(text)
        self.pending += value
        lines = self.pending.splitlines(keepends=True)
        self.pending = ""
        for line in lines:
            if line.endswith(("\n", "\r")):
                message = line.strip()
                if message:
                    emit("progress", message=message)
            else:
                self.pending = line
        return len(value)

    def flush(self) -> None:
        message = self.pending.strip()
        self.pending = ""
        if message:
            emit("progress", message=message)


def _analysis(params: dict[str, Any]) -> dict[str, Any]:
    video = Path(str(params["video_path"])).expanduser().resolve()
    script = Path(str(params["script_path"])).expanduser().resolve()
    output = Path(str(params["project_path"])).expanduser().resolve()
    config_raw = params.get("config_path")
    background_raw = params.get("background_image")

    if not video.is_file():
        raise ValueError(f"No se encontró el video: {video}")
    if not script.is_file():
        raise ValueError(f"No se encontró el guion: {script}")
    if output.exists():
        if not bool(params.get("allow_replace")):
            raise ValueError(f"Ya existe un proyecto en: {output}")
        if not output.is_file():
            raise ValueError(f"La ruta de proyecto no es un archivo reemplazable: {output}")
        output.unlink()

    config_path = None if not config_raw else Path(str(config_raw)).expanduser().resolve()
    background = None if not background_raw else Path(str(background_raw)).expanduser().resolve()
    if config_path is not None and not config_path.is_file():
        raise ValueError(f"No se encontró la configuración: {config_path}")
    if background is not None and not background.is_file():
        raise ValueError(f"No se encontró el fondo: {background}")

    output.parent.mkdir(parents=True, exist_ok=True)
    config = load_config(str(config_path) if config_path else None)
    if background is not None:
        config["background"]["image"] = str(background)

    device, label, fp16 = _select_whisper_device()
    emit("device", device=device, label=label, fp16=fp16)
    emit("progress", message="Preparando análisis de video y guion…")
    stream = ProgressStream()
    with redirect_stdout(stream):
        generate_edit_project(
            str(video),
            script=str(script),
            config=config,
            verbose=True,
            project_output=str(output),
        )
        stream.flush()
    return {"projectPath": str(output)}


def _render(params: dict[str, Any]) -> dict[str, Any]:
    project = Path(str(params["project_path"])).expanduser().resolve()
    output = Path(str(params["output_path"])).expanduser().resolve()
    if not project.is_file():
        raise ValueError(f"No se encontró el proyecto: {project}")
    output.parent.mkdir(parents=True, exist_ok=True)
    emit("progress", message="Preparando render final…")
    stream = ProgressStream()
    with redirect_stdout(stream):
        result = render_project(project, output=output, verbose=True)
        stream.flush()
    return {"outputPath": str(result)}


def _unique_folder(target: Path) -> Path:
    if not target.exists():
        return target
    for index in range(2, 10_000):
        candidate = target.with_name(f"{target.name}-{index}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"No se pudo elegir una carpeta disponible para {target.name}")


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _batch_paths(params: dict[str, Any], key: str, label: str) -> list[Path]:
    raw_paths = params.get(key)
    if not isinstance(raw_paths, list) or not raw_paths:
        raise ValueError(f"Selecciona al menos un {label}")
    paths = [Path(str(raw)).expanduser().resolve() for raw in raw_paths]
    if len({_path_key(path) for path in paths}) != len(paths):
        raise ValueError(f"La selección contiene {label}s repetidos")
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise ValueError(f"No se encontró el {label}: {missing[0]}")
    return paths


def _batch(params: dict[str, Any]) -> dict[str, Any]:
    videos = _batch_paths(params, "video_paths", "video")
    scripts = _batch_paths(params, "script_paths", "guion")
    output_root = Path(str(params.get("output_directory", ""))).expanduser().resolve()
    if len(videos) != len(scripts):
        raise ValueError(
            "La cantidad de videos y guiones debe ser igual "
            f"({len(videos)} videos, {len(scripts)} guiones)"
        )
    if not output_root.is_dir():
        raise ValueError(f"La carpeta base no existe: {output_root}")

    generated: list[str] = []
    failed: list[dict[str, str]] = []
    matches: list[dict[str, Any]] = []
    remaining_scripts = list(scripts)
    total = len(videos)
    device, label, fp16 = _select_whisper_device()
    emit("device", device=device, label=label, fp16=fp16)

    for index, video in enumerate(videos):
        emit(
            "progress",
            message=(
                f"[{index + 1}/{total}] Identificando el guion de {video.name} "
                f"entre {len(remaining_scripts)} candidato(s)…"
            ),
            itemIndex=index,
            itemTotal=total,
        )
        try:
            if not remaining_scripts:
                raise ValueError("No quedan guiones disponibles para identificar")
            folder = _unique_folder(output_root / video.stem)
            folder.mkdir(parents=True)
            copied_video = folder / video.name
            shutil.copy2(video, copied_video)
            project_path = folder / f"{video.stem}.creacut.json"
            stream = ProgressStream()
            with redirect_stdout(stream):
                project = generate_edit_project(
                    str(copied_video),
                    script_candidates=remaining_scripts,
                    config=load_config(None),
                    verbose=True,
                )
                stream.flush()

            selected_script = Path(project.script_path).resolve()
            selected_key = _path_key(selected_script)
            if selected_key not in {_path_key(path) for path in remaining_scripts}:
                raise RuntimeError("El pipeline seleccionó un guion fuera del lote")
            copied_script = folder / selected_script.name
            shutil.copy2(selected_script, copied_script)
            project.script = replace(project.script, path=str(copied_script))
            save_project(project, project_path)
            remaining_scripts = [
                path for path in remaining_scripts if _path_key(path) != selected_key
            ]

            score = project.script.identification_score
            generated.append(str(project_path))
            matches.append(
                {
                    "videoPath": str(video),
                    "scriptPath": str(selected_script),
                    "score": score,
                    "projectPath": str(project_path),
                }
            )
            emit(
                "progress",
                message=(
                    f"[{index + 1}/{total}] {video.name} → {selected_script.name} "
                    f"(coincidencia {score:.1%})"
                    if score is not None
                    else f"[{index + 1}/{total}] {video.name} → {selected_script.name}"
                ),
                itemIndex=index,
                itemTotal=total,
            )
        except BaseException as exc:
            failed.append({"video": str(video), "error": str(exc) or type(exc).__name__})
            emit(
                "progress",
                message=f"[{index + 1}/{total}] Error en {video.name}: {exc}",
                itemIndex=index,
                itemTotal=total,
            )

    return {
        "generatedProjects": generated,
        "matches": matches,
        "failed": failed,
        "unmatchedScripts": [str(path) for path in remaining_scripts],
    }


def main() -> int:
    try:
        params = json.loads(sys.stdin.read() or "{}")
        if not isinstance(params, dict):
            raise ValueError("Los parámetros del trabajo deben ser un objeto")
        if ARGS.kind == "analysis":
            result = _analysis(params)
        elif ARGS.kind == "render":
            result = _render(params)
        else:
            result = _batch(params)
        emit("completed", result=result)
        return 0
    except BaseException as exc:
        emit(
            "failed",
            error=str(exc) or type(exc).__name__,
            detail=traceback.format_exc(limit=12),
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
