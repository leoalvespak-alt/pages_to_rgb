"""Domain services for the firmware V2.2 RGB result channel."""

from src.pages_to_audio.rgb.canonical import (
    build_payload,
    canonical_items_bytes,
    compact_json_bytes,
    payload_sha256,
    resolved_items,
)
from src.pages_to_audio.rgb.policy import (
    DEFAULT_BRIGHTNESS_PERCENT,
    DEFAULT_OFF_MS,
    DEFAULT_ON_MS,
    DEFAULT_PALETTE,
    validate_complete_answer_set,
)
from src.pages_to_audio.rgb.schemas import (
    RgbEventName,
    RgbResultCommand,
    RgbSequencePayload,
    RgbSequenceStatus,
)

__all__ = [
    "DEFAULT_BRIGHTNESS_PERCENT",
    "DEFAULT_OFF_MS",
    "DEFAULT_ON_MS",
    "DEFAULT_PALETTE",
    "RgbEventName",
    "RgbResultCommand",
    "RgbSequencePayload",
    "RgbSequenceStatus",
    "build_payload",
    "canonical_items_bytes",
    "compact_json_bytes",
    "payload_sha256",
    "resolved_items",
    "validate_complete_answer_set",
]
