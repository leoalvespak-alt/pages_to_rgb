package com.pagestoaudio.gateway.util

import java.io.File
import java.io.InputStream
import java.security.MessageDigest

object Sha256Util {

    private const val BUFFER_SIZE = 8192

    /**
     * Calcula SHA-256 hex via streaming — não carrega arquivo inteiro em RAM.
     * Determinístico: ler arquivo 2x → mesmo hash.
     */
    fun sha256HexStreaming(file: File): String {
        file.inputStream().use { return sha256HexStreaming(it) }
    }

    fun sha256HexStreaming(input: InputStream): String {
        val digest = MessageDigest.getInstance("SHA-256")
        val buffer = ByteArray(BUFFER_SIZE)
        var read: Int
        while (input.read(buffer).also { read = it } != -1) {
            digest.update(buffer, 0, read)
        }
        return digest.digest().toHex()
    }

    fun sha256Hex(bytes: ByteArray): String {
        val digest = MessageDigest.getInstance("SHA-256")
        return digest.digest(bytes).toHex()
    }

    private fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it) }
}
