"""Editable, serializable project model built from an alignment plan."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, Mapping

from .align import merge_ranges, pad_ranges, split_on_word_gaps
from .common import GuionSentence, MatchCandidate
from .decisions import (
    AlignmentCandidate,
    AlignmentPlan,
    CandidateRejection,
    RetakeDecision,
    SentenceDecision,
)


PROJECT_KIND = "creacut.edit-project"
PROJECT_SCHEMA_VERSION = 1


class ProjectValidationError(ValueError):
    """The in-memory project violates the versioned project contract."""


def _error(path: str, message: str) -> ProjectValidationError:
    return ProjectValidationError(f"{path}: {message}")


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _error(path, "expected an object")
    return value


def _required(data: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in data:
        raise _error(path, f"missing required field {key!r}")
    return data[key]


def _string(value: Any, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise _error(path, "expected a non-empty string" if not allow_empty else "expected a string")
    return value


def _number(value: Any, path: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _error(path, "expected a number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise _error(path, "must be finite") from exc
    if not math.isfinite(result):
        raise _error(path, "must be finite")
    if minimum is not None and result < minimum:
        raise _error(path, f"must be >= {minimum}")
    return result


def _optional_number(value: Any, path: str, *, minimum: float | None = None) -> float | None:
    return None if value is None else _number(value, path, minimum=minimum)


def _optional_int(value: Any, path: str, *, minimum: int = 0) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise _error(path, "expected an integer or null")
    if value < minimum:
        raise _error(path, f"must be >= {minimum}")
    return value


def _json_copy(value: Any, path: str) -> Any:
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise _error(path, f"must contain only finite JSON values ({exc})") from exc
    return json.loads(encoded)


def _json_sha256(value: Any, path: str) -> str:
    copied = _json_copy(value, path)
    encoded = json.dumps(
        copied,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class SourceSnapshot:
    path: str
    duration_s: float | None = None
    size_bytes: int | None = None
    mtime_ns: int | None = None

    def validate(self) -> None:
        _string(self.path, "source.path")
        _optional_number(self.duration_s, "source.duration_s", minimum=0.0)
        _optional_int(self.size_bytes, "source.size_bytes")
        _optional_int(self.mtime_ns, "source.mtime_ns")

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "duration_s": self.duration_s,
                "size_bytes": self.size_bytes, "mtime_ns": self.mtime_ns}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SourceSnapshot":
        d = _mapping(data, "source")
        result = cls(
            path=_string(d.get("path"), "source.path"),
            duration_s=_optional_number(d.get("duration_s"), "source.duration_s", minimum=0.0),
            size_bytes=_optional_int(d.get("size_bytes"), "source.size_bytes"),
            mtime_ns=_optional_int(d.get("mtime_ns"), "source.mtime_ns"),
        )
        result.validate()
        return result


@dataclass(frozen=True)
class ScriptSnapshot:
    path: str
    sha256: str | None = None
    identification_score: float | None = None

    def validate(self) -> None:
        _string(self.path, "script.path")
        if self.sha256 is not None:
            value = _string(self.sha256, "script.sha256").lower()
            if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise _error("script.sha256", "expected 64 hexadecimal characters")
        score = _optional_number(self.identification_score, "script.identification_score")
        if score is not None and not 0.0 <= score <= 1.0:
            raise _error("script.identification_score", "must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "sha256": self.sha256,
                "identification_score": self.identification_score}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ScriptSnapshot":
        d = _mapping(data, "script")
        sha = d.get("sha256")
        result = cls(
            path=_string(d.get("path"), "script.path"),
            sha256=None if sha is None else _string(sha, "script.sha256"),
            identification_score=_optional_number(
                d.get("identification_score"), "script.identification_score"
            ),
        )
        result.validate()
        return result


@dataclass
class TranscriptSnapshot:
    """Post-patch Whisper data; extra top-level metadata remains preserved."""

    text: str
    segments: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def raw_duration_s(self) -> float:
        # This deliberately mirrors the legacy pipeline, whose analysis limit
        # is the end of Whisper's final ordered segment, not media duration.
        return float(self.segments[-1]["end"]) if self.segments else 0.0

    def validate(self) -> None:
        _string(self.text, "transcript.text", allow_empty=True)
        if not isinstance(self.segments, list):
            raise _error("transcript.segments", "expected an array")
        previous_start = -math.inf
        for index, segment in enumerate(self.segments):
            path = f"transcript.segments[{index}]"
            item = _mapping(segment, path)
            start = _number(item.get("start"), f"{path}.start", minimum=0.0)
            end = _number(item.get("end"), f"{path}.end", minimum=0.0)
            if end < start:
                raise _error(path, "end must be >= start")
            if start < previous_start:
                raise _error(path, "segments must be ordered by start time")
            previous_start = start
            _string(item.get("text"), f"{path}.text", allow_empty=True)
            prob = _number(item.get("no_speech_prob", 0.0), f"{path}.no_speech_prob")
            if not 0.0 <= prob <= 1.0:
                raise _error(f"{path}.no_speech_prob", "must be between 0 and 1")
            words = item.get("words", [])
            if not isinstance(words, list):
                raise _error(f"{path}.words", "expected an array")
            for word_index, word in enumerate(words):
                word_path = f"{path}.words[{word_index}]"
                w = _mapping(word, word_path)
                _string(w.get("word"), f"{word_path}.word", allow_empty=True)
                word_start = _number(w.get("start"), f"{word_path}.start", minimum=0.0)
                word_end = _number(w.get("end"), f"{word_path}.end", minimum=0.0)
                if word_end < word_start:
                    raise _error(word_path, "end must be >= start")
        _json_copy(self.metadata, "transcript.metadata")
        _json_copy(self.segments, "transcript.segments")

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "segments": _json_copy(self.segments, "transcript.segments"),
            "metadata": _json_copy(self.metadata, "transcript.metadata"),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TranscriptSnapshot":
        d = _mapping(data, "transcript")
        segments = d.get("segments")
        if not isinstance(segments, list):
            raise _error("transcript.segments", "expected an array")
        metadata = d.get("metadata", {})
        if not isinstance(metadata, dict):
            raise _error("transcript.metadata", "expected an object")
        # Accept raw Whisper dictionaries and preserve any additional top-level keys.
        extras = {key: value for key, value in d.items() if key not in {"text", "segments", "metadata"}}
        combined_metadata = copy.deepcopy(metadata)
        combined_metadata.update(copy.deepcopy(extras))
        result = cls(
            text=_string(d.get("text", ""), "transcript.text", allow_empty=True),
            segments=copy.deepcopy(segments),
            metadata=combined_metadata,
        )
        result.validate()
        return result


@dataclass(frozen=True)
class ProjectProvenance:
    generator_name: str = "creacut"
    generator_version: str = "0.1.0"
    created_at_utc: str = ""
    match_threshold: float = 0.0
    good_match_threshold: float = 0.0
    transcript_sha256: str = ""

    def validate(self) -> None:
        _string(self.generator_name, "provenance.generator.name")
        _string(self.generator_version, "provenance.generator.version")
        _string(self.created_at_utc, "provenance.created_at_utc")
        for name, value in (("match_threshold", self.match_threshold),
                            ("good_match_threshold", self.good_match_threshold)):
            number = _number(value, f"provenance.alignment.{name}")
            if not 0.0 <= number <= 1.0:
                raise _error(f"provenance.alignment.{name}", "must be between 0 and 1")
        digest = _string(self.transcript_sha256, "provenance.transcript_sha256").lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise _error(
                "provenance.transcript_sha256",
                "expected 64 hexadecimal characters",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "generator": {"name": self.generator_name, "version": self.generator_version},
            "created_at_utc": self.created_at_utc,
            "alignment": {"match_threshold": self.match_threshold,
                          "good_match_threshold": self.good_match_threshold},
            "transcript_sha256": self.transcript_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProjectProvenance":
        d = _mapping(data, "provenance")
        generator = _mapping(d.get("generator"), "provenance.generator")
        alignment = _mapping(d.get("alignment"), "provenance.alignment")
        result = cls(
            generator_name=_string(generator.get("name"), "provenance.generator.name"),
            generator_version=_string(generator.get("version"), "provenance.generator.version"),
            created_at_utc=_string(d.get("created_at_utc"), "provenance.created_at_utc"),
            match_threshold=_number(alignment.get("match_threshold"), "provenance.alignment.match_threshold"),
            good_match_threshold=_number(alignment.get("good_match_threshold"), "provenance.alignment.good_match_threshold"),
            transcript_sha256=_string(
                d.get("transcript_sha256"), "provenance.transcript_sha256"
            ),
        )
        result.validate()
        return result


@dataclass(frozen=True)
class AutomaticSelectionSnapshot:
    recommended_candidate_id: str | None
    selection_reason: str
    previous_selection_end_s: float
    chronological_floor_s: float
    retake_floor_s: float | None
    strict_floor_s: float
    applied_floor_s: float
    fallback_used: bool = False
    rejected_candidates: tuple[CandidateRejection, ...] = field(default_factory=tuple)

    @classmethod
    def from_decision(cls, decision: SentenceDecision) -> "AutomaticSelectionSnapshot":
        return cls(
            recommended_candidate_id=decision.selected_candidate_id,
            selection_reason=decision.selection_reason,
            previous_selection_end_s=decision.previous_selection_end_s,
            chronological_floor_s=decision.chronological_floor_s,
            retake_floor_s=decision.retake_floor_s,
            strict_floor_s=decision.strict_floor_s,
            applied_floor_s=decision.applied_floor_s,
            fallback_used=decision.fallback_used,
            rejected_candidates=tuple(decision.rejected_candidates),
        )

    def validate(self, candidate_ids: set[str], path: str) -> None:
        if self.recommended_candidate_id is not None and self.recommended_candidate_id not in candidate_ids:
            raise _error(f"{path}.recommended_candidate_id", "does not identify a segment candidate")
        _string(self.selection_reason, f"{path}.selection_reason")
        _number(self.previous_selection_end_s, f"{path}.previous_selection_end_s")
        _number(self.chronological_floor_s, f"{path}.chronological_floor_s")
        _optional_number(self.retake_floor_s, f"{path}.retake_floor_s")
        _number(self.strict_floor_s, f"{path}.strict_floor_s")
        _number(self.applied_floor_s, f"{path}.applied_floor_s")
        if not isinstance(self.fallback_used, bool):
            raise _error(f"{path}.fallback_used", "expected a boolean")
        seen: set[str] = set()
        for rejection in self.rejected_candidates:
            if rejection.candidate_id not in candidate_ids:
                raise _error(f"{path}.rejected_candidates", "references an unknown candidate")
            if rejection.candidate_id in seen:
                raise _error(f"{path}.rejected_candidates", "contains a duplicate candidate")
            seen.add(rejection.candidate_id)
            if not rejection.reasons or any(not reason for reason in rejection.reasons):
                raise _error(f"{path}.rejected_candidates", "reasons must be non-empty strings")

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommended_candidate_id": self.recommended_candidate_id,
            "selection_reason": self.selection_reason,
            "previous_selection_end_s": self.previous_selection_end_s,
            "chronological_floor_s": self.chronological_floor_s,
            "retake_floor_s": self.retake_floor_s,
            "strict_floor_s": self.strict_floor_s,
            "applied_floor_s": self.applied_floor_s,
            "fallback_used": self.fallback_used,
            "rejected_candidates": [item.to_dict() for item in self.rejected_candidates],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], path: str) -> "AutomaticSelectionSnapshot":
        d = _mapping(data, path)
        recommended = d.get("recommended_candidate_id")
        rejections_data = d.get("rejected_candidates", [])
        if not isinstance(rejections_data, list):
            raise _error(f"{path}.rejected_candidates", "expected an array")
        rejections: list[CandidateRejection] = []
        for index, raw in enumerate(rejections_data):
            rd = _mapping(raw, f"{path}.rejected_candidates[{index}]")
            reasons = rd.get("reasons")
            if not isinstance(reasons, list) or not all(isinstance(reason, str) for reason in reasons):
                raise _error(f"{path}.rejected_candidates[{index}].reasons", "expected an array of strings")
            rejections.append(CandidateRejection(
                _string(rd.get("candidate_id"), f"{path}.rejected_candidates[{index}].candidate_id"),
                tuple(reasons),
            ))
        fallback = d.get("fallback_used", False)
        if not isinstance(fallback, bool):
            raise _error(f"{path}.fallback_used", "expected a boolean")
        return cls(
            recommended_candidate_id=None if recommended is None else _string(recommended, f"{path}.recommended_candidate_id"),
            selection_reason=_string(d.get("selection_reason"), f"{path}.selection_reason"),
            previous_selection_end_s=_number(d.get("previous_selection_end_s"), f"{path}.previous_selection_end_s"),
            chronological_floor_s=_number(d.get("chronological_floor_s"), f"{path}.chronological_floor_s"),
            retake_floor_s=_optional_number(d.get("retake_floor_s"), f"{path}.retake_floor_s"),
            strict_floor_s=_number(d.get("strict_floor_s"), f"{path}.strict_floor_s"),
            applied_floor_s=_number(d.get("applied_floor_s"), f"{path}.applied_floor_s"),
            fallback_used=fallback,
            rejected_candidates=tuple(rejections),
        )


def _candidate_from_dict(data: Mapping[str, Any], path: str) -> AlignmentCandidate:
    d = _mapping(data, path)
    refinements = d.get("refinements", [])
    if not isinstance(refinements, list) or not all(isinstance(item, str) for item in refinements):
        raise _error(f"{path}.refinements", "expected an array of strings")
    candidate = AlignmentCandidate(
        id=_string(d.get("id"), f"{path}.id"),
        source_start_s=_number(d.get("source_start_s"), f"{path}.source_start_s", minimum=0.0),
        source_end_s=_number(d.get("source_end_s"), f"{path}.source_end_s", minimum=0.0),
        score=_number(d.get("score"), f"{path}.score"),
        transcript_text=_string(d.get("transcript_text", ""), f"{path}.transcript_text", allow_empty=True),
        segment_start_idx=_optional_int(d.get("segment_start_idx"), f"{path}.segment_start_idx"),
        segment_end_idx=_optional_int(d.get("segment_end_idx"), f"{path}.segment_end_idx"),
        refinements=tuple(refinements),
    )
    if candidate.source_end_s <= candidate.source_start_s:
        raise _error(path, "source_end_s must be greater than source_start_s")
    if not 0.0 <= candidate.score <= 1.0:
        raise _error(f"{path}.score", "must be between 0 and 1")
    if (candidate.segment_start_idx is None) != (candidate.segment_end_idx is None):
        raise _error(path, "segment indices must both be null or both be integers")
    if (candidate.segment_start_idx is not None and
            candidate.segment_end_idx < candidate.segment_start_idx):
        raise _error(path, "segment_end_idx must be >= segment_start_idx")
    duration = d.get("duration_s")
    if duration is not None and not math.isclose(
        _number(duration, f"{path}.duration_s", minimum=0.0), candidate.duration_s,
        abs_tol=1e-9,
    ):
        raise _error(f"{path}.duration_s", "does not equal source_end_s - source_start_s")
    return candidate


@dataclass
class EditSegment:
    id: str
    paragraph_idx: int
    sentence_idx: int
    script_text: str
    normalized_script_text: str
    candidates: tuple[AlignmentCandidate, ...]
    automatic_selection: AutomaticSelectionSnapshot
    selected_candidate_id: str | None
    source_start_s: float | None
    source_end_s: float | None
    # Positive means audio should play later than video. Persisted now; the
    # renderer will apply it in a later stage.
    audio_offset_s: float = 0.0

    @classmethod
    def from_decision(cls, decision: SentenceDecision) -> "EditSegment":
        selected = decision.selected_candidate
        return cls(
            id=f"p{decision.sentence.paragraph_idx}:s{decision.sentence.sentence_idx}",
            paragraph_idx=decision.sentence.paragraph_idx,
            sentence_idx=decision.sentence.sentence_idx,
            script_text=decision.sentence.text,
            normalized_script_text=decision.sentence.normalized,
            candidates=tuple(decision.candidates),
            automatic_selection=AutomaticSelectionSnapshot.from_decision(decision),
            selected_candidate_id=decision.selected_candidate_id,
            source_start_s=None if selected is None else selected.source_start_s,
            source_end_s=None if selected is None else selected.source_end_s,
        )

    @property
    def selected_candidate(self) -> AlignmentCandidate | None:
        if self.selected_candidate_id is None:
            return None
        return next((item for item in self.candidates if item.id == self.selected_candidate_id), None)

    @property
    def duration_s(self) -> float | None:
        if self.source_start_s is None or self.source_end_s is None:
            return None
        return self.source_end_s - self.source_start_s

    @property
    def transcript_text(self) -> str:
        candidate = self.selected_candidate
        return "" if candidate is None else candidate.transcript_text

    @property
    def alignment_score(self) -> float | None:
        candidate = self.selected_candidate
        return None if candidate is None else candidate.score

    @property
    def is_modified(self) -> bool:
        if (
            self.selected_candidate_id
            != self.automatic_selection.recommended_candidate_id
        ):
            return True
        candidate = self.selected_candidate
        if candidate is None:
            return self.audio_offset_s != 0.0
        return (
            self.source_start_s != candidate.source_start_s
            or self.source_end_s != candidate.source_end_s
            or self.audio_offset_s != 0.0
        )

    def select_candidate(self, candidate_id: str | None) -> None:
        if candidate_id is None:
            self.selected_candidate_id = None
            self.source_start_s = None
            self.source_end_s = None
            return
        candidate = next((item for item in self.candidates if item.id == candidate_id), None)
        if candidate is None:
            raise _error("selected_candidate_id", f"unknown candidate {candidate_id!r}")
        self.selected_candidate_id = candidate.id
        self.source_start_s = candidate.source_start_s
        self.source_end_s = candidate.source_end_s

    def set_source_bounds(self, start_s: float, end_s: float) -> None:
        if self.selected_candidate_id is None:
            raise _error("source_bounds", "cannot set bounds without a selected candidate")
        start = _number(start_s, "source_start_s", minimum=0.0)
        end = _number(end_s, "source_end_s", minimum=0.0)
        if end <= start:
            raise _error("source_bounds", "end must be greater than start")
        self.source_start_s, self.source_end_s = start, end

    def validate(self, path: str = "segment") -> None:
        _string(self.id, f"{path}.id")
        for name, value in (("paragraph_idx", self.paragraph_idx), ("sentence_idx", self.sentence_idx)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise _error(f"{path}.{name}", "expected a non-negative integer")
        expected_id = f"p{self.paragraph_idx}:s{self.sentence_idx}"
        if self.id != expected_id:
            raise _error(f"{path}.id", f"expected {expected_id!r}")
        _string(self.script_text, f"{path}.script_text")
        _string(self.normalized_script_text, f"{path}.normalized_script_text", allow_empty=True)
        if not isinstance(self.candidates, tuple):
            raise _error(f"{path}.candidates", "expected immutable candidate evidence")
        ids: set[str] = set()
        for index, candidate in enumerate(self.candidates):
            candidate_path = f"{path}.candidates[{index}]"
            if not isinstance(candidate, AlignmentCandidate):
                raise _error(candidate_path, "expected AlignmentCandidate")
            _candidate_from_dict(candidate.to_dict(), candidate_path)
            if candidate.id in ids:
                raise _error(candidate_path, f"duplicate candidate id {candidate.id!r}")
            ids.add(candidate.id)
        self.automatic_selection.validate(ids, f"{path}.automatic_selection")
        if self.selected_candidate_id is None:
            if self.source_start_s is not None or self.source_end_s is not None:
                raise _error(path, "unselected segments must have null source bounds")
        else:
            if self.selected_candidate_id not in ids:
                raise _error(f"{path}.selected_candidate_id", "does not identify a segment candidate")
            if self.source_start_s is None or self.source_end_s is None:
                raise _error(path, "selected segments require both source bounds")
            start = _number(self.source_start_s, f"{path}.source_start_s", minimum=0.0)
            end = _number(self.source_end_s, f"{path}.source_end_s", minimum=0.0)
            if end <= start:
                raise _error(path, "source_end_s must be greater than source_start_s")
        _number(self.audio_offset_s, f"{path}.audio_offset_s")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "paragraph_idx": self.paragraph_idx,
            "sentence_idx": self.sentence_idx, "script_text": self.script_text,
            "normalized_script_text": self.normalized_script_text,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "automatic_selection": self.automatic_selection.to_dict(),
            "selected_candidate_id": self.selected_candidate_id,
            "source_start_s": self.source_start_s, "source_end_s": self.source_end_s,
            "audio_offset_s": self.audio_offset_s,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], path: str = "segment") -> "EditSegment":
        d = _mapping(data, path)
        candidates_data = d.get("candidates")
        if not isinstance(candidates_data, list):
            raise _error(f"{path}.candidates", "expected an array")
        candidates = tuple(
            _candidate_from_dict(item, f"{path}.candidates[{index}]")
            for index, item in enumerate(candidates_data)
        )
        selected = d.get("selected_candidate_id")
        paragraph_idx = _optional_int(d.get("paragraph_idx"), f"{path}.paragraph_idx")
        sentence_idx = _optional_int(d.get("sentence_idx"), f"{path}.sentence_idx")
        if paragraph_idx is None or sentence_idx is None:
            raise _error(path, "paragraph_idx and sentence_idx cannot be null")
        result = cls(
            id=_string(d.get("id"), f"{path}.id"),
            paragraph_idx=paragraph_idx, sentence_idx=sentence_idx,
            script_text=_string(d.get("script_text"), f"{path}.script_text"),
            normalized_script_text=_string(d.get("normalized_script_text", ""), f"{path}.normalized_script_text", allow_empty=True),
            candidates=candidates,
            automatic_selection=AutomaticSelectionSnapshot.from_dict(
                d.get("automatic_selection"), f"{path}.automatic_selection"
            ),
            selected_candidate_id=None if selected is None else _string(selected, f"{path}.selected_candidate_id"),
            source_start_s=_optional_number(d.get("source_start_s"), f"{path}.source_start_s", minimum=0.0),
            source_end_s=_optional_number(d.get("source_end_s"), f"{path}.source_end_s", minimum=0.0),
            audio_offset_s=_number(d.get("audio_offset_s", 0.0), f"{path}.audio_offset_s"),
        )
        result.validate(path)
        return result


def _retake_from_dict(data: Mapping[str, Any], path: str) -> RetakeDecision:
    d = _mapping(data, path)
    def string_tuple(name: str) -> tuple[str, ...]:
        raw = d.get(name, [])
        if not isinstance(raw, list) or not all(isinstance(item, str) and item for item in raw):
            raise _error(f"{path}.{name}", "expected an array of non-empty strings")
        return tuple(raw)
    paragraph_idx = _optional_int(d.get("paragraph_idx"), f"{path}.paragraph_idx")
    if paragraph_idx is None:
        raise _error(f"{path}.paragraph_idx", "cannot be null")
    floor_id = d.get("floor_candidate_id")
    return RetakeDecision(
        paragraph_idx=paragraph_idx,
        candidate_ids=string_tuple("candidate_ids"),
        good_candidate_ids=string_tuple("good_candidate_ids"),
        strong_candidate_ids=string_tuple("strong_candidate_ids"),
        floor_candidate_id=None if floor_id is None else _string(floor_id, f"{path}.floor_candidate_id"),
        floor_s=_optional_number(d.get("floor_s"), f"{path}.floor_s", minimum=0.0),
        reason=_string(d.get("reason"), f"{path}.reason"),
    )


@dataclass
class EditProject:
    """Canonical editable state; derived render ranges are never persisted."""

    KIND: ClassVar[str] = PROJECT_KIND
    SCHEMA_VERSION: ClassVar[int] = PROJECT_SCHEMA_VERSION

    project_id: str
    source: SourceSnapshot
    script: ScriptSnapshot
    transcript: TranscriptSnapshot
    settings: dict[str, Any]
    provenance: ProjectProvenance
    segments: list[EditSegment]
    retake_decisions: list[RetakeDecision] = field(default_factory=list)
    # Global offset uses the same sign convention as the per-segment value.
    audio_offset_s: float = 0.0
    # Reserved transport slots; overlay editing is intentionally not active yet.
    overlays: list[dict[str, Any]] = field(default_factory=list)
    extensions: dict[str, Any] = field(default_factory=dict)

    @property
    def source_video(self) -> str:
        return self.source.path

    @property
    def script_path(self) -> str:
        return self.script.path

    @classmethod
    def from_alignment_plan(
        cls,
        plan: AlignmentPlan,
        source_video: str | Path,
        script_path: str | Path,
        transcript: TranscriptSnapshot | Mapping[str, Any],
        settings: Mapping[str, Any],
        *,
        script_score: float | None = None,
        project_id: str | None = None,
        source_duration_s: float | None = None,
        source_size_bytes: int | None = None,
        source_mtime_ns: int | None = None,
        script_sha256: str | None = None,
        generator_version: str = "0.1.0",
        created_at_utc: str | None = None,
    ) -> "EditProject":
        """Purely project plan data; never reads media/script paths or renders."""
        if not isinstance(plan, AlignmentPlan):
            raise ProjectValidationError("plan: expected AlignmentPlan")
        if isinstance(transcript, Mapping):
            transcript_data = copy.deepcopy(dict(transcript))
            raw_segments = transcript_data.get("segments")
            if isinstance(raw_segments, list):
                transcript_data["text"] = " ".join(
                    str(segment.get("text", "")).strip()
                    for segment in raw_segments
                    if isinstance(segment, Mapping)
                    and str(segment.get("text", "")).strip()
                )
            transcript_snapshot = TranscriptSnapshot.from_dict(transcript_data)
        else:
            transcript_snapshot = copy.deepcopy(transcript)
        if not isinstance(transcript_snapshot, TranscriptSnapshot):
            raise ProjectValidationError("transcript: expected TranscriptSnapshot or object")
        created = created_at_utc or datetime.now(timezone.utc).isoformat()
        result = cls(
            project_id=project_id or str(uuid.uuid4()),
            source=SourceSnapshot(str(source_video), source_duration_s,
                                  source_size_bytes, source_mtime_ns),
            script=ScriptSnapshot(str(script_path), script_sha256, script_score),
            transcript=transcript_snapshot,
            settings=_json_copy(dict(settings), "settings"),
            provenance=ProjectProvenance(
                generator_version=generator_version,
                created_at_utc=created,
                match_threshold=plan.match_threshold,
                good_match_threshold=plan.good_match_threshold,
                transcript_sha256=_json_sha256(
                    transcript_snapshot.to_dict(), "transcript"
                ),
            ),
            segments=[EditSegment.from_decision(decision) for decision in plan.decisions],
            retake_decisions=list(plan.retakes),
        )
        result.validate()
        return result

    def validate(self) -> None:
        _string(self.project_id, "project_id")
        if not isinstance(self.source, SourceSnapshot):
            raise _error("source", "expected SourceSnapshot")
        if not isinstance(self.script, ScriptSnapshot):
            raise _error("script", "expected ScriptSnapshot")
        if not isinstance(self.transcript, TranscriptSnapshot):
            raise _error("transcript", "expected TranscriptSnapshot")
        if not isinstance(self.provenance, ProjectProvenance):
            raise _error("provenance", "expected ProjectProvenance")
        self.source.validate()
        self.script.validate()
        self.transcript.validate()
        self.provenance.validate()
        if not isinstance(self.settings, dict):
            raise _error("settings", "expected an object")
        _json_copy(self.settings, "settings")
        _number(self.audio_offset_s, "audio_offset_s")
        if not isinstance(self.overlays, list) or not all(
            isinstance(overlay, dict) for overlay in self.overlays
        ):
            raise _error("overlays", "expected an array of objects")
        if not isinstance(self.extensions, dict):
            raise _error("extensions", "expected an object")
        _json_copy(self.overlays, "overlays")
        _json_copy(self.extensions, "extensions")
        # The timeline layer lives in extensions so schema-v1 projects remain
        # readable.  When present, however, it is a first-class validated
        # editing contract rather than opaque untrusted JSON.
        self.source_timeline_state()
        # Slide assets follow the same extension rule.  The render/timeline
        # integration arrives in a later stage, but malformed manifests must
        # never be silently persisted in an otherwise valid project.
        self.slides_state()
        transcript_sha256 = _json_sha256(self.transcript.to_dict(), "transcript")
        if self.provenance.transcript_sha256 != transcript_sha256:
            raise _error(
                "provenance.transcript_sha256",
                "does not match the transcript snapshot",
            )
        if not isinstance(self.segments, list):
            raise _error("segments", "expected an array")
        segment_ids: set[str] = set()
        sentence_keys: set[tuple[int, int]] = set()
        candidate_ids: set[str] = set()
        previous_key: tuple[int, int] | None = None
        for index, segment in enumerate(self.segments):
            path = f"segments[{index}]"
            if not isinstance(segment, EditSegment):
                raise _error(path, "expected EditSegment")
            segment.validate(path)
            key = (segment.paragraph_idx, segment.sentence_idx)
            if segment.id in segment_ids:
                raise _error(f"{path}.id", "duplicate segment id")
            if key in sentence_keys:
                raise _error(path, "duplicate script coordinates")
            if previous_key is not None and key <= previous_key:
                raise _error(path, "segments must be in increasing script order")
            previous_key = key
            segment_ids.add(segment.id)
            sentence_keys.add(key)
            for candidate in segment.candidates:
                if candidate.id in candidate_ids:
                    raise _error(f"{path}.candidates", f"globally duplicate candidate id {candidate.id!r}")
                candidate_ids.add(candidate.id)
                if (
                    candidate.segment_end_idx is not None
                    and candidate.segment_end_idx >= len(self.transcript.segments)
                ):
                    raise _error(
                        f"{path}.candidates",
                        "references a transcript segment outside the snapshot",
                    )
                if (
                    self.source.duration_s is not None
                    and candidate.source_end_s > self.source.duration_s + 1e-6
                ):
                    raise _error(
                        f"{path}.candidates",
                        "candidate range exceeds known source duration",
                    )
            if (
                self.source.duration_s is not None
                and segment.source_end_s is not None
                and segment.source_end_s > self.source.duration_s + 1e-6
            ):
                raise _error(
                    path,
                    "editable range exceeds known source duration",
                )
        if not isinstance(self.retake_decisions, list):
            raise _error("retake_decisions", "expected an array")
        retake_paragraphs: set[int] = set()
        for index, retake in enumerate(self.retake_decisions):
            path = f"retake_decisions[{index}]"
            if not isinstance(retake, RetakeDecision):
                raise _error(path, "expected RetakeDecision")
            if retake.paragraph_idx in retake_paragraphs:
                raise _error(path, "duplicate paragraph retake evidence")
            retake_paragraphs.add(retake.paragraph_idx)
            ids = set(retake.candidate_ids)
            if len(ids) != len(retake.candidate_ids):
                raise _error(f"{path}.candidate_ids", "contains duplicates")
            if not set(retake.good_candidate_ids).issubset(ids):
                raise _error(path, "good candidates must belong to candidate_ids")
            if not set(retake.strong_candidate_ids).issubset(set(retake.good_candidate_ids)):
                raise _error(path, "strong candidates must belong to good_candidate_ids")
            if retake.floor_candidate_id is not None and retake.floor_candidate_id not in ids:
                raise _error(path, "floor candidate must belong to candidate_ids")
            if not ids.issubset(candidate_ids):
                raise _error(path, "references candidates outside the project inventory")
            if (retake.floor_candidate_id is None) != (retake.floor_s is None):
                raise _error(path, "floor candidate and floor_s must both be set or both be null")
            _optional_number(retake.floor_s, f"{path}.floor_s", minimum=0.0)
            _string(retake.reason, f"{path}.reason")

    def to_matches(self) -> list[MatchCandidate]:
        self.validate()
        return self._matches_for_selection(automatic=False)

    def _matches_for_selection(self, *, automatic: bool) -> list[MatchCandidate]:
        """Project sentence evidence into legacy matches.

        The automatic projection intentionally reads immutable candidate evidence,
        while the normal projection honours the user's current candidate and
        bounds.  Keeping both projections lets the timeline distinguish the IA
        proposal from the effective edit without duplicating either one.
        """
        self.validate()
        matches: list[MatchCandidate] = []
        for segment in self.segments:
            candidate_id = (
                segment.automatic_selection.recommended_candidate_id
                if automatic
                else segment.selected_candidate_id
            )
            candidate = next(
                (item for item in segment.candidates if item.id == candidate_id),
                None,
            )
            if candidate is None:
                continue
            if automatic:
                start, end = candidate.source_start_s, candidate.source_end_s
            else:
                assert segment.source_start_s is not None and segment.source_end_s is not None
                start, end = segment.source_start_s, segment.source_end_s
            sentence = GuionSentence(
                segment.paragraph_idx, segment.sentence_idx,
                segment.script_text, segment.normalized_script_text,
            )
            matches.append(MatchCandidate(
                sentence=sentence, start=start,
                end=end, score=candidate.score,
                transcript_text=candidate.transcript_text,
                segment_start_idx=candidate.segment_start_idx,
                segment_end_idx=candidate.segment_end_idx,
                refinements=candidate.refinements,
            ))
        return matches

    def _compile_legacy_matches(
        self, matches: list[MatchCandidate]
    ) -> list[tuple[float, float]]:
        """Compile match evidence using the historical output rules."""
        if any(
            current.start < previous.start
            for previous, current in zip(matches, matches[1:])
        ):
            raise _error(
                "segments",
                "selected takes must remain in chronological source order",
            )
        clean = merge_ranges([(item.start, item.end) for item in matches], self.settings)
        raw_duration = self.transcript.raw_duration_s
        limit = raw_duration + 5.0
        clean = pad_ranges(clean, limit, self.settings)
        clean = split_on_word_gaps(clean, self.transcript.segments, self.settings)
        if clean:
            start, end = clean[-1]
            clean[-1] = (start, min(limit, end + 1.0))
        return clean

    def compile_clean_ranges(self) -> list[tuple[float, float]]:
        """Reproduce the legacy merge/pad/gap-split/tail range compilation."""
        return self._compile_legacy_matches(self.to_matches())

    def compile_automatic_ranges(self) -> list[tuple[float, float]]:
        """Return the original CREAcut recommendation using immutable evidence."""
        return self._compile_legacy_matches(
            self._matches_for_selection(automatic=True)
        )

    def source_timeline_state(self):
        """Return the optional persisted source-timeline layer, if present."""
        from .source_timeline import (
            SourceTimelineError,
            SourceTimelineState,
            TIMELINE_EXTENSION_KEY,
        )

        payload = self.extensions.get(TIMELINE_EXTENSION_KEY)
        if payload is None:
            return None
        try:
            return SourceTimelineState.from_dict(payload)
        except SourceTimelineError as exc:
            raise _error(f"extensions.{TIMELINE_EXTENSION_KEY}", str(exc)) from exc

    def slides_state(self):
        """Return the optional, validated imported-slide manifest."""
        from .slides import (
            SLIDES_EXTENSION_KEY,
            SlideTrackState,
            SlidesStateError,
        )

        payload = self.extensions.get(SLIDES_EXTENSION_KEY)
        if payload is None:
            return None
        try:
            return SlideTrackState.from_dict(payload)
        except SlidesStateError as exc:
            raise _error(f"extensions.{SLIDES_EXTENSION_KEY}", str(exc)) from exc

    def set_slides_state(self, state) -> None:
        """Persist a validated slide manifest without changing schema v1."""
        from .slides import SlideTrackState, SlidesStateError

        if not isinstance(state, SlideTrackState):
            raise _error("slides", "expected SlideTrackState")
        try:
            state.validate()
        except SlidesStateError as exc:
            raise _error("slides", str(exc)) from exc
        self.extensions["creacut.slides"] = state.to_dict()

    def set_source_timeline_state(self, state) -> None:
        """Persist a validated manual source-timeline layer in extensions."""
        from .source_timeline import (
            SourceTimelineError,
            SourceTimelineState,
            TIMELINE_EXTENSION_KEY,
        )

        if not isinstance(state, SourceTimelineState):
            raise _error(
                f"extensions.{TIMELINE_EXTENSION_KEY}",
                "expected SourceTimelineState",
            )
        try:
            payload = state.to_dict()
        except SourceTimelineError as exc:
            raise _error(f"extensions.{TIMELINE_EXTENSION_KEY}", str(exc)) from exc
        self.extensions[TIMELINE_EXTENSION_KEY] = payload

    def source_timeline(self, *, source_duration_s: float | None = None):
        """Build full-source keep/discard regions for the editor.

        A duration is deliberately required.  Whisper's final timestamp is an
        analysis limit, not proof of the MP4's duration, so it is not used as a
        silent substitute for the source-media clock.
        """
        from .source_timeline import (
            SourceTimelineError,
            SourceTimelineProjection,
        )

        state = self.source_timeline_state()
        duration = (
            self.source.duration_s
            if source_duration_s is None
            else float(source_duration_s)
        )
        if duration is None and state is not None:
            duration = state.source_duration_s
        if duration is None:
            raise _error(
                "source.duration_s",
                "is required to build a full source timeline",
            )
        try:
            return SourceTimelineProjection.build(
                duration_s=duration,
                automatic_keep_ranges=self.compile_automatic_ranges(),
                effective_keep_ranges=self.compile_render_ranges(
                    source_duration_s=duration
                ),
                state=state,
                segment_ranges=[
                    (segment.id, segment.source_start_s, segment.source_end_s)
                    for segment in self.segments
                    if segment.source_start_s is not None
                    and segment.source_end_s is not None
                ],
            )
        except SourceTimelineError as exc:
            raise _error("source_timeline", str(exc)) from exc

    def compile_render_ranges(
        self, *, source_duration_s: float | None = None
    ) -> list[tuple[float, float]]:
        """Compile the exact current render ranges.

        Projects without a source-timeline extension retain the historical
        output byte-for-byte.  Once the user edits source regions, only the
        explicit manual decisions are applied; legacy padding/merging is never
        re-run after that layer.
        """
        state = self.source_timeline_state()
        legacy_ranges = self.compile_clean_ranges()
        if state is None:
            return legacy_ranges
        from .source_timeline import (
            SourceTimelineProjection,
            SourceTimelineError,
            apply_overrides,
        )

        duration = source_duration_s
        if duration is None:
            duration = self.source.duration_s
        if duration is None:
            duration = state.source_duration_s
        try:
            projection = SourceTimelineProjection.build(
                duration_s=duration,
                automatic_keep_ranges=self.compile_automatic_ranges(),
                effective_keep_ranges=apply_overrides(legacy_ranges, state),
                state=state,
            )
        except SourceTimelineError as exc:
            raise _error("source_timeline", str(exc)) from exc
        return list(projection.keep_ranges)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "kind": self.KIND, "schema_version": self.SCHEMA_VERSION,
            "project_id": self.project_id, "source": self.source.to_dict(),
            "script": self.script.to_dict(), "transcript": self.transcript.to_dict(),
            "settings": _json_copy(self.settings, "settings"),
            "provenance": self.provenance.to_dict(),
            "audio_offset_s": self.audio_offset_s,
            "overlays": _json_copy(self.overlays, "overlays"),
            "extensions": _json_copy(self.extensions, "extensions"),
            "retake_decisions": [retake.to_dict() for retake in self.retake_decisions],
            "segments": [segment.to_dict() for segment in self.segments],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EditProject":
        d = _mapping(data, "project")
        if d.get("kind") != cls.KIND:
            raise _error("kind", f"expected {cls.KIND!r}")
        version = d.get("schema_version")
        if isinstance(version, bool) or not isinstance(version, int):
            raise _error("schema_version", "expected an integer")
        if version != cls.SCHEMA_VERSION:
            direction = "newer" if version > cls.SCHEMA_VERSION else "unsupported older"
            raise _error("schema_version", f"{direction} project version {version}; supported version is {cls.SCHEMA_VERSION}")
        settings = _required(d, "settings", "project")
        if not isinstance(settings, dict):
            raise _error("settings", "expected an object")
        segments_data = _required(d, "segments", "project")
        retakes_data = _required(d, "retake_decisions", "project")
        if not isinstance(segments_data, list):
            raise _error("segments", "expected an array")
        if not isinstance(retakes_data, list):
            raise _error("retake_decisions", "expected an array")
        overlays = _required(d, "overlays", "project")
        extensions = _required(d, "extensions", "project")
        if not isinstance(overlays, list) or not all(
            isinstance(overlay, dict) for overlay in overlays
        ):
            raise _error("overlays", "expected an array of objects")
        if not isinstance(extensions, dict):
            raise _error("extensions", "expected an object")
        result = cls(
            project_id=_string(_required(d, "project_id", "project"), "project_id"),
            source=SourceSnapshot.from_dict(_required(d, "source", "project")),
            script=ScriptSnapshot.from_dict(_required(d, "script", "project")),
            transcript=TranscriptSnapshot.from_dict(
                _required(d, "transcript", "project")
            ),
            settings=_json_copy(settings, "settings"),
            provenance=ProjectProvenance.from_dict(
                _required(d, "provenance", "project")
            ),
            segments=[EditSegment.from_dict(item, f"segments[{index}]")
                      for index, item in enumerate(segments_data)],
            retake_decisions=[_retake_from_dict(item, f"retake_decisions[{index}]")
                              for index, item in enumerate(retakes_data)],
            audio_offset_s=_number(
                _required(d, "audio_offset_s", "project"), "audio_offset_s"
            ),
            overlays=_json_copy(overlays, "overlays"),
            extensions=_json_copy(extensions, "extensions"),
        )
        result.validate()
        return result
