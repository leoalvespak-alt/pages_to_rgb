"""Gateway endpoints — §13.4 / Phase 2 + Android-Only Etapa 1."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from apps.api.dependencies import SettingsDep, UowDep
from src.pages_to_audio.admin.settings_service import get_effective_admin_settings, rgb_for_answer
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
    prefix="/gateway",
    tags=["gateway"],
    dependencies=[Depends(verify_gateway_token)],
)

GatewayIdDep = Annotated[str, Depends(verify_gateway_token)]

# In-memory command cursors per session — Etapa 5 simplificado (long polling stub).
# TODO(ETAPA5-INMEM): Cursor volátil (dict global por processo); restart/worker múltiplo perde
# estado. Para produção usar tabela persistente (ex: SessionResultDelivery.cursor ou
# gateway_command_state com SELECT ... FOR UPDATE + sleep cooperativo até wait_ms).
# Limitação documentada e aceita para E2E Android-Only sem ESP32. wait_ms até 25000 é
# validado mas não bloqueia nesta versão stub (retorno imediato).
_command_cursors: dict[str, int] = {}


class HelloRequest(BaseModel):
    app_version: str = ""
    device_model: str = ""
    gateway_code: str = Field(min_length=1, max_length=128)


class HelloResponse(BaseModel):
    server_version: str
    contract_version: str
    capabilities: list[str]


@router.post("/hello", response_model=HelloResponse)
async def hello(body: HelloRequest, gateway_id: GatewayIdDep, uow: UowDep) -> HelloResponse:
    """Register/update gateway last_seen and return server capabilities."""
    gateway = await uow.session.scalar(
        select(AndroidGateway).where(AndroidGateway.gateway_code == gateway_id).with_for_update()
    )
    if gateway is None:
        gateway = AndroidGateway(
            gateway_code=gateway_id,
            app_version=body.app_version,
            device_model=body.device_model,
            last_seen_at=datetime.now(UTC),
            metadata_={
                "hello_gateway_code": body.gateway_code,
                "capture_source": "ANDROID_CAMERA",
            },
        )
        uow.session.add(gateway)
    else:
        gateway.app_version = body.app_version
        gateway.device_model = body.device_model
        gateway.last_seen_at = datetime.now(UTC)
        gateway.metadata_ = {
            "hello_gateway_code": body.gateway_code,
            "capture_source": "ANDROID_CAMERA",
        }
    logger.info("gateway_hello", gateway_id=gateway_id, app_version=body.app_version)
    return HelloResponse(
        server_version="0.2.0-rgb-results",
        contract_version="2.2",
        capabilities=[
            "frame_upload",
            "session_start",
            "probe_analysis",
            "result_poll",
            "rgb_sequence_schema_1",
            "rgb_sequence_events",
            "capture_policy",
            "gateway_command",
        ],
    )


class SessionStartRequest(BaseModel):
    expected_pages: int | None = None
    expected_questions: int | None = None
    minimum_ratio: float | None = None
    gateway_code: str = Field(default="", max_length=128)
    device_code: str = Field(default="CAM-001", min_length=1, max_length=128)
    capture_source: str = Field(default="ANDROID_CAMERA", pattern="^(ANDROID_CAMERA|ESP32_CAMERA)$")
    allow_new_session: bool = True
    resume_hint: str | None = Field(default=None, max_length=128)


class SessionStartResponse(BaseModel):
    session_id: str
    status: str
    expected_pages: int
    expected_questions: int
    minimum_ratio: float


@router.post("/session/start", response_model=SessionStartResponse)
async def session_start(
    body: SessionStartRequest,
    gateway_id: GatewayIdDep,
    settings: SettingsDep,
    uow: UowDep,
) -> SessionStartResponse:
    """Create or resume a capture session (idempotent)."""
    gateway = await uow.session.scalar(
        select(AndroidGateway).where(AndroidGateway.gateway_code == gateway_id).with_for_update()
    )
    if gateway is None:
        gateway = AndroidGateway(
            gateway_code=gateway_id,
            last_seen_at=datetime.now(UTC),
            metadata_={"session_start": True},
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
            capture_source=body.capture_source,
        )
        uow.session.add(device)
        await uow.session.flush()
    else:
        # Update capture_source and last_seen
        device.capture_source = body.capture_source
        device.last_seen_at = datetime.now(UTC)
    if not device.enabled:
        raise HTTPException(status_code=403, detail="Device is disabled")

    gateway.last_seen_at = datetime.now(UTC)
    device.last_seen_at = datetime.now(UTC)

    admin_settings = await get_effective_admin_settings(uow.session)
    ep = body.expected_pages if body.expected_pages is not None else admin_settings.expected_pages
    eq = (
        body.expected_questions
        if body.expected_questions is not None
        else admin_settings.expected_questions
    )
    mr = body.minimum_ratio if body.minimum_ratio is not None else admin_settings.minimum_ratio

    # Handle allow_new_session=false → only resume existing CAPTURING session
    if not body.allow_new_session:
        resume_session: Session | None = None
        if body.resume_hint:
            resume_session = await uow.session.scalar(
                select(Session)
                .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
                .where(
                    Session.public_id == body.resume_hint,
                    AndroidGateway.gateway_code == gateway_id,
                    Session.device_id == device.id,
                )
            )
            is_capturing = (
                resume_session is not None
                and SessionState(resume_session.status) == SessionState.CAPTURING
            )
            if is_capturing:
                gateway.last_seen_at = datetime.now(UTC)
                device.last_seen_at = datetime.now(UTC)
                return SessionStartResponse(
                    session_id=resume_session.public_id,
                    status=resume_session.status,
                    expected_pages=resume_session.expected_pages,
                    expected_questions=resume_session.expected_questions,
                    minimum_ratio=float(resume_session.minimum_ratio),
                )
        # Try latest CAPTURING without hint
        resume_session = await uow.session.scalar(
            select(Session)
            .where(
                Session.device_id == device.id,
                Session.gateway_id == gateway.id,
                Session.status == SessionState.CAPTURING.value,
            )
            .order_by(Session.created_at.desc())
        )
        if resume_session is not None:
            gateway.last_seen_at = datetime.now(UTC)
            device.last_seen_at = datetime.now(UTC)
            return SessionStartResponse(
                session_id=resume_session.public_id,
                status=resume_session.status,
                expected_pages=resume_session.expected_pages,
                expected_questions=resume_session.expected_questions,
                minimum_ratio=float(resume_session.minimum_ratio),
            )
        raise HTTPException(
            status_code=409,
            detail="No resumable session and allow_new_session=false",
        )

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
        capture_source=body.capture_source,
        session_type="EXAM",
        config_snapshot={
            **admin_settings.snapshot("EXAM"),
            "expected_pages": ep,
            "expected_questions": eq,
            "minimum_ratio": mr,
        },
        provider_snapshot={
            "settings_version": admin_settings.version,
            "ocr_provider": admin_settings.ocr_provider,
            "solve_model": admin_settings.solve_model,
            "verify_model": admin_settings.verify_model,
            "arbiter_model": admin_settings.arbiter_model,
        },
    )
    uow.session.add(session)
    await uow.session.flush()
    logger.info(
        "session_start",
        session_id=session_id,
        gateway_id=gateway_id,
        capture_source=body.capture_source,
    )

    return SessionStartResponse(
        session_id=session_id,
        status=SessionState.CAPTURING.value,
        expected_pages=ep,
        expected_questions=eq,
        minimum_ratio=mr,
    )


@router.post("/session/{session_id}/heartbeat")
async def heartbeat(
    session_id: str,
    gateway_id: GatewayIdDep,
    uow: UowDep,
    payload: dict[str, Any] | None = Body(default=None),
) -> dict[str, Any]:
    session = await uow.session.scalar(
        select(Session)
        .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
        .where(
            Session.public_id == session_id,
            AndroidGateway.gateway_code == gateway_id,
        )
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


@router.get("/session/{session_id}/policy", response_model=CapturePolicy)
async def get_policy(session_id: str, gateway_id: GatewayIdDep, uow: UowDep) -> CapturePolicy:
    session = await uow.session.scalar(
        select(Session)
        .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
        .where(
            Session.public_id == session_id,
            AndroidGateway.gateway_code == gateway_id,
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    # Also ensure device enabled via session binding
    device = await uow.session.get(Device, session.device_id)
    if device is None or not device.enabled:
        raise HTTPException(status_code=403, detail="Device disabled")
    return build_capture_policy(expected_pages=session.expected_pages)


class GatewayCommandResponse(BaseModel):
    """Resposta de GET /command — compatível com ANDROID_GATEWAY_CONTRACT § GET /v1/device/command.

    Campos obrigatórios para CAPTURE_*: capture_id, frames, gap_ms. Para PING/STOP/PAUSE/RESUME
    apenas command/cursor/session_id. frame_size/jpeg_quality são opcionais (ex: UXGA/8
    para ESP32, 1280x720/75 para PROBE Android).
    """

    command: str  # CAPTURE_PROBE | CAPTURE_FULL | PAUSE | RESUME | PING | STOP
    cursor: int
    session_id: str
    capture_id: str | None = None
    frames: int | None = None
    gap_ms: int | None = None
    frame_size: str | None = None
    jpeg_quality: int | None = None


@router.get("/session/{session_id}/command", response_model=GatewayCommandResponse)
async def get_command(
    session_id: str,
    gateway_id: GatewayIdDep,
    uow: UowDep,
    cursor: int = Query(default=0, ge=0),
    wait_ms: int = Query(default=0, ge=0, le=25000),
    phase: str | None = Query(default=None),
) -> GatewayCommandResponse:
    """Long polling simplificado — cursor monotônico, wait_ms até 25000 (validado).

    Stub Etapa 5: retorna imediatamente (sem sleep cooperativo). wait_ms é aceito para
    compatibilidade com firmware/ Android ViewModel que envia waitMs=25000 e phase=CAPTURE.
    Cursor é in-memory (_command_cursors); ver TODO acima. Comandos possíveis:
    CAPTURE_PROBE, CAPTURE_FULL, PAUSE, RESUME, PING, STOP (cf. ANDROID_GATEWAY_CONTRACT).

    Para PING/STOP/PAUSE/RESUME apenas command/cursor/session_id; para CAPTURE_* inclui
    capture_id/frames/gap_ms (e opcional frame_size/jpeg_quality).
    Diferente de GET /result (que retorna 204 quando cursor >= delivery.cursor), este
    endpoint sempre retorna 200 com cursor+1 para manter compatibilidade com
    SessionViewModel/fetchCommand que espera CommandResponse não-nulo.
    """
    session = await uow.session.scalar(
        select(Session)
        .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
        .where(
            Session.public_id == session_id,
            AndroidGateway.gateway_code == gateway_id,
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    device = await uow.session.get(Device, session.device_id)
    if device is None or not device.enabled:
        raise HTTPException(status_code=403, detail="Device disabled")

    # Simple monotonic cursor: increment per call, persistent per session.
    # Respeita cursor do cliente (se cliente já avançou, não regride).
    last = _command_cursors.get(session_id, cursor)
    next_cursor = max(last + 1, cursor + 1)
    # If client is ahead, respect it
    if cursor >= last:
        next_cursor = cursor + 1
    _command_cursors[session_id] = next_cursor

    # Determine command based on session state + phase hint.
    try:
        state = SessionState(session.status)
    except ValueError:
        state = SessionState.CAPTURING

    if state in {SessionState.LOCKED, SessionState.CAPTURE_LOCKING}:
        return GatewayCommandResponse(command="STOP", cursor=next_cursor, session_id=session_id)
    if state.is_terminal:
        return GatewayCommandResponse(command="STOP", cursor=next_cursor, session_id=session_id)
    if state == SessionState.CAPTURING:
        # Phase explícita tem prioridade (permite servidor forçar PAUSE/RESUME/PROBE).
        norm_phase = (phase or "").strip().upper()
        if norm_phase == "PAUSE":
            return GatewayCommandResponse(
                command="PAUSE", cursor=next_cursor, session_id=session_id
            )
        if norm_phase == "RESUME":
            return GatewayCommandResponse(
                command="RESUME", cursor=next_cursor, session_id=session_id
            )
        if norm_phase == "PROBE":
            cid = f"cap-{next_cursor:03d}-probe"
            return GatewayCommandResponse(
                command="CAPTURE_PROBE",
                cursor=next_cursor,
                session_id=session_id,
                capture_id=cid,
                frames=1,
                gap_ms=180,
                frame_size="1280x720",
                jpeg_quality=75,
            )
        # Rotação determinística para demo/E2E sem policy dinâmica:
        # - a cada 5 → CAPTURE_PROBE (1 frame, 180ms, 72p quality 75)
        # - a cada 7 → PAUSE (raro, demonstra PAUSE/RESUME sem quebrar fluxo CAPTURE)
        # - a cada 4 → PING (heartbeat)
        # - senão → CAPTURE_FULL (3 frames, 180ms)
        if next_cursor % 7 == 0:
            return GatewayCommandResponse(
                command="PAUSE", cursor=next_cursor, session_id=session_id
            )
        if next_cursor % 7 == 1:
            # Imediatamente após PAUSE, envia RESUME para retomar preview
            return GatewayCommandResponse(
                command="RESUME", cursor=next_cursor, session_id=session_id
            )
        if next_cursor % 5 == 0:
            cid = f"cap-{next_cursor:03d}-probe"
            return GatewayCommandResponse(
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
            return GatewayCommandResponse(command="PING", cursor=next_cursor, session_id=session_id)
        cid = f"cap-{next_cursor:03d}-full"
        return GatewayCommandResponse(
            command="CAPTURE_FULL",
            cursor=next_cursor,
            session_id=session_id,
            capture_id=cid,
            frames=3,
            gap_ms=180,
            frame_size="UXGA",
            jpeg_quality=92,
        )
    # Para estados intermediários (ex: IMAGE_PROCESSING mas não terminal nem CAPTURING)
    return GatewayCommandResponse(command="PING", cursor=next_cursor, session_id=session_id)


@router.post("/session/{session_id}/end-signal")
async def end_signal(
    session_id: str,
    gateway_id: GatewayIdDep,
    uow: UowDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    session = await uow.session.scalar(
        select(Session)
        .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
        .where(
            Session.public_id == session_id,
            AndroidGateway.gateway_code == gateway_id,
        )
        .with_for_update()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
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
        # Idempotente: já LOCKED — garantir delivery PROCESSING/READY visível ao polling
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
                "mark_result_processing_idempotent_failed",
                error=str(exc),
                session_id=session_id,
            )
        return {"session_id": session_id, "status": session.status, "locked": True}

    # Walk through allowed transitions to LOCKED
    # CAPTURING -> CAPTURE_END_CANDIDATE -> CAPTURE_LOCKING -> LOCKED
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

    # ETAPA 6 — marcar RESULT_PROCESSING para que GET /result não fique em NOT_STARTED.
    # Não altera formato RGB (schema_version 1, canonical PACK="<BBBBBII").
    try:
        from src.pages_to_audio.rgb.delivery import SessionBinding, mark_result_processing

        gateway_row = await uow.session.scalar(
            select(AndroidGateway).where(AndroidGateway.gateway_code == gateway_id)
        )
        # device já validado; gateway_row deve existir (hello/start garante)
        if gateway_row is not None:
            binding = SessionBinding(session=session, device=device, gateway=gateway_row)
            await mark_result_processing(uow.session, binding)
            await uow.session.flush()
    except Exception as exc:
        logger.warning("mark_result_processing_failed", error=str(exc), session_id=session_id)

    # Tentativa best-effort de iniciar ProcessExamWorkflow via Temporal.
    # Se TEMPORAL_ADDRESS vazio ou Temporal offline, apenas loga; painel ainda
    # pode publicar RGB manualmente via simulate_android / admin publish.
    try:
        temporal_addr = getattr(settings, "TEMPORAL_ADDRESS", "")
        if temporal_addr:
            from src.pages_to_audio.workflows.starter import TemporalWorkflowStarter

            starter = TemporalWorkflowStarter()
            await starter.start_process_exam(session.public_id)
            logger.info("workflow_start_after_lock", session_id=session_id)
    except Exception as exc:
        logger.warning("workflow_start_after_lock_failed", error=str(exc), session_id=session_id)

    logger.info("end_signal", session_id=session_id, status=session.status)
    return {"session_id": session_id, "status": session.status, "locked": True}


@router.get("/session/{session_id}/summary")
async def session_summary(
    session_id: str,
    gateway_id: GatewayIdDep,
    uow: UowDep,
) -> dict[str, Any]:
    """Painel — resumo mínimo para Android-only Etapas 6 (sem ESP32).

    Retorna estado da captura, contagem de frames, e, quando existir,
    a lista de FinalAnswer por Question (A-E + cor da paleta RGB_RESULT_V1.md:31).
    Formato RGB imutável: schema_version 1, palette defaults, SHA canonical
    struct.pack("<BBBBBII"). Mesmo payload que firmware V2.2 lerá.
    """
    from sqlalchemy import func

    from src.pages_to_audio.db.models.final_answer import FinalAnswer
    from src.pages_to_audio.db.models.frame import Frame
    from src.pages_to_audio.db.models.question import Question
    from src.pages_to_audio.db.models.rgb_sequence import RgbSequence
    from src.pages_to_audio.db.models.session_result_delivery import SessionResultDelivery

    session = await uow.session.scalar(
        select(Session)
        .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
        .where(
            Session.public_id == session_id,
            AndroidGateway.gateway_code == gateway_id,
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    device = await uow.session.get(Device, session.device_id)
    gateway = await uow.session.scalar(
        select(AndroidGateway).where(AndroidGateway.gateway_code == gateway_id)
    )
    # Gate idempotente já validado acima; device/gateway podem ser None só se deletados
    if device is None or gateway is None:
        raise HTTPException(status_code=404, detail="Binding not found")

    frames_count = (
        await uow.session.scalar(
            select(func.count()).select_from(Frame).where(Frame.session_id == session.id)
        )
        or 0
    )
    # Questions + FinalAnswers ordenadas por question_number
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
            rgb = rgb_for_answer(session.config_snapshot, "EXAM", letter)
            color = {"rgb": rgb, "letter": letter}
        answers.append(
            {
                "question_number": question.question_number,
                "status": question.status,
                "answer": letter,
                "validated": bool(final is not None and final.validated),
                "color": color,
            }
        )
    # Delivery + sequência ativa (se houver)
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
        "expected_pages": session.expected_pages,
        "expected_questions": session.expected_questions,
        "minimum_ratio": float(session.minimum_ratio),
        "settings_version": (session.config_snapshot or {}).get("settings_version", 0),
        "rgb_defaults": {
            key: (session.config_snapshot or {}).get(key)
            for key in ("brightness_percent", "on_ms", "off_ms")
        },
        "capture_source": getattr(session, "capture_source", "ANDROID_CAMERA"),
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "capture_locked_at": (
            session.capture_locked_at.isoformat() if session.capture_locked_at else None
        ),
        "processing_started_at": (
            session.processing_started_at.isoformat()  # type: ignore[union-attr]
            if getattr(session, "processing_started_at", None)
            else None
        ),
        "device_code": device.device_code,
        "gateway_code": gateway.gateway_code,
        "frames_count": frames_count,
        "questions_count": len(rows),
        "answers": answers,
        "delivery": {
            "command": delivery.command if delivery else None,
            "cursor": delivery.cursor if delivery else None,
            "reason_code": delivery.reason_code if delivery else None,
            "active_sequence_id": (
                str(delivery.active_sequence_id)
                if delivery and delivery.active_sequence_id
                else None
            ),
        }
        if delivery
        else None,
        "rgb_sequence": rgb_sequence_info,
    }


@router.post("/session/{session_id}/debug/publish-rgb")
async def debug_publish_rgb(
    session_id: str,
    gateway_id: GatewayIdDep,
    uow: UowDep,
) -> dict[str, Any]:
    """Debug — publica RGB manualmente sem workflow (Android-Only).

    Útil quando Temporal offline: cria/reutiliza RgbSequence a partir de
    Question+FinalAnswer já validadas. Retorna RESULT_CANCELLED se conjunto
    incompleto (ver `src/pages_to_audio/rgb/policy.py:34`).
    Idempotente: mesmo answers → reused:true, não duplica revision.
    """
    from src.pages_to_audio.rgb.publisher import publish_rgb_for_session

    session = await uow.session.scalar(
        select(Session)
        .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
        .where(
            Session.public_id == session_id,
            AndroidGateway.gateway_code == gateway_id,
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    # publish_rgb_for_session já valida binding interno e faz flush
    result = await publish_rgb_for_session(uow.session, session_public_id=session_id)
    # Uow commit é feito pelo dependency finalizer; flush já garante visibilidade
    return {
        "session_id": session_id,
        "command": result.command.value,
        "sequence_id": result.sequence.sequence_id if result.sequence else None,
        "revision": result.sequence.revision if result.sequence else None,
        "sha256": result.sequence.payload_sha256 if result.sequence else None,
        "reason_code": result.reason_code,
        "reused": result.reused,
    }


class CaptureRequest(BaseModel):
    capture_id: str = Field(min_length=1, max_length=128)
    mode: str = "full"
    command_cursor: int = 0
    requested_frames: int = Field(default=3, ge=0, le=100)


@router.post("/session/{session_id}/capture")
async def create_capture(
    session_id: str,
    body: CaptureRequest,
    gateway_id: GatewayIdDep,
    uow: UowDep,
) -> dict[str, Any]:
    """Open a capture burst."""
    session = await uow.session.scalar(
        select(Session)
        .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
        .where(
            Session.public_id == session_id,
            AndroidGateway.gateway_code == gateway_id,
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    device = await uow.session.get(Device, session.device_id)
    if device is None or not device.enabled:
        raise HTTPException(status_code=403, detail="Device disabled")

    existing = await uow.session.scalar(
        select(Capture)
        .where(Capture.session_id == session.id, Capture.capture_id == body.capture_id)
        .with_for_update()
    )
    if existing is not None:
        existing.mode = body.mode
        existing.command_cursor = body.command_cursor
        existing.requested_frames = body.requested_frames
        await uow.session.flush()
        return {
            "session_id": session_id,
            "capture_id": body.capture_id,
            "status": existing.status,
            "requested_frames": existing.requested_frames,
            "received_frames": existing.received_frames,
        }

    cap = Capture(
        session_id=session.id,
        capture_id=body.capture_id,
        mode=body.mode,
        command_cursor=body.command_cursor,
        requested_frames=body.requested_frames,
        received_frames=0,
        status="open",
        capture_source=session.capture_source
        if hasattr(session, "capture_source")
        else "ANDROID_CAMERA",
        session_type=getattr(session, "session_type", "EXAM") or "EXAM",
    )
    uow.session.add(cap)
    await uow.session.flush()
    logger.info("capture_created", session_id=session_id, capture_id=body.capture_id)
    return {
        "session_id": session_id,
        "capture_id": body.capture_id,
        "status": "open",
        "requested_frames": cap.requested_frames,
        "received_frames": cap.received_frames,
    }


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
async def upload_frame_gateway(
    session_id: str,
    file: UploadFile,
    gateway_id: GatewayIdDep,
    uow: UowDep,
    _settings: SettingsDep,
    x_frame_index: int = Header(..., alias="X-Frame-Index"),
    x_capture_id: str = Header(..., alias="X-Capture-Id"),
    x_sha256: str = Header(..., alias="X-SHA256"),
    x_received_at: str | None = Header(None, alias="X-Received-Android-At"),
    x_resolution: str | None = Header(None, alias="X-Resolution"),
    x_orientation: int | None = Header(None, alias="X-Orientation"),
) -> dict[str, Any]:
    """Receive a JPEG frame from the Android gateway."""
    # Validate binding
    session = await uow.session.scalar(
        select(Session)
        .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
        .where(
            Session.public_id == session_id,
            AndroidGateway.gateway_code == gateway_id,
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    device = await uow.session.get(Device, session.device_id)
    if device is None or not device.enabled:
        raise HTTPException(status_code=403, detail="Device disabled")

    data = await file.read()

    from src.pages_to_audio.capture.frame_upload import FrameUploadRequest
    from src.pages_to_audio.capture.frame_upload import upload_frame as _upload

    width, height = _parse_resolution(x_resolution)

    from src.pages_to_audio.storage import get_storage_adapter

    storage = get_storage_adapter()

    req = FrameUploadRequest(
        session_id=session_id,
        capture_id=x_capture_id,
        frame_index=x_frame_index,
        declared_sha256=x_sha256,
        data=data,
        mime_type=file.content_type or "image/jpeg",
        received_android_at=x_received_at,
        capture_source=getattr(session, "capture_source", "ANDROID_CAMERA"),
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
async def capture_complete(
    session_id: str,
    gateway_id: GatewayIdDep,
    uow: UowDep,
    capture_id: str = Query(..., min_length=1, max_length=128),
    received_frames: int = Query(..., ge=0),
) -> dict[str, Any]:
    session = await uow.session.scalar(
        select(Session)
        .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
        .where(
            Session.public_id == session_id,
            AndroidGateway.gateway_code == gateway_id,
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
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
        "capture_complete",
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
