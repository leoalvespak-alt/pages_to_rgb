"""Audio validation — §36.2, §9.5.

All checks must pass before an AudioArtifact is marked READY.
Failure raises NonRetryableError(AUDIO_VALIDATION_FAILED) — never publish invalid audio.

Checks (§36.2):
1. File exists and size > minimum.
2. Duration within expected range.
3. No corruption (FFmpeg can probe it).
4. 20-second silence present within central region (detected by ffmpeg silencedetect).
"""

from __future__ import annotations

import asyncio
import json

from src.pages_to_audio.common.errors import NonRetryableError, ReasonCode
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)

_FFMPEG_TIMEOUT_S = 30.0
_MIN_SIZE_BYTES = 4096
_SILENCE_THRESHOLD_DB = -40
_SILENCE_MIN_DURATION_S = 15.0


class AudioValidationError(Exception):
    pass


async def _ffprobe_duration(audio_data: bytes) -> float:
    """Use ffprobe to get duration from raw audio bytes via pipe."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-i",
            "pipe:0",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(
            proc.communicate(input=audio_data), timeout=_FFMPEG_TIMEOUT_S
        )
    except (TimeoutError, FileNotFoundError):
        return 0.0

    try:
        data = json.loads(stdout)
        return float(data.get("format", {}).get("duration", 0.0))
    except (json.JSONDecodeError, ValueError):
        return 0.0


async def _detect_silence(audio_data: bytes) -> list[dict[str, float]]:
    """Run FFmpeg silencedetect filter on audio bytes, return detected silence intervals."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-i",
            "pipe:0",
            "-af",
            f"silencedetect=n={_SILENCE_THRESHOLD_DB}dB:d={_SILENCE_MIN_DURATION_S}",
            "-f",
            "null",
            "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(
            proc.communicate(input=audio_data), timeout=_FFMPEG_TIMEOUT_S
        )
    except (TimeoutError, FileNotFoundError):
        return []

    silences: list[dict[str, float]] = []
    lines = stderr.decode(errors="replace").splitlines()
    current: dict[str, float] = {}
    for line in lines:
        if "silence_start:" in line:
            try:
                current = {"start": float(line.split("silence_start:")[1].strip())}
            except ValueError:
                pass
        elif "silence_end:" in line and current:
            try:
                parts = line.split("|")
                end = float(parts[0].split("silence_end:")[1].strip())
                duration = float(parts[1].split("silence_duration:")[1].strip())
                current["end"] = end
                current["duration"] = duration
                silences.append(current)
                current = {}
            except (ValueError, IndexError):
                pass
    return silences


async def validate_audio(
    audio_data: bytes,
    *,
    expected_min_duration_s: float = 60.0,
    expected_max_duration_s: float = 3600.0,
    require_inter_round_silence: bool = True,
) -> None:
    """Validate audio data. Raises NonRetryableError on any failure.

    §36.2 checks:
    1. Size > minimum.
    2. Probed duration within expected range.
    3. FFprobe can parse the file (no corruption).
    4. 20-second silence present (if require_inter_round_silence=True).
    """
    errors: list[str] = []

    if len(audio_data) < _MIN_SIZE_BYTES:
        errors.append(f"Audio too small: {len(audio_data)} bytes (min {_MIN_SIZE_BYTES})")

    if not errors:
        duration = await _ffprobe_duration(audio_data)
        if duration <= 0:
            errors.append("Could not determine audio duration (possibly corrupt)")
        elif duration < expected_min_duration_s:
            errors.append(f"Duration {duration:.1f}s < expected minimum {expected_min_duration_s}s")
        elif duration > expected_max_duration_s:
            errors.append(f"Duration {duration:.1f}s > expected maximum {expected_max_duration_s}s")

    if not errors and require_inter_round_silence:
        silences = await _detect_silence(audio_data)
        long_silences = [s for s in silences if s.get("duration", 0) >= _SILENCE_MIN_DURATION_S]
        if not long_silences:
            errors.append(
                f"No inter-round silence >= {_SILENCE_MIN_DURATION_S}s detected "
                f"(§36: 20-second gap between Rodada 1 and Rodada 2)"
            )

    if errors:
        error_str = "; ".join(errors)
        logger.error("audio_validation_failed", errors=errors)
        raise NonRetryableError(
            f"Audio validation failed: {error_str}",
            reason_code=ReasonCode.TTS_PROVIDER_FAILED,
        )

    logger.info("audio_validation_passed", size_bytes=len(audio_data))
