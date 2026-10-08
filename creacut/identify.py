"""Stage 2 — Identify which script corresponds to the video."""

import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

from .common import normalize, parse_guion


def identify_guion(
    segments: list[dict], guion_files: list[Path], verbose: bool = False
) -> tuple[Path, float]:
    text_parts = []
    for seg in segments:
        if seg["no_speech_prob"] > 0.7:
            continue
        t = seg["text"].strip()
        if len(t) < 20 and re.search(r"\d", t):
            continue
        text_parts.append(t)
        if seg["end"] > 15:
            break

    whisper_text = normalize(" ".join(text_parts))
    if verbose:
        print(f"  First ~15s: \"{whisper_text[:120]}...\"")

    scores: list[tuple[Path, float]] = []
    for gf in guion_files:
        paras = parse_guion(gf)
        if not paras:
            continue
        first_para = normalize(paras[0])
        score = SequenceMatcher(None, first_para, whisper_text, autojunk=False).ratio()
        scores.append((gf, score))

    scores.sort(key=lambda x: x[1], reverse=True)

    if not scores:
        raise ValueError("No readable Markdown scripts with content were found")

    if verbose:
        print("  Top 5 matches:")
        for path, score in scores[:5]:
            print(f"    {score:.3f}  {path.name}")

    best_path, best_score = scores[0]
    if best_score < 0.5:
        print(
            f"WARNING: Best match score = {best_score:.3f} (< 0.5).\n"
            f"  Candidate: {best_path}\n"
            f"  Use --guion to specify manually.",
            file=sys.stderr,
        )

    return best_path, best_score
