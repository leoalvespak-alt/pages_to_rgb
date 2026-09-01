from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Response

from apps.api.dependencies import UowDep
from apps.api.schemas.admin import (
    AdminSettingsRead,
    AdminSettingsUpdate,
    ProviderTestRequest,
    ProviderTestResponse,
)
from src.pages_to_audio.admin.settings_service import (
    SettingsConflictError,
    decrypt_secret,
    get_admin_settings_row,
    settings_read,
    update_admin_settings,
)
from src.pages_to_audio.auth.admin import AdminClaimsDep, AdminCsrfDep
from src.pages_to_audio.db.models.audit_event import AuditEvent

router = APIRouter(prefix="/admin/settings", tags=["admin-settings"])


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
    column = (
        "anthropic_api_key_encrypted" if provider == "claude" else f"{provider}_api_key_encrypted"
    )
    return decrypt_secret(getattr(row, column, None))


async def _probe_provider(provider: str, model: str, key: str) -> None:
    if not key:
        raise HTTPException(status_code=422, detail="Provider key is not configured")
    headers = {"Content-Type": "application/json"}
    if provider == "gemini":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        params = {"key": key}
        payload: dict[str, Any] = {"contents": [{"parts": [{"text": "Reply OK"}]}]}
    elif provider == "claude":
        url = "https://api.anthropic.com/v1/messages"
        params = {}
        headers.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
        payload = {
            "model": model,
            "max_tokens": 4,
            "messages": [{"role": "user", "content": "Reply OK"}],
        }
    else:
        url = (
            "https://api.deepseek.com/chat/completions"
            if provider == "deepseek"
            else "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        )
        params = {}
        headers["Authorization"] = f"Bearer {key}"
        payload = {
            "model": model,
            "max_tokens": 4,
            "messages": [{"role": "user", "content": "Reply OK"}],
        }
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as client:
        result = await client.post(url, params=params, headers=headers, json=payload)
        result.raise_for_status()


@router.post("/test", response_model=ProviderTestResponse)
async def test_provider(
    body: ProviderTestRequest, _claims: AdminCsrfDep, uow: UowDep
) -> ProviderTestResponse:
    compatible = {
        "deepseek": "deepseek-v4-pro",
        "gemini": "gemini-3.1-pro",
        "claude": "claude-opus-5",
        "glm": "glm-5.3",
    }
    if compatible[body.provider] != body.model:
        raise HTTPException(status_code=422, detail="Model is incompatible with provider")
    row = await get_admin_settings_row(uow.session)
    started = time.perf_counter()
    error_code: str | None = None
    message: str | None = None
    ok = False
    try:
        await _probe_provider(body.provider, body.model, _provider_key(row, body.provider))
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
