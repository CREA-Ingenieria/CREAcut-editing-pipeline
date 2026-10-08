"""Create a self-contained CREAcut editor demo without running Whisper.

The generated transcript and alignment evidence are deterministic fixtures.  The
MP4 is produced locally by :mod:`creacut.demo_media`, so this script needs no
network access, microphone, source recording, or external ``ffmpeg`` command.

Run from the repository root::

    python scripts/create_editor_demo.py --output-dir demo_editor
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


# Direct execution places ``scripts`` (rather than the repository root) first on
# sys.path.  Add the root so the command works before an editable installation.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from creacut.common import GuionSentence, MatchCandidate, normalize
from creacut.config import DEFAULTS
from creacut.decisions import (
    AlignmentCandidate,
    AlignmentPlan,
    CandidateRejection,
    RetakeDecision,
    SentenceDecision,
    candidate_id_for,
)
from creacut.preview import build_preview_timeline
from creacut.project import EditProject
from creacut.project_io import load_project, save_project


VIDEO_FILENAME = "creacut-demo.mp4"
SCRIPT_FILENAME = "creacut-demo-guion.md"
PROJECT_FILENAME = "creacut-demo.creacut.json"
SOURCE_DURATION_S = 12.0

FIRST_SENTENCE = (
    "CREAcut puede proponer más de una toma para una oración."
)
SECOND_SENTENCE = (
    "Después puedes elegir la toma que prefieras y guardar el proyecto."
)

SCRIPT_CONTENT = (
    "---\n"
    "title: Demostración del editor CREAcut\n"
    "---\n"
    f"{FIRST_SENTENCE} {SECOND_SENTENCE}\n"
)


@dataclass(frozen=True)
class DemoArtifacts:
    """Paths and preview metadata produced by :func:`create_editor_demo`."""

    output_dir: Path
    video_path: Path
    script_path: Path
    project_path: Path
    preview_duration_s: float
    preview_clip_count: int


class DemoOutputConflictError(FileExistsError):
    """Existing files prevent a safe, implicit demo regeneration."""


def _timed_words(text: str, start_s: float, end_s: float) -> list[dict]:
    """Distribute deterministic mock word timestamps over a transcript span."""
    tokens = text.split()
    step = (end_s - start_s) / len(tokens)
    words: list[dict] = []
    for index, token in enumerate(tokens):
        word_start = start_s + index * step
        word_end = end_s if index == len(tokens) - 1 else start_s + (index + 1) * step
        words.append({
            "word": f" {token}",
            "start": round(word_start, 6),
            "end": round(word_end, 6),
        })
    return words


def build_demo_transcript() -> dict:
    """Return the simulated post-Whisper snapshot used by the editor demo."""
    take_a_text = "CREAcut puede proponer una toma para una oración."
    take_b_text = FIRST_SENTENCE
    final_text = SECOND_SENTENCE
    return {
        "text": f"{take_a_text} {take_b_text} {final_text}",
        "segments": [
            {
                "start": 0.75,
                "end": 3.25,
                "text": f" {take_a_text}",
                "no_speech_prob": 0.04,
                "words": _timed_words(take_a_text, 0.75, 3.25),
            },
            {
                "start": 4.75,
                "end": 7.25,
                "text": f" {take_b_text}",
                "no_speech_prob": 0.02,
                "words": _timed_words(take_b_text, 4.75, 7.25),
            },
            {
                "start": 8.75,
                "end": 11.25,
                "text": f" {final_text}",
                "no_speech_prob": 0.03,
                "words": _timed_words(final_text, 8.75, 11.25),
            },
            {
                "start": 11.25,
                "end": SOURCE_DURATION_S,
                "text": "",
                "no_speech_prob": 1.0,
                "words": [],
            },
        ],
        "metadata": {
            "language": "es",
            "demo": True,
            "note": "Transcripción simulada; Whisper no se ejecutó.",
        },
    }


def _match(
    sentence: GuionSentence,
    *,
    start_s: float,
    end_s: float,
    score: float,
    transcript_text: str,
    transcript_segment_idx: int,
    refinements: tuple[str, ...] = (),
) -> MatchCandidate:
    return MatchCandidate(
        sentence=sentence,
        start=start_s,
        end=end_s,
        score=score,
        transcript_text=transcript_text,
        segment_start_idx=transcript_segment_idx,
        segment_end_idx=transcript_segment_idx,
        refinements=refinements,
    )


def build_demo_alignment_plan() -> AlignmentPlan:
    """Build observable decisions with one editable retake choice."""
    first = GuionSentence(0, 0, FIRST_SENTENCE, normalize(FIRST_SENTENCE))
    second = GuionSentence(0, 1, SECOND_SENTENCE, normalize(SECOND_SENTENCE))

    take_a = _match(
        first,
        start_s=0.75,
        end_s=3.25,
        score=0.84,
        transcript_text="CREAcut puede proponer una toma para una oración.",
        transcript_segment_idx=0,
        refinements=("demo_take_a",),
    )
    take_b = _match(
        first,
        start_s=4.75,
        end_s=7.25,
        score=0.96,
        transcript_text=FIRST_SENTENCE,
        transcript_segment_idx=1,
        refinements=("demo_take_b", "last_strong_retake"),
    )
    final_take = _match(
        second,
        start_s=8.75,
        end_s=11.25,
        score=0.93,
        transcript_text=SECOND_SENTENCE,
        transcript_segment_idx=2,
        refinements=("demo_final_take",),
    )

    take_a_id = candidate_id_for(take_a)
    take_b_id = candidate_id_for(take_b)
    final_take_id = candidate_id_for(final_take)

    decisions = (
        SentenceDecision(
            sentence=first,
            candidates=(
                AlignmentCandidate.from_match(take_a),
                AlignmentCandidate.from_match(take_b),
            ),
            selected_candidate_id=take_b_id,
            selection_reason="unique_best",
            previous_selection_end_s=0.0,
            chronological_floor_s=-0.5,
            retake_floor_s=4.75,
            strict_floor_s=4.25,
            applied_floor_s=4.25,
            rejected_candidates=(
                CandidateRejection(take_a_id, ("before_retake_floor",)),
            ),
        ),
        SentenceDecision(
            sentence=second,
            candidates=(AlignmentCandidate.from_match(final_take),),
            selected_candidate_id=final_take_id,
            selection_reason="unique_best",
            previous_selection_end_s=7.25,
            chronological_floor_s=6.75,
            retake_floor_s=4.75,
            strict_floor_s=6.75,
            applied_floor_s=6.75,
        ),
    )
    retake = RetakeDecision(
        paragraph_idx=0,
        candidate_ids=(take_a_id, take_b_id),
        good_candidate_ids=(take_a_id, take_b_id),
        strong_candidate_ids=(take_a_id, take_b_id),
        floor_candidate_id=take_b_id,
        floor_s=4.75,
        reason="last_strong_candidate",
    )
    return AlignmentPlan(
        decisions=decisions,
        retakes=(retake,),
        selected_matches=(take_b, final_take),
        match_threshold=0.55,
        good_match_threshold=0.60,
    )


def _create_demo_video(path: Path, *, overwrite: bool) -> Path:
    """Late import keeps project-fixture helpers usable without media tooling."""
    from creacut.demo_media import create_demo_video

    return create_demo_video(path, overwrite=overwrite)


def _validated_artifacts(
    destination: Path,
    video_path: Path,
    script_path: Path,
    project_path: Path,
) -> DemoArtifacts:
    """Load the saved demo and verify it still matches this fixture version."""
    if script_path.read_text(encoding="utf-8") != SCRIPT_CONTENT:
        raise DemoOutputConflictError(
            f"El guion existente no es el demo esperado: {script_path}"
        )
    project = load_project(project_path)
    script_digest = hashlib.sha256(script_path.read_bytes()).hexdigest()
    source_digest = hashlib.sha256(video_path.read_bytes()).hexdigest()
    demo_extension = project.extensions.get("demo")
    expected_plan = build_demo_alignment_plan()
    expected_first = expected_plan.decisions[0]
    expected_retake = expected_plan.retakes[0]
    decisions_match = (
        len(project.segments) == 2
        and tuple(candidate.id for candidate in project.segments[0].candidates)
        == tuple(candidate.id for candidate in expected_first.candidates)
        and project.segments[0].selected_candidate_id
        == expected_first.selected_candidate_id
        and project.segments[0].automatic_selection.selection_reason
        == expected_first.selection_reason
        and len(project.retake_decisions) == 1
        and project.retake_decisions[0].strong_candidate_ids
        == expected_retake.strong_candidate_ids
    )
    if (
        project.project_id != "creacut-editor-demo-v1"
        or project.source.path != str(video_path)
        or project.script.path != str(script_path)
        or project.script.sha256 != script_digest
        or project.source.size_bytes != video_path.stat().st_size
        or project.source.duration_s != SOURCE_DURATION_S
        or not isinstance(demo_extension, dict)
        or demo_extension.get("version") != 1
        or demo_extension.get("source_sha256") != source_digest
        or not decisions_match
    ):
        raise DemoOutputConflictError(
            f"El conjunto existente no coincide con el demo CREAcut v1: {destination}"
        )
    timeline = build_preview_timeline(project)
    if timeline.is_empty or len(timeline.clips) != 2:
        raise DemoOutputConflictError(
            "El proyecto existente no contiene los dos clips demo esperados"
        )
    return DemoArtifacts(
        output_dir=destination,
        video_path=video_path,
        script_path=script_path,
        project_path=project_path,
        preview_duration_s=timeline.duration_s,
        preview_clip_count=len(timeline.clips),
    )


def create_editor_demo(
    output_dir: str | Path,
    *,
    force: bool = False,
) -> DemoArtifacts:
    """Generate the local MP4, Markdown script, and editable project JSON."""
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)

    requested_video_path = (destination / VIDEO_FILENAME).resolve()
    script_path = (destination / SCRIPT_FILENAME).resolve()
    project_path = (destination / PROJECT_FILENAME).resolve()
    targets = (requested_video_path, script_path, project_path)
    non_files = [path for path in targets if path.exists() and not path.is_file()]
    if non_files:
        raise DemoOutputConflictError(
            "Una ruta de salida existe pero no es un archivo: "
            + ", ".join(str(path) for path in non_files)
        )
    existing = [path for path in targets if path.is_file()]
    if existing and not force:
        if len(existing) == len(targets):
            try:
                return _validated_artifacts(
                    destination,
                    requested_video_path,
                    script_path,
                    project_path,
                )
            except (OSError, ValueError) as exc:
                raise DemoOutputConflictError(
                    "La carpeta contiene archivos demo incompatibles. Usa "
                    "--force para reemplazar exclusivamente los tres archivos "
                    f"del demo, o elige otro --output-dir: {destination}"
                ) from exc
        raise DemoOutputConflictError(
            "La carpeta ya contiene parte de los archivos del demo. Usa "
            "--force para reemplazar exclusivamente esos destinos, o elige "
            f"otro --output-dir: {destination}"
        )

    video_path = Path(
        _create_demo_video(requested_video_path, overwrite=force)
    ).resolve()

    script_path.write_text(SCRIPT_CONTENT, encoding="utf-8", newline="\n")
    script_sha256 = hashlib.sha256(script_path.read_bytes()).hexdigest()
    source_stat = video_path.stat()

    settings = copy.deepcopy(DEFAULTS)
    # Keep the two selected sentences as visibly separate preview clips.
    settings["retakes"]["merge_gap"] = 0.25
    settings["retakes"]["pad_start"] = 0.0
    settings["retakes"]["pad_end"] = 0.0

    project = EditProject.from_alignment_plan(
        build_demo_alignment_plan(),
        source_video=video_path,
        script_path=script_path,
        transcript=build_demo_transcript(),
        settings=settings,
        script_score=1.0,
        project_id="creacut-editor-demo-v1",
        source_duration_s=SOURCE_DURATION_S,
        source_size_bytes=source_stat.st_size,
        script_sha256=script_sha256,
        generator_version="0.1.0-demo",
        created_at_utc="2026-08-20T00:00:00+00:00",
    )
    project.extensions["demo"] = {
        "version": 1,
        "whisper_was_run": False,
        "source_sha256": hashlib.sha256(video_path.read_bytes()).hexdigest(),
        "video_sections": [
            {"label": "Toma A", "start_s": 0.0, "end_s": 4.0},
            {"label": "Toma B", "start_s": 4.0, "end_s": 8.0},
            {"label": "Final", "start_s": 8.0, "end_s": 12.0},
        ],
    }
    save_project(project, project_path)

    # Treat persistence and preview compilation as part of generation: a demo
    # is only reported as ready if the exact saved file survives both checks.
    return _validated_artifacts(
        destination,
        video_path,
        script_path,
        project_path,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Crea un video y un proyecto de demostración para el editor de "
            "CREAcut sin ejecutar Whisper."
        )
    )
    parser.add_argument(
        "--output-dir",
        default="demo_editor",
        help="Directorio de salida (predeterminado: demo_editor)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reemplaza los tres archivos demo si ya existen.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = create_editor_demo(
        args.output_dir,
        force=args.force,
    )
    print("\nDemostración de CREAcut lista.")
    print(f"Video:   {artifacts.video_path}")
    print(f"Guion:   {artifacts.script_path}")
    print(f"Proyecto: {artifacts.project_path}")
    print(
        "Preview: "
        f"{artifacts.preview_clip_count} cortes, "
        f"{artifacts.preview_duration_s:.2f} s"
    )
    print("\nÁbrela con:")
    print(f'python -m creacut.ui "{artifacts.project_path}"')
    print("\nTambién puedes usar:")
    print(f'creacut-editor "{artifacts.project_path}"')
    print(
        "\nNota: este demo prueba preview, tomas y guardado; no prueba "
        "Whisper, la alineación real ni el render final."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
