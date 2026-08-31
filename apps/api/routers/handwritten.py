"""Handwritten word endpoints — isolado de /gateway (EXAM)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from apps.api.dependencies import SettingsDep, UowDep
from src.pages_to_audio.auth.gateway import verify_gateway_token
from src.pages_to_audio.capture.policy import CapturePolicy, build_capture_policy
from src.pages_to_audio.common.errors import AppError, FrameConflictError, InvalidStateTransition
from src.pages_to_audio.common.ids import new_public_id
from src.pages_to_audio.db.models.capture import Capture
from src.pages_to_audio.db.models.device import Device
from src.pages_to_audio.db.models.gateway import AndroidGateway
from src.pages_to_audio.db.models.session import Session
from src.pages_to_audio.domain.enums.roles import ActorType
from src.pages_to_audio.domain.enums.session_state import SessionState
from src.pages_to_audio.domain.state_machine import transition_session
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/handwritten",
    tags=["handwritten"],
    dependencies=[Depends(verify_gateway_token)],
)

GatewayIdDep = Annotated[str, Depends(verify_gateway_token)]

_hw_command_cursors: dict[str, int] = {}


class HandwrittenSessionStartRequest(BaseModel):
    expected_words: int | None = Field(default=10, ge=1, le=1000)
    expected_pages: int | None = None
    expected_questions: int | None = None
    minimum_ratio: float | None = None
    gateway_code: str = Field(default="", max_length=128)
    device_code: str = Field(default="CAM-001", min_length=1, max_length=128)
    capture_source: str = Field(default="ANDROID_CAMERA", pattern="^(ANDROID_CAMERA|ESP32_CAMERA)$")


class HandwrittenSessionStartResponse(BaseModel):
    session_id: str
    status: str
    expected_pages: int
    expected_questions: int
    expected_words: int
    minimum_ratio: float
    session_type: str


@router.post("/session/start", response_model=HandwrittenSessionStartResponse)
async def handwritten_start(
    body: HandwrittenSessionStartRequest,
    gateway_id: GatewayIdDep,
    settings: SettingsDep,
    uow: UowDep,
) -> HandwrittenSessionStartResponse:
    """Create HANDWRITTEN_WORD session — 10 fotos, 10 palavras, paleta palavra→cor."""
    # Fixed 10 for handwritten test; allow override but default 10
    ep = body.expected_pages if body.expected_pages is not None else 10
    eq = body.expected_questions if body.expected_questions is not None else 10
    if body.expected_words is not None:
        ep = body.expected_words
        eq = body.expected_words
    mr = (
        body.minimum_ratio
        if body.minimum_ratio is not None
        else settings.capture_defaults.MINIMUM_RATIO
    )
    # Force ANDROID_CAMERA for handwritten (só câmera)
    capture_source = "ANDROID_CAMERA"

    gateway = await uow.session.scalar(
        select(AndroidGateway).where(AndroidGateway.gateway_code == gateway_id).with_for_update()
    )
    if gateway is None:
        gateway = AndroidGateway(
            gateway_code=gateway_id,
            last_seen_at=datetime.now(UTC),
            metadata_={"handwritten_start": True},
        )
        uow.session.add(gateway)
        await uow.session.flush()

    device = await uow.session.scalar(
        select(Device).where(Device.device_code == body.device_code).with_for_update()
    )
    if device is None:
        device = Device(
            device_code=body.device_code,
            display_name=body.device_code,
            capture_source=capture_source,
        )
        uow.session.add(device)
        await uow.session.flush()
    else:
        device.capture_source = capture_source
        device.last_seen_at = datetime.now(UTC)
    if not device.enabled:
        raise HTTPException(status_code=403, detail="Device is disabled")

    gateway.last_seen_at = datetime.now(UTC)
    device.last_seen_at = datetime.now(UTC)

    session_id = new_public_id()
    now = datetime.now(UTC)
    session = Session(
        public_id=session_id,
        device_id=device.id,
        gateway_id=gateway.id,
        status=SessionState.CAPTURING.value,
        expected_pages=ep,
        expected_questions=eq,
        minimum_ratio=mr,
        capture_started_at=now,
        capture_source=capture_source,
        session_type="HANDWRITTEN_WORD",
    )
    uow.session.add(session)
    await uow.session.flush()
    logger.info("handwritten_start", session_id=session_id, gateway_id=gateway_id)
    return HandwrittenSessionStartResponse(
        session_id=session_id,
        status=SessionState.CAPTURING.value,
        expected_pages=ep,
        expected_questions=eq,
        expected_words=eq,
        minimum_ratio=mr,
        session_type="HANDWRITTEN_WORD",
    )


@router.get("/session/{session_id}/policy", response_model=CapturePolicy)
async def get_handwritten_policy(
    session_id: str, gateway_id: GatewayIdDep, uow: UowDep
) -> CapturePolicy:
    session = await uow.session.scalar(
        select(Session)
        .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
        .where(Session.public_id == session_id, AndroidGateway.gateway_code == gateway_id)
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    device = await uow.session.get(Device, session.device_id)
    if device is None or not device.enabled:
        raise HTTPException(status_code=403, detail="Device disabled")
    if getattr(session, "session_type", "EXAM") != "HANDWRITTEN_WORD":
        raise HTTPException(status_code=404, detail="Not a handwritten session")
    return build_capture_policy(expected_pages=session.expected_pages)


class HandwrittenGatewayCommandResponse(BaseModel):
    command: str
    cursor: int
    session_id: str
    capture_id: str | None = None
    frames: int | None = None
    gap_ms: int | None = None
    frame_size: str | None = None
    jpeg_quality: int | None = None


@router.get("/session/{session_id}/command", response_model=HandwrittenGatewayCommandResponse)
async def get_handwritten_command(
    session_id: str,
    gateway_id: GatewayIdDep,
    uow: UowDep,
    cursor: int = Query(default=0, ge=0),
    wait_ms: int = Query(default=0, ge=0, le=25000),
    phase: str | None = Query(default=None),
) -> HandwrittenGatewayCommandResponse:
    session = await uow.session.scalar(
        select(Session)
        .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
        .where(Session.public_id == session_id, AndroidGateway.gateway_code == gateway_id)
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    device = await uow.session.get(Device, session.device_id)
    if device is None or not device.enabled:
        raise HTTPException(status_code=403, detail="Device disabled")
    if getattr(session, "session_type", "EXAM") != "HANDWRITTEN_WORD":
        raise HTTPException(status_code=404, detail="Not a handwritten session")

    last = _hw_command_cursors.get(session_id, cursor)
    next_cursor = max(last + 1, cursor + 1)
    if cursor >= last:
        next_cursor = cursor + 1
    _hw_command_cursors[session_id] = next_cursor

    try:
        state = SessionState(session.status)
    except ValueError:
        state = SessionState.CAPTURING

    if state in {SessionState.LOCKED, SessionState.CAPTURE_LOCKING}:
        return HandwrittenGatewayCommandResponse(
            command="STOP", cursor=next_cursor, session_id=session_id
        )
    if state.is_terminal:
        return HandwrittenGatewayCommandResponse(
            command="STOP", cursor=next_cursor, session_id=session_id
        )
    if state == SessionState.CAPTURING:
        norm_phase = (phase or "").strip().upper()
        if norm_phase == "PAUSE":
            return HandwrittenGatewayCommandResponse(
                command="PAUSE", cursor=next_cursor, session_id=session_id
            )
        if norm_phase == "RESUME":
            return HandwrittenGatewayCommandResponse(
                command="RESUME", cursor=next_cursor, session_id=session_id
            )
        if norm_phase == "PROBE":
            cid = f"cap-{next_cursor:03d}-probe"
            return HandwrittenGatewayCommandResponse(
                command="CAPTURE_PROBE",
                cursor=next_cursor,
                session_id=session_id,
                capture_id=cid,
                frames=1,
                gap_ms=180,
                frame_size="1280x720",
                jpeg_quality=75,
            )
        if next_cursor % 5 == 0:
            cid = f"cap-{next_cursor:03d}-probe"
            return HandwrittenGatewayCommandResponse(
                command="CAPTURE_PROBE",
                cursor=next_cursor,
                session_id=session_id,
                capture_id=cid,
                frames=1,
                gap_ms=180,
                frame_size="1280x720",
                jpeg_quality=75,
            )
        if next_cursor % 4 == 0:
            return HandwrittenGatewayCommandResponse(
                command="PING", cursor=next_cursor, session_id=session_id
            )
        cid = f"cap-{next_cursor:03d}-full"
        return HandwrittenGatewayCommandResponse(
            command="CAPTURE_FULL",
            cursor=next_cursor,
            session_id=session_id,
            capture_id=cid,
            frames=1,
            gap_ms=180,
            frame_size="UXGA",
            jpeg_quality=92,
        )
    return HandwrittenGatewayCommandResponse(
        command="PING", cursor=next_cursor, session_id=session_id
    )


@router.post("/session/{session_id}/heartbeat")
async def handwritten_heartbeat(
    session_id: str,
    gateway_id: GatewayIdDep,
    uow: UowDep,
    payload: dict[str, Any] | None = Body(default=None),
) -> dict[str, Any]:
    session = await uow.session.scalar(
        select(Session)
        .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
        .where(Session.public_id == session_id, AndroidGateway.gateway_code == gateway_id)
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    gateway = await uow.session.scalar(
        select(AndroidGateway).where(AndroidGateway.gateway_code == gateway_id).with_for_update()
    )
    if gateway is not None:
        gateway.last_seen_at = datetime.now(UTC)
    device = await uow.session.get(Device, session.device_id)
    if device is not None:
        device.last_seen_at = datetime.now(UTC)
    await uow.session.flush()
    return {"session_id": session_id, "status": session.status, "policy_valid": True}


def _parse_resolution(value: str | None) -> tuple[int | None, int | None]:
    if not value:
        return None, None
    if "x" in value.lower():
        parts = value.lower().split("x")
        try:
            w = int(parts[0].strip())
            h = int(parts[1].strip())
            return w, h
        except (ValueError, IndexError):
            return None, None
    return None, None


@router.post("/session/{session_id}/frame")
async def upload_frame_handwritten(
    session_id: str,
    file: UploadFile,
    gateway_id: GatewayIdDep,
    uow: UowDep,
    x_frame_index: int = Header(..., alias="X-Frame-Index"),
    x_capture_id: str = Header(..., alias="X-Capture-Id"),
    x_sha256: str = Header(..., alias="X-SHA256"),
    x_received_at: str | None = Header(None, alias="X-Received-Android-At"),
    x_resolution: str | None = Header(None, alias="X-Resolution"),
    x_orientation: int | None = Header(None, alias="X-Orientation"),
) -> dict[str, Any]:
    session = await uow.session.scalar(
        select(Session)
        .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
        .where(Session.public_id == session_id, AndroidGateway.gateway_code == gateway_id)
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if getattr(session, "session_type", "EXAM") != "HANDWRITTEN_WORD":
        raise HTTPException(status_code=404, detail="Not a handwritten session")
    device = await uow.session.get(Device, session.device_id)
    if device is None or not device.enabled:
        raise HTTPException(status_code=403, detail="Device disabled")

    data = await file.read()
    from src.pages_to_audio.capture.frame_upload import FrameUploadRequest
    from src.pages_to_audio.capture.frame_upload import upload_frame as _upload
    from src.pages_to_audio.storage import get_storage_adapter

    width, height = _parse_resolution(x_resolution)
    storage = get_storage_adapter()
    req = FrameUploadRequest(
        session_id=session_id,
        capture_id=x_capture_id,
        frame_index=x_frame_index,
        declared_sha256=x_sha256,
        data=data,
        mime_type=file.content_type or "image/jpeg",
        received_android_at=x_received_at,
        capture_source="ANDROID_CAMERA",
        android_orientation=x_orientation,
        source_resolution=x_resolution,
        width=width,
        height=height,
    )
    try:
        result = await _upload(req, storage, uow.session)
    except (AppError, FrameConflictError) as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    return {
        "session_id": session_id,
        "capture_id": x_capture_id,
        "frame_index": x_frame_index,
        "sha256": result.sha256,
        "storage_key": result.storage_key,
        "frame_db_id": result.frame_db_id,
        "duplicate": result.duplicate,
    }


@router.post("/session/{session_id}/capture-complete")
async def handwritten_capture_complete(
    session_id: str,
    gateway_id: GatewayIdDep,
    uow: UowDep,
    capture_id: str = Query(..., min_length=1, max_length=128),
    received_frames: int = Query(..., ge=0),
) -> dict[str, Any]:
    session = await uow.session.scalar(
        select(Session)
        .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
        .where(Session.public_id == session_id, AndroidGateway.gateway_code == gateway_id)
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if getattr(session, "session_type", "EXAM") != "HANDWRITTEN_WORD":
        raise HTTPException(status_code=404, detail="Not a handwritten session")
    device = await uow.session.get(Device, session.device_id)
    if device is None or not device.enabled:
        raise HTTPException(status_code=403, detail="Device disabled")
    cap = await uow.session.scalar(
        select(Capture)
        .where(Capture.session_id == session.id, Capture.capture_id == capture_id)
        .with_for_update()
    )
    if cap is None:
        raise HTTPException(status_code=404, detail="Capture not found")
    cap.received_frames = received_frames
    cap.status = "complete"
    cap.completed_at = datetime.now(UTC)
    await uow.session.flush()
    logger.info(
        "handwritten_capture_complete",
        session_id=session_id,
        capture_id=capture_id,
        received=received_frames,
    )
    return {
        "session_id": session_id,
        "capture_id": capture_id,
        "received_frames": cap.received_frames,
        "status": cap.status,
    }


@router.post("/session/{session_id}/end-signal")
async def handwritten_end_signal(
    session_id: str,
    gateway_id: GatewayIdDep,
    uow: UowDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    session = await uow.session.scalar(
        select(Session)
        .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
        .where(Session.public_id == session_id, AndroidGateway.gateway_code == gateway_id)
        .with_for_update()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if getattr(session, "session_type", "EXAM") != "HANDWRITTEN_WORD":
        raise HTTPException(status_code=404, detail="Not a handwritten session")
    device = await uow.session.get(Device, session.device_id)
    if device is None or not device.enabled:
        raise HTTPException(status_code=403, detail="Device disabled")
    try:
        cur = SessionState(session.status)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Invalid session state") from exc
    if cur.is_terminal:
        return {"session_id": session_id, "status": session.status, "already_terminal": True}
    if cur == SessionState.LOCKED:
        try:
            from src.pages_to_audio.rgb.delivery import SessionBinding, mark_result_processing

            gateway_row = await uow.session.scalar(
                select(AndroidGateway).where(AndroidGateway.gateway_code == gateway_id)
            )
            if gateway_row is not None:
                binding_locked = SessionBinding(session=session, device=device, gateway=gateway_row)
                await mark_result_processing(uow.session, binding_locked)
                await uow.session.flush()
        except Exception as exc:
            logger.warning(
                "hw_mark_processing_idempotent_failed", error=str(exc), session_id=session_id
            )
        return {"session_id": session_id, "status": session.status, "locked": True}
    try:
        if cur == SessionState.CAPTURING:
            session = await transition_session(
                uow,
                session,
                SessionState.CAPTURE_END_CANDIDATE,
                reason=None,
                actor=ActorType.GATEWAY,
                payload={"end_signal": "manual"},
            )
            cur = SessionState(session.status)
        if cur == SessionState.CAPTURE_END_CANDIDATE:
            session = await transition_session(
                uow,
                session,
                SessionState.CAPTURE_LOCKING,
                reason=None,
                actor=ActorType.GATEWAY,
                payload={"end_signal": "manual"},
            )
            cur = SessionState(session.status)
        if cur == SessionState.CAPTURE_LOCKING:
            session.capture_locked_at = datetime.now(UTC)
            await uow.session.flush()
            session = await transition_session(
                uow,
                session,
                SessionState.LOCKED,
                reason=None,
                actor=ActorType.GATEWAY,
                payload={"end_signal": "manual"},
            )
    except InvalidStateTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        from src.pages_to_audio.rgb.delivery import SessionBinding, mark_result_processing

        gateway_row = await uow.session.scalar(
            select(AndroidGateway).where(AndroidGateway.gateway_code == gateway_id)
        )
        if gateway_row is not None:
            binding = SessionBinding(session=session, device=device, gateway=gateway_row)
            await mark_result_processing(uow.session, binding)
            await uow.session.flush()
    except Exception as exc:
        logger.warning("hw_mark_processing_failed", error=str(exc), session_id=session_id)
    try:
        temporal_addr = getattr(settings, "TEMPORAL_ADDRESS", "")
        if temporal_addr:
            from src.pages_to_audio.workflows.starter import TemporalWorkflowStarter

            starter = TemporalWorkflowStarter()
            await starter.start_process_exam(session.public_id)
            logger.info("hw_workflow_start_after_lock", session_id=session_id)
    except Exception as exc:
        logger.warning("hw_workflow_start_failed", error=str(exc), session_id=session_id)
    logger.info("hw_end_signal", session_id=session_id, status=session.status)
    return {"session_id": session_id, "status": session.status, "locked": True}


@router.get("/session/{session_id}/summary")
async def handwritten_summary(
    session_id: str, gateway_id: GatewayIdDep, uow: UowDep
) -> dict[str, Any]:
    from sqlalchemy import func

    from src.pages_to_audio.db.models.final_answer import FinalAnswer
    from src.pages_to_audio.db.models.frame import Frame
    from src.pages_to_audio.db.models.question import Question
    from src.pages_to_audio.db.models.rgb_sequence import RgbSequence
    from src.pages_to_audio.db.models.session_result_delivery import SessionResultDelivery
    from src.pages_to_audio.rgb.policy import HANDWRITTEN_PALETTE

    session = await uow.session.scalar(
        select(Session)
        .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
        .where(Session.public_id == session_id, AndroidGateway.gateway_code == gateway_id)
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if getattr(session, "session_type", "EXAM") != "HANDWRITTEN_WORD":
        raise HTTPException(status_code=404, detail="Not a handwritten session")
    device = await uow.session.get(Device, session.device_id)
    gateway = await uow.session.scalar(
        select(AndroidGateway).where(AndroidGateway.gateway_code == gateway_id)
    )
    if device is None or gateway is None:
        raise HTTPException(status_code=404, detail="Binding not found")
    frames_count = (
        await uow.session.scalar(
            select(func.count()).select_from(Frame).where(Frame.session_id == session.id)
        )
        or 0
    )
    rows = (
        await uow.session.execute(
            select(Question, FinalAnswer)
            .outerjoin(FinalAnswer, FinalAnswer.question_id == Question.id)
            .where(Question.session_id == session.id)
            .order_by(Question.question_number)
        )
    ).all()
    answers: list[dict[str, Any]] = []
    for question, final in rows:
        letter = final.answer if final is not None else None
        color = None
        if letter in {"A", "B", "C", "D", "E"}:
            rgb = HANDWRITTEN_PALETTE[letter].rgb  # type: ignore[index]
            color = {"rgb": list(rgb), "letter": letter}
        answers.append(
            {
                "question_number": question.question_number,
                "status": question.status,
                "answer": letter,
                "validated": bool(final is not None and final.validated),
                "color": color,
            }
        )
    delivery = await uow.session.scalar(
        select(SessionResultDelivery).where(SessionResultDelivery.session_id == session.id)
    )
    rgb_sequence_info: dict[str, Any] | None = None
    if delivery is not None and delivery.active_sequence_id is not None:
        seq = await uow.session.get(RgbSequence, delivery.active_sequence_id)
        if seq is not None:
            rgb_sequence_info = {
                "sequence_id": seq.sequence_id,
                "revision": seq.revision,
                "status": seq.status,
                "answers": seq.answers,
                "item_count": seq.item_count,
                "sha256": seq.payload_sha256,
                "payload_size": seq.payload_size,
            }
    return {
        "session_id": session.public_id,
        "status": session.status,
        "session_type": "HANDWRITTEN_WORD",
        "expected_pages": session.expected_pages,
        "expected_questions": session.expected_questions,
        "expected_words": session.expected_questions,
        "minimum_ratio": float(session.minimum_ratio),
        "capture_source": getattr(session, "capture_source", "ANDROID_CAMERA"),
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "capture_locked_at": session.capture_locked_at.isoformat()
        if session.capture_locked_at
        else None,
        "processing_started_at": getattr(session, "processing_started_at", None).isoformat()
        if getattr(session, "processing_started_at", None)
        else None,
        "device_code": device.device_code,
        "gateway_code": gateway.gateway_code,
        "frames_count": frames_count,
        "questions_count": len(rows),
        "answers": answers,
        "delivery": {
            "command": delivery.command if delivery else None,
            "cursor": delivery.cursor if delivery else None,
            "reason_code": delivery.reason_code if delivery else None,
            "active_sequence_id": str(delivery.active_sequence_id)
            if delivery and delivery.active_sequence_id
            else None,
        }
        if delivery
        else None,
        "rgb_sequence": rgb_sequence_info,
    }


@router.post("/session/{session_id}/debug/publish-rgb")
async def handwritten_debug_publish_rgb(
    session_id: str, gateway_id: GatewayIdDep, uow: UowDep
) -> dict[str, Any]:
    from src.pages_to_audio.rgb.publisher import publish_rgb_for_session

    session = await uow.session.scalar(
        select(Session)
        .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
        .where(Session.public_id == session_id, AndroidGateway.gateway_code == gateway_id)
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if getattr(session, "session_type", "EXAM") != "HANDWRITTEN_WORD":
        raise HTTPException(status_code=404, detail="Not a handwritten session")
    result = await publish_rgb_for_session(uow.session, session_public_id=session_id)
    return {
        "session_id": session_id,
        "command": result.command.value,
        "sequence_id": result.sequence.sequence_id if result.sequence else None,
        "revision": result.sequence.revision if result.sequence else None,
        "sha256": result.sequence.payload_sha256 if result.sequence else None,
        "reason_code": result.reason_code,
        "reused": result.reused,
    }
