package com.pagestoaudio.gateway.spool

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(
    entities = [
        PendingFrame::class,
        SessionHistoryEntity::class,
        PendingRgbCommand::class,
        RgbEventOutbox::class,
        RgbCommandCursor::class,
    ],
    version = 4,
    exportSchema = true
)
abstract class AppDatabase : RoomDatabase() {

    abstract fun spoolDao(): SpoolDao
    abstract fun sessionHistoryDao(): SessionHistoryDao
    abstract fun rgbCommandDao(): RgbCommandDao

    companion object {
        @Volatile
        private var INSTANCE: AppDatabase? = null

        fun getInstance(context: Context): AppDatabase =
            INSTANCE ?: synchronized(this) {
                INSTANCE ?: buildDatabase(context).also { INSTANCE = it }
            }

        private val MIGRATION_2_3 = object : androidx.room.migration.Migration(2, 3) {
            override fun migrate(db: androidx.sqlite.db.SupportSQLiteDatabase) {
                db.execSQL("CREATE TABLE IF NOT EXISTS session_history (sessionId TEXT NOT NULL PRIMARY KEY, type TEXT NOT NULL, startedAt INTEGER NOT NULL, endedAt INTEGER, frames INTEGER NOT NULL, status TEXT NOT NULL, previewJson TEXT, pendingCount INTEGER NOT NULL, lastSyncAt INTEGER, lastError TEXT)")
            }
        }

        private val MIGRATION_3_4 = object : androidx.room.migration.Migration(3, 4) {
            override fun migrate(db: androidx.sqlite.db.SupportSQLiteDatabase) {
                db.execSQL(
                    "CREATE TABLE IF NOT EXISTS pending_rgb_commands " +
                        "(commandId TEXT NOT NULL, deviceCode TEXT NOT NULL, sessionId TEXT, " +
                        "kind TEXT NOT NULL, status TEXT NOT NULL, requestedJson TEXT NOT NULL, " +
                        "effectiveJson TEXT NOT NULL, expiresAt TEXT NOT NULL, receivedAt INTEGER NOT NULL, " +
                        "attempts INTEGER NOT NULL, PRIMARY KEY(commandId))"
                )
                db.execSQL(
                    "CREATE INDEX IF NOT EXISTS index_pending_rgb_commands_deviceCode_status " +
                        "ON pending_rgb_commands(deviceCode, status)"
                )
                db.execSQL(
                    "CREATE INDEX IF NOT EXISTS index_pending_rgb_commands_receivedAt " +
                        "ON pending_rgb_commands(receivedAt)"
                )
                db.execSQL(
                    "CREATE TABLE IF NOT EXISTS rgb_event_outbox " +
                        "(commandId TEXT NOT NULL, deviceCode TEXT NOT NULL, idempotencyKey TEXT NOT NULL, " +
                        "event TEXT NOT NULL, payloadJson TEXT NOT NULL, effectivePayloadJson TEXT NOT NULL, " +
                        "firmwareVersion TEXT, deviceTimestamp TEXT, createdAt INTEGER NOT NULL, sentAt INTEGER, " +
                        "attempts INTEGER NOT NULL, lastError TEXT, PRIMARY KEY(commandId, idempotencyKey))"
                )
                db.execSQL(
                    "CREATE INDEX IF NOT EXISTS index_rgb_event_outbox_deviceCode_sentAt " +
                        "ON rgb_event_outbox(deviceCode, sentAt)"
                )
                db.execSQL(
                    "CREATE INDEX IF NOT EXISTS index_rgb_event_outbox_createdAt " +
                        "ON rgb_event_outbox(createdAt)"
                )
                db.execSQL(
                    "CREATE TABLE IF NOT EXISTS rgb_command_cursors " +
                        "(deviceCode TEXT NOT NULL, cursor INTEGER NOT NULL, PRIMARY KEY(deviceCode))"
                )
            }
        }

        private fun buildDatabase(context: Context): AppDatabase =
            Room.databaseBuilder(
                context.applicationContext,
                AppDatabase::class.java,
                "gateway_spool.db"
            )
                .addMigrations(MIGRATION_2_3)
                .addMigrations(MIGRATION_3_4)
                .build()

        /** Para testes instrumentados — DB em memória. */
        fun createInMemory(context: Context): AppDatabase =
            Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java)
                .allowMainThreadQueries()
                .build()
    }
}
