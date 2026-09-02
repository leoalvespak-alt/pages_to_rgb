package com.pagestoaudio.gateway.spool

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.work.Configuration
import androidx.work.WorkManager
import androidx.work.testing.SynchronousExecutor
import androidx.work.testing.TestDriver
import androidx.work.testing.WorkManagerTestInitHelper
import java.io.File
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * Etapa 4 — SpoolRepository: save idempotente + WorkName único + enqueue KEEP
 *
 * Cobre:
 * - PendingFrame unique index (via DAO)
 * - save() idempotente: mesmo session/capture/index+sha → success(existing)
 * - save() conflito: mesmo índice sha diferente → failure
 * - save() verifica arquivo e SHA streaming antes do insert
 * - enqueueUpload WorkName "upload-{session}-{capture}-{index}" com KEEP
 */
@RunWith(RobolectricTestRunner::class)
class SpoolRepositoryTest {

    private lateinit var context: Context
    private lateinit var db: AppDatabase
    private lateinit var dao: SpoolDao
    private lateinit var workManager: WorkManager
    private lateinit var repository: SpoolRepository
    private lateinit var spoolDir: File

    @Before
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        // WorkManager de teste (SynchronousExecutor) para inspeção de fila
        val config = Configuration.Builder()
            .setMinimumLoggingLevel(android.util.Log.DEBUG)
            .setExecutor(SynchronousExecutor())
            .build()
        WorkManagerTestInitHelper.initializeTestWorkManager(context, config)
        workManager = WorkManager.getInstance(context)

        db = Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        dao = db.spoolDao()
        repository = SpoolRepository(context, dao, workManager)
        spoolDir = File(context.filesDir, "spool_test").apply { mkdirs() }
    }

    @After
    fun tearDown() {
        db.close()
        spoolDir.deleteRecursively()
    }

    private fun createTempJpeg(sessionId: String, captureId: String, idx: Int, content: ByteArray = "fake-jpeg-${System.nanoTime()}".toByteArray()): Pair<File, String> {
        val dir = File(spoolDir, sessionId).apply { mkdirs() }
        val file = File(dir, "${captureId}_${idx}.jpg")
        file.writeBytes(content)
        val sha = com.pagestoaudio.gateway.util.Sha256Util.sha256HexStreaming(file)
        return file to sha
    }

    @Test
    fun `save idempotente mesmo sha retorna existing`() = runBlocking {
        val (file, sha) = createTempJpeg("S-1", "cap-001", 0)
        val frame = PendingFrame(sessionId = "S-1", captureId = "cap-001", frameIndex = 0, sha256 = sha, filePath = file.absolutePath, resolution = "1280x720", orientation = 0, createdAt = System.currentTimeMillis())

        val r1 = repository.save(frame)
        assertTrue(r1.isSuccess)
        // Re-salvar mesmo objeto (mesmo sha)
        val r2 = repository.save(frame.copy(id = "other-id"))
        assertTrue(r2.isSuccess)
        // Deve retornar o existente (id original), não duplicar
        assertEquals(r1.getOrNull()!!.id, r2.getOrNull()!!.id)
        assertEquals(1, dao.pendingCount())
    }

    @Test
    fun `save conflito sha diferente falha sem inserir`() = runBlocking {
        val (file1, sha1) = createTempJpeg("S-2", "cap-002", 0, "content-a".toByteArray())
        val frame1 = PendingFrame(sessionId = "S-2", captureId = "cap-002", frameIndex = 0, sha256 = sha1, filePath = file1.absolutePath, resolution = "1280x720", orientation = 0, createdAt = System.currentTimeMillis())
        assertTrue(repository.save(frame1).isSuccess)

        // Mesmo session/capture/index com conteúdo diferente → sha diferente
        val (file2, sha2) = createTempJpeg("S-2", "cap-002", 0, "content-b".toByteArray())
        // sha2 != sha1
        assertNotEquals(sha1, sha2)
        val frame2 = PendingFrame(sessionId = "S-2", captureId = "cap-002", frameIndex = 0, sha256 = sha2, filePath = file2.absolutePath, resolution = "1280x720", orientation = 0, createdAt = System.currentTimeMillis())
        val r2 = repository.save(frame2)
        assertTrue(r2.isFailure)
        assertTrue(r2.exceptionOrNull()!!.message!!.contains("Conflito"))
        assertEquals(1, dao.pendingCount())
    }

    @Test
    fun `save falha se arquivo inexistente`() = runBlocking {
        val frame = PendingFrame(sessionId = "S-3", captureId = "cap-003", frameIndex = 0, sha256 = "a".repeat(64), filePath = "/nonexistent/path.jpg", resolution = "1280x720", orientation = 0, createdAt = System.currentTimeMillis())
        val r = repository.save(frame)
        assertTrue(r.isFailure)
        assertTrue(r.exceptionOrNull()!!.message!!.contains("inexistente"))
    }

    @Test
    fun `save falha se sha não bate com arquivo`() = runBlocking {
        val (file, _) = createTempJpeg("S-4", "cap-004", 0)
        val wrongSha = "f".repeat(64)
        val frame = PendingFrame(sessionId = "S-4", captureId = "cap-004", frameIndex = 0, sha256 = wrongSha, filePath = file.absolutePath, resolution = "1280x720", orientation = 0, createdAt = System.currentTimeMillis())
        val r = repository.save(frame)
        assertTrue(r.isFailure)
        assertTrue(r.exceptionOrNull()!!.message!!.contains("SHA mismatch"))
    }

    @Test
    fun `enqueueUpload usa WorkName único e KEEP`() = runBlocking {
        val (file, sha) = createTempJpeg("S-5", "cap-005", 1)
        val frame = PendingFrame(sessionId = "S-5", captureId = "cap-005", frameIndex = 1, sha256 = sha, filePath = file.absolutePath, resolution = "1920x1080", orientation = 90, createdAt = System.currentTimeMillis())
        repository.save(frame) // já enfileira

        val workName = "upload-S-5-cap-005-1"
        val infos = workManager.getWorkInfosForUniqueWork(workName).get()
        assertEquals(1, infos.size)
        // Segunda chamada com KEEP não duplica
        repository.enqueueUpload(frame)
        val infos2 = workManager.getWorkInfosForUniqueWork(workName).get()
        assertEquals(1, infos2.size)
    }

    @Test
    fun `reenqueueAllPending re-enfileira após corte`() = runBlocking {
        val (f1, s1) = createTempJpeg("S-6", "cap-006", 0)
        val (f2, s2) = createTempJpeg("S-6", "cap-006", 1)
        val frame1 = PendingFrame(sessionId = "S-6", captureId = "cap-006", frameIndex = 0, sha256 = s1, filePath = f1.absolutePath, resolution = "1280x720", orientation = 0, createdAt = System.currentTimeMillis())
        val frame2 = PendingFrame(sessionId = "S-6", captureId = "cap-006", frameIndex = 1, sha256 = s2, filePath = f2.absolutePath, resolution = "1280x720", orientation = 0, createdAt = System.currentTimeMillis())
        repository.save(frame1)
        repository.save(frame2)
        assertEquals(2, dao.pendingCount())
        // Simular corte de rede: WorkManager ainda tem 2 works, mas reenqueue deve ser idempotente
        val n = repository.reenqueueAllPending()
        assertEquals(2, n)
        assertEquals(1, workManager.getWorkInfosForUniqueWork("upload-S-6-cap-006-0").get().size)
        assertEquals(1, workManager.getWorkInfosForUniqueWork("upload-S-6-cap-006-1").get().size)
    }

    @Test
    fun `markAck apaga somente após ACK`() = runBlocking {
        val (file, sha) = createTempJpeg("S-7", "cap-007", 0)
        assertTrue(file.exists())
        val frame = PendingFrame(sessionId = "S-7", captureId = "cap-007", frameIndex = 0, sha256 = sha, filePath = file.absolutePath, resolution = "1280x720", orientation = 0, createdAt = System.currentTimeMillis())
        val saved = repository.save(frame).getOrNull()!!
        assertTrue(File(saved.filePath).exists())
        val ackRes = repository.markAck(saved.id)
        assertTrue(ackRes.isSuccess)
        assertFalse(File(saved.filePath).exists())
        assertEquals(0, dao.pendingCount())
        assertEquals(1, dao.acked(10).size)
    }
}
