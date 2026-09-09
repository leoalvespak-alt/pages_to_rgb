package com.pagestoaudio.gateway.esp

import android.content.Context
import android.content.SharedPreferences
import android.util.Base64
import java.security.SecureRandom
import java.util.UUID

/**
 * S03.2 — provisionamento de confiança local e segredo por dispositivo.
 *
 * - Identidade estável do gateway (UUID persistido) — hotspot de IP variável
 *   não muda a identidade.
 * - Segredo por dispositivo (32 bytes aleatórios, Base64) guardado em
 *   SharedPreferences privado. Em build com androidx.security disponível,
 *   migrar para EncryptedSharedPreferences sem mudar esta interface.
 * - Discovery UDP nunca autentica (contrato §2); segredo só é exigido nos
 *   handlers HTTP após provisionamento.
 */
class EspProvisioning(context: Context) {

    private val prefs: SharedPreferences =
        context.getSharedPreferences("esp_provisioning", Context.MODE_PRIVATE)

    /** Identidade estável do gateway local. */
    fun gatewayId(): String {
        var id = prefs.getString("gateway_id", null)
        if (id.isNullOrBlank()) {
            id = "GW-" + UUID.randomUUID().toString().take(8).uppercase()
            prefs.edit().putString("gateway_id", id).apply()
        }
        return id!!
    }

    /** Segredo do dispositivo (criado uma vez, estável).
     *
     * C01: USO EXCLUSIVO do fluxo explícito de pareamento (tela do app).
     * NUNCA chamar a partir de rota HTTP não autenticada: nenhuma rota
     * protegida pode criar credencial por pedido não autenticado (RA02).
     */
    fun getOrCreateDeviceSecret(deviceId: String): String {
        val key = "dev_secret_$deviceId"
        var secret = prefs.getString(key, null)
        if (secret.isNullOrBlank()) {
            val bytes = ByteArray(32)
            SecureRandom().nextBytes(bytes)
            secret = Base64.encodeToString(bytes, Base64.NO_WRAP)
            prefs.edit().putString(key, secret).apply()
        }
        return secret!!
    }

    /** Valida credencial local por dispositivo (tempo constante). */
    fun validateDevice(deviceId: String, presented: String?): Boolean {
        if (deviceId.isBlank() || presented.isNullOrEmpty()) return false
        val expected = prefs.getString("dev_secret_$deviceId", null) ?: return false
        if (expected.length != presented.length) return false
        var diff = 0
        for (i in expected.indices) diff = diff or (expected[i].code xor presented[i].code)
        return diff == 0
    }

    fun isDeviceProvisioned(deviceId: String): Boolean =
        !prefs.getString("dev_secret_$deviceId", null).isNullOrBlank()

    /**
     * C01 — pareamento explícito: o operador digita na tela do app o mesmo
     * segredo compilado no firmware (`P2A_DEVICE_SECRET` em private_config.h).
     * É a única forma de criar credencial; rotas HTTP nunca criam.
     */
    fun importDeviceSecret(deviceId: String, secret: String): Boolean {
        if (!deviceId.matches(Regex("^[A-Za-z0-9_-]{1,63}$"))) return false
        if (secret.length < 16 || secret.length > 256) return false
        prefs.edit().putString("dev_secret_$deviceId", secret).apply()
        return true
    }

    /** Remove pareamento (revogação local imediata). */
    fun removeDevice(deviceId: String) {
        prefs.edit().remove("dev_secret_$deviceId").apply()
    }

    /** Dispositivos pareados (para a tela de pareamento; sem expor segredos). */
    fun listDevices(): List<String> =
        prefs.all.keys.mapNotNull { k ->
            if (k.startsWith("dev_secret_")) k.removePrefix("dev_secret_") else null
        }.sorted()
}
