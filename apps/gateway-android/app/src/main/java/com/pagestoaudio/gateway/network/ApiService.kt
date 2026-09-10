package com.pagestoaudio.gateway.network

import com.google.gson.annotations.SerializedName
import okhttp3.RequestBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

/**
 * Contrato Retrofit para o servidor Pages to Audio.
 *
 * Base URL configurável via GatewayConfig (ex: https://api.pagestoaudio.example/api/v1/).
 * Endpoints espelham apps/api/routers/gateway.py e gateway_rgb.py.
 */
interface ApiService {

    // ── Sessão ──────────────────────────────────────────────────────────────

    @POST("gateway/hello")
    suspend fun hello(@Body body: HelloRequest): Response<HelloResponse>

    @POST("gateway/session/start")
    suspend fun startSession(@Body body: StartSessionRequest): Response<StartSessionResponse>

    @GET("gateway/camera/capabilities")
    suspend fun getCameraCapabilities(
        @Query("device_code") deviceCode: String,
        @Header("X-Camera-Capabilities-Version") advertisedVersion: String? = null,
    ): Response<CameraCapabilitiesV1>

    @POST("gateway/session/{id}/heartbeat")
    suspend fun heartbeat(
        @Path("id") sessionId: String,
        @Body body: HeartbeatRequest? = null
    ): Response<HeartbeatResponse>

    @GET("gateway/session/{id}/policy")
    suspend fun getPolicy(@Path("id") sessionId: String): Response<CapturePolicyResponse>

    @GET("gateway/session/{id}/command")
    suspend fun getCommand(
        @Path("id") sessionId: String,
        @Query("cursor") cursor: Long,
        @Query("wait_ms") waitMs: Long = 25000,
        @Query("phase") phase: String = "CAPTURE"
    ): Response<CommandResponse>

    @POST("gateway/session/{id}/command/ack")
    suspend fun ackCommand(
        @Path("id") sessionId: String,
        @Body body: CommandAckRequest
    ): Response<Unit>

    // ── Upload de frame — multipart com JPEG bruto, headers X-* obrigatórios ─────

    @retrofit2.http.Multipart
    @POST("gateway/session/{id}/frame")
    suspend fun uploadFrame(
        @Path("id") sessionId: String,
        @Header("X-Capture-Id") captureId: String,
        @Header("X-Frame-Index") frameIndex: Int,
        @Header("X-SHA256") sha256: String,
        @Header("X-Resolution") resolution: String,
        @Header("X-Received-Android-At") receivedAt: String,
        @Header("X-Orientation") orientation: Int,
        @retrofit2.http.Part file: okhttp3.MultipartBody.Part
    ): Response<FrameUploadResponse>

    @POST("gateway/session/{id}/capture-complete")
    suspend fun captureComplete(
        @Path("id") sessionId: String,
        @Query("capture_id") captureId: String,
        @Query("received_frames") receivedFrames: Int
    ): Response<CaptureCompleteResponse>

    @POST("gateway/session/{id}/end-signal")
    suspend fun endSignal(
        @Path("id") sessionId: String,
        @Body body: EndSignalRequest = EndSignalRequest()
    ): Response<EndSignalResponse>

    // ── Resultado RGB ─────────────────────────────────────────────────────

    @GET("gateway/session/{id}/result")
    suspend fun getResult(
        @Path("id") sessionId: String,
        @Query("device_id") deviceId: String,
        @Query("cursor") cursor: Long = 0
    ): Response<SessionResultResponse>

    @GET("gateway/session/{id}/rgb-sequence")
    suspend fun getRgbSequence(
        @Path("id") sessionId: String,
        @Query("device_id") deviceId: String,
        @Query("sequence_id") sequenceId: String? = null
    ): Response<RgbSequenceResponse>

    @GET("gateway/session/{id}/rgb-test")
    suspend fun getRgbTest(
        @Path("id") sessionId: String,
        @Query("after_id") afterId: Int = 0
    ): Response<RgbTestCommandResponse?>

    @POST("gateway/session/{id}/rgb-sequence/event")
    suspend fun postRgbEvent(
        @Path("id") sessionId: String,
        @Body body: RgbEventRequest
    ): Response<RgbEventResponse>

    // ── Comandos RGB físicos por dispositivo ──────────────────────────────

    @GET("gateway/devices/{device_id}/commands")
    suspend fun getDeviceRgbCommands(
        @Path("device_id") deviceId: String,
        @Query("after") after: Long = 0
    ): Response<RgbDeviceCommandPage>

    @POST("gateway/devices/{device_id}/commands/{command_id}/events")
    suspend fun postDeviceRgbEvent(
        @Path("device_id") deviceId: String,
        @Path("command_id") commandId: String,
        @Header("Idempotency-Key") idempotencyKey: String,
        @Body body: RgbDeviceEventRequest
    ): Response<RgbDeviceCommandResponse>

    // ── Handwritten (isolado de /gateway, 10 fotos) ────────────────

    @POST("handwritten/session/start")
    suspend fun startHandwrittenSession(@Body body: HandwrittenStartRequest): Response<HandwrittenStartResponse>

    @retrofit2.http.Multipart
    @POST("handwritten/session/{id}/frame")
    suspend fun uploadHandwrittenFrame(
        @Path("id") sessionId: String,
        @Header("X-Capture-Id") captureId: String,
        @Header("X-Frame-Index") frameIndex: Int,
        @Header("X-SHA256") sha256: String,
        @Header("X-Resolution") resolution: String,
        @Header("X-Received-Android-At") receivedAt: String,
        @Header("X-Orientation") orientation: Int,
        @retrofit2.http.Part file: okhttp3.MultipartBody.Part
    ): Response<FrameUploadResponse>

    @POST("handwritten/session/{id}/capture-complete")
    suspend fun captureCompleteHandwritten(
        @Path("id") sessionId: String,
        @Query("capture_id") captureId: String,
        @Query("received_frames") receivedFrames: Int
    ): Response<CaptureCompleteResponse>

    @POST("handwritten/session/{id}/end-signal")
    suspend fun endSignalHandwritten(
        @Path("id") sessionId: String,
        @Body body: EndSignalRequest = EndSignalRequest()
    ): Response<EndSignalResponse>

    @GET("handwritten/session/{id}/command")
    suspend fun getHandwrittenCommand(
        @Path("id") sessionId: String,
        @Query("cursor") cursor: Long,
        @Query("wait_ms") waitMs: Long = 25000,
        @Query("phase") phase: String = "CAPTURE"
    ): Response<CommandResponse>

    @GET("handwritten/session/{id}/policy")
    suspend fun getHandwrittenPolicy(@Path("id") sessionId: String): Response<CapturePolicyResponse>

    @GET("handwritten/session/{id}/summary")
    suspend fun getHandwrittenSummary(@Path("id") sessionId: String): Response<HandwrittenSummaryResponse>
}

// ── DTOs ──────────────────────────────────────────────────────────────────

data class HelloRequest(
    @SerializedName("gateway_code") val gatewayCode: String,
    @SerializedName("app_version") val appVersion: String = "1.0.0",
    @SerializedName("device_model") val deviceModel: String? = null
)

data class HelloResponse(
    @SerializedName("server_version") val serverVersion: String? = null,
    @SerializedName("contract_version") val contractVersion: String? = null,
    @SerializedName("capabilities") val capabilities: List<String> = emptyList()
)

data class StartSessionRequest(
    @SerializedName("device_code") val deviceCode: String,
    @SerializedName("capture_source") val captureSource: String = "ANDROID_CAMERA",
    @SerializedName("allow_new_session") val allowNewSession: Boolean = true,
    @SerializedName("resume_hint") val resumeHint: String? = null,
    @SerializedName("resume_requested") val resumeRequested: Boolean = false,
    @SerializedName("last_session_id") val lastSessionId: String? = null,
    @SerializedName("gateway_code") val gatewayCode: String? = null,
    @SerializedName("reset_reason") val resetReason: String? = null,
    @SerializedName("trigger") val trigger: String? = null,
    @SerializedName("camera_mode") val cameraMode: String = "OCR",
    @SerializedName("camera_capabilities_version") val cameraCapabilitiesVersion: String? = null,
)

data class StartSessionResponse(
    @SerializedName("session_id") val sessionId: String,
    @SerializedName("cursor") val cursor: Long = 0,
    @SerializedName("resumed") val resumed: Boolean = false,
    @SerializedName("status") val status: String? = null,
    @SerializedName("camera_profile_revision_id") val cameraProfileRevisionId: String? = null,
    @SerializedName("camera_profile_snapshot") val cameraProfileSnapshot: CameraProfileSnapshot? = null,
    @SerializedName("requested_camera_config") val requestedCameraConfig: CameraConfigV2? = null,
    @SerializedName("effective_camera_config") val effectiveCameraConfig: CameraConfigV2? = null,
    @SerializedName("firmware_version") val firmwareVersion: String? = null,
    @SerializedName("capabilities_version") val capabilitiesVersion: String? = null,
)

data class CameraCapabilitiesV1(
    @SerializedName("version") val version: String = "v1",
    @SerializedName("contract_version") val contractVersion: String = "v2",
    @SerializedName("firmware_version") val firmwareVersion: String? = null,
    @SerializedName("driver_version") val driverVersion: String? = null,
    @SerializedName("available") val available: Map<String, Any> = emptyMap(),
    @SerializedName("protected") val protected: Map<String, Any> = emptyMap(),
    @SerializedName("unavailable") val unavailable: Map<String, String> = emptyMap(),
    @SerializedName("feature_enabled") val featureEnabled: Boolean = false,
    @SerializedName("compatible") val compatible: Boolean = false,
    @SerializedName("reason_code") val reasonCode: String? = null,
    @SerializedName("message") val message: String = "",
)

data class CameraProfileSnapshot(
    @SerializedName("mode") val mode: String? = null,
    @SerializedName("revision") val revision: Int? = null,
    @SerializedName("public_id") val publicId: String? = null,
    @SerializedName("capabilities_version") val capabilitiesVersion: String? = null,
    @SerializedName("config") val config: CameraConfigV2? = null,
)

data class CameraConfigV2(
    @SerializedName("frame_size") val frameSize: String? = null,
    @SerializedName("esp_jpeg_quality") val espJpegQuality: Int? = null,
    @SerializedName("frame_count") val frameCount: Int? = null,
    @SerializedName("intra_frame_gap_ms") val intraFrameGapMs: Int? = null,
    @SerializedName("page_interval_ms") val pageIntervalMs: Int? = null,
    @SerializedName("android_jpeg_quality_percent") val androidJpegQualityPercent: Int? = null,
    @SerializedName("brightness") val brightness: Int? = null,
    @SerializedName("contrast") val contrast: Int? = null,
    @SerializedName("saturation") val saturation: Int? = null,
    @SerializedName("awb") val awb: Boolean? = null,
    @SerializedName("awb_gain") val awbGain: Boolean? = null,
    @SerializedName("wb_mode") val wbMode: String? = null,
    @SerializedName("aec") val aec: Boolean? = null,
    @SerializedName("aec2") val aec2: Boolean? = null,
    @SerializedName("agc") val agc: Boolean? = null,
    @SerializedName("bpc") val bpc: Boolean? = null,
    @SerializedName("wpc") val wpc: Boolean? = null,
    @SerializedName("raw_gamma") val rawGamma: Boolean? = null,
    @SerializedName("lens_correction") val lensCorrection: Boolean? = null,
    @SerializedName("dcw") val dcw: Boolean? = null,
    @SerializedName("hmirror") val hmirror: Boolean? = null,
    @SerializedName("vflip") val vflip: Boolean? = null,
    @SerializedName("special_effect") val specialEffect: String? = null,
    @SerializedName("colorbar") val colorbar: Boolean? = null,
)

data class HeartbeatRequest(
    @SerializedName("device_id") val deviceId: String,
    @SerializedName("phase") val phase: String = "CAPTURE",
    @SerializedName("cursor") val cursor: Long = 0
)

data class HeartbeatResponse(
    @SerializedName("policy_valid") val policyValid: Boolean = true,
    @SerializedName("last_seen_at") val lastSeenAt: String? = null
)

data class CapturePolicyResponse(
    @SerializedName("version") val version: String,
    @SerializedName("lease_id") val leaseId: String,
    @SerializedName("valid_until") val validUntil: String,
    @SerializedName("probe_interval_ms") val probeIntervalMs: Int,
    @SerializedName("probe_resolution") val probeResolution: String,
    @SerializedName("probe_jpeg_quality") val probeJpegQuality: Int,
    @SerializedName("stable_probe_count") val stableProbeCount: Int,
    @SerializedName("full_frames") val fullFrames: Int,
    @SerializedName("full_resolution") val fullResolution: String,
    @SerializedName("full_jpeg_quality") val fullJpegQuality: Int,
    @SerializedName("full_gap_ms") val fullGapMs: Int,
    @SerializedName("expected_pages") val expectedPages: Int,
    @SerializedName("end") val end: EndPolicy? = null
)

data class EndPolicy(
    @SerializedName("manual_enabled") val manualEnabled: Boolean = true,
    @SerializedName("visual_marker_enabled") val visualMarkerEnabled: Boolean = true,
    @SerializedName("open_hand_enabled") val openHandEnabled: Boolean = true,
    @SerializedName("soft_idle_seconds") val softIdleSeconds: Int = 30,
    @SerializedName("hard_idle_seconds") val hardIdleSeconds: Int = 120
)

data class PolicyProfile(
    @SerializedName("resolution") val resolution: String, // "1280x720" | "highest_available"
    @SerializedName("quality") val quality: Int
)

data class CommandResponse(
    @SerializedName("command") val command: String, // CAPTURE_PROBE | CAPTURE_FULL | PAUSE | RESUME | PING | STOP (fechado no servidor)
    @SerializedName("cursor") val cursor: Long,
    @SerializedName("session_id") val sessionId: String? = null,
    @SerializedName("capture_id") val captureId: String? = null,
    @SerializedName("frames") val frames: Int = 1,
    @SerializedName("gap_ms") val gapMs: Long = 180,
    @SerializedName("frame_size") val frameSize: String? = null,
    @SerializedName("jpeg_quality") val jpegQuality: Int? = null
)

data class CommandAckRequest(
    @SerializedName("cursor") val cursor: Long
)

data class FrameUploadResponse(
    @SerializedName("ok") val ok: Boolean = true,
    @SerializedName("storage_key") val storageKey: String? = null,
    @SerializedName("duplicate") val duplicate: Boolean = false,
    @SerializedName("frame_id") val frameId: String? = null
)

data class CaptureCompleteRequest(
    @SerializedName("capture_id") val captureId: String,
    @SerializedName("frames") val frames: Int,
    @SerializedName("device_id") val deviceId: String
)

data class CaptureCompleteResponse(
    @SerializedName("ok") val ok: Boolean = true
)

data class EndSignalRequest(
    @SerializedName("reason") val reason: String = "user_requested"
)

data class EndSignalResponse(
    @SerializedName("ok") val ok: Boolean = true,
    @SerializedName("status") val status: String? = null
)

data class SessionResultResponse(
    // S01.1/A03: servidor usa `command` (não `status`); string de respostas "ABCDE".
    @SerializedName("command") val command: String, // RESULT_NOT_STARTED | RESULT_PROCESSING | RGB_SEQUENCE_READY | RESULT_CANCELLED
    @SerializedName("cursor") val cursor: Long = 0,
    @SerializedName("session_id") val sessionId: String? = null,
    @SerializedName("sequence_id") val sequenceId: String? = null,
    @SerializedName("revision") val revision: Int? = null,
    @SerializedName("item_count") val itemCount: Int? = null,
    @SerializedName("sha256") val sha256: String? = null
)

data class RgbSequenceResponse(
    @SerializedName("schema_version") val schemaVersion: Int = 1,
    @SerializedName("session_id") val sessionId: String? = null,
    @SerializedName("sequence_id") val sequenceId: String,
    @SerializedName("revision") val revision: Int,
    // S01.1/A03: protocolo usa string contígua "ABCDE" (não lista).
    @SerializedName("answers") val answers: String,
    @SerializedName("sha256") val sha256: String,
    @SerializedName("item_count") val itemCount: Int? = null,
    @SerializedName("palette") val palette: Map<String, Any>? = null
)

data class RgbTestCommandResponse(
    @SerializedName("command_id") val commandId: Int,
    @SerializedName("rgb") val rgb: List<Int>,
    @SerializedName("brightness_percent") val brightnessPercent: Int,
    @SerializedName("on_ms") val onMs: Long,
    @SerializedName("off_ms") val offMs: Long
)

data class RgbDeviceCommandPage(
    @SerializedName("items") val items: List<RgbDeviceCommand> = emptyList(),
    @SerializedName("cursor") val cursor: Long = 0,
)

data class RgbDeviceCommand(
    @SerializedName("command_id") val commandId: String,
    @SerializedName("device_code") val deviceCode: String,
    @SerializedName("session_id") val sessionId: String? = null,
    @SerializedName("kind") val kind: String = "TEST",
    @SerializedName("status") val status: String,
    @SerializedName("requested") val requested: Map<String, Any> = emptyMap(),
    @SerializedName("effective") val effective: Map<String, Any> = emptyMap(),
    @SerializedName("expires_at") val expiresAt: String,
    @SerializedName("failure_reason") val failureReason: String? = null,
    @SerializedName("idempotent") val idempotent: Boolean = false,
)

data class RgbDeviceEventRequest(
    @SerializedName("event") val event: String,
    @SerializedName("effective_payload") val effectivePayload: Map<String, Any> = emptyMap(),
    @SerializedName("payload") val payload: Map<String, Any> = emptyMap(),
    @SerializedName("firmware_version") val firmwareVersion: String? = null,
    @SerializedName("device_timestamp") val deviceTimestamp: String? = null,
)

data class RgbDeviceCommandResponse(
    @SerializedName("command_id") val commandId: String? = null,
    @SerializedName("status") val status: String? = null,
)

data class RgbEventRequest(
    @SerializedName("device_id") val deviceId: String,
    @SerializedName("session_id") val sessionId: String,
    @SerializedName("sequence_id") val sequenceId: String,
    @SerializedName("revision") val revision: Int,
    @SerializedName("event") val event: String, // RECEIVED | STARTED | RESUMED | COMPLETED | INVALID
    @SerializedName("next_index") val nextIndex: Int,
    @SerializedName("item_count") val itemCount: Int
)

data class RgbEventResponse(
    @SerializedName("ok") val ok: Boolean = true,
    @SerializedName("duplicate") val duplicate: Boolean = false
)

data class HandwrittenStartRequest(
    @SerializedName("device_code") val deviceCode: String,
    @SerializedName("expected_words") val expectedWords: Int? = null,
    @SerializedName("gateway_code") val gatewayCode: String? = null,
    @SerializedName("capture_source") val captureSource: String = "ANDROID_CAMERA"
)

data class HandwrittenStartResponse(
    @SerializedName("session_id") val sessionId: String,
    @SerializedName("status") val status: String? = null,
    @SerializedName("session_type") val sessionType: String = "HANDWRITTEN_WORD",
    @SerializedName("expected_words") val expectedWords: Int = 10
)

data class HandwrittenSummaryResponse(
    @SerializedName("session_id") val sessionId: String,
    @SerializedName("status") val status: String,
    @SerializedName("session_type") val sessionType: String = "HANDWRITTEN_WORD",
    @SerializedName("frames_count") val framesCount: Int = 0,
    @SerializedName("answers") val answers: List<HandwrittenAnswerItem> = emptyList(),
    @SerializedName("delivery") val delivery: Any? = null,
    @SerializedName("rgb_sequence") val rgbSequence: Any? = null
)

data class HandwrittenAnswerItem(
    @SerializedName("question_number") val questionNumber: Int,
    @SerializedName("answer") val answer: String? = null,
    @SerializedName("word") val word: String? = null,
    @SerializedName("validated") val validated: Boolean = false,
    @SerializedName("color") val color: Map<String, Any>? = null
)
