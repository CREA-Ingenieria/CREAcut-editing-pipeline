"""Stage 6c — Detect bold phrases in guion and convert to TermOverlay cards."""

import re
from pathlib import Path

from .common import (
    CutSentence,
    TermOverlay,
    normalize,
    split_sentences,
)
from .extract_items import find_segment_time, raw_to_cut


def _format_card_text(phrase: str, preceded_by: str) -> str:
    """Wrap phrase in quotes; prepend (...) if it doesn't open a sentence."""
    stripped = preceded_by.rstrip()
    if not stripped or stripped[-1] in ".?!":
        return f'"{phrase[0].upper()}{phrase[1:]}"'
    return f'"(...) {phrase}"'


def _find_sentence_range(phrase: str, paragraph: str) -> tuple[int, int]:
    """Return (start_idx, end_idx) of sentences spanning the bold phrase."""
    norm_phrase = normalize(phrase)
    sents = split_sentences(paragraph)

    for i, sent in enumerate(sents):
        if norm_phrase in normalize(sent):
            return (i, i)

    phrase_sents = split_sentences(phrase)
    if len(phrase_sents) > 1:
        first_idx = None
        last_idx = None
        for ps in phrase_sents:
            norm_ps = normalize(ps)
            for i, sent in enumerate(sents):
                if norm_ps in normalize(sent):
                    if first_idx is None:
                        first_idx = i
                    last_idx = i
                    break
        if first_idx is not None and last_idx is not None:
            return (first_idx, last_idx)

    return (0, 0)


def detect_bold_cards(
    guion_path: Path,
    cut_sentences: list[CutSentence],
    segments: list[dict] | None = None,
    clean_ranges: list[tuple[float, float]] | None = None,
    verbose: bool = False,
) -> list[TermOverlay]:
    """
    Read raw guion markdown, extract **bold** phrases, and map them to
    TermOverlay objects using cut_sentences for timestamps.
    """
    text = guion_path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    body = parts[2].strip() if len(parts) >= 3 else text

    cut_map = {(cs.paragraph_idx, cs.sentence_idx): cs for cs in cut_sentences}
    overlays: list[TermOverlay] = []
    para_idx = 0

    for raw_line in body.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("!"):
            line = line[1:].strip()

        bold_matches = list(re.finditer(r"\*\*([^*]+)\*\*", line))
        if bold_matches:
            paragraph = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)

            for match in bold_matches:
                phrase = match.group(1).strip()
                preceded_by = line[: match.start()]
                card_text = _format_card_text(phrase, preceded_by)

                start_idx, end_idx = _find_sentence_range(phrase, paragraph)
                cs_start = cut_map.get((para_idx, start_idx))
                cs_end = cut_map.get((para_idx, end_idx))

                if cs_start is None:
                    if verbose:
                        print(f"    [bold] no CutSentence para {para_idx}/{start_idx} — skipped")
                    continue
                if cs_end is None:
                    cs_end = cs_start

                cut_start = cs_start.cut_start
                cut_end = cs_end.cut_end

                # Word-level: refine start for single-sentence phrases that
                # begin mid-sentence (multi-sentence ranges already have
                # correct sentence boundaries as anchors)
                if segments and clean_ranges and start_idx == end_idx:
                    raw_t = find_segment_time(
                        segments, phrase,
                        cs_start.raw_start, cs_end.raw_end,
                        clean_ranges=clean_ranges,
                    )
                    if raw_t is not None:
                        cut_t = raw_to_cut(raw_t, clean_ranges)
                        if cut_t is not None and cut_t > cut_start:
                            cut_start = cut_t

                overlays.append(TermOverlay(
                    term=card_text,
                    definition="",
                    cut_start=round(cut_start, 3),
                    cut_end=round(cut_end, 3),
                    module_slug="",
                ))
                if verbose:
                    print(f"    [bold] \"{phrase[:50]}\" → card {cut_start:.1f}s–{cut_end:.1f}s ({cut_end - cut_start:.1f}s)")

        para_idx += 1

    return overlays
