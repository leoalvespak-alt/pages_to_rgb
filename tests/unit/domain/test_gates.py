"""Unit tests for Gate 1 and Gate 2 — §6.7, §9.1, §61."""

from __future__ import annotations

import pytest

from src.pages_to_audio.domain.gates import evaluate_gate_1, evaluate_gate_2

# ─── Gate 1 ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ready,expected,ratio,should_pass,should_degrade,should_succeed", [
    # Canonical test (§6.7.3): expected=70, ratio=0.90 → required=63
    (70, 70, 0.90, True,  False, True),   # 70/70 — full success
    (69, 70, 0.90, True,  True,  False),  # 69/70 — degraded
    (63, 70, 0.90, True,  True,  False),  # 63/70 — passes (boundary)
    (62, 70, 0.90, False, False, False),  # 62/70 — blocked
    (0,  70, 0.90, False, False, False),  # 0/70  — blocked
    # Edge: ratio 1.0 → required == expected
    (10, 10, 1.00, True,  False, True),
    (9,  10, 1.00, False, False, False),
])
def test_gate_1_cases(
    ready: int,
    expected: int,
    ratio: float,
    should_pass: bool,
    should_degrade: bool,
    should_succeed: bool,
) -> None:
    r = evaluate_gate_1(ready, expected, ratio)
    assert r.passed == should_pass, f"gate1 passed mismatch: ready={ready}"
    assert r.degraded == should_degrade, f"gate1 degraded mismatch: ready={ready}"
    assert r.success == should_succeed, f"gate1 success mismatch: ready={ready}"
    assert r.blocked == (not should_pass)


def test_gate_1_required_formula() -> None:
    """ceil(70 * 0.90) = ceil(63.0) = 63."""
    r = evaluate_gate_1(0, 70, 0.90)
    assert r.required == 63


def test_gate_1_ratio_field() -> None:
    r = evaluate_gate_1(63, 70, 0.90)
    assert abs(r.ratio - 63 / 70) < 1e-6


# ─── Gate 2 ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("validated,expected,ratio,should_pass", [
    (70, 70, 0.90, True),
    (63, 70, 0.90, True),   # boundary pass
    (62, 70, 0.90, False),  # boundary block
    (0,  70, 0.90, False),
])
def test_gate_2_cases(
    validated: int,
    expected: int,
    ratio: float,
    should_pass: bool,
) -> None:
    r = evaluate_gate_2(validated, expected, ratio)
    assert r.passed == should_pass


def test_gate_2_required_formula() -> None:
    r = evaluate_gate_2(0, 70, 0.90)
    assert r.required == 63


def test_gate_2_blocked_means_no_tts() -> None:
    """When Gate 2 is blocked, gate2_result.passed is False — ProcessExamWorkflow must not call TTS."""
    r = evaluate_gate_2(62, 70, 0.90)
    assert r.blocked
    assert not r.passed
