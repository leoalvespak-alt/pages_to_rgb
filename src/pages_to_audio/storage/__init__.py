"""Storage factory — seleciona adapter via STORAGE_PROVIDER."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.pages_to_audio.config.settings import get_settings

if TYPE_CHECKING:
    from src.pages_to_audio.domain.ports.storage import StoragePort


def get_storage_adapter() -> StoragePort:
    settings = get_settings()
    if settings.STORAGE_PROVIDER == "r2":
        from src.pages_to_audio.storage.r2_storage import R2StorageAdapter

        return R2StorageAdapter()
    if settings.supabase.URL and settings.supabase.SERVICE_ROLE_KEY.get_secret_value():
        from src.pages_to_audio.storage.supabase_storage import SupabaseStorageAdapter

        return SupabaseStorageAdapter()
    from src.pages_to_audio.storage.fake_storage import FakeStorageAdapter

    return FakeStorageAdapter()
