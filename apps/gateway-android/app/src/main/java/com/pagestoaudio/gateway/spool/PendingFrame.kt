package com.pagestoaudio.gateway.spool

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey
import java.util.UUID

/**
 * Room Entity — spool durável (Etapa 4).
 *
 * Ordem obrigatória:
 * capturar → salvar privado → Room insert → SHA → enfileirar → POST → aguardar 2xx → apagar somente após ACK
 *
 * Índice único exigido: (session_id, capture_id, frame_index)
 */
@Entity(
    tableName = "pending_frames",
    indices = [
        Index(value = ["session_id", "capture_id", "frame_index"], unique = true),
        Index(value = ["ack"]),
        Index(value = ["session_id"]),
        Index(value = ["sha256"])
    ]
)
data class PendingFrame(
    @PrimaryKey
    val id: String = UUID.randomUUID().toString(),

    @ColumnInfo(name = "session_id")
    val sessionId: String,

    @ColumnInfo(name = "capture_id")
    val captureId: String,

    @ColumnInfo(name = "frame_index")
    val frameIndex: Int,

    @ColumnInfo(name = "sha256")
    val sha256: String,

    @ColumnInfo(name = "filePath")
    val filePath: String,

    @ColumnInfo(name = "resolution")
    val resolution: String, // "WxH"

    @ColumnInfo(name = "orientation")
    val orientation: Int, // graus 0/90/180/270

    @ColumnInfo(name = "createdAt")
    val createdAt: Long, // epoch millis

    @ColumnInfo(name = "ack")
    val ack: Boolean = false,

    @ColumnInfo(name = "attempts")
    val attempts: Int = 0,

    @ColumnInfo(name = "width")
    val width: Int = 0,

    @ColumnInfo(name = "height")
    val height: Int = 0,

    @ColumnInfo(name = "sessionType", defaultValue = "EXAM")
    val sessionType: String = "EXAM"
)
