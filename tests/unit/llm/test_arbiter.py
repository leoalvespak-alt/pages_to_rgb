"""Tests for Arbiter — §31, §8.9, §8.11.5."""

from __future__ import annotations

import pytest

from src.pages_to_audio.domain.ports.reasoning import SolveResult, VerifyResult
from src.pages_to_audio.llm.arbiter import (
    ArbiterTrigger,
    arbitrate_question,
    should_arbitrate,
)
from src.pages_to_audio.llm.providers.fake_reasoning import FakeReasoningProvider

_ALTS = {"A": "opt A", "B": "opt B", "C": "opt C", "D": "opt D"}


def _solve_result(answer: str, flags: list[str] | None = None) -> SolveResult:
    return SolveResult(
        question_number=1,
        answer=answer,
        evidence_ids=[],
        ambiguity_flags=flags or [],
    )


def _verify_result(
    answer: str,
    status: str = "confident",
    flags: list[str] | None = None,
) -> VerifyResult:
    return VerifyResult(
        question_number=1,
        answer=answer,
        evidence_ids=[],
        verification_status=status,  # type: ignore[arg-type]
        ambiguity_flags=flags or [],
    )


class TestShouldArbitrate:
    def test_disagreement_triggers_arbitration(self) -> None:
        triggers = should_arbitrate(_solve_result("A"), _verify_result("B"))
        assert ArbiterTrigger.DISAGREEMENT in triggers

    def test_agreement_no_triggers(self) -> None:
        triggers = should_arbitrate(_solve_result("C"), _verify_result("C"))
        assert triggers == []

    def test_critical_ambiguity_flag_triggers(self) -> None:
        triggers = should_arbitrate(
            _solve_result("A", flags=["critical_ambiguity"]),
            _verify_result("A"),
        )
        assert ArbiterTrigger.AMBIGUITY_FLAG in triggers

    def test_ocr_conflict_triggers(self) -> None:
        triggers = should_arbitrate(
            _solve_result("A"),
            _verify_result("A"),
            ocr_conflict=True,
        )
        assert ArbiterTrigger.OCR_CONFLICT in triggers

    def test_visual_dependency_with_uncertain_status_triggers(self) -> None:
        triggers = should_arbitrate(
            _solve_result("A"),
            _verify_result("A", status="uncertain"),
            visual_dependency=True,
        )
        assert ArbiterTrigger.VISUAL_DEPENDENCY in triggers

    def test_visual_dependency_when_confident_no_trigger(self) -> None:
        triggers = should_arbitrate(
            _solve_result("A"),
            _verify_result("A", status="confident"),
            visual_dependency=True,
        )
        assert ArbiterTrigger.VISUAL_DEPENDENCY not in triggers

    def test_evidence_conflict_triggers(self) -> None:
        triggers = should_arbitrate(
            _solve_result("B"),
            _verify_result("B"),
            evidence_conflict=True,
        )
        assert ArbiterTrigger.EVIDENCE_CONFLICT in triggers

    def test_multiple_triggers_possible(self) -> None:
        triggers = should_arbitrate(
            _solve_result("A"),
            _verify_result("B"),
            ocr_conflict=True,
        )
        assert ArbiterTrigger.DISAGREEMENT in triggers
        assert ArbiterTrigger.OCR_CONFLICT in triggers


class TestArbitrateQuestion:
    @pytest.mark.asyncio
    async def test_arbiter_returns_result(self) -> None:
        primary = FakeReasoningProvider(default_answer="A", arbitrate_decision="solver_correct")
        fallback = FakeReasoningProvider(default_answer="A")
        solver = _solve_result("A")
        verifier = _verify_result("B")

        result, provider = await arbitrate_question(
            1, "Q", _ALTS, [], solver, verifier,
            primary=primary, fallback=fallback,
        )
        assert result.answer == "A"
        assert result.decision == "solver_correct"
        assert provider == "anthropic"

    @pytest.mark.asyncio
    async def test_arbiter_receives_both_answers(self) -> None:
        """§31: Arbiter input includes both Solver and Verifier answers."""
        captured: list[object] = []

        class CapturingProvider(FakeReasoningProvider):
            async def arbitrate(self, request):  # type: ignore[override]
                captured.append(request)
                return await super().arbitrate(request)

        primary = CapturingProvider(default_answer="A")
        fallback = FakeReasoningProvider(default_answer="A")
        solver = _solve_result("A")
        verifier = _verify_result("B")

        await arbitrate_question(
            1, "Q text", _ALTS, ["ev1"], solver, verifier,
            primary=primary, fallback=fallback,
        )
        assert len(captured) == 1
        req = captured[0]
        assert req.solver_answer == "A"  # type: ignore[attr-defined]
        assert req.verifier_answer == "B"  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_disagreement_triggers_arbiter_not_fallback(self) -> None:
        """§8.11.5: solver≠verifier triggers Arbiter — not provider fallback."""
        primary = FakeReasoningProvider(default_answer="C", arbitrate_decision="independent_finding")
        fallback = FakeReasoningProvider(default_answer="A")
        solver = _solve_result("A")
        verifier = _verify_result("B")

        triggers = should_arbitrate(solver, verifier)
        assert ArbiterTrigger.DISAGREEMENT in triggers

        result, provider = await arbitrate_question(
            1, "Q", _ALTS, [], solver, verifier, primary=primary, fallback=fallback
        )
        assert provider == "anthropic"  # primary was not bypassed by fallback logic
        assert primary.arbitrate_call_count == 1
        assert fallback.arbitrate_call_count == 0
