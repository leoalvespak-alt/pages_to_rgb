"""Camera control contract shared by the API and the capture boundary.

The contract deliberately models still-image capture only.  Video, clip and
preview are legacy diagnostic concepts and are not valid profile modes.
"""

from __future__ import annotations

from copy import deepcopy
from enum import StrEnum
from typing import Any


class CameraMode(StrEnum):
    OCR = "OCR"
    PHOTO = "PHOTO"


UNSUPPORTED_CAMERA_MODES = frozenset({"VIDEO", "CLIP", "PREVIEW"})

_COMMON_PROFILE: dict[str, Any] = {
    "frame_size": "UXGA",
    "esp_jpeg_quality": 10,
    "intra_frame_gap_ms": 220,
    "page_interval_ms": 5000,
    "brightness": 0,
    "contrast": 1,
    "saturation": 0,
    "awb": True,
    "awb_gain": True,
    "wb_mode": "AUTO",
    "aec": True,
    "aec2": True,
    "agc": True,
    "bpc": True,
    "wpc": True,
    "raw_gamma": True,
    "lens_correction": True,
    "dcw": True,
    "hmirror": False,
    "vflip": False,
    "special_effect": "NORMAL",
    "colorbar": False,
    "technical_config": {
        "sensor": "OV2640",
        "pixel_format": "JPEG",
        "xclk_hz": 10_000_000,
        "buffer_bytes": 655_360,
        "framebuffers": 1,
        "psram_required": True,
        "dma_enabled": False,
    },
}

DEFAULT_CAMERA_PROFILES: dict[CameraMode, dict[str, Any]] = {
    CameraMode.OCR: {**deepcopy(_COMMON_PROFILE), "frame_count": 2},
    CameraMode.PHOTO: {**deepcopy(_COMMON_PROFILE), "frame_count": 1},
}

AVAILABLE_CAMERA_VALUES: dict[str, Any] = {
    "modes": [CameraMode.OCR.value, CameraMode.PHOTO.value],
    "frame_size": ["UXGA"],
    "esp_jpeg_quality": {"min": 8, "max": 12},
    "frame_count": {"min": 1, "max": 3},
    "intra_frame_gap_ms": {"min": 180, "max": 300},
    "page_interval_ms": {"min": 5000, "max": 86_400_000},
    "image_controls": [
        "brightness",
        "contrast",
        "saturation",
        "awb",
        "awb_gain",
        "wb_mode",
        "aec",
        "aec2",
        "agc",
        "bpc",
        "wpc",
        "raw_gamma",
        "lens_correction",
        "dcw",
        "hmirror",
        "vflip",
        "special_effect",
        "colorbar",
    ],
}

PROTECTED_CAMERA_VALUES: dict[str, Any] = {
    "sensor": "OV2640",
    "pixel_format": "JPEG",
    "frame_size": "UXGA",
    "xclk_hz": 10_000_000,
    "buffer_bytes": 655_360,
    "framebuffers": 1,
    "psram_required": True,
    "dma_enabled": False,
}

UNAVAILABLE_CAMERA_CONTROLS: dict[str, str] = {
    "video": "Vídeo não faz parte do contrato de produção desta release.",
    "clip": "Clipe não faz parte do contrato de produção desta release.",
    "preview": "Preview não faz parte do contrato de produção desta release.",
    "sharpness": "O driver OV2640 local não implementa este controle.",
    "denoise": "O driver OV2640 local não implementa este controle.",
    "autofocus": "O OV2640 não expõe autofocus no contrato desta placa.",
    "manual_focus": "Foco manual não está disponível no OV2640 desta placa.",
    "pll": "PLL não é configurável no contrato protegido da firmware Production.",
    "flash": "Flash de iluminação não é controlado por este contrato de câmera.",
}


def normalize_camera_mode(value: str | CameraMode) -> CameraMode:
    """Normalize a requested mode and reject legacy video-like modes."""

    normalized = value.value if isinstance(value, CameraMode) else str(value).strip().upper()
    if normalized in UNSUPPORTED_CAMERA_MODES:
        raise ValueError(f"Camera mode {normalized} is not supported; use OCR or PHOTO")
    try:
        return CameraMode(normalized)
    except ValueError as exc:
        raise ValueError(f"Unknown camera mode {normalized!r}; use OCR or PHOTO") from exc


def default_profile_values(mode: str | CameraMode) -> dict[str, Any]:
    """Return a detached default profile payload for the requested mode."""

    return deepcopy(DEFAULT_CAMERA_PROFILES[normalize_camera_mode(mode)])
