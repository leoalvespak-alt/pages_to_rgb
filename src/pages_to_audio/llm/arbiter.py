"""Arbiter orchestration — §31, §8.9.

Arbiter is triggered (§31) by:
  1. Solver ≠ Verifier answer disagreement
  2. Ambiguity flag marked critical by either
  3. OCR conflict flag set
  4. Critical visual dependency flag
  5. Evidence conflict flag

The Arbiter receives BOTH solver and verifier answers (§31) — unlike the Verifier
which must not see the Solver's answer (§30). The decision is final.
"""

from __future__ import annotations

from enum import StrEnum

from src.pages_to_audio.domain.ports.reasoning import (
    ArbitrateRequest,
    ArbitrateResult,
    ReasoningProvider,
    SolveResult,
    VerifyResult,
)
from src.pages_to_audio.llm.fallback_policy import run_with_fallback
from src.pages_to_audio.llm.prompt_registry import get_prompt
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)


class ArbiterTrigger(StrEnum):
    DISAGREEMENT = "disagreement"
    AMBIGUITY_FLAG = "ambiguity_flag"
    OCR_CONFLICT = "ocr_conflict"
    VISUAL_DEPENDENCY = "visual_dependency"
    EVIDENCE_CONFLICT = "evidence_conflict"


def should_arbitrate(
    solver: SolveResult,
    verifier: VerifyResult,
    *,
    ocr_conflict: bool = False,
    visual_dependency: bool = False,
    evidence_conflict: bool = False,
) -> list[ArbiterTrigger]:
    """Return list of active arbitration triggers (§31). Empty means no arbitration needed."""
    triggers: list[ArbiterTrigger] = []

    if solver.answer != verifier.answer:
        triggers.append(ArbiterTrigger.DISAGREEMENT)

    critical_flags = solver.ambiguity_flags + verifier.ambiguity_flags
    if any("critical" in f.lower() or "ambig" in f.lower() for f in critical_flags):
        triggers.append(ArbiterTrigger.AMBIGUITY_FLAG)

    if ocr_conflict:
        triggers.append(ArbiterTrigger.OCR_CONFLICT)
    visual_check = solver.needs_visual_recheck or verifier.verification_status == "uncertain"
    if visual_dependency and visual_check:
        triggers.append(ArbiterTrigger.VISUAL_DEPENDENCY)
    if evidence_conflict:
        triggers.append(ArbiterTrigger.EVIDENCE_CONFLICT)

    return triggers


async def arbitrate_question(
    question_number: int,
    text: str,
    alternatives: dict[str, str],
    evidence_refs: list[str],
    solver_result: SolveResult,
    verifier_result: VerifyResult,
    *,
    primary: ReasoningProvider,
    fallback: ReasoningProvider,
    max_retries: int = 2,
) -> tuple[ArbitrateResult, str]:
    """Run the Arbiter. Returns (result, provider_used)."""
    _, prompt_version = get_prompt("arbiter", "v1")

    request = ArbitrateRequest(
        question_number=question_number,
        text=text,
        alternatives=alternatives,
        solver_answer=solver_result.answer,
        verifier_answer=verifier_result.answer,
        evidence_refs=evidence_refs,
        prompt_version=prompt_version[:12],
        effort="max",
    )

    result, provider = await run_with_fallback(
        lambda: primary.arbitrate(request),
        lambda: fallback.arbitrate(request),
        max_retries=max_retries,
        context=f"arbiter:q{question_number}",
    )
    logger.info(
        "arbiter_done",
        question=question_number,
        provider=provider,
        answer=result.answer,
        decision=result.decision,
    )
    return result, provider
