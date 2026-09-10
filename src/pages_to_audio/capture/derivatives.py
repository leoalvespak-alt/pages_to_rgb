"""Derived OCR images; originals are never changed or overwritten."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.pages_to_audio.common.errors import FrameConflictError, ReasonCode
from src.pages_to_audio.db.models.image_artifact import ImageArtifact
from src.pages_to_audio.domain.ports.storage import StoragePort
from src.pages_to_audio.storage.keys import derived_key


@dataclass(frozen=True)
class DerivedArtifactResult:
    storage_key: str
    sha256: str
    original_storage_key: str
    original_sha256: str


def _ocr_derivative_bytes(original: bytes) -> bytes:
    """Create a deterministic grayscale JPEG without changing original bytes."""

    from PIL import Image

    with Image.open(BytesIO(original)) as image:
        output = BytesIO()
        image.convert("L").save(output, format="JPEG", quality=92, optimize=True)
    return output.getvalue()


async def persist_ocr_derivative(
    *,
    storage: StoragePort,
    db_session: AsyncSession,
    session_id: str,
    session_db_id: Any,
    capture_id: str,
    frame_index: int,
    frame_id: Any,
    original_storage_key: str,
    original_sha256: str,
    original_bytes: bytes,
) -> DerivedArtifactResult:
    """Store one OCR derivative and link it to the immutable original SHA."""

    derivative_bytes = _ocr_derivative_bytes(original_bytes)
    derivative_sha256 = hashlib.sha256(derivative_bytes).hexdigest()
    storage_key = derived_key(session_id, "ocr", f"{capture_id}-{frame_index}")
    try:
        await storage.put_object(
            "pages-derived",
            storage_key,
            derivative_bytes,
            "image/jpeg",
            sha256=derivative_sha256,
            overwrite=False,
        )
    except Exception as exc:
        from src.pages_to_audio.common.errors import StorageOverwriteForbidden

        if not isinstance(exc, StorageOverwriteForbidden):
            raise
        existing = await storage.get_object("pages-derived", storage_key)
        if hashlib.sha256(existing).hexdigest().lower() != derivative_sha256.lower():
            raise FrameConflictError(
                reason_code=ReasonCode.FRAME_DUPLICATE_CONFLICT,
                message="OCR derived object exists with different content",
            ) from exc

    db_session.add(
        ImageArtifact(
            session_id=session_db_id,
            frame_id=frame_id,
            artifact_type="OCR_DERIVED",
            storage_key=storage_key,
            sha256=derivative_sha256,
            metadata_={
                "original_storage_key": original_storage_key,
                "original_sha256": original_sha256,
                "source": "immutable_frame_original",
            },
        )
    )
    return DerivedArtifactResult(
        storage_key=storage_key,
        sha256=derivative_sha256,
        original_storage_key=original_storage_key,
        original_sha256=original_sha256,
    )
