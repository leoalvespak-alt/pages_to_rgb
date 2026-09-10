package com.pagestoaudio.gateway.domain

import com.pagestoaudio.gateway.BuildConfig

/**
 * Configuração do Gateway — base URL, identidades cloud/local e tuning.
 *
 * S01.3/A02: identidade cloud (gatewayId + gatewaySecret) é provisionada via
 * DataStore após hello/start e NUNCA usa segredo vazio como configuração
 * operacional. deviceId padrão é apenas placeholder de build — requireProvisioned()
 * deve ser verificado antes de permitir captura real.
 */
data class GatewayConfig(
    val baseUrl: String = "https://ptr.rotadeataque.com.br/api/v1/",
    val deviceId: String = "GW-ANDROID-001",
    val deviceSecret: String? = null,
    val gatewayId: String? = null,
    val gatewaySecret: String? = null,
    val captureSource: String = "ANDROID_CAMERA", // ANDROID_CAMERA | ESP32_CAMERA
    val maxFrameSizeBytes: Long = 10 * 1024 * 1024, // 10 MB
    val commandWaitMs: Long = 25000,
    val spoolPruneDays: Int = 7
) {
    init {
        require(baseUrl.endsWith("/")) { "baseUrl deve terminar com /" }
        require(deviceId.isNotBlank()) { "deviceId não pode ser vazio" }
        require(deviceId.matches(ESP_ID_RE)) { "deviceId fora do padrão ESP (1-63 alnum/_/-)" }
        gatewayId?.let { require(it.matches(ESP_ID_RE)) { "gatewayId fora do padrão ESP" } }
    }

    /** S01.3: captura real exige identidade cloud provisionada (nunca segredo vazio). */
    fun requireProvisioned() {
        require(!gatewayId.isNullOrBlank()) { "gatewayId não provisionado — valide a conexão antes de capturar" }
        require(!gatewaySecret.isNullOrBlank()) { "gatewaySecret não provisionado — valide a conexão antes de capturar" }
    }

    val isProvisioned: Boolean get() = !gatewayId.isNullOrBlank() && !gatewaySecret.isNullOrBlank()

    companion object {
        private val ESP_ID_RE = Regex("^[A-Za-z0-9_-]{1,63}$")

        fun isValidEspId(value: String): Boolean = ESP_ID_RE.matches(value)

        fun fromEnv(): GatewayConfig {
            // BuildConfig is generated from process-local build inputs. Release
            // builds receive the real gateway token through P2A_GATEWAY_SECRET;
            // no credential is stored in source control.
            return GatewayConfig(
                baseUrl = BuildConfig.GATEWAY_BASE_URL,
                deviceId = BuildConfig.GATEWAY_DEVICE_ID,
                gatewayId = BuildConfig.GATEWAY_ID.ifBlank { BuildConfig.GATEWAY_DEVICE_ID },
                gatewaySecret = BuildConfig.GATEWAY_SECRET.ifBlank { null },
            )
        }
    }
}
