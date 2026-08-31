"""Vision port — §20."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class VisionRequest:
    storage_key: str
    region: dict[str, float] | None = None
    context: str = ""
    hints: list[str] = field(default_factory=list)


@dataclass
class VisionResult:
    description: str
    structured_data: dict[str, Any]
    confidence: float
    provider: str


class VisionProvider(Protocol):
    async def analyze_region(self, request: VisionRequest) -> VisionResult: ...
