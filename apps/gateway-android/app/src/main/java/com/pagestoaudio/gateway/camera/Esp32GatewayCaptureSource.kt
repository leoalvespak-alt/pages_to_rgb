package com.pagestoaudio.gateway.camera

import android.util.Log
import android.util.Size
import kotlinx.coroutines.delay

/**
 * Stub para futura integração ESP32-CAM → Gateway (ports 8786/8787).
 *
 * Contrato: deve compilar e trocar com PhoneCameraCaptureSource sem quebrar build,
 * mas retorna erro controlado quando invocado (hardware não conectado).
 */
class Esp32GatewayCaptureSource(
    private val gatewayHost: String? = null,
    private val httpPort: Int = 8787,
    private val udpPort: Int = 8786
) : CaptureSource {

    companion object {
        private const val TAG = "Esp32GatewayCapture"
    }

    override fun availableResolutions(): List<Size> {
        Log.w(TAG, "ESP32 não conectado — availableResolutions() retorna vazio")
        return emptyList()
    }

    override suspend fun capture(mode: CaptureMode): CapturedFrame {
        Log.w(TAG, "ESP32 não conectado — capture(mode=$mode) rejeitado. Host=$gatewayHost ports $httpPort/$udpPort")
        // Sem sleep arbitrário — erro imediato e controlado
        throw Esp32NotConnectedException(
            "ESP32 não conectado. Selecione \"Câmera do celular\" ou conecte o hardware ESP32-CAM " +
                "(esperado em $gatewayHost:$httpPort / UDP $udpPort). Modo solicitado: $mode"
        )
    }

    /**
     * Overload session-aware — mesmo comportamento de erro controlado.
     */
    suspend fun capture(
        mode: CaptureMode,
        sessionId: String,
        captureId: String,
        frameIndex: Int
    ): CapturedFrame {
        Log.w(TAG, "ESP32 não conectado — capture session=$sessionId cap=$captureId idx=$frameIndex mode=$mode")
        throw Esp32NotConnectedException(
            "ESP32 não conectado (sessão $sessionId, captura $captureId). Verifique hardware e discovery UDP 8786."
        )
    }
}

/**
 * Erro controlado para UI exibir diálogo/aviso sem crash.
 */
class Esp32NotConnectedException(message: String, cause: Throwable? = null) : IllegalStateException(message, cause)
