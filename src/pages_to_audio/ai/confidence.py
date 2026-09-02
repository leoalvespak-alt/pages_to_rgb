"""Confidence bands for OCR review and critical-token handling."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class ReviewMode(StrEnum):
    ACCEPT = "accept"
    VERIFY = "verify"
    RECOMPOSE = "recompose"
    MANUAL = "manual"


# Negations, answer-affecting qualifiers, numeric values and symbols are more
# dangerous to silently alter than ordinary prose.
_CRITICAL_RE = re.compile(
    r"\b(?:NÃO|NAO|EXCETO|INCORRETA|INCORRETO|ART(?:IGO)?\.?)\b|"
    r"\d|%|[+\-*/=<>≤≥±√∞©®°]|"
    r"\balternativa\s+[A-E]\b|(?<![A-Za-z])[A-E](?=\s*[\)\].:-])",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ConfidenceDecision:
    score: float
    critical: bool
    accept_threshold: float
    verify_threshold: float
    mode: ReviewMode

    @property
    def requires_gemini(self) -> bool:
        return self.mode is not ReviewMode.ACCEPT

    @property
    def manual_review_required(self) -> bool:
        return self.mode is ReviewMode.MANUAL


def is_critical_text(text: str) -> bool:
    return bool(_CRITICAL_RE.search(text))


def decide_review(confidence: float, text: str) -> ConfidenceDecision:
    score = max(0.0, min(1.0, float(confidence)))
    critical = is_critical_text(text)
    accept = 0.95 if critical else 0.90
    verify = 0.85 if critical else 0.75
    mode = (
        ReviewMode.ACCEPT
        if score >= accept
        else ReviewMode.VERIFY
        if score >= verify
        else ReviewMode.RECOMPOSE
    )
    return ConfidenceDecision(score, critical, accept, verify, mode)


def finalize_review(confidence: float, text: str, *, ambiguous: bool = False) -> ConfidenceDecision:
    decision = decide_review(confidence, text)
    if ambiguous:
        return ConfidenceDecision(
            decision.score,
            decision.critical,
            decision.accept_threshold,
            decision.verify_threshold,
            ReviewMode.MANUAL,
        )
    return decision
