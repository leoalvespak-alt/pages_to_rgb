package com.pagestoaudio.gateway.sync

import android.content.Context
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.pagestoaudio.gateway.network.ApiService
import com.pagestoaudio.gateway.spool.AppDatabase
import com.pagestoaudio.gateway.util.Sha256Util
import java.io.File
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.asRequestBody
import org.json.JSONObject

/**
 * WorkManager — Upload idempotente com retry exponencial (Etapa 4).
 *
 * Constraints: NETWORK_CONNECTED
 * Backoff: EXPONENTIAL (5s → 5min)
 * Headers obrigatórios: X-Capture-Id, X-Frame-Index, X-SHA256, X-Resolution, X-Received-Android-At, X-Orientation
 *
 * Ordem: POST → aguardar 2xx → markAck → apagar somente após ACK.
 * Reenvio com mesmo session_id+capture_id+frame_index+sha256 → 200 idempotente.
 * Mesmo capture_id+frame_index com sha diferente → 409 CONFLICT → não marcar ACK, logar crítico.
 */
class UploadWorker(
    appContext: Context,
    params: WorkerParameters,
    private val apiService: ApiService? = null, // injetado via WorkerFactory em app real
    private val database: AppDatabase? = null
) : CoroutineWorker(appContext, params) {

    companion object {
        const val TAG = "UploadWorker"
        const val KEY_FRAME_ID = "frame_id"
        const val KEY_SESSION_ID = "session_id"
        private val MEDIA_JPEG = "image/jpeg".toMediaType()
    }

    override suspend fun doWork(): Result {
        val frameId = inputData.getString(KEY_FRAME_ID)
            ?: return Result.failure(errorData("missing frame_id"))

        val db = database ?: AppDatabase.getInstance(applicationContext)
        val dao = db.spoolDao()
        val frame = dao.findById(frameId)
            ?: run {
                Log.w(TAG, "Frame não encontrado no Room — possivelmente já ACK e limpo. id=$frameId")
                return Result.success() // idempotente: já não há o que enviar
            }

        if (frame.ack) {
            Log.i(TAG, "Frame já ACK — skip upload id=${frame.id} cap=${frame.captureId} idx=${frame.frameIndex}")
            return Result.success()
        }

        val file = File(frame.filePath)
        if (!file.exists() || file.length() == 0L) {
            Log.e(TAG, "Arquivo spool inexistente/vazio: ${frame.filePath} id=${frame.id}")
            // Falha permanente — não adianta retry sem arquivo
            return Result.failure(errorData("file missing: ${frame.filePath}"))
        }

        // Recalcular SHA-256 via streaming para garantir integridade antes do envio
        val computedSha = try {
            Sha256Util.sha256HexStreaming(file)
        } catch (e: Exception) {
            Log.e(TAG, "Falha ao calcular SHA-256", e)
            return Result.retry()
        }

        if (computedSha != frame.sha256) {
            Log.e(TAG, "SHA mismatch! Room sha=${frame.sha256} computed=$computedSha id=${frame.id} — falha permanente")
            return Result.failure(errorData("sha mismatch room=${frame.sha256} computed=$computedSha"))
        }

        val api = apiService ?: run {
            Log.e(TAG, "ApiService não injetado — retry. Configure WorkerFactory com ApiService.")
            return Result.retry()
        }

        return try {
            val receivedAt = java.time.Instant.now().toString() // ISO-8601 para X-Received-Android-At
            val body = file.asRequestBody(MEDIA_JPEG)
            val part = okhttp3.MultipartBody.Part.createFormData("file", file.name, body)

            Log.i(TAG, "Enviando frame session=${frame.sessionId} cap=${frame.captureId} idx=${frame.frameIndex} sha=${frame.sha256.take(12)}... res=${frame.resolution} orient=${frame.orientation}")

            val response = if (frame.sessionType == "HANDWRITTEN_WORD") {
                api.uploadHandwrittenFrame(
                    sessionId = frame.sessionId,
                    captureId = frame.captureId,
                    frameIndex = frame.frameIndex,
                    sha256 = frame.sha256,
                    resolution = frame.resolution,
                    receivedAt = receivedAt,
                    orientation = frame.orientation,
                    file = part
                )
            } else {
                api.uploadFrame(
                    sessionId = frame.sessionId,
                    captureId = frame.captureId,
                    frameIndex = frame.frameIndex,
                    sha256 = frame.sha256,
                    resolution = frame.resolution,
                    receivedAt = receivedAt,
                    orientation = frame.orientation,
                    file = part
                )
            }

            when {
                response.isSuccessful -> {
                    val bodyResp = response.body()
                    Log.i(TAG, "Upload 2xx ok duplicate=${bodyResp?.duplicate} storage_key=${bodyResp?.storageKey} id=${frame.id}")
                    dao.markAck(frame.id)
                    // Apagar arquivo SOMENTE após ACK confirmado (ordem obrigatória)
                    if (file.exists()) {
                        val deleted = file.delete()
                        Log.i(TAG, "Arquivo spool removido após ACK: deleted=$deleted path=${file.absolutePath}")
                    }
                    Result.success()
                }
                response.code() == 409 -> {
                    // Conflito: mesmo capture_id+frame_index com sha diferente
                    val errBody = response.errorBody()?.string()
                    Log.e(TAG, "Upload 409 CONFLICT — mesmo capture/frame com SHA diferente id=${frame.id} body=$errBody — requer novo capture_id (não retry)")
                    dao.incrementAttempts(frame.id)
                    Result.failure(errorData("409 conflict: $errBody"))
                }
                response.code() in 400..499 && response.code() != 408 && response.code() != 429 -> {
                    // Erro cliente não-retriável (exceto timeout/rate-limit)
                    val errBody = try { response.errorBody()?.string() } catch (_: Exception) { null }
                    Log.e(TAG, "Upload erro cliente ${response.code()} id=${frame.id} body=$errBody")
                    dao.incrementAttempts(frame.id)
                    Result.failure(errorData("client error ${response.code()}: $errBody"))
                }
                else -> {
                    // 5xx ou 408/429 → retry com backoff exponencial
                    val errBody = try { response.errorBody()?.string() } catch (_: Exception) { null }
                    Log.w(TAG, "Upload erro transitório ${response.code()} id=${frame.id} body=$errBody — retry com backoff")
                    dao.incrementAttempts(frame.id)
                    Result.retry()
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "Upload exceção (rede?) id=${frame.id} — retry", e)
            try { dao.incrementAttempts(frame.id) } catch (_: Exception) {}
            Result.retry()
        }
    }

    private fun errorData(message: String): androidx.work.Data {
        return androidx.work.Data.Builder()
            .putString("error", message)
            .build()
    }
}
