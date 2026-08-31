"""Reconstruction engine — §21.1, §6.4.

Assembles per-page input → calls LLM with structured output → persists questions.
Rule: no regex extraction (CLAUDE.md rule 14), no gap filling (§60).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from src.pages_to_audio.common.errors import NonRetryableError, ReasonCode
from src.pages_to_audio.domain.models.reconstruction import ExamReconstructionResult
from src.pages_to_audio.llm.prompt_registry import get_prompt
from src.pages_to_audio.observability.logging import get_logger
from src.pages_to_audio.reconstruction.validators import validate_reconstruction

logger = get_logger(__name__)


@dataclass
class PageInput:
    page_index: int
    ocr_text: str
    image_storage_key: str | None = None
    derived_keys: list[str] = field(default_factory=list)
    layout_hints: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReconstructionInput:
    session_id: str
    pages: list[PageInput]
    expected_questions: int = 0
    prompt_name: str = "reconstruction"
    prompt_version: str = "v1"


class ReconstructionEngine:
    """
    LLM-backed reconstruction with structured output and Pydantic validation.
    Requires an async callable that accepts (prompt: str, input_data: dict)
    and returns a dict (the LLM structured response).
    """

    def __init__(self, llm_callable: Any) -> None:
        self._llm = llm_callable

    async def reconstruct(self, inp: ReconstructionInput) -> ExamReconstructionResult:
        prompt_content, prompt_hash = get_prompt(inp.prompt_name, inp.prompt_version)

        # Build window of pages (with overlap for cross-page questions)
        page_data = [
            {"page_index": p.page_index, "ocr_text": p.ocr_text, "layout": p.layout_hints}
            for p in inp.pages
        ]

        llm_input = {
            "pages": page_data,
            "expected_questions": inp.expected_questions,
        }

        import time

        t0 = time.monotonic()
        try:
            raw_response = await self._llm(prompt_content, llm_input)
        except Exception as exc:
            raise NonRetryableError(
                f"LLM reconstruction call failed: {exc}",
                reason_code=ReasonCode.RECONSTRUCTION_SCHEMA_INVALID,
            ) from exc
        latency_ms = (time.monotonic() - t0) * 1000

        try:
            result = ExamReconstructionResult.model_validate(raw_response)
        except ValidationError as exc:
            raise NonRetryableError(
                f"LLM reconstruction response failed Pydantic validation: {exc}",
                reason_code=ReasonCode.RECONSTRUCTION_SCHEMA_INVALID,
            ) from exc

        result.prompt_version = inp.prompt_version
        result.prompt_hash = prompt_hash
        result.latency_ms = latency_ms
        result.total_pages_analyzed = len(inp.pages)

        # Run deterministic validators (§21.4)
        validate_reconstruction(result)

        logger.info(
            "reconstruction_complete",
            session_id=inp.session_id,
            questions=len(result.questions),
            prompt_hash=prompt_hash[:12],
            latency_ms=round(latency_ms),
        )
        return result
