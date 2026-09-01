from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response

from apps.api.dependencies import SettingsDep
from apps.api.schemas.admin import AdminLoginRequest, AdminMeResponse, AdminSessionResponse
from src.pages_to_audio.auth.admin import (
    COOKIE_NAME,
    AdminClaimsDep,
    AdminCsrfDep,
    clear_login_attempts,
    create_admin_token,
    enforce_login_rate_limit,
    verify_admin_password,
)

router = APIRouter(prefix="/admin", tags=["admin-auth"])


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


@router.post("/login", response_model=AdminSessionResponse)
async def login(
    body: AdminLoginRequest, request: Request, response: Response, settings: SettingsDep
) -> AdminSessionResponse:
    key = _client_key(request)
    enforce_login_rate_limit(key, settings)
    if not verify_admin_password(body.password, settings):
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Invalid credentials")
    clear_login_attempts(key)
    token, _csrf, expires = create_admin_token(settings)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.ADMIN_SESSION_TTL_DAYS * 86400,
        expires=expires,
        path="/",
        secure=settings.APP_ENV == "production",
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return AdminSessionResponse(expires_at=expires)


@router.get("/me", response_model=AdminMeResponse)
async def me(claims: AdminClaimsDep, response: Response) -> AdminMeResponse:
    response.headers["Cache-Control"] = "no-store"
    return AdminMeResponse(
        expires_at=datetime.fromtimestamp(int(claims["exp"]), tz=UTC),
        csrf_token=str(claims["csrf"]),
    )


@router.post("/logout", status_code=204)
async def logout(_claims: AdminCsrfDep, response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")
    response.headers["Cache-Control"] = "no-store"
