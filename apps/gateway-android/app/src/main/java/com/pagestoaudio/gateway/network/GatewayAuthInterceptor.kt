package com.pagestoaudio.gateway.network

import okhttp3.Interceptor
import okhttp3.Response

/**
 * Interceptor OkHttp que adiciona autenticação do Gateway em todas as requisições HTTPS
 * para o VPS, conforme ANDROID_GATEWAY_CONTRACT.md (X-Device-Id, Authorization, X-Firmware-Version).
 *
 * O hotspot WPA2 protege o enlace local; o Android deve usar HTTPS/TLS nas chamadas para o VPS.
 */
class GatewayAuthInterceptor(
    private val deviceIdProvider: () -> String,
    private val deviceSecretProvider: () -> String?,
    private val firmwareVersionProvider: () -> String = { "gateway-android/1.0.0" }
) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val original = chain.request()
        val deviceId = deviceIdProvider()
        val secret = deviceSecretProvider()
        val fw = firmwareVersionProvider()

        val builder = original.newBuilder()
            .header("X-Device-Id", deviceId)
            .header("X-Firmware-Version", fw)
            .header("X-Capture-Source", "ANDROID_CAMERA")

        if (!secret.isNullOrBlank()) {
            builder.header("Authorization", "Bearer $secret")
        }

        return chain.proceed(builder.build())
    }
}
