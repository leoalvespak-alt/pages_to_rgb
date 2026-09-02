package com.pagestoaudio.gateway.spool

import android.content.Context
import android.util.Log
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.Data
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import com.pagestoaudio.gateway.sync.UploadWorker
import com.pagestoaudio.gateway.util.Sha256Util
import java.io.File
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.withContext

/**
 * Repositório de spool — coração da confiabilidade (Etapa 4).
 *
 * Ordem obrigatória (mesma do firmware: salvar antes de enviar):
 * 1. capturar JPEG (PhoneCameraCaptureSource → spool/{session}/{capture}_{idx}.jpg)
 * 2. salvar em armazenamento privado (getFilesDir()/spool/{session_id}/) — atomicamente
 * 3. calcular SHA-256 streaming (Sha256Util.sha256HexStreaming) — determinístico, não carrega 2x em RAM
 * 4. inserir em Room PendingFrame(session_id, capture_id, frame_index, sha256, path) —
 *    unique index (session_id, capture_id, frame_index) com OnConflictStrategy.ABORT
 * 5. enfileirar UploadWorker com WorkName "upload-{session}-{capture}-{index}" + KEEP
 * 6. POST /gateway/session/{id}/frame com headers X-Capture-Id, X-Frame-Index, X-SHA256,
 *    X-Resolution, X-Received-Android-At, X-Orientation (multipart JPEG)
 * 7. aguardar 2xx → markAck() → apagar arquivo SOMENTE após ACK; 409 → não retry; 5xx/408/429 → retry
 *
 * Responsabilidades:
 * - save(): persiste PendingFrame no Room (ABORT se violar unique index), verifica SHA streaming vs Room
 * - pending(): lista não-ACK
 * - markAck(): marca ACK e remove arquivo somente após ACK do servidor (ordem obrigatória)
 * - reenqueueAllPending(): ao reabrir o app ou após corte de rede, re-enfileira tudo não-ACK (idempotente → 200)
 */
class SpoolRepository(
    private val context: Context,
    private val dao: SpoolDao,
    private val workManager: WorkManager = WorkManager.getInstance(context)
) {
    companion object {
        private const val TAG = "SpoolRepository"
    }

    suspend fun save(frame: PendingFrame): Result<PendingFrame> = withContext(Dispatchers.IO) {
        try {
            // Validação explícita de unicidade antes do insert (mensagem de erro amigável)
            val existing = dao.findByCaptureFrame(frame.sessionId, frame.captureId, frame.frameIndex)
            if (existing != null) {
                if (existing.sha256 == frame.sha256) {
                    Log.i(TAG, "save: frame já existe com mesmo sha — idempotente session=${frame.sessionId} cap=${frame.captureId} idx=${frame.frameIndex}")
                    return@withContext Result.success(existing)
                } else {
                    // Mesmo capture_id+frame_index com sha diferente → 409 esperado no servidor
                    val msg = "Conflito: mesmo session/capture/frame_index com SHA diferente " +
                        "(existente=${existing.sha256} novo=${frame.sha256}) — criar novo capture_id"
                    Log.e(TAG, msg)
                    return@withContext Result.failure(IllegalStateException(msg))
                }
            }

            // Verificar arquivo existe antes de inserir
            val f = File(frame.filePath)
            if (!f.exists() || f.length() == 0L) {
                return@withContext Result.failure(IllegalStateException("Arquivo spool inexistente/vazio: ${frame.filePath}"))
            }
            // Verificação de integridade: recalcular SHA streaming e comparar com Room
            // (garante que arquivo não corrompeu entre captura e insert)
            try {
                val computed = Sha256Util.sha256HexStreaming(f)
                if (computed != frame.sha256) {
                    val msg = "SHA mismatch antes do insert: Room sha=${frame.sha256} computed=$computed — arquivo corrompido"
                    Log.e(TAG, msg)
                    return@withContext Result.failure(IllegalStateException(msg))
                }
            } catch (e: Exception) {
                Log.e(TAG, "Falha ao recalcular SHA antes do insert", e)
                return@withContext Result.failure(e)
            }

            dao.insert(frame)
            Log.i(TAG, "save ok: id=${frame.id} session=${frame.sessionId} cap=${frame.captureId} idx=${frame.frameIndex} sha=${frame.sha256.take(12)}...")

            // Enfileirar upload imediatamente (WorkManager cuidará de Constraints)
            enqueueUpload(frame)

            Result.success(frame)
        } catch (e: Exception) {
            Log.e(TAG, "save failed", e)
            Result.failure(e)
        }
    }

    suspend fun pending(): List<PendingFrame> = withContext(Dispatchers.IO) { dao.pending() }

    suspend fun pendingForSession(sessionId: String): List<PendingFrame> =
        withContext(Dispatchers.IO) { dao.pendingForSession(sessionId) }

    suspend fun pendingCount(): Int = withContext(Dispatchers.IO) { dao.pendingCount() }

    suspend fun pendingCountForSession(sessionId: String): Int =
        withContext(Dispatchers.IO) { dao.pendingCountForSession(sessionId) }

    fun pendingCountFlow(): Flow<Int> = dao.pendingCountFlow()
    fun pendingFlow(): Flow<List<PendingFrame>> = dao.pendingFlow()

    suspend fun lastForSession(sessionId: String): PendingFrame? =
        withContext(Dispatchers.IO) { dao.lastForSession(sessionId) }

    /**
     * Marca ACK no Room e apaga arquivo local SOMENTE após ACK (ordem obrigatória).
     * Retorna true se arquivo foi removido ou já não existia.
     */
    suspend fun markAck(id: String): Result<Boolean> = withContext(Dispatchers.IO) {
        try {
            val frame = dao.findById(id) ?: return@withContext Result.failure(NoSuchElementException("PendingFrame não encontrado: $id"))
            val updated = dao.markAck(id)
            if (updated == 0) {
                Log.w(TAG, "markAck: nenhuma linha afetada id=$id")
            }
            // Apagar arquivo SOMENTE após ACK confirmado
            val file = File(frame.filePath)
            var deleted = true
            if (file.exists()) {
                deleted = file.delete()
                if (!deleted) {
                    Log.w(TAG, "markAck: ACK ok mas falha ao apagar arquivo ${file.absolutePath} — será limpo em prune()")
                } else {
                    Log.i(TAG, "markAck + delete ok: ${frame.captureId}/${frame.frameIndex} sha=${frame.sha256.take(12)}...")
                }
            }
            Result.success(deleted)
        } catch (e: Exception) {
            Log.e(TAG, "markAck failed id=$id", e)
            Result.failure(e)
        }
    }

    suspend fun incrementAttempts(id: String) = withContext(Dispatchers.IO) { dao.incrementAttempts(id) }

    /**
     * Enfileira UploadWorker com Constraints(NETWORK_CONNECTED) + Backoff EXPONENTIAL.
     * Idempotente: mesmo workName por frame (ExistingWorkPolicy.KEEP — não duplica).
     */
    fun enqueueUpload(frame: PendingFrame) {
        val input = Data.Builder()
            .putString(UploadWorker.KEY_FRAME_ID, frame.id)
            .putString(UploadWorker.KEY_SESSION_ID, frame.sessionId)
            .build()

        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()

        val request = OneTimeWorkRequestBuilder<UploadWorker>()
            .setInputData(input)
            .setConstraints(constraints)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 5, TimeUnit.SECONDS)
            .addTag("upload")
            .addTag("session:${frame.sessionId}")
            .build()

        // WorkName único por frame garante idempotência de enfileiramento
        val workName = "upload-${frame.sessionId}-${frame.captureId}-${frame.frameIndex}"
        workManager.enqueueUniqueWork(workName, ExistingWorkPolicy.KEEP, request)
        Log.d(TAG, "enqueueUpload: $workName pendingId=${frame.id}")
    }

    /**
     * Ao reabrir o app, re-enfileira tudo não-ACK. Reenvio com mesmo
     * session_id+capture_id+frame_index+sha256 → servidor 200 idempotente.
     */
    suspend fun reenqueueAllPending(): Int = withContext(Dispatchers.IO) {
        val pendings = dao.pending()
        pendings.forEach { enqueueUpload(it) }
        if (pendings.isNotEmpty()) {
            Log.i(TAG, "reenqueueAllPending: ${pendings.size} frames re-enfileirados")
        }
        pendings.size
    }

    suspend fun reenqueuePendingForSession(sessionId: String): Int = withContext(Dispatchers.IO) {
        val pendings = dao.pendingForSession(sessionId)
        pendings.forEach { enqueueUpload(it) }
        pendings.size
    }

    suspend fun pruneAckedOlderThan(days: Int = 7): Int = withContext(Dispatchers.IO) {
        val before = System.currentTimeMillis() - TimeUnit.DAYS.toMillis(days.toLong())
        dao.pruneAcked(before)
    }
}
