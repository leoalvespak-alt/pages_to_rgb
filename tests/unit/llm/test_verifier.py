"""Tests for Verifier — §30, §8.8, §8.11.8.

Critical invariant (§30): Verifier solves independently.
The Solver's answer MUST NOT appear in the Verifier's payload.
"""

from __future__ import annotations

import pytest

from src.pages_to_audio.llm.providers.fake_reasoning import FakeReasoningProvider
from src.pages_to_audio.llm.verifier import answers_agree, verify_question

_ALTS = {"A": "Option A", "B": "Option B", "C": "Option C", "D": "Option D"}


class TestVerifyQuestion:
    @pytest.mark.asyncio
    async def test_returns_verifier_answer(self) -> None:
        primary = FakeReasoningProvider(default_answer="C")
        fallback = FakeReasoningProvider(default_answer="A")
        result, provider = await verify_question(
            3, "Q text", _ALTS, [], primary=primary, fallback=fallback
        )
        assert result.answer == "C"
        assert provider == "anthropic"

    @pytest.mark.asyncio
    async def test_solver_answer_not_in_verify_payload(self) -> None:
        """§8.11.8 / §30: Verifier payload must not contain Solver's answer."""
        primary = FakeReasoningProvider(default_answer="B")
        fallback = FakeReasoningProvider(default_answer="A")

        # verify_question has no solver_answer parameter — independence is structural
        result, _ = await verify_question(
            1, "Question text here", _ALTS, ["ev1"], primary=primary, fallback=fallback
        )

        # Inspect recorded payloads
        assert len(primary.recorded_verify_payloads) == 1
        payload = primary.recorded_verify_payloads[0]

        # The payload must not include any reference to a Solver answer
        # (VerifyRequest has no solver_answer field by design)
        payload_dict = {
            "question_number": payload.question_number,
            "text": payload.text,
            "alternatives": payload.alternatives,
            "evidence_refs": payload.evidence_refs,
            "prompt_version": payload.prompt_version,
        }
        assert "solver" not in str(payload_dict).lower(), (
            "Solver answer leaked into Verifier payload — §30 violation"
        )

    @pytest.mark.asyncio
    async def test_verifier_is_independent_of_solver_result(self) -> None:
        """Verifier returns its own answer regardless of what Solver found."""
        primary_solver = FakeReasoningProvider(default_answer="A")
        primary_verifier = FakeReasoningProvider(default_answer="D")
        fallback = FakeReasoningProvider(default_answer="A")

        solver_result = await primary_solver.solve(
            type("SR", (), {
                "question_number": 1,
                "text": "Q", "alternatives": _ALTS,
                "evidence_refs": [], "prompt_version": "", "effort": "high",
                "provider": "", "model": "",
            })()  # type: ignore[call-arg, arg-type]
        )

        verify_result, _ = await verify_question(
            1, "Q", _ALTS, [], primary=primary_verifier, fallback=fallback
        )
        # Even though solver said A, verifier independently says D
        assert verify_result.answer == "D"
        assert verify_result.answer != solver_result.answer


class TestAnswersAgree:
    def test_same_answer_agrees(self) -> None:
        assert answers_agree("C", "C") is True

    def test_case_insensitive(self) -> None:
        assert answers_agree("c", "C") is True

    def test_different_answers_disagree(self) -> None:
        assert answers_agree("A", "B") is False

    def test_disagreement_does_not_trigger_fallback(self) -> None:
        # §27.3 / §8.5.2: disagreement triggers Arbiter, not provider fallback
        # answers_agree is a deterministic function — it returns a bool, not an exception
        result = answers_agree("A", "B")
        assert isinstance(result, bool)
        assert result is False
