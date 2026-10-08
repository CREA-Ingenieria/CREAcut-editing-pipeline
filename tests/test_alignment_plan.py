"""Contract tests for the explainable alignment plan introduced in Stage 1."""

from __future__ import annotations

import copy
import json

import pytest

import creacut.align as align_module
from creacut.align import align, build_alignment_plan
from creacut.common import GuionSentence, MatchCandidate, normalize
from creacut.config import DEFAULTS


def _sentence(paragraph_idx: int, sentence_idx: int, text: str) -> GuionSentence:
    return GuionSentence(paragraph_idx, sentence_idx, text, normalize(text))


def _match(
    sentence: GuionSentence,
    start: float,
    end: float,
    score: float,
) -> MatchCandidate:
    return MatchCandidate(sentence=sentence, start=start, end=end, score=score)


@pytest.fixture
def alignment_config() -> dict:
    config = copy.deepcopy(DEFAULTS)
    config["retakes"]["match_threshold"] = 0.55
    config["retakes"]["good_match_threshold"] = 0.60
    return config


def test_plan_preserves_retake_alternatives_and_applies_latest_strong_floor(
    monkeypatch,
    alignment_config,
):
    first = _sentence(0, 0, "Esta oración abre el párrafo.")
    second = _sentence(0, 1, "Esta oración continúa la explicación.")

    candidates_by_sentence = {
        (0, 0): [
            _match(first, 1.0, 2.0, 0.95),
            _match(first, 10.0, 11.0, 0.90),
        ],
        (0, 1): [
            # This is the best textual match, but belongs to the discarded take.
            _match(second, 3.0, 4.0, 0.99),
            _match(second, 11.5, 12.5, 0.75),
        ],
    }

    def fake_find_matches(sentence, segments, config):
        return list(candidates_by_sentence[(sentence.paragraph_idx, sentence.sentence_idx)])

    monkeypatch.setattr(align_module, "find_matches", fake_find_matches)

    plan = build_alignment_plan([first, second], [], alignment_config)

    assert isinstance(plan.decisions, tuple)
    assert isinstance(plan.retakes, tuple)
    assert isinstance(plan.selected_matches, tuple)
    assert len(plan.decisions) == 2
    assert len(plan.retakes) == 1

    retake = plan.retakes[0]
    assert retake.paragraph_idx == 0
    assert len(retake.candidate_ids) == 2
    assert set(retake.good_candidate_ids) == set(retake.candidate_ids)
    assert set(retake.strong_candidate_ids) == set(retake.candidate_ids)
    assert retake.floor_s == pytest.approx(10.0)
    assert retake.floor_candidate_id in retake.strong_candidate_ids
    assert retake.reason

    first_decision, second_decision = plan.decisions
    first_early = next(
        candidate
        for candidate in first_decision.candidates
        if candidate.source_start_s == pytest.approx(1.0)
    )
    first_late = next(
        candidate
        for candidate in first_decision.candidates
        if candidate.source_start_s == pytest.approx(10.0)
    )

    assert first_decision.sentence == first
    assert first_decision.selected_candidate_id == first_late.id
    assert retake.floor_candidate_id == first_late.id
    assert first_decision.selection_reason == "unique_best"
    assert first_decision.previous_selection_end_s == pytest.approx(0.0)
    assert first_decision.chronological_floor_s == pytest.approx(-0.5)
    assert first_decision.retake_floor_s == pytest.approx(10.0)
    assert first_decision.strict_floor_s == pytest.approx(9.5)
    assert first_decision.applied_floor_s == pytest.approx(9.5)
    assert first_decision.fallback_used is False

    first_rejection = next(
        rejection
        for rejection in first_decision.rejected_candidates
        if rejection.candidate_id == first_early.id
    )
    assert isinstance(first_rejection.reasons, tuple)
    assert "before_retake_floor" in first_rejection.reasons

    second_early = next(
        candidate
        for candidate in second_decision.candidates
        if candidate.source_start_s == pytest.approx(3.0)
    )
    second_late = next(
        candidate
        for candidate in second_decision.candidates
        if candidate.source_start_s == pytest.approx(11.5)
    )

    assert second_decision.sentence == second
    assert second_decision.selected_candidate_id == second_late.id
    assert second_decision.selection_reason == "unique_best"
    assert second_decision.previous_selection_end_s == pytest.approx(11.0)
    assert second_decision.chronological_floor_s == pytest.approx(10.5)
    assert second_decision.retake_floor_s == pytest.approx(10.0)
    assert second_decision.strict_floor_s == pytest.approx(10.5)
    assert second_decision.applied_floor_s == pytest.approx(10.5)
    assert second_decision.fallback_used is False

    second_rejection = next(
        rejection
        for rejection in second_decision.rejected_candidates
        if rejection.candidate_id == second_early.id
    )
    assert "before_previous_selection" in second_rejection.reasons

    assert [match.start for match in plan.selected_matches] == [10.0, 11.5]


def test_exact_best_score_tie_selects_latest_strong_candidate(
    monkeypatch,
    alignment_config,
):
    # sentence_idx=1 deliberately avoids declaring a paragraph-level retake: this
    # isolates the tie-breaking rule inside the sentence decision itself.
    sentence = _sentence(0, 1, "Una oración repetida exactamente.")
    matches = [
        _match(sentence, 2.0, 3.0, 0.82),
        _match(sentence, 8.0, 9.0, 0.82),
    ]

    monkeypatch.setattr(
        align_module,
        "find_matches",
        lambda sentence, segments, config: list(matches),
    )

    plan = build_alignment_plan([sentence], [], alignment_config)
    decision = plan.decisions[0]
    latest = next(
        candidate
        for candidate in decision.candidates
        if candidate.source_start_s == pytest.approx(8.0)
    )

    assert plan.retakes == ()
    assert decision.selected_candidate_id == latest.id
    assert decision.selection_reason == "latest_strong"
    assert decision.retake_floor_s is None
    assert decision.fallback_used is False
    assert plan.selected_matches[0].start == pytest.approx(8.0)


def test_sentence_without_candidates_is_preserved_as_a_decision(
    monkeypatch,
    alignment_config,
):
    sentence = _sentence(2, 0, "Esta oración no aparece en la transcripción.")
    monkeypatch.setattr(
        align_module,
        "find_matches",
        lambda sentence, segments, config: [],
    )

    plan = build_alignment_plan([sentence], [], alignment_config)

    assert len(plan.decisions) == 1
    decision = plan.decisions[0]
    assert decision.sentence == sentence
    assert decision.candidates == ()
    assert decision.selected_candidate_id is None
    assert decision.selection_reason == "no_candidate"
    assert decision.previous_selection_end_s == pytest.approx(0.0)
    assert decision.chronological_floor_s == pytest.approx(-0.5)
    assert decision.retake_floor_s is None
    assert decision.strict_floor_s == pytest.approx(-0.5)
    assert decision.applied_floor_s == pytest.approx(-0.5)
    assert decision.fallback_used is False
    assert decision.rejected_candidates == ()
    assert len(plan.retakes) == 1
    assert plan.retakes[0].reason == "no_candidates"
    assert plan.retakes[0].detected is False
    assert plan.selected_matches == ()


def test_candidates_expose_transcript_span_and_refinement_metadata(
    sample_segments,
    alignment_config,
):
    sentence = _sentence(0, 0, "Welcome to this lesson.")

    plan = build_alignment_plan([sentence], sample_segments, alignment_config)
    decision = plan.decisions[0]
    candidate = next(
        candidate
        for candidate in decision.candidates
        if candidate.segment_start_idx == 0
    )

    assert candidate.id
    assert candidate.source_start_s == pytest.approx(0.0)
    assert candidate.source_end_s == pytest.approx(1.2)
    assert candidate.score > 0.60
    assert candidate.transcript_text.strip() == "Welcome to this lesson."
    assert candidate.segment_start_idx == 0
    assert candidate.segment_end_idx == 0
    assert isinstance(candidate.refinements, tuple)
    assert decision.selected_candidate_id == candidate.id

    selected = plan.selected_matches[0]
    assert selected.transcript_text.strip() == candidate.transcript_text.strip()
    assert selected.segment_start_idx == candidate.segment_start_idx
    assert selected.segment_end_idx == candidate.segment_end_idx
    assert selected.refinements == candidate.refinements


def test_alignment_plan_to_dict_is_json_serializable(
    monkeypatch,
    alignment_config,
):
    sentence = _sentence(1, 1, "Decisión serializable en español.")
    match = _match(sentence, 4.0, 5.0, 0.91)
    monkeypatch.setattr(
        align_module,
        "find_matches",
        lambda sentence, segments, config: [match],
    )

    plan = build_alignment_plan([sentence], [], alignment_config)
    payload = plan.to_dict()
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    decoded = json.loads(encoded)

    assert isinstance(payload, dict)
    assert decoded == payload
    assert isinstance(decoded["decisions"], list)
    assert isinstance(decoded["retakes"], list)
    assert isinstance(decoded["selected_matches"], list)
    assert decoded["decisions"][0]["selected_candidate_id"]
    assert decoded["decisions"][0]["selection_reason"] == "unique_best"


def test_align_remains_compatible_with_plan_selected_matches(
    monkeypatch,
    alignment_config,
):
    first = _sentence(0, 1, "Primera decisión compatible.")
    second = _sentence(1, 1, "Segunda decisión compatible.")
    candidates_by_sentence = {
        (0, 1): [
            _match(first, 1.0, 2.0, 0.70),
            _match(first, 5.0, 6.0, 0.90),
        ],
        (1, 1): [_match(second, 7.0, 8.0, 0.88)],
    }

    def fake_find_matches(sentence, segments, config):
        return list(candidates_by_sentence[(sentence.paragraph_idx, sentence.sentence_idx)])

    monkeypatch.setattr(align_module, "find_matches", fake_find_matches)

    plan = build_alignment_plan([first, second], [], alignment_config)
    legacy_result = align([first, second], [], alignment_config)

    assert isinstance(legacy_result, list)
    assert legacy_result == list(plan.selected_matches)


def test_diagnostic_metadata_does_not_change_legacy_match_equality():
    sentence = _sentence(0, 0, "Contrato histórico de igualdad.")
    legacy = MatchCandidate(sentence, 1.0, 2.0, 0.90)
    observable = MatchCandidate(
        sentence,
        1.0,
        2.0,
        0.90,
        transcript_text="Contrato histórico de igualdad.",
        segment_start_idx=3,
        segment_end_idx=4,
        refinements=("peak_end_trim",),
    )

    assert observable == legacy


def test_build_plan_discovers_each_sentence_candidates_once(
    monkeypatch,
    alignment_config,
):
    first = _sentence(0, 0, "Inicio del párrafo.")
    second = _sentence(0, 1, "Continuación del párrafo.")
    calls: list[tuple[int, int]] = []

    def fake_find_matches(sentence, segments, config):
        calls.append((sentence.paragraph_idx, sentence.sentence_idx))
        start = 1.0 + sentence.sentence_idx
        return [_match(sentence, start, start + 0.5, 0.90)]

    monkeypatch.setattr(align_module, "find_matches", fake_find_matches)

    build_alignment_plan([first, second], [], alignment_config)

    assert calls == [(0, 0), (0, 1)]
