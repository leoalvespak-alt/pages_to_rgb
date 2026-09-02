package com.pagestoaudio.gateway.spool

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(
    entities = [PendingFrame::class, SessionHistoryEntity::class],
    version = 3,
    exportSchema = true
)
abstract class AppDatabase : RoomDatabase() {

    abstract fun spoolDao(): SpoolDao
    abstract fun sessionHistoryDao(): SessionHistoryDao

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

        private fun buildDatabase(context: Context): AppDatabase =
            Room.databaseBuilder(
                context.applicationContext,
                AppDatabase::class.java,
                "gateway_spool.db"
            )
                .addMigrations(MIGRATION_2_3)
                .build()

        /** Para testes instrumentados — DB em memória. */
        fun createInMemory(context: Context): AppDatabase =
            Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java)
                .allowMainThreadQueries()
                .build()
    }
}
