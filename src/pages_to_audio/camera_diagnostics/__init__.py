"""D00-D01 — domínio de diagnóstico de câmera (puro, sem I/O)."""

from __future__ import annotations

# Limites iniciais propostos (contrato P2A-CAMERA-DIAG-2026-09-09 §2/§10).
PHOTO_MAX_BYTES = 2 * 1024 * 1024
PREVIEW_ROUND_MAX_BYTES = 20 * 1024 * 1024
CLIP_INPUT_MAX_BYTES = 20 * 1024 * 1024
CLIP_MAX_SECONDS = 30
CLIP_MAX_FRAMES = 60
CLIP_DEFAULT_SECONDS = 10
PREVIEW_DEFAULT_SECONDS = 60
PREVIEW_TARGET_FPS = 2.0
CLIP_TARGET_FPS = 2.0
HISTORY_DAYS = 7
HISTORY_MAX_BYTES_PER_DEVICE = 100 * 1024 * 1024
PREVIEW_TRANSIENT_TTL_S = 10 * 60
HEARTBEAT_S = 10
AUTHZ_TTL_S = 30
STALE_AFTER_S = 5
VIDEO_CONVERT_TIMEOUT_S = 60

VALID_MODES = frozenset({"PHOTO", "CLIP", "PREVIEW"})
VALID_STATUSES = frozenset({"REQUESTED", "ACTIVE", "STOPPING", "COMPLETED", "FAILED", "EXPIRED"})
# Somente resoluções já validadas pelo plano principal na v1.
VALID_RESOLUTIONS = frozenset({"QVGA", "VGA", "SVGA", "XGA", "SXGA", "UXGA"})

TERMINAL_STATUSES = frozenset({"COMPLETED", "FAILED", "EXPIRED"})


def limits_for_mode(mode: str) -> dict[str, int]:
    if mode == "PHOTO":
        return {"duration_limit_s": 30, "bytes_limit": PHOTO_MAX_BYTES, "max_frames": 1}
    if mode == "CLIP":
        return {
            "duration_limit_s": CLIP_DEFAULT_SECONDS,
            "bytes_limit": CLIP_INPUT_MAX_BYTES,
            "max_frames": CLIP_MAX_FRAMES,
        }
    return {
        "duration_limit_s": PREVIEW_DEFAULT_SECONDS,
        "bytes_limit": PREVIEW_ROUND_MAX_BYTES,
        "max_frames": PREVIEW_DEFAULT_SECONDS * int(PREVIEW_TARGET_FPS),
    }


def validate_profile(resolution: str | None, jpeg_quality: int | None) -> dict[str, int | str]:
    res = (resolution or ("SVGA")).upper()
    if res not in VALID_RESOLUTIONS:
        raise ValueError(f"resolution must be one of {sorted(VALID_RESOLUTIONS)}")
    q = int(jpeg_quality) if jpeg_quality is not None else 18
    if not 5 <= q <= 40:
        raise ValueError("jpeg_quality must be in [5, 40]")
    return {"resolution": res, "jpeg_quality": q}


def diag_prefix(device_code: str, diagnostic_id: str) -> str:
    return f"diagnostics/{device_code}/{diagnostic_id}/"


def photo_key(device_code: str, diagnostic_id: str, frame_index: int) -> str:
    return f"diagnostics/{device_code}/{diagnostic_id}/photo_{frame_index:04d}.jpg"


def clip_frame_key(device_code: str, diagnostic_id: str, frame_index: int) -> str:
    return f"diagnostics/{device_code}/{diagnostic_id}/clip_{frame_index:04d}.jpg"


def preview_key(device_code: str, diagnostic_id: str) -> str:
    # Objeto temporário de índice único (ponteiro last_frame_key no banco).
    return f"diagnostics/{device_code}/{diagnostic_id}/preview_latest.jpg"


def clip_output_key(device_code: str, diagnostic_id: str) -> str:
    return f"diagnostics/{device_code}/{diagnostic_id}/clip.mp4"


def is_diagnostic_key(key: str) -> bool:
    # Limpeza restrita a diagnóstico: só chaves com este prefixo verificadas.
    return (key.startswith("diagnostics/") and "/dg_" in key) or key.startswith("diagnostics/")


def effective_fps(received_frames: int, elapsed_s: float) -> float:
    if elapsed_s <= 0:
        return 0.0
    return round(received_frames / elapsed_s, 2)
