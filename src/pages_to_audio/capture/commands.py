"""S02.8/A13 — comandos gateway persistentes, GET sem efeito, long-poll limitado.

- GET nunca avança cursor nem alterna PAUSE/PROBE/PING por contador demo.
- Comando deriva do estado real da sessão; STOP/RESUME (controle) nunca ficam
  presos atrás de captura impedida pela pausa (seleção de controle prioritária).
- Cursor monotônico persistido em gateway_commands; repetição do mesmo cursor
  retorna o mesmo comando (idempotente). ACK confirma efeito durável.
- Long-poll: espera cooperativa até wait_ms (teto servidor 25s), sem sleep
  arbitrário de sincronização — polling de visibilidade, não de correção.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.pages_to_audio.common.contract_ids import MAX_EXACT_CURSOR
from src.pages_to_audio.db.models.gateway_command import GatewayCommand
from src.pages_to_audio.db.models.session import Session
from src.pages_to_audio.domain.enums.session_state import SessionState

CONTROL_COMMANDS = {"STOP", "RESUME", "PAUSE"}


def _desired_command(
    state: SessionState,
    *,
    phase: str | None,
    capture_source: str = "ANDROID_CAMERA",
    camera_config: dict | None = None,
) -> tuple[str, dict | None]:
    norm = (phase or "").strip().upper()
    if state in {SessionState.LOCKED, SessionState.CAPTURE_LOCKING} or state.is_terminal:
        return "STOP", None
    if state != SessionState.CAPTURING:
        return "PING", None
    # Controle explícito tem prioridade e nunca é bloqueado pela pausa.
    if norm in {"PAUSE", "RESUME", "STOP"}:
        return norm, None
    if capture_source == "ESP32_CAMERA":
        config = camera_config or {}
        if norm == "PROBE":
            return "CAPTURE_PROBE", {
                "frames": 1,
                "gap_ms": 0,
                "frame_size": "UXGA",
                "jpeg_quality": 10,
            }
        return "CAPTURE_FULL", {
            "frames": int(config.get("frame_count") or 2),
            "gap_ms": int(config.get("intra_frame_gap_ms") or 220),
            "frame_size": str(config.get("frame_size") or "UXGA"),
            "jpeg_quality": int(config.get("esp_jpeg_quality") or 10),
        }
    if norm == "PROBE":
        return "CAPTURE_PROBE", {
            "frames": 1,
            "gap_ms": 180,
            "frame_size": "1280x720",
            "jpeg_quality": 75,
        }
    return "CAPTURE_FULL", {"frames": 3, "gap_ms": 180, "frame_size": "UXGA", "jpeg_quality": 92}


async def next_persistent_command(
    db: AsyncSession,
    session: Session,
    *,
    client_cursor: int,
    phase: str | None,
    wait_ms: int = 0,
) -> GatewayCommand:
    """Retorna comando para cursor+1 (persistido) ou o já persistido (idempotente).

    Long-poll limitado: se o estado ainda não exige controle e wait_ms>0, aguarda
    de forma cooperativa até wait_ms antes de emitir CAPTURE_* (evita busy-poll).
    GET nunca consome: só cria a linha do próximo cursor.
    """
    if client_cursor < 0 or client_cursor > MAX_EXACT_CURSOR:
        raise ValueError("cursor fora do intervalo exato 0..2^53-1")
    state = SessionState(session.status)
    capture_source = getattr(session, "capture_source", "ANDROID_CAMERA")
    camera_config = getattr(session, "effective_camera_config_json", None)
    command, payload = _desired_command(
        state,
        phase=phase,
        capture_source=capture_source,
        camera_config=camera_config,
    )
    # Long-poll cooperativo apenas para comandos de captura (não controle).
    if wait_ms > 0 and command not in CONTROL_COMMANDS and command != "STOP":
        deadline = min(int(wait_ms), 25000) / 1000.0
        # Espera em fatias curtas; qualquer mudança de estado sai mais cedo.
        waited = 0.0
        step = 0.25
        while waited < deadline:
            await asyncio.sleep(step)
            waited += step
            await db.refresh(session)
            try:
                cur_state = SessionState(session.status)
            except ValueError:
                break
            new_command, _ = _desired_command(
                cur_state,
                phase=phase,
                capture_source=capture_source,
                camera_config=camera_config,
            )
            if new_command in CONTROL_COMMANDS or new_command == "STOP":
                command, payload = new_command, None
                break
    target = client_cursor + 1
    if target > MAX_EXACT_CURSOR:
        raise ValueError("cursor fora do intervalo exato 0..2^53-1")
    existing = await db.scalar(
        select(GatewayCommand).where(
            GatewayCommand.session_id == session.id, GatewayCommand.cursor == target
        )
    )
    if existing is not None:
        return existing
    # Garante monotonicidade: próximo cursor é max(target, max_persistido+1).
    max_cursor = await db.scalar(
        select(func.max(GatewayCommand.cursor)).where(GatewayCommand.session_id == session.id)
    )
    if max_cursor is not None and int(max_cursor) >= target:
        target = int(max_cursor) + 1
    row = GatewayCommand(
        session_id=session.id,
        cursor=target,
        command=command,
        payload=_payload_for(command, payload, target),
        status="PENDING",
    )
    db.add(row)
    await db.flush()
    return row


def _payload_for(command: str, payload: dict | None, cursor: int) -> dict | None:
    if command == "CAPTURE_FULL":
        base = dict(payload or {})
        return {**base, "capture_id": f"cap-{cursor:03d}-full"}
    if command == "CAPTURE_PROBE":
        base = dict(payload or {})
        return {**base, "capture_id": f"cap-{cursor:03d}-probe"}
    return None


async def ack_command(db: AsyncSession, session: Session, *, cursor: int) -> GatewayCommand | None:
    """Confirma efeito durável do comando (contrato §5.7). Idempotente."""
    row = await db.scalar(
        select(GatewayCommand)
        .where(GatewayCommand.session_id == session.id, GatewayCommand.cursor == cursor)
        .with_for_update()
    )
    if row is None:
        return None
    if row.status != "ACKED":
        row.status = "ACKED"
        row.ack_at = datetime.now(UTC)
        row.attempts = int(row.attempts or 0) + 1
        await db.flush()
    return row
