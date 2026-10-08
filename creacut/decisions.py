"""Observable decision models for script-to-transcript alignment.

These models describe why an automatic take was selected without changing the
legacy objects consumed by the rendering pipeline.  They are intentionally
free of UI and persistence concerns; a later project layer can serialize or
edit them through deterministic, analysis-local candidate IDs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .common import GuionSentence, MatchCandidate


def candidate_id_for(match: MatchCandidate) -> str:
    """Return a deterministic ID for a candidate within one alignment run."""
    sentence = match.sentence
    seg_start = match.segment_start_idx
    seg_end = match.segment_end_idx
    segment_span = (
        f"seg{seg_start}-{seg_end}"
        if seg_start is not None and seg_end is not None
        else "seg-unknown"
    )
    start_ms = round(match.start * 1000)
    end_ms = round(match.end * 1000)
    return (
        f"p{sentence.paragraph_idx}:s{sentence.sentence_idx}:"
        f"{segment_span}:{start_ms}-{end_ms}"
    )


@dataclass(frozen=True)
class AlignmentCandidate:
    """A selectable take candidate and the evidence used to describe it.

    ``transcript_text`` is the segment window used for matching.  The refined
    time span can be narrower (or extend through a ghost-tail correction).
    """

    id: str
    source_start_s: float
    source_end_s: float
    score: float
    transcript_text: str = ""
    segment_start_idx: int | None = None
    segment_end_idx: int | None = None
    refinements: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_match(cls, match: MatchCandidate) -> "AlignmentCandidate":
        return cls(
            id=candidate_id_for(match),
            source_start_s=match.start,
            source_end_s=match.end,
            score=match.score,
            transcript_text=match.transcript_text,
            segment_start_idx=match.segment_start_idx,
            segment_end_idx=match.segment_end_idx,
            refinements=tuple(match.refinements),
        )

    @property
    def duration_s(self) -> float:
        return self.source_end_s - self.source_start_s

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_start_s": self.source_start_s,
            "source_end_s": self.source_end_s,
            "duration_s": self.duration_s,
            "score": self.score,
            "transcript_text": self.transcript_text,
            "segment_start_idx": self.segment_start_idx,
            "segment_end_idx": self.segment_end_idx,
            "refinements": list(self.refinements),
        }


@dataclass(frozen=True)
class CandidateRejection:
    """Why an otherwise valid candidate was excluded by ordering filters."""

    candidate_id: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class SentenceDecision:
    """Post-deduplication candidates and the choice for one script sentence."""

    sentence: GuionSentence
    candidates: tuple[AlignmentCandidate, ...]
    selected_candidate_id: str | None
    selection_reason: str
    previous_selection_end_s: float
    chronological_floor_s: float
    retake_floor_s: float | None
    strict_floor_s: float
    applied_floor_s: float
    fallback_used: bool = False
    rejected_candidates: tuple[CandidateRejection, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        candidate_ids = {candidate.id for candidate in self.candidates}
        if (
            self.selected_candidate_id is not None
            and self.selected_candidate_id not in candidate_ids
        ):
            raise ValueError(
                "selected_candidate_id must identify one of the sentence candidates"
            )

    @property
    def selected_candidate(self) -> AlignmentCandidate | None:
        if self.selected_candidate_id is None:
            return None
        return next(
            (c for c in self.candidates if c.id == self.selected_candidate_id),
            None,
        )

    def to_dict(self) -> dict:
        return {
            "sentence": {
                "paragraph_idx": self.sentence.paragraph_idx,
                "sentence_idx": self.sentence.sentence_idx,
                "text": self.sentence.text,
                "normalized": self.sentence.normalized,
            },
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "selected_candidate_id": self.selected_candidate_id,
            "selection_reason": self.selection_reason,
            "previous_selection_end_s": self.previous_selection_end_s,
            "chronological_floor_s": self.chronological_floor_s,
            "retake_floor_s": self.retake_floor_s,
            "strict_floor_s": self.strict_floor_s,
            "applied_floor_s": self.applied_floor_s,
            "fallback_used": self.fallback_used,
            "rejected_candidates": [
                rejection.to_dict() for rejection in self.rejected_candidates
            ],
        }


@dataclass(frozen=True)
class RetakeDecision:
    """Evidence used to establish a retake floor for one paragraph."""

    paragraph_idx: int
    candidate_ids: tuple[str, ...]
    good_candidate_ids: tuple[str, ...]
    strong_candidate_ids: tuple[str, ...]
    floor_candidate_id: str | None
    floor_s: float | None
    reason: str

    @property
    def detected(self) -> bool:
        return self.floor_candidate_id is not None

    def to_dict(self) -> dict:
        return {
            "paragraph_idx": self.paragraph_idx,
            "candidate_ids": list(self.candidate_ids),
            "good_candidate_ids": list(self.good_candidate_ids),
            "strong_candidate_ids": list(self.strong_candidate_ids),
            "floor_candidate_id": self.floor_candidate_id,
            "floor_s": self.floor_s,
            "detected": self.detected,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AlignmentPlan:
    """Observable output whose selected matches are a legacy projection.

    ``decisions`` is the canonical explanation. ``selected_matches`` exists so
    the current rendering pipeline can keep consuming ``MatchCandidate``
    objects while the editable project layer is introduced incrementally.
    """

    decisions: tuple[SentenceDecision, ...]
    retakes: tuple[RetakeDecision, ...]
    selected_matches: tuple[MatchCandidate, ...] = field(repr=False)
    match_threshold: float = 0.0
    good_match_threshold: float = 0.0

    def __post_init__(self) -> None:
        decision_ids = tuple(
            decision.selected_candidate_id
            for decision in self.decisions
            if decision.selected_candidate_id is not None
        )
        legacy_ids = tuple(candidate_id_for(match) for match in self.selected_matches)
        if decision_ids != legacy_ids:
            raise ValueError(
                "selected_matches must be the legacy projection of decisions"
            )

    def to_dict(self) -> dict:
        return {
            "match_threshold": self.match_threshold,
            "good_match_threshold": self.good_match_threshold,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "retakes": [retake.to_dict() for retake in self.retakes],
            "selected_matches": [
                {
                    "candidate_id": candidate_id_for(match),
                    "paragraph_idx": match.sentence.paragraph_idx,
                    "sentence_idx": match.sentence.sentence_idx,
                    "script_text": match.sentence.text,
                    "source_start_s": match.start,
                    "source_end_s": match.end,
                    "score": match.score,
                }
                for match in self.selected_matches
            ],
            "selected_candidate_ids": [
                decision.selected_candidate_id
                for decision in self.decisions
                if decision.selected_candidate_id is not None
            ],
        }
