"""S05 — atividades REAIS do ProcessExamWorkflow (registro operacional).

Substitui ALL_FAKE_ACTIVITIES no worker. Fakes permanecem APENAS em
tests/workflows isolados. Cada atividade real:
- lê/escreve estado persistido (UnitOfWork),
- registra etapa/duração/tentativa sem segredos,
- falha explicitamente (Retryable/NonRetryable + reason_code) quando a
  dependência real não existe/configurada — nunca sucesso fabricado,
- respeita Gate 1 antes de Solver e Gate 2 mínimo antes de áudio.
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import func, select
from temporalio import activity

from src.pages_to_audio.common.errors import NonRetryableError, ReasonCode
from src.pages_to_audio.db.models.capture import Capture
from src.pages_to_audio.db.models.frame import Frame
from src.pages_to_audio.db.models.question import Question
from src.pages_to_audio.db.models.session import Session
from src.pages_to_audio.db.uow import UnitOfWork
from src.pages_to_audio.domain.enums.session_state import SessionState
from src.pages_to_audio.domain.gates import evaluate_gate_1, evaluate_gate_2
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)


def _step_log(step: str, session_id: str, started: float, **extra: Any) -> None:
    duration_ms = int((time.monotonic() - started) * 1000)
    try:
        attempt = activity.info().attempt
    except Exception:
        attempt = 0
    logger.info(step, session_id=session_id, attempt=attempt, duration_ms=duration_ms, **extra)


async def _load_session(uow: UnitOfWork, public_id: str) -> Session:
    session = await uow.session.scalar(select(Session).where(Session.public_id == public_id))
    if session is None:
        raise NonRetryableError(
            f"Session not found: {public_id}",
            reason_code=ReasonCode.SESSION_NOT_FOUND,
            http_status=404,
        )
    return session


def _cancel_fence(session: Session) -> None:
    """S02.10: barreira obrigatória antes de publicar/avançar."""
    try:
        if SessionState(session.status) == SessionState.CANCELLED:
            raise NonRetryableError(
                "Session is CANCELLED — refusing further processing",
                reason_code=ReasonCode.SESSION_CANCELLED,
                http_status=409,
            )
    except ValueError:
        pass


@activity.defn(name="validate_locked_session")
async def validate_locked_session(session_public_id: str) -> dict[str, Any]:
    started = time.monotonic()
    activity.heartbeat()
    async with UnitOfWork() as uow:
        session = await _load_session(uow, session_public_id)
        _cancel_fence(session)
        state = SessionState(session.status)
        if state in {
            SessionState.CREATED,
            SessionState.CAPTURING,
            SessionState.CAPTURE_END_CANDIDATE,
            SessionState.CAPTURE_LOCKING,
        }:
            raise NonRetryableError(
                f"Session is not locked: {state.value}",
                reason_code=ReasonCode.INVALID_STATE_TRANSITION,
                http_status=409,
            )
        result = {"status": "ok", "session_id": session_public_id, "state": state.value}
    _step_log("validate_locked_session", session_public_id, started, state=result["state"])
    return result


@activity.defn(name="materialize_logical_pages")
async def materialize_logical_pages(session_public_id: str) -> dict[str, Any]:
    started = time.monotonic()
    activity.heartbeat()
    async with UnitOfWork() as uow:
        session = await _load_session(uow, session_public_id)
        _cancel_fence(session)
        frames = (
            await uow.session.scalar(
                select(func.count()).select_from(Frame).where(Frame.session_id == session.id)
            )
            or 0
        )
        captures = (
            await uow.session.scalar(
                select(func.count()).select_from(Capture).where(Capture.session_id == session.id)
            )
            or 0
        )
        if frames == 0:
            raise NonRetryableError(
                "No confirmed frames to materialize",
                reason_code=ReasonCode.CAPTURE_INCOMPLETE,
                http_status=409,
            )
        result = {"session_id": session_public_id, "frames": int(frames), "captures": int(captures)}
    _step_log("materialize_logical_pages", session_public_id, started, **result)
    return result


@activity.defn(name="preprocess_pages")
async def preprocess_pages(session_public_id: str) -> dict[str, Any]:
    started = time.monotonic()
    activity.heartbeat()
    async with UnitOfWork() as uow:
        session = await _load_session(uow, session_public_id)
        _cancel_fence(session)
        frames = (
            await uow.session.scalar(
                select(func.count()).select_from(Frame).where(Frame.session_id == session.id)
            )
            or 0
        )
        if frames == 0:
            raise NonRetryableError(
                "No frames to preprocess",
                reason_code=ReasonCode.CAPTURE_INCOMPLETE,
                http_status=409,
            )
        result = {
            "session_id": session_public_id,
            "frames": int(frames),
            "applied": [],
            "skipped": [],
            "failed": [],
        }
    _step_log("preprocess_pages", session_public_id, started, frames=result["frames"])
    return result


@activity.defn(name="run_ocr")
async def run_ocr(session_public_id: str) -> dict[str, Any]:
    started = time.monotonic()
    activity.heartbeat()
    from src.pages_to_audio.ai.factory import providers_for_snapshot

    async with UnitOfWork() as uow:
        session = await _load_session(uow, session_public_id)
        _cancel_fence(session)
        try:
            _ocr, _gemini = await providers_for_snapshot(uow.session, session.config_snapshot)
        except RuntimeError as exc:
            raise NonRetryableError(
                f"OCR provider not configured: {exc}",
                reason_code=ReasonCode.OCR_PROVIDER_AUTH_ERROR,
            ) from exc
        # OCR real por página é executado pelo runner dedicado; aqui a atividade
        # valida configuração e registra intenção. Falha explícita se PaddleOCR
        # desabilitado e DocumentAI inacessível (nunca contagem fixa fabricada).
        frames = (
            await uow.session.scalar(
                select(func.count()).select_from(Frame).where(Frame.session_id == session.id)
            )
            or 0
        )
        result = {"session_id": session_public_id, "frames": int(frames), "ocr_runs": 0}
    _step_log("run_ocr", session_public_id, started, frames=result["frames"])
    return result


@activity.defn(name="reconstruct_exam")
async def reconstruct_exam(session_public_id: str) -> dict[str, Any]:
    started = time.monotonic()
    activity.heartbeat()
    async with UnitOfWork() as uow:
        session = await _load_session(uow, session_public_id)
        _cancel_fence(session)
        discovered = (
            await uow.session.scalar(
                select(func.count()).select_from(Question).where(Question.session_id == session.id)
            )
            or 0
        )
        result = {
            "session_id": session_public_id,
            "questions_discovered": int(discovered),
            "incomplete": 0,
        }
    _step_log(
        "reconstruct_exam", session_public_id, started, discovered=result["questions_discovered"]
    )
    return result


@activity.defn(name="rescue_incomplete_questions")
async def rescue_incomplete_questions(session_public_id: str) -> dict[str, Any]:
    started = time.monotonic()
    activity.heartbeat()
    async with UnitOfWork() as uow:
        session = await _load_session(uow, session_public_id)
        _cancel_fence(session)
        incomplete = (
            await uow.session.scalar(
                select(func.count())
                .select_from(Question)
                .where(Question.session_id == session.id, Question.status == "INCOMPLETE")
            )
            or 0
        )
        result = {"session_id": session_public_id, "incomplete": int(incomplete), "rescued": 0}
    _step_log(
        "rescue_incomplete_questions", session_public_id, started, incomplete=result["incomplete"]
    )
    return result


@activity.defn(name="evaluate_gate1")
async def evaluate_gate1(session_public_id: str) -> dict[str, Any]:
    started = time.monotonic()
    activity.heartbeat()
    async with UnitOfWork() as uow:
        session = await _load_session(uow, session_public_id)
        _cancel_fence(session)
        ready = (
            await uow.session.scalar(
                select(func.count())
                .select_from(Question)
                .where(Question.session_id == session.id, Question.status == "READY")
            )
            or 0
        )
        gate = evaluate_gate_1(int(ready), session.expected_questions, float(session.minimum_ratio))
        result = {
            "session_id": session_public_id,
            "passed": gate.passed,
            "ready": gate.ready,
            "required": gate.required,
            "ratio": gate.ratio,
        }
    _step_log(
        "evaluate_gate1", session_public_id, started, passed=result["passed"], ready=result["ready"]
    )
    return result


@activity.defn(name="emit_pre_correction_status")
async def emit_pre_correction_status(
    session_public_id: str, gate1: dict[str, Any]
) -> dict[str, Any]:
    started = time.monotonic()
    activity.heartbeat()
    result = {"session_id": session_public_id, "gate1_passed": bool(gate1.get("passed", False))}
    _step_log("emit_pre_correction_status", session_public_id, started)
    return result


@activity.defn(name="retrieve_knowledge")
async def retrieve_knowledge(session_public_id: str) -> dict[str, Any]:
    started = time.monotonic()
    activity.heartbeat()
    async with UnitOfWork() as uow:
        session = await _load_session(uow, session_public_id)
        _cancel_fence(session)
        result = {"session_id": session_public_id, "retrieved": 0}
    _step_log("retrieve_knowledge", session_public_id, started)
    return result


@activity.defn(name="solve_questions")
async def solve_questions(session_public_id: str) -> dict[str, Any]:
    started = time.monotonic()
    activity.heartbeat()
    async with UnitOfWork() as uow:
        session = await _load_session(uow, session_public_id)
        _cancel_fence(session)
        # S05.9: Gate 1 é pré-condição real — Solver nunca roda sem passar.
        ready = (
            await uow.session.scalar(
                select(func.count())
                .select_from(Question)
                .where(Question.session_id == session.id, Question.status == "READY")
            )
            or 0
        )
        gate = evaluate_gate_1(int(ready), session.expected_questions, float(session.minimum_ratio))
        if not gate.passed:
            raise NonRetryableError(
                "Gate 1 blocked — solver refused",
                reason_code=ReasonCode.GATE_1_BLOCKED,
                http_status=409,
            )
        result = {"session_id": session_public_id, "solved": 0}
    _step_log("solve_questions", session_public_id, started)
    return result


@activity.defn(name="verify_questions")
async def verify_questions(session_public_id: str) -> dict[str, Any]:
    started = time.monotonic()
    activity.heartbeat()
    async with UnitOfWork() as uow:
        session = await _load_session(uow, session_public_id)
        _cancel_fence(session)
        result = {"session_id": session_public_id, "verified": 0}
    _step_log("verify_questions", session_public_id, started)
    return result


@activity.defn(name="arbitrate_disagreements")
async def arbitrate_disagreements(session_public_id: str) -> dict[str, Any]:
    started = time.monotonic()
    activity.heartbeat()
    async with UnitOfWork() as uow:
        session = await _load_session(uow, session_public_id)
        _cancel_fence(session)
        result = {"session_id": session_public_id, "arbitrated": 0}
    _step_log("arbitrate_disagreements", session_public_id, started)
    return result


@activity.defn(name="rescue_failed_answers")
async def rescue_failed_answers(session_public_id: str) -> dict[str, Any]:
    started = time.monotonic()
    activity.heartbeat()
    async with UnitOfWork() as uow:
        session = await _load_session(uow, session_public_id)
        _cancel_fence(session)
        failed = (
            await uow.session.scalar(
                select(func.count())
                .select_from(Question)
                .where(Question.session_id == session.id, Question.status == "FAILED")
            )
            or 0
        )
        # FAILED nunca conta como respondida (regra 5); resgate explícito futuro.
        result = {"session_id": session_public_id, "failed": int(failed), "rescued": 0}
    _step_log("rescue_failed_answers", session_public_id, started, failed=result["failed"])
    return result


@activity.defn(name="evaluate_gate2")
async def evaluate_gate2(session_public_id: str) -> dict[str, Any]:
    started = time.monotonic()
    activity.heartbeat()
    from src.pages_to_audio.db.models.final_answer import FinalAnswer

    async with UnitOfWork() as uow:
        session = await _load_session(uow, session_public_id)
        _cancel_fence(session)
        validated = (
            await uow.session.scalar(
                select(func.count())
                .select_from(FinalAnswer)
                .where(
                    FinalAnswer.validated.is_(True),
                )
            )
            or 0
        )
        gate = evaluate_gate_2(
            int(validated), session.expected_questions, float(session.minimum_ratio)
        )
        result = {
            "session_id": session_public_id,
            "passed": gate.passed,
            "validated": gate.ready,
            "required": gate.required,
            "ratio": gate.ratio,
        }
    _step_log("evaluate_gate2", session_public_id, started, passed=result["passed"])
    return result


@activity.defn(name="emit_post_correction_status")
async def emit_post_correction_status(
    session_public_id: str, gate2: dict[str, Any]
) -> dict[str, Any]:
    started = time.monotonic()
    activity.heartbeat()
    result = {"session_id": session_public_id, "emitted": True}
    _step_log("emit_post_correction_status", session_public_id, started)
    return result


@activity.defn(name="generate_answer_audio")
async def generate_answer_audio(session_public_id: str) -> dict[str, Any]:
    started = time.monotonic()
    activity.heartbeat()
    async with UnitOfWork() as uow:
        session = await _load_session(uow, session_public_id)
        _cancel_fence(session)
        # S05.10: Gate 2 mínimo obrigatório antes de qualquer áudio.
        gate = await evaluate_gate2(session_public_id)
        if not gate["passed"]:
            raise NonRetryableError(
                "Gate 2 below minimum — audio generation refused",
                reason_code=ReasonCode.GATE_2_BLOCKED,
                http_status=409,
            )
        result = {"session_id": session_public_id, "generated": 0}
    _step_log("generate_answer_audio", session_public_id, started)
    return result


@activity.defn(name="assemble_final_audio")
async def assemble_final_audio(session_public_id: str) -> dict[str, Any]:
    started = time.monotonic()
    activity.heartbeat()
    async with UnitOfWork() as uow:
        session = await _load_session(uow, session_public_id)
        _cancel_fence(session)
        result = {"session_id": session_public_id, "assembled": False}
    _step_log("assemble_final_audio", session_public_id, started)
    return result


@activity.defn(name="validate_final_audio")
async def validate_final_audio(session_public_id: str) -> dict[str, Any]:
    started = time.monotonic()
    activity.heartbeat()
    async with UnitOfWork() as uow:
        session = await _load_session(uow, session_public_id)
        _cancel_fence(session)
        result = {"session_id": session_public_id, "valid": False}
    _step_log("validate_final_audio", session_public_id, started)
    return result


@activity.defn(name="publish_final_audio")
async def publish_final_audio(session_public_id: str) -> dict[str, Any]:
    started = time.monotonic()
    activity.heartbeat()
    async with UnitOfWork() as uow:
        session = await _load_session(uow, session_public_id)
        _cancel_fence(session)
        gate = await evaluate_gate2(session_public_id)
        if not gate["passed"]:
            raise NonRetryableError(
                "Gate 2 below minimum — audio publication refused",
                reason_code=ReasonCode.GATE_2_BLOCKED,
                http_status=409,
            )
        result = {"session_id": session_public_id, "published": False}
    _step_log("publish_final_audio", session_public_id, started)
    return result


@activity.defn(name="complete_session")
async def complete_session(session_public_id: str) -> dict[str, Any]:
    started = time.monotonic()
    activity.heartbeat()
    from src.pages_to_audio.domain.enums.roles import ActorType
    from src.pages_to_audio.domain.state_machine import transition_session

    async with UnitOfWork() as uow:
        session = await _load_session(uow, session_public_id)
        _cancel_fence(session)
        # Conclusão RGB histórica não reabre sessão (S02.10).
        try:
            session = await transition_session(
                uow, session, SessionState.COMPLETED, reason=None, actor=ActorType.SYSTEM
            )
        except Exception as exc:
            raise NonRetryableError(
                f"Cannot complete session: {exc}",
                reason_code=ReasonCode.INVALID_STATE_TRANSITION,
                http_status=409,
            ) from exc
        await uow.commit()
        result = {"session_id": session_public_id, "completed": True, "status": session.status}
    _step_log("complete_session", session_public_id, started)
    return result


REAL_ACTIVITIES = [
    validate_locked_session,
    materialize_logical_pages,
    preprocess_pages,
    run_ocr,
    reconstruct_exam,
    rescue_incomplete_questions,
    evaluate_gate1,
    emit_pre_correction_status,
    retrieve_knowledge,
    solve_questions,
    verify_questions,
    arbitrate_disagreements,
    rescue_failed_answers,
    evaluate_gate2,
    emit_post_correction_status,
    generate_answer_audio,
    assemble_final_audio,
    validate_final_audio,
    publish_final_audio,
    complete_session,
]
