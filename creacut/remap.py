"""Stage 4 — Remap alignment timestamps to the cut-video timeline."""

from .common import CutSentence, MatchCandidate


def remap_to_cut(
    selected: list[MatchCandidate],
    clean_ranges: list[tuple[float, float]],
    xfade_dur: float = 0.0,
    verbose: bool = False,
) -> list[CutSentence]:
    offsets: list[tuple[float, float, float]] = []
    cumulative = 0.0
    for s, e in clean_ranges:
        offsets.append((s, e, cumulative))
        cumulative += (e - s) - xfade_dur

    result: list[CutSentence] = []
    for m in selected:
        for range_start, range_end, offset in offsets:
            # A manually split source range may cut through the middle of a
            # sentence.  Keep every visible intersection rather than mapping
            # only the first range containing ``m.start`` as the old pipeline
            # did.  Existing unsplit projects still produce one item.
            raw_start = max(m.start, range_start)
            raw_end = min(m.end, range_end)
            if raw_end <= raw_start:
                continue
            cut_start = max(0.0, (raw_start - range_start) + offset)
            cut_end = (raw_end - range_start) + offset
            result.append(CutSentence(
                text=m.sentence.text,
                cut_start=round(cut_start, 3),
                cut_end=round(cut_end, 3),
                paragraph_idx=m.sentence.paragraph_idx,
                sentence_idx=m.sentence.sentence_idx,
                raw_start=round(raw_start, 3),
                raw_end=round(raw_end, 3),
            ))
            if verbose:
                print(f"    [{m.sentence.paragraph_idx}:{m.sentence.sentence_idx}] "
                      f"{raw_start:.1f}s→{cut_start:.1f}s  \"{m.sentence.text[:50]}...\"")

    return result
