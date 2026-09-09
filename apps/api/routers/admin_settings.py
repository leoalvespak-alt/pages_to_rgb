from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from apps.api.dependencies import UowDep
from apps.api.schemas.admin import (
    AdminSettingsRead,
    AdminSettingsUpdate,
    ProviderCatalogResponse,
    ProviderTestRequest,
    ProviderTestResponse,
    RgbTestRequest,
    RgbTestResponse,
)
from src.pages_to_audio.admin.settings_service import (
    SettingsConflictError,
    get_admin_settings_row,
    provider_secret,
    settings_read,
    update_admin_settings,
)
from src.pages_to_audio.auth.admin import AdminClaimsDep, AdminCsrfDep
from src.pages_to_audio.db.models.audit_event import AuditEvent
from src.pages_to_audio.db.models.rgb_test_command import RgbTestCommand
from src.pages_to_audio.db.models.session import Session
from src.pages_to_audio.llm.providers.catalog import (
    catalog_payload,
    is_supported_model,
)

router = APIRouter(prefix="/admin/settings", tags=["admin-settings"])


@router.get("/catalog", response_model=ProviderCatalogResponse)
async def provider_catalog(_claims: AdminClaimsDep) -> ProviderCatalogResponse:
    """Return the provider/model catalog used by the Admin UI."""
    return ProviderCatalogResponse(providers=catalog_payload())


@router.get("", response_model=AdminSettingsRead)
async def read_settings(
    _claims: AdminClaimsDep, uow: UowDep, response: Response
) -> AdminSettingsRead:
    response.headers["Cache-Control"] = "no-store"
    return settings_read(await get_admin_settings_row(uow.session))


@router.put("", response_model=AdminSettingsRead)
async def write_settings(
    body: AdminSettingsUpdate,
    _claims: AdminCsrfDep,
    uow: UowDep,
    response: Response,
) -> AdminSettingsRead:
    try:
        row = await update_admin_settings(uow.session, body)
    except SettingsConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    response.headers["Cache-Control"] = "no-store"
    return settings_read(row)


def _provider_key(row: Any, provider: str) -> str:
    return provider_secret(row, provider)


async def _probe_provider(provider: str, model: str, key: str) -> None:
    if not key:
        raise HTTPException(status_code=422, detail="Provider key is not configured")
    headers = {"Content-Type": "application/json"}
    if provider != "gemini":
        raise HTTPException(
            status_code=422,
            detail="Google Document AI é validado separadamente com project/location/processor",
        )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    params = {"key": key}
    payload: dict[str, Any] = {
        "contents": [{"parts": [{"text": "Reply OK"}]}],
        "generationConfig": {"maxOutputTokens": 4, "temperature": 0},
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as client:
        result = await client.post(url, params=params, headers=headers, json=payload)
        result.raise_for_status()


async def _probe_document_ai(row: Any, credentials: str) -> None:
    """Validate access to the configured processor without processing a document."""
    project = str(getattr(row, "google_document_ai_project_id", "") or "")
    location = str(getattr(row, "google_document_ai_location", "") or "")
    processor = str(getattr(row, "google_document_ai_processor_id", "") or "")
    await _probe_document_ai_with(project, location, processor, credentials)


async def _probe_document_ai_with(
    project: str, location: str, processor: str, credentials: str
) -> None:
    """S06.6: testa a configuração efetivamente proposta (não a salva)."""
    if not project or not location or not processor:
        raise HTTPException(
            status_code=422, detail="Google Document AI project/location/processor is incomplete"
        )
    if not credentials:
        raise HTTPException(status_code=422, detail="Provider key is not configured")
    try:
        # S05.7/A27: save-and-verify usa o mesmo loader do processamento real
        # (JSON ou caminho), com refresh em thread.
        from src.pages_to_audio.ocr.credentials import (
            get_google_access_token,
            load_google_credentials,
        )

        creds = load_google_credentials(credentials)
        token = await get_google_access_token(creds)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail="Google Document AI credentials could not be loaded"
        ) from exc
    url = f"https://{location}-documentai.googleapis.com/v1/projects/{project}/locations/{location}/processors/{processor}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Google Document AI timed out") from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in {401, 403}:
            raise HTTPException(
                status_code=422, detail="Google Document AI credential was rejected"
            ) from exc
        raise
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail="Google Document AI is unreachable") from exc


@router.post("/test", response_model=ProviderTestResponse)
async def test_provider(
    body: ProviderTestRequest, _claims: AdminCsrfDep, uow: UowDep
) -> ProviderTestResponse:
    if not is_supported_model(body.provider, body.model):
        raise HTTPException(status_code=422, detail="Model is incompatible with provider")
    row = await get_admin_settings_row(uow.session)
    started = time.perf_counter()
    error_code: str | None = None
    message: str | None = None
    ok = False
    try:
        # S06.6/A23: usa a proposta do formulário quando enviada; salva só se omitida.
        if body.provider == "google_document_ai":
            project = body.google_document_ai_project_id or str(
                getattr(row, "google_document_ai_project_id", "") or ""
            )
            location = body.google_document_ai_location or str(
                getattr(row, "google_document_ai_location", "") or ""
            )
            processor = body.google_document_ai_processor_id or str(
                getattr(row, "google_document_ai_processor_id", "") or ""
            )
            credentials = body.google_document_ai_credentials
            if credentials is None:
                credentials = _provider_key(row, body.provider)
            await _probe_document_ai_with(project, location, processor, credentials)
        else:
            key = body.api_key if body.api_key is not None else _provider_key(row, body.provider)
            await _probe_provider(body.provider, body.model, key)
        ok = True
    except HTTPException:
        raise
    except httpx.TimeoutException:
        error_code, message = "TIMEOUT", "Provider timed out"
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        error_code = (
            "UNAUTHORIZED"
            if status in {401, 403}
            else "RATE_LIMITED"
            if status == 429
            else "UPSTREAM_ERROR"
        )
        message = f"Provider returned HTTP {status}"
    except httpx.RequestError:
        error_code, message = "NETWORK_ERROR", "Could not reach provider"
    response = ProviderTestResponse(
        ok=ok,
        provider=body.provider,
        model=body.model,
        latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
        error_code=error_code,
        message=message,
    )
    uow.session.add(
        AuditEvent(
            session_id=None,
            event_type="ADMIN_PROVIDER_TESTED",
            stage="SYSTEM",
            severity="INFO" if ok else "WARNING",
            actor_type="admin",
            reason_code=error_code,
            payload={
                "provider": body.provider,
                "model": body.model,
                "ok": ok,
                "latency_ms": response.latency_ms,
            },
        )
    )
    await uow.session.flush()
    return response


@router.post("/rgb-test", response_model=RgbTestResponse)
async def send_rgb_test(
    body: RgbTestRequest, _claims: AdminCsrfDep, uow: UowDep
) -> RgbTestResponse:
    session = await uow.session.scalar(select(Session).where(Session.public_id == body.session_id))
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status not in {"CREATED", "CAPTURING"}:
        raise HTTPException(status_code=409, detail="Session is not active")
    command = RgbTestCommand(
        session_id=session.id,
        rgb=list(body.rgb),
        brightness_percent=body.brightness_percent,
        on_ms=body.on_ms,
        off_ms=body.off_ms,
    )
    uow.session.add(command)
    await uow.session.flush()
    uow.session.add(
        AuditEvent(
            session_id=session.id,
            event_type="ADMIN_RGB_TEST_SENT",
            stage="DELIVER",
            severity="INFO",
            actor_type="admin",
            payload={
                "command_id": command.id,
                "rgb": list(body.rgb),
                "brightness_percent": body.brightness_percent,
                "on_ms": body.on_ms,
                "off_ms": body.off_ms,
            },
        )
    )
    return RgbTestResponse(
        command_id=command.id,
        session_id=str(session.public_id),
        rgb=body.rgb,
        brightness_percent=body.brightness_percent,
        on_ms=body.on_ms,
        off_ms=body.off_ms,
    )
