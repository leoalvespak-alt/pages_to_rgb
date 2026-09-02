"""Single source of truth for administrator-visible provider models.

The catalog deliberately contains only model identifiers that are known by the
provider integrations.  The Admin UI consumes this through the authenticated
API instead of maintaining a second, stale allow-list in JavaScript.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

ProviderKind = Literal["llm", "ocr"]


@dataclass(frozen=True, slots=True)
class ProviderDefinition:
    name: str
    label: str
    kind: ProviderKind
    models: tuple[str, ...]
    endpoint: str
    secret_field: str
    notes: str = ""

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["models"] = list(self.models)
        return value


PROVIDER_CATALOG: tuple[ProviderDefinition, ...] = (
    ProviderDefinition(
        name="gemini",
        label="Google Gemini 3.1 Pro",
        kind="llm",
        models=("gemini-3.1-pro-preview",),
        endpoint="https://generativelanguage.googleapis.com/v1beta",
        secret_field="gemini_api_key",  # noqa: S106 - field name, not a credential
        notes="preview",
    ),
    ProviderDefinition(
        name="google_document_ai",
        label="Google Document AI OCR",
        kind="ocr",
        models=("OCR_PROCESSOR",),
        endpoint="https://{location}-documentai.googleapis.com/v1",
        secret_field="google_document_ai_credentials",  # noqa: S106 - field name, not a credential
    ),
)

_BY_NAME = {item.name: item for item in PROVIDER_CATALOG}
_BY_MODEL = {model: item.name for item in PROVIDER_CATALOG for model in item.models}


def provider_definition(name: str) -> ProviderDefinition:
    try:
        return _BY_NAME[name]
    except KeyError as exc:
        raise ValueError(f"Unknown provider: {name}") from exc


def provider_for_model(model: str) -> str | None:
    return _BY_MODEL.get(model)


def is_supported_model(provider: str, model: str) -> bool:
    definition = _BY_NAME.get(provider)
    return definition is not None and model in definition.models


def catalog_payload() -> list[dict[str, object]]:
    return [item.as_dict() for item in PROVIDER_CATALOG]
