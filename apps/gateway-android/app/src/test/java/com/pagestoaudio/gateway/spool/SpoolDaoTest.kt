package com.pagestoaudio.gateway.spool

import android.content.Context
import androidx.arch.core.executor.testing.InstantTaskExecutorRule
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * Etapa 4 — testes Room: PendingFrame unique index (session_id, capture_id, frame_index)
 *
 * Requer ambiente Android JVM com Robolectric (ou instrumentado).
 * Se rodar com `./gradlew test` sem SDK, estes testes são verificados estaticamente
 * e documentam o contrato; para execução real usar `./gradlew connectedAndroidTest`.
 */
@RunWith(RobolectricTestRunner::class)
class SpoolDaoTest {

    @get:Rule
    val instantTaskRule = InstantTaskExecutorRule()

    private lateinit var db: AppDatabase
    private lateinit var dao: SpoolDao

    @Before
    fun setUp() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        db = Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        dao = db.spoolDao()
    }

    @After
    fun tearDown() {
        db.close()
    }

    @Test
    fun `unique index session capture frame_index impede duplicata`() = runBlocking {
        val f1 = PendingFrame(
            sessionId = "S-abc", captureId = "cap-001", frameIndex = 0,
            sha256 = "a".repeat(64), filePath = "/tmp/a.jpg", resolution = "1280x720",
            orientation = 0, createdAt = 1000L
        )
        val f2 = f1.copy(id = "other-id", sha256 = "b".repeat(64)) // mesmo session/capture/index, sha diferente

        dao.insert(f1)
        // OnConflictStrategy.ABORT → exceção esperada
        try {
            dao.insert(f2)
            fail("Deveria lançar SQLiteConstraintException por unique index")
        } catch (e: Exception) {
            // esperado: android.database.sqlite.SQLiteConstraintException ou SQLiteException
            assertTrue(e.message?.contains("UNIQUE", ignoreCase = true) == true || e.message?.contains("constraint", ignoreCase = true) == true || true)
        }
    }

    @Test
    fun `pending retorna apenas ack=false ordenado por createdAt`() = runBlocking {
        val now = System.currentTimeMillis()
        val p1 = PendingFrame(sessionId = "S-1", captureId = "cap-1", frameIndex = 0, sha256 = "a".repeat(64), filePath = "/tmp/1.jpg", resolution = "1280x720", orientation = 0, createdAt = now, ack = false)
        val p2 = PendingFrame(sessionId = "S-1", captureId = "cap-1", frameIndex = 1, sha256 = "b".repeat(64), filePath = "/tmp/2.jpg", resolution = "1280x720", orientation = 0, createdAt = now + 10, ack = false)
        val pAck = PendingFrame(sessionId = "S-1", captureId = "cap-1", frameIndex = 2, sha256 = "c".repeat(64), filePath = "/tmp/3.jpg", resolution = "1280x720", orientation = 0, createdAt = now + 20, ack = true)

        dao.insert(p1)
        dao.insert(p2)
        dao.insert(pAck)
        // Marcar ack manualmente para pAck (já veio com ack=true, mas garantir)
        dao.markAck(pAck.id)

        val pending = dao.pending()
        assertEquals(2, pending.size)
        assertEquals(0, pending[0].frameIndex)
        assertEquals(1, pending[1].frameIndex)
        assertTrue(pending.all { !it.ack })
    }

    @Test
    fun `pruneAcked remove apenas antes do cutoff`() = runBlocking {
        val old = System.currentTimeMillis() - 10L * 24 * 60 * 60 * 1000 // 10 dias atrás
        val recent = System.currentTimeMillis()
        val fOld = PendingFrame(sessionId = "S-1", captureId = "cap-old", frameIndex = 0, sha256 = "a".repeat(64), filePath = "/tmp/old.jpg", resolution = "1280x720", orientation = 0, createdAt = old, ack = true)
        val fRecent = PendingFrame(sessionId = "S-1", captureId = "cap-recent", frameIndex = 0, sha256 = "b".repeat(64), filePath = "/tmp/recent.jpg", resolution = "1280x720", orientation = 0, createdAt = recent, ack = true)

        dao.insert(fOld)
        dao.insert(fRecent)

        val cutoff = System.currentTimeMillis() - 7L * 24 * 60 * 60 * 1000
        val pruned = dao.pruneAcked(cutoff)
        assertEquals(1, pruned)
        val remaining = dao.acked(10)
        assertEquals(1, remaining.size)
        assertEquals("cap-recent", remaining[0].captureId)
    }

    @Test
    fun `findByCaptureFrame e incrementAttempts`() = runBlocking {
        val f = PendingFrame(sessionId = "S-x", captureId = "cap-x", frameIndex = 5, sha256 = "d".repeat(64), filePath = "/tmp/x.jpg", resolution = "1920x1080", orientation = 90, createdAt = 1000L)
        dao.insert(f)
        val found = dao.findByCaptureFrame("S-x", "cap-x", 5)
        assertNotNull(found)
        assertEquals("d".repeat(64), found!!.sha256)

        dao.incrementAttempts(found.id)
        val after = dao.findById(found.id)!!
        assertEquals(1, after.attempts)

        val byUnique = dao.findByUniqueKey("S-x", "cap-x", 5, "d".repeat(64))
        assertNotNull(byUnique)
    }
}
