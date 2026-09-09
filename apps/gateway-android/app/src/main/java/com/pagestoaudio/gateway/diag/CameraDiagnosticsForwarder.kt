package com.pagestoaudio.gateway.diag

import android.util.Log
import com.pagestoaudio.gateway.spool.PendingFrame
import com.pagestoaudio.gateway.spool.SpoolRepository
import com.pagestoaudio.gateway.util.Sha256Util
import java.io.File
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

/**
 * D02/D04 — forwarder de diagnóstico ESP → cloud.
 *
 * - Foto/clipe: usa a fila durável existente (SpoolRepository) com
 *   sessionId="diag:{diagnosticId}" e sessionType="DIAG" (tipo/quota próprios,
 *   sem segunda implementação de spool). Preserva bytes/hash/identidade;
 *   nenhuma falha gera crescimento ilimitado (quota + MAX_ATTEMPTS).
 * - Prévia: caminho transitório — 1 upload em voo + 1 frame mais recente
 *   aguardando; intermediárias descartadas; sem retry indefinido; nunca usa
 *   spool de missão.
 * - Encerramento: prazo local, STOP explícito, perda de autorização
 *   (30 s sem heartbeat). Recuperação pós-reboot: re-enfileira só pendências
 *   duráveis de foto/clipe; nunca reinicia câmera sozinho.
 */
class CameraDiagnosticsForwarder(
    private val spool: SpoolRepository,
    private val filesDir: File,
    private val scope: CoroutineScope,
    private val cloud: DiagCloudBridge,
) {
    interface DiagCloudBridge {
        suspend fun claim(diagnosticId: String): Boolean
        suspend fun uploadFrame(
            diagnosticId: String, frameIndex: Int, sha: String, file: File,
            capturedMonoMs: Long, width: Int, height: Int,
        ): CloudAck
        suspend fun uploadPreview(
            diagnosticId: String, frameIndex: Int, sha: String, file: File,
            capturedMonoMs: Long, width: Int, height: Int,
        ): CloudAck
        suspend fun event(diagnosticId: String, event: String, reason: String?): Boolean
        suspend fun ack(diagnosticId: String): Boolean
    }

    data class CloudAck(val accepted: Boolean, val duplicate: Boolean)

    companion object {
        private const val TAG = "DiagFwd"
    }

    private val mutex = Mutex()
    private var state = DiagState()
    private var stopJob: Job? = null

    // Prévia: último frame aguardando (índice único) + contador em voo.
    private var previewPending: PendingPreview? = null
    private val previewInFlight = AtomicInteger(0)

    private data class PendingPreview(
        val frameIndex: Int, val sha: String, val file: File,
        val capturedMonoMs: Long, val width: Int, val height: Int,
    )

    suspend fun start(req: DiagRequest): Boolean = mutex.withLock {
        if (!DiagConfig.diagnosticsEnabled) {
            Log.w(TAG, "diagnóstico desligado por flag")
            return false
        }
        if (state.active) {
            Log.w(TAG, "já há diagnóstico ativo ${state.request?.diagnosticId}")
            return false
        }
        val claimed = try { withContext(Dispatchers.IO) { cloud.claim(req.diagnosticId) } }
        catch (e: Exception) {
            Log.w(TAG, "claim falhou", e)
            false
        }
        // Do not expose an ACTIVE local stream until the cloud lease exists.
        if (!claimed) return false
        state = DiagState(active = true, request = req, lastHeartbeatMs = System.currentTimeMillis())
        stopJob?.cancel()
        stopJob = scope.launch {
            val wait = (req.deadlineMs - System.currentTimeMillis()).coerceAtLeast(0L)
            delay(wait)
            stop("deadline")
        }
        Log.i(TAG, "diagnóstico iniciado ${req.diagnosticId} modo=${req.mode}")
        true
    }

    suspend fun heartbeat(diagnosticId: String): Boolean = mutex.withLock {
        val req = state.request
        if (!state.active || req?.diagnosticId != diagnosticId) return false
        state = state.copy(lastHeartbeatMs = System.currentTimeMillis())
        true
    }

    /** Chamado pelo loop de supervisão (10 s): expira sem renovação em 30 s. */
    suspend fun checkAuthz(): Boolean = mutex.withLock {
        val req = state.request ?: return false
        if (!state.active) return false
        val idle = System.currentTimeMillis() - state.lastHeartbeatMs
        if (idle > DiagConfig.AUTHZ_TTL_S * 1000L) {
            Log.w(TAG, "autorização expirada ${req.diagnosticId} idle=${idle}ms")
            scope.launch { stopLocked("authz-expired") }
            return false
        }
        true
    }

    suspend fun stop(reason: String): Boolean = mutex.withLock { stopLocked(reason) }

    private suspend fun stopLocked(reason: String): Boolean {
        val req = state.request ?: return false.also { state = DiagState() }
        state = state.copy(active = false)
        stopJob?.cancel()
        stopJob = null
        previewPending = null
        return try {
            withContext(Dispatchers.IO) { cloud.event(req.diagnosticId, "STOPPED", reason) }
            withContext(Dispatchers.IO) { cloud.ack(req.diagnosticId) }
            Log.i(TAG, "diagnóstico ${req.diagnosticId} encerrado: $reason")
            state = DiagState()
            true
        } catch (e: Exception) {
            Log.w(TAG, "stop cloud falhou", e)
            state = DiagState()
            false
        }
    }

    fun isActive(diagnosticId: String? = null): Boolean {
        val s = state
        if (!s.active) return false
        if (diagnosticId != null && s.request?.diagnosticId != diagnosticId) return false
        return System.currentTimeMillis() <= (s.request?.deadlineMs ?: 0L)
    }

    fun activeRequest(): DiagRequest? = state.request?.takeIf { isActive(it.diagnosticId) }

    /**
     * Recebe JPEG bruto da ESP (bytes já validados no handler local).
     * Foto/clipe → fila durável; prévia → buffer limitado transitório.
     * Retorna HTTP local: 201 novo, 208 duplicata, 409 conflito, 413 quota.
     */
    suspend fun onDeviceFrame(
        diagnosticId: String, frameIndex: Int, sha: String, bytes: ByteArray,
        capturedMonoMs: Long, width: Int, height: Int,
    ): Int {
        val req = mutex.withLock { state.request }
        if (!isActive(diagnosticId) || req == null) return 409
        if (req.mode == DiagMode.PREVIEW) return onPreviewFrame(req, frameIndex, sha, bytes, capturedMonoMs, width, height)
        return onDurableFrame(req, frameIndex, sha, bytes, capturedMonoMs, width, height)
    }

    private suspend fun onDurableFrame(
        req: DiagRequest, frameIndex: Int, sha: String, bytes: ByteArray,
        capturedMonoMs: Long, width: Int, height: Int,
    ): Int {
        if (bytes.size > 2 * 1024 * 1024) return 413
        val dir = File(filesDir, "diag_spool/${req.diagnosticId}").apply { mkdirs() }
        val target = File(dir, "diag_${req.diagnosticId}_${frameIndex}.jpg")
        if (target.exists()) {
            val existing = try { Sha256Util.sha256HexStreaming(target) } catch (_: Exception) { "" }
            if (existing.equals(sha, ignoreCase = true)) return 208
            return 409
        }
        val written = spool.writeAtomically(target, bytes)
        if (written.isFailure) return 500
        val computed = try { Sha256Util.sha256HexStreaming(target) } catch (_: Exception) {
            target.delete(); return 500
        }
        if (!computed.equals(sha, ignoreCase = true)) {
            target.delete(); return 409
        }
        // Quota própria de diagnóstico (sem tocar spool de missão).
        val quota = diagQuota(req.diagnosticId)
        if (!quota.canAccept(bytes.size.toLong())) {
            target.delete()
            Log.w(TAG, "quota de diagnóstico excedida ${req.diagnosticId}")
            return 413
        }
        val frame = PendingFrame(
            sessionId = "diag:${req.diagnosticId}",
            captureId = "diag:${req.diagnosticId}",
            frameIndex = frameIndex,
            sha256 = computed,
            filePath = target.absolutePath,
            resolution = "${width}x${height}",
            orientation = 0,
            createdAt = System.currentTimeMillis(),
            sessionType = "DIAG",
            width = width,
            height = height,
        )
        val saved = spool.save(frame)
        if (saved.isFailure) return 500
        if (false) {
            var ok = false
            var attempt = 0
            while (!ok && attempt < DiagConfig.DIAG_MAX_ATTEMPTS && isActive(req.diagnosticId)) {
                try {
                    // Teto de tentativas (sem retry infinito); 409 do cloud não repete.
                    val ack = cloud.uploadFrame(req.diagnosticId, frameIndex, computed, target, capturedMonoMs, width, height)
                    ok = ack.accepted
                    if (ok) spool.markAck(frame.id)
                } catch (e: Exception) {
                    Log.w(TAG, "upload diag tentativa $attempt falhou", e)
                }
                attempt++
                if (!ok) delay(2000L * attempt)
            }
        }
        return 201
    }

    private suspend fun onPreviewFrame(
        req: DiagRequest, frameIndex: Int, sha: String, bytes: ByteArray,
        capturedMonoMs: Long, width: Int, height: Int,
    ): Int {
        // Buffer limitado: 1 em voo + 1 aguardando; descarta intermediárias.
        if (previewInFlight.get() >= DiagConfig.PREVIEW_IN_FLIGHT_MAX) {
            val dropped = mutex.withLock {
                val had = previewPending != null
                val dir = File(filesDir, "diag_preview/${req.diagnosticId}").apply { mkdirs() }
                val target = File(dir, "preview_latest.jpg")
                target.writeBytes(bytes)
                previewPending = PendingPreview(frameIndex, sha, target, capturedMonoMs, width, height)
                if (had) state = state.copy(queuedPreviewDropped = state.queuedPreviewDropped + 1)
                had
            }
            Log.d(TAG, "prévia: intermediária descartada (dropped=$dropped)")
            return 202
        }
        previewInFlight.incrementAndGet()
        scope.launch(Dispatchers.IO) {
            try {
                val dir = File(filesDir, "diag_preview/${req.diagnosticId}").apply { mkdirs() }
                val target = File(dir, "preview_latest.jpg")
                target.writeBytes(bytes)
                try { cloud.uploadPreview(req.diagnosticId, frameIndex, sha, target, capturedMonoMs, width, height) } catch (e: Exception) {
                    Log.w(TAG, "prévia upload falhou (sem retry infinito)", e)
                }
            } finally {
                previewInFlight.decrementAndGet()
                // Se há um mais recente aguardando, envia só ele (não a fila).
                val next = mutex.withLock { val n = previewPending; previewPending = null; n }
                if (next != null && isActive(req.diagnosticId)) {
                    onPreviewFrame(req, next.frameIndex, next.sha, next.file.readBytes(), next.capturedMonoMs, next.width, next.height)
                }
            }
        }
        return 201
    }

    private suspend fun diagQuota(diagnosticId: String): DiagQuota {
        val pendings = try { spool.pending() } catch (_: Exception) { emptyList() }
        val mine = pendings.filter { it.sessionId == "diag:$diagnosticId" }
        var bytes = 0L
        mine.forEach { bytes += try { File(it.filePath).length() } catch (_: Exception) { 0L } }
        return DiagQuota(mine.size, bytes)
    }

    /** Pós-reboot: re-enfileira só pendências duráveis de diagnóstico (sem reiniciar câmera). */
    suspend fun recoverDurable(): Int {
        return try {
            val pendings = spool.pending()
            val mine = pendings.filter { it.sessionId.startsWith("diag:") && it.sessionType == "DIAG" }
            mine.forEach { spool.enqueueUpload(it) }
            if (mine.isNotEmpty()) Log.i(TAG, "recoverDurable: ${mine.size} pendências de diagnóstico re-enfileiradas")
            mine.size
        } catch (e: Exception) {
            Log.w(TAG, "recoverDurable falhou", e)
            0
        }
    }
}
