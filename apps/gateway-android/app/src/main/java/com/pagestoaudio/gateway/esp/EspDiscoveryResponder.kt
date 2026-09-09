package com.pagestoaudio.gateway.esp

import android.util.Log
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.SocketException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONObject

/**
 * S03.1 — discovery UDP 8786 (apenas localização, nunca autenticação).
 *
 * Anuncia esquema/capacidades/identidade. Segredo Bearer nunca trafega aqui.
 */
class EspDiscoveryResponder(
    private val provisioning: EspProvisioning,
    private val scope: CoroutineScope,
    private val udpPort: Int = 8786,
    private val httpsPort: Int = 8787
) {
    companion object {
        private const val TAG = "EspDiscovery"
        const val INTEGRATION_VERSION = "P2A-INTEGRACAO-2026-09-09/r1"
    }

    private var job: Job? = null

    fun start() {
        if (job?.isActive == true) return
        job = scope.launch(Dispatchers.IO) {
            var socket: DatagramSocket? = null
            try {
                socket = DatagramSocket(udpPort).apply { broadcast = true }
                Log.i(TAG, "Discovery UDP ouvindo em $udpPort")
                val buf = ByteArray(2048)
                while (isActive) {
                    try {
                        val packet = DatagramPacket(buf, buf.size)
                        socket.receive(packet)
                        val reply = JSONObject()
                            .put("schema", "p2a-esp/1")
                            .put("integration", INTEGRATION_VERSION)
                            .put("gateway_id", provisioning.gatewayId())
                            .put("https_port", httpsPort)
                            .put("capabilities", org.json.JSONArray(listOf("frame", "capture-complete", "command", "result", "event")))
                            .toString()
                        val out = reply.toByteArray()
                        socket.send(DatagramPacket(out, out.size, packet.address, packet.port))
                    } catch (e: SocketException) {
                        if (!isActive) break
                        Log.w(TAG, "Discovery socket erro", e)
                    } catch (e: Exception) {
                        Log.w(TAG, "Discovery pacote ignorado", e)
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Discovery não iniciou em $udpPort", e)
            } finally {
                try { socket?.close() } catch (_: Exception) {}
            }
        }
    }

    fun stop() {
        job?.cancel()
        job = null
    }
}
