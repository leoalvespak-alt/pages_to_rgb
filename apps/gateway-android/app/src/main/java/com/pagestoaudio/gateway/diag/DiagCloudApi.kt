package com.pagestoaudio.gateway.diag

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import org.json.JSONObject
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * D02 — cliente cloud do diagnóstico (reutiliza base URL/token do app).
 *
 * Endpoints (contrato §5): claim, event, frame (durável), preview
 * (transitório), ack. Nunca expõe segredo da ESP nem token cloud ao browser.
 */
class DiagCloudApi(
    private val baseUrl: String,
    private val gatewayId: String,
    private val bearer: () -> String,
    client: OkHttpClient? = null,
) : CameraDiagnosticsForwarder.DiagCloudBridge {
    companion object {
        private const val TAG = "DiagCloud"
    }

    private val http: OkHttpClient = client ?: OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    // GatewayConfig normally already ends in /api/v1/.  Normalize once so
    // diagnostics never call /api/v1/api/v1/... when the app is configured
    // with the canonical cloud base URL.
    private val apiRoot: String = baseUrl.trimEnd('/').let {
        if (it.endsWith("/api/v1")) it else "$it/api/v1"
    }

    suspend fun pending(deviceCode: String): List<DiagRequest> = withContext(Dispatchers.IO) {
        val url = "$apiRoot/gateway/diagnostics/pending?device_code=$deviceCode"
        val req = Request.Builder().url(url).get()
            .apply { headers().forEach { (k, v) -> header(k, v) } }.build()
        http.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) return@withContext emptyList()
            val root = JSONObject(resp.body?.string().orEmpty())
            val items = root.optJSONArray("pending") ?: return@withContext emptyList()
            buildList {
                for (i in 0 until items.length()) {
                    val item = items.optJSONObject(i) ?: continue
                    val mode = runCatching {
                        DiagMode.valueOf(item.optString("mode", "PHOTO"))
                    }.getOrDefault(DiagMode.PHOTO)
                    add(
                        DiagRequest(
                            diagnosticId = item.optString("diagnostic_id"),
                            deviceId = deviceCode,
                            mode = mode,
                            resolution = item.optString("resolution", "SVGA"),
                            jpegQuality = item.optInt("jpeg_quality", 18),
                            durationS = item.optInt("duration_s", 60).coerceIn(1, 60),
                            maxFrames = item.optInt("max_frames", 1).coerceIn(1, 60),
                        )
                    )
                }
            }
        }
    }

    private fun headers(): Map<String, String> = mapOf(
        "Authorization" to "Bearer ${bearer()}",
        "X-Gateway-Id" to gatewayId,
    )

    override suspend fun claim(diagnosticId: String): Boolean = withContext(Dispatchers.IO) {
        val body = JSONObject().put("capabilities", org.json.JSONArray(listOf(DiagConfig.CAPABILITY))).toString()
        val req = Request.Builder()
            .url("$apiRoot/gateway/diagnostics/$diagnosticId/claim")
            .post(okhttp3.RequestBody.create("application/json".toMediaType(), body))
            .apply { headers().forEach { (k, v) -> header(k, v) } }
            .build()
        http.newCall(req).execute().use { it.isSuccessful }
    }

    override suspend fun uploadFrame(
        diagnosticId: String, frameIndex: Int, sha: String, file: File,
        capturedMonoMs: Long, width: Int, height: Int,
    ): CameraDiagnosticsForwarder.CloudAck = withContext(Dispatchers.IO) {
        postJpeg("$apiRoot/gateway/diagnostics/$diagnosticId/frame",
            diagnosticId, frameIndex, sha, file, capturedMonoMs, width, height)
    }

    override suspend fun uploadPreview(
        diagnosticId: String, frameIndex: Int, sha: String, file: File,
        capturedMonoMs: Long, width: Int, height: Int,
    ): CameraDiagnosticsForwarder.CloudAck = withContext(Dispatchers.IO) {
        postJpeg("$apiRoot/gateway/diagnostics/$diagnosticId/preview",
            diagnosticId, frameIndex, sha, file, capturedMonoMs, width, height)
    }

    private fun postJpeg(
        url: String, diagnosticId: String, frameIndex: Int, sha: String, file: File,
        capturedMonoMs: Long, width: Int, height: Int,
    ): CameraDiagnosticsForwarder.CloudAck {
        val part = MultipartBody.Part.createFormData(
            "file", file.name, file.asRequestBody("image/jpeg".toMediaType()))
        val body = MultipartBody.Builder().setType(MultipartBody.FORM).addPart(part).build()
        val req = Request.Builder()
            .url(url)
            .post(body)
            .header("Authorization", "Bearer ${bearer()}")
            .header("X-Gateway-Id", gatewayId)
            .header("X-Frame-Index", frameIndex.toString())
            .header("X-SHA256", sha)
            .header("X-Captured-Mono-Ms", capturedMonoMs.toString())
            .header("X-Width", width.toString())
            .header("X-Height", height.toString())
            .build()
        http.newCall(req).execute().use { resp ->
            val dup = resp.code == 208
            return CameraDiagnosticsForwarder.CloudAck(resp.isSuccessful || dup, dup)
        }
    }

    override suspend fun event(diagnosticId: String, event: String, reason: String?): Boolean =
        withContext(Dispatchers.IO) {
            try {
                val body = JSONObject().put("event", event)
                    .put("reason", reason ?: JSONObject.NULL).toString()
                val req = Request.Builder()
                    .url("$apiRoot/gateway/diagnostics/$diagnosticId/event")
                    .post(okhttp3.RequestBody.create("application/json".toMediaType(), body))
                    .apply { headers().forEach { (k, v) -> header(k, v) } }
                    .build()
                http.newCall(req).execute().use { it.isSuccessful }
            } catch (e: Exception) {
                Log.w(TAG, "event falhou", e)
                false
            }
        }

    override suspend fun ack(diagnosticId: String): Boolean = withContext(Dispatchers.IO) {
        try {
            val req = Request.Builder()
                .url("$apiRoot/gateway/diagnostics/$diagnosticId/ack")
                .post(okhttp3.RequestBody.create("application/json".toMediaType(), "{}"))
                .apply { headers().forEach { (k, v) -> header(k, v) } }
                .build()
            http.newCall(req).execute().use { it.isSuccessful }
        } catch (e: Exception) {
            Log.w(TAG, "ack falhou", e)
            false
        }
    }
}
