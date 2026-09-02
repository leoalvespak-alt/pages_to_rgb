"""Deterministic OCR → multimodal review → Gemini resolution pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from src.pages_to_audio.ai.confidence import (
    ReviewMode,
    decide_review,
    finalize_review,
    is_critical_text,
)
from src.pages_to_audio.domain.ports.ocr import OCRProvider, OCRRequest
from src.pages_to_audio.domain.ports.reasoning import SolveRequest
from src.pages_to_audio.llm.providers.gemini_provider import GeminiProvider, ReconciliationResult


@dataclass(frozen=True, slots=True)
class ConsolidatedQuestion:
    text: str
    uncertainty_flags: list[str]
    confidence: float
    critical: bool
    review_mode: ReviewMode
    manual_review_required: bool
    ocr_provider: str
    review_provider: str
    resolution_provider: str
    resolution_model: str
    ocr_raw_storage_key: str


async def process_question(
    ocr: OCRProvider,
    gemini: GeminiProvider,
    *,
    request: OCRRequest,
    image_bytes: bytes,
    question_number: int,
    alternatives: dict[str, str],
) -> tuple[ConsolidatedQuestion, str]:
    """Run the mandated three-step flow and return consolidated text + answer."""
    ocr_result = await ocr.analyze_page(request)
    span_scores = [
        float(block["confidence"])
        for block in ocr_result.blocks
        if isinstance(block, dict)
        and isinstance(block.get("text"), str)
        and block.get("text", "").strip()
        and isinstance(block.get("confidence"), (int, float))
        and float(block["confidence"]) > 0
    ]
    initial_score = min(span_scores) if span_scores else ocr_result.confidence
    initial = decide_review(initial_score, ocr_result.text)
    flags: list[str] = []
    consolidated = ocr_result.text
    final_confidence = initial.score
    final_decision = initial
    if initial.requires_gemini:
        crop = request.hints.get("crop_bytes")
        context = request.hints.get("context_local", "")
        reconciliation = await gemini.reconcile_ocr(
            ocr_result.text,
            image_bytes,
            crop_bytes=bytes(crop) if isinstance(crop, (bytes, bytearray)) else None,
            context_local=context if isinstance(context, str) else str(context),
            ocr_spans=[
                {"text": block.get("text", ""), "confidence": block.get("confidence", 0.0)}
                for block in ocr_result.blocks
                if isinstance(block, dict) and block.get("text")
            ],
            review_mode=initial.mode.value,
            ocr_confidence=ocr_result.confidence,
        )
        if isinstance(reconciliation, ReconciliationResult):
            consolidated = reconciliation.text
            flags = reconciliation.uncertainty_flags
            critical = initial.critical or is_critical_text(consolidated)
            final_confidence = (
                reconciliation.critical_confidence
                if critical and reconciliation.critical_confidence is not None
                else reconciliation.confidence
            )
            final_decision = finalize_review(
                final_confidence,
                consolidated,
                ambiguous=reconciliation.ambiguous and reconciliation.ambiguity_affects_answer,
            )
        else:
            # Compatibility for older provider adapters returning (text, flags).
            consolidated, raw_flags = reconciliation
            flags = [str(flag) for flag in raw_flags]
            final_confidence = initial.score
            final_decision = finalize_review(final_confidence, consolidated)
    answer = await gemini.solve(
        SolveRequest(
            question_number=question_number,
            text=consolidated,
            alternatives=alternatives,
            evidence_refs=[ocr_result.raw_storage_key],
            provider="gemini",
            model=gemini.model,
        )
    )
    return (
        ConsolidatedQuestion(
            text=consolidated,
            uncertainty_flags=flags,
            confidence=final_confidence,
            critical=final_decision.critical,
            review_mode=final_decision.mode,
            manual_review_required=final_decision.manual_review_required,
            ocr_provider=ocr_result.provider,
            review_provider="gemini",
            resolution_provider="gemini",
            resolution_model=gemini.model,
            ocr_raw_storage_key=ocr_result.raw_storage_key,
        ),
        answer.answer,
    )
