package com.pagestoaudio.gateway.spool

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface SpoolDao {

    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insert(frame: PendingFrame)

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insertIgnore(frame: PendingFrame): Long

    @Query("SELECT * FROM pending_frames WHERE ack = 0 ORDER BY createdAt ASC")
    suspend fun pending(): List<PendingFrame>

    @Query("SELECT * FROM pending_frames WHERE ack = 0 AND session_id = :sessionId ORDER BY frame_index ASC, createdAt ASC")
    suspend fun pendingForSession(sessionId: String): List<PendingFrame>

    @Query("SELECT * FROM pending_frames WHERE ack = 0 AND session_id = :sessionId AND capture_id = :captureId ORDER BY frame_index ASC")
    suspend fun pendingForCapture(sessionId: String, captureId: String): List<PendingFrame>

    @Query("SELECT COUNT(*) FROM pending_frames WHERE ack = 0")
    suspend fun pendingCount(): Int

    @Query("SELECT COUNT(*) FROM pending_frames WHERE ack = 0 AND session_id = :sessionId")
    suspend fun pendingCountForSession(sessionId: String): Int

    @Query("SELECT * FROM pending_frames WHERE session_id = :sessionId ORDER BY createdAt DESC LIMIT 1")
    suspend fun lastForSession(sessionId: String): PendingFrame?

    @Query("SELECT * FROM pending_frames ORDER BY createdAt DESC LIMIT 1")
    suspend fun lastOverall(): PendingFrame?

    @Query("SELECT COUNT(*) FROM pending_frames WHERE ack = 0")
    fun pendingCountFlow(): Flow<Int>

    @Query("SELECT * FROM pending_frames WHERE ack = 0 ORDER BY createdAt ASC")
    fun pendingFlow(): Flow<List<PendingFrame>>

    @Query("UPDATE pending_frames SET ack = 1 WHERE id = :id")
    suspend fun markAck(id: String): Int

    @Query("UPDATE pending_frames SET attempts = attempts + 1 WHERE id = :id")
    suspend fun incrementAttempts(id: String): Int

    @Query("SELECT * FROM pending_frames WHERE id = :id LIMIT 1")
    suspend fun findById(id: String): PendingFrame?

    @Query("SELECT * FROM pending_frames WHERE session_id = :sessionId AND capture_id = :captureId AND frame_index = :frameIndex LIMIT 1")
    suspend fun findByCaptureFrame(sessionId: String, captureId: String, frameIndex: Int): PendingFrame?

    @Query("SELECT * FROM pending_frames WHERE session_id = :sessionId AND sha256 = :sha256 AND capture_id = :captureId AND frame_index = :frameIndex LIMIT 1")
    suspend fun findByUniqueKey(sessionId: String, captureId: String, frameIndex: Int, sha256: String): PendingFrame?

    @Query("DELETE FROM pending_frames WHERE ack = 1 AND createdAt < :before")
    suspend fun pruneAcked(before: Long): Int

    @Delete
    suspend fun delete(frame: PendingFrame)

    @Query("DELETE FROM pending_frames WHERE id = :id")
    suspend fun deleteById(id: String): Int

    @Query("SELECT * FROM pending_frames WHERE ack = 1 ORDER BY createdAt DESC LIMIT :limit")
    suspend fun acked(limit: Int = 20): List<PendingFrame>
}
