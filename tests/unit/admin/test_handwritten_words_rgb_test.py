from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.api.schemas.admin import AdminSettingsUpdate, RgbTestRequest
from src.pages_to_audio.handwritten.mapping import normalize_word, word_to_letter


def test_custom_handwritten_words_are_complete_unique_and_trimmed() -> None:
    payload = AdminSettingsUpdate(
        version=1,
        handwritten_words={
            "A": "  Ana ",
            "B": "Bia",
            "C": "Caio",
            "D": "Davi",
            "E": "Eva",
        },
    )
    assert payload.handwritten_words == {
        "A": "Ana",
        "B": "Bia",
        "C": "Caio",
        "D": "Davi",
        "E": "Eva",
    }


@pytest.mark.parametrize(
    "words",
    [
        {"A": "Ana"},
        {"A": "Ana", "B": "Ana", "C": "Caio", "D": "Davi", "E": "Eva"},
        {"A": "", "B": "Bia", "C": "Caio", "D": "Davi", "E": "Eva"},
    ],
)
def test_custom_handwritten_words_reject_invalid_maps(words: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        AdminSettingsUpdate(version=1, handwritten_words=words)


def test_dynamic_word_mapping_is_accent_and_case_insensitive() -> None:
    words = {"A": "José", "B": "Bia", "C": "Caio", "D": "Davi", "E": "Eva"}
    assert normalize_word(" jose ", words) == "José"
    assert word_to_letter("JOSÉ", words) == "A"


def test_rgb_test_contract_validates_channels_brightness_and_times() -> None:
    request = RgbTestRequest(
        session_id="11111111-1111-1111-1111-111111111111",
        rgb=(12, 34, 56),
        brightness_percent=80,
        on_ms=1500,
        off_ms=500,
    )
    assert request.rgb == (12, 34, 56)
    with pytest.raises(ValidationError):
        RgbTestRequest(
            session_id="x",
            rgb=(256, 0, 0),
            brightness_percent=101,
            on_ms=99,
            off_ms=-1,
        )
