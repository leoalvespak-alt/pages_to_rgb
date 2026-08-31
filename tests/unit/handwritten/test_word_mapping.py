"""Testes de mapping palavra→cor — HANDWRITTEN_WORD isolado."""

import pytest

from src.pages_to_audio.handwritten.mapping import (
    HANDWRITTEN_LETTER_TO_WORD,
    HANDWRITTEN_PALETTE_RGB,
    HANDWRITTEN_WORD_TO_LETTER,
    HANDWRITTEN_WORDS,
    normalize_word,
    word_to_letter,
)
from src.pages_to_audio.rgb.policy import HANDWRITTEN_PALETTE


@pytest.mark.unit
def test_handwritten_words_count() -> None:
    assert len(HANDWRITTEN_WORDS) == 5
    assert set(HANDWRITTEN_WORDS) == {"João", "Maria", "Pedro", "Paula", "Fernanda"}


@pytest.mark.unit
def test_word_to_letter_mapping() -> None:
    assert word_to_letter("João") == "A"
    assert word_to_letter("Maria") == "B"
    assert word_to_letter("Pedro") == "C"
    assert word_to_letter("Paula") == "D"
    assert word_to_letter("Fernanda") == "E"


@pytest.mark.unit
def test_normalize_case_and_accent_insensitive() -> None:
    assert normalize_word("joao") == "João"
    assert normalize_word("JOAO") == "João"
    assert normalize_word("  joão  ") == "João"
    assert normalize_word("JoAo") == "João"
    assert normalize_word("MARIA") == "Maria"
    assert normalize_word("maria") == "Maria"
    assert normalize_word("PEDRO") == "Pedro"
    assert normalize_word("paula") == "Paula"
    assert normalize_word("FERNANDA") == "Fernanda"


@pytest.mark.unit
def test_normalize_invalid_returns_none() -> None:
    assert normalize_word(None) is None
    assert normalize_word("") is None
    assert normalize_word("   ") is None
    assert normalize_word("Carlos") is None
    assert normalize_word("Joana") is None
    assert word_to_letter("Carlos") is None
    assert word_to_letter("") is None


@pytest.mark.unit
def test_letter_to_word_invert() -> None:
    assert HANDWRITTEN_LETTER_TO_WORD["A"] == "João"
    assert HANDWRITTEN_LETTER_TO_WORD["B"] == "Maria"
    assert HANDWRITTEN_LETTER_TO_WORD["C"] == "Pedro"
    assert HANDWRITTEN_LETTER_TO_WORD["D"] == "Paula"
    assert HANDWRITTEN_LETTER_TO_WORD["E"] == "Fernanda"
    assert set(HANDWRITTEN_WORD_TO_LETTER.values()) == {"A", "B", "C", "D", "E"}


@pytest.mark.unit
def test_handwritten_palette_exact_colors() -> None:
    # João→Azul 0,0,255 | Maria→Vermelho 255,0,0 | Pedro→Verde 0,255,0
    # Paula→Roxo 128,0,128 | Fernanda→Amarelo 255,255,0
    assert HANDWRITTEN_PALETTE["A"].rgb == (0, 0, 255)
    assert HANDWRITTEN_PALETTE["B"].rgb == (255, 0, 0)
    assert HANDWRITTEN_PALETTE["C"].rgb == (0, 255, 0)
    assert HANDWRITTEN_PALETTE["D"].rgb == (128, 0, 128)
    assert HANDWRITTEN_PALETTE["E"].rgb == (255, 255, 0)
    assert HANDWRITTEN_PALETTE_RGB["A"] == (0, 0, 255)
    assert HANDWRITTEN_PALETTE_RGB["E"] == (255, 255, 0)


@pytest.mark.unit
def test_handwritten_palette_structure_same_as_default() -> None:
    from src.pages_to_audio.rgb.policy import DEFAULT_PALETTE

    assert set(HANDWRITTEN_PALETTE.keys()) == {"A", "B", "C", "D", "E"}
    assert set(DEFAULT_PALETTE.keys()) == {"A", "B", "C", "D", "E"}
    # Both have same schema (RgbColor with rgb tuple)
    for letter in "ABCDE":
        assert len(HANDWRITTEN_PALETTE[letter].rgb) == 3
        assert len(DEFAULT_PALETTE[letter].rgb) == 3


@pytest.mark.unit
def test_handwritten_palette_does_not_equal_default() -> None:
    from src.pages_to_audio.rgb.policy import DEFAULT_PALETTE

    # Ensure isolation: handwritten palette is not a copy of default
    assert HANDWRITTEN_PALETTE["A"].rgb != DEFAULT_PALETTE["A"].rgb
    assert HANDWRITTEN_PALETTE["B"].rgb != DEFAULT_PALETTE["B"].rgb


@pytest.mark.unit
def test_canonical_sha_with_handwritten_palette() -> None:
    from src.pages_to_audio.rgb.canonical import build_payload, canonical_items_bytes
    from src.pages_to_audio.rgb.schemas import RgbDefaults
    import hashlib

    defaults = RgbDefaults()
    payload, raw = build_payload(
        session_id="S-hw",
        sequence_id="rgb-hw-001",
        revision=1,
        answers="ABCDEABCDE",  # 10 words: João×2 etc mapped to A-E twice
        defaults=defaults,
        palette=HANDWRITTEN_PALETTE,
    )
    assert payload.item_count == 10
    assert len(canonical_items_bytes(payload)) == 10 * 13
    assert payload.sha256 == hashlib.sha256(canonical_items_bytes(payload)).hexdigest()
    assert len(raw) <= 262144
