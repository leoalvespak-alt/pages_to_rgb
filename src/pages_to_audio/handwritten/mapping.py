"""Mapping palavra → A-E → RGB para teste manuscrito.

Isolado do fluxo EXAM — usa HANDWRITTEN_PALETTE de rgb/policy.py.
"""

from __future__ import annotations

import unicodedata

from src.pages_to_audio.rgb.policy import HANDWRITTEN_PALETTE
from src.pages_to_audio.rgb.schemas import AnswerLetter

HANDWRITTEN_WORDS: tuple[str, ...] = ("João", "Maria", "Pedro", "Paula", "Fernanda")

HANDWRITTEN_WORD_TO_LETTER: dict[str, AnswerLetter] = {
    "joao": "A",  # Azul
    "maria": "B",  # Vermelho
    "pedro": "C",  # Verde
    "paula": "D",  # Roxo
    "fernanda": "E",  # Amarelo
}

HANDWRITTEN_LETTER_TO_WORD: dict[AnswerLetter, str] = {
    "A": "João",
    "B": "Maria",
    "C": "Pedro",
    "D": "Paula",
    "E": "Fernanda",
}

HANDWRITTEN_PALETTE_RGB: dict[AnswerLetter, tuple[int, int, int]] = {
    letter: color.rgb for letter, color in HANDWRITTEN_PALETTE.items()
}


def _strip_accents(value: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn"
    )


def normalize_word(raw: str | None) -> str | None:
    """Normaliza palavra bruta para uma das 5 canônicas ou None.

    - trim, case-insensitive, acento-insensitive
    - retorna forma canônica `João` etc se casar, senão None
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    key = _strip_accents(s).lower()
    # key sem acento -> look up
    letter = HANDWRITTEN_WORD_TO_LETTER.get(key)
    if letter is None:
        return None
    return HANDWRITTEN_LETTER_TO_WORD[letter]


def word_to_letter(word: str | None) -> AnswerLetter | None:
    """Converte palavra (qualquer case/acento) para A-E."""
    norm = normalize_word(word)
    if norm is None:
        return None
    key = _strip_accents(norm).lower()
    return HANDWRITTEN_WORD_TO_LETTER.get(key)


def letter_to_rgb(letter: AnswerLetter) -> tuple[int, int, int]:
    return HANDWRITTEN_PALETTE_RGB[letter]
