"""Reconstruction domain models — §21.2.

All validated by Pydantic. No regex extraction allowed (CLAUDE.md rule 14).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Completeness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING = "missing"


class QuestionFlag(StrEnum):
    NUMBER_MISSING = "NUMBER_MISSING"
    ALTERNATIVES_INCOMPLETE = "ALTERNATIVES_INCOMPLETE"
    VISUAL_AMBIGUITY = "VISUAL_AMBIGUITY"
    DUPLICATE_NUMBER = "DUPLICATE_NUMBER"
    SEQUENCE_GAP = "SEQUENCE_GAP"
    OCR_CONFLICT = "OCR_CONFLICT"
    MEDIA_UNRESOLVED = "MEDIA_UNRESOLVED"
    CROSS_PAGE = "CROSS_PAGE"


class AlternativesModel(BaseModel):
    A: str = ""
    B: str = ""
    C: str = ""
    D: str = ""
    E: str = ""

    def non_empty(self) -> dict[str, str]:
        return {k: v for k, v in self.model_dump().items() if v.strip()}

    def valid_letters(self) -> set[str]:
        return {k for k, v in self.model_dump().items() if v.strip()}


class SourceRegion(BaseModel):
    page_index: int
    x: float
    y: float
    width: float
    height: float


class ReconstructedQuestion(BaseModel):
    """Exact schema of §21.2."""

    question_number: int = Field(..., ge=1, le=200)
    text: str = Field(..., min_length=1)
    alternatives: AlternativesModel = Field(default_factory=AlternativesModel)
    page_refs: list[int] = Field(default_factory=list)
    media_refs: list[str] = Field(default_factory=list)
    source_regions: list[SourceRegion] = Field(default_factory=list)
    completeness: Completeness = Completeness.MISSING
    flags: list[QuestionFlag] = Field(default_factory=list)
    reconstruction_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("alternatives")
    @classmethod
    def at_least_two_alternatives(cls, v: AlternativesModel) -> AlternativesModel:
        if len(v.non_empty()) < 2:
            raise ValueError("Question must have at least 2 non-empty alternatives")
        return v


class ExamReconstructionResult(BaseModel):
    """Full structured output from the LLM reconstruction step (§21.2)."""

    questions: list[ReconstructedQuestion] = Field(default_factory=list)
    total_pages_analyzed: int = 0
    prompt_version: str = ""
    prompt_hash: str = ""
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0
    estimated_cost_usd: float = 0.0
