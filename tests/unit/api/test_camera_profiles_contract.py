"""G03 — contract tests for production OCR/PHOTO camera profiles."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from apps.api.main import create_app
from apps.api.schemas.admin import CameraCapabilitiesV1, CameraProfileCreate
from src.pages_to_audio.camera_profiles.contract import (
    AVAILABLE_CAMERA_VALUES,
    UNAVAILABLE_CAMERA_CONTROLS,
    CameraMode,
    default_profile_values,
    normalize_camera_mode,
)
from src.pages_to_audio.camera_profiles.service import (
    CameraProfileError,
    capabilities_payload,
    create_profile,
    device_supports_v2,
    require_v2_enabled,
)
from src.pages_to_audio.config.settings import AppSettings
from src.pages_to_audio.db.models.audit_event import AuditEvent
from src.pages_to_audio.db.models.camera_profile_revision import CameraProfileRevision


@pytest.mark.unit
def test_default_ocr_and_photo_profiles_are_distinct_static_profiles() -> None:
    ocr = default_profile_values(CameraMode.OCR)
    photo = default_profile_values(CameraMode.PHOTO)

    assert ocr["frame_size"] == photo["frame_size"] == "UXGA"
    assert ocr["esp_jpeg_quality"] == photo["esp_jpeg_quality"] == 10
    assert ocr["frame_count"] == 2
    assert photo["frame_count"] == 1
    assert ocr["technical_config"]["sensor"] == "OV2640"


@pytest.mark.unit
def test_camera_profile_quality_contract_rejects_android_quality_in_esp_field() -> None:
    for quality in (8, 10, 12):
        assert CameraProfileCreate(esp_jpeg_quality=quality).esp_jpeg_quality == quality
    for quality in (7, 13, 90):
        with pytest.raises(ValidationError):
            CameraProfileCreate(esp_jpeg_quality=quality)


@pytest.mark.unit
def test_camera_profile_rejects_video_clip_and_preview_modes() -> None:
    for mode in ("VIDEO", "CLIP", "PREVIEW"):
        with pytest.raises(ValidationError):
            CameraProfileCreate(mode=mode)
        with pytest.raises(ValueError):
            normalize_camera_mode(mode)


@pytest.mark.unit
def test_capabilities_report_unavailable_controls_and_protected_values() -> None:
    settings = AppSettings(_env_file=None, CAMERA_CONTRACT_V2_ENABLED=True)  # type: ignore[call-arg]
    device = SimpleNamespace(
        firmware_version="production-2.1",
        metadata_={
            "camera_capabilities_version": "v2",
            "driver_version": "esp32-camera 2.1.7",
        },
    )

    response = CameraCapabilitiesV1(**capabilities_payload(device, settings))

    assert response.compatible is True
    assert response.feature_enabled is True
    assert response.protected["xclk_hz"] == 10_000_000
    assert response.available["esp_jpeg_quality"] == {"min": 8, "max": 12}
    assert set(("video", "clip", "preview")) <= set(response.unavailable)
    assert response.unavailable == UNAVAILABLE_CAMERA_CONTROLS
    assert response.available["modes"] == AVAILABLE_CAMERA_VALUES["modes"]


@pytest.mark.unit
def test_old_firmware_is_incompatible_when_contract_flag_is_enabled() -> None:
    settings = AppSettings(_env_file=None, CAMERA_CONTRACT_V2_ENABLED=True)  # type: ignore[call-arg]
    device = SimpleNamespace(metadata_={}, firmware_version="legacy-1")

    assert device_supports_v2(device) is False
    with pytest.raises(CameraProfileError, match="capability v2") as caught:
        require_v2_enabled(settings, device)
    assert caught.value.reason_code == "FIRMWARE_CAPABILITY_V2_REQUIRED"


@pytest.mark.unit
def test_legacy_session_flow_keeps_feature_disabled_and_new_routes_are_documented() -> None:
    app = create_app()
    openapi = app.openapi()
    paths = openapi["paths"]

    assert "/api/v1/admin/camera-profiles/capabilities" in paths
    assert "/api/v1/admin/camera-profiles" in paths
    assert "/api/v1/gateway/camera/capabilities" in paths
    assert "post" in paths["/api/v1/admin/camera-profiles"]
    assert "put" not in paths["/api/v1/admin/camera-profiles"]
    assert "patch" not in paths["/api/v1/admin/camera-profiles"]
    assert "CameraCapabilitiesV1" in openapi["components"]["schemas"]

    from apps.api.routers import gateway

    source = inspect.getsource(gateway.session_start)
    assert "camera_profile_snapshot_json" in source
    assert "CAMERA_PROFILE_SNAPSHOT_CREATED" in source
    assert "require_v2_enabled" in source


@pytest.mark.unit
def test_revision_creation_serializes_scope_and_audits_actor() -> None:
    from src.pages_to_audio.camera_profiles import service

    source = inspect.getsource(service.create_profile)
    assert "with_for_update" in source
    assert "CAMERA_PROFILE_CREATED" in source
    assert "created_by=actor" in source
    assert "pg_advisory_xact_lock" in inspect.getsource(service._lock_scope)


@pytest.mark.asyncio
async def test_new_revision_supersedes_previous_revision_and_records_admin_actor() -> None:
    class RecordingSession:
        bind = None

        def __init__(self, scalar_results: list[object]) -> None:
            self.scalar_results = scalar_results
            self.added: list[object] = []

        async def scalar(self, *_args: object, **_kwargs: object) -> object:
            return self.scalar_results.pop(0)

        def add(self, value: object) -> None:
            self.added.append(value)

        async def flush(self) -> None:
            return None

    settings = AppSettings(_env_file=None, CAMERA_CONTRACT_V2_ENABLED=True)  # type: ignore[call-arg]
    body = CameraProfileCreate(mode="PHOTO")
    previous = CameraProfileRevision(mode="PHOTO", revision=1, active=True)
    session = RecordingSession([previous])

    created = await create_profile(session, body, actor="admin", settings=settings)

    assert created.revision == 2
    assert created.frame_count == 1
    assert created.created_by == "admin"
    assert previous.active is False
    assert any(
        isinstance(item, AuditEvent) and item.actor_type == "admin" for item in session.added
    )
