from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ProviderName = Literal["gemini", "google_document_ai"]
OcrProvider = Literal["google_document_ai"]
ModelName = Literal["gemini-3.1-pro-preview", "OCR_PROCESSOR"]
ReasoningModelName = Literal["gemini-3.1-pro-preview"]


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
    solve_model: ReasoningModelName
    verify_model: ReasoningModelName
    arbiter_model: ReasoningModelName
    gemini_api_key: str = ""
    google_document_ai_project_id: str = ""
    google_document_ai_location: str = "us"
    google_document_ai_processor_id: str = ""
    google_document_ai_processor_version: str | None = None
    google_document_ai_credentials: str = ""
    gemini_configured: bool
    google_document_ai_configured: bool
    google_document_ai_credentials_configured: bool
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
    solve_model: ReasoningModelName | None = None
    verify_model: ReasoningModelName | None = None
    arbiter_model: ReasoningModelName | None = None
    deepseek_api_key: str | None = Field(default=None, max_length=8192)
    gemini_api_key: str | None = Field(default=None, max_length=8192)
    anthropic_api_key: str | None = Field(default=None, max_length=8192)
    glm_api_key: str | None = Field(default=None, max_length=8192)
    google_document_ai_project_id: str | None = Field(default=None, max_length=256)
    google_document_ai_location: str | None = Field(default=None, min_length=1, max_length=32)
    google_document_ai_processor_id: str | None = Field(default=None, max_length=256)
    google_document_ai_processor_version: str | None = Field(default=None, max_length=256)
    google_document_ai_credentials: str | None = Field(default=None, max_length=32768)
    clear_google_document_ai_credentials: bool = False
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
        if self.clear_google_document_ai_credentials and self.google_document_ai_credentials:
            raise ValueError("Cannot set and clear Google Document AI credentials together")
        return self


class ProviderTestRequest(BaseModel):
    provider: ProviderName
    model: ModelName
    # S06.6: verificação usa a configuração PROPOSTA no formulário (quando
    # enviada), nunca a credencial antiga salva — salvo apenas como fallback
    # quando o campo proposto é omitido.
    api_key: str | None = Field(default=None, max_length=8192)
    google_document_ai_project_id: str | None = Field(default=None, max_length=256)
    google_document_ai_location: str | None = Field(default=None, max_length=32)
    google_document_ai_processor_id: str | None = Field(default=None, max_length=256)
    google_document_ai_credentials: str | None = Field(default=None, max_length=32768)


class ProviderTestResponse(BaseModel):
    ok: bool
    provider: ProviderName
    model: ModelName
    latency_ms: int
    error_code: str | None = None
    message: str | None = None


class ProviderCatalogItem(BaseModel):
    name: ProviderName
    label: str
    kind: Literal["llm", "ocr"]
    models: list[str]
    endpoint: str
    secret_field: str
    notes: str = ""


class ProviderCatalogResponse(BaseModel):
    providers: list[ProviderCatalogItem]


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
    command_id: str
    session_id: str
    rgb: tuple[int, int, int]
    brightness_percent: int
    on_ms: int
    off_ms: int


class CameraCapabilitiesV1(BaseModel):
    """Read-only capability report for the camera contract v2."""

    version: Literal["v1"] = "v1"
    contract_version: Literal["v2"] = "v2"
    firmware_version: str = "unknown"
    driver_version: str = "esp32-camera 2.1.7"
    available: dict[str, Any]
    protected: dict[str, Any]
    unavailable: dict[str, str]
    feature_enabled: bool = False
    compatible: bool = False
    reason_code: str | None = None
    message: str


class CameraProfileCreate(BaseModel):
    """Requested values for a new immutable OCR/PHOTO revision."""

    device_code: str | None = Field(default=None, max_length=63, pattern=r"^[A-Za-z0-9._:-]+$")
    mode: str = Field(default="OCR", min_length=1, max_length=16)
    frame_size: Literal["UXGA"] = "UXGA"
    esp_jpeg_quality: int = Field(default=10, ge=8, le=12)
    frame_count: int | None = Field(default=None, ge=1, le=3)
    intra_frame_gap_ms: int = Field(default=220, ge=180, le=300)
    page_interval_ms: int = Field(default=5000, ge=5000, le=86_400_000)
    brightness: int = Field(default=0, ge=-2, le=2)
    contrast: int = Field(default=1, ge=-2, le=2)
    saturation: int = Field(default=0, ge=-2, le=2)
    awb: bool = True
    awb_gain: bool = True
    wb_mode: Literal["AUTO", "SUNNY", "CLOUDY", "OFFICE", "HOME"] = "AUTO"
    aec: bool = True
    aec2: bool = True
    agc: bool = True
    bpc: bool = True
    wpc: bool = True
    raw_gamma: bool = True
    lens_correction: bool = True
    dcw: bool = True
    hmirror: bool = False
    vflip: bool = False
    special_effect: Literal["NORMAL", "NEGATIVE", "GRAYSCALE", "RED", "GREEN", "BLUE", "SEPIA"] = (
        "NORMAL"
    )
    colorbar: bool = False

    @model_validator(mode="after")
    def validate_mode(self) -> CameraProfileCreate:
        from src.pages_to_audio.camera_profiles.contract import normalize_camera_mode

        normalize_camera_mode(self.mode)
        return self


class CameraProfileRevisionRead(BaseModel):
    public_id: str
    device_code: str | None
    mode: Literal["OCR", "PHOTO"]
    revision: int
    capabilities_version: str
    requested: dict[str, Any]
    effective: dict[str, Any]
    created_by: str | None
    created_at: datetime
    active: bool


class CameraProfileListResponse(BaseModel):
    items: list[CameraProfileRevisionRead]
    feature_enabled: bool


class AdminDeviceRead(BaseModel):
    device_code: str
    display_name: str
    enabled: bool
    firmware_version: str | None
    camera_capabilities_version: str | None = None
    capture_source: str
    last_seen_at: datetime | None = None
    telemetry: dict[str, Any] = Field(default_factory=dict)


class AdminDeviceListResponse(BaseModel):
    items: list[AdminDeviceRead]


class RgbDeviceTestRequest(BaseModel):
    """Manual physical RGB request; the device is addressed by the URL."""

    model_config = ConfigDict(extra="forbid")

    session_id: str | None = Field(default=None, max_length=64)
    rgb: tuple[int, int, int] | None = None
    hex_color: str | None = Field(default=None, pattern=r"^#?[0-9A-Fa-f]{6}$")
    brightness_percent: int = Field(default=12, ge=0, le=100)
    on_ms: int = Field(default=3000, ge=100, le=60000)
    off_ms: int = Field(default=5000, ge=0, le=60000)
    repeat_count: int = Field(default=1, ge=1, le=20)

    @model_validator(mode="after")
    def normalize_color(self) -> RgbDeviceTestRequest:
        if self.rgb is None and self.hex_color is None:
            raise ValueError("Provide rgb or hex_color")
        if self.rgb is not None and self.hex_color is not None:
            raise ValueError("Provide only one of rgb or hex_color")
        if self.rgb is not None and any(channel < 0 or channel > 255 for channel in self.rgb):
            raise ValueError("RGB channels must be in [0, 255]")
        if self.hex_color is not None:
            value = self.hex_color.removeprefix("#")
            self.rgb = tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[assignment]
        if (self.on_ms + self.off_ms) * self.repeat_count > 120000:
            raise ValueError("RGB test duration must be at most 120 seconds")
        return self


class RgbDeviceCommandRead(BaseModel):
    command_id: str
    device_code: str
    session_id: str | None
    kind: Literal["TEST", "STOP"]
    status: str
    requested: dict[str, Any]
    effective: dict[str, Any]
    expires_at: datetime
    failure_reason: str | None = None
    idempotent: bool = False


class RgbDeviceCommandListResponse(BaseModel):
    items: list[RgbDeviceCommandRead]
    cursor: int


class RgbDeviceEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["FORWARDED", "RECEIVED", "APPLIED", "OFF", "FAILED", "EXPIRED", "CANCELLED"]
    effective_payload: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    firmware_version: str | None = Field(default=None, max_length=128)
    device_timestamp: datetime | None = None


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
    frames_total: int = 0
    frames_page: int = 1
    answers: list[AdminAnswerItem]
    rgb_sequence: AdminRgbSequenceItem | None
    delivery: dict[str, Any] | None
    logs: list[AdminAuditItem]
    logs_total: int = 0
    logs_page: int = 1


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
