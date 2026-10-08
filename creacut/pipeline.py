"""Pipeline orchestrator — wires all stages together."""

import hashlib
import json
import os
import sys
import copy
from pathlib import Path

from .align import build_alignment_plan, merge_ranges, pad_ranges, split_on_word_gaps
from .bookend import wrap_with_bookends
from .common import find_script_files, guion_sentences, parse_guion
from .cut import build_cut_clip, export_clip, transition_overlap
from .detect_bold import detect_bold_cards
from .detect_lists import detect_lists
from .detect_terms import build_term_overlays, detect_terms
from .extract_items import extract_list_items
from .identify import identify_guion
from .media import probe_media_duration
from .normalize import normalize_audio
from .overlay import composite_equations, composite_overlays, composite_terms
from .project import EditProject
from .project_io import load_project, save_project
from .remap import remap_to_cut
from .transcribe import patch_ghost_words, transcribe


def _path_key(path: str | Path) -> str:
    return os.path.normcase(str(Path(path).resolve()))


def _validate_output_paths(
    source_video: Path,
    script_path: Path,
    *,
    output_video: Path | None,
    json_output: str | None,
    project_output: str | None,
) -> None:
    """Reject output collisions before any user file can be overwritten."""
    inputs = {
        _path_key(source_video): "source video",
        _path_key(script_path): "script",
        _path_key(source_video.with_suffix(".whisper.json")): "Whisper cache",
    }
    outputs = [
        ("output video", output_video),
        ("alignment JSON", json_output),
        ("editable project", project_output),
    ]
    seen_outputs: dict[str, str] = {}
    for role, path in outputs:
        if path is None:
            continue
        key = _path_key(path)
        if key in inputs:
            sys.exit(f"Error: {role} would overwrite the {inputs[key]}: {path}")
        if key in seen_outputs:
            sys.exit(
                f"Error: {role} and {seen_outputs[key]} use the same path: {path}"
            )
        seen_outputs[key] = role


def process_video(
    video_path: str,
    script: str | None = None,
    output: str | None = None,
    config: dict | None = None,
    dry_run: bool = False,
    verbose: bool = False,
    json_output: str | None = None,
    project_output: str | None = None,
    project_only: bool = False,
    script_candidates: list[str | Path] | None = None,
) -> EditProject | None:
    if config is None:
        from .config import DEFAULTS
        config = DEFAULTS

    vp = Path(video_path).resolve()
    if not vp.exists():
        sys.exit(f"Error: file not found: {vp}")

    # ── Stage 1: Transcription ───────────────────────────────────────
    print("=== Stage 1: Transcription ===")
    result = transcribe(vp, config, verbose=verbose)
    segments = result["segments"]
    print(f"  {len(segments)} segments, {len(result['text'])} chars")

    # Stage 1b: Ghost-word patching
    segments, _patched = patch_ghost_words(vp, config=config, verbose=verbose)
    if _patched:
        result["segments"] = segments

    # ── Stage 2: Script identification ───────────────────────────────
    print("\n=== Stage 2: Script Identification ===")
    if script:
        gp = Path(script).resolve()
        gs = 1.0
        print(f"  Provided: {gp.name}")
    elif script_candidates is not None:
        gfiles = [Path(candidate).expanduser().resolve() for candidate in script_candidates]
        missing = [path for path in gfiles if not path.is_file()]
        if missing:
            raise ValueError(f"Script candidate not found: {missing[0]}")
        if not gfiles:
            raise ValueError("At least one script candidate is required")
        print(f"  Searching {len(gfiles)} selected scripts...")
        gp, gs = identify_guion(segments, gfiles, verbose=verbose)
        print(f"  → {gp.name}  (score {gs:.3f})")
    else:
        scripts_dir = config.get("scripts", {}).get("directory")
        if scripts_dir:
            gfiles = find_script_files(scripts_dir)
            print(f"  Searching {len(gfiles)} scripts in {scripts_dir}...")
            gp, gs = identify_guion(segments, gfiles, verbose=verbose)
            print(f"  → {gp.name}  (score {gs:.3f})")
        else:
            sys.exit(
                "Error: no script provided. Use --script <path> or set "
                "scripts.directory in creacut.yml for auto-identification."
            )
    gp = Path(gp).resolve()

    # Project-only analysis must not depend on render output settings.
    op = None
    if not project_only:
        if output:
            op = Path(output).resolve()
        else:
            out_dir = (
                Path(config["output"]["directory"])
                if config["output"]["directory"]
                else vp.parent
            )
            suffix = config["output"]["suffix"]
            op = out_dir / f"{vp.stem}{suffix}.mp4"

    _validate_output_paths(
        vp,
        gp,
        output_video=op,
        json_output=json_output,
        project_output=project_output,
    )

    paragraphs = parse_guion(gp)
    sents = guion_sentences(paragraphs)
    print(f"  {len(paragraphs)} paragraphs, {len(sents)} sentences")

    # ── Stage 3: Alignment ───────────────────────────────────────────
    print("\n=== Stage 3: Alignment ===")
    alignment_plan = build_alignment_plan(sents, segments, config, verbose=verbose)
    selected = list(alignment_plan.selected_matches)

    project = None
    if project_output or project_only:
        project_transcript = dict(result)
        project_transcript["segments"] = segments
        project_transcript["text"] = " ".join(
            segment["text"].strip()
            for segment in segments
            if segment["text"].strip()
        )
        source_stat = vp.stat()
        script_sha256 = hashlib.sha256(gp.read_bytes()).hexdigest()
        project = EditProject.from_alignment_plan(
            alignment_plan,
            source_video=vp,
            script_path=gp,
            transcript=project_transcript,
            settings=config,
            script_score=gs,
            source_duration_s=probe_media_duration(vp),
            source_size_bytes=source_stat.st_size,
            source_mtime_ns=source_stat.st_mtime_ns,
            script_sha256=script_sha256,
        )

        if project_output:
            saved_project = save_project(project, project_output)
            print(f"  Project → {saved_project}")

    if project_only and not json_output:
        print("\n[project-only — no range compilation, content detection, or video exported]")
        return project

    raw_ranges = [(m.start, m.end) for m in selected]
    clean = merge_ranges(raw_ranges, config)
    raw_dur = segments[-1]["end"] if segments else 0.0
    clean = pad_ranges(clean, raw_dur + 5.0, config)
    clean = split_on_word_gaps(clean, segments, config)
    if clean:
        s, e = clean[-1]
        clean[-1] = (s, min(raw_dur + 5.0, e + 1.0))
    edited_dur = sum(e - s for s, e in clean)
    good_thresh = config["retakes"]["good_match_threshold"]
    n_retakes = sum(
        1
        for decision in alignment_plan.decisions
        if decision.selected_candidate_id is not None
        and len([
            candidate
            for candidate in decision.candidates
            if candidate.score >= good_thresh
        ]) > 1
    )
    print(f"\n  {len(clean)} segment(s), {n_retakes} retake(s) detected")
    print(f"  {raw_dur:.1f}s raw → {edited_dur:.1f}s edited")
    for i, (s, e) in enumerate(clean):
        print(f"    [{i + 1}] {s:.1f}s – {e:.1f}s ({e - s:.1f}s)")

    if json_output:
        data = {
            "script": str(gp),
            "script_score": gs,
            "matches": [
                {"sentence": m.sentence.text, "start": m.start,
                 "end": m.end, "score": m.score}
                for m in selected
            ],
            "clean_ranges": clean,
            "raw_duration": raw_dur,
            "edited_duration": edited_dur,
        }
        Path(json_output).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  Alignment → {json_output}")

    if project_only:
        print("\n[project-only — no content detection or video exported]")
        return project

    # ── Stage 4: Remap timestamps ────────────────────────────────────
    print("\n=== Stage 4: Remap to Cut Timeline ===")
    xfade = transition_overlap(config)
    cut_sentences = remap_to_cut(selected, clean, xfade_dur=xfade, verbose=verbose)
    print(f"  {len(cut_sentences)} sentences mapped to cut timeline")

    # ── Stages 5–6: Content detection ────────────────────────────────
    overlays = []
    term_overlays = []
    eq_overlays = []
    lists_enabled = config["overlays"]["lists"]["enabled"]
    terms_enabled = config["overlays"]["terms"]["enabled"]
    bold_enabled = config["overlays"]["bold_cards"]["enabled"]
    eq_enabled = config["overlays"]["equations"]["enabled"]

    if lists_enabled:
        print("\n=== Stage 5: List Detection ===")
        detections = detect_lists(sents, verbose=verbose)
        print(f"  {len(detections)} list(s) detected")
        if detections:
            print("\n=== Stage 6: List Item Extraction ===")
            overlays = extract_list_items(
                detections, sents, gp, cut_sentences,
                config=config, segments=segments, clean_ranges=clean,
                verbose=verbose,
            )
            print(f"  {len(overlays)} overlay(s) ready")

    # module_slug: in standalone mode, derive from script filename stem
    module_slug = gp.stem

    if terms_enabled:
        vocab_file = config["overlays"]["terms"].get("vocab_file")
        print("\n=== Stage 6b: Key Term Detection ===")
        term_detections = detect_terms(sents, vocab_file, verbose=verbose)
        print(f"  {len(term_detections)} term(s) detected")
        if term_detections:
            term_overlays = build_term_overlays(
                term_detections, sents, cut_sentences,
                module_slug=module_slug,
                segments=segments, clean_ranges=clean, verbose=verbose,
            )
            print(f"  {len(term_overlays)} term overlay(s) ready")

    if bold_enabled:
        print("\n=== Stage 6c: Bold Phrase Cards ===")
        bold_overlays = detect_bold_cards(
            gp, cut_sentences,
            segments=segments, clean_ranges=clean, verbose=verbose,
        )
        print(f"  {len(bold_overlays)} bold card(s) ready")
        if bold_overlays:
            term_overlays.extend(bold_overlays)

    eq_specs = config["overlays"]["equations"].get("specs_file")
    if eq_enabled and eq_specs:
        print("\n=== Stage 8e: Equation Overlay Detection ===")
        from .render_equation import build_equation_overlays
        eq_overlays = build_equation_overlays(
            eq_specs, segments, cut_sentences, verbose=verbose,
        )
        print(f"  {len(eq_overlays)} equation overlay(s) ready")

    if dry_run:
        print("\n[dry-run — no video exported]")
        return

    # ── Stages 7–8: Cut, chroma & overlay ────────────────────────────
    print("\n=== Stage 7–8: Cut & Export ===")
    needs_mask = (bool(overlays) or bool(eq_overlays)) and config["chroma"]["enabled"]
    clip, video_size, video, get_rgba_frame = build_cut_clip(
        vp, clean, config, verbose=verbose, with_speaker_mask=needs_mask,
    )

    if overlays:
        print("\n=== Stage 9: Overlay Composition ===")
        clip = composite_overlays(
            clip, overlays, video_size, config,
            get_rgba_frame=get_rgba_frame, verbose=verbose,
        )

    if eq_overlays:
        print("\n=== Stage 8e: Equation Overlay Composition ===")
        clip = composite_equations(
            clip, eq_overlays, video_size, config,
            get_rgba_frame=get_rgba_frame, verbose=verbose,
        )

    # Suppress term overlays that overlap with list/equation overlays
    suppress_ranges = [(ov.cut_start, ov.cut_end) for ov in overlays]
    suppress_ranges += [(ov.cut_start, ov.cut_end) for ov in eq_overlays]
    if suppress_ranges and term_overlays:
        term_overlays = [
            t for t in term_overlays
            if not any(s <= t.cut_end and t.cut_start <= e for s, e in suppress_ranges)
        ]

    if term_overlays:
        print("\n=== Stage 8c: Term Overlay Composition ===")
        clip = composite_terms(clip, term_overlays, video_size, config, verbose=verbose)

    # ── Stage 10: Bookends ───────────────────────────────────────────
    intro_video = None
    if config["bookends"]["intro_video"] or config["bookends"]["closing_image"]:
        print("\n=== Stage 10: Bookends ===")
        clip, intro_video = wrap_with_bookends(clip, config, verbose=verbose)

    export_clip(clip, op, verbose=verbose)
    video.close()
    if intro_video is not None:
        intro_video.close()

    # ── Stage 11: Audio normalization ────────────────────────────────
    if config["audio"]["normalize"]:
        print("\n=== Stage 11: Audio Normalization ===")
        normalize_audio(op, verbose=verbose)

    print(f"\n  ✓ {op}")


def generate_edit_project(
    video_path: str,
    script: str | None = None,
    config: dict | None = None,
    verbose: bool = False,
    project_output: str | None = None,
    script_candidates: list[str | Path] | None = None,
) -> EditProject:
    """Run analysis stages only and return the editable project model."""
    project = process_video(
        video_path=video_path,
        script=script,
        script_candidates=script_candidates,
        config=config,
        verbose=verbose,
        project_output=project_output,
        project_only=True,
    )
    if project is None:  # Defensive: project_only must always return the model.
        raise RuntimeError("Project generation completed without an EditProject")
    return project


def _project_reference_path(value: str, project_path: Path) -> Path:
    """Resolve project-relative paths without changing the saved project."""
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (project_path.parent / path).resolve()


def _validate_project_source(
    project: EditProject, source: Path, *, allow_source_mismatch: bool
) -> None:
    if not source.is_file():
        raise ValueError(f"No se encontró el video fuente del proyecto: {source}")
    stat = source.stat()
    mismatches: list[str] = []
    if project.source.size_bytes is not None and stat.st_size != project.source.size_bytes:
        mismatches.append("tamaño")
    if project.source.mtime_ns is not None and stat.st_mtime_ns != project.source.mtime_ns:
        mismatches.append("fecha de modificación")
    if mismatches and not allow_source_mismatch:
        raise ValueError(
            "El video localizado no coincide con el snapshot del proyecto "
            f"({', '.join(mismatches)}). Usa allow_source_mismatch solo si verificaste la fuente."
        )


def render_project(
    project_path: str | Path,
    *,
    output: str | Path | None = None,
    config: dict | None = None,
    dry_run: bool = False,
    verbose: bool = False,
    allow_source_mismatch: bool = False,
) -> Path | list[tuple[float, float]]:
    """Render an approved editable project without re-running Whisper/alignment.

    The legacy ``process_video`` route is intentionally left unchanged.  This
    entry point consumes the effective source timeline and therefore honours
    manual keep/discard decisions, splits and moved cuts stored in the project.
    """
    project_file = Path(project_path).expanduser().resolve()
    project = load_project(project_file)
    source = _project_reference_path(project.source.path, project_file)
    script = _project_reference_path(project.script.path, project_file)
    _validate_project_source(
        project, source, allow_source_mismatch=allow_source_mismatch
    )
    render_config = copy.deepcopy(project.settings if config is None else config)
    media_duration = probe_media_duration(source)
    ranges = project.compile_render_ranges(source_duration_s=media_duration)
    if not ranges:
        raise ValueError("El proyecto no conserva ningún tramo para renderizar")
    if output is None:
        suffix = render_config.get("output", {}).get("suffix", "_edited")
        destination = source.with_name(f"{source.stem}{suffix}.mp4")
    else:
        destination = Path(output).expanduser().resolve()
    _validate_output_paths(
        source,
        script,
        output_video=destination,
        json_output=None,
        project_output=None,
    )
    if dry_run:
        if verbose:
            print(f"[render-project dry-run] {len(ranges)} rango(s) efectivos")
            for index, (start, end) in enumerate(ranges, start=1):
                print(f"  [{index}] {start:.3f}s – {end:.3f}s")
        return ranges

    selected = project.to_matches()
    transcript_segments = project.transcript.segments
    overlays = []
    term_overlays = []
    eq_overlays = []
    if script.is_file():
        paragraphs = parse_guion(script)
        sentences = guion_sentences(paragraphs)
        xfade = transition_overlap(render_config)
        cut_sentences = remap_to_cut(selected, ranges, xfade_dur=xfade, verbose=verbose)
        if render_config["overlays"]["lists"].get("enabled", False):
            detections = detect_lists(sentences, verbose=verbose)
            if detections:
                overlays = extract_list_items(
                    detections, sentences, script, cut_sentences,
                    config=render_config, segments=transcript_segments,
                    clean_ranges=ranges, verbose=verbose,
                )
        if render_config["overlays"]["terms"].get("enabled", False):
            detections = detect_terms(
                sentences, render_config["overlays"]["terms"].get("vocab_file"), verbose=verbose
            )
            if detections:
                term_overlays = build_term_overlays(
                    detections, sentences, cut_sentences,
                    module_slug=script.stem, segments=transcript_segments,
                    clean_ranges=ranges, verbose=verbose,
                )
        if render_config["overlays"]["bold_cards"].get("enabled", False):
            term_overlays.extend(detect_bold_cards(
                script, cut_sentences, segments=transcript_segments,
                clean_ranges=ranges, verbose=verbose,
            ))
        equation_specs = render_config["overlays"]["equations"].get("specs_file")
        if render_config["overlays"]["equations"].get("enabled", False) and equation_specs:
            from .render_equation import build_equation_overlays

            eq_overlays = build_equation_overlays(
                equation_specs, transcript_segments, cut_sentences, verbose=verbose
            )
    elif verbose:
        print("  Script no disponible: se omiten overlays regenerables.")

    slide_state = project.slides_state()
    approved_slides = bool(slide_state and any(page.enabled for page in slide_state.pages))
    if approved_slides and not render_config["chroma"]["enabled"]:
        raise ValueError(
            "Hay diapositivas activas en la línea de tiempo, pero Chroma está "
            "desactivado. Activa Chroma en los ajustes de render, o desactiva "
            "las diapositivas antes de exportar."
        )
    needs_mask = (bool(overlays) or bool(eq_overlays) or approved_slides) and render_config["chroma"]["enabled"]
    clip, video_size, video, get_rgba_frame = build_cut_clip(
        source, ranges, render_config, verbose=verbose, with_speaker_mask=needs_mask
    )
    intro_video = None
    try:
        if overlays:
            clip = composite_overlays(
                clip, overlays, video_size, render_config,
                get_rgba_frame=get_rgba_frame, verbose=verbose,
            )
        if eq_overlays:
            clip = composite_equations(
                clip, eq_overlays, video_size, render_config,
                get_rgba_frame=get_rgba_frame, verbose=verbose,
            )
        suppress_ranges = [(item.cut_start, item.cut_end) for item in overlays]
        suppress_ranges += [(item.cut_start, item.cut_end) for item in eq_overlays]
        if suppress_ranges and term_overlays:
            term_overlays = [
                item for item in term_overlays
                if not any(start <= item.cut_end and item.cut_start <= end for start, end in suppress_ranges)
            ]
        if term_overlays:
            clip = composite_terms(clip, term_overlays, video_size, render_config, verbose=verbose)
        if approved_slides and slide_state is not None:
            from .slide_composite import composite_slides

            clip = composite_slides(
                clip,
                state=slide_state,
                project_path=project_file,
                ranges=ranges,
                video_size=video_size,
                config=render_config,
                get_rgba_frame=get_rgba_frame,
                verbose=verbose,
            )
        if render_config["bookends"].get("intro_video") or render_config["bookends"].get("closing_image"):
            clip, intro_video = wrap_with_bookends(clip, render_config, verbose=verbose)
        export_clip(clip, destination, verbose=verbose)
    finally:
        video.close()
        if intro_video is not None:
            intro_video.close()
    if render_config["audio"].get("normalize", False):
        normalize_audio(destination, verbose=verbose)
    if verbose:
        print(f"  ✓ {destination}")
    return destination
