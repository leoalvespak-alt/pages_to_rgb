package com.pagestoaudio.gateway.camera

import android.util.Size

/**
 * Contrato exigido pelo PLANO_ANDROID_ONLY.md §0 e §3.1.
 *
 * Exatamente como no plano — não alterar assinatura sem atualizar o plano.
 */
enum class CaptureMode {
    /** Prova de baixa qualidade / 720p — quality 75 */
    PROBE,

    /** Qualidade máxima disponível — quality 92 */
    FULL
}

/**
 * Envelope produzido por qualquer CaptureSource, compatível com
 * ANDROID_GATEWAY_CONTRACT.md:86 (device_id, session_id, capture_id, frame_index,
 * resolução real, JPEG bytes, SHA-256, timestamp, orientação, estado da captura).
 */
data class CapturedFrame(
    val captureId: String,
    val frameIndex: Int,
    val sha256: String,
    val resolution: String, // "WxH" — ex: "1280x720"
    val bytes: ByteArray? = null,
    val filePath: String,
    val createdAt: Long, // epoch millis
    val orientation: Int, // Exif orientation constante (1,3,6,8) ou 0/90/180/270 normalizado
    val width: Int,
    val height: Int
) {
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (javaClass != other?.javaClass) return false
        other as CapturedFrame
        return captureId == other.captureId &&
            frameIndex == other.frameIndex &&
            sha256 == other.sha256
    }

    override fun hashCode(): Int {
        var result = captureId.hashCode()
        result = 31 * result + frameIndex
        result = 31 * result + sha256.hashCode()
        return result
    }
}

/**
 * Interface exigida literalmente pelo plano Etapa 2/3:
 * ```
 * interface CaptureSource { suspend fun capture(mode: CaptureMode): CapturedFrame; fun availableResolutions(): List<Size> }
 * ```
 */
interface CaptureSource {
    suspend fun capture(mode: CaptureMode): CapturedFrame
    fun availableResolutions(): List<Size>
}

/**
 * Extensão para captura com controle de sessão/captureId/frameIndex explícitos
 * (necessária para spool idempotente). Implementações devem oferecer este overload
 * além do capture(mode) básico para compatibilidade com o contrato.
 */
interface SessionAwareCaptureSource : CaptureSource {
    suspend fun capture(
        mode: CaptureMode,
        sessionId: String,
        captureId: String,
        frameIndex: Int
    ): CapturedFrame
}
