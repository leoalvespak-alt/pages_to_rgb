"""Supabase Storage adapter — §2.1."""

from __future__ import annotations

import httpx

from src.pages_to_audio.common.errors import (
    ReasonCode,
    StorageError,
    StorageOverwriteForbidden,
)
from src.pages_to_audio.config.settings import get_settings
from src.pages_to_audio.domain.ports.storage import StoredObject

_TIMEOUT = httpx.Timeout(30.0)
_IMMUTABLE_BUCKETS = {"pages-originals"}


class SupabaseStorageAdapter:
    def __init__(self) -> None:
        settings = get_settings()
        self._url = settings.supabase.URL.rstrip("/")
        self._key = settings.supabase.SERVICE_ROLE_KEY.get_secret_value()
        self._buckets = {
            "pages-originals": settings.supabase.BUCKET_ORIGINALS,
            "pages-derived": settings.supabase.BUCKET_DERIVED,
            "ocr-raw": settings.supabase.BUCKET_OCR_RAW,
            "knowledge": settings.supabase.BUCKET_KNOWLEDGE,
            "audio": settings.supabase.BUCKET_AUDIO,
            "audit-exports": settings.supabase.BUCKET_AUDIT,
        }

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self._key,
            "Authorization": f"Bearer {self._key}",
        }

    def _storage_url(self, bucket: str, key: str) -> str:
        return f"{self._url}/storage/v1/object/{bucket}/{key}"

    async def put_object(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str,
        *,
        sha256: str,
        overwrite: bool = False,
    ) -> StoredObject:
        if not overwrite and bucket in _IMMUTABLE_BUCKETS:
            # Check existence first; reject overwrite
            if await self.object_exists(bucket, key):
                raise StorageOverwriteForbidden(bucket, key)

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            try:
                resp = await client.post(
                    self._storage_url(bucket, key),
                    content=data,
                    headers={
                        **self._headers(),
                        "Content-Type": content_type,
                        "x-upsert": "true" if overwrite else "false",
                    },
                )
                if resp.status_code not in (200, 201):
                    raise StorageError(
                        f"Storage upload failed: {resp.status_code} {resp.text}",
                        reason_code=ReasonCode.STORAGE_UPLOAD_FAILED,
                    )
            except httpx.TimeoutException as exc:
                raise StorageError(
                    "Storage upload timeout",
                    reason_code=ReasonCode.STORAGE_TIMEOUT,
                ) from exc

        # Verify upload succeeded
        if not await self.object_exists(bucket, key):
            raise StorageError(
                "Object not found after upload",
                reason_code=ReasonCode.STORAGE_UPLOAD_FAILED,
            )

        return StoredObject(
            bucket=bucket,
            key=key,
            sha256=sha256,
            size_bytes=len(data),
            content_type=content_type,
        )

    async def object_exists(self, bucket: str, key: str) -> bool:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            try:
                resp = await client.head(
                    self._storage_url(bucket, key),
                    headers=self._headers(),
                )
                return resp.status_code == 200
            except httpx.TimeoutException:
                return False

    async def get_object(self, bucket: str, key: str) -> bytes:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            try:
                resp = await client.get(
                    self._storage_url(bucket, key),
                    headers=self._headers(),
                )
                if resp.status_code != 200:
                    raise StorageError(
                        f"Object not found: {bucket}/{key}",
                        reason_code=ReasonCode.STORAGE_OBJECT_NOT_FOUND,
                    )
                return resp.content
            except httpx.TimeoutException as exc:
                raise StorageError(
                    "Storage download timeout",
                    reason_code=ReasonCode.STORAGE_TIMEOUT,
                ) from exc

    async def create_signed_url(self, bucket: str, key: str, ttl_seconds: int) -> str:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{self._url}/storage/v1/object/sign/{bucket}/{key}",
                json={"expiresIn": ttl_seconds},
                headers={**self._headers(), "Content-Type": "application/json"},
            )
            if resp.status_code != 200:
                raise StorageError(
                    "Failed to create signed URL",
                    reason_code=ReasonCode.STORAGE_DOWNLOAD_FAILED,
                )
            data = resp.json()
            return f"{self._url}/storage/v1{data['signedURL']}"

    async def delete_object(self, bucket: str, key: str) -> None:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            await client.delete(
                self._storage_url(bucket, key),
                headers=self._headers(),
            )
