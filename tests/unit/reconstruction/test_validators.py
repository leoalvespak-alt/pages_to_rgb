"""Unit tests for reconstruction validators — §21.4, §6.5."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.pages_to_audio.domain.models.reconstruction import (
    AlternativesModel,
    Completeness,
    ExamReconstructionResult,
    QuestionFlag,
    ReconstructedQuestion,
)
from src.pages_to_audio.reconstruction.validators import validate_reconstruction


def _q(
    number: int = 1,
    text: str = "Qual é a resposta?",
    alternatives: dict | None = None,
    completeness: Completeness = Completeness.COMPLETE,
    flags: list[QuestionFlag] | None = None,
) -> ReconstructedQuestion:
    if alternatives is None:
        alternatives = {"A": "Alfa", "B": "Beta", "C": "Gama"}
    return ReconstructedQuestion(
        question_number=number,
        text=text,
        alternatives=AlternativesModel(**{k: v for k, v in alternatives.items()}),
        completeness=completeness,
        flags=flags or [],
    )


def test_complete_question_passes_all_checks() -> None:
    result = ExamReconstructionResult(questions=[_q(1)])
    report = validate_reconstruction(result)
    assert report.issues == []
    assert report.ready_count == 1


def test_duplicate_question_numbers_flagged() -> None:
    result = ExamReconstructionResult(questions=[_q(5), _q(5)])
    report = validate_reconstruction(result)
    flagged = [i for i in report.issues if i.flag == QuestionFlag.DUPLICATE_NUMBER]
    assert len(flagged) >= 1


def test_sequence_gap_flagged() -> None:
    result = ExamReconstructionResult(questions=[_q(1), _q(3)])  # gap at 2
    report = validate_reconstruction(result)
    gap_issues = [i for i in report.issues if i.flag == QuestionFlag.SEQUENCE_GAP]
    assert len(gap_issues) >= 1


def test_missing_alternative_not_invented() -> None:
    """§60: missing alternative must NOT be filled. Pydantic rejects < 2 alternatives."""
    with pytest.raises(ValidationError):
        ReconstructedQuestion(
            question_number=1,
            text="Qual?",
            alternatives=AlternativesModel(A="Alfa"),  # only 1 — model rejects
            completeness=Completeness.COMPLETE,
        )


def test_one_alternative_only_marks_incomplete() -> None:
    """A question with only 1 alternative (produced by a buggy LLM) gets flagged."""
    # Build with 2 alternatives, then mutate for testing validators directly
    q = ReconstructedQuestion(
        question_number=1,
        text="Qual?",
        alternatives=AlternativesModel(A="ok", B="also ok"),
        completeness=Completeness.COMPLETE,
    )
    # Force a scenario where validator sees limited alternatives by clearing B
    q.alternatives.B = ""  # type: ignore[assignment]
    # Now only A is non-empty

    result = ExamReconstructionResult(questions=[q])
    report = validate_reconstruction(result)
    alt_issues = [i for i in report.issues if i.flag == QuestionFlag.ALTERNATIVES_INCOMPLETE]
    assert len(alt_issues) >= 1
    assert q.completeness != Completeness.COMPLETE


def test_empty_text_marks_missing() -> None:
    q = ReconstructedQuestion(
        question_number=1,
        text="   ",
        alternatives=AlternativesModel(A="ok", B="also"),
        completeness=Completeness.COMPLETE,
    )
    result = ExamReconstructionResult(questions=[q])
    validate_reconstruction(result)
    assert q.completeness == Completeness.MISSING


def test_visual_ambiguity_flag_degrades_complete() -> None:
    q = _q(1, completeness=Completeness.COMPLETE, flags=[QuestionFlag.VISUAL_AMBIGUITY])
    result = ExamReconstructionResult(questions=[q])
    validate_reconstruction(result)
    assert q.completeness == Completeness.PARTIAL


def test_multiple_questions_independent_counts() -> None:
    questions = [_q(i) for i in range(1, 6)]
    result = ExamReconstructionResult(questions=questions)
    report = validate_reconstruction(result)
    assert report.ready_count == 5
    assert report.incomplete_count == 0
    assert report.failed_count == 0


def test_report_total() -> None:
    q1 = _q(1, completeness=Completeness.COMPLETE)
    q2 = _q(2, completeness=Completeness.PARTIAL)
    q3 = _q(3, completeness=Completeness.MISSING)
    result = ExamReconstructionResult(questions=[q1, q2, q3])
    report = validate_reconstruction(result)
    assert report.total == 3
