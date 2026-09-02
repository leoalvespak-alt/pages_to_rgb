package com.pagestoaudio.gateway.network

import okhttp3.Dns
import java.net.InetAddress
import java.net.UnknownHostException

/**
 * Preserva o resolvedor configurado no Android e só usa o alternativo quando
 * o sistema declara que não consegue resolver o host.
 */
class FallbackDns(
    private val primary: Dns,
    private val fallback: Dns,
    private val onFallback: (String, UnknownHostException) -> Unit = { _, _ -> }
) : Dns {
    override fun lookup(hostname: String): List<InetAddress> = try {
        primary.lookup(hostname)
    } catch (failure: UnknownHostException) {
        onFallback(hostname, failure)
        fallback.lookup(hostname)
    }
}
