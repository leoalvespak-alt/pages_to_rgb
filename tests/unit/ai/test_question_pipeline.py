from __future__ import annotations

import pytest

from src.pages_to_audio.ai.confidence import ReviewMode
from src.pages_to_audio.ai.question_pipeline import process_question
from src.pages_to_audio.domain.ports.ocr import NormalizedOCRResult, OCRRequest
from src.pages_to_audio.domain.ports.reasoning import SolveResult


class Ocr:
    def __init__(self, confidence: float = 0.80, text: str = "OCR text") -> None:
        self.confidence = confidence
        self.text = text

    async def analyze_page(self, request: OCRRequest) -> NormalizedOCRResult:
        return NormalizedOCRResult(
            text=self.text,
            blocks=[],
            lines=[],
            tokens=[],
            reading_order=[],
            tables=[],
            formulas=[],
            confidence=self.confidence,
            raw_storage_key="ocr/raw.json",
            provider="google_document_ai",
        )


class Gemini:
    model = "gemini-3.1-pro-preview"

    def __init__(self) -> None:
        self.reconcile_args: tuple[str, bytes, bytes | None, str] | None = None
        self.solve_text: str | None = None

    async def reconcile_ocr(self, ocr_text: str, image_bytes: bytes, **kwargs):  # type: ignore[no-untyped-def]
        self.reconcile_args = (
            ocr_text,
            image_bytes,
            kwargs.get("crop_bytes"),
            kwargs.get("context_local", ""),
        )
        return "Consolidated", []

    async def solve(self, request) -> SolveResult:  # type: ignore[no-untyped-def]
        self.solve_text = request.text
        return SolveResult(request.question_number, "A", ["ocr/raw.json"])


@pytest.mark.asyncio
async def test_pipeline_sends_original_image_and_consolidated_text() -> None:
    gemini = Gemini()
    consolidated, answer = await process_question(
        Ocr(),
        gemini,  # type: ignore[arg-type]
        request=OCRRequest(
            original_storage_key="frames/q1.jpg",
            hints={"crop_bytes": bytearray(b"crop"), "context_local": "enunciado local"},
        ),
        image_bytes=b"original-image",
        question_number=1,
        alternatives={"A": "one", "B": "two"},
    )
    assert gemini.reconcile_args == ("OCR text", b"original-image", b"crop", "enunciado local")
    assert gemini.solve_text == "Consolidated"
    assert consolidated.text == "Consolidated"
    assert consolidated.review_mode is ReviewMode.VERIFY
    assert consolidated.manual_review_required is False
    assert consolidated.review_provider == "gemini"
    assert answer == "A"


@pytest.mark.asyncio
async def test_high_confidence_ordinary_text_skips_visual_review() -> None:
    gemini = Gemini()
    consolidated, answer = await process_question(
        Ocr(confidence=0.99, text="Texto normal"),
        gemini,  # type: ignore[arg-type]
        request=OCRRequest(original_storage_key="frames/q1.jpg"),
        image_bytes=b"original-image",
        question_number=1,
        alternatives={"A": "one", "B": "two"},
    )
    assert gemini.reconcile_args is None
    assert consolidated.text == "Texto normal"
    assert consolidated.review_mode is ReviewMode.ACCEPT
    assert answer == "A"
