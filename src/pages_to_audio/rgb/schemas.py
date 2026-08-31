"""Strict Pydantic schemas for RGB result schema version 1."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)

AnswerLetter = Literal["A", "B", "C", "D", "E"]


def _json_array_to_rgb_tuple(value: object) -> object:
    """Keep strict channel validation while accepting JSON arrays on rehydrate."""

    return tuple(value) if isinstance(value, list) else value


RgbTriple = Annotated[
    tuple[StrictInt, StrictInt, StrictInt],
    BeforeValidator(_json_array_to_rgb_tuple),
]


class RgbResultCommand(StrEnum):
    """Commands understood by the firmware RESULT_WAIT poll."""

    RESULT_NOT_STARTED = "RESULT_NOT_STARTED"
    RESULT_PROCESSING = "RESULT_PROCESSING"
    RGB_SEQUENCE_READY = "RGB_SEQUENCE_READY"
    RESULT_CANCELLED = "RESULT_CANCELLED"


class RgbEventName(StrEnum):
    """Events emitted by the firmware while delivering/playing a sequence."""

    RECEIVED = "RECEIVED"
    STARTED = "STARTED"
    RESUMED = "RESUMED"
    COMPLETED = "COMPLETED"
    INVALID = "INVALID"


class RgbSequenceStatus(StrEnum):
    """Persistent lifecycle of one immutable sequence revision."""

    READY = "READY"
    RECEIVED = "RECEIVED"
    PLAYING = "PLAYING"
    COMPLETED = "COMPLETED"
    INVALID = "INVALID"
    SUPERSEDED = "SUPERSEDED"


class RgbColor(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    rgb: RgbTriple

    @field_validator("rgb")
    @classmethod
    def validate_rgb(cls, value: RgbTriple) -> RgbTriple:
        if len(value) != 3 or any(channel < 0 or channel > 255 for channel in value):
            raise ValueError("rgb channels must contain exactly three values from 0 to 255")
        return value


class RgbDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    brightness_percent: int = Field(default=12, ge=0, le=100)
    on_ms: int = Field(default=3000, ge=100, le=60000)
    off_ms: int = Field(default=5000, ge=0, le=60000)


class RgbOverride(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    index: int = Field(ge=0, le=999)
    rgb: RgbTriple | None = None
    brightness_percent: int | None = Field(default=None, ge=0, le=100)
    on_ms: int | None = Field(default=None, ge=100, le=60000)
    off_ms: int | None = Field(default=None, ge=0, le=60000)

    @field_validator("rgb")
    @classmethod
    def validate_override_rgb(cls, value: RgbTriple | None) -> RgbTriple | None:
        if value is not None and (
            len(value) != 3 or any(channel < 0 or channel > 255 for channel in value)
        ):
            raise ValueError("override rgb must contain three channels from 0 to 255")
        return value


class RgbSequencePayload(BaseModel):
    """Wire payload served by /rgb-sequence and consumed by the ESP32."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    session_id: str = Field(min_length=1, max_length=128)
    sequence_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    revision: int = Field(ge=1)
    item_count: int = Field(ge=1, le=1000)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    answers: str = Field(min_length=1, max_length=1000, pattern=r"^[A-E]+$")
    defaults: RgbDefaults = Field(default_factory=RgbDefaults)
    palette: dict[AnswerLetter, RgbColor]
    overrides: list[RgbOverride] = Field(default_factory=list)

    @field_validator("palette")
    @classmethod
    def validate_palette(cls, value: dict[AnswerLetter, RgbColor]) -> dict[AnswerLetter, RgbColor]:
        expected = {"A", "B", "C", "D", "E"}
        if set(value) != expected:
            raise ValueError("palette must define exactly A, B, C, D and E")
        return value

    @model_validator(mode="after")
    def validate_payload(self) -> RgbSequencePayload:
        if self.item_count != len(self.answers):
            raise ValueError("item_count must equal the number of answers")
        indexes = [override.index for override in self.overrides]
        if len(indexes) != len(set(indexes)):
            raise ValueError("overrides cannot repeat an index")
        if any(index >= self.item_count for index in indexes):
            raise ValueError("override index must point to an item in the sequence")
        return self
