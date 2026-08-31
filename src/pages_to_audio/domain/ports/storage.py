"""Storage port — §2.1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class StoredObject:
    bucket: str
    key: str
    sha256: str
    size_bytes: int
    content_type: str


class StoragePort(Protocol):
    async def put_object(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str,
        *,
        sha256: str,
        overwrite: bool = False,
    ) -> StoredObject: ...

    async def object_exists(self, bucket: str, key: str) -> bool: ...

    async def get_object(self, bucket: str, key: str) -> bytes: ...

    async def create_signed_url(self, bucket: str, key: str, ttl_seconds: int) -> str: ...

    async def delete_object(self, bucket: str, key: str) -> None: ...
