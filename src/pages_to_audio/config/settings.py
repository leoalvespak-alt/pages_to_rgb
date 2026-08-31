from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Single flat settings class — avoids env var collisions from nested BaseSettings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    APP_ENV: Literal["development", "production", "test"] = "development"
    APP_NAME: str = "pages-to-audio"
    APP_BASE_URL: str = "http://localhost:8000"
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: SecretStr = SecretStr("")

    # Supabase (legado — mantido para fallback degradado)
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: SecretStr = SecretStr("")
    SUPABASE_ANON_KEY: SecretStr = SecretStr("")
    SUPABASE_BUCKET_ORIGINALS: str = "pages-originals"
    SUPABASE_BUCKET_DERIVED: str = "pages-derived"
    SUPABASE_BUCKET_OCR_RAW: str = "ocr-raw"
    SUPABASE_BUCKET_KNOWLEDGE: str = "knowledge"
    SUPABASE_BUCKET_AUDIO: str = "audio"
    SUPABASE_BUCKET_AUDIT: str = "audit-exports"

    # Storage provider — supabase (legado) | r2 (PTR usa r2)
    STORAGE_PROVIDER: Literal["supabase", "r2"] = "supabase"
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: SecretStr = SecretStr("")
    R2_SECRET_ACCESS_KEY: SecretStr = SecretStr("")
    R2_ENDPOINT: str = ""
    R2_BUCKET_ORIGINALS: str = "pages-to-rgb-originals"
    R2_BUCKET_DERIVED: str = "pages-to-rgb-derived"
    R2_BUCKET_OCR_RAW: str = "pages-to-rgb-ocr"
    R2_BUCKET_KNOWLEDGE: str = "knowledge"
    R2_BUCKET_AUDIO: str = "audio"
    R2_BUCKET_AUDIT: str = "audit-exports"

    # Auth
    ADMIN_EMAIL: str = ""
    ADMIN_PASSWORD_HASH: str = ""
    SESSION_SECRET: SecretStr = SecretStr("")
    CSRF_SECRET: SecretStr = SecretStr("")
    ANDROID_GATEWAY_TOKEN: SecretStr = SecretStr("")
    ANDROID_GATEWAY_TOKEN_PREVIOUS: SecretStr = SecretStr("")
    DEVICE_HMAC_MASTER_KEY: SecretStr = SecretStr("")
    DEVICE_REPLAY_WINDOW_SECONDS: int = 300

    # Temporal
    TEMPORAL_ADDRESS: str = ""
    TEMPORAL_NAMESPACE: str = "pages-to-audio"
    TEMPORAL_TASK_QUEUE: str = "pages-to-audio-main"
    TEMPORAL_TLS: bool = False

    # Anthropic
    ANTHROPIC_API_KEY: SecretStr = SecretStr("")
    ANTHROPIC_MODEL_SOLVER: str = "claude-opus-5"
    ANTHROPIC_MODEL_VERIFIER: str = "claude-opus-5"
    ANTHROPIC_MODEL_ARBITER: str = "claude-opus-5"

    # DeepSeek
    DEEPSEEK_API_KEY: SecretStr = SecretStr("")
    DEEPSEEK_MODEL: str = "deepseek-v4-pro"
    DEEPSEEK_FALLBACK_ENABLED: bool = True
    DEEPSEEK_CROSSCHECK_ON_HIGH_RISK: bool = False

    # OCR
    GOOGLE_DOCUMENT_AI_PROJECT_ID: str = ""
    GOOGLE_DOCUMENT_AI_LOCATION: str = "us"
    GOOGLE_DOCUMENT_AI_PROCESSOR_ID: str = ""
    GOOGLE_APPLICATION_CREDENTIALS: str = ""
    AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT: str = ""
    AZURE_DOCUMENT_INTELLIGENCE_KEY: SecretStr = SecretStr("")
    PADDLE_OCR_ENABLED: bool = False
    PADDLE_OCR_REMOTE_URL: str = ""

    # TTS
    TTS_PROVIDER: Literal["google", "azure"] = "google"
    TTS_FALLBACK_PROVIDER: Literal["google", "azure"] = "azure"
    GOOGLE_TTS_CREDENTIALS: str = ""
    AZURE_SPEECH_KEY: SecretStr = SecretStr("")
    AZURE_SPEECH_REGION: str = ""

    # Capture defaults
    DEFAULT_EXPECTED_PAGES: int = 30
    DEFAULT_EXPECTED_QUESTIONS: int = 70
    DEFAULT_MINIMUM_RATIO: float = 0.90

    # Temp storage
    LOCAL_TEMP_ROOT: str = "/tmp/pages-to-audio"  # noqa: S108
    LOCAL_TEMP_MAX_GB: float = 2.0
    LOCAL_TEMP_TTL_HOURS: int = 6

    # Concurrency
    MAX_IMAGE_PROCESSING_CONCURRENCY: int = 1
    MAX_OCR_CONCURRENCY: int = 3
    MAX_LLM_CONCURRENCY: int = 4
    MAX_AUDIO_CONCURRENCY: int = 1

    # Retry
    MAX_RECONSTRUCTION_RESCUE_ROUNDS: int = 3
    MAX_ANSWER_RESCUE_ROUNDS: int = 3

    # Retention
    IDEMPOTENCY_TTL_HOURS: int = 48

    # Observability
    SENTRY_DSN: str = ""
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    OTEL_SERVICE_NAME: str = "pages-to-audio"

    # Embedding / RAG
    OPENAI_API_KEY: SecretStr = SecretStr("")
    OPENAI_API_BASE: str = "https://api.openai.com/v1"
    EMBEDDING_PROVIDER: str = "fake"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536
    RAG_TOP_K: int = 10
    RAG_RRF_K: int = 60
    RAG_CHUNK_SIZE: int = 500
    RAG_CHUNK_OVERLAP: int = 50

    # Feature flags
    RERANKER_ENABLED: bool = False
    STATUS_AUDIO_ENABLED: bool = True
    WEB_SEARCH_ENABLED: bool = True

    # Firmware V2.2 RGB result channel
    RGB_RESULTS_ENABLED: bool = True
    RGB_SEQUENCE_SCHEMA_VERSION: int = 1
    RGB_SEQUENCE_MAX_ITEMS: int = 1000
    RGB_SEQUENCE_MAX_JSON_BYTES: int = 262144
    RGB_DEFAULT_BRIGHTNESS_PERCENT: int = 12
    RGB_DEFAULT_ON_MS: int = 3000
    RGB_DEFAULT_OFF_MS: int = 5000

    @field_validator("DEFAULT_MINIMUM_RATIO")
    @classmethod
    def validate_ratio(cls, v: float) -> float:
        if not (0 < v <= 1):
            raise ValueError("DEFAULT_MINIMUM_RATIO must be in (0, 1]")
        return v

    @field_validator("RGB_SEQUENCE_SCHEMA_VERSION")
    @classmethod
    def validate_rgb_schema(cls, v: int) -> int:
        if v != 1:
            raise ValueError("Only RGB sequence schema version 1 is supported")
        return v

    @field_validator("RGB_SEQUENCE_MAX_ITEMS")
    @classmethod
    def validate_rgb_max_items(cls, v: int) -> int:
        if not (1 <= v <= 1000):
            raise ValueError("RGB_SEQUENCE_MAX_ITEMS must be in [1, 1000]")
        return v

    @field_validator("RGB_SEQUENCE_MAX_JSON_BYTES")
    @classmethod
    def validate_rgb_max_json_bytes(cls, v: int) -> int:
        if not (1 <= v <= 262144):
            raise ValueError("RGB_SEQUENCE_MAX_JSON_BYTES must be in [1, 262144]")
        return v

    @field_validator("RGB_DEFAULT_BRIGHTNESS_PERCENT")
    @classmethod
    def validate_rgb_brightness(cls, v: int) -> int:
        if not (0 <= v <= 100):
            raise ValueError("RGB_DEFAULT_BRIGHTNESS_PERCENT must be in [0, 100]")
        return v

    @field_validator("RGB_DEFAULT_ON_MS")
    @classmethod
    def validate_rgb_on_ms(cls, v: int) -> int:
        if not (100 <= v <= 60000):
            raise ValueError("RGB_DEFAULT_ON_MS must be in [100, 60000]")
        return v

    @field_validator("RGB_DEFAULT_OFF_MS")
    @classmethod
    def validate_rgb_off_ms(cls, v: int) -> int:
        if not (0 <= v <= 60000):
            raise ValueError("RGB_DEFAULT_OFF_MS must be in [0, 60000]")
        return v

    @model_validator(mode="after")
    def validate_production_secrets(self) -> AppSettings:
        if self.APP_ENV != "production":
            return self
        required: dict[str, str] = {
            "DATABASE_URL": self.DATABASE_URL.get_secret_value(),
            "SESSION_SECRET": self.SESSION_SECRET.get_secret_value(),
            "TEMPORAL_ADDRESS": self.TEMPORAL_ADDRESS,
        }
        if self.STORAGE_PROVIDER == "supabase":
            required["SUPABASE_URL"] = self.SUPABASE_URL
            required["SUPABASE_SERVICE_ROLE_KEY"] = (
                self.SUPABASE_SERVICE_ROLE_KEY.get_secret_value()
            )
        else:
            required["R2_ACCOUNT_ID"] = self.R2_ACCOUNT_ID
            required["R2_ENDPOINT"] = self.R2_ENDPOINT
            required["R2_ACCESS_KEY_ID"] = self.R2_ACCESS_KEY_ID.get_secret_value()
            required["R2_SECRET_ACCESS_KEY"] = self.R2_SECRET_ACCESS_KEY.get_secret_value()
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"Production requires these settings: {missing}")
        return self

    def __repr__(self) -> str:
        return f"AppSettings(APP_ENV={self.APP_ENV!r}, APP_NAME={self.APP_NAME!r})"

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        # mode='json' ensures SecretStr values become '**********' (not raw objects)
        kwargs.setdefault("mode", "json")
        data: dict[str, Any] = super().model_dump(**kwargs)
        self._redact_secrets(data)
        return data

    def _redact_secrets(self, obj: object) -> None:
        if isinstance(obj, dict):
            for k in list(obj.keys()):
                key_upper = str(k).upper()
                if any(s in key_upper for s in ("KEY", "SECRET", "PASSWORD", "TOKEN", "DSN")):
                    obj[k] = "***"
                else:
                    self._redact_secrets(obj[k])
        elif isinstance(obj, list):
            for item in obj:
                self._redact_secrets(item)

    # Convenience accessors (for code that uses settings.supabase.URL etc.)
    @property
    def database(self) -> _DatabaseProxy:
        return _DatabaseProxy(self)

    @property
    def supabase(self) -> _SupabaseProxy:
        return _SupabaseProxy(self)

    @property
    def r2(self) -> _R2Proxy:
        return _R2Proxy(self)

    @property
    def auth(self) -> _AuthProxy:
        return _AuthProxy(self)

    @property
    def temporal(self) -> _TemporalProxy:
        return _TemporalProxy(self)

    @property
    def capture_defaults(self) -> _CaptureDefaultsProxy:
        return _CaptureDefaultsProxy(self)


class _DatabaseProxy:
    def __init__(self, s: AppSettings) -> None:
        self._s = s

    @property
    def DATABASE_URL(self) -> SecretStr:  # noqa: N802
        return self._s.DATABASE_URL


class _SupabaseProxy:
    def __init__(self, s: AppSettings) -> None:
        self._s = s

    @property
    def URL(self) -> str:  # noqa: N802
        return self._s.SUPABASE_URL

    @property
    def SERVICE_ROLE_KEY(self) -> SecretStr:  # noqa: N802
        return self._s.SUPABASE_SERVICE_ROLE_KEY

    @property
    def BUCKET_ORIGINALS(self) -> str:  # noqa: N802
        return self._s.SUPABASE_BUCKET_ORIGINALS

    @property
    def BUCKET_DERIVED(self) -> str:  # noqa: N802
        return self._s.SUPABASE_BUCKET_DERIVED

    @property
    def BUCKET_OCR_RAW(self) -> str:  # noqa: N802
        return self._s.SUPABASE_BUCKET_OCR_RAW

    @property
    def BUCKET_KNOWLEDGE(self) -> str:  # noqa: N802
        return self._s.SUPABASE_BUCKET_KNOWLEDGE

    @property
    def BUCKET_AUDIO(self) -> str:  # noqa: N802
        return self._s.SUPABASE_BUCKET_AUDIO

    @property
    def BUCKET_AUDIT(self) -> str:  # noqa: N802
        return self._s.SUPABASE_BUCKET_AUDIT


class _R2Proxy:
    def __init__(self, s: AppSettings) -> None:
        self._s = s

    @property
    def ACCOUNT_ID(self) -> str:  # noqa: N802
        return self._s.R2_ACCOUNT_ID

    @property
    def ACCESS_KEY_ID(self) -> SecretStr:  # noqa: N802
        return self._s.R2_ACCESS_KEY_ID

    @property
    def SECRET_ACCESS_KEY(self) -> SecretStr:  # noqa: N802
        return self._s.R2_SECRET_ACCESS_KEY

    @property
    def ENDPOINT(self) -> str:  # noqa: N802
        return self._s.R2_ENDPOINT

    @property
    def BUCKET_ORIGINALS(self) -> str:  # noqa: N802
        return self._s.R2_BUCKET_ORIGINALS

    @property
    def BUCKET_DERIVED(self) -> str:  # noqa: N802
        return self._s.R2_BUCKET_DERIVED

    @property
    def BUCKET_OCR_RAW(self) -> str:  # noqa: N802
        return self._s.R2_BUCKET_OCR_RAW

    @property
    def BUCKET_KNOWLEDGE(self) -> str:  # noqa: N802
        return self._s.R2_BUCKET_KNOWLEDGE

    @property
    def BUCKET_AUDIO(self) -> str:  # noqa: N802
        return self._s.R2_BUCKET_AUDIO

    @property
    def BUCKET_AUDIT(self) -> str:  # noqa: N802
        return self._s.R2_BUCKET_AUDIT


class _AuthProxy:
    def __init__(self, s: AppSettings) -> None:
        self._s = s

    @property
    def ANDROID_GATEWAY_TOKEN(self) -> SecretStr:  # noqa: N802
        return self._s.ANDROID_GATEWAY_TOKEN

    @property
    def ANDROID_GATEWAY_TOKEN_PREVIOUS(self) -> SecretStr:  # noqa: N802
        return self._s.ANDROID_GATEWAY_TOKEN_PREVIOUS

    @property
    def DEVICE_HMAC_MASTER_KEY(self) -> SecretStr:  # noqa: N802
        return self._s.DEVICE_HMAC_MASTER_KEY

    @property
    def DEVICE_REPLAY_WINDOW_SECONDS(self) -> int:  # noqa: N802
        return self._s.DEVICE_REPLAY_WINDOW_SECONDS

    @property
    def SESSION_SECRET(self) -> SecretStr:  # noqa: N802
        return self._s.SESSION_SECRET


class _TemporalProxy:
    def __init__(self, s: AppSettings) -> None:
        self._s = s

    @property
    def ADDRESS(self) -> str:  # noqa: N802
        return self._s.TEMPORAL_ADDRESS

    @property
    def NAMESPACE(self) -> str:  # noqa: N802
        return self._s.TEMPORAL_NAMESPACE

    @property
    def TASK_QUEUE(self) -> str:  # noqa: N802
        return self._s.TEMPORAL_TASK_QUEUE


class _CaptureDefaultsProxy:
    def __init__(self, s: AppSettings) -> None:
        self._s = s

    @property
    def EXPECTED_PAGES(self) -> int:  # noqa: N802
        return self._s.DEFAULT_EXPECTED_PAGES

    @property
    def EXPECTED_QUESTIONS(self) -> int:  # noqa: N802
        return self._s.DEFAULT_EXPECTED_QUESTIONS

    @property
    def MINIMUM_RATIO(self) -> float:  # noqa: N802
        return self._s.DEFAULT_MINIMUM_RATIO


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
