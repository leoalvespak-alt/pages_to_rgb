"""OCR port — §19."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class BoundingBox:
    x: float
    y: float
    width: float
    height: float


@dataclass
class OCRRequest:
    original_storage_key: str
    derived_refs: list[str] = field(default_factory=list)
    page_index: int = 0
    hints: dict[str, Any] = field(default_factory=dict)
    requested_features: list[str] = field(default_factory=list)


@dataclass
class NormalizedOCRResult:
    text: str
    blocks: list[dict[str, Any]]
    lines: list[dict[str, Any]]
    tokens: list[dict[str, Any]]
    reading_order: list[int]
    tables: list[dict[str, Any]]
    formulas: list[dict[str, Any]]
    confidence: float
    raw_storage_key: str
    provider: str
    model: str | None = None
    quality_metrics: dict[str, Any] = field(default_factory=dict)


class OCRProvider(Protocol):
    async def analyze_page(self, request: OCRRequest) -> NormalizedOCRResult: ...
