"""CapturePolicy — §3.2. Exact fields from §15.2."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from src.pages_to_audio.common.ids import new_uuid
from src.pages_to_audio.config.settings import get_settings


class EndPolicy(BaseModel):
    manual_enabled: bool = True
    visual_marker_enabled: bool = True
    open_hand_enabled: bool = True
    soft_idle_seconds: int = 30
    hard_idle_seconds: int = 120


class CapturePolicy(BaseModel):
    version: str = "1"
    lease_id: str = ""
    valid_until: str = ""
    probe_interval_ms: int = 500
    probe_resolution: str = "QVGA"
    probe_jpeg_quality: int = 50
    stable_probe_count: int = 3
    full_frames: int = 3
    full_resolution: str = "UXGA"
    full_jpeg_quality: int = 90
    full_gap_ms: int = 200
    expected_pages: int = 30
    end: EndPolicy = EndPolicy()


def build_capture_policy(
    expected_pages: int | None = None,
    *,
    lease_ttl_seconds: int = 60,
) -> CapturePolicy:
    settings = get_settings()
    ep = expected_pages or settings.capture_defaults.EXPECTED_PAGES
    valid_until = (datetime.now(UTC) + timedelta(seconds=lease_ttl_seconds)).isoformat()

    return CapturePolicy(
        lease_id=new_uuid(),
        valid_until=valid_until,
        expected_pages=ep,
        end=EndPolicy(
            soft_idle_seconds=30,
            hard_idle_seconds=120,
        ),
    )
