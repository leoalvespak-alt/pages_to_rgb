package com.pagestoaudio.gateway.domain

import androidx.room.withTransaction
import com.google.gson.Gson
import com.google.gson.JsonParser
import com.pagestoaudio.gateway.network.ApiService
import com.pagestoaudio.gateway.network.RgbDeviceCommand
import com.pagestoaudio.gateway.network.RgbDeviceEventRequest
import com.pagestoaudio.gateway.spool.AppDatabase
import com.pagestoaudio.gateway.spool.PendingRgbCommand
import com.pagestoaudio.gateway.spool.RgbEventOutbox
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** Durable cloud-to-ESP command bridge. The screen is not part of this path. */
class RgbCommandRepository(
    private val api: ApiService,
    private val database: AppDatabase,
) {
    private val dao = database.rgbCommandDao()
    private val gson = Gson()

    data class PollResult(val received: Int, val cursor: Long)
    data class DrainResult(val sent: Int, val retryableFailure: Boolean)

    suspend fun pollDevice(deviceCode: String): Result<PollResult> = withContext(Dispatchers.IO) {
        try {
            val current = dao.cursor(deviceCode)?.cursor ?: 0L
            val response = api.getDeviceRgbCommands(deviceCode, current)
            if (!response.isSuccessful) {
                return@withContext Result.failure(
                    IllegalStateException("getDeviceRgbCommands ${response.code()}")
                )
            }
            val page = response.body()
                ?: return@withContext Result.failure(IllegalStateException("empty RGB command page"))
            if (page.cursor < current) {
                return@withContext Result.failure(IllegalStateException("RGB command cursor regressed"))
            }
            val receivedAt = System.currentTimeMillis()
            val pending = page.items.map { it.toPending(deviceCode, receivedAt) }
            database.withTransaction {
                dao.persistCloudPage(deviceCode, page.cursor, pending)
            }
            Result.success(PollResult(pending.size, page.cursor))
        } catch (error: Exception) {
            Result.failure(error)
        }
    }

    suspend fun localCommands(deviceCode: String, limit: Int = 20): List<PendingRgbCommand> =
        withContext(Dispatchers.IO) { dao.commandsForDevice(deviceCode, limit) }

    suspend fun recordLocalEvent(
        deviceCode: String,
        commandId: String,
        event: String,
        payloadJson: String,
        effectivePayloadJson: String,
        firmwareVersion: String?,
        deviceTimestamp: String?,
        idempotencyKey: String,
    ): Result<Boolean> = withContext(Dispatchers.IO) {
        try {
            val normalizedPayload = normalizeJson(payloadJson)
            val normalizedEffective = normalizeJson(effectivePayloadJson)
            val row = RgbEventOutbox(
                commandId = commandId,
                deviceCode = deviceCode,
                idempotencyKey = idempotencyKey,
                event = event,
                payloadJson = normalizedPayload,
                effectivePayloadJson = normalizedEffective,
                firmwareVersion = firmwareVersion,
                deviceTimestamp = deviceTimestamp,
                createdAt = System.currentTimeMillis(),
            )
            val persisted = database.withTransaction {
                val command = dao.command(commandId)
                    ?: throw IllegalStateException("RGB command not found")
                if (command.deviceCode != deviceCode) {
                    throw IllegalStateException("RGB command device mismatch")
                }
                val existing = dao.event(commandId, idempotencyKey)
                if (existing != null) {
                    if (
                        normalizeJson(existing.payloadJson) != normalizedPayload ||
                            normalizeJson(existing.effectivePayloadJson) != normalizedEffective
                    ) {
                        throw IllegalStateException("idempotency key reused with different payload")
                    }
                    false
                } else {
                    val nextStatus = localStatus(event)
                    if (!isAllowedTransition(command.status, nextStatus)) {
                        throw IllegalStateException(
                            "invalid RGB state transition ${command.status} -> $nextStatus"
                        )
                    }
                    dao.insertEventIfAbsent(row)
                    dao.updateStatus(commandId, nextStatus)
                    true
                }
            }
            Result.success(persisted)
        } catch (error: Exception) {
            Result.failure(error)
        }
    }

    suspend fun drainEvents(limit: Int = 20): Result<DrainResult> = withContext(Dispatchers.IO) {
        var sent = 0
        var retryableFailure = false
        for (event in dao.pendingEvents(limit)) {
            try {
                val response = api.postDeviceRgbEvent(
                    deviceId = event.deviceCode,
                    commandId = event.commandId,
                    idempotencyKey = event.idempotencyKey,
                    body = RgbDeviceEventRequest(
                        event = event.event,
                        effectivePayload = jsonMap(event.effectivePayloadJson),
                        payload = jsonMap(event.payloadJson),
                        firmwareVersion = event.firmwareVersion,
                        deviceTimestamp = event.deviceTimestamp,
                    ),
                )
                if (response.isSuccessful) {
                    dao.markEventSent(event.commandId, event.idempotencyKey, System.currentTimeMillis())
                    sent++
                } else {
                    val message = "postDeviceRgbEvent ${response.code()}"
                    dao.recordEventFailure(event.commandId, event.idempotencyKey, message)
                    retryableFailure = response.code() >= 500 || response.code() == 408 || response.code() == 429
                }
            } catch (error: Exception) {
                dao.recordEventFailure(
                    event.commandId,
                    event.idempotencyKey,
                    error.message ?: error.javaClass.simpleName,
                )
                retryableFailure = true
            }
        }
        Result.success(DrainResult(sent, retryableFailure))
    }

    private fun RgbDeviceCommand.toPending(deviceCode: String, receivedAt: Long): PendingRgbCommand {
        require(this.deviceCode == deviceCode) { "RGB command device mismatch" }
        require(commandId.isNotBlank()) { "RGB command_id is blank" }
        require(kind in CLOUD_KINDS) { "unknown RGB command kind: $kind" }
        require(status in CLOUD_STATUSES) { "unknown RGB command status: $status" }
        require(expiresAt.isNotBlank()) { "RGB command expiry is blank" }
        return PendingRgbCommand(
            commandId = commandId,
            deviceCode = deviceCode,
            sessionId = sessionId,
            kind = kind,
            status = status,
            requestedJson = gson.toJson(requested),
            effectiveJson = gson.toJson(effective),
            expiresAt = expiresAt,
            receivedAt = receivedAt,
        )
    }

    private fun jsonMap(value: String): Map<String, Any> =
        gson.fromJson(value, Map::class.java) as? Map<String, Any> ?: emptyMap()

    private fun normalizeJson(value: String): String {
        val parsed = runCatching { JsonParser.parseString(value) }
            .getOrElse { throw IllegalArgumentException("invalid JSON payload") }
        require(parsed.isJsonObject) { "RGB payload must be a JSON object" }
        return parsed.toString()
    }

    private fun localStatus(event: String): String = when (event) {
        "FORWARDED" -> "FORWARDED"
        "RECEIVED" -> "RECEIVED"
        "APPLIED" -> "APPLIED"
        "OFF" -> "OFF"
        "FAILED" -> "FAILED"
        "CANCELLED" -> "CANCELLED"
        "EXPIRED" -> "EXPIRED"
        else -> throw IllegalArgumentException("unknown RGB event: $event")
    }

    private fun isAllowedTransition(current: String, next: String): Boolean = when (current) {
        "QUEUED" -> next in setOf("FORWARDED", "RECEIVED", "FAILED", "CANCELLED", "EXPIRED")
        "FORWARDED" -> next in setOf("RECEIVED", "APPLIED", "FAILED", "CANCELLED", "EXPIRED")
        "RECEIVED" -> next in setOf("APPLIED", "FAILED", "CANCELLED", "EXPIRED")
        "APPLIED" -> next in setOf("OFF", "FAILED")
        "CANCELLED" -> next == "OFF"
        else -> false
    }

    private companion object {
        val CLOUD_KINDS = setOf("TEST", "STOP")
        val CLOUD_STATUSES = setOf(
            "QUEUED", "FORWARDED", "RECEIVED", "APPLIED", "OFF",
            "FAILED", "CANCELLED", "EXPIRED"
        )
    }
}
