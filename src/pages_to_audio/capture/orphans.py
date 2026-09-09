"""S02.3/§12.3 — órfãos storage↔DB: registro + reconciliação (transação própria)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import select

from src.pages_to_audio.db.engine import get_session_factory
from src.pages_to_audio.db.models.capture import Capture
from src.pages_to_audio.db.models.frame import Frame
from src.pages_to_audio.db.models.session import Session
from src.pages_to_audio.db.models.storage_orphan import StorageOrphan
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)


def parse_frame_key(key: str) -> tuple[str, str, int] | None:
    """sessions/{sid}/frames/{capture_id}/{frame_index}.jpg (storage.keys.frame_key)."""
    parts = key.split("/")
    if len(parts) != 5 or parts[0] != "sessions" or parts[2] != "frames":
        return None
    try:
        return parts[1], parts[3], int(parts[4].rsplit(".", 1)[0])
    except (ValueError, IndexError):
        return None


async def record_orphan(*, bucket: str, key: str, sha256: str, session_db_id: object) -> None:
    """Registra órfão em transação própria (sobrevive ao rollback do UoW chamador)."""
    factory = get_session_factory()
    async with factory() as db:
        db.add(
            StorageOrphan(
                bucket=bucket,
                key=key,
                sha256=sha256,
                session_id=session_db_id,  # type: ignore[arg-type]
                created_at=datetime.now(UTC),
            )
        )
        await db.commit()


async def reconcile(*, limit: int = 200) -> dict[str, int]:
    """Varre órfãos não resolvidos; idempotente e seguro para rodar repetido."""
    from src.pages_to_audio.storage import get_storage_adapter

    storage = get_storage_adapter()
    factory = get_session_factory()
    stats = {"linked": 0, "recreated": 0, "discarded": 0, "kept": 0}
    async with factory() as db:
        orphans = (
            (
                await db.execute(
                    select(StorageOrphan)
                    .where(StorageOrphan.resolved_at.is_(None))
                    .order_by(StorageOrphan.created_at)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        for orphan in orphans:
            try:
                exists = await storage.object_exists(orphan.bucket, orphan.key)
            except Exception as exc:
                logger.warning("orphan_head_failed", key=orphan.key, error=str(exc)[:160])
                stats["kept"] += 1
                continue
            if not exists:
                orphan.resolved_at = datetime.now(UTC)
                orphan.resolution = "discarded"
                stats["discarded"] += 1
                continue
            parsed = parse_frame_key(orphan.key)
            if parsed is None:
                orphan.resolved_at = datetime.now(UTC)
                orphan.resolution = "unparseable_key"
                stats["kept"] += 1
                continue
            sid, capture_id, frame_index = parsed
            session = await db.scalar(select(Session).where(Session.public_id == sid))
            if session is None:
                stats["kept"] += 1
                continue
            capture = await db.scalar(
                select(Capture).where(
                    Capture.session_id == session.id, Capture.capture_id == capture_id
                )
            )
            if capture is None:
                stats["kept"] += 1
                continue
            frame = await db.scalar(
                select(Frame).where(
                    Frame.capture_id == capture.id, Frame.frame_index == frame_index
                )
            )
            if frame is not None:
                if str(frame.sha256).lower() == str(orphan.sha256).lower():
                    orphan.resolved_at = datetime.now(UTC)
                    orphan.resolution = "already_linked"
                    stats["linked"] += 1
                else:
                    orphan.resolved_at = datetime.now(UTC)
                    orphan.resolution = "conflict_kept"
                    stats["kept"] += 1
                continue
            try:
                raw = await storage.get_object(orphan.bucket, orphan.key)
            except Exception as exc:
                logger.warning("orphan_get_failed", key=orphan.key, error=str(exc)[:160])
                stats["kept"] += 1
                continue
            if hashlib.sha256(raw).hexdigest().lower() != str(orphan.sha256).lower():
                orphan.resolved_at = datetime.now(UTC)
                orphan.resolution = "hash_mismatch_kept"
                stats["kept"] += 1
                continue
            db.add(
                Frame(
                    session_id=session.id,
                    capture_id=capture.id,
                    frame_index=frame_index,
                    sha256=str(orphan.sha256).lower(),
                    content_length=len(raw),
                    mime_type="image/jpeg",
                    storage_key=orphan.key,
                    status="accepted",
                )
            )
            capture.received_frames = int(capture.received_frames or 0) + 1
            orphan.resolved_at = datetime.now(UTC)
            orphan.resolution = "recreated"
            stats["recreated"] += 1
        await db.commit()
    return stats
