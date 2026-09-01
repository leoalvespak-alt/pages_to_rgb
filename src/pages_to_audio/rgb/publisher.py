"""Publish immutable, firmware-compatible RGB result revisions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.pages_to_audio.common.errors import ReasonCode
from src.pages_to_audio.config.settings import get_settings
from src.pages_to_audio.db.models.audit_event import AuditEvent
from src.pages_to_audio.db.models.device import Device
from src.pages_to_audio.db.models.final_answer import FinalAnswer
from src.pages_to_audio.db.models.gateway import AndroidGateway
from src.pages_to_audio.db.models.question import Question
from src.pages_to_audio.db.models.rgb_sequence import RgbSequence
from src.pages_to_audio.db.models.session import Session
from src.pages_to_audio.db.models.session_result_delivery import SessionResultDelivery
from src.pages_to_audio.domain.enums.audit import AuditEventType, AuditSeverity, AuditStage
from src.pages_to_audio.rgb.canonical import build_payload, canonical_items_bytes
from src.pages_to_audio.rgb.delivery import (
    RgbApiError,
    SessionBinding,
    get_or_create_delivery,
)
from src.pages_to_audio.rgb.policy import (
    DEFAULT_PALETTE,
    HANDWRITTEN_PALETTE,
    AnswerCandidate,
    validate_complete_answer_set,
)
from src.pages_to_audio.rgb.schemas import (
    AnswerLetter,
    RgbColor,
    RgbDefaults,
    RgbResultCommand,
    RgbSequenceStatus,
)


@dataclass(frozen=True, slots=True)
class RgbPublicationResult:
    sequence: RgbSequence | None
    command: RgbResultCommand
    reason_code: str | None
    reused: bool


async def _internal_binding(db: AsyncSession, session_public_id: str) -> SessionBinding:
    stmt = (
        select(Session, Device, AndroidGateway)
        .join(Device, Session.device_id == Device.id)
        .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
        .where(Session.public_id == session_public_id)
        .with_for_update()
    )
    row = (await db.execute(stmt)).one_or_none()
    if row is None:
        raise RgbApiError(
            "Session not found",
            reason_code=ReasonCode.SESSION_NOT_FOUND,
            http_status=404,
        )
    session, device, gateway = row
    return SessionBinding(session=session, device=device, gateway=gateway)


def _defaults(snapshot: dict[str, Any] | None = None) -> RgbDefaults:
    settings = get_settings()
    data = snapshot or {}
    return RgbDefaults(
        brightness_percent=int(
            data.get("brightness_percent", settings.RGB_DEFAULT_BRIGHTNESS_PERCENT)
        ),
        on_ms=int(data.get("on_ms", settings.RGB_DEFAULT_ON_MS)),
        off_ms=int(data.get("off_ms", settings.RGB_DEFAULT_OFF_MS)),
    )


def _snapshot_palette(session: Session) -> dict[AnswerLetter, RgbColor]:
    session_type = session.session_type or "EXAM"
    fallback = HANDWRITTEN_PALETTE if session_type == "HANDWRITTEN_WORD" else DEFAULT_PALETTE
    snapshot = session.config_snapshot or {}
    key = "handwritten_palette" if session_type == "HANDWRITTEN_WORD" else "palette"
    raw = snapshot.get(key)
    if not isinstance(raw, dict) or set(raw) != set("ABCDE"):
        return {letter: color.model_copy(deep=True) for letter, color in fallback.items()}
    try:
        palette = {
            letter: RgbColor(rgb=tuple(raw[letter]["rgb"])) for letter in ("A", "B", "C", "D", "E")
        }
        return cast(dict[AnswerLetter, RgbColor], palette)
    except (KeyError, TypeError, ValueError):
        return {letter: color.model_copy(deep=True) for letter, color in fallback.items()}


async def mark_processing_for_session(
    db: AsyncSession,
    *,
    session_public_id: str,
) -> None:
    """Persist RESULT_PROCESSING for a workflow that has started."""

    from src.pages_to_audio.rgb.delivery import mark_result_processing

    binding = await _internal_binding(db, session_public_id)
    await mark_result_processing(db, binding)
    await db.flush()


async def publish_rgb_for_session(
    db: AsyncSession,
    *,
    session_public_id: str,
) -> RgbPublicationResult:
    """Create/reuse a valid RGB revision or explicitly cancel RGB delivery."""

    settings = get_settings()
    binding = await _internal_binding(db, session_public_id)
    if not settings.RGB_RESULTS_ENABLED:
        await get_or_create_delivery(
            db,
            binding,
            command=RgbResultCommand.RESULT_CANCELLED,
            reason_code=ReasonCode.RGB_RESULTS_DISABLED.value,
        )
        await db.flush()
        return RgbPublicationResult(
            sequence=None,
            command=RgbResultCommand.RESULT_CANCELLED,
            reason_code=ReasonCode.RGB_RESULTS_DISABLED.value,
            reused=False,
        )

    # The delivery row is also the per-session lock for publication races.
    current_delivery = await db.scalar(
        select(SessionResultDelivery)
        .where(
            SessionResultDelivery.session_id == binding.session.id,
        )
        .with_for_update()
    )
    if (
        current_delivery is None
        or current_delivery.command != RgbResultCommand.RGB_SEQUENCE_READY.value
    ):
        await get_or_create_delivery(
            db,
            binding,
            command=RgbResultCommand.RESULT_PROCESSING,
        )

    rows = (
        await db.execute(
            select(Question, FinalAnswer)
            .outerjoin(FinalAnswer, FinalAnswer.question_id == Question.id)
            .where(Question.session_id == binding.session.id)
            .order_by(Question.question_number)
        )
    ).all()
    candidates = [
        AnswerCandidate(
            question_number=question.question_number,
            answer=final.answer if final is not None else None,
            validated=bool(final is not None and final.validated),
            question_status=question.status,
        )
        for question, final in rows
    ]
    answers, reason = validate_complete_answer_set(
        binding.session.expected_questions,
        candidates,
        max_items=settings.RGB_SEQUENCE_MAX_ITEMS,
    )
    if answers is None:
        reason_code = reason or ReasonCode.RGB_SEQUENCE_INCOMPLETE.value
        await get_or_create_delivery(
            db,
            binding,
            command=RgbResultCommand.RESULT_CANCELLED,
            reason_code=reason_code,
        )
        db.add(
            AuditEvent(
                session_id=binding.session.id,
                event_type=AuditEventType.RGB_SEQUENCE_INVALID,
                stage=AuditStage.SYSTEM,
                severity=AuditSeverity.WARNING,
                reason_code=reason_code,
                actor_type="workflow",
                payload={"expected_questions": binding.session.expected_questions},
            )
        )
        await db.flush()
        return RgbPublicationResult(
            sequence=None,
            command=RgbResultCommand.RESULT_CANCELLED,
            reason_code=reason_code,
            reused=False,
        )

    defaults = _defaults(binding.session.config_snapshot)
    # Isolated palette selection — HANDWRITTEN_WORD does not touch EXAM
    palette = _snapshot_palette(binding.session)
    probe_payload, _ = build_payload(
        session_id=binding.session.public_id,
        sequence_id="rgb-probe",
        revision=1,
        answers=answers,
        defaults=defaults,
        palette=palette,
    )

    latest = await db.scalar(
        select(RgbSequence)
        .where(RgbSequence.session_id == binding.session.id)
        .order_by(RgbSequence.revision.desc())
        .limit(1)
        .with_for_update()
    )
    existing = await db.scalar(
        select(RgbSequence)
        .where(
            RgbSequence.session_id == binding.session.id,
            RgbSequence.payload_sha256 == probe_payload.sha256,
            RgbSequence.status.notin_(
                [RgbSequenceStatus.INVALID.value, RgbSequenceStatus.SUPERSEDED.value]
            ),
        )
        .order_by(RgbSequence.revision.desc())
        .limit(1)
    )
    if existing is not None:
        sequence = existing
        reused = True
    else:
        revision = latest.revision + 1 if latest is not None else 1
        sequence_id = f"rgb-{uuid.uuid4().hex}"
        payload, raw = build_payload(
            session_id=binding.session.public_id,
            sequence_id=sequence_id,
            revision=revision,
            answers=answers,
            defaults=defaults,
            palette=palette,
        )
        if len(raw) > settings.RGB_SEQUENCE_MAX_JSON_BYTES:
            raise RgbApiError(
                "RGB sequence exceeds firmware JSON limit",
                reason_code=ReasonCode.RGB_SEQUENCE_INVALID,
                http_status=409,
            )
        if latest is not None and latest.status in {
            RgbSequenceStatus.READY.value,
            RgbSequenceStatus.RECEIVED.value,
            RgbSequenceStatus.PLAYING.value,
        }:
            latest.status = RgbSequenceStatus.SUPERSEDED.value
        sequence = RgbSequence(
            sequence_id=payload.sequence_id,
            session_id=binding.session.id,
            revision=payload.revision,
            schema_version=payload.schema_version,
            status=RgbSequenceStatus.READY.value,
            answers=payload.answers,
            item_count=payload.item_count,
            defaults=payload.defaults.model_dump(mode="json"),
            palette={key: value.model_dump(mode="json") for key, value in payload.palette.items()},
            overrides=[item.model_dump(mode="json") for item in payload.overrides],
            payload_sha256=payload.sha256,
            payload_size=len(canonical_items_bytes(payload)),
            ready_at=datetime.now(UTC),
        )
        db.add(sequence)
        await db.flush()
        reused = False
        db.add(
            AuditEvent(
                session_id=binding.session.id,
                event_type=AuditEventType.RGB_SEQUENCE_PUBLISHED,
                stage=AuditStage.SYSTEM,
                severity=AuditSeverity.INFO,
                actor_type="workflow",
                payload={
                    "sequence_id": sequence.sequence_id,
                    "revision": sequence.revision,
                    "item_count": sequence.item_count,
                    "payload_sha256": sequence.payload_sha256,
                },
            )
        )

    await get_or_create_delivery(
        db,
        binding,
        command=RgbResultCommand.RGB_SEQUENCE_READY,
        active_sequence_id=sequence.id,
    )
    await db.flush()
    return RgbPublicationResult(
        sequence=sequence,
        command=RgbResultCommand.RGB_SEQUENCE_READY,
        reason_code=None,
        reused=reused,
    )
