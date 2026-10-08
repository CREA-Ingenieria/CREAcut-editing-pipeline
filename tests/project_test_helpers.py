"""Deterministic factories shared by editable-project contract tests."""

from __future__ import annotations

import copy
from pathlib import Path

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
from creacut.project import EditProject


def make_alignment_plan() -> tuple[AlignmentPlan, MatchCandidate, MatchCandidate]:
    sentence = GuionSentence(
        0,
        0,
        "Esta explicación tiene dos tomas.",
        normalize("Esta explicación tiene dos tomas."),
    )
    unmatched = GuionSentence(
        0,
        1,
        "Esta oración no fue pronunciada.",
        normalize("Esta oración no fue pronunciada."),
    )
    early = MatchCandidate(
        sentence,
        1.0,
        2.0,
        0.82,
        transcript_text="Esta explicación tiene dos tomas.",
        segment_start_idx=0,
        segment_end_idx=0,
        refinements=("opener_start",),
    )
    recommended = MatchCandidate(
        sentence,
        5.0,
        6.3,
        0.94,
        transcript_text="Esta explicación tiene dos tomas, versión final.",
        segment_start_idx=2,
        segment_end_idx=2,
        refinements=("peak_end_trim",),
    )
    early_candidate = AlignmentCandidate.from_match(early)
    recommended_candidate = AlignmentCandidate.from_match(recommended)
    early_id = candidate_id_for(early)
    recommended_id = candidate_id_for(recommended)

    decisions = (
        SentenceDecision(
            sentence=sentence,
            candidates=(early_candidate, recommended_candidate),
            selected_candidate_id=recommended_id,
            selection_reason="unique_best",
            previous_selection_end_s=0.0,
            chronological_floor_s=-0.5,
            retake_floor_s=5.0,
            strict_floor_s=4.5,
            applied_floor_s=4.5,
            rejected_candidates=(
                CandidateRejection(early_id, ("before_retake_floor",)),
            ),
        ),
        SentenceDecision(
            sentence=unmatched,
            candidates=(),
            selected_candidate_id=None,
            selection_reason="no_candidate",
            previous_selection_end_s=6.3,
            chronological_floor_s=5.8,
            retake_floor_s=5.0,
            strict_floor_s=5.8,
            applied_floor_s=5.8,
        ),
    )
    retake = RetakeDecision(
        paragraph_idx=0,
        candidate_ids=(early_id, recommended_id),
        good_candidate_ids=(early_id, recommended_id),
        strong_candidate_ids=(early_id, recommended_id),
        floor_candidate_id=recommended_id,
        floor_s=5.0,
        reason="last_strong_candidate",
    )
    plan = AlignmentPlan(
        decisions=decisions,
        retakes=(retake,),
        selected_matches=(recommended,),
        match_threshold=0.55,
        good_match_threshold=0.60,
    )
    return plan, early, recommended


def make_edit_project(
    tmp_dir: Path,
    sample_script: Path,
    sample_segments: list[dict],
) -> tuple[EditProject, AlignmentPlan, MatchCandidate, MatchCandidate, Path]:
    video_path = tmp_dir / "clase con espacios y ñ.mp4"
    video_path.write_bytes(b"source placeholder")
    plan, early, recommended = make_alignment_plan()
    transcript = {
        "text": " ".join(
            segment["text"].strip() for segment in sample_segments
        ),
        "segments": copy.deepcopy(sample_segments),
    }
    project = EditProject.from_alignment_plan(
        plan,
        source_video=video_path,
        script_path=sample_script,
        transcript=transcript,
        settings=copy.deepcopy(DEFAULTS),
        script_score=0.97,
        project_id="proyecto-pruebas-ñ",
        generator_version="test",
        created_at_utc="2026-08-20T12:00:00+00:00",
    )
    return project, plan, early, recommended, video_path
