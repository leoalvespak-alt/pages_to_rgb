from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.pages_to_audio.rgb.canonical import build_payload
from src.pages_to_audio.rgb.policy import DEFAULT_PALETTE
from src.pages_to_audio.rgb.schemas import RgbDefaults, RgbOverride


def _palette():
    return {key: value.model_copy(deep=True) for key, value in DEFAULT_PALETTE.items()}


def test_rgb_defaults_and_palette_enforce_firmware_ranges() -> None:
    with pytest.raises(ValidationError):
        RgbDefaults(brightness_percent=101)
    with pytest.raises(ValidationError):
        RgbDefaults(on_ms=99)
    with pytest.raises(ValidationError):
        build_payload(
            session_id="S-1",
            sequence_id="rgb-1",
            revision=1,
            answers="A",
            defaults=RgbDefaults(),
            palette={**_palette(), "A": {"rgb": (256, 0, 0)}},
        )


def test_rgb_schema_is_strict_about_numeric_fields() -> None:
    with pytest.raises(ValidationError):
        RgbDefaults(brightness_percent="12")  # type: ignore[arg-type]


def test_duplicate_and_out_of_range_overrides_are_rejected() -> None:
    with pytest.raises(ValidationError, match="repeat an index"):
        build_payload(
            session_id="S-1",
            sequence_id="rgb-1",
            revision=1,
            answers="AB",
            defaults=RgbDefaults(),
            palette=_palette(),
            overrides=[RgbOverride(index=1), RgbOverride(index=1)],
        )
    with pytest.raises(ValidationError, match="point to an item"):
        build_payload(
            session_id="S-1",
            sequence_id="rgb-1",
            revision=1,
            answers="A",
            defaults=RgbDefaults(),
            palette=_palette(),
            overrides=[RgbOverride(index=1)],
        )


def test_sequence_limits_reject_more_than_firmware_maximum() -> None:
    with pytest.raises(ValidationError):
        build_payload(
            session_id="S-1",
            sequence_id="rgb-1",
            revision=1,
            answers="A" * 1001,
            defaults=RgbDefaults(),
            palette=_palette(),
        )
