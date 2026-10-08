"""Stage 6b — Detect key terms in guion sentences using curated vocabulary."""

import json
from pathlib import Path

from .common import (
    CutSentence,
    GuionSentence,
    TERM_DISPLAY_DURATION,
    TermDetection,
    TermOverlay,
    normalize,
)
from .extract_items import find_segment_time, raw_to_cut


def load_vocab(vocab_file: str | None) -> list[dict]:
    if vocab_file is None:
        return []
    path = Path(vocab_file)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def detect_terms(
    sentences: list[GuionSentence],
    vocab_file: str | None,
    verbose: bool = False,
) -> list[TermDetection]:
    vocab = load_vocab(vocab_file)
    if not vocab:
        return []

    detections: list[TermDetection] = []
    used_terms: set[str] = set()

    for i, sent in enumerate(sentences):
        norm_text = sent.normalized
        for entry in vocab:
            term = entry["term"]
            if term in used_terms:
                continue
            norm_term = normalize(term)
            if norm_term in norm_text:
                detections.append(TermDetection(
                    term=term.title(),
                    definition=entry["definition"],
                    sentence_idx=i,
                ))
                used_terms.add(term)
                if verbose:
                    print(f"    [term] \"{term}\" at sent {i}")
                break

    return detections


def build_term_overlays(
    detections: list[TermDetection],
    sentences: list[GuionSentence],
    cut_sentences: list[CutSentence],
    module_slug: str = "",
    segments: list[dict] | None = None,
    clean_ranges: list[tuple[float, float]] | None = None,
    verbose: bool = False,
) -> list[TermOverlay]:
    cut_map = {(cs.paragraph_idx, cs.sentence_idx): cs for cs in cut_sentences}
    overlays: list[TermOverlay] = []

    for det in detections:
        if det.sentence_idx >= len(sentences):
            continue
        gs = sentences[det.sentence_idx]
        cs = cut_map.get((gs.paragraph_idx, gs.sentence_idx))
        if not cs:
            continue

        cut_start = cs.cut_start

        # Word-level: find when speaker says the term
        if segments and clean_ranges:
            raw_t = find_segment_time(
                segments, det.term,
                cs.raw_start, cs.raw_end,
                clean_ranges=clean_ranges,
            )
            if raw_t is not None:
                cut_t = raw_to_cut(raw_t, clean_ranges)
                if cut_t is not None:
                    cut_start = cut_t

        cut_end = cut_start + TERM_DISPLAY_DURATION

        overlays.append(TermOverlay(
            term=det.term,
            definition=det.definition,
            cut_start=round(cut_start, 3),
            cut_end=round(cut_end, 3),
            module_slug=module_slug,
        ))
        if verbose:
            print(f"    [term-overlay] \"{det.term}\" at {cut_start:.1f}s–{cut_end:.1f}s")

    return overlays
