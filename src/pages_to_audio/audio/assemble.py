"""Audio assembly — §36, §9.4.

Each speech segment is synthesized via TTS.
Silence segments are WAV PCM silence files.
All segments are concatenated with FFmpeg (concat demuxer).

Rules (§9.4):
- Silence is physical (not SSML) — generated as WAV, then concatenated (§9.4.2).
- FFmpeg timeout: 120s (§9.4.3, §42).
- FFmpeg executed without shell=True (no shell injection).
- Temp files managed under TempManager — cleaned in finally (§9.4.5).
- §17: no image written permanently to local disk.
"""

from __future__ import annotations

import asyncio
import hashlib
import struct
import tempfile
from pathlib import Path

from src.pages_to_audio.audio.plan import AudioPlan, SilenceSegment, SpeechSegment
from src.pages_to_audio.common.errors import NonRetryableError, ReasonCode
from src.pages_to_audio.domain.ports.tts import TTSProvider, TTSRequest, TTSSegment
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)

_FFMPEG_TIMEOUT_S = 120.0
_SAMPLE_RATE = 44100
_CHANNELS = 2
_BITS = 16


def _make_silence_wav(duration_seconds: float) -> bytes:
    """Generate WAV silence file for physical gap insertion (§9.4.2)."""
    num_samples = int(_SAMPLE_RATE * duration_seconds)
    pcm = b"\x00" * (num_samples * _CHANNELS * (_BITS // 8))
    data_size = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        _CHANNELS,
        _SAMPLE_RATE,
        _SAMPLE_RATE * _CHANNELS * (_BITS // 8),
        _CHANNELS * (_BITS // 8),
        _BITS,
        b"data",
        data_size,
    )
    return header + pcm


async def _synthesize_speech(
    segment: SpeechSegment,
    provider: TTSProvider,
) -> TTSSegment:
    request = TTSRequest(
        text=segment.text,
        language_code="pt-BR",
        speaking_rate=segment.speaking_rate,
    )
    return await provider.synthesize(request)


async def _run_ffmpeg(args: list[str]) -> bytes:
    """Execute FFmpeg, return stdout bytes. §9.4.3: no shell=True, 120s timeout."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_FFMPEG_TIMEOUT_S)
    except TimeoutError as exc:
        raise NonRetryableError(
            f"FFmpeg timed out after {_FFMPEG_TIMEOUT_S}s",
            reason_code=ReasonCode.TTS_PROVIDER_FAILED,
        ) from exc
    except FileNotFoundError as exc:
        raise NonRetryableError(
            "ffmpeg not found in PATH",
            reason_code=ReasonCode.TTS_PROVIDER_FAILED,
        ) from exc

    if proc.returncode != 0:
        raise NonRetryableError(
            f"FFmpeg failed (exit {proc.returncode}): {stderr.decode(errors='replace')[:500]}",
            reason_code=ReasonCode.TTS_PROVIDER_FAILED,
        )
    return stdout


async def assemble_audio(
    plan: AudioPlan,
    tts_provider: TTSProvider,
    *,
    output_format: str = "mp3",
) -> bytes:
    """Synthesize all segments and concatenate with FFmpeg.

    Returns final audio bytes. Temp directory is cleaned in finally.
    §9.4.5: all temp files cleaned even on error.
    """
    with tempfile.TemporaryDirectory(prefix="pta_audio_") as tmp_dir:
        tmp = Path(tmp_dir)
        segment_files: list[Path] = []

        for idx, seg in enumerate(plan.segments):
            if isinstance(seg, SpeechSegment):
                tts_result = await _synthesize_speech(seg, tts_provider)
                seg_path = tmp / f"seg_{idx:04d}.mp3"
                seg_path.write_bytes(tts_result.audio_data)
            elif isinstance(seg, SilenceSegment):
                silence_wav = _make_silence_wav(seg.duration_seconds)
                seg_path = tmp / f"seg_{idx:04d}.wav"
                seg_path.write_bytes(silence_wav)
            else:
                continue
            segment_files.append(seg_path)

        if not segment_files:
            raise NonRetryableError(
                "No segments to assemble",
                reason_code=ReasonCode.TTS_PROVIDER_FAILED,
            )

        concat_list = tmp / "concat.txt"
        concat_list.write_text(
            "\n".join(f"file '{p}'" for p in segment_files),
            encoding="utf-8",
        )

        output_path = tmp / f"output.{output_format}"
        ffmpeg_args = [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c:a",
            "libmp3lame" if output_format == "mp3" else "copy",
            "-q:a",
            "2",
            "-y",
            str(output_path),
        ]
        await _run_ffmpeg(ffmpeg_args)

        result = output_path.read_bytes()
        sha256 = hashlib.sha256(result).hexdigest()
        logger.info(
            "audio_assembled",
            format=output_format,
            size_bytes=len(result),
            sha256=sha256[:16],
            segment_count=len(segment_files),
        )
        return result
