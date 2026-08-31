"""Fake deterministic activities for Phase 4 — §4.3.6.

These activities read/write real session state in the DB
but simulate the provider work with deterministic stubs.
"""

from __future__ import annotations

import asyncio
from typing import Any

from temporalio import activity

from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Payload dataclasses (kept small — no blobs, §17.2)
# ---------------------------------------------------------------------------


class SessionRef:
    """Minimal session reference passed between activities."""

    def __init__(self, public_id: str) -> None:
        self.public_id = public_id


# ---------------------------------------------------------------------------
# Fake activities — each simulates one workflow step
# ---------------------------------------------------------------------------


@activity.defn(name="fake_validate_locked_session")
async def fake_validate_locked_session(session_public_id: str) -> dict[str, Any]:
    activity.heartbeat()
    logger.info("fake_validate_locked_session", session_id=session_public_id)
    await asyncio.sleep(0)
    return {"status": "ok", "session_id": session_public_id}


@activity.defn(name="fake_materialize_logical_pages")
async def fake_materialize_logical_pages(session_public_id: str) -> dict[str, Any]:
    activity.heartbeat()
    logger.info("fake_materialize_logical_pages", session_id=session_public_id)
    await asyncio.sleep(0)
    return {"logical_pages": 5, "session_id": session_public_id}


@activity.defn(name="fake_preprocess_pages")
async def fake_preprocess_pages(session_public_id: str) -> dict[str, Any]:
    activity.heartbeat()
    logger.info("fake_preprocess_pages", session_id=session_public_id)
    await asyncio.sleep(0)
    return {"preprocessed": 5, "session_id": session_public_id}


@activity.defn(name="fake_run_ocr")
async def fake_run_ocr(session_public_id: str) -> dict[str, Any]:
    activity.heartbeat()
    logger.info("fake_run_ocr", session_id=session_public_id)
    await asyncio.sleep(0)
    return {"ocr_runs": 5, "session_id": session_public_id}


@activity.defn(name="fake_reconstruct_exam")
async def fake_reconstruct_exam(session_public_id: str) -> dict[str, Any]:
    activity.heartbeat()
    logger.info("fake_reconstruct_exam", session_id=session_public_id)
    await asyncio.sleep(0)
    return {"questions_discovered": 10, "incomplete": 0}


@activity.defn(name="fake_rescue_incomplete_questions")
async def fake_rescue_incomplete_questions(session_public_id: str) -> dict[str, Any]:
    activity.heartbeat()
    logger.info("fake_rescue_incomplete_questions", session_id=session_public_id)
    await asyncio.sleep(0)
    return {"rescued": 0}


@activity.defn(name="fake_evaluate_gate1")
async def fake_evaluate_gate1(session_public_id: str) -> dict[str, Any]:
    activity.heartbeat()
    logger.info("fake_evaluate_gate1", session_id=session_public_id)
    await asyncio.sleep(0)
    # Fake: always pass with 10 out of 10
    return {"ready": 10, "expected": 10, "required": 9, "passed": True, "degraded": False}


@activity.defn(name="fake_emit_pre_correction_status")
async def fake_emit_pre_correction_status(
    session_public_id: str, gate1_result: dict[str, Any]
) -> dict[str, Any]:
    activity.heartbeat()
    logger.info("fake_emit_pre_correction_status", session_id=session_public_id)
    await asyncio.sleep(0)
    return {"message_emitted": True}


@activity.defn(name="fake_retrieve_knowledge")
async def fake_retrieve_knowledge(session_public_id: str) -> dict[str, Any]:
    activity.heartbeat()
    logger.info("fake_retrieve_knowledge", session_id=session_public_id)
    await asyncio.sleep(0)
    return {"retrieval_runs": 10}


@activity.defn(name="fake_solve_questions")
async def fake_solve_questions(session_public_id: str) -> dict[str, Any]:
    activity.heartbeat()
    logger.info("fake_solve_questions", session_id=session_public_id)
    await asyncio.sleep(0)
    return {"solved": 10}


@activity.defn(name="fake_verify_questions")
async def fake_verify_questions(session_public_id: str) -> dict[str, Any]:
    activity.heartbeat()
    logger.info("fake_verify_questions", session_id=session_public_id)
    await asyncio.sleep(0)
    return {"verified": 10, "agreements": 10, "disagreements": 0}


@activity.defn(name="fake_arbitrate_disagreements")
async def fake_arbitrate_disagreements(session_public_id: str) -> dict[str, Any]:
    activity.heartbeat()
    logger.info("fake_arbitrate_disagreements", session_id=session_public_id)
    await asyncio.sleep(0)
    return {"arbitrated": 0}


@activity.defn(name="fake_rescue_failed_answers")
async def fake_rescue_failed_answers(session_public_id: str) -> dict[str, Any]:
    activity.heartbeat()
    logger.info("fake_rescue_failed_answers", session_id=session_public_id)
    await asyncio.sleep(0)
    return {"rescued_answers": 0}


@activity.defn(name="fake_evaluate_gate2")
async def fake_evaluate_gate2(session_public_id: str) -> dict[str, Any]:
    activity.heartbeat()
    logger.info("fake_evaluate_gate2", session_id=session_public_id)
    await asyncio.sleep(0)
    return {"validated": 10, "expected": 10, "required": 9, "passed": True}


@activity.defn(name="fake_emit_post_correction_status")
async def fake_emit_post_correction_status(
    session_public_id: str, gate2_result: dict[str, Any]
) -> dict[str, Any]:
    activity.heartbeat()
    logger.info("fake_emit_post_correction_status", session_id=session_public_id)
    await asyncio.sleep(0)
    return {"message_emitted": True}


@activity.defn(name="fake_generate_answer_audio")
async def fake_generate_answer_audio(session_public_id: str) -> dict[str, Any]:
    activity.heartbeat()
    logger.info("fake_generate_answer_audio", session_id=session_public_id)
    await asyncio.sleep(0)
    return {"segments_generated": 10}


@activity.defn(name="fake_assemble_final_audio")
async def fake_assemble_final_audio(session_public_id: str) -> dict[str, Any]:
    activity.heartbeat()
    logger.info("fake_assemble_final_audio", session_id=session_public_id)
    await asyncio.sleep(0)
    return {"audio_assembled": True}


@activity.defn(name="fake_validate_final_audio")
async def fake_validate_final_audio(session_public_id: str) -> dict[str, Any]:
    activity.heartbeat()
    logger.info("fake_validate_final_audio", session_id=session_public_id)
    await asyncio.sleep(0)
    return {"valid": True, "duration_seconds": 120.0}


@activity.defn(name="fake_publish_final_audio")
async def fake_publish_final_audio(session_public_id: str) -> dict[str, Any]:
    activity.heartbeat()
    logger.info("fake_publish_final_audio", session_id=session_public_id)
    await asyncio.sleep(0)
    return {
        "published": True,
        "storage_key": f"sessions/{session_public_id}/audio/final/result.mp3",
    }


@activity.defn(name="fake_complete_session")
async def fake_complete_session(session_public_id: str) -> dict[str, Any]:
    activity.heartbeat()
    logger.info("fake_complete_session", session_id=session_public_id)
    await asyncio.sleep(0)
    return {"completed": True}


ALL_FAKE_ACTIVITIES = [
    fake_validate_locked_session,
    fake_materialize_logical_pages,
    fake_preprocess_pages,
    fake_run_ocr,
    fake_reconstruct_exam,
    fake_rescue_incomplete_questions,
    fake_evaluate_gate1,
    fake_emit_pre_correction_status,
    fake_retrieve_knowledge,
    fake_solve_questions,
    fake_verify_questions,
    fake_arbitrate_disagreements,
    fake_rescue_failed_answers,
    fake_evaluate_gate2,
    fake_emit_post_correction_status,
    fake_generate_answer_audio,
    fake_assemble_final_audio,
    fake_validate_final_audio,
    fake_publish_final_audio,
    fake_complete_session,
]
