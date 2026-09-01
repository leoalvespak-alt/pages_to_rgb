from __future__ import annotations

import base64
import hashlib
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.schemas.admin import AdminSettingsRead, AdminSettingsUpdate, PaletteColor
from src.pages_to_audio.config.settings import AppSettings, get_settings
from src.pages_to_audio.db.models.admin_settings import (
    DEFAULT_EXAM_PALETTE,
    DEFAULT_HANDWRITTEN_PALETTE,
    AdminSettings,
)
from src.pages_to_audio.db.models.audit_event import AuditEvent


class SettingsConflictError(RuntimeError):
    pass


class SettingsCryptoError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EffectiveAdminSettings:
    version: int
    ocr_provider: str
    solve_model: str
    verify_model: str
    arbiter_model: str
    expected_pages: int
    expected_questions: int
    handwritten_expected_questions: int
    minimum_ratio: float
    brightness_percent: int
    on_ms: int
    off_ms: int
    palette: dict[str, dict[str, list[int]]]
    handwritten_palette: dict[str, dict[str, list[int]]]

    def snapshot(self, session_type: str) -> dict[str, Any]:
        data = asdict(self)
        data["session_type"] = session_type
        data["settings_version"] = data.pop("version")
        return data


def _fernet(settings: AppSettings | None = None) -> Fernet:
    app_settings = settings or get_settings()
    secret = app_settings.ADMIN_SETTINGS_ENCRYPTION_KEY.get_secret_value()
    if not secret:
        raise SettingsCryptoError("ADMIN_SETTINGS_ENCRYPTION_KEY is required")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt_secret(value: str, settings: AppSettings | None = None) -> str:
    if not value:
        raise ValueError("Secret must not be empty")
    return _fernet(settings).encrypt(value.encode()).decode()


def decrypt_secret(value: str | None, settings: AppSettings | None = None) -> str:
    if not value:
        return ""
    try:
        return _fernet(settings).decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise SettingsCryptoError("Encrypted admin secret is invalid") from exc


def mask_secret(value: str | None) -> str:
    return "••••••••" if value else ""


def fallback_effective(settings: AppSettings | None = None) -> EffectiveAdminSettings:
    app = settings or get_settings()
    return EffectiveAdminSettings(
        version=0,
        ocr_provider="google_document_ai",
        solve_model=app.DEEPSEEK_MODEL,
        verify_model=app.DEEPSEEK_MODEL,
        arbiter_model=app.ANTHROPIC_MODEL_ARBITER,
        expected_pages=app.DEFAULT_EXPECTED_PAGES,
        expected_questions=app.DEFAULT_EXPECTED_QUESTIONS,
        handwritten_expected_questions=10,
        minimum_ratio=app.DEFAULT_MINIMUM_RATIO,
        brightness_percent=app.RGB_DEFAULT_BRIGHTNESS_PERCENT,
        on_ms=app.RGB_DEFAULT_ON_MS,
        off_ms=app.RGB_DEFAULT_OFF_MS,
        palette={k: {"rgb": list(v["rgb"])} for k, v in DEFAULT_EXAM_PALETTE.items()},
        handwritten_palette={
            k: {"rgb": list(v["rgb"])} for k, v in DEFAULT_HANDWRITTEN_PALETTE.items()
        },
    )


def effective_from_row(row: AdminSettings) -> EffectiveAdminSettings:
    return EffectiveAdminSettings(
        version=row.version,
        ocr_provider=row.ocr_provider,
        solve_model=row.solve_model,
        verify_model=row.verify_model,
        arbiter_model=row.arbiter_model,
        expected_pages=row.expected_pages,
        expected_questions=row.expected_questions,
        handwritten_expected_questions=row.handwritten_expected_questions,
        minimum_ratio=float(row.minimum_ratio),
        brightness_percent=row.brightness_percent,
        on_ms=row.on_ms,
        off_ms=row.off_ms,
        palette=row.palette,
        handwritten_palette=row.handwritten_palette,
    )


async def get_admin_settings_row(db: AsyncSession, *, lock: bool = False) -> AdminSettings:
    stmt = select(AdminSettings).where(AdminSettings.singleton_key == 1)
    if lock:
        stmt = stmt.with_for_update()
    row = await db.scalar(stmt)
    if row is None:
        row = AdminSettings(singleton_key=1)
        db.add(row)
        await db.flush()
    return row


async def get_effective_admin_settings(db: AsyncSession) -> EffectiveAdminSettings:
    row = await db.scalar(select(AdminSettings).where(AdminSettings.singleton_key == 1))
    return effective_from_row(row) if row is not None else fallback_effective()


def _palette_for_api(raw: dict[str, dict[str, list[int]]]) -> dict[str, PaletteColor]:
    return {letter: PaletteColor(rgb=tuple(value["rgb"])) for letter, value in raw.items()}


def settings_read(row: AdminSettings) -> AdminSettingsRead:
    return AdminSettingsRead(
        ocr_provider=row.ocr_provider,
        solve_model=row.solve_model,
        verify_model=row.verify_model,
        arbiter_model=row.arbiter_model,
        deepseek_api_key=mask_secret(row.deepseek_api_key_encrypted),
        gemini_api_key=mask_secret(row.gemini_api_key_encrypted),
        anthropic_api_key=mask_secret(row.anthropic_api_key_encrypted),
        glm_api_key=mask_secret(row.glm_api_key_encrypted),
        deepseek_configured=bool(row.deepseek_api_key_encrypted),
        gemini_configured=bool(row.gemini_api_key_encrypted),
        anthropic_configured=bool(row.anthropic_api_key_encrypted),
        glm_configured=bool(row.glm_api_key_encrypted),
        expected_pages=row.expected_pages,
        expected_questions=row.expected_questions,
        handwritten_expected_questions=row.handwritten_expected_questions,
        minimum_ratio=float(row.minimum_ratio),
        brightness_percent=row.brightness_percent,
        on_ms=row.on_ms,
        off_ms=row.off_ms,
        palette=_palette_for_api(row.palette),
        handwritten_palette=_palette_for_api(row.handwritten_palette),
        version=row.version,
        updated_at=row.updated_at,
    )


async def update_admin_settings(
    db: AsyncSession, payload: AdminSettingsUpdate, *, actor: str = "admin"
) -> AdminSettings:
    row = await get_admin_settings_row(db, lock=True)
    if row.version != payload.version:
        raise SettingsConflictError("Settings were changed by another request")
    data = payload.model_dump(exclude_unset=True)
    changed: list[str] = []
    ordinary = {
        "ocr_provider",
        "solve_model",
        "verify_model",
        "arbiter_model",
        "expected_pages",
        "expected_questions",
        "handwritten_expected_questions",
        "minimum_ratio",
        "brightness_percent",
        "on_ms",
        "off_ms",
        "palette",
        "handwritten_palette",
    }
    for field in ordinary:
        if field in data and data[field] is not None:
            value = data[field]
            if field in {"palette", "handwritten_palette"}:
                value = {k: {"rgb": list(v["rgb"])} for k, v in value.items()}
            if field == "minimum_ratio":
                value = Decimal(str(value))
            setattr(row, field, value)
            changed.append(field)
    for name in ("deepseek", "gemini", "anthropic", "glm"):
        input_field = f"{name}_api_key"
        column = f"{name}_api_key_encrypted"
        if data.get(f"clear_{input_field}"):
            setattr(row, column, None)
            changed.append(input_field)
        else:
            value = data.get(input_field)
            if value and "•" not in value and value != "***":
                setattr(row, column, encrypt_secret(value))
                changed.append(input_field)
    row.version += 1
    db.add(
        AuditEvent(
            session_id=None,
            event_type="ADMIN_SETTINGS_UPDATED",
            stage="SYSTEM",
            severity="INFO",
            actor_type=actor,
            payload={"changed_fields": sorted(changed), "settings_version": row.version},
        )
    )
    await db.flush()
    return row


def palette_from_snapshot(
    snapshot: dict[str, Any] | None, session_type: str
) -> dict[str, dict[str, list[int]]] | None:
    if not snapshot:
        return None
    key = "handwritten_palette" if session_type == "HANDWRITTEN_WORD" else "palette"
    value = snapshot.get(key)
    return value if isinstance(value, dict) else None


def rgb_for_answer(snapshot: dict[str, Any] | None, session_type: str, letter: str) -> list[int]:
    palette = palette_from_snapshot(snapshot, session_type)
    fallback = (
        DEFAULT_HANDWRITTEN_PALETTE if session_type == "HANDWRITTEN_WORD" else DEFAULT_EXAM_PALETTE
    )
    source = palette or fallback
    value = source.get(letter, {}).get("rgb")
    if not isinstance(value, list) or len(value) != 3:
        value = fallback[letter]["rgb"]
    return [int(channel) for channel in value]
