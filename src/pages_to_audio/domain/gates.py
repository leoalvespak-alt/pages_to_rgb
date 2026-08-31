"""Gate 1 and Gate 2 logic — §23, §33, §6.7, §9.1."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GateResult:
    gate: int
    ready: int
    expected: int
    required: int
    passed: bool
    degraded: bool
    ratio: float

    @property
    def success(self) -> bool:
        return self.ready == self.expected

    @property
    def blocked(self) -> bool:
        return not self.passed


def evaluate_gate_1(
    ready: int,
    expected_questions: int,
    minimum_ratio: float,
) -> GateResult:
    """
    Gate 1 formula (§23):
      required = ceil(expected * minimum_ratio)
      ready >= required → pass (degraded if ready < expected)
      ready < required → blocked
    """
    required = ceil(expected_questions * minimum_ratio)
    passed = ready >= required
    degraded = passed and ready < expected_questions
    ratio = ready / expected_questions if expected_questions else 0.0

    result = GateResult(
        gate=1,
        ready=ready,
        expected=expected_questions,
        required=required,
        passed=passed,
        degraded=degraded,
        ratio=ratio,
    )

    logger.info(
        "gate_1_evaluated",
        ready=ready,
        expected=expected_questions,
        required=required,
        passed=passed,
        degraded=degraded,
        ratio=round(ratio, 4),
    )
    return result


def evaluate_gate_2(
    validated: int,
    expected_questions: int,
    minimum_ratio: float,
) -> GateResult:
    """
    Gate 2 formula (§33):
      required = ceil(expected * minimum_ratio)
      validated >= required → pass (may be degraded)
      validated < required → blocked → NO audio gabarito (Invariant 6)
    """
    required = ceil(expected_questions * minimum_ratio)
    passed = validated >= required
    degraded = passed and validated < expected_questions
    ratio = validated / expected_questions if expected_questions else 0.0

    result = GateResult(
        gate=2,
        ready=validated,
        expected=expected_questions,
        required=required,
        passed=passed,
        degraded=degraded,
        ratio=ratio,
    )

    logger.info(
        "gate_2_evaluated",
        validated=validated,
        expected=expected_questions,
        required=required,
        passed=passed,
        degraded=degraded,
        ratio=round(ratio, 4),
    )
    return result
