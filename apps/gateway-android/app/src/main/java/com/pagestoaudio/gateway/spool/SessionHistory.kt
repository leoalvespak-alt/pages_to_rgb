package com.pagestoaudio.gateway.spool

import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Entity(tableName = "session_history")
data class SessionHistoryEntity(
    @androidx.room.PrimaryKey val sessionId: String,
    val type: String,
    val startedAt: Long,
    val endedAt: Long? = null,
    val frames: Int = 0,
    val status: String = "STARTED",
    val previewJson: String? = null,
    val pendingCount: Int = 0,
    val lastSyncAt: Long? = null,
    val lastError: String? = null
)

@Dao
interface SessionHistoryDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(item: SessionHistoryEntity)

    @Query("SELECT * FROM session_history ORDER BY startedAt DESC")
    fun observeAll(): Flow<List<SessionHistoryEntity>>

    @Query("SELECT * FROM session_history WHERE sessionId = :id LIMIT 1")
    suspend fun find(id: String): SessionHistoryEntity?
}
