package com.pagestoaudio.gateway.spool

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

/** Cloud RGB command durably received before local ESP delivery. */
@Entity(
    tableName = "pending_rgb_commands",
    primaryKeys = ["commandId"],
    indices = [
        Index(value = ["deviceCode", "status"]),
        Index(value = ["receivedAt"]),
    ],
)
data class PendingRgbCommand(
    val commandId: String,
    val deviceCode: String,
    val sessionId: String? = null,
    val kind: String,
    val status: String,
    val requestedJson: String,
    val effectiveJson: String,
    val expiresAt: String,
    val receivedAt: Long,
    val attempts: Int = 0,
)

/** Local ESP event outbox; sentAt is set only after cloud confirms the event. */
@Entity(
    tableName = "rgb_event_outbox",
    primaryKeys = ["commandId", "idempotencyKey"],
    indices = [
        Index(value = ["deviceCode", "sentAt"]),
        Index(value = ["createdAt"]),
    ],
)
data class RgbEventOutbox(
    val commandId: String,
    val deviceCode: String,
    val idempotencyKey: String,
    val event: String,
    val payloadJson: String,
    val effectivePayloadJson: String,
    val firmwareVersion: String? = null,
    val deviceTimestamp: String? = null,
    val createdAt: Long,
    val sentAt: Long? = null,
    val attempts: Int = 0,
    val lastError: String? = null,
)

/** Durable cursor for the cloud device-command stream. */
@Entity(tableName = "rgb_command_cursors")
data class RgbCommandCursor(
    @PrimaryKey
    val deviceCode: String,
    val cursor: Long,
)
