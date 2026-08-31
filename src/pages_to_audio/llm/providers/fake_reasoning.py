"""Fake deterministic ReasoningProvider for tests — §8.11.1.

Configurable per question_number. Can raise on demand to test fallback and error paths.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from src.pages_to_audio.domain.ports.reasoning import (
    ArbitrateRequest,
    ArbitrateResult,
    SolveRequest,
    SolveResult,
    VerifyRequest,
    VerifyResult,
)


@dataclass
class FakeReasoningProvider:
    """Deterministic fake provider.

    Attributes:
        default_answer: Fallback answer letter when question_number not in overrides.
        solve_overrides: Per-question answer overrides for solve().
        verify_overrides: Per-question answer overrides for verify().
        solve_error: If set, raise this exception on every solve() call.
        verify_error: If set, raise this exception on every verify() call.
        arbitrate_error: If set, raise this exception on every arbitrate() call.
        recorded_verify_payloads: Collects raw VerifyRequest objects for payload inspection.
    """

    default_answer: str = "A"
    solve_overrides: dict[int, str] = field(default_factory=dict)
    verify_overrides: dict[int, str] = field(default_factory=dict)
    solve_error: Exception | None = None
    verify_error: Exception | None = None
    arbitrate_error: Exception | None = None
    recorded_verify_payloads: list[VerifyRequest] = field(default_factory=list)
    arbitrate_decision: str = "solver_correct"
    solve_call_count: int = 0
    verify_call_count: int = 0
    arbitrate_call_count: int = 0

    async def solve(self, request: SolveRequest) -> SolveResult:
        self.solve_call_count += 1
        if self.solve_error is not None:
            raise self.solve_error
        answer = self.solve_overrides.get(request.question_number, self.default_answer)
        return SolveResult(
            question_number=request.question_number,
            answer=answer,
            evidence_ids=[],
        )

    async def verify(self, request: VerifyRequest) -> VerifyResult:
        self.verify_call_count += 1
        self.recorded_verify_payloads.append(request)
        if self.verify_error is not None:
            raise self.verify_error
        answer = self.verify_overrides.get(request.question_number, self.default_answer)
        return VerifyResult(
            question_number=request.question_number,
            answer=answer,
            evidence_ids=[],
            verification_status="confident",
        )

    async def arbitrate(self, request: ArbitrateRequest) -> ArbitrateResult:
        self.arbitrate_call_count += 1
        if self.arbitrate_error is not None:
            raise self.arbitrate_error
        return ArbitrateResult(
            question_number=request.question_number,
            answer=request.solver_answer,
            decision=self.arbitrate_decision,
            evidence_ids=[],
        )


def make_error_sequence(errors: list[Exception | None]) -> Callable[[], None]:
    """Return a callable that raises the next error in sequence (or does nothing for None)."""
    idx = 0

    def _raise() -> None:
        nonlocal idx
        exc = errors[idx % len(errors)]
        idx += 1
        if exc is not None:
            raise exc

    return _raise
