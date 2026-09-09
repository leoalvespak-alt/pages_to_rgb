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
import java.nio.charset.Charsets
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
        suspend fun startForDevice(deviceId: String, resumeHint: Boolean, lastSessionId: String?): CloudSession
        suspend fun enqueueCloudUpload(frame: PendingFrame)
        suspend fun cloudCaptureComplete(sessionId: String, captureId: String, frames: Int): Boolean
        suspend fun cloudCommand(sessionId: String, cursor: Long): CloudCommand?
        suspend fun cloudResult(sessionId: String, cursor: Long): String?
    }

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
                    req.method == "POST" && path == "/v1/device/start" -> deviceStart(req)
                    req.method == "POST" && path == "/v1/device/frame" -> deviceFrame(req)
                    req.method == "POST" && path == "/v1/device/capture-complete" -> deviceCaptureComplete(req)
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
        val body = JSONObject()
            .put("schema", "p2a-esp/1")
            .put("gateway_id", provisioning.gatewayId())
            .put("capabilities", org.json.JSONArray(listOf("frame", "capture-complete", "command", "result", "event")))
        return 200 to body.toString()
    }

    private suspend fun deviceStart(req: HttpRequest): Pair<Int, String> {
        val json = try { JSONObject(req.bodyAsText()) } catch (_: Exception) {
            return 400 to JSONObject().put("error", "invalid json").toString()
        }
        val deviceId = json.optString("device_id", "")
        if (!isValidEspId(deviceId)) return 422 to JSONObject().put("error", "invalid device_id").toString()
        val resumeHint = json.optBoolean("resume_hint", false)
        val lastSessionId = json.optString("last_session_id", null)?.takeIf { it.isNotBlank() }
        // Provisiona segredo do dispositivo no primeiro contato em bancada; em
        // produção exige provisionamento prévio (sem fallback inseguro automático).
        if (!provisioning.isDeviceProvisioned(deviceId)) {
            provisioning.getOrCreateDeviceSecret(deviceId)
        }
        return try {
            val session = cloud.startForDevice(deviceId, resumeHint, lastSessionId)
            deviceSessions[deviceId] = session
            200 to JSONObject()
                .put("session_id", session.sessionId)
                .put("resumed", session.resumed)
                .put("cursor", session.cursor)
                .put("gateway_id", provisioning.gatewayId())
                .toString()
        } catch (e: Exception) {
            Log.w(TAG, "deviceStart falhou", e)
            503 to JSONObject().put("error", "cloud unavailable").toString()
        }
    }

    private suspend fun deviceFrame(req: HttpRequest): Pair<Int, String> {
        // S03.6: valida limites antes de aceitar; JPEG real verificado.
        val deviceId = req.headers["x-device-id"] ?: ""
        val secret = req.headers["authorization"]?.removePrefix("Bearer ")?.trim()
        if (!provisioning.validateDevice(deviceId, secret)) {
            return 401 to JSONObject().put("error", "unauthorized device").toString()
        }
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
        val cursor = req.query["cursor"]?.toLongOrNull() ?: 0L
        val session = deviceSessions[deviceId]
            ?: return 409 to JSONObject().put("error", "no session").toString()
        val cmd = try { cloud.cloudCommand(session.sessionId, cursor) } catch (_: Exception) { null }
            ?: return 200 to JSONObject().put("command", "PING").put("cursor", cursor).toString()
        return 200 to JSONObject()
            .put("command", cmd.command)
            .put("cursor", cmd.cursor)
            .put("payload", JSONObject(cmd.payload))
            .toString()
    }

    private suspend fun deviceResult(req: HttpRequest): Pair<Int, String> {
        val deviceId = req.query["device_id"] ?: ""
        val cursor = req.query["cursor"]?.toLongOrNull() ?: 0L
        val session = deviceSessions[deviceId]
            ?: return 409 to JSONObject().put("error", "no session").toString()
        val result = try { cloud.cloudResult(session.sessionId, cursor) } catch (_: Exception) { null }
            ?: return 204 to ""
        return 200 to result
    }

    private fun deviceEvent(req: HttpRequest): Pair<Int, String> {
        // Eventos locais persistidos antes de confirmar ao firmware quando há
        // transferência de responsabilidade (S03.8): grava em outbox-arquivo.
        return try {
            val json = JSONObject(req.bodyAsText())
            val deviceId = json.optString("device_id", "")
            if (!isValidEspId(deviceId)) return 422 to JSONObject().put("error", "invalid device").toString()
            val outbox = File(filesDir, "esp_outbox").apply { mkdirs() }
            val name = "evt-${System.currentTimeMillis()}-${(0..9999).random()}.json"
            File(outbox, name).writeText(json.toString(), Charsets.UTF_8)
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
        fun bodyAsText(): String = body.toString(Charsets.UTF_8)
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
        val headerText = headerBytes.toByteArray().toString(Charsets.UTF_8)
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
        val bytes = body.toByteArray(Charsets.UTF_8)
        val status = when (code) {
            200 -> "OK"; 201 -> "Created"; 202 -> "Accepted"; 204 -> "No Content"; 208 -> "Already Reported"
            400 -> "Bad Request"; 401 -> "Unauthorized"; 404 -> "Not Found"
            409 -> "Conflict"; 413 -> "Content Too Large"; 415 -> "Unsupported Media Type"
            422 -> "Unprocessable Entity"; 500 -> "Internal Error"; 503 -> "Unavailable"
            else -> "OK"
        }
        val head = "HTTP/1.1 $code $status\r\nContent-Type: application/json\r\nContent-Length: ${bytes.size}\r\nConnection: close\r\n\r\n"
        val out = socket.getOutputStream()
        out.write(head.toByteArray(Charsets.UTF_8))
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
