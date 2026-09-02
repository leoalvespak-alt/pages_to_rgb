package com.pagestoaudio.gateway.network

import okhttp3.Dns
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.net.InetAddress
import java.net.UnknownHostException

class FallbackDnsTest {
    @Test
    fun `uses primary result without querying fallback`() {
        val expected = listOf(InetAddress.getByAddress(byteArrayOf(10, 0, 0, 1)))
        var fallbackCalled = false
        val dns = FallbackDns(
            primary = object : Dns { override fun lookup(hostname: String) = expected },
            fallback = object : Dns {
                override fun lookup(hostname: String): List<InetAddress> {
                    fallbackCalled = true
                    return emptyList()
                }
            },
        )

        assertEquals(expected, dns.lookup("ptr.rotadeataque.com.br"))
        assertFalse(fallbackCalled)
    }

    @Test
    fun `uses fallback after Android resolver reports unknown host`() {
        val expected = listOf(InetAddress.getByAddress(byteArrayOf(10, 0, 0, 2)))
        var fallbackReported = false
        val dns = FallbackDns(
            primary = object : Dns {
                override fun lookup(hostname: String): List<InetAddress> =
                    throw UnknownHostException("system resolver failed")
            },
            fallback = object : Dns { override fun lookup(hostname: String) = expected },
            onFallback = { hostname, _ ->
                fallbackReported = hostname == "ptr.rotadeataque.com.br"
            }
        )

        assertEquals(expected, dns.lookup("ptr.rotadeataque.com.br"))
        assertTrue(fallbackReported)
    }
}
