"""Solver orchestration — §29, §8.7.

Solve a single question using the primary provider with fallback.
Enforces Gate 1 prerequisite via caller — Solver itself is stateless.
"""

from __future__ import annotations

from src.pages_to_audio.domain.ports.reasoning import (
    ReasoningProvider,
    SolveRequest,
    SolveResult,
)
from src.pages_to_audio.llm.fallback_policy import run_with_fallback
from src.pages_to_audio.llm.prompt_registry import get_prompt
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)


async def solve_question(
    question_number: int,
    text: str,
    alternatives: dict[str, str],
    evidence_refs: list[str],
    *,
    primary: ReasoningProvider,
    fallback: ReasoningProvider,
    max_retries: int = 2,
) -> tuple[SolveResult, str]:
    """Solve one question. Returns (result, provider_used).

    §6 invariant: caller must guarantee Gate 1 passed before calling this function.
    """
    _, prompt_version = get_prompt("solver", "v1")

    request = SolveRequest(
        question_number=question_number,
        text=text,
        alternatives=alternatives,
        evidence_refs=evidence_refs,
        prompt_version=prompt_version[:12],
    )

    result, provider = await run_with_fallback(
        lambda: primary.solve(request),
        lambda: fallback.solve(request),
        max_retries=max_retries,
        context=f"solver:q{question_number}",
    )
    logger.info(
        "solver_done",
        question=question_number,
        provider=provider,
        answer=result.answer,
    )
    return result, provider
