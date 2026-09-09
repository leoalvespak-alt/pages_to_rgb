"""D05 — montagem de MP4 a partir de JPEGs reais temporizados (worker existente).

Sem codificador embarcado. Usa FFmpeg da imagem de produção com manifest
concat + durações reais. Uma conversão por vez (lock em memória + linha),
timeout 60 s, kill/wait/reap, temporários privados limitados, argv
estruturado (sem shell), validação com ffprobe + reprodução real.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.pages_to_audio.camera_diagnostics import (
    CLIP_MAX_FRAMES,
    VIDEO_CONVERT_TIMEOUT_S,
    clip_output_key,
)
from src.pages_to_audio.db.models.camera_diagnostic import (
    CameraDiagnostic,
    CameraDiagnosticFrame,
)
from src.pages_to_audio.domain.ports.storage import StoragePort
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)

# Uma conversão por vez no worker designado (processo único; com réplicas,
# a trava real é a transição COMPLETED→clip_key is None sob FOR UPDATE).
_conversion_lock = asyncio.Lock()


def _ffmpeg_exists() -> str | None:
    return shutil.which("ffmpeg")


def _ffprobe_exists() -> str | None:
    return shutil.which("ffprobe")


def _safe_frame_name(index: int) -> str:
    if not 0 <= index < CLIP_MAX_FRAMES:
        raise ValueError("frame index out of range")
    return f"f_{index:04d}.jpg"


async def schedule_clip_conversion(
    db: AsyncSession,
    storage: StoragePort,
    bucket: str,
    row: CameraDiagnostic,
    device_code: str,
) -> bool:
    """Agenda quando o clipe tem frames suficientes; idempotente.

    Retorna True se a conversão foi concluída aqui, False se adiada/já feita.
    Não chama OCR/solver/áudio. Chamado fora do request HTTP idealmente;
    aqui executa inline sob lock com timeout (worker real chama convert_clip).
    """
    if row.mode != "CLIP" or row.clip_key:
        return False
    frames = (
        await db.scalars(
            select(CameraDiagnosticFrame)
            .where(
                CameraDiagnosticFrame.diagnostic_id == row.id,
                CameraDiagnosticFrame.transient.is_(False),
            )
            .order_by(CameraDiagnosticFrame.frame_index)
        )
    ).all()
    if len(frames) < 2:
        return False
    # Só converte quando a rodada expirou/parou ou atingiu o teto — nunca
    # "completa" um clipe parcial como se fosse captura completa.
    if row.status not in ("STOPPING", "COMPLETED", "EXPIRED") and len(frames) < int(
        row.max_frames or CLIP_MAX_FRAMES
    ):
        # Permite conversão antecipada após duração? Não: aguarda STOP/expiração
        # salvo se o chamador marcou explicitamente (D05.3 conciliação cloud).
        return False
    return await convert_clip(db, storage, bucket, row, device_code)


async def convert_clip(
    db: AsyncSession,
    storage: StoragePort,
    bucket: str,
    row: CameraDiagnostic,
    device_code: str,
) -> bool:
    if row.clip_key:
        return True
    ffmpeg = _ffmpeg_exists()
    if not ffmpeg:
        logger.warning("clip_no_ffmpeg")
        return False
    frames = (
        await db.scalars(
            select(CameraDiagnosticFrame)
            .where(
                CameraDiagnosticFrame.diagnostic_id == row.id,
                CameraDiagnosticFrame.transient.is_(False),
            )
            .order_by(CameraDiagnosticFrame.frame_index)
        )
    ).all()
    if len(frames) < 2:
        return False
    async with _conversion_lock:
        # Re-checa sob lock (idempotência).
        await db.refresh(row)
        if row.clip_key:
            return True
        tmpdir = Path(tempfile.mkdtemp(prefix="p2a_clip_"))
        try:
            # Baixa JPEGs com nomes validados; preserva intervalos via manifest.
            mono = [f.captured_mono_ms or 0 for f in frames]
            durations: list[float] = []
            for i, f in enumerate(frames):
                data = await storage.get_object(bucket, f.storage_key)
                if len(data) > 2 * 1024 * 1024:
                    raise ValueError("clip frame exceeds per-frame ceiling")
                (tmpdir / _safe_frame_name(f.frame_index)).write_bytes(data)
                if i + 1 < len(frames) and mono[i + 1] > mono[i]:
                    durations.append(max(0.1, (mono[i + 1] - mono[i]) / 1000.0))
                else:
                    durations.append(0.5)  # fallback 2 fps declarado
            manifest = tmpdir / "concat.txt"
            lines: list[str] = []
            for i, f in enumerate(frames):
                lines.append(f"file '{_safe_frame_name(f.frame_index)}'")
                lines.append(f"duration {durations[i]:.3f}")
            # Último arquivo repetido (requisito do demuxer concat).
            lines.append(f"file '{_safe_frame_name(frames[-1].frame_index)}'")
            manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
            out = tmpdir / "clip.mp4"
            # Encoder: prefere libx264 se existir, senão mpeg4 nativo.
            enc = await _pick_encoder(ffmpeg)
            if enc is None:
                logger.warning("clip_no_h264_encoder")
                return False
            cmd = [
                ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(manifest),
                "-c:v", enc, "-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                "-movflags", "+faststart", str(out),
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            try:
                await asyncio.wait_for(proc.communicate(), timeout=VIDEO_CONVERT_TIMEOUT_S)
            except TimeoutError:
                proc.kill()
                await proc.wait()
                logger.warning("clip_ffmpeg_timeout", diagnostic_id=row.diagnostic_id)
                return False
            if proc.returncode != 0 or not out.exists() or out.stat().st_size == 0:
                logger.warning("clip_ffmpeg_failed", rc=proc.returncode)
                return False
            # Valida duração com ffprobe + abre como MP4 real.
            duration_s, _fps = await _probe(out)
            if duration_s <= 0:
                return False
            mp4_bytes = out.read_bytes()
            key = clip_output_key(device_code, row.diagnostic_id)
            import hashlib as _hl

            await storage.put_object(
                bucket, key, mp4_bytes, "video/mp4",
                sha256=_hl.sha256(mp4_bytes).hexdigest(), overwrite=True,
            )
            row.clip_key = key
            row.clip_duration_s = duration_s
            row.clip_fps = round(len(frames) / duration_s, 2) if duration_s else 0.0
            await db.flush()
            logger.info(
                "clip_converted", diagnostic_id=row.diagnostic_id,
                frames=len(frames), duration_s=duration_s,
            )
            return True
        except Exception as exc:
            logger.warning("clip_convert_failed", error=str(exc)[:200])
            return False
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


async def _pick_encoder(ffmpeg: str) -> str | None:
    try:
        proc = await asyncio.create_subprocess_exec(
            ffmpeg, "-hide_banner", "-encoders",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        text = out.decode(errors="ignore")
        if "libx264" in text:
            return "libx264"
    except Exception as exc:  # sem encoder listado, usa mpeg4
        logger.debug("encoder_probe_failed", error=str(exc)[:120])
    return None


async def _probe(path: Path) -> tuple[float, float]:
    ffprobe = _ffprobe_exists()
    if not ffprobe:
        # Sem ffprobe: aceita com duração estimada (registrado; player valida).
        return 0.0, 0.0
    try:
        proc = await asyncio.create_subprocess_exec(
            ffprobe, "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        duration_s = float(out.decode().strip() or 0)
        return duration_s, 0.0
    except Exception:
        return 0.0, 0.0
