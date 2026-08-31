"""Temporal activities that bridge Gate 2 and the firmware RGB channel."""

from __future__ import annotations

from typing import Any

from temporalio import activity

from src.pages_to_audio.db.uow import UnitOfWork
from src.pages_to_audio.rgb.publisher import (
    mark_processing_for_session,
    publish_rgb_for_session,
)


@activity.defn(name="mark_rgb_result_processing")
async def mark_rgb_result_processing(session_public_id: str) -> dict[str, Any]:
    activity.heartbeat()
    async with UnitOfWork() as uow:
        await mark_processing_for_session(uow.session, session_public_id=session_public_id)
        await uow.commit()
    return {"session_id": session_public_id, "command": "RESULT_PROCESSING"}


@activity.defn(name="publish_rgb_result")
async def publish_rgb_result(session_public_id: str) -> dict[str, Any]:
    activity.heartbeat()
    async with UnitOfWork() as uow:
        result = await publish_rgb_for_session(uow.session, session_public_id=session_public_id)
        await uow.commit()
    return {
        "session_id": session_public_id,
        "command": result.command.value,
        "sequence_id": result.sequence.sequence_id if result.sequence else None,
        "revision": result.sequence.revision if result.sequence else None,
        "reason_code": result.reason_code,
        "reused": result.reused,
    }
