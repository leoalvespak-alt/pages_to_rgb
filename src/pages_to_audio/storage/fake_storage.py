"""In-memory fake storage for tests — same semantics as real storage."""

from __future__ import annotations

from src.pages_to_audio.common.errors import ReasonCode, StorageError, StorageOverwriteForbidden
from src.pages_to_audio.domain.ports.storage import StoredObject

_IMMUTABLE_BUCKETS = {"pages-originals"}


class FakeStorageAdapter:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], bytes] = {}
        self._metadata: dict[tuple[str, str], StoredObject] = {}
        self.simulate_timeout: bool = False
        self.simulate_upload_fail: bool = False

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
        if self.simulate_timeout:
            raise StorageError("Simulated timeout", reason_code=ReasonCode.STORAGE_TIMEOUT)
        if self.simulate_upload_fail:
            raise StorageError("Simulated failure", reason_code=ReasonCode.STORAGE_UPLOAD_FAILED)

        k = (bucket, key)
        if not overwrite and bucket in _IMMUTABLE_BUCKETS and k in self._store:
            raise StorageOverwriteForbidden(bucket, key)

        self._store[k] = data
        obj = StoredObject(
            bucket=bucket,
            key=key,
            sha256=sha256,
            size_bytes=len(data),
            content_type=content_type,
        )
        self._metadata[k] = obj
        return obj

    async def object_exists(self, bucket: str, key: str) -> bool:
        return (bucket, key) in self._store

    async def get_object(self, bucket: str, key: str) -> bytes:
        k = (bucket, key)
        if k not in self._store:
            raise StorageError(
                f"Not found: {bucket}/{key}", reason_code=ReasonCode.STORAGE_OBJECT_NOT_FOUND
            )
        return self._store[k]

    async def create_signed_url(self, bucket: str, key: str, ttl_seconds: int) -> str:
        return f"https://fake-storage.local/{bucket}/{key}?expires={ttl_seconds}"

    async def delete_object(self, bucket: str, key: str) -> None:
        self._store.pop((bucket, key), None)
        self._metadata.pop((bucket, key), None)
