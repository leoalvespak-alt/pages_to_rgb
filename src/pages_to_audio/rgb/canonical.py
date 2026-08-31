"""Canonical RGB item resolution and SHA-256 compatible with the ESP32."""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from typing import cast

from src.pages_to_audio.rgb.schemas import (
    AnswerLetter,
    RgbColor,
    RgbDefaults,
    RgbOverride,
    RgbSequencePayload,
)


@dataclass(frozen=True, slots=True)
class ResolvedRgbItem:
    answer: AnswerLetter
    r: int
    g: int
    b: int
    brightness_percent: int
    on_ms: int
    off_ms: int


def resolved_items(payload: RgbSequencePayload) -> tuple[ResolvedRgbItem, ...]:
    """Apply palette, defaults and sparse overrides in protocol order."""

    defaults: RgbDefaults = payload.defaults
    items = [
        ResolvedRgbItem(
            answer=letter,
            r=payload.palette[letter].rgb[0],
            g=payload.palette[letter].rgb[1],
            b=payload.palette[letter].rgb[2],
            brightness_percent=defaults.brightness_percent,
            on_ms=defaults.on_ms,
            off_ms=defaults.off_ms,
        )
        for answer in payload.answers
        for letter in (cast(AnswerLetter, answer),)
    ]

    for override in payload.overrides:
        current = items[override.index]
        r, g, b = override.rgb if override.rgb is not None else (current.r, current.g, current.b)
        items[override.index] = ResolvedRgbItem(
            answer=current.answer,
            r=r,
            g=g,
            b=b,
            brightness_percent=(
                override.brightness_percent
                if override.brightness_percent is not None
                else current.brightness_percent
            ),
            on_ms=override.on_ms if override.on_ms is not None else current.on_ms,
            off_ms=override.off_ms if override.off_ms is not None else current.off_ms,
        )
    return tuple(items)


def canonical_items_bytes(payload: RgbSequencePayload) -> bytes:
    """Pack each resolved item as <BBBBBII, exactly 13 bytes per item."""

    return b"".join(
        struct.pack(
            "<BBBBBII",
            ord(item.answer),
            item.r,
            item.g,
            item.b,
            item.brightness_percent,
            item.on_ms,
            item.off_ms,
        )
        for item in resolved_items(payload)
    )


def payload_sha256(payload: RgbSequencePayload) -> str:
    """Return the lowercase SHA-256 expected in the wire payload."""

    return hashlib.sha256(canonical_items_bytes(payload)).hexdigest()


def validate_payload_sha256(payload: RgbSequencePayload) -> None:
    """Raise ValueError when metadata does not match resolved item bytes."""

    actual = payload_sha256(payload)
    if actual != payload.sha256:
        raise ValueError(f"RGB payload SHA-256 mismatch: expected {payload.sha256}, got {actual}")


def compact_json_bytes(payload: RgbSequencePayload) -> bytes:
    """Serialize a payload compactly for the 256 KiB firmware download limit."""

    return json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def build_payload(
    *,
    session_id: str,
    sequence_id: str,
    revision: int,
    answers: str,
    defaults: RgbDefaults,
    palette: dict[AnswerLetter, RgbColor],
    overrides: list[RgbOverride] | None = None,
) -> tuple[RgbSequencePayload, bytes]:
    """Build a validated payload and return it together with its compact JSON."""

    draft = RgbSequencePayload(
        session_id=session_id,
        sequence_id=sequence_id,
        revision=revision,
        item_count=len(answers),
        sha256="0" * 64,
        answers=answers,
        defaults=defaults,
        palette=palette,
        overrides=overrides or [],
    )
    payload = draft.model_copy(update={"sha256": payload_sha256(draft)})
    return payload, compact_json_bytes(payload)
