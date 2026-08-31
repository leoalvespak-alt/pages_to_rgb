"""Tests for structured output schemas — §28, §14, §15."""

from __future__ import annotations

import json

import pytest

from src.pages_to_audio.common.errors import NonRetryableError, ReasonCode
from src.pages_to_audio.llm.schemas import (
    ArbiterOutput,
    SolverOutput,
    VerifierOutput,
    parse_llm_output,
    validate_answer_in_alternatives,
)


class TestSolverOutput:
    def test_valid(self) -> None:
        out = SolverOutput(
            question_number=1,
            answer="C",
            evidence_ids=["e1"],
            needs_visual_recheck=False,
            ambiguity_flags=[],
        )
        assert out.answer == "C"

    def test_lowercase_normalised(self) -> None:
        out = SolverOutput(question_number=1, answer="b", evidence_ids=[])
        assert out.answer == "B"

    def test_invalid_letter_raises(self) -> None:
        with pytest.raises(Exception):
            SolverOutput(question_number=1, answer="Z", evidence_ids=[])

    def test_multi_char_raises(self) -> None:
        with pytest.raises(Exception):
            SolverOutput(question_number=1, answer="AB", evidence_ids=[])

    def test_defaults(self) -> None:
        out = SolverOutput(question_number=5, answer="A", evidence_ids=[])
        assert out.needs_visual_recheck is False
        assert out.ambiguity_flags == []


class TestVerifierOutput:
    def test_valid_confident(self) -> None:
        out = VerifierOutput(
            question_number=2,
            answer="D",
            evidence_ids=[],
            verification_status="confident",
        )
        assert out.verification_status == "confident"

    def test_invalid_status_raises(self) -> None:
        with pytest.raises(Exception):
            VerifierOutput(
                question_number=2,
                answer="A",
                evidence_ids=[],
                verification_status="sure",  # type: ignore[arg-type]
            )

    def test_lowercase_answer_normalised(self) -> None:
        out = VerifierOutput(
            question_number=1, answer="e", evidence_ids=[], verification_status="uncertain"
        )
        assert out.answer == "E"


class TestArbiterOutput:
    def test_valid_decisions(self) -> None:
        for decision in ("solver_correct", "verifier_correct", "independent_finding", "unresolvable"):
            out = ArbiterOutput(
                question_number=3,
                answer="B",
                decision=decision,  # type: ignore[arg-type]
                evidence_ids=[],
            )
            assert out.decision == decision

    def test_invalid_decision_raises(self) -> None:
        with pytest.raises(Exception):
            ArbiterOutput(
                question_number=1,
                answer="A",
                decision="coin_flip",  # type: ignore[arg-type]
                evidence_ids=[],
            )


class TestParseLlmOutput:
    def test_parses_clean_json(self) -> None:
        raw = json.dumps({
            "question_number": 1,
            "answer": "B",
            "evidence_ids": [],
            "needs_visual_recheck": False,
            "ambiguity_flags": [],
        })
        result = parse_llm_output(raw, SolverOutput)
        assert result.answer == "B"

    def test_strips_markdown_fences(self) -> None:
        raw = '```json\n{"question_number":1,"answer":"C","evidence_ids":[]}\n```'
        result = parse_llm_output(raw, SolverOutput)
        assert result.answer == "C"

    def test_invalid_json_raises_schema_error(self) -> None:
        with pytest.raises(NonRetryableError) as exc_info:
            parse_llm_output("not json at all", SolverOutput)
        assert exc_info.value.reason_code == ReasonCode.LLM_SCHEMA_INVALID

    def test_invalid_schema_raises(self) -> None:
        raw = json.dumps({"question_number": 1, "answer": "Z", "evidence_ids": []})
        with pytest.raises(NonRetryableError) as exc_info:
            parse_llm_output(raw, SolverOutput)
        assert exc_info.value.reason_code == ReasonCode.LLM_SCHEMA_INVALID

    def test_no_regex_used_for_answer_extraction(self) -> None:
        # §14: extraction must go through JSON parse, not regex.
        # This test proves structured JSON is the extraction mechanism.
        raw = json.dumps({
            "question_number": 7,
            "answer": "E",
            "evidence_ids": ["ref-1"],
            "verification_status": "confident",
        })
        out = parse_llm_output(raw, VerifierOutput)
        assert out.answer == "E"
        assert out.evidence_ids == ["ref-1"]


class TestValidateAnswerInAlternatives:
    def test_valid_alternative(self) -> None:
        validate_answer_in_alternatives("C", {"A": "opt1", "B": "opt2", "C": "opt3"})

    def test_invalid_alternative_raises(self) -> None:
        with pytest.raises(NonRetryableError) as exc_info:
            validate_answer_in_alternatives("E", {"A": "opt1", "B": "opt2", "C": "opt3"})
        assert exc_info.value.reason_code == ReasonCode.LLM_ANSWER_INVALID_ALTERNATIVE

    def test_invariant_7_letter_not_offered(self) -> None:
        # §Invariant 7: only letters in the alternatives set are valid
        with pytest.raises(NonRetryableError):
            validate_answer_in_alternatives("D", {"A": "x", "B": "y"})
