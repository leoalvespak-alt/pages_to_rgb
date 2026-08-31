"""Rescue engine for incomplete questions — §22, §6.6.

9 strategies in priority order.
Budget: MAX_RECONSTRUCTION_RESCUE_ROUNDS (§22, §43).
Loop-prevention: persistent attempt counter, raises when exhausted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from src.pages_to_audio.common.errors import NonRetryableError, ReasonCode
from src.pages_to_audio.domain.models.reconstruction import (
    Completeness,
    ReconstructedQuestion,
)
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)


class RescueStrategy(StrEnum):
    ALTERNATE_FRAME = "alternate_frame"
    NEW_PREPROCESSING = "new_preprocessing"
    SECONDARY_OCR = "secondary_ocr"
    DIRECTED_CROP = "directed_crop"
    VISION_PROVIDER = "vision_provider"
    ADJACENT_PAGES = "adjacent_pages"
    SPECIFIC_RECONSTRUCTION = "specific_reconstruction"
    VARIANT_COMPARISON = "variant_comparison"
    FINAL_MULTIMODAL = "final_multimodal"


STRATEGIES_IN_ORDER: list[RescueStrategy] = list(RescueStrategy)


@dataclass
class RescueAttempt:
    strategy: RescueStrategy
    success: bool
    reason_code: str
    detail: str
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    result: dict[str, Any] | None = None


@dataclass
class RescueContext:
    """Everything a rescue pass needs — no blobs, only refs."""

    session_id: str
    question_number: int
    page_refs: list[int] = field(default_factory=list)
    alternate_frame_keys: list[str] = field(default_factory=list)
    ocr_raw_keys: list[str] = field(default_factory=list)
    derived_image_keys: list[str] = field(default_factory=list)
    adjacent_page_refs: list[int] = field(default_factory=list)
    attempt_number: int = 0
    max_attempts: int = 3


class RescueEngine:
    """
    Applies the 9 rescue strategies of §22 in sequence.
    Does not implement real providers — stubs each strategy as a hook.
    Phase 6 wires OCR + Vision; Phase 8 wires LLM rescue.
    """

    def __init__(self, max_attempts: int = 3) -> None:
        self._max_attempts = max_attempts

    async def rescue_question(
        self,
        question: ReconstructedQuestion,
        ctx: RescueContext,
    ) -> tuple[ReconstructedQuestion, list[RescueAttempt]]:
        """
        Try all 9 strategies until question is COMPLETE or budget exhausted.
        Returns (possibly updated question, list of attempts).
        """
        if ctx.attempt_number >= self._max_attempts:
            raise NonRetryableError(
                f"Rescue budget exceeded for question {ctx.question_number} "
                f"after {ctx.attempt_number} rounds",
                reason_code=ReasonCode.RECONSTRUCTION_RESCUE_BUDGET_EXCEEDED,
            )

        attempts: list[RescueAttempt] = []

        for strategy in STRATEGIES_IN_ORDER:
            if question.completeness == Completeness.COMPLETE:
                break

            attempt = await self._apply_strategy(strategy, question, ctx)
            attempts.append(attempt)

            if attempt.success and attempt.result:
                updated = self._merge_result(question, attempt.result)
                if updated.completeness == Completeness.COMPLETE:
                    logger.info(
                        "rescue_success",
                        strategy=strategy,
                        question_number=ctx.question_number,
                    )
                    return updated, attempts

        logger.info(
            "rescue_exhausted",
            question_number=ctx.question_number,
            attempts=len(attempts),
            final_completeness=question.completeness,
        )
        return question, attempts

    async def _apply_strategy(
        self,
        strategy: RescueStrategy,
        question: ReconstructedQuestion,
        ctx: RescueContext,
    ) -> RescueAttempt:
        """Stub: each strategy returns a no-op. Real implementations replace these."""
        import asyncio

        await asyncio.sleep(0)

        logger.debug(
            "rescue_strategy_attempt", strategy=strategy, question_number=ctx.question_number
        )

        return RescueAttempt(
            strategy=strategy,
            success=False,
            reason_code="NOT_IMPLEMENTED",
            detail=f"Strategy {strategy} not yet implemented in this phase",
        )

    def _merge_result(
        self,
        question: ReconstructedQuestion,
        result: dict[str, Any],
    ) -> ReconstructedQuestion:
        """Merge rescue result into existing question (non-destructive)."""
        if result.get("text"):
            question = question.model_copy(update={"text": result["text"]})
        if "alternatives" in result:
            question = question.model_copy(update={"alternatives": result["alternatives"]})
        if "completeness" in result:
            question = question.model_copy(update={"completeness": result["completeness"]})
        return question
