package com.pagestoaudio.gateway.diag

/**
 * D02 — encaminhamento de diagnóstico (foto/clipe/prévia da ESP real).
 *
 * Reutiliza serviço local TLS, cliente cloud, fila durável e storage
 * existentes; implementa somente handlers/adaptações novas.
 *
 * Regras (contrato P2A-CAMERA-DIAG-2026-09-09):
 * - Associa diagnóstico a dispositivo real; NUNCA aciona CameraX por fallback.
 *   Origem sempre identificada como ESP física.
 * - Foto/clipe: fila durável existente com tipo/quota de diagnóstico
 *   (sem segunda implementação de spool). Preserva hash/identidade.
 * - Prévia: buffer limitado — 1 imagem em trânsito + no máx. 1 aguardando;
 *   descarta intermediárias, sem retry indefinido, sem acumular atraso.
 * - Encerra por prazo, STOP e perda de autorização. Recupera pendências
 *   duráveis sem reiniciar câmera após reboot.
 * - Feature flag desligada por padrão: diagnosticsEnabled=false.
 */
object DiagConfig {
    const val CAPABILITY = "camera_diagnostics_v1"
    var diagnosticsEnabled: Boolean = false

    // Quotas próprias (não tocam spool de missão).
    const val DIAG_QUEUE_MAX_ITEMS = 64
    const val DIAG_QUEUE_MAX_BYTES = 20L * 1024L * 1024L
    const val DIAG_MAX_ATTEMPTS = 8

    // Prévia: 1 em voo + 1 aguardando; resto descartado.
    const val PREVIEW_IN_FLIGHT_MAX = 1
    const val PREVIEW_QUEUED_MAX = 1

    // Janela de disponibilidade local (placa acordada recebe o pedido).
    const val AVAILABILITY_WINDOW_S = 120L
    // Heartbeat de controle a cada 10 s; expira após 30 s sem renovação.
    const val HEARTBEAT_S = 10L
    const val AUTHZ_TTL_S = 30L
}

enum class DiagMode { PHOTO, CLIP, PREVIEW }

data class DiagRequest(
    val diagnosticId: String,
    val deviceId: String,
    val mode: DiagMode,
    val resolution: String,
    val jpegQuality: Int,
    val durationS: Int,
    val maxFrames: Int,
    val deadlineMs: Long = System.currentTimeMillis() + durationS * 1000L,
)

data class DiagState(
    val active: Boolean = false,
    val request: DiagRequest? = null,
    val lastHeartbeatMs: Long = 0L,
    val inFlight: Int = 0,
    val queuedPreviewDropped: Int = 0,
)

/** Quota da fila de diagnóstico (contabiliza só itens diag_*). */
data class DiagQuota(val items: Int, val bytes: Long) {
    fun canAccept(bytes: Long): Boolean =
        items < DiagConfig.DIAG_QUEUE_MAX_ITEMS &&
            (this.bytes + bytes) <= DiagConfig.DIAG_QUEUE_MAX_BYTES
}
