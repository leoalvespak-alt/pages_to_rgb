"""R2 Storage adapter — S3-compatible, mesma interface de SupabaseStorageAdapter.

Usa boto3 quando disponível (produção). Em testes sem boto3/sem credenciais,
degrada para store in-memory compatível com FakeStorageAdapter.
"""

from __future__ import annotations

from typing import Any

from src.pages_to_audio.common.errors import (
    ReasonCode,
    StorageError,
    StorageOverwriteForbidden,
)
from src.pages_to_audio.config.settings import get_settings
from src.pages_to_audio.domain.ports.storage import StoredObject

_IMMUTABLE_BUCKETS = {"pages-to-rgb-originals", "pages-originals"}


class R2StorageAdapter:
    """S3/R2 adapter com fallback in-memory para testes offline."""

    def __init__(self) -> None:
        settings = get_settings()
        self._endpoint = settings.R2_ENDPOINT.rstrip("/") if settings.R2_ENDPOINT else ""
        self._account_id = settings.R2_ACCOUNT_ID
        self._access_key = settings.R2_ACCESS_KEY_ID.get_secret_value()
        self._secret_key = settings.R2_SECRET_ACCESS_KEY.get_secret_value()
        self._bucket_originals = settings.R2_BUCKET_ORIGINALS
        self._bucket_derived = settings.R2_BUCKET_DERIVED
        self._bucket_ocr = settings.R2_BUCKET_OCR_RAW
        self._bucket_knowledge = settings.R2_BUCKET_KNOWLEDGE
        self._bucket_audio = settings.R2_BUCKET_AUDIO
        # fallback store
        self._fallback_store: dict[tuple[str, str], bytes] = {}
        self._client: Any | None = None
        self._client_error: Exception | None = None
        if self._endpoint and self._access_key and self._secret_key:
            try:
                import boto3
                from botocore.config import Config

                self._client = boto3.client(
                    "s3",
                    endpoint_url=self._endpoint,
                    aws_access_key_id=self._access_key,
                    aws_secret_access_key=self._secret_key,
                    region_name="auto",
                    config=Config(signature_version="s3v4", retries={"max_attempts": 2}),
                )
            except Exception as exc:  # pragma: no cover - missing dep
                self._client_error = exc
                self._client = None

    def _use_fallback(self) -> bool:
        return self._client is None

    def _resolve_bucket(self, bucket: str) -> str:
        mapping = {
            "pages-originals": self._bucket_originals,
            "pages-derived": self._bucket_derived,
            "ocr-raw": self._bucket_ocr,
            "knowledge": self._bucket_knowledge,
            "audio": self._bucket_audio,
            "audit-exports": self._bucket_audio,
        }
        return mapping.get(bucket, bucket)

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
        bucket = self._resolve_bucket(bucket)
        if not overwrite and bucket in _IMMUTABLE_BUCKETS:
            if await self.object_exists(bucket, key):
                raise StorageOverwriteForbidden(bucket, key)
        if self._use_fallback():
            k = (bucket, key)
            if not overwrite and bucket in _IMMUTABLE_BUCKETS and k in self._fallback_store:
                raise StorageOverwriteForbidden(bucket, key)
            self._fallback_store[k] = data
            return StoredObject(
                bucket=bucket,
                key=key,
                sha256=sha256,
                size_bytes=len(data),
                content_type=content_type,
            )
        # real R2 via boto3 — run in thread to avoid blocking event loop
        import asyncio

        def _put() -> None:
            assert self._client is not None
            self._client.put_object(
                Bucket=bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                Metadata={"sha256": sha256},
            )

        try:
            await asyncio.to_thread(_put)
        except Exception as exc:  # pragma: no cover
            raise StorageError(
                f"R2 upload failed: {exc}", reason_code=ReasonCode.STORAGE_UPLOAD_FAILED
            ) from exc
        if not await self.object_exists(bucket, key):
            raise StorageError(
                "Object not found after upload", reason_code=ReasonCode.STORAGE_UPLOAD_FAILED
            )
        return StoredObject(
            bucket=bucket, key=key, sha256=sha256, size_bytes=len(data), content_type=content_type
        )

    async def object_exists(self, bucket: str, key: str) -> bool:
        bucket = self._resolve_bucket(bucket)
        if self._use_fallback():
            return (bucket, key) in self._fallback_store
        import asyncio

        def _head() -> bool:
            assert self._client is not None
            try:
                self._client.head_object(Bucket=bucket, Key=key)
                return True
            except Exception as exc:
                # botocore ClientError 404 -> False
                msg = str(exc)
                if "404" in msg or "Not Found" in msg or "NoSuchKey" in msg:
                    return False
                return False

        return await asyncio.to_thread(_head)

    async def get_object(self, bucket: str, key: str) -> bytes:
        bucket = self._resolve_bucket(bucket)
        if self._use_fallback():
            data = self._fallback_store.get((bucket, key))
            if data is None:
                raise StorageError(
                    f"Object not found: {bucket}/{key}",
                    reason_code=ReasonCode.STORAGE_OBJECT_NOT_FOUND,
                )
            return data
        import asyncio

        def _get() -> bytes:
            assert self._client is not None
            resp = self._client.get_object(Bucket=bucket, Key=key)
            body = resp["Body"].read()
            return body  # type: ignore[no-any-return]

        try:
            return await asyncio.to_thread(_get)
        except Exception as exc:  # pragma: no cover
            raise StorageError(
                f"Object not found: {bucket}/{key}", reason_code=ReasonCode.STORAGE_OBJECT_NOT_FOUND
            ) from exc

    async def create_signed_url(self, bucket: str, key: str, ttl_seconds: int) -> str:
        bucket = self._resolve_bucket(bucket)
        if self._use_fallback():
            return f"https://fake-r2.local/{bucket}/{key}?expires={ttl_seconds}"
        import asyncio

        def _sign() -> str:
            assert self._client is not None
            return self._client.generate_presigned_url(  # type: ignore[no-any-return]
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=ttl_seconds,
            )

        return await asyncio.to_thread(_sign)

    async def delete_object(self, bucket: str, key: str) -> None:
        bucket = self._resolve_bucket(bucket)
        if self._use_fallback():
            self._fallback_store.pop((bucket, key), None)
            return
        import asyncio

        def _del() -> None:
            assert self._client is not None
            self._client.delete_object(Bucket=bucket, Key=key)

        await asyncio.to_thread(_del)

    # helper for tests
    def _inject_fake(self, bucket: str, key: str, data: bytes) -> None:
        self._fallback_store[(bucket, key)] = data
