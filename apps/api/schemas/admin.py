from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ProviderName = Literal["deepseek", "gemini", "claude", "glm"]
OcrProvider = Literal["google_document_ai", "azure", "paddle"]
ModelName = Literal["deepseek-v4-pro", "gemini-3.1-pro", "claude-opus-5", "glm-5.3"]


class AdminLoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


class AdminSessionResponse(BaseModel):
    authenticated: bool = True
    expires_at: datetime


class AdminMeResponse(AdminSessionResponse):
    csrf_token: str


class PaletteColor(BaseModel):
    rgb: tuple[int, int, int]

    @field_validator("rgb")
    @classmethod
    def valid_rgb(cls, value: tuple[int, int, int]) -> tuple[int, int, int]:
        if any(channel < 0 or channel > 255 for channel in value):
            raise ValueError("RGB channels must be in [0, 255]")
        return value


Palette = dict[str, PaletteColor]
HandwrittenWords = dict[str, str]


def _validate_palette(value: Palette) -> Palette:
    if set(value) != set("ABCDE"):
        raise ValueError("Palette must contain exactly A, B, C, D and E")
    return value


def _validate_words(value: HandwrittenWords) -> HandwrittenWords:
    if set(value) != set("ABCDE"):
        raise ValueError("Words must contain exactly A, B, C, D and E")
    normalized = {letter: word.strip() for letter, word in value.items()}
    if any(not word or len(word) > 80 for word in normalized.values()):
        raise ValueError("Each handwritten word must contain 1 to 80 characters")
    if len({word.casefold() for word in normalized.values()}) != 5:
        raise ValueError("Handwritten words must be unique")
    return normalized


class AdminSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ocr_provider: OcrProvider
    solve_model: ModelName
    verify_model: ModelName
    arbiter_model: ModelName
    deepseek_api_key: str = ""
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    glm_api_key: str = ""
    deepseek_configured: bool
    gemini_configured: bool
    anthropic_configured: bool
    glm_configured: bool
    expected_pages: int
    expected_questions: int
    handwritten_expected_questions: int
    minimum_ratio: float
    brightness_percent: int
    on_ms: int
    off_ms: int
    palette: Palette
    handwritten_palette: Palette
    handwritten_words: HandwrittenWords
    version: int
    updated_at: datetime | None = None


class AdminSettingsUpdate(BaseModel):
    version: int = Field(ge=1)
    ocr_provider: OcrProvider | None = None
    solve_model: ModelName | None = None
    verify_model: ModelName | None = None
    arbiter_model: ModelName | None = None
    deepseek_api_key: str | None = Field(default=None, max_length=8192)
    gemini_api_key: str | None = Field(default=None, max_length=8192)
    anthropic_api_key: str | None = Field(default=None, max_length=8192)
    glm_api_key: str | None = Field(default=None, max_length=8192)
    clear_deepseek_api_key: bool = False
    clear_gemini_api_key: bool = False
    clear_anthropic_api_key: bool = False
    clear_glm_api_key: bool = False
    expected_pages: int | None = Field(default=None, ge=1, le=1000)
    expected_questions: int | None = Field(default=None, ge=1, le=1000)
    handwritten_expected_questions: int | None = Field(default=None, ge=1, le=1000)
    minimum_ratio: float | None = Field(default=None, gt=0, le=1)
    brightness_percent: int | None = Field(default=None, ge=0, le=100)
    on_ms: int | None = Field(default=None, ge=100, le=60000)
    off_ms: int | None = Field(default=None, ge=0, le=60000)
    palette: Palette | None = None
    handwritten_palette: Palette | None = None
    handwritten_words: HandwrittenWords | None = None

    @field_validator("palette", "handwritten_palette")
    @classmethod
    def complete_palette(cls, value: Palette | None) -> Palette | None:
        return _validate_palette(value) if value is not None else None

    @field_validator("handwritten_words")
    @classmethod
    def complete_words(cls, value: HandwrittenWords | None) -> HandwrittenWords | None:
        return _validate_words(value) if value is not None else None

    @model_validator(mode="after")
    def key_actions_are_unambiguous(self) -> AdminSettingsUpdate:
        for name in ("deepseek", "gemini", "anthropic", "glm"):
            if getattr(self, f"clear_{name}_api_key") and getattr(self, f"{name}_api_key"):
                raise ValueError(f"Cannot set and clear {name} key together")
        return self


class ProviderTestRequest(BaseModel):
    provider: ProviderName
    model: ModelName


class ProviderTestResponse(BaseModel):
    ok: bool
    provider: ProviderName
    model: ModelName
    latency_ms: int
    error_code: str | None = None
    message: str | None = None


class RgbTestRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    rgb: tuple[int, int, int]
    brightness_percent: int = Field(ge=0, le=100)
    on_ms: int = Field(ge=100, le=60000)
    off_ms: int = Field(ge=0, le=60000)

    @field_validator("rgb")
    @classmethod
    def valid_test_rgb(cls, value: tuple[int, int, int]) -> tuple[int, int, int]:
        if any(channel < 0 or channel > 255 for channel in value):
            raise ValueError("RGB channels must be in [0, 255]")
        return value


class RgbTestResponse(BaseModel):
    command_id: int
    session_id: str
    rgb: tuple[int, int, int]
    brightness_percent: int
    on_ms: int
    off_ms: int


class AdminSessionListItem(BaseModel):
    public_id: str
    session_type: str
    status: str
    created_at: datetime
    updated_at: datetime
    expected_questions: int
    frames_count: int
    device_code: str | None = None
    gateway_code: str | None = None


class AdminSessionListResponse(BaseModel):
    items: list[AdminSessionListItem]
    page: int
    limit: int
    total: int
    pages: int


class AdminCaptureItem(BaseModel):
    id: str
    capture_id: str
    status: str
    expected_frames: int
    received_frames: int
    created_at: datetime


class AdminFrameItem(BaseModel):
    frame_id: str
    capture_id: str
    frame_index: int
    storage_key: str
    sha256: str
    width: int | None
    height: int | None
    orientation: int | None
    resolution: str | None
    created_at: datetime


class AdminAnswerItem(BaseModel):
    question_number: int
    status: str
    answer: str | None
    validated: bool
    color: dict[str, Any] | None


class AdminRgbSequenceItem(BaseModel):
    sequence_id: str
    revision: int
    status: str
    answers: str
    item_count: int
    defaults: dict[str, Any]
    palette: dict[str, Any]
    sha256: str
    payload_size: int


class AdminAuditItem(BaseModel):
    event_type: str
    stage: str
    severity: str
    reason_code: str | None
    actor_type: str | None
    payload: dict[str, Any] | None
    created_at: datetime


class AdminSessionDetail(BaseModel):
    public_id: str
    session_type: str
    status: str
    created_at: datetime
    updated_at: datetime
    expected_pages: int
    expected_questions: int
    minimum_ratio: float
    capture_source: str
    settings_version: int
    device_code: str | None
    gateway_code: str | None
    captures: list[AdminCaptureItem]
    frames: list[AdminFrameItem]
    answers: list[AdminAnswerItem]
    rgb_sequence: AdminRgbSequenceItem | None
    delivery: dict[str, Any] | None
    logs: list[AdminAuditItem]


class SignedFrameUrlResponse(BaseModel):
    url: str
    expires_in: int = 300


class AdminActionRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    from_stage: str | None = Field(default=None, max_length=64)


class AdminActionResponse(BaseModel):
    session_id: str
    status: str
    operation_id: str | None = None
    idempotent: bool = False
