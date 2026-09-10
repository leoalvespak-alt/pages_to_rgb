package com.pagestoaudio.gateway.network

import okhttp3.Interceptor
import okhttp3.Response

/**
 * Interceptor OkHttp que adiciona autenticação do Gateway em todas as requisições HTTPS
 * para o VPS, conforme INTEGRACAO_CONSOLIDADA §3 + servidor auth/gateway.py.
 *
 * Cloud: Authorization: Bearer <gateway-token> + X-Gateway-Id (obrigatórios).
 * Metadados: X-Device-Id, X-Firmware-Version, X-Capture-Source.
 * Nunca envia Bearer vazio (S01.3/A02): sem credencial provisionada a request
 * segue sem Authorization para o servidor responder 401 explícito.
 */
class GatewayAuthInterceptor(
    private val deviceIdProvider: () -> String,
    private val deviceSecretProvider: () -> String?,
    private val firmwareVersionProvider: () -> String = { "gateway-android/1.0.0" },
    private val gatewayIdProvider: () -> String? = { null },
    private val gatewaySecretProvider: (() -> String?)? = null
) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val original = chain.request()
        val deviceId = deviceIdProvider()
        val deviceSecret = deviceSecretProvider()
        val fw = firmwareVersionProvider()
        // S01.3: identidade cloud provisionada tem precedência sobre segredo legado.
        val gatewayId = gatewayIdProvider()
        val gatewaySecret = gatewaySecretProvider?.invoke() ?: deviceSecret

        val builder = original.newBuilder()
            .header("X-Device-Id", deviceId)
            .header("X-Firmware-Version", fw)
            .header("X-Capture-Source", "ANDROID_CAMERA")

        if (!gatewayId.isNullOrBlank()) {
            builder.header("X-Gateway-Id", gatewayId)
        }
        if (!gatewaySecret.isNullOrBlank()) {
            builder.header("Authorization", "Bearer $gatewaySecret")
        }

        return chain.proceed(builder.build())
    }
}
