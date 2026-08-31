"""Unit tests for reconstruction domain models — §21.2."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.pages_to_audio.domain.models.reconstruction import (
    AlternativesModel,
    Completeness,
    ExamReconstructionResult,
    ReconstructedQuestion,
)


def test_valid_question() -> None:
    q = ReconstructedQuestion(
        question_number=5,
        text="Qual das alternativas abaixo está correta?",
        alternatives=AlternativesModel(A="op1", B="op2", C="op3"),
        completeness=Completeness.COMPLETE,
    )
    assert q.question_number == 5
    assert q.alternatives.non_empty() == {"A": "op1", "B": "op2", "C": "op3"}
    assert q.alternatives.valid_letters() == {"A", "B", "C"}


def test_question_requires_at_least_two_alternatives() -> None:
    with pytest.raises(ValidationError):
        ReconstructedQuestion(
            question_number=1,
            text="Qual?",
            alternatives=AlternativesModel(A="only one"),
            completeness=Completeness.COMPLETE,
        )


def test_question_number_range() -> None:
    with pytest.raises(ValidationError):
        ReconstructedQuestion(
            question_number=0,
            text="Invalid",
            alternatives=AlternativesModel(A="x", B="y"),
            completeness=Completeness.COMPLETE,
        )


def test_exam_result_empty_questions() -> None:
    r = ExamReconstructionResult()
    assert r.questions == []


def test_exam_result_full() -> None:
    r = ExamReconstructionResult(
        questions=[
            ReconstructedQuestion(
                question_number=1,
                text="Q1",
                alternatives=AlternativesModel(A="a", B="b"),
                completeness=Completeness.COMPLETE,
            )
        ],
        prompt_version="v1",
        prompt_hash="abc123",
        provider="anthropic",
        model="claude-opus-5",
    )
    assert len(r.questions) == 1
    assert r.prompt_version == "v1"


def test_alternatives_model_non_empty() -> None:
    a = AlternativesModel(A="yes", B="no", C="", D="maybe")
    non_empty = a.non_empty()
    assert set(non_empty.keys()) == {"A", "B", "D"}
    assert "C" not in non_empty


def test_completeness_enum() -> None:
    assert Completeness.COMPLETE == "complete"
    assert Completeness.PARTIAL == "partial"
    assert Completeness.MISSING == "missing"
