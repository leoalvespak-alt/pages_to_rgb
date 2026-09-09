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

/**
 * C01 — discovery UDP 8786 no formato normativo LOCAL_PROTOCOL_V1.
 *
 * A ESP transmite `P2A_DISCOVER_V1 device=<id> nonce=<hex>` e aceita SOMENTE
 * `P2A_GATEWAY_V1 nonce=<eco> port=<porta>`. Resposta JSON anterior era
 * ignorada pelo firmware (RA01). Discovery é apenas localização, nunca
 * autenticação: segredo Bearer jamais trafega aqui.
 *
 * Anti-replay: (nonce, endereço) recentes são respondidos uma única vez por
 * janela; repetição dentro da janela é descartada sem resposta.
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
        const val LOCAL_PROTOCOL_VERSION = "P2A-LOCAL/1"
        private const val REPLAY_WINDOW_MS = 10_000L
        private const val REPLAY_MAX = 512
        private val DISCOVER_RE = Regex("^P2A_DISCOVER_V1 device=([A-Za-z0-9_-]{1,63}) nonce=([0-9a-fA-F]{1,16})$")
    }

    private var job: Job? = null
    // (nonce normalizado + endereço) → instante da resposta, para anti-replay.
    private val seen = LinkedHashMap<String, Long>()

    fun start() {
        if (job?.isActive == true) return
        job = scope.launch(Dispatchers.IO) {
            var socket: DatagramSocket? = null
            try {
                socket = DatagramSocket(udpPort).apply { broadcast = true }
                Log.i(TAG, "Discovery UDP ouvindo em $udpPort (P2A_GATEWAY_V1)")
                val buf = ByteArray(2048)
                while (isActive) {
                    try {
                        val packet = DatagramPacket(buf, buf.size)
                        socket.receive(packet)
                        val msg = String(packet.data, 0, packet.length, Charsets.US_ASCII).trim()
                        val reply = handleDiscover(msg, packet.address.hostAddress ?: "")
                        if (reply != null) {
                            val out = reply.toByteArray(Charsets.US_ASCII)
                            socket.send(DatagramPacket(out, out.size, packet.address, packet.port))
                        }
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

    /**
     * Retorna a resposta exata ou null (ignorar sem responder).
     * Visível para testes contratuais com os mesmos vetores do firmware.
     */
    fun handleDiscover(message: String, sender: String): String? {
        val m = DISCOVER_RE.matchEntire(message) ?: run {
            Log.w(TAG, "Discovery formato inválido de $sender")
            return null
        }
        val nonce = m.groupValues[2].lowercase()
        val key = "$nonce@$sender"
        val now = System.currentTimeMillis()
        synchronized(seen) {
            pruneLocked(now)
            if (seen.containsKey(key)) {
                Log.w(TAG, "Discovery replay descartado ($key)")
                return null
            }
            seen[key] = now
        }
        // Echo exato do nonce + porta do serviço local. Sem JSON, sem segredo.
        return "P2A_GATEWAY_V1 nonce=$nonce port=$httpsPort"
    }

    private fun pruneLocked(now: Long) {
        val it = seen.entries.iterator()
        while (it.hasNext()) {
            if (now - it.next().getValue() > REPLAY_WINDOW_MS) it.remove()
        }
        while (seen.size > REPLAY_MAX) {
            seen.entries.iterator().let { e -> if (e.hasNext()) { e.next(); e.remove() } }
        }
    }
}
