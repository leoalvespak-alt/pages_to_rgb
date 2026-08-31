"""Reasoning port — §26."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class SolveRequest:
    question_number: int
    text: str
    alternatives: dict[str, str]
    evidence_refs: list[str] = field(default_factory=list)
    prompt_version: str = ""
    effort: str = "high"
    provider: str = ""
    model: str = ""


@dataclass
class SolveResult:
    question_number: int
    answer: str
    evidence_ids: list[str]
    needs_visual_recheck: bool = False
    ambiguity_flags: list[str] = field(default_factory=list)


@dataclass
class VerifyRequest:
    question_number: int
    text: str
    alternatives: dict[str, str]
    evidence_refs: list[str] = field(default_factory=list)
    prompt_version: str = ""
    effort: str = "high"
    provider: str = ""
    model: str = ""


@dataclass
class VerifyResult:
    question_number: int
    answer: str
    evidence_ids: list[str]
    verification_status: str
    ambiguity_flags: list[str] = field(default_factory=list)


@dataclass
class ArbitrateRequest:
    question_number: int
    text: str
    alternatives: dict[str, str]
    solver_answer: str
    verifier_answer: str
    evidence_refs: list[str] = field(default_factory=list)
    prompt_version: str = ""
    effort: str = "max"
    provider: str = ""
    model: str = ""


@dataclass
class ArbitrateResult:
    question_number: int
    answer: str
    decision: str
    evidence_ids: list[str]
    ambiguity_flags: list[str] = field(default_factory=list)


class ReasoningProvider(Protocol):
    async def solve(self, request: SolveRequest) -> SolveResult: ...

    async def verify(self, request: VerifyRequest) -> VerifyResult: ...

    async def arbitrate(self, request: ArbitrateRequest) -> ArbitrateResult: ...
