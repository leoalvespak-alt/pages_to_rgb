package com.pagestoaudio.gateway.sync

import android.content.Context
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.pagestoaudio.gateway.camera.CaptureMode
import com.pagestoaudio.gateway.camera.SessionAwareCaptureSource
import com.pagestoaudio.gateway.domain.SessionRepository
import com.pagestoaudio.gateway.network.ApiService
import com.pagestoaudio.gateway.spool.SpoolRepository
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlin.coroutines.coroutineContext

/**
 * Worker opcional para long-polling de comandos do servidor (Etapa 5).
 *
 * Enquanto a sessão está CAPTURING:
 * ```
 * while (sessionActive) {
 *   val cmd = api.getCommand(sessionId, cursor, waitMs=25000, phase="CAPTURE")
 *   cursor = cmd.cursor
 *   when (cmd.command) {
 *     "CAPTURE_PROBE" -> captureSource.capture(mode=PROBE)
 *     "CAPTURE_FULL"  -> repeat(cmd.frames) { captureSource.capture(mode=FULL) ; upload() }
 *     "PAUSE"         -> pausePreview()
 *     "RESUME"        -> resumePreview()
 *     "PING"          -> heartbeat()
 *     "STOP"          -> spool.awaitDrain(); api.postEndSignal(); showResultPollingUI()
 *   }
 * }
 * ```
 *
 * Nota: WorkManager não deve abrir câmera em background — este worker apenas orquestra;
 * a captura efetiva deve ocorrer quando o app está em foreground (MainActivity).
 * Para simplificar a V1, o polling principal vive no SessionViewModel; este Worker
 * é fallback para manter cursor atualizado quando o app está em background com sessão ativa.
 */
class CommandPollWorker(
    appContext: Context,
    params: WorkerParameters,
    private val apiService: ApiService? = null,
    private val sessionRepository: SessionRepository? = null,
    private val captureSource: SessionAwareCaptureSource? = null,
    private val spoolRepository: SpoolRepository? = null
) : CoroutineWorker(appContext, params) {

    companion object {
        const val TAG = "CommandPollWorker"
        const val KEY_SESSION_ID = "session_id"
        const val KEY_CURSOR = "cursor"
        const val KEY_DEVICE_ID = "device_id"
    }

    override suspend fun doWork(): Result {
        val sessionId = inputData.getString(KEY_SESSION_ID) ?: return Result.failure()
        val deviceId = inputData.getString(KEY_DEVICE_ID) ?: return Result.failure()
        var cursor = inputData.getLong(KEY_CURSOR, 0L)

        val api = apiService ?: run {
            Log.w(TAG, "ApiService não injetado — polling via SessionRepository/ViewModel é o caminho principal")
            return Result.success()
        }

        Log.i(TAG, "CommandPoll start session=$sessionId cursor=$cursor")

        return try {
            // Loop leve — uma única iteração por execução do Worker; WorkManager re-agenda via PeriodicWork
            // Para long-polling contínuo em foreground, usar SessionViewModel.pollCommands() com wait_ms=25000
            val response = api.getCommand(sessionId, cursor, waitMs = 25000, phase = "CAPTURE")
            if (!response.isSuccessful) {
                Log.w(TAG, "getCommand falhou: ${response.code()} — retry")
                return Result.retry()
            }
            val cmd = response.body() ?: run {
                Log.w(TAG, "getCommand body nulo — retry")
                return Result.retry()
            }

            // S04.5: cursor avança SOMENTE após efeito; desconhecido nunca consome.
            Log.i(TAG, "Comando recebido: ${cmd.command} cursor=${cmd.cursor} captureId=${cmd.captureId} frames=${cmd.frames} gapMs=${cmd.gapMs}")

            var effectOk = true
            when (cmd.command) {
                "CAPTURE_PROBE" -> effectOk = handleCapture(cmd, CaptureMode.PROBE, sessionId)
                "CAPTURE_FULL" -> effectOk = handleCapture(cmd, CaptureMode.FULL, sessionId)
                "PAUSE" -> Log.i(TAG, "PAUSE — preview deve pausar (tratado no ViewModel)")
                "RESUME" -> Log.i(TAG, "RESUME — preview deve retomar")
                "PING" -> {
                    sessionRepository?.heartbeat(sessionId)
                    Log.d(TAG, "PING → heartbeat enviado")
                }
                "STOP" -> {
                    Log.i(TAG, "STOP recebido — drain com verificação antes do end-signal")
                    // S04.3/S04.4: só sinaliza após drain real; pendência mantém estado.
                    if (awaitSpoolDrain(sessionId)) {
                        val endRes = sessionRepository?.endSignal(sessionId)
                        effectOk = endRes?.isSuccess != false
                    } else {
                        Log.w(TAG, "STOP adiado: spool com pendências — sem end-signal")
                        effectOk = false
                    }
                }
                else -> {
                    Log.w(TAG, "Comando desconhecido: ${cmd.command} — cursor preservado")
                    effectOk = false
                }
            }
            if (effectOk) {
                try {
                    sessionRepository?.ackCommand(sessionId, cmd.cursor)
                } catch (e: Exception) {
                    Log.w(TAG, "ackCommand falhou cursor=${cmd.cursor}", e)
                }
                cursor = cmd.cursor
            }

            Result.success(
                androidx.work.Data.Builder()
                    .putLong(KEY_CURSOR, cursor)
                    .putString(KEY_SESSION_ID, sessionId)
                    .build()
            )
        } catch (e: CancellationException) {
            Log.i(TAG, "CommandPoll cancelado")
            Result.success()
        } catch (e: Exception) {
            Log.w(TAG, "CommandPoll erro — retry", e)
            Result.retry()
        }
    }

    private suspend fun handleCapture(
        cmd: com.pagestoaudio.gateway.network.CommandResponse,
        mode: CaptureMode,
        sessionId: String
    ): Boolean {
        val source = captureSource
        if (source == null) {
            Log.w(TAG, "CaptureSource não injetado — captura ignorada (deve ocorrer em foreground via ViewModel)")
            return false
        }
        val captureId = cmd.captureId ?: "cap-${System.currentTimeMillis()}-${mode.name.lowercase()}"
        val frames = cmd.frames.coerceIn(1, 10)
        val gapMs = cmd.gapMs.coerceIn(0, 5000)

        var allOk = true
        repeat(frames) { idx ->
            if (!coroutineContext.isActive) return false
            try {
                Log.i(TAG, "Capturando frame $idx/$frames mode=$mode captureId=$captureId")
                val captured = source.capture(mode, sessionId, captureId, idx)
                // Spool
                val pending = (source as? com.pagestoaudio.gateway.camera.PhoneCameraCaptureSource)
                    ?.toPendingFrame(captured, sessionId)
                if (pending != null) {
                    // S04.4: Result verificado — falha preserva pendência sem cursor.
                    val saveRes = spoolRepository?.save(pending)
                    if (saveRes?.isFailure == true) {
                        allOk = false
                        Log.e(TAG, "Spool save falhou frame $idx: ${saveRes.exceptionOrNull()?.message}")
                    }
                }
                if (idx < frames - 1 && gapMs > 0) {
                    delay(gapMs)
                }
            } catch (e: Exception) {
                allOk = false
                Log.e(TAG, "Falha ao capturar frame $idx", e)
            }
        }
        return allOk
    }

    private suspend fun awaitSpoolDrain(sessionId: String, timeoutMs: Long = 30_000): Boolean {
        val repo = spoolRepository ?: return false
        val start = System.currentTimeMillis()
        while (System.currentTimeMillis() - start < timeoutMs) {
            val pending = repo.pendingCountForSession(sessionId)
            if (pending == 0) {
                Log.i(TAG, "Spool drain completo para session $sessionId")
                return true
            }
            Log.d(TAG, "Spool drain aguardando: $pending pendentes")
            delay(1000)
        }
        Log.w(TAG, "Spool drain timeout após ${timeoutMs}ms — SEM end-signal com pendências")
        return false
    }
}
