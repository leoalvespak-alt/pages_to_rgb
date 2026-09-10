"""Gateway endpoints — §13.4 / Phase 2 + Android-Only Etapa 1."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from apps.api.dependencies import SettingsDep, UowDep
from src.pages_to_audio.admin.settings_service import get_effective_admin_settings, rgb_for_answer
from src.pages_to_audio.auth.gateway import verify_gateway_token
from src.pages_to_audio.camera_profiles.contract import normalize_camera_mode
from src.pages_to_audio.camera_profiles.service import (
    CameraProfileError,
    ensure_default_profile,
    profile_payload,
    require_v2_enabled,
)
from src.pages_to_audio.capture.policy import CapturePolicy, build_capture_policy
from src.pages_to_audio.common.contract_ids import (
    ESP_ID_PATTERN,
    MAX_EXACT_CURSOR,
)
from src.pages_to_audio.common.errors import AppError, FrameConflictError, InvalidStateTransition
from src.pages_to_audio.common.ids import new_public_id
from src.pages_to_audio.db.models.capture import Capture
from src.pages_to_audio.db.models.device import Device
from src.pages_to_audio.db.models.gateway import AndroidGateway
from src.pages_to_audio.db.models.rgb_test_command import RgbTestCommand
from src.pages_to_audio.db.models.session import Session
from src.pages_to_audio.domain.enums.roles import ActorType
from src.pages_to_audio.domain.enums.session_state import SessionState
from src.pages_to_audio.domain.state_machine import transition_session
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)


async def _result_cursor_for(uow: UowDep, session: Session) -> int:
    """Cursor de resultado autoritativo (contrato §3.7); 0 sem delivery."""
    from src.pages_to_audio.db.models.session_result_delivery import SessionResultDelivery

    delivery = await uow.session.scalar(
        select(SessionResultDelivery).where(SessionResultDelivery.session_id == session.id)
    )
    return int(delivery.cursor) if delivery is not None else 0


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


class RgbTestCommandResponse(BaseModel):
    command_id: int
    rgb: tuple[int, int, int]
    brightness_percent: int
    on_ms: int
    off_ms: int


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
    expected_pages: int | None = Field(default=None, ge=1, le=100)
    expected_questions: int | None = Field(default=None, ge=1, le=1000)
    minimum_ratio: float | None = Field(default=None, gt=0, le=1)
    gateway_code: str = Field(default="", max_length=128)
    device_code: str = Field(default="CAM-001", min_length=1, max_length=63, pattern=ESP_ID_PATTERN)
    capture_source: str = Field(default="ANDROID_CAMERA", pattern="^(ANDROID_CAMERA|ESP32_CAMERA)$")
    allow_new_session: bool = True
    resume_hint: str | None = Field(default=None, max_length=63, pattern=ESP_ID_PATTERN)
    # Tradução contrato §3.7 (local start): resume_hint booleano + last_session_id.
    resume_requested: bool = False
    last_session_id: str | None = Field(default=None, max_length=63, pattern=ESP_ID_PATTERN)
    camera_mode: str = Field(default="OCR", min_length=1, max_length=16)
    camera_capabilities_version: str | None = Field(default=None, pattern=r"^v[0-9]+$")


class SessionStartResponse(BaseModel):
    session_id: str
    status: str
    expected_pages: int
    expected_questions: int
    minimum_ratio: float
    resumed: bool = False
    cursor: int = Field(default=0, ge=0, le=MAX_EXACT_CURSOR)
    camera_profile_revision_id: str | None = None
    camera_profile_snapshot: dict[str, Any] | None = None
    requested_camera_config: dict[str, Any] | None = None
    effective_camera_config: dict[str, Any] | None = None
    firmware_version: str | None = None
    capabilities_version: str | None = None


def _camera_response_fields(session: Session) -> dict[str, Any]:
    return {
        "camera_profile_revision_id": (
            str(session.camera_profile_revision_id)
            if session.camera_profile_revision_id is not None
            else None
        ),
        "camera_profile_snapshot": session.camera_profile_snapshot_json,
        "requested_camera_config": session.requested_camera_config_json,
        "effective_camera_config": session.effective_camera_config_json,
        "firmware_version": session.firmware_version,
        "capabilities_version": session.capabilities_version,
    }


@router.post("/session/start", response_model=SessionStartResponse)
async def session_start(
    body: SessionStartRequest,
    gateway_id: GatewayIdDep,
    settings: SettingsDep,
    uow: UowDep,
) -> SessionStartResponse:
    """Create or resume a capture session (idempotent)."""
    try:
        camera_mode = normalize_camera_mode(body.camera_mode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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

    # Handle allow_new_session=false → only resume existing CAPTURING session.
    # Contrato §3.7-3.8: hint exato nunca cai silenciosamente em outra sessão;
    # sessão encerrada retorna 409 com resolução explícita.
    # Tradução local→cloud: resume_requested+last_session_id equivalem a resume_hint.
    effective_hint = body.resume_hint or (body.last_session_id if body.resume_requested else None)
    if not body.allow_new_session:
        resume_session: Session | None = None
        if effective_hint:
            hint_session = await uow.session.scalar(
                select(Session)
                .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
                .where(
                    Session.public_id == effective_hint,
                    AndroidGateway.gateway_code == gateway_id,
                    Session.device_id == device.id,
                )
            )
            if hint_session is None:
                raise HTTPException(
                    status_code=409,
                    detail="Resume hint does not match an exact gateway/device session",
                )
            if SessionState(hint_session.status) != SessionState.CAPTURING:
                raise HTTPException(
                    status_code=409,
                    detail=f"Hinted session is {hint_session.status}; no silent fallback",
                )
            resume_session = hint_session
            gateway.last_seen_at = datetime.now(UTC)
            device.last_seen_at = datetime.now(UTC)
            return SessionStartResponse(
                session_id=resume_session.public_id,
                status=resume_session.status,
                expected_pages=resume_session.expected_pages,
                expected_questions=resume_session.expected_questions,
                minimum_ratio=float(resume_session.minimum_ratio),
                resumed=True,
                cursor=await _result_cursor_for(uow, resume_session),
                **_camera_response_fields(resume_session),
            )
        # Sem hint: retoma a CAPTURING mais recente do mesmo vínculo (autoritativo).
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
                resumed=True,
                cursor=await _result_cursor_for(uow, resume_session),
                **_camera_response_fields(resume_session),
            )
        raise HTTPException(
            status_code=409,
            detail="No resumable session and allow_new_session=false",
        )

    # allow_new_session=true com hint explícito: retoma se CAPTURING, senão 409
    # explícito quando hint aponta sessão encerrada/inexistente (sem criar outra
    # sessão silenciosamente no lugar da indicada).
    if effective_hint:
        hinted = await uow.session.scalar(
            select(Session)
            .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
            .where(
                Session.public_id == effective_hint,
                AndroidGateway.gateway_code == gateway_id,
                Session.device_id == device.id,
            )
        )
        if hinted is not None:
            if SessionState(hinted.status) == SessionState.CAPTURING:
                gateway.last_seen_at = datetime.now(UTC)
                device.last_seen_at = datetime.now(UTC)
                return SessionStartResponse(
                    session_id=hinted.public_id,
                    status=hinted.status,
                    expected_pages=hinted.expected_pages,
                    expected_questions=hinted.expected_questions,
                    minimum_ratio=float(hinted.minimum_ratio),
                    resumed=True,
                    cursor=await _result_cursor_for(uow, hinted),
                    **_camera_response_fields(hinted),
                )
            raise HTTPException(
                status_code=409,
                detail=f"Hinted session is {hinted.status}; not resumable",
            )

    camera_profile = None
    if settings.CAMERA_CONTRACT_V2_ENABLED:
        try:
            require_v2_enabled(
                settings,
                device,
                advertised_version=body.camera_capabilities_version,
            )
            camera_profile = await ensure_default_profile(
                uow.session,
                mode=camera_mode,
                actor=gateway_id,
                settings=settings,
            )
        except CameraProfileError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={"reason_code": exc.reason_code, "message": str(exc)},
            ) from exc

    session_id = new_public_id()
    now = datetime.now(UTC)
    # S07/contrato §2: novas sessões recebem explicitamente o perfil low-power
    # (12%/150ms/2850ms). Revisões antigas e seus hashes permanecem imutáveis.
    camera_values = profile_payload(camera_profile) if camera_profile is not None else None
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
            "rgb_profile": "low-power",
            "brightness_percent": 12,
            "on_ms": 150,
            "off_ms": 2850,
        },
        provider_snapshot={
            "settings_version": admin_settings.version,
            "ocr_provider": admin_settings.ocr_provider,
            "solve_model": admin_settings.solve_model,
            "verify_model": admin_settings.verify_model,
            "arbiter_model": admin_settings.arbiter_model,
        },
        camera_profile_revision_id=camera_profile.id if camera_profile is not None else None,
        camera_profile_snapshot_json=(
            {
                "mode": camera_profile.mode,
                "revision": camera_profile.revision,
                "public_id": str(camera_profile.public_id),
                "capabilities_version": camera_profile.capabilities_version,
                "config": camera_values,
            }
            if camera_profile is not None
            else None
        ),
        requested_camera_config_json=camera_values,
        effective_camera_config_json=camera_values,
        firmware_version=device.firmware_version if camera_profile is not None else None,
        capabilities_version=(
            camera_profile.capabilities_version if camera_profile is not None else None
        ),
    )
    uow.session.add(session)
    await uow.session.flush()
    if camera_profile is not None:
        from src.pages_to_audio.db.models.audit_event import AuditEvent

        uow.session.add(
            AuditEvent(
                session_id=session.id,
                event_type="CAMERA_PROFILE_SNAPSHOT_CREATED",
                stage="CAPTURE",
                severity="INFO",
                reason_code=None,
                actor_type="gateway",
                payload={
                    "mode": camera_profile.mode,
                    "revision": camera_profile.revision,
                    "profile_public_id": str(camera_profile.public_id),
                    "requested": camera_values,
                    "effective": camera_values,
                },
            )
        )
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
        resumed=False,
        cursor=0,
        **_camera_response_fields(session),
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
        telemetry = {
            key: payload[key]
            for key in ("state", "rssi", "firmware", "camera_profile")
            if isinstance(payload, dict) and key in payload
        }
        if telemetry:
            metadata = dict(device.metadata_ or {})
            metadata["telemetry"] = telemetry
            device.metadata_ = metadata
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

    Contrato §3.9: comando desconhecido ou campo obrigatório inválido nunca consome
    cursor — por isso `command` é Literal fechado (422 em valor desconhecido).
    """

    command: Literal["CAPTURE_PROBE", "CAPTURE_FULL", "PAUSE", "RESUME", "PING", "STOP"]
    cursor: int = Field(ge=0, le=MAX_EXACT_CURSOR)
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
    cursor: int = Query(default=0, ge=0, le=MAX_EXACT_CURSOR),
    wait_ms: int = Query(default=0, ge=0, le=25000),
    phase: str | None = Query(default=None),
) -> GatewayCommandResponse:
    """S02.8: comandos persistentes, GET sem efeito colateral, long-poll limitado.

    Cursor monotônico persistido em gateway_commands; repetição do mesmo cursor
    retorna o mesmo comando. wait_ms (teto 25s) aguarda de forma cooperativa por
    comando de controle; nunca alterna PAUSE/PROBE/PING por contador demo.
    Para PING/STOP/PAUSE/RESUME apenas command/cursor/session_id; CAPTURE_*
    inclui capture_id/frames/gap_ms.
    """
    from src.pages_to_audio.capture.commands import next_persistent_command

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

    try:
        row = await next_persistent_command(
            uow.session, session, client_cursor=cursor, phase=phase, wait_ms=wait_ms
        )
        await uow.session.flush()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    payload = row.payload or {}
    return GatewayCommandResponse(
        command=row.command,  # type: ignore[arg-type]
        cursor=int(row.cursor),
        session_id=session_id,
        capture_id=payload.get("capture_id"),
        frames=payload.get("frames"),
        gap_ms=payload.get("gap_ms"),
        frame_size=payload.get("frame_size"),
        jpeg_quality=payload.get("jpeg_quality"),
    )


class CommandAckRequest(BaseModel):
    cursor: int = Field(ge=0, le=MAX_EXACT_CURSOR)


@router.post("/session/{session_id}/command/ack")
async def ack_command_endpoint(
    session_id: str,
    body: CommandAckRequest,
    gateway_id: GatewayIdDep,
    uow: UowDep,
) -> dict[str, Any]:
    """S02.8/contrato §5.7: confirma efeito durável; repetir GET não altera estado."""
    from src.pages_to_audio.capture.commands import ack_command

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
    row = await ack_command(uow.session, session, cursor=body.cursor)
    await uow.session.flush()
    if row is None:
        raise HTTPException(status_code=404, detail="Command not found for cursor")
    return {"session_id": session_id, "cursor": int(row.cursor), "acked": True}


@router.post("/session/{session_id}/end-signal")
async def end_signal(
    session_id: str,
    gateway_id: GatewayIdDep,
    uow: UowDep,
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

    # S02.9/A04: congela intenção de processamento na MESMA transação do LOCK
    # (outbox). Dispatcher envia após commit com ID determinístico; falha do
    # Temporal deixa evento PENDING observável (nunca "locked:true" sem intent).
    try:
        from src.pages_to_audio.capture.dispatcher import enqueue_workflow_intent

        await enqueue_workflow_intent(
            uow.session, session_db_id=session.id, session_public_id=session.public_id
        )
        await uow.session.flush()
    except Exception as exc:
        logger.warning("workflow_outbox_enqueue_failed", error=str(exc), session_id=session_id)
        raise HTTPException(status_code=500, detail="Failed to persist processing intent") from exc

    # Tentativa best-effort de despacho imediato (após intent durável).
    try:
        # The post-commit worker owns dispatch; this request never dispatches
        # against its still-open transaction.
        pass
    except Exception as exc:
        # Intent permanece PENDING para retry observável pelo dispatcher.
        logger.warning("workflow_dispatch_failed_pending", error=str(exc), session_id=session_id)

    logger.info("end_signal", session_id=session_id, status=session.status)
    return {"session_id": session_id, "status": session.status, "locked": True}


@router.get("/session/{session_id}/rgb-test", response_model=RgbTestCommandResponse | None)
async def get_rgb_test_command(
    session_id: str,
    gateway_id: GatewayIdDep,
    uow: UowDep,
    after_id: int = Query(default=0, ge=0),
) -> RgbTestCommandResponse | None:
    session = await uow.session.scalar(
        select(Session)
        .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
        .where(Session.public_id == session_id, AndroidGateway.gateway_code == gateway_id)
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    command = await uow.session.scalar(
        select(RgbTestCommand)
        .where(
            RgbTestCommand.session_id == session.id,
            RgbTestCommand.id > after_id,
            RgbTestCommand.delivered_at.is_(None),
        )
        .order_by(RgbTestCommand.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if command is None:
        return None
    if not isinstance(command.rgb, list) or len(command.rgb) != 3:
        raise HTTPException(status_code=500, detail="Invalid RGB test command")
    command.delivered_at = datetime.now(UTC)
    return RgbTestCommandResponse(
        command_id=command.id,
        rgb=(int(command.rgb[0]), int(command.rgb[1]), int(command.rgb[2])),
        brightness_percent=command.brightness_percent,
        on_ms=command.on_ms,
        off_ms=command.off_ms,
    )


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
    capture_id: str = Field(min_length=1, max_length=63, pattern=ESP_ID_PATTERN)
    mode: str = "full"
    command_cursor: int = Field(default=0, ge=0, le=MAX_EXACT_CURSOR)
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


async def _read_frame_body_limited(
    file: UploadFile, *, limit_bytes: int = 12 * 1024 * 1024
) -> bytes:
    """Lê corpo em chunks aplicando limite antes de carga integral (S01.5/A19)."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit_bytes:
            raise HTTPException(status_code=413, detail="Frame body exceeds size limit")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/session/{session_id}/frame")
async def upload_frame_gateway(
    session_id: str,
    file: UploadFile,
    gateway_id: GatewayIdDep,
    uow: UowDep,
    _settings: SettingsDep,
    x_frame_index: int = Header(..., alias="X-Frame-Index", ge=0, le=10000),
    x_capture_id: str = Header(
        ..., alias="X-Capture-Id", min_length=1, max_length=63, pattern=ESP_ID_PATTERN
    ),
    x_sha256: str = Header(
        ..., alias="X-SHA256", min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$"
    ),
    x_received_at: str | None = Header(None, alias="X-Received-Android-At"),
    x_resolution: str | None = Header(None, alias="X-Resolution"),
    x_orientation: int | None = Header(None, alias="X-Orientation"),
    x_page_number: int | None = Header(None, alias="X-Page-Number", ge=0),
    x_frame_number: int | None = Header(None, alias="X-Frame-Number", ge=0),
) -> dict[str, Any]:
    """Receive a JPEG frame from the Android gateway."""
    # Limite de corpo aplicado antes de carregar integralmente (S01.5): FastAPI já
    # bufferiza, mas rejeitamos Content-Length declarado > 12MB antes de ler.
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

    data = await _read_frame_body_limited(file)

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
        page_number=x_page_number,
        frame_number=x_frame_number,
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
        "derived_storage_key": result.derived_storage_key,
        "duplicate": result.duplicate,
    }


@router.post("/session/{session_id}/capture-complete")
async def capture_complete(
    session_id: str,
    gateway_id: GatewayIdDep,
    uow: UowDep,
    capture_id: str = Query(..., min_length=1, max_length=63, pattern=ESP_ID_PATTERN),
    received_frames: int = Query(..., ge=0, le=10000),
) -> dict[str, Any]:
    """Fecha burst. S02.6/A12: contagem autoritativa = frames únicos no banco.

    O número declarado pelo cliente é registrado como `declared_frames` para
    auditoria, mas nunca sobrescreve a contagem. Divergência gera evento de
    atenção sem inflar contagem.
    """
    from sqlalchemy import func

    from src.pages_to_audio.db.models.frame import Frame

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
    confirmed = (
        await uow.session.scalar(
            select(func.count()).select_from(Frame).where(Frame.capture_id == cap.id)
        )
        or 0
    )
    cap.received_frames = int(confirmed)
    cap.status = "complete"
    cap.completed_at = datetime.now(UTC)
    await uow.session.flush()
    if int(received_frames) != int(confirmed):
        logger.warning(
            "capture_complete_count_mismatch",
            session_id=session_id,
            capture_id=capture_id,
            declared=int(received_frames),
            confirmed=int(confirmed),
        )
    logger.info(
        "capture_complete",
        session_id=session_id,
        capture_id=capture_id,
        received=int(confirmed),
    )
    return {
        "session_id": session_id,
        "capture_id": capture_id,
        "received_frames": cap.received_frames,
        "declared_frames": int(received_frames),
        "status": cap.status,
    }
