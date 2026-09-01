package com.pagestoaudio.gateway.domain

import android.util.Log
import com.pagestoaudio.gateway.network.ApiService
import com.pagestoaudio.gateway.network.EndSignalRequest
import com.pagestoaudio.gateway.network.HandwrittenStartRequest
import com.pagestoaudio.gateway.network.HeartbeatRequest
import com.pagestoaudio.gateway.network.StartSessionRequest
import com.pagestoaudio.gateway.spool.SessionHistoryDao
import com.pagestoaudio.gateway.spool.SessionHistoryEntity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Repositório de sessão — orquestra ciclo de vida da sessão no servidor.
 *
 * Responsável por: hello → startSession (com capture_source=ANDROID_CAMERA) → heartbeat → endSignal.
 * Respeita regra allow_new_session=false só retoma (ANDROID_GATEWAY_CONTRACT.md:55).
 */
class SessionRepository(
    private val api: ApiService,
    private val deviceId: String,
    private val deviceSecret: String? = null
    , private val historyDao: SessionHistoryDao? = null
) {
    companion object {
        private const val TAG = "SessionRepository"
    }

    data class SessionState(
        val sessionId: String,
        val cursor: Long = 0,
        val resumed: Boolean = false,
        val status: String? = null
    )

    sealed class SessionResult {
        data class Success(val state: SessionState) : SessionResult()
        data class Error(val message: String, val cause: Throwable? = null, val code: Int? = null) : SessionResult()
    }

    suspend fun startSession(
        allowNewSession: Boolean = true,
        resumeHint: String? = null,
        lastSessionId: String? = null
    ): SessionResult = withContext(Dispatchers.IO) {
        try {
            val req = StartSessionRequest(
                deviceCode = deviceId,
                captureSource = "ANDROID_CAMERA",
                allowNewSession = allowNewSession,
                resumeHint = resumeHint,
                gatewayCode = deviceId,
                lastSessionId = lastSessionId
            )
            val resp = api.startSession(req)
            if (resp.isSuccessful) {
                val body = resp.body()!!
                val state = SessionState(
                    sessionId = body.sessionId,
                    cursor = body.cursor,
                    resumed = body.resumed,
                    status = body.status
                )
                Log.i(TAG, "startSession ok: session=${state.sessionId} resumed=${state.resumed} cursor=${state.cursor}")
                historyDao?.upsert(SessionHistoryEntity(state.sessionId, "EXAM", System.currentTimeMillis(), status = state.status ?: "STARTED"))
                SessionResult.Success(state)
            } else {
                val err = resp.errorBody()?.string()
                Log.e(TAG, "startSession falhou: ${resp.code()} $err")
                SessionResult.Error("Falha ao iniciar sessão: ${resp.code()} $err", code = resp.code())
            }
        } catch (e: Exception) {
            Log.e(TAG, "startSession exceção", e)
            SessionResult.Error("Erro de rede ao iniciar sessão: ${e.message}", e)
        }
    }

    suspend fun startHandwrittenSession(): SessionResult = withContext(Dispatchers.IO) {
        try {
            val req = HandwrittenStartRequest(
                deviceCode = deviceId,
                gatewayCode = deviceId,
                captureSource = "ANDROID_CAMERA"
            )
            val resp = api.startHandwrittenSession(req)
            if (resp.isSuccessful) {
                val body = resp.body()!!
                val state = SessionState(
                    sessionId = body.sessionId,
                    cursor = 0,
                    resumed = false,
                    status = body.status
                )
                Log.i(TAG, "startHandwritten ok: session=${state.sessionId} words=${body.expectedWords}")
                historyDao?.upsert(SessionHistoryEntity(state.sessionId, "HANDWRITTEN_WORD", System.currentTimeMillis(), status = body.status ?: "STARTED"))
                SessionResult.Success(state)
            } else {
                val err = resp.errorBody()?.string()
                Log.e(TAG, "startHandwritten falhou: ${resp.code()} $err")
                SessionResult.Error("Falha handwritten: ${resp.code()} $err", code = resp.code())
            }
        } catch (e: Exception) {
            Log.e(TAG, "startHandwritten exceção", e)
            SessionResult.Error("Erro rede handwritten: ${e.message}", e)
        }
    }

    suspend fun heartbeat(sessionId: String, phase: String = "CAPTURE", cursor: Long = 0): Result<Unit> =
        withContext(Dispatchers.IO) {
            try {
                val resp = api.heartbeat(sessionId, HeartbeatRequest(deviceId, phase, cursor))
                if (resp.isSuccessful) {
                    Log.d(TAG, "heartbeat ok session=$sessionId phase=$phase")
                    Result.success(Unit)
                } else {
                    Log.w(TAG, "heartbeat falhou ${resp.code()} session=$sessionId")
                    Result.failure(IllegalStateException("heartbeat ${resp.code()}"))
                }
            } catch (e: Exception) {
                Log.w(TAG, "heartbeat exceção session=$sessionId", e)
                Result.failure(e)
            }
        }

    suspend fun endSignal(sessionId: String, reason: String = "user_requested"): Result<Unit> =
        withContext(Dispatchers.IO) {
            try {
                val resp = api.endSignal(sessionId, EndSignalRequest(reason))
                if (resp.isSuccessful) {
                    Log.i(TAG, "endSignal ok session=$sessionId")
                    Result.success(Unit)
                } else {
                    val err = resp.errorBody()?.string()
                    Log.e(TAG, "endSignal falhou ${resp.code()} $err")
                    Result.failure(IllegalStateException("endSignal ${resp.code()}: $err"))
                }
            } catch (e: Exception) {
                Log.e(TAG, "endSignal exceção", e)
                Result.failure(e)
            }
        }

    suspend fun endHandwrittenSignal(sessionId: String, reason: String = "user_requested"): Result<Unit> =
        withContext(Dispatchers.IO) {
            try {
                val resp = api.endSignalHandwritten(sessionId, EndSignalRequest(reason))
                if (resp.isSuccessful) {
                    Log.i(TAG, "endHandwritten ok session=$sessionId")
                    Result.success(Unit)
                } else {
                    val err = resp.errorBody()?.string()
                    Log.e(TAG, "endHandwritten falhou ${resp.code()} $err")
                    Result.failure(IllegalStateException("endHandwritten ${resp.code()}: $err"))
                }
            } catch (e: Exception) {
                Log.e(TAG, "endHandwritten exceção", e)
                Result.failure(e)
            }
        }

    suspend fun captureComplete(sessionId: String, captureId: String, frames: Int): Result<Unit> =
        withContext(Dispatchers.IO) {
            try {
                val resp = api.captureComplete(sessionId, captureId, frames)
                if (resp.isSuccessful) Result.success(Unit)
                else Result.failure(IllegalStateException("captureComplete ${resp.code()}"))
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    suspend fun captureCompleteHandwritten(sessionId: String, captureId: String, frames: Int): Result<Unit> =
        withContext(Dispatchers.IO) {
            try {
                val resp = api.captureCompleteHandwritten(sessionId, captureId, frames)
                if (resp.isSuccessful) Result.success(Unit)
                else Result.failure(IllegalStateException("captureCompleteHandwritten ${resp.code()}"))
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    suspend fun fetchCommand(sessionId: String, cursor: Long, waitMs: Long = 25000, phase: String = "CAPTURE") =
        withContext(Dispatchers.IO) {
            try {
                val resp = api.getCommand(sessionId, cursor, waitMs, phase)
                if (resp.isSuccessful) Result.success(resp.body()!!)
                else Result.failure(IllegalStateException("getCommand ${resp.code()}"))
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    suspend fun fetchHandwrittenCommand(sessionId: String, cursor: Long, waitMs: Long = 25000, phase: String = "CAPTURE") =
        withContext(Dispatchers.IO) {
            try {
                val resp = api.getHandwrittenCommand(sessionId, cursor, waitMs, phase)
                if (resp.isSuccessful) Result.success(resp.body()!!)
                else Result.failure(IllegalStateException("getHandwrittenCommand ${resp.code()}"))
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    suspend fun fetchResult(sessionId: String, cursor: Long = 0) = withContext(Dispatchers.IO) {
        try {
            val resp = api.getResult(sessionId, deviceId, cursor)
            if (resp.isSuccessful) Result.success(resp.body())
            else Result.failure(IllegalStateException("getResult ${resp.code()}"))
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun fetchRgbTest(sessionId: String, afterId: Int) = withContext(Dispatchers.IO) {
        try {
            val resp = api.getRgbTest(sessionId, afterId)
            if (resp.isSuccessful) Result.success(resp.body())
            else Result.failure(IllegalStateException("getRgbTest ${resp.code()}"))
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
