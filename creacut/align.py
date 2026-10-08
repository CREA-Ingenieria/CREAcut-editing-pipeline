"""Stage 3 — Align script sentences to transcription segments, handling retakes."""

from difflib import SequenceMatcher

from .common import GuionSentence, MatchCandidate, normalize
from .decisions import (
    AlignmentCandidate,
    AlignmentPlan,
    CandidateRejection,
    RetakeDecision,
    SentenceDecision,
    candidate_id_for,
)


def _is_restart_marker(text: str, restart_words: set[str]) -> bool:
    low = text.strip().lower()
    return any(w in low for w in restart_words)


def find_matches(
    sentence: GuionSentence, segments: list[dict], config: dict
) -> list[MatchCandidate]:
    restart_words = set(config["retakes"]["restart_words"])
    match_threshold = config["retakes"]["match_threshold"]
    max_word_gap = config["retakes"]["max_word_gap"]

    candidates = []
    norm_sent = sentence.normalized
    # Short sentences need a wider cap so fused segments (e.g. "A? B?") aren't rejected before scoring.
    cap_mult = 4 if len(norm_sent) < 20 else 2

    for i in range(len(segments)):
        if segments[i]["no_speech_prob"] > 0.7:
            continue
        if _is_restart_marker(segments[i]["text"], restart_words):
            continue

        acc = ""
        best_score = 0.0
        best_end = i

        for j in range(i, min(i + 10, len(segments))):
            acc += segments[j]["text"]
            norm_acc = normalize(acc)
            if not norm_acc:
                continue
            if len(norm_acc) > len(norm_sent) * cap_mult:
                break
            if len(norm_acc) < len(norm_sent) * 0.3:
                continue

            score = SequenceMatcher(None, norm_sent, norm_acc, autojunk=False).ratio()
            if score > best_score:
                best_score = score
                best_end = j

        if best_score >= match_threshold:
            refinements: list[str] = []

            # Refine start: find the first segment in [i..best_end] whose text
            # contains the opening words of the script sentence. This eliminates
            # leading off-camera chatter when Whisper groups it with real speech.
            guion_opener = norm_sent.split()[:3]
            actual_start = segments[i]["start"]
            if guion_opener and len(guion_opener[0]) > 1:
                for k in range(i, best_end + 1):
                    seg_words_norm = normalize(segments[k]["text"]).split()
                    if all(w in seg_words_norm for w in guion_opener):
                        seg_kw = segments[k].get("words", [])
                        if seg_kw:
                            for w in seg_kw:
                                if normalize(w["word"]).strip() == guion_opener[0]:
                                    actual_start = w["start"]
                                    break
                            else:
                                actual_start = seg_kw[0]["start"]
                        else:
                            actual_start = segments[k]["start"]
                        break
            if actual_start != segments[i]["start"]:
                refinements.append("opener_start")

            # Refine end: extend to the next segment only when the current segment
            # ends with ghost words (≥2 final words share the same timestamp as the
            # segment boundary). This catches Whisper's split-on-ghost-word pattern
            # without consuming the first segment of the following script sentence.
            actual_end = segments[best_end]["end"]
            seg_tail_words = segments[best_end].get("words", [])
            has_ghost_tail = (
                len(seg_tail_words) >= 2
                and seg_tail_words[-1]["end"] == actual_end
                and seg_tail_words[-2]["end"] == actual_end
            )
            if has_ghost_tail:
                next_k = best_end + 1
                if next_k < len(segments):
                    next_seg = segments[next_k]
                    if next_seg["start"] - actual_end <= 0.1:
                        next_words = next_seg.get("words", [])
                        if next_words and next_words[-1]["end"] > actual_end:
                            actual_end = next_words[-1]["end"]
                            refinements.append("ghost_tail_extension")

            # End refinement: tighten actual_end to where the script
            # sentence content peaks in the word timeline.  When Whisper
            # packs two sentences into one segment, the match end
            # overshoots the sentence boundary.
            scan_limit = min(best_end + 2, len(segments))
            all_match_words = []
            for seg in segments[i:scan_limit]:
                for w in seg.get("words", []):
                    if w["end"] <= actual_start:
                        continue
                    if w["start"] > actual_end:
                        break
                    all_match_words.append(w)

            if len(all_match_words) >= 4:
                peak_end = actual_end
                peak_score = 0.0
                running = ""
                for w in all_match_words:
                    running += w["word"]
                    nr = normalize(running)
                    if not nr or len(nr) < len(norm_sent) * 0.3:
                        continue
                    if len(nr) > len(norm_sent) * cap_mult:
                        break
                    sc = SequenceMatcher(
                        None, norm_sent, nr, autojunk=False
                    ).ratio()
                    if sc > peak_score:
                        peak_score = sc
                        peak_end = w["end"]

                if peak_score >= match_threshold and peak_end < actual_end - 0.5:
                    actual_end = peak_end
                    refinements.append("peak_end_trim")

            # Retake trimming: if the matched range contains a ghost word
            # (> max_word_gap) the pre-gap content is an incomplete take.
            # Advance actual_start past the ghost word to use only the final take.
            for seg in segments[i:best_end + 1]:
                for w in seg.get("words", []):
                    if w["start"] < actual_start or w["end"] > actual_end:
                        continue
                    if w["end"] - w["start"] > max_word_gap and w["end"] < actual_end - 1.0:
                        actual_start = w["end"]
                        if "ghost_gap_trim" not in refinements:
                            refinements.append("ghost_gap_trim")

            transcript_text = " ".join(
                segments[k]["text"].strip()
                for k in range(i, best_end + 1)
                if segments[k]["text"].strip()
            )

            candidates.append(
                MatchCandidate(
                    sentence=sentence,
                    start=actual_start,
                    end=actual_end,
                    score=best_score,
                    transcript_text=transcript_text,
                    segment_start_idx=i,
                    segment_end_idx=best_end,
                    refinements=tuple(refinements),
                )
            )

    if len(candidates) > 1:
        candidates.sort(key=lambda c: c.start)
        deduped = [candidates[0]]
        for c in candidates[1:]:
            if c.start < deduped[-1].end:
                if c.score > deduped[-1].score:
                    deduped[-1] = c
            else:
                deduped.append(c)
        candidates = deduped

    return candidates


def _detect_retake_starts_with_decisions(
    sentences: list[GuionSentence],
    segments: list[dict],
    config: dict,
    verbose: bool = False,
    candidate_inventory: dict[
        tuple[int, int], list[MatchCandidate]
    ] | None = None,
) -> tuple[dict[int, float], tuple[RetakeDecision, ...]]:
    """Detect retake boundaries by finding paragraphs with multiple good matches.

    For each paragraph, look at its first sentence. If it has >1 good matches,
    the paragraph was retaken — record the start time of the last strong match
    together with the evidence used to establish that floor.
    """
    good_match_threshold = config["retakes"]["good_match_threshold"]

    # Group sentences by paragraph_idx, find first sentence of each paragraph
    first_by_para: dict[int, GuionSentence] = {}
    for sent in sentences:
        if sent.sentence_idx == 0:
            first_by_para[sent.paragraph_idx] = sent

    retake_starts: dict[int, float] = {}
    decisions: list[RetakeDecision] = []
    for p_idx, first_sent in first_by_para.items():
        sentence_key = (first_sent.paragraph_idx, first_sent.sentence_idx)
        candidates = (
            candidate_inventory.get(sentence_key)
            if candidate_inventory is not None
            else None
        )
        if candidates is None:
            candidates = find_matches(first_sent, segments, config)
        good = [c for c in candidates if c.score >= good_match_threshold]
        strong: list[MatchCandidate] = []
        floor_candidate = None

        if len(good) > 1:
            best_score = max(c.score for c in good)
            strong = [c for c in good if c.score >= best_score * 0.8]
            if len(strong) > 1:
                floor_candidate = strong[-1]
                retake_starts[p_idx] = floor_candidate.start
                if verbose:
                    print(
                        f"  Retake detected: paragraph {p_idx} has {len(strong)} takes, "
                        f"using from t={floor_candidate.start:.1f}s"
                    )

        if floor_candidate is not None:
            reason = "last_strong_candidate"
        elif not candidates:
            reason = "no_candidates"
        elif len(good) < 2:
            reason = "fewer_than_two_good_candidates"
        else:
            reason = "fewer_than_two_strong_candidates"

        decisions.append(RetakeDecision(
            paragraph_idx=p_idx,
            candidate_ids=tuple(candidate_id_for(c) for c in candidates),
            good_candidate_ids=tuple(candidate_id_for(c) for c in good),
            strong_candidate_ids=tuple(candidate_id_for(c) for c in strong),
            floor_candidate_id=(
                candidate_id_for(floor_candidate)
                if floor_candidate is not None
                else None
            ),
            floor_s=floor_candidate.start if floor_candidate is not None else None,
            reason=reason,
        ))

    return retake_starts, tuple(decisions)


def _candidate_rejections(
    candidates: list[MatchCandidate],
    eligible: list[MatchCandidate],
    chronological_floor: float,
    retake_floor: float | None,
    fallback_used: bool,
) -> tuple[CandidateRejection, ...]:
    eligible_ids = {candidate_id_for(c) for c in eligible}
    rejections: list[CandidateRejection] = []

    for candidate in candidates:
        candidate_id = candidate_id_for(candidate)
        if candidate_id in eligible_ids:
            continue

        reasons = []
        if candidate.start < chronological_floor:
            reasons.append("before_previous_selection")
        if (
            not fallback_used
            and retake_floor is not None
            and candidate.start < retake_floor - 0.5
        ):
            reasons.append("before_retake_floor")
        if not reasons:
            reasons.append("filtered_out")

        rejections.append(CandidateRejection(candidate_id, tuple(reasons)))

    return tuple(rejections)


def build_alignment_plan(
    sentences: list[GuionSentence],
    segments: list[dict],
    config: dict,
    verbose: bool = False,
) -> AlignmentPlan:
    """Align sentences and retain candidates, filters, and selection reasons."""
    good_match_threshold = config["retakes"]["good_match_threshold"]
    match_threshold = config["retakes"]["match_threshold"]

    # Candidate discovery is the expensive, evidentiary part of alignment.
    # Run it once so retake analysis and sentence decisions reference the exact
    # same candidates (and therefore the same analysis-local IDs).
    candidate_inventory: dict[tuple[int, int], list[MatchCandidate]] = {}
    for sentence in sentences:
        sentence_key = (sentence.paragraph_idx, sentence.sentence_idx)
        if sentence_key not in candidate_inventory:
            candidate_inventory[sentence_key] = find_matches(
                sentence, segments, config,
            )

    retake_starts, retake_decisions = _detect_retake_starts_with_decisions(
        sentences,
        segments,
        config,
        verbose,
        candidate_inventory=candidate_inventory,
    )

    selected: list[MatchCandidate] = []
    decisions: list[SentenceDecision] = []
    min_start = 0.0

    for sent in sentences:
        candidates = candidate_inventory[(sent.paragraph_idx, sent.sentence_idx)]
        previous_selection_end = min_start
        chronological_floor = min_start - 0.5
        retake_floor = retake_starts.get(sent.paragraph_idx)

        # Phase 2: retake-aware filtering
        strict_floor = max(
            chronological_floor,
            (retake_floor if retake_floor is not None else 0.0) - 0.5,
        )
        filtered = [c for c in candidates if c.start >= strict_floor]

        # Phase 3: fallback without retake constraint if no candidates
        fallback_used = False
        if not filtered:
            fallback_candidates = [
                c for c in candidates if c.start >= chronological_floor
            ]
            if fallback_candidates:
                fallback_used = True
                filtered = fallback_candidates

        applied_floor = chronological_floor if fallback_used else strict_floor
        observable_candidates = tuple(
            AlignmentCandidate.from_match(candidate) for candidate in candidates
        )
        rejected_candidates = _candidate_rejections(
            candidates,
            filtered,
            chronological_floor,
            retake_floor,
            fallback_used,
        )

        if not filtered:
            decisions.append(SentenceDecision(
                sentence=sent,
                candidates=observable_candidates,
                selected_candidate_id=None,
                selection_reason="no_candidate",
                previous_selection_end_s=previous_selection_end,
                chronological_floor_s=chronological_floor,
                retake_floor_s=retake_floor,
                strict_floor_s=strict_floor,
                applied_floor_s=applied_floor,
                fallback_used=fallback_used,
                rejected_candidates=rejected_candidates,
            ))
            if verbose:
                print(f"  SKIP: {sent.text[:70]}...")
            continue

        good = [c for c in filtered if c.score >= good_match_threshold]
        if good:
            best_score = max(c.score for c in good)
            strong = [c for c in good if c.score >= best_score * 0.8]
            top = [c for c in strong if c.score == best_score]
            # If there's a single uniquely best candidate, prefer it over a
            # lower-scoring later candidate that would otherwise win via
            # strong[-1]. The strong[-1] retake preference only makes sense
            # when multiple candidates genuinely tie for the best score.
            if len(top) == 1:
                pick = top[0]
                selection_reason = "unique_best"
            else:
                pick = strong[-1]
                selection_reason = "latest_strong"
        else:
            pick = max(filtered, key=lambda c: c.score)
            selection_reason = "best_below_good_threshold"

        selected.append(pick)
        min_start = pick.end
        decisions.append(SentenceDecision(
            sentence=sent,
            candidates=observable_candidates,
            selected_candidate_id=candidate_id_for(pick),
            selection_reason=selection_reason,
            previous_selection_end_s=previous_selection_end,
            chronological_floor_s=chronological_floor,
            retake_floor_s=retake_floor,
            strict_floor_s=strict_floor,
            applied_floor_s=applied_floor,
            fallback_used=fallback_used,
            rejected_candidates=rejected_candidates,
        ))

        if verbose:
            n_takes = len(
                [c for c in candidates if c.score >= good_match_threshold]
            )
            tag = f" ×{n_takes}" if n_takes > 1 else ""
            print(
                f"  [{pick.start:6.1f} – {pick.end:6.1f}] "
                f"score={pick.score:.2f}{tag}  {sent.text[:60]}..."
            )

    return AlignmentPlan(
        decisions=tuple(decisions),
        retakes=retake_decisions,
        selected_matches=tuple(selected),
        match_threshold=match_threshold,
        good_match_threshold=good_match_threshold,
    )


def align(
    sentences: list[GuionSentence],
    segments: list[dict],
    config: dict,
    verbose: bool = False,
) -> list[MatchCandidate]:
    """Backward-compatible facade returning only automatic selections."""
    plan = build_alignment_plan(sentences, segments, config, verbose)
    return list(plan.selected_matches)


def merge_ranges(
    ranges: list[tuple[float, float]], config: dict
) -> list[tuple[float, float]]:
    max_gap = config["retakes"]["merge_gap"]
    if not ranges:
        return []
    merged: list[list[float]] = [list(ranges[0])]
    for s, e in ranges[1:]:
        if s - merged[-1][1] <= max_gap:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def pad_ranges(
    ranges: list[tuple[float, float]],
    max_end: float,
    config: dict,
) -> list[tuple[float, float]]:
    pad_start = config["retakes"]["pad_start"]
    pad_end = config["retakes"]["pad_end"]
    return [
        (max(0.0, s - pad_start), min(max_end, e + pad_end))
        for s, e in ranges
    ]


def split_on_word_gaps(
    ranges: list[tuple[float, float]],
    segments: list[dict],
    config: dict,
) -> list[tuple[float, float]]:
    """Split clean ranges wherever a Whisper word spans an implausibly long gap.

    When a speaker pauses mid-sentence, Whisper sometimes assigns the entire gap
    to a single word (e.g., 'intervenciones' spanning 18s). This function detects
    such words and splits the range at [range_start, word_start] + [word_end, range_end],
    removing the silence from the output.
    """
    max_word_gap = config["retakes"]["split_gap"]
    min_pre_gap_dur = config["retakes"]["min_pre_gap_dur"]
    pad_start = config["retakes"]["pad_start"]

    result = []
    for rng_start, rng_end in ranges:
        sub_start = rng_start
        for seg in segments:
            if seg["end"] <= rng_start or seg["start"] >= rng_end:
                continue
            for w in seg.get("words", []):
                if w["start"] < rng_start or w["end"] > rng_end:
                    continue
                if w["end"] - w["start"] > max_word_gap:
                    pre_dur = w["start"] - sub_start
                    if pre_dur >= min_pre_gap_dur:
                        result.append((sub_start, w["start"]))
                    sub_start = max(rng_start, w["end"] - pad_start)
        result.append((sub_start, rng_end))
    return [(s, e) for s, e in result if e - s > 0.05]
