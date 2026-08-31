"""Handwritten word test — exports."""

from src.pages_to_audio.handwritten.mapping import (
    HANDWRITTEN_LETTER_TO_WORD,
    HANDWRITTEN_PALETTE_RGB,
    HANDWRITTEN_WORD_TO_LETTER,
    HANDWRITTEN_WORDS,
    normalize_word,
    word_to_letter,
)

__all__ = [
    "HANDWRITTEN_LETTER_TO_WORD",
    "HANDWRITTEN_PALETTE_RGB",
    "HANDWRITTEN_WORDS",
    "HANDWRITTEN_WORD_TO_LETTER",
    "normalize_word",
    "word_to_letter",
]
