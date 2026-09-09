"""Resolve encrypted Admin provider settings for a new processing session."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.pages_to_audio.admin.settings_service import decrypt_secret
from src.pages_to_audio.config.settings import get_settings
from src.pages_to_audio.db.models.admin_settings import AdminSettings
from src.pages_to_audio.llm.providers.gemini_provider import GeminiProvider
from src.pages_to_audio.ocr.providers.google_document_ai import GoogleDocumentAIProvider
from src.pages_to_audio.storage import get_storage_adapter


async def providers_for_snapshot(
    db: AsyncSession, snapshot: dict[str, object] | None = None
) -> tuple[GoogleDocumentAIProvider, GeminiProvider]:
    """Build Google OCR and Gemini clients from the DB-backed Admin config.

    Only non-secret identifiers are expected in ``snapshot``. Credentials are
    decrypted for the lifetime of the provider object and never copied to the
    session snapshot or returned from this function.
    """
    row = await db.scalar(select(AdminSettings).where(AdminSettings.singleton_key == 1))
    if row is None:
        raise RuntimeError("Admin settings are not initialized")
    settings = get_settings()
    snapshot = snapshot or {}
    ocr_provider = str(snapshot.get("ocr_provider") or row.ocr_provider)
    if ocr_provider != "google_document_ai":
        raise RuntimeError("Only Google Document AI Enterprise OCR is supported")
    gemini_key = decrypt_secret(row.gemini_api_key_encrypted, settings)
    if not gemini_key:
        raise RuntimeError("Gemini provider key is not configured")
    model_values = [
        str(snapshot.get(name) or getattr(row, name))
        for name in ("solve_model", "verify_model", "arbiter_model")
    ]
    if any(value != "gemini-3.1-pro-preview" for value in model_values):
        raise RuntimeError("Only Gemini 3.1 Pro Preview is supported")
    model = model_values[0]
    # S05.6/A22: snapshot integral congelado — projeto/localização/processador e
    # versão vêm do snapshot da sessão; configuração atual só para novas sessões.
    project = snapshot.get("google_document_ai_project_id") or row.google_document_ai_project_id
    location = snapshot.get("google_document_ai_location") or row.google_document_ai_location
    processor = (
        snapshot.get("google_document_ai_processor_id") or row.google_document_ai_processor_id
    )
    processor_version = snapshot.get(
        "google_document_ai_processor_version", row.google_document_ai_processor_version
    )
    if not project or not location or not processor:
        raise RuntimeError("Google Document AI project/location/processor is not configured")
    document_credentials = decrypt_secret(row.google_document_ai_credentials_encrypted, settings)
    if not document_credentials:
        raise RuntimeError("Google Document AI credentials are not configured")
    gemini = GeminiProvider(settings, api_key=gemini_key, model=model)
    ocr = GoogleDocumentAIProvider(
        settings,
        storage=get_storage_adapter(),
        credentials_json=document_credentials,
        project_id=str(project),
        location=str(location),
        processor_id=str(processor),
        processor_version=str(processor_version) if processor_version else None,
    )
    return ocr, gemini
