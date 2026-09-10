"""G04 — immutable originals, OCR derivatives and upload telemetry."""

from __future__ import annotations

import hashlib
import uuid
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from src.pages_to_audio.capture.frame_upload import (
    FrameUploadRequest,
    _validate_image_content,
    upload_frame,
)
from src.pages_to_audio.common.errors import NonRetryableError
from src.pages_to_audio.db.models.frame import Frame
from src.pages_to_audio.db.models.image_artifact import ImageArtifact
from src.pages_to_audio.storage.fake_storage import FakeStorageAdapter


def _jpeg_bytes() -> bytes:
    image = Image.new("RGB", (96, 64), color=(40, 100, 160))
    output = BytesIO()
    image.save(output, format="JPEG", quality=88)
    return output.getvalue()


def _result(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_proves_origin_db_and_derived_sha_without_overwriting_original() -> None:
    data = _jpeg_bytes()
    original_sha = hashlib.sha256(data).hexdigest()
    session_id = uuid.uuid4()
    session = SimpleNamespace(
        id=session_id,
        public_id="S-G04-001",
        status="CAPTURING",
        capture_source="ANDROID_CAMERA",
        session_type="EXAM",
        requested_camera_config_json={
            "frame_size": "UXGA",
            "esp_jpeg_quality": 10,
            "frame_count": 2,
            "technical_config": {"buffer_bytes": 655360, "dma_enabled": False},
        },
        effective_camera_config_json={
            "frame_size": "UXGA",
            "esp_jpeg_quality": 10,
            "frame_count": 2,
            "technical_config": {"buffer_bytes": 655360, "dma_enabled": False},
        },
        camera_profile_revision_id=uuid.uuid4(),
        camera_profile_snapshot_json={"revision": 1},
        firmware_version="production-2.1",
        capabilities_version="v2",
    )
    capture = SimpleNamespace(id=uuid.uuid4(), received_frames=0)
    storage = FakeStorageAdapter()
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[_result(session), _result(capture), _result(None), _result(None)]
    )
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    result = await upload_frame(
        FrameUploadRequest(
            session_id=session.public_id,
            capture_id="CAP-G04-001",
            frame_index=0,
            page_number=3,
            frame_number=1,
            declared_sha256=original_sha,
            data=data,
            mime_type="image/jpeg",
            source_resolution="UXGA",
        ),
        storage,
        db,
    )

    assert result.sha256 == original_sha
    assert result.derived_storage_key is not None
    assert result.storage_key != result.derived_storage_key
    assert await storage.get_object("pages-originals", result.storage_key) == data
    derived = await storage.get_object("pages-derived", result.derived_storage_key)
    assert hashlib.sha256(derived).hexdigest() != original_sha

    frames = [
        item for call in db.add.call_args_list for item in call.args if isinstance(item, Frame)
    ]
    artifacts = [
        item
        for call in db.add.call_args_list
        for item in call.args
        if isinstance(item, ImageArtifact)
    ]
    assert len(frames) == 1
    assert len(artifacts) == 1
    frame = frames[0]
    artifact = artifacts[0]
    assert frame.sha256 == original_sha
    assert frame.storage_key_original == result.storage_key
    assert frame.jpeg_size_bytes == len(data)
    assert frame.jpeg_valid is True
    assert frame.page_number == 3
    assert frame.frame_number == 1
    assert frame.configured_buffer_bytes == 655360
    assert frame.dma_enabled is False
    assert artifact.metadata_["original_sha256"] == original_sha
    assert artifact.metadata_["original_storage_key"] == result.storage_key
    assert artifact.storage_key == result.derived_storage_key


@pytest.mark.unit
def test_truncated_jpeg_is_rejected_after_magic_byte_check() -> None:
    with pytest.raises(NonRetryableError, match="decodable image"):
        _validate_image_content(b"\xff\xd8\xff\xe0not-a-jpeg", "image/jpeg")


@pytest.mark.unit
def test_admin_frame_listing_orders_by_logical_page_before_arrival_time() -> None:
    import inspect

    from apps.api.routers import admin_sessions

    source = inspect.getsource(admin_sessions.session_detail)
    assert "Frame.page_number.nulls_last()" in source
    assert "Frame.frame_number.nulls_last()" in source


@pytest.mark.unit
def test_capture_complete_returns_authoritative_count_without_undefined_upload_result() -> None:
    import inspect

    from apps.api.routers import gateway

    source = inspect.getsource(gateway.capture_complete)
    assert '"declared_frames"' in source
    assert '"status"' in source
    assert "result.duplicate" not in source
