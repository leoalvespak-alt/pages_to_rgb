"""Status message templates — §34, §6.8.

Literal text from §34 for Gate 1 and Gate 2 status audio.
These are the text scripts; TTS synthesis happens in Phase 9.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StatusMessage:
    text: str
    gate: int
    outcome: str  # "success" | "degraded" | "blocked"
    ready: int
    expected: int


def gate1_success(ready: int, expected: int) -> StatusMessage:
    """Gate 1 — 100% recognized (§34)."""
    return StatusMessage(
        text=f"Captura validada. {ready} de {expected} questões reconhecidas. Iniciando correção.",
        gate=1,
        outcome="success",
        ready=ready,
        expected=expected,
    )


def gate1_degraded(ready: int, expected: int, failed: int) -> StatusMessage:
    """Gate 1 — passed but not 100% (§34)."""
    text = (
        f"{ready} de {expected} questões reconhecidas. "
        f"{failed} falhas registradas. Iniciando correção."
    )
    return StatusMessage(text=text, gate=1, outcome="degraded", ready=ready, expected=expected)


def gate1_blocked(ready: int, expected: int, failed: int) -> StatusMessage:
    """Gate 1 — blocked (§34)."""
    text = (
        f"Falha de processamento. {ready} de {expected} questões válidas. "
        f"{failed} falhas. Processo encerrado."
    )
    return StatusMessage(text=text, gate=1, outcome="blocked", ready=ready, expected=expected)


def gate2_success(validated: int, expected: int) -> StatusMessage:
    """Gate 2 — all answers validated."""
    return StatusMessage(
        text=f"Gabarito completo. {validated} de {expected} questões validadas. Gerando áudio.",
        gate=2,
        outcome="success",
        ready=validated,
        expected=expected,
    )


def gate2_degraded(validated: int, expected: int, failed: int) -> StatusMessage:
    """Gate 2 — passed but degraded."""
    text = (
        f"{validated} de {expected} questões com gabarito. "
        f"{failed} sem resposta. Gerando áudio parcial."
    )
    return StatusMessage(text=text, gate=2, outcome="degraded", ready=validated, expected=expected)


def gate2_blocked(validated: int, expected: int, failed: int) -> StatusMessage:
    """Gate 2 — blocked (no audio gabarito)."""
    text = (
        f"Gabarito insuficiente. {validated} de {expected} questões válidas. "
        f"{failed} falhas. Áudio de gabarito não gerado."
    )
    return StatusMessage(text=text, gate=2, outcome="blocked", ready=validated, expected=expected)


def build_gate1_message(
    ready: int,
    expected: int,
    passed: bool,
    success: bool,
) -> StatusMessage:
    failed = expected - ready
    if not passed:
        return gate1_blocked(ready, expected, failed)
    if success:
        return gate1_success(ready, expected)
    return gate1_degraded(ready, expected, failed)


def build_gate2_message(
    validated: int,
    expected: int,
    passed: bool,
    success: bool,
) -> StatusMessage:
    failed = expected - validated
    if not passed:
        return gate2_blocked(validated, expected, failed)
    if success:
        return gate2_success(validated, expected)
    return gate2_degraded(validated, expected, failed)
