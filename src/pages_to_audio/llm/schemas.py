"""Pydantic structured output schemas for Solver/Verifier/Arbiter — §28.

§14: answer is NEVER extracted with regex from raw LLM text.
All parsing flows through json.loads → model_validate.
The regex below is used only for field-level FORMAT VALIDATION
(ensuring the answer letter is A-E), which is schema enforcement, not extraction.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, field_validator

from src.pages_to_audio.common.errors import NonRetryableError, ReasonCode
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)

_LETTER_RE = re.compile(r"^[A-E]$")


def _validate_letter(v: str) -> str:
    upper = v.upper()
    if not _LETTER_RE.match(upper):
        raise ValueError(f"answer must be a single letter A-E, got: {v!r}")
    return upper


class SolverOutput(BaseModel):
    """Exact §28 schema for Solver structured output."""

    question_number: int
    answer: str
    evidence_ids: list[str]
    needs_visual_recheck: bool = False
    ambiguity_flags: list[str] = []

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, v: str) -> str:
        return _validate_letter(v)


class VerifierOutput(BaseModel):
    """Exact §28 schema for Verifier structured output."""

    question_number: int
    answer: str
    evidence_ids: list[str]
    verification_status: Literal["confident", "uncertain", "ambiguous"]
    ambiguity_flags: list[str] = []

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, v: str) -> str:
        return _validate_letter(v)


class ArbiterOutput(BaseModel):
    """Exact §28 schema for Arbiter structured output."""

    question_number: int
    answer: str
    decision: Literal["solver_correct", "verifier_correct", "independent_finding", "unresolvable"]
    evidence_ids: list[str]
    ambiguity_flags: list[str] = []

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, v: str) -> str:
        return _validate_letter(v)


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:] if len(lines) > 1 else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        text = "\n".join(inner).strip()
    return text


def parse_llm_output[T: BaseModel](raw: str, schema: type[T]) -> T:
    """Parse LLM text through JSON + Pydantic schema (§15, §14).

    On failure raises NonRetryableError(LLM_SCHEMA_INVALID) — caller may
    attempt schema repair (§28.2) before triggering provider fallback.
    """
    text = _strip_fences(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NonRetryableError(
            f"LLM response is not valid JSON: {exc}",
            reason_code=ReasonCode.LLM_SCHEMA_INVALID,
        ) from exc
    try:
        return schema.model_validate(data)
    except Exception as exc:
        raise NonRetryableError(
            f"LLM response failed {schema.__name__} validation: {exc}",
            reason_code=ReasonCode.LLM_SCHEMA_INVALID,
        ) from exc


def validate_answer_in_alternatives(answer: str, alternatives: dict[str, str]) -> None:
    """Guard: answer must be one of the provided alternative letters — Invariant 7."""
    if answer not in alternatives:
        raise NonRetryableError(
            f"LLM returned {answer!r} which is not in alternatives {list(alternatives)}",
            reason_code=ReasonCode.LLM_ANSWER_INVALID_ALTERNATIVE,
        )
