package com.pagestoaudio.gateway.domain

/**
 * Configuração do Gateway — base URL, device identity e tuning.
 *
 * Persistida via DataStore em implementação completa; aqui modelo puro.
 */
data class GatewayConfig(
    val baseUrl: String = "https://api.pagestoaudio.example/api/v1/",
    val deviceId: String = "GW-ANDROID-001",
    val deviceSecret: String? = null,
    val captureSource: String = "ANDROID_CAMERA", // ANDROID_CAMERA | ESP32_CAMERA
    val maxFrameSizeBytes: Long = 10 * 1024 * 1024, // 10 MB
    val commandWaitMs: Long = 25000,
    val spoolPruneDays: Int = 7
) {
    init {
        require(baseUrl.endsWith("/")) { "baseUrl deve terminar com /" }
        require(deviceId.isNotBlank()) { "deviceId não pode ser vazio" }
    }

    companion object {
        fun fromEnv(): GatewayConfig {
            // Em build real, ler de BuildConfig ou DataStore
            return GatewayConfig()
        }
    }
}
