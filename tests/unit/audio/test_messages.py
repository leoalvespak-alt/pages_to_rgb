"""Unit tests for status messages — §34, §6.8."""

from __future__ import annotations

import pytest

from src.pages_to_audio.audio.messages import (
    build_gate1_message,
    build_gate2_message,
    gate1_blocked,
    gate1_degraded,
    gate1_success,
    gate2_blocked,
)


def test_gate1_success_message() -> None:
    msg = gate1_success(70, 70)
    assert "70 de 70" in msg.text
    assert "Iniciando correção" in msg.text
    assert msg.outcome == "success"


def test_gate1_degraded_message() -> None:
    msg = gate1_degraded(65, 70, 5)
    assert "65 de 70" in msg.text
    assert "5 falhas" in msg.text
    assert "Iniciando correção" in msg.text
    assert msg.outcome == "degraded"


def test_gate1_blocked_message() -> None:
    msg = gate1_blocked(60, 70, 10)
    assert "60 de 70" in msg.text
    assert "Processo encerrado" in msg.text
    assert msg.outcome == "blocked"


def test_gate2_blocked_no_audio_text() -> None:
    msg = gate2_blocked(50, 70, 20)
    assert "Áudio de gabarito não gerado" in msg.text
    assert msg.outcome == "blocked"


@pytest.mark.parametrize("ready,expected,passed,success,expected_outcome", [
    (70, 70, True,  True,  "success"),
    (65, 70, True,  False, "degraded"),
    (62, 70, False, False, "blocked"),
])
def test_build_gate1_message_outcomes(
    ready: int,
    expected: int,
    passed: bool,
    success: bool,
    expected_outcome: str,
) -> None:
    msg = build_gate1_message(ready, expected, passed, success)
    assert msg.outcome == expected_outcome
    assert msg.gate == 1


@pytest.mark.parametrize("validated,expected,passed,success,expected_outcome", [
    (70, 70, True,  True,  "success"),
    (65, 70, True,  False, "degraded"),
    (62, 70, False, False, "blocked"),
])
def test_build_gate2_message_outcomes(
    validated: int,
    expected: int,
    passed: bool,
    success: bool,
    expected_outcome: str,
) -> None:
    msg = build_gate2_message(validated, expected, passed, success)
    assert msg.outcome == expected_outcome
    assert msg.gate == 2
