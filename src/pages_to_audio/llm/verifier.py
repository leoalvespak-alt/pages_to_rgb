"""Verifier orchestration — §30, §8.8.

§30 critical rule: the Verifier MUST solve independently.
The Solver's answer MUST NOT appear in the Verifier's payload.
Enforcement: this module never accepts a solver_answer parameter and never
passes one to the provider. Independence is verifiable by inspecting the
recorded_verify_payloads on FakeReasoningProvider (§8.11.8).
"""

from __future__ import annotations

from src.pages_to_audio.domain.ports.reasoning import (
    ReasoningProvider,
    VerifyRequest,
    VerifyResult,
)
from src.pages_to_audio.llm.fallback_policy import run_with_fallback
from src.pages_to_audio.llm.prompt_registry import get_prompt
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)


async def verify_question(
    question_number: int,
    text: str,
    alternatives: dict[str, str],
    evidence_refs: list[str],
    *,
    primary: ReasoningProvider,
    fallback: ReasoningProvider,
    max_retries: int = 2,
) -> tuple[VerifyResult, str]:
    """Verify one question independently. Returns (result, provider_used).

    §30: no solver_answer is passed — independence is structurally guaranteed
    by the absence of that parameter, not just by documentation.
    """
    _, prompt_version = get_prompt("verifier", "v1")

    request = VerifyRequest(
        question_number=question_number,
        text=text,
        alternatives=alternatives,
        evidence_refs=evidence_refs,
        prompt_version=prompt_version[:12],
    )

    result, provider = await run_with_fallback(
        lambda: primary.verify(request),
        lambda: fallback.verify(request),
        max_retries=max_retries,
        context=f"verifier:q{question_number}",
    )
    logger.info(
        "verifier_done",
        question=question_number,
        provider=provider,
        answer=result.answer,
        status=result.verification_status,
    )
    return result, provider


def answers_agree(solver_answer: str, verifier_answer: str) -> bool:
    """Deterministic comparison — §30 (comparison happens in code, not via LLM)."""
    return solver_answer.upper() == verifier_answer.upper()
