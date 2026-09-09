"""Storage factory — seleciona adapter via STORAGE_PROVIDER."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.pages_to_audio.config.settings import get_settings

if TYPE_CHECKING:
    from src.pages_to_audio.domain.ports.storage import StoragePort


def get_storage_adapter() -> StoragePort:
    """S02.4/A16: produção nunca usa fallback em memória silencioso.

    Em APP_ENV=production, provider configurado indisponível é erro explícito.
    Em dev/test, FakeStorageAdapter permanece explícito para testes isolados.
    """
    settings = get_settings()
    if settings.STORAGE_PROVIDER == "r2":
        from src.pages_to_audio.storage.r2_storage import R2StorageAdapter

        adapter = R2StorageAdapter()
        if adapter.is_configured or settings.APP_ENV != "production":
            return adapter  # type: ignore[return-value]
        raise RuntimeError(
            "STORAGE_PROVIDER=r2 em produção sem endpoint/credenciais configurados"
        )
    if settings.supabase.URL and settings.supabase.SERVICE_ROLE_KEY.get_secret_value():
        from src.pages_to_audio.storage.supabase_storage import SupabaseStorageAdapter

        return SupabaseStorageAdapter()  # type: ignore[return-value]
    if settings.APP_ENV == "production":
        raise RuntimeError(
            "Nenhum storage real configurado em produção; fallback em memória proibido"
        )
    from src.pages_to_audio.storage.fake_storage import FakeStorageAdapter

    return FakeStorageAdapter()  # type: ignore[return-value]
