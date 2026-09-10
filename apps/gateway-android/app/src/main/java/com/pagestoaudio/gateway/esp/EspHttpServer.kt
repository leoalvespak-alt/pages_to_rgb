package com.pagestoaudio.gateway.esp

import android.util.Log
import com.pagestoaudio.gateway.spool.PendingFrame
import com.pagestoaudio.gateway.spool.SpoolRepository
import com.pagestoaudio.gateway.util.Sha256Util
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.InputStream
import java.net.ServerSocket
import java.net.Socket
import java.nio.charset.StandardCharsets
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

/**
 * S03.1/S03.3 — serviço local HTTPS 8787 (nesta etapa: HTTP em bancada isolada;
 * TLS com confiança provisionada antes do aceite de produção, contrato §2).
 *
 * Handlers: HELLO, start, comandos, upload (JPEG bruto), capture-complete,
 * resultado e eventos. HELLO repetido nunca altera estado de domínio.
 * JPEG nunca é transformado antes de encaminhar (bytes/hash preservados).
 * ACK durável (200/201/208 + identidade/hash) somente após posse recuperável
 * (arquivo atômico + registro Room + reconciliação).
 */
class EspHttpServer(
    private val provisioning: EspProvisioning,
    private val spool: SpoolRepository,
    private val filesDir: File,
    private val scope: CoroutineScope,
    private val port: Int = 8787,
    private val cloud: EspCloudBridge,
) {
    companion object {
        private const val TAG = "EspHttp"
        private const val MAX_BODY = 12 * 1024 * 1024
    }

    /** Ponte para o cloud (implementada pelo Service a partir do SessionRepository). */
    interface EspCloudBridge {
        suspend fun startForDevice(deviceId: String, resumeHint: Boolean, lastSessionId: String?, allowNewSession: Boolean): CloudSession
        suspend fun enqueueCloudUpload(frame: PendingFrame)
        suspend fun cloudCaptureComplete(sessionId: String, captureId: String, frames: Int): Boolean
        /** Comando integral (payload JSON completo, nunca "{}" fixo). */
        suspend fun cloudCommand(sessionId: String, cursor: Long, phase: String, waitMs: Long): CloudCommand?
        /** Resultado integral serializado (todos os campos, nunca só command/cursor). */
        suspend fun cloudResult(sessionId: String, cursor: Long): String?
        suspend fun cloudHeartbeat(sessionId: String, deviceId: String, state: String, rssi: Int, cameraProfile: String): Boolean
        /** Fault é evento local durável (sem rota cloud em INTEGRACAO rev.1); retorna se persistiu. */
        suspend fun cloudFault(deviceId: String, code: String, detail: String, cameraProfile: String): Boolean
        /** Sequência RGB integral serializada (answers/palette/sha256 preservados). */
        suspend fun cloudRgbSequence(sessionId: String, sequenceId: String?): String?
        suspend fun cloudRgbEvent(sessionId: String, sequenceId: String, revision: Int, event: String, nextIndex: Int, itemCount: Int, deviceId: String): Boolean
        /** Local RGB queue is read-only until the ESP posts its physical event. */
        suspend fun localRgbCommand(deviceId: String): String?
        suspend fun localRgbEvent(
            deviceId: String,
            commandId: String,
            event: String,
            payload: String,
            effectivePayload: String,
            firmwareVersion: String?,
            deviceTimestamp: String?,
            idempotencyKey: String,
        ): Boolean
    }

    /** Erro cloud com código HTTP preservado (401/403/404/409/422/503 têm semântica distinta). */
    class CloudException(val code: Int, message: String) : Exception(message)

    data class CloudSession(val sessionId: String, val resumed: Boolean, val cursor: Long)
    data class CloudCommand(val command: String, val cursor: Long, val payload: String)

    private var job: Job? = null
    // Sessão ESP atual por dispositivo (memória + reconciliada com arquivos locais).
    private val deviceSessions = mutableMapOf<String, CloudSession>()

    fun start() {
        if (job?.isActive == true) return
        job = scope.launch(Dispatchers.IO) {
            var server: ServerSocket? = null
            try {
                server = ServerSocket(port)
                Log.i(TAG, "Serviço local ouvindo em $port")
                while (isActive) {
                    try {
                        val socket = server.accept()
                        launch { handle(socket) }
                    } catch (e: Exception) {
                        if (!isActive) break
                        Log.w(TAG, "accept falhou", e)
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Servidor local não iniciou em $port", e)
            } finally {
                try { server?.close() } catch (_: Exception) {}
            }
        }
    }

    fun stop() {
        job?.cancel()
        job = null
    }

    private suspend fun handle(socket: Socket) {
        try {
            socket.use { s ->
                val input = s.getInputStream()
                val req = readRequest(input) ?: run {
                    writeResponse(s, 400, JSONObject().put("error", "bad request").toString())
                    return
                }
                val path = req.path
                val response: Pair<Int, String> = when {
                    req.method == "GET" && path == "/v1/hello" -> hello(req)
                    req.method == "POST" && path == "/v1/device/hello" -> deviceHello(req)
                    req.method == "POST" && path == "/v1/device/start" -> deviceStart(req)
                    req.method == "POST" && path == "/v1/device/frame" -> deviceFrame(req)
                    req.method == "POST" && path == "/v1/device/capture-complete" -> deviceCaptureComplete(req)
                    req.method == "POST" && path == "/v1/device/heartbeat" -> deviceHeartbeat(req)
                    req.method == "POST" && path == "/v1/device/fault" -> deviceFault(req)
                    req.method == "GET" && path == "/v1/device/rgb-sequence" -> deviceRgbSequence(req)
                    req.method == "POST" && path == "/v1/device/rgb-sequence/event" -> deviceRgbEvent(req)
                    req.method == "GET" && path == "/v1/device/rgb-test" -> deviceRgbTestCommand(req)
                    req.method == "POST" && path == "/v1/device/rgb-test/event" -> deviceRgbTestEvent(req)
                    req.method == "GET" && path == "/v1/device/diagnostics" -> diagStatus(req)
                    req.method == "POST" && path == "/v1/device/diagnostics" -> diagStart(req)
                    req.method == "POST" && path == "/v1/device/diagnostics/frame" -> diagFrame(req)
                    req.method == "POST" && path == "/v1/device/diagnostics/stop" -> diagStop(req)
                    req.method == "GET" && path == "/v1/device/command" -> deviceCommand(req)
                    req.method == "GET" && path == "/v1/device/result" -> deviceResult(req)
                    req.method == "POST" && path == "/v1/device/event" -> deviceEvent(req)
                    else -> 404 to JSONObject().put("error", "not found").toString()
                }
                writeResponse(s, response.first, response.second)
            }
        } catch (e: Exception) {
            Log.w(TAG, "handler erro", e)
        }
    }

    // ── Rotas ──────────────────────────────────────────────────────────────

    private fun hello(req: HttpRequest): Pair<Int, String> {
        // Alias público de presença (sem estado). Canônico autenticado: POST /v1/device/hello.
        val body = JSONObject()
            .put("schema", "p2a-esp/1")
            .put("local_protocol", "P2A-LOCAL/1")
            .put("deprecated", "use POST /v1/device/hello")
            .put("gateway_id", provisioning.gatewayId())
            .put("capabilities", org.json.JSONArray(listOf("frame", "capture-complete", "command", "result", "event", "heartbeat", "fault", "rgb-sequence", "rgb-test", "camera_diagnostics_v1")))
        return 200 to body.toString()
    }

    // ── Autenticação local (C01/RA02) ─────────────────────────────────────
    // Toda rota protegida exige dispositivo pareado + Bearer válido. NENHUMA
    // rota cria credencial: pareamento é só pela tela do app (importDeviceSecret).

    private fun bearerOf(req: HttpRequest): String? =
        req.headers["authorization"]?.removePrefix("Bearer ")?.trim()?.takeIf { it.isNotEmpty() }

    /** null = autorizado; senão a resposta de erro a devolver. */
    private fun requireAuth(req: HttpRequest, deviceId: String): Pair<Int, String>? {
        if (!isValidEspId(deviceId)) {
            return 422 to JSONObject().put("error", "invalid device_id").toString()
        }
        if (!provisioning.isDeviceProvisioned(deviceId)) {
            return 401 to JSONObject()
                .put("error", "device not paired")
                .put("code", "DEVICE_NOT_PROVISIONED")
                .toString()
        }
        if (!provisioning.validateDevice(deviceId, bearerOf(req))) {
            return 401 to JSONObject().put("error", "unauthorized device").toString()
        }
        return null
    }

    /** POST /v1/device/hello canônico (o firmware usa este; GET /v1/hello é alias). */
    private fun deviceHello(req: HttpRequest): Pair<Int, String> {
        val json = try { JSONObject(req.bodyAsText()) } catch (_: Exception) {
            return 400 to JSONObject().put("error", "invalid json").toString()
        }
        val deviceId = json.optString("device_id", "")
        // HELLO nunca abre sessão nem altera domínio; só presença + capacidades.
        requireAuth(req, deviceId)?.let { return it }
        val body = JSONObject()
            .put("schema", "p2a-esp/1")
            .put("local_protocol", "P2A-LOCAL/1")
            .put("gateway_id", provisioning.gatewayId())
            .put("device_id", deviceId)
            .put("capabilities", org.json.JSONArray(listOf("frame", "capture-complete", "command", "result", "event", "heartbeat", "fault", "rgb-sequence", "rgb-test", "camera_diagnostics_v1")))
        return 200 to body.toString()
    }

    // ── Diagnóstico de câmera (D02/D04 — delega ao forwarder quando ligado) ──
    // Hook mínimo: sem forwarder configurado, responde 501 controlado.
    var diagForwarder: com.pagestoaudio.gateway.diag.CameraDiagnosticsForwarder? = null

    private suspend fun diagStatus(req: HttpRequest): Pair<Int, String> {
        val fwd = diagForwarder
        if (!com.pagestoaudio.gateway.diag.DiagConfig.diagnosticsEnabled || fwd == null) {
            return 501 to JSONObject().put("error", "camera diagnostics disabled").toString()
        }
        val id = req.query["diagnostic_id"]
        val deviceId = req.query["device_id"] ?: ""
        // Estado de teste também exige pareamento: sem info para estranhos.
        requireAuth(req, deviceId)?.let { return it }
        val active = fwd.isActive(id)
        val request = fwd.activeRequest()
        return 200 to JSONObject()
            .put("active", active)
            .put("diagnostic_id", request?.diagnosticId)
            .put("mode", request?.mode?.name)
            .put("resolution", request?.resolution)
            .put("jpeg_quality", request?.jpegQuality)
            .put("duration_s", request?.durationS)
            .put("max_frames", request?.maxFrames)
            .toString()
    }

    private suspend fun diagStart(req: HttpRequest): Pair<Int, String> {
        val fwd = diagForwarder
        if (!com.pagestoaudio.gateway.diag.DiagConfig.diagnosticsEnabled || fwd == null) {
            return 501 to JSONObject().put("error", "camera diagnostics disabled").toString()
        }
        return try {
            val json = JSONObject(req.bodyAsText())
            val diagId = json.optString("diagnostic_id", "")
            val deviceId = json.optString("device_id", "")
            val mode = json.optString("mode", "PHOTO")
            if (!isValidEspId(diagId) || !isValidEspId(deviceId)) {
                return 422 to JSONObject().put("error", "invalid diagnostic identity").toString()
            }
            requireAuth(req, deviceId)?.let { return it }
            // Nunca aciona CameraX: só encaminha controle à ESP; origem é a placa.
            val ok = fwd.start(
                com.pagestoaudio.gateway.diag.DiagRequest(
                    diagnosticId = diagId, deviceId = deviceId,
                    mode = runCatching { com.pagestoaudio.gateway.diag.DiagMode.valueOf(mode) }
                        .getOrDefault(com.pagestoaudio.gateway.diag.DiagMode.PHOTO),
                    resolution = json.optString("resolution", "SVGA"),
                    jpegQuality = json.optInt("jpeg_quality", 18),
                    durationS = json.optInt("duration_s", 60).coerceIn(1, 60),
                    maxFrames = json.optInt("max_frames", 1).coerceIn(1, 60),
                )
            )
            if (ok) 200 to JSONObject().put("accepted", true).toString()
            else 409 to JSONObject().put("error", "busy").toString()
        } catch (_: Exception) {
            400 to JSONObject().put("error", "invalid json").toString()
        }
    }

    private suspend fun diagFrame(req: HttpRequest): Pair<Int, String> {
        val fwd = diagForwarder
        if (!com.pagestoaudio.gateway.diag.DiagConfig.diagnosticsEnabled || fwd == null) {
            return 501 to JSONObject().put("error", "camera diagnostics disabled").toString()
        }
        val deviceId = req.headers["x-device-id"] ?: ""
        val secret = req.headers["authorization"]?.removePrefix("Bearer ")?.trim()
        if (!provisioning.validateDevice(deviceId, secret)) {
            return 401 to JSONObject().put("error", "unauthorized device").toString()
        }
        val diagId = req.headers["x-diagnostic-id"] ?: ""
        val frameIndex = req.headers["x-frame-index"]?.toIntOrNull()
        val sha = req.headers["x-sha256"] ?: ""
        val monoMs = req.headers["x-captured-mono-ms"]?.toLongOrNull() ?: 0L
        if (!isValidEspId(diagId) || frameIndex == null || frameIndex < 0 ||
            !sha.matches(Regex("^[0-9a-fA-F]{64}$"))) {
            return 422 to JSONObject().put("error", "invalid diagnostic headers").toString()
        }
        if (req.body.size > MAX_BODY || req.body.size < 128 || !isJpeg(req.body)) {
            return 415 to JSONObject().put("error", "not a jpeg").toString()
        }
        val bounds = decodeBounds(req.body)
        return when (val code = fwd.onDeviceFrame(diagId, frameIndex, sha, req.body, monoMs, bounds.first, bounds.second)) {
            201 -> 201 to JSONObject().put("diagnostic_id", diagId).put("frame_index", frameIndex).put("sha256", sha).toString()
            208 -> 208 to JSONObject().put("diagnostic_id", diagId).put("duplicate", true).toString()
            202 -> 202 to JSONObject().put("diagnostic_id", diagId).put("transient", true).toString()
            413 -> 413 to JSONObject().put("error", "quota exceeded").toString()
            else -> 409 to JSONObject().put("error", "not accepting").toString()
        }
    }

    private suspend fun diagStop(req: HttpRequest): Pair<Int, String> {
        val fwd = diagForwarder
        if (!com.pagestoaudio.gateway.diag.DiagConfig.diagnosticsEnabled || fwd == null) {
            return 501 to JSONObject().put("error", "camera diagnostics disabled").toString()
        }
        return try {
            val json = JSONObject(req.bodyAsText())
            val diagId = json.optString("diagnostic_id", "")
            val deviceId = json.optString("device_id", "")
            if (!isValidEspId(diagId) || !isValidEspId(deviceId)) {
                return 422 to JSONObject().put("error", "invalid diagnostic identity").toString()
            }
            requireAuth(req, deviceId)?.let { return it }
            fwd.stop("esp-stop")
            200 to JSONObject().put("released", true).toString()
        } catch (_: Exception) {
            400 to JSONObject().put("error", "invalid json").toString()
        }
    }

    private suspend fun deviceStart(req: HttpRequest): Pair<Int, String> {
        val json = try { JSONObject(req.bodyAsText()) } catch (_: Exception) {
            return 400 to JSONObject().put("error", "invalid json").toString()
        }
        val deviceId = json.optString("device_id", "")
        // C01/RA02: sem criação implícita de credencial por pedido não autenticado.
        requireAuth(req, deviceId)?.let { return it }
        val resumeHint = json.optBoolean("resume_hint", false)
        val allowNew = if (json.has("allow_new_session")) json.optBoolean("allow_new_session", true) else !resumeHint
        val lastSessionId = json.optString("last_session_id", null)?.takeIf { it.isNotBlank() }
        return try {
            val session = cloud.startForDevice(deviceId, resumeHint, lastSessionId, allowNew)
            deviceSessions[deviceId] = session
            200 to JSONObject()
                .put("session_id", session.sessionId)
                .put("resumed", session.resumed)
                .put("cursor", session.cursor)
                .put("gateway_id", provisioning.gatewayId())
                .toString()
        } catch (e: CloudException) {
            // C01/RA03: propaga 401/403/404/409/422 com semântica; resto vira 503.
            val code = if (e.code in listOf(400, 401, 403, 404, 409, 410, 422)) e.code else 503
            Log.w(TAG, "deviceStart cloud $code", e)
            code to JSONObject().put("error", e.message ?: "cloud unavailable").put("code", e.code).toString()
        } catch (e: Exception) {
            Log.w(TAG, "deviceStart falhou", e)
            503 to JSONObject().put("error", "cloud unavailable").toString()
        }
    }

    private suspend fun deviceFrame(req: HttpRequest): Pair<Int, String> {
        // S03.6: valida limites antes de aceitar; JPEG real verificado.
        val deviceId = req.headers["x-device-id"] ?: ""
        requireAuth(req, deviceId)?.let { return it }
        val captureId = req.headers["x-capture-id"] ?: ""
        val frameIndex = req.headers["x-frame-index"]?.toIntOrNull()
        val sha = req.headers["x-sha256"] ?: ""
        if (!isValidEspId(captureId) || frameIndex == null || frameIndex < 0 || !sha.matches(Regex("^[0-9a-fA-F]{64}$"))) {
            return 422 to JSONObject().put("error", "invalid identity headers").toString()
        }
        val bytes = req.body
        if (bytes.size > MAX_BODY || bytes.size < 128) {
            return 413 to JSONObject().put("error", "invalid body size").toString()
        }
        if (!isJpeg(bytes)) return 415 to JSONObject().put("error", "not a jpeg").toString()
        val session = deviceSessions[deviceId]
            ?: return 409 to JSONObject().put("error", "no session — start first").toString()
        // S03.5: tmp→rename atômico + registro Room + reconciliação antes do ACK.
        val dir = File(filesDir, "esp_spool/${session.sessionId}").apply { mkdirs() }
        val target = File(dir, "${captureId}_${frameIndex}.jpg")
        if (target.exists()) {
            val existingSha = try { Sha256Util.sha256HexStreaming(target) } catch (_: Exception) { "" }
            if (existingSha.equals(sha, ignoreCase = true)) {
                // S03.6: duplicata idêntica retorna mesma identidade/hash (208).
                val ok = JSONObject()
                    .put("capture_id", captureId)
                    .put("frame_index", frameIndex)
                    .put("sha256", existingSha)
                    .put("duplicate", true)
                    .toString()
                return 208 to ok
            }
            return 409 to JSONObject().put("error", "conflict: same key different hash").toString()
        }
        val written = spool.writeAtomically(target, bytes)
        if (written.isFailure) return 500 to JSONObject().put("error", "spool write failed").toString()
        val computed = try { Sha256Util.sha256HexStreaming(target) } catch (e: Exception) {
            target.delete()
            return 500 to JSONObject().put("error", "hash failed").toString()
        }
        if (!computed.equals(sha, ignoreCase = true)) {
            target.delete()
            return 409 to JSONObject().put("error", "sha mismatch").toString()
        }
        val bounds = decodeBounds(bytes)
        val frame = PendingFrame(
            sessionId = session.sessionId,
            captureId = captureId,
            frameIndex = frameIndex,
            sha256 = computed,
            filePath = target.absolutePath,
            resolution = "${bounds.first}x${bounds.second}",
            orientation = 0,
            createdAt = System.currentTimeMillis(),
            sessionType = "EXAM",
            width = bounds.first,
            height = bounds.second,
        )
        val saved = spool.save(frame)
        if (saved.isFailure) {
            return 500 to JSONObject().put("error", "spool register failed").toString()
        }
        withContext(Dispatchers.IO) {
            try { cloud.enqueueCloudUpload(frame) } catch (e: Exception) {
                Log.w(TAG, "enqueueCloudUpload falhou (retry via WorkManager)", e)
            }
        }
        // S03.6: ACK durável somente após posse recuperável.
        val ok = JSONObject()
            .put("capture_id", captureId)
            .put("frame_index", frameIndex)
            .put("sha256", computed)
            .put("duplicate", false)
            .toString()
        return 201 to ok
    }

    private suspend fun deviceCaptureComplete(req: HttpRequest): Pair<Int, String> {
        val json = try { JSONObject(req.bodyAsText()) } catch (_: Exception) {
            return 400 to JSONObject().put("error", "invalid json").toString()
        }
        val deviceId = json.optString("device_id", "")
        requireAuth(req, deviceId)?.let { return it }
        val sessionId = json.optString("session_id", "")
        val captureId = json.optString("capture_id", "")
        val frames = json.optInt("frames", -1)
        if (!isValidEspId(deviceId) || !isValidEspId(captureId) || sessionId.isBlank() || frames < 0) {
            return 422 to JSONObject().put("error", "invalid capture-complete").toString()
        }
        // S05-like no Android: efetiva cloud somente com recebidos conciliados —
        // aqui delega; pendências mantêm 202 (não-ACK) em vez de falso 200.
        val ok = try { cloud.cloudCaptureComplete(sessionId, captureId, frames) } catch (_: Exception) { false }
        return if (ok) {
            200 to JSONObject().put("capture_id", captureId).put("confirmed", true).toString()
        } else {
            202 to JSONObject().put("capture_id", captureId).put("pending", true).toString()
        }
    }

    private suspend fun deviceCommand(req: HttpRequest): Pair<Int, String> {
        val deviceId = req.query["device_id"] ?: ""
        requireAuth(req, deviceId)?.let { return it }
        val cursor = req.query["cursor"]?.toLongOrNull() ?: 0L
        val waitMs = req.query["wait_ms"]?.toLongOrNull()?.coerceIn(0L, 25000L) ?: 0L
        val phase = req.query["phase"] ?: "CAPTURE"
        val querySession = req.query["session_id"]
        val session = deviceSessions[deviceId]
            ?: return 409 to JSONObject().put("error", "no session").toString()
        if (querySession != null && querySession != session.sessionId) {
            // C01: vínculo sessão/dispositivo — sessão divergente nunca anexa silenciosamente.
            return 409 to JSONObject().put("error", "session mismatch").toString()
        }
        // C01/RA01: RESULT_WAIT consulta resultado integral; CAPTURE consulta comando integral.
        if (phase == "RESULT_WAIT") {
            val result = try { cloud.cloudResult(session.sessionId, cursor) } catch (_: Exception) { null }
                ?: return 204 to ""
            return 200 to result
        }
        val cmd = try { cloud.cloudCommand(session.sessionId, cursor, phase, waitMs) } catch (_: Exception) { null }
            ?: return 200 to JSONObject().put("command", "NONE").put("cursor", cursor).toString()
        return 200 to JSONObject()
            .put("command", cmd.command)
            .put("cursor", cmd.cursor)
            .put("payload", JSONObject(cmd.payload))
            .toString()
    }

    private suspend fun deviceResult(req: HttpRequest): Pair<Int, String> {
        val deviceId = req.query["device_id"] ?: ""
        requireAuth(req, deviceId)?.let { return it }
        val cursor = req.query["cursor"]?.toLongOrNull() ?: 0L
        val session = deviceSessions[deviceId]
            ?: return 409 to JSONObject().put("error", "no session").toString()
        // C01/RA01: corpo integral do resultado (command/cursor/session/sequence/revision/sha).
        val result = try { cloud.cloudResult(session.sessionId, cursor) } catch (_: Exception) { null }
            ?: return 204 to ""
        return 200 to result
    }

    private suspend fun deviceHeartbeat(req: HttpRequest): Pair<Int, String> {
        val json = try { JSONObject(req.bodyAsText()) } catch (_: Exception) {
            return 400 to JSONObject().put("error", "invalid json").toString()
        }
        val deviceId = json.optString("device_id", "")
        requireAuth(req, deviceId)?.let { return it }
        val sessionId = json.optString("session_id", "")
        val state = json.optString("state", "UNKNOWN")
        val rssi = json.optInt("rssi", 0)
        val cameraProfile = json.optString("camera_profile", "NONE")
        if (sessionId.isBlank()) return 422 to JSONObject().put("error", "invalid heartbeat").toString()
        val ok = try { cloud.cloudHeartbeat(sessionId, deviceId, state, rssi, cameraProfile) } catch (_: Exception) { false }
        return if (ok) 200 to JSONObject().put("policy_valid", true).toString()
        else 503 to JSONObject().put("error", "cloud unavailable").toString()
    }

    private suspend fun deviceFault(req: HttpRequest): Pair<Int, String> {
        val json = try { JSONObject(req.bodyAsText()) } catch (_: Exception) {
            return 400 to JSONObject().put("error", "invalid json").toString()
        }
        val deviceId = json.optString("device_id", "")
        requireAuth(req, deviceId)?.let { return it }
        val code = json.optString("code", "UNKNOWN")
        val detail = json.optString("detail", "")
        val cameraProfile = json.optString("camera_profile", "NONE")
        // Sem rota cloud em INTEGRACAO rev.1: evento local durável (outbox-arquivo, consumidor em C02).
        val ok = try { cloud.cloudFault(deviceId, code, detail, cameraProfile) } catch (_: Exception) { false }
        return if (ok) 200 to JSONObject().put("accepted", true).toString()
        else 500 to JSONObject().put("error", "fault not persisted").toString()
    }

    private suspend fun deviceRgbSequence(req: HttpRequest): Pair<Int, String> {
        val deviceId = req.query["device_id"] ?: ""
        requireAuth(req, deviceId)?.let { return it }
        val sessionId = req.query["session_id"] ?: ""
        val sequenceId = req.query["sequence_id"]
        if (sessionId.isBlank() || sequenceId.isNullOrBlank()) {
            return 422 to JSONObject().put("error", "invalid rgb-sequence query").toString()
        }
        val session = deviceSessions[deviceId]
        if (session != null && session.sessionId != sessionId) {
            return 409 to JSONObject().put("error", "session mismatch").toString()
        }
        val body = try { cloud.cloudRgbSequence(sessionId, sequenceId) } catch (_: Exception) { null }
            ?: return 404 to JSONObject().put("error", "sequence not found").toString()
        return 200 to body
    }

    private suspend fun deviceRgbEvent(req: HttpRequest): Pair<Int, String> {
        val json = try { JSONObject(req.bodyAsText()) } catch (_: Exception) {
            return 400 to JSONObject().put("error", "invalid json").toString()
        }
        val deviceId = json.optString("device_id", "")
        requireAuth(req, deviceId)?.let { return it }
        val sessionId = json.optString("session_id", "")
        val sequenceId = json.optString("sequence_id", "")
        val revision = json.optInt("revision", -1)
        val event = json.optString("event", "")
        val nextIndex = json.optInt("next_index", -1)
        val itemCount = json.optInt("item_count", -1)
        if (sessionId.isBlank() || sequenceId.isBlank() || revision < 0 || event.isBlank()
            || nextIndex < 0 || itemCount < 0) {
            return 422 to JSONObject().put("error", "invalid rgb event").toString()
        }
        val ok = try {
            cloud.cloudRgbEvent(sessionId, sequenceId, revision, event, nextIndex, itemCount, deviceId)
        } catch (_: Exception) { false }
        return if (ok) 200 to JSONObject().put("accepted", true).toString()
        else 503 to JSONObject().put("error", "cloud unavailable").toString()
    }

    /** Cloud RGB commands are staged in Room before the ESP is allowed to read them. */
    private suspend fun deviceRgbTestCommand(req: HttpRequest): Pair<Int, String> {
        val deviceId = req.query["device_id"] ?: ""
        requireAuth(req, deviceId)?.let { return it }
        val command = try { cloud.localRgbCommand(deviceId) } catch (e: Exception) {
            Log.w(TAG, "local RGB command read failed", e)
            null
        }
        return 200 to (command ?: JSONObject().put("command", "NONE").toString())
    }

    /** Persist the ESP event in the local outbox before acknowledging it. */
    private suspend fun deviceRgbTestEvent(req: HttpRequest): Pair<Int, String> {
        val json = try { JSONObject(req.bodyAsText()) } catch (_: Exception) {
            return 400 to JSONObject().put("error", "invalid json").toString()
        }
        val deviceId = json.optString("device_id", "")
        requireAuth(req, deviceId)?.let { return it }
        val commandId = json.optString("command_id", "")
        val event = json.optString("event", "")
        if (!isValidEspId(commandId) || event !in setOf(
                "FORWARDED", "RECEIVED", "APPLIED", "OFF", "FAILED", "EXPIRED", "CANCELLED"
            )
        ) {
            return 422 to JSONObject().put("error", "invalid rgb test event").toString()
        }
        val payload = json.optJSONObject("payload")?.toString() ?: "{}"
        val effective = json.optJSONObject("effective_payload")?.toString() ?: "{}"
        val key = req.headers["idempotency-key"]?.takeIf { it.isNotBlank() }
            ?: "$commandId:$event"
        val accepted = try {
            cloud.localRgbEvent(
                deviceId = deviceId,
                commandId = commandId,
                event = event,
                payload = payload,
                effectivePayload = effective,
                firmwareVersion = json.optString("firmware_version", "").takeIf { it.isNotBlank() },
                deviceTimestamp = json.optString("device_timestamp", "").takeIf { it.isNotBlank() },
                idempotencyKey = key,
            )
        } catch (e: Exception) {
            Log.w(TAG, "local RGB event persistence failed", e)
            false
        }
        return if (accepted) {
            200 to JSONObject().put("accepted", true).put("idempotency_key", key).toString()
        } else {
            409 to JSONObject().put("error", "local RGB event rejected").toString()
        }
    }

    private fun deviceEvent(req: HttpRequest): Pair<Int, String> {
        // Eventos locais persistidos antes de confirmar ao firmware quando há
        // transferência de responsabilidade (S03.8): grava em outbox-arquivo.
        return try {
            val json = JSONObject(req.bodyAsText())
            val deviceId = json.optString("device_id", "")
            requireAuth(req, deviceId)?.let { return it }
            if (!isValidEspId(deviceId)) return 422 to JSONObject().put("error", "invalid device").toString()
            val outbox = File(filesDir, "esp_outbox").apply { mkdirs() }
            val name = "evt-${System.currentTimeMillis()}-${(0..9999).random()}.json"
            File(outbox, name).writeText(json.toString(), StandardCharsets.UTF_8)
            200 to JSONObject().put("accepted", true).put("duplicate", false).toString()
        } catch (_: Exception) {
            400 to JSONObject().put("error", "invalid event").toString()
        }
    }

    // ── HTTP mínimo ────────────────────────────────────────────────────────

    private data class HttpRequest(
        val method: String,
        val path: String,
        val query: Map<String, String>,
        val headers: Map<String, String>,
        val body: ByteArray,
    ) {
        fun bodyAsText(): String = body.toString(StandardCharsets.UTF_8)
    }

    private fun readRequest(input: InputStream): HttpRequest? {
        val headerBytes = ByteArrayOutputStream()
        var matched = 0
        val terminator = byteArrayOf(13, 10, 13, 10)
        while (true) {
            val b = input.read()
            if (b == -1) return null
            headerBytes.write(b)
            val arr = headerBytes.toByteArray()
            matched = if (arr.size >= 4 && arr.takeLast(4) == terminator.toList()) 4 else 0
            if (matched == 4) break
            if (arr.size > 65536) return null
        }
        val headerText = headerBytes.toByteArray().toString(StandardCharsets.UTF_8)
        val lines = headerText.split("\r\n")
        if (lines.isEmpty()) return null
        val requestLine = lines[0].split(" ")
        if (requestLine.size < 2) return null
        val method = requestLine[0].uppercase()
        val fullPath = requestLine[1]
        val path = fullPath.substringBefore("?")
        val query = fullPath.substringAfter("?", "").split("&").mapNotNull {
            val kv = it.split("=", limit = 2)
            if (kv.size == 2 && kv[0].isNotBlank()) kv[0] to kv[1] else null
        }.toMap()
        val headers = mutableMapOf<String, String>()
        for (line in lines.drop(1)) {
            if (line.isBlank()) continue
            val idx = line.indexOf(":")
            if (idx > 0) headers[line.substring(0, idx).trim().lowercase()] = line.substring(idx + 1).trim()
        }
        val contentLength = headers["content-length"]?.toIntOrNull() ?: 0
        if (contentLength < 0 || contentLength > MAX_BODY) return null
        val body = ByteArray(contentLength)
        var read = 0
        while (read < contentLength) {
            val n = input.read(body, read, contentLength - read)
            if (n == -1) break
            read += n
        }
        return HttpRequest(method, path, query, headers, body.copyOf(read))
    }

    private fun writeResponse(socket: Socket, code: Int, body: String) {
        val bytes = body.toByteArray(StandardCharsets.UTF_8)
        val status = when (code) {
            200 -> "OK"; 201 -> "Created"; 202 -> "Accepted"; 204 -> "No Content"; 208 -> "Already Reported"
            400 -> "Bad Request"; 401 -> "Unauthorized"; 404 -> "Not Found"
            409 -> "Conflict"; 413 -> "Content Too Large"; 415 -> "Unsupported Media Type"
            422 -> "Unprocessable Entity"; 500 -> "Internal Error"; 503 -> "Unavailable"
            else -> "OK"
        }
        val head = "HTTP/1.1 $code $status\r\nContent-Type: application/json\r\nContent-Length: ${bytes.size}\r\nConnection: close\r\n\r\n"
        val out = socket.getOutputStream()
        out.write(head.toByteArray(StandardCharsets.UTF_8))
        out.write(bytes)
        out.flush()
    }

    private fun isValidEspId(value: String): Boolean =
        value.matches(Regex("^[A-Za-z0-9_-]{1,63}$"))

    private fun isJpeg(bytes: ByteArray): Boolean =
        bytes.size > 3 && bytes[0] == 0xFF.toByte() && bytes[1] == 0xD8.toByte() && bytes[2] == 0xFF.toByte()

    private fun decodeBounds(bytes: ByteArray): Pair<Int, Int> {
        return try {
            val opts = android.graphics.BitmapFactory.Options().apply { inJustDecodeBounds = true }
            android.graphics.BitmapFactory.decodeByteArray(bytes, 0, bytes.size, opts)
            Pair(opts.outWidth.takeIf { it > 0 } ?: 0, opts.outHeight.takeIf { it > 0 } ?: 0)
        } catch (_: Exception) { Pair(0, 0) }
    }
}
