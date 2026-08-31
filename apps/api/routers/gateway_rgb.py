"""Firmware V2.2 RGB result delivery endpoints for Android Gateway."""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from apps.api.dependencies import UowDep
from src.pages_to_audio.auth.gateway import verify_gateway_token
from src.pages_to_audio.rgb.delivery import (
    RgbApiError,
    get_sequence_for_binding,
    get_session_binding,
    record_rgb_event,
    result_snapshot,
)
from src.pages_to_audio.rgb.schemas import RgbEventName, RgbResultCommand

router = APIRouter(
    prefix="/gateway",
    tags=["gateway-rgb"],
    dependencies=[Depends(verify_gateway_token)],
)
GatewayIdDep = Annotated[str, Depends(verify_gateway_token)]


class ResultPollResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: RgbResultCommand
    cursor: int = Field(ge=0, strict=True)
    session_id: str
    sequence_id: str | None = None
    revision: int | None = Field(default=None, ge=1, strict=True)
    item_count: int | None = Field(default=None, ge=1, le=1000, strict=True)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class RgbSequenceEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    sequence_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    revision: int = Field(ge=1, strict=True)
    event: RgbEventName
    next_index: int = Field(ge=0, le=1000, strict=True)
    item_count: int = Field(ge=1, le=1000, strict=True)


def _raise_api_error(error: RgbApiError) -> NoReturn:
    # Kept as a helper so all three endpoints preserve the same public error mapping.
    raise error


@router.get(
    "/session/{session_id}/result",
    response_model=ResultPollResponse,
    responses={204: {"description": "No result cursor update"}},
)
async def get_result(
    session_id: str,
    uow: UowDep,
    gateway_code: GatewayIdDep,
    device_id: str = Query(min_length=1, max_length=128),
    cursor: int = Query(default=0, ge=0),
) -> ResultPollResponse | Response:
    try:
        binding = await get_session_binding(
            uow.session,
            session_public_id=session_id,
            device_code=device_id,
            gateway_code=gateway_code,
        )
        snapshot = await result_snapshot(uow.session, binding, cursor=cursor)
    except RgbApiError as exc:
        _raise_api_error(exc)
    if snapshot is None:
        return Response(status_code=204)
    return ResultPollResponse(
        command=snapshot.command,
        cursor=snapshot.cursor,
        session_id=snapshot.session_id,
        sequence_id=snapshot.sequence_id,
        revision=snapshot.revision,
        item_count=snapshot.item_count,
        sha256=snapshot.sha256,
    )


@router.get(
    "/session/{session_id}/rgb-sequence",
    response_class=Response,
    responses={200: {"content": {"application/json": {}}}},
)
async def download_rgb_sequence(
    session_id: str,
    uow: UowDep,
    gateway_code: GatewayIdDep,
    device_id: str = Query(min_length=1, max_length=128),
    sequence_id: str = Query(min_length=1, max_length=64),
) -> Response:
    try:
        binding = await get_session_binding(
            uow.session,
            session_public_id=session_id,
            device_code=device_id,
            gateway_code=gateway_code,
        )
        _, raw = await get_sequence_for_binding(
            uow.session,
            binding,
            sequence_id=sequence_id,
        )
    except RgbApiError as exc:
        _raise_api_error(exc)
    return Response(content=raw, media_type="application/json")


@router.post(
    "/session/{session_id}/rgb-sequence/event",
    status_code=200,
)
async def receive_rgb_event(
    session_id: str,
    body: RgbSequenceEventRequest,
    uow: UowDep,
    gateway_code: GatewayIdDep,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, object]:
    try:
        binding = await get_session_binding(
            uow.session,
            session_public_id=session_id,
            device_code=body.device_id,
            gateway_code=gateway_code,
        )
        result = await record_rgb_event(
            uow.session,
            binding,
            session_id=body.session_id,
            sequence_id=body.sequence_id,
            revision=body.revision,
            event=body.event,
            next_index=body.next_index,
            item_count=body.item_count,
            idempotency_key=idempotency_key,
            raw_payload=body.model_dump(mode="json"),
        )
    except RgbApiError as exc:
        _raise_api_error(exc)
    return {
        "accepted": True,
        "duplicate": result.duplicate,
        "session_id": session_id,
        "sequence_id": result.sequence.sequence_id,
        "revision": result.sequence.revision,
        "event": body.event.value,
        "next_index": result.sequence.last_next_index,
        "item_count": result.sequence.item_count,
    }
