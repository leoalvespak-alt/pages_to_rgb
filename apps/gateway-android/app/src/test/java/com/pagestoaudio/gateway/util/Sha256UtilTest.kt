package com.pagestoaudio.gateway.util

import java.io.File
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import java.security.MessageDigest

/**
 * Etapa 4 — Sha256Util streaming determinístico
 */
@RunWith(RobolectricTestRunner::class)
class Sha256UtilTest {

    @Test
    fun `sha256 streaming deterministico ler 2x mesmo hash`() {
        val tmp = File.createTempFile("sha_test", ".bin")
        tmp.writeBytes("hello world deterministico".toByteArray())
        val h1 = Sha256Util.sha256HexStreaming(tmp)
        val h2 = Sha256Util.sha256HexStreaming(tmp)
        assertEquals(h1, h2)
        assertEquals(64, h1.length)
        tmp.delete()
    }

    @Test
    fun `sha256 hex bate com MessageDigest`() {
        val data = "Pages to Audio".toByteArray()
        val expected = MessageDigest.getInstance("SHA-256").digest(data).joinToString("") { "%02x".format(it) }
        val actual = Sha256Util.sha256Hex(data)
        assertEquals(expected, actual)
    }

    @Test
    fun `sha256 arquivo vazio conhecido`() {
        val tmp = File.createTempFile("empty", ".jpg")
        tmp.writeBytes(ByteArray(0))
        val sha = Sha256Util.sha256HexStreaming(tmp)
        // SHA-256 de vazio
        assertEquals("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", sha)
        tmp.delete()
    }
}
