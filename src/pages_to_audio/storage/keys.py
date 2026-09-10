"""Storage key conventions — §12.2. All pure functions, no I/O."""

from __future__ import annotations


def frame_key(session_id: str, capture_id: str, frame_index: int) -> str:
    return f"sessions/{session_id}/frames/{capture_id}/{frame_index}.jpg"


def page_original_key(session_id: str, logical_index: int) -> str:
    return f"sessions/{session_id}/pages/{logical_index}/original.jpg"


def derived_key(session_id: str, artifact_type: str, artifact_id: str) -> str:
    return f"sessions/{session_id}/derived/{artifact_type}/{artifact_id}.jpg"


def ocr_raw_key(session_id: str, provider: str, logical_index: int) -> str:
    return f"sessions/{session_id}/ocr/{provider}/{logical_index}.json"


def audio_status_key(session_id: str, artifact_id: str) -> str:
    return f"sessions/{session_id}/audio/status/{artifact_id}.mp3"


def audio_final_key(session_id: str, artifact_id: str) -> str:
    return f"sessions/{session_id}/audio/final/{artifact_id}.mp3"


# D01/D04/D05 — namespace próprio de diagnóstico (nunca mistura com missão).
def diag_photo_key(device_code: str, diagnostic_id: str, frame_index: int) -> str:
    return f"diagnostics/{device_code}/{diagnostic_id}/photo_{frame_index:04d}.jpg"


def diag_clip_frame_key(device_code: str, diagnostic_id: str, frame_index: int) -> str:
    return f"diagnostics/{device_code}/{diagnostic_id}/clip_{frame_index:04d}.jpg"


def diag_preview_key(device_code: str, diagnostic_id: str) -> str:
    return f"diagnostics/{device_code}/{diagnostic_id}/preview_latest.jpg"


def diag_clip_key(device_code: str, diagnostic_id: str) -> str:
    return f"diagnostics/{device_code}/{diagnostic_id}/clip.mp4"
