from __future__ import annotations

import hashlib
import math
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Response
from sqlalchemy import func, or_, select

from apps.api.dependencies import SettingsDep, UowDep
from apps.api.schemas.admin import (
    AdminActionRequest,
    AdminActionResponse,
    AdminAnswerItem,
    AdminAuditItem,
    AdminCaptureItem,
    AdminFrameItem,
    AdminRgbSequenceItem,
    AdminSessionDetail,
    AdminSessionListItem,
    AdminSessionListResponse,
    SignedFrameUrlResponse,
)
from src.pages_to_audio.admin.settings_service import rgb_for_answer
from src.pages_to_audio.auth.admin import AdminClaimsDep, AdminCsrfDep
from src.pages_to_audio.db.models.audit_event import AuditEvent
from src.pages_to_audio.db.models.capture import Capture
from src.pages_to_audio.db.models.device import Device
from src.pages_to_audio.db.models.final_answer import FinalAnswer
from src.pages_to_audio.db.models.frame import Frame
from src.pages_to_audio.db.models.gateway import AndroidGateway
from src.pages_to_audio.db.models.question import Question
from src.pages_to_audio.db.models.rgb_sequence import RgbSequence
from src.pages_to_audio.db.models.session import Session
from src.pages_to_audio.db.models.session_result_delivery import SessionResultDelivery
from src.pages_to_audio.domain.enums.roles import ActorType
from src.pages_to_audio.domain.enums.session_state import SessionState
from src.pages_to_audio.domain.state_machine import ALLOWED_TRANSITIONS, transition_session
from src.pages_to_audio.rgb.delivery import SessionBinding, get_or_create_delivery
from src.pages_to_audio.rgb.schemas import RgbResultCommand
from src.pages_to_audio.storage import get_storage_adapter

router = APIRouter(prefix="/admin/sessions", tags=["admin-sessions"])


@router.get("", response_model=AdminSessionListResponse)
async def list_sessions(
    _claims: AdminClaimsDep,
    uow: UowDep,
    response: Response,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    type_: str = Query(default="all", alias="type"),
    status: str = Query(default="all"),
    q: str = Query(default="", max_length=128),
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> AdminSessionListResponse:
    if type_ not in {"all", "EXAM", "HANDWRITTEN_WORD"}:
        raise HTTPException(status_code=422, detail="Invalid session type")
    valid_states = {state.value for state in SessionState}
    if status != "all" and status not in valid_states:
        raise HTTPException(status_code=422, detail="Invalid session status")

    filters: list[Any] = []
    if type_ != "all":
        filters.append(Session.session_type == type_)
    if status != "all":
        filters.append(Session.status == status)
    if created_from is not None:
        filters.append(Session.created_at >= created_from)
    if created_to is not None:
        filters.append(Session.created_at <= created_to)
    if q.strip():
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(
                Session.public_id.ilike(pattern),
                Device.device_code.ilike(pattern),
                AndroidGateway.gateway_code.ilike(pattern),
            )
        )

    base = (
        select(Session, Device.device_code, AndroidGateway.gateway_code, func.count(Frame.id))
        .join(Device, Session.device_id == Device.id)
        .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
        .outerjoin(Frame, Frame.session_id == Session.id)
        .where(*filters)
        .group_by(Session.id, Device.device_code, AndroidGateway.gateway_code)
    )
    total = int(
        await uow.session.scalar(
            select(func.count(Session.id))
            .join(Device, Session.device_id == Device.id)
            .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
            .where(*filters)
        )
        or 0
    )
    rows = (
        await uow.session.execute(
            base.order_by(Session.created_at.desc()).offset((page - 1) * limit).limit(limit)
        )
    ).all()
    response.headers["Cache-Control"] = "no-store"
    return AdminSessionListResponse(
        items=[
            AdminSessionListItem(
                public_id=session.public_id,
                session_type=session.session_type,
                status=session.status,
                created_at=session.created_at,
                updated_at=session.updated_at,
                expected_questions=session.expected_questions,
                frames_count=int(frames_count),
                device_code=device_code,
                gateway_code=gateway_code,
            )
            for session, device_code, gateway_code, frames_count in rows
        ],
        page=page,
        limit=limit,
        total=total,
        pages=math.ceil(total / limit) if total else 0,
    )


async def _session_binding(
    uow: UowDep, public_id: str, *, lock: bool = False
) -> tuple[Session, Device, AndroidGateway]:
    stmt = (
        select(Session, Device, AndroidGateway)
        .join(Device, Session.device_id == Device.id)
        .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
        .where(Session.public_id == public_id)
    )
    if lock:
        stmt = stmt.with_for_update()
    row = (await uow.session.execute(stmt)).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return row


@router.get("/{public_id}", response_model=AdminSessionDetail)
async def session_detail(
    public_id: str, _claims: AdminClaimsDep, uow: UowDep, response: Response
) -> AdminSessionDetail:
    session, device, gateway = await _session_binding(uow, public_id)
    captures = (
        await uow.session.scalars(
            select(Capture).where(Capture.session_id == session.id).order_by(Capture.created_at)
        )
    ).all()
    frames = (
        await uow.session.scalars(
            select(Frame).where(Frame.session_id == session.id).order_by(Frame.created_at)
        )
    ).all()
    answer_rows = (
        await uow.session.execute(
            select(Question, FinalAnswer)
            .outerjoin(FinalAnswer, FinalAnswer.question_id == Question.id)
            .where(Question.session_id == session.id)
            .order_by(Question.question_number)
        )
    ).all()
    delivery = await uow.session.scalar(
        select(SessionResultDelivery).where(SessionResultDelivery.session_id == session.id)
    )
    sequence = None
    if delivery is not None and delivery.active_sequence_id is not None:
        sequence = await uow.session.get(RgbSequence, delivery.active_sequence_id)
    logs = (
        await uow.session.scalars(
            select(AuditEvent)
            .where(AuditEvent.session_id == session.id)
            .order_by(AuditEvent.created_at.desc())
            .limit(500)
        )
    ).all()
    response.headers["Cache-Control"] = "no-store"
    return AdminSessionDetail(
        public_id=session.public_id,
        session_type=session.session_type,
        status=session.status,
        created_at=session.created_at,
        updated_at=session.updated_at,
        expected_pages=session.expected_pages,
        expected_questions=session.expected_questions,
        minimum_ratio=float(session.minimum_ratio),
        capture_source=session.capture_source,
        settings_version=int((session.config_snapshot or {}).get("settings_version", 0)),
        device_code=device.device_code,
        gateway_code=gateway.gateway_code,
        captures=[
            AdminCaptureItem(
                id=str(item.id),
                capture_id=item.capture_id,
                status=item.status,
                expected_frames=item.requested_frames,
                received_frames=item.received_frames,
                created_at=item.created_at,
            )
            for item in captures
        ],
        frames=[
            AdminFrameItem(
                frame_id=str(item.id),
                capture_id=str(item.capture_id),
                frame_index=item.frame_index,
                storage_key=item.storage_key,
                sha256=item.sha256,
                width=item.width,
                height=item.height,
                orientation=item.android_orientation,
                resolution=item.source_resolution,
                created_at=item.created_at,
            )
            for item in frames
        ],
        answers=[
            AdminAnswerItem(
                question_number=question.question_number,
                status=question.status,
                answer=final.answer if final else None,
                validated=bool(final and final.validated),
                color={
                    "letter": final.answer,
                    "rgb": rgb_for_answer(
                        session.config_snapshot, session.session_type, final.answer
                    ),
                }
                if final and final.answer in set("ABCDE")
                else None,
            )
            for question, final in answer_rows
        ],
        rgb_sequence=AdminRgbSequenceItem(
            sequence_id=sequence.sequence_id,
            revision=sequence.revision,
            status=sequence.status,
            answers=sequence.answers,
            item_count=sequence.item_count,
            defaults=sequence.defaults,
            palette=sequence.palette,
            sha256=sequence.payload_sha256,
            payload_size=sequence.payload_size,
        )
        if sequence
        else None,
        delivery={
            "command": delivery.command,
            "cursor": delivery.cursor,
            "reason_code": delivery.reason_code,
        }
        if delivery
        else None,
        logs=[
            AdminAuditItem(
                event_type=item.event_type,
                stage=item.stage,
                severity=item.severity,
                reason_code=item.reason_code,
                actor_type=item.actor_type,
                payload=item.payload,
                created_at=item.created_at,
            )
            for item in logs
        ],
    )


@router.get("/{public_id}/frames/{frame_id}/url", response_model=SignedFrameUrlResponse)
async def frame_url(
    public_id: str,
    frame_id: uuid.UUID,
    _claims: AdminClaimsDep,
    uow: UowDep,
    settings: SettingsDep,
    response: Response,
) -> SignedFrameUrlResponse:
    frame = await uow.session.scalar(
        select(Frame)
        .join(Session, Frame.session_id == Session.id)
        .where(Session.public_id == public_id, Frame.id == frame_id)
    )
    if frame is None:
        raise HTTPException(status_code=404, detail="Frame not found")
    storage = get_storage_adapter()
    url = await storage.create_signed_url(settings.R2_BUCKET_ORIGINALS, frame.storage_key, 300)
    response.headers["Cache-Control"] = "no-store"
    return SignedFrameUrlResponse(url=url)


@router.post("/{public_id}/cancel", response_model=AdminActionResponse)
async def cancel_session(
    public_id: str,
    body: AdminActionRequest,
    _claims: AdminCsrfDep,
    uow: UowDep,
) -> AdminActionResponse:
    session, device, gateway = await _session_binding(uow, public_id, lock=True)
    state = SessionState(session.status)
    if state == SessionState.CANCELLED:
        return AdminActionResponse(session_id=public_id, status=session.status, idempotent=True)
    if state.is_terminal or SessionState.CANCELLED not in ALLOWED_TRANSITIONS[state]:
        raise HTTPException(status_code=409, detail="Session cannot be cancelled in this state")
    session = await transition_session(
        uow,
        session,
        SessionState.CANCELLED,
        reason=None,
        actor=ActorType.ADMIN,
        payload={"admin_reason": body.reason},
    )
    await get_or_create_delivery(
        uow.session,
        SessionBinding(session=session, device=device, gateway=gateway),
        command=RgbResultCommand.RESULT_CANCELLED,
        reason_code="ADMIN_CANCELLED",
    )
    await uow.session.flush()
    return AdminActionResponse(session_id=public_id, status=session.status)


@router.post("/{public_id}/retry", response_model=AdminActionResponse, status_code=202)
async def retry_session(
    public_id: str,
    body: AdminActionRequest,
    _claims: AdminCsrfDep,
    uow: UowDep,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
) -> AdminActionResponse:
    session, _device, _gateway = await _session_binding(uow, public_id, lock=True)
    operation_suffix = hashlib.sha256(idempotency_key.encode()).hexdigest()[:12]
    operation_id = f"process-exam-{public_id}-retry-{operation_suffix}"
    duplicate = await uow.session.scalar(
        select(AuditEvent).where(
            AuditEvent.session_id == session.id,
            AuditEvent.event_type == "ADMIN_SESSION_RETRY",
            AuditEvent.payload["idempotency_key"].astext == idempotency_key,
        )
    )
    if duplicate is not None:
        return AdminActionResponse(
            session_id=public_id,
            status=session.status,
            operation_id=operation_id,
            idempotent=True,
        )
    state = SessionState(session.status)
    if state != SessionState.FAILED_RECOVERABLE:
        raise HTTPException(status_code=409, detail="Only recoverable failures can be retried")
    target_name = (body.from_stage or "IMAGE_PROCESSING").upper()
    allowed_targets = ALLOWED_TRANSITIONS[state]
    try:
        target = SessionState(target_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid retry stage") from exc
    if target not in allowed_targets:
        raise HTTPException(status_code=409, detail="Retry stage is not allowed")
    session = await transition_session(
        uow,
        session,
        target,
        reason=None,
        actor=ActorType.ADMIN,
        payload={"admin_reason": body.reason, "idempotency_key": idempotency_key},
    )
    uow.session.add(
        AuditEvent(
            session_id=session.id,
            event_type="ADMIN_SESSION_RETRY",
            stage="system",
            severity="info",
            actor_type="admin",
            payload={
                "reason": body.reason,
                "from_stage": target.value,
                "idempotency_key": idempotency_key,
            },
        )
    )
    await uow.session.flush()
    from src.pages_to_audio.workflows.starter import TemporalWorkflowStarter

    await TemporalWorkflowStarter().start_process_exam(
        public_id, operation_suffix=operation_suffix
    )
    return AdminActionResponse(
        session_id=public_id,
        status=session.status,
        operation_id=operation_id,
    )
