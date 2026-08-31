"""Policy and defaults for creating safe RGB result sequences."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from src.pages_to_audio.rgb.schemas import AnswerLetter, RgbColor

DEFAULT_BRIGHTNESS_PERCENT = 12
DEFAULT_ON_MS = 3000
DEFAULT_OFF_MS = 5000
MAX_SEQUENCE_ITEMS = 1000

DEFAULT_PALETTE: dict[AnswerLetter, RgbColor] = {
    "A": RgbColor(rgb=(255, 255, 255)),
    "B": RgbColor(rgb=(255, 255, 0)),
    "C": RgbColor(rgb=(0, 255, 255)),
    "D": RgbColor(rgb=(0, 0, 255)),
    "E": RgbColor(rgb=(255, 0, 0)),
}

# HANDWRITTEN_WORD palette — mesma estrutura de DEFAULT_PALETTE, defaults 12%/3000/5000
# Mapping: João(A)=Azul 0,0,255 | Maria(B)=Vermelho 255,0,0 | Pedro(C)=Verde 0,255,0
#          Paula(D)=Roxo 128,0,128 | Fernanda(E)=Amarelo 255,255,0
HANDWRITTEN_PALETTE: dict[AnswerLetter, RgbColor] = {
    "A": RgbColor(rgb=(0, 0, 255)),
    "B": RgbColor(rgb=(255, 0, 0)),
    "C": RgbColor(rgb=(0, 255, 0)),
    "D": RgbColor(rgb=(128, 0, 128)),
    "E": RgbColor(rgb=(255, 255, 0)),
}


@dataclass(frozen=True, slots=True)
class AnswerCandidate:
    """Minimal answer projection used by the policy and unit tests."""

    question_number: int
    answer: str | None
    validated: bool
    question_status: str


def validate_complete_answer_set(
    expected_questions: int,
    candidates: Iterable[AnswerCandidate],
    *,
    max_items: int = MAX_SEQUENCE_ITEMS,
) -> tuple[str | None, str | None]:
    """Return ordered answers or an explicit reason for refusing RGB output."""

    if expected_questions < 1 or expected_questions > min(max_items, MAX_SEQUENCE_ITEMS):
        return None, "RGB_EXPECTED_QUESTION_COUNT_OUT_OF_RANGE"

    by_number: dict[int, AnswerCandidate] = {}
    for candidate in candidates:
        if candidate.question_number in by_number:
            return None, "RGB_QUESTION_NUMBER_DUPLICATE"
        by_number[candidate.question_number] = candidate

    expected_numbers = set(range(1, expected_questions + 1))
    if set(by_number) != expected_numbers:
        return None, "RGB_QUESTION_SEQUENCE_GAP"

    answers: list[str] = []
    for number in range(1, expected_questions + 1):
        candidate = by_number[number]
        if candidate.question_status == "FAILED":
            return None, "RGB_QUESTION_FAILED"
        if not candidate.validated:
            return None, "RGB_ANSWER_NOT_VALIDATED"
        if candidate.answer not in {"A", "B", "C", "D", "E"}:
            return None, "RGB_ANSWER_INVALID_ALTERNATIVE"
        answers.append(candidate.answer)

    return "".join(answers), None
