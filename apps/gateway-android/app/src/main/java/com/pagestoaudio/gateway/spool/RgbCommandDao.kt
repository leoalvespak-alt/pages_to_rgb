package com.pagestoaudio.gateway.spool

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction

@Dao
interface RgbCommandDao {

    @Query("SELECT * FROM rgb_command_cursors WHERE deviceCode = :deviceCode LIMIT 1")
    suspend fun cursor(deviceCode: String): RgbCommandCursor?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun saveCursor(value: RgbCommandCursor)

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insertCommandIfAbsent(value: PendingRgbCommand): Long

    @Query(
        "SELECT * FROM pending_rgb_commands " +
            "WHERE deviceCode = :deviceCode AND status IN ('QUEUED','FORWARDED','RECEIVED','APPLIED','CANCELLED') " +
            "ORDER BY receivedAt ASC LIMIT :limit"
    )
    suspend fun commandsForDevice(deviceCode: String, limit: Int = 20): List<PendingRgbCommand>

    @Query("SELECT * FROM pending_rgb_commands WHERE commandId = :commandId LIMIT 1")
    suspend fun command(commandId: String): PendingRgbCommand?

    @Query("UPDATE pending_rgb_commands SET status = :status WHERE commandId = :commandId")
    suspend fun updateStatus(commandId: String, status: String): Int

    @Query("SELECT * FROM rgb_event_outbox WHERE sentAt IS NULL ORDER BY createdAt ASC LIMIT :limit")
    suspend fun pendingEvents(limit: Int = 20): List<RgbEventOutbox>

    @Query(
        "SELECT * FROM rgb_event_outbox " +
            "WHERE commandId = :commandId AND idempotencyKey = :idempotencyKey LIMIT 1"
    )
    suspend fun event(commandId: String, idempotencyKey: String): RgbEventOutbox?

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insertEventIfAbsent(value: RgbEventOutbox): Long

    @Query(
        "UPDATE rgb_event_outbox SET sentAt = :sentAt, attempts = attempts + 1, lastError = NULL " +
            "WHERE commandId = :commandId AND idempotencyKey = :idempotencyKey"
    )
    suspend fun markEventSent(commandId: String, idempotencyKey: String, sentAt: Long): Int

    @Query(
        "UPDATE rgb_event_outbox SET attempts = attempts + 1, lastError = :error " +
            "WHERE commandId = :commandId AND idempotencyKey = :idempotencyKey"
    )
    suspend fun recordEventFailure(commandId: String, idempotencyKey: String, error: String): Int

    @Transaction
    suspend fun persistCloudPage(
        deviceCode: String,
        cursor: Long,
        commands: List<PendingRgbCommand>,
    ) {
        commands.forEach { insertCommandIfAbsent(it) }
        saveCursor(RgbCommandCursor(deviceCode, cursor))
    }
}
