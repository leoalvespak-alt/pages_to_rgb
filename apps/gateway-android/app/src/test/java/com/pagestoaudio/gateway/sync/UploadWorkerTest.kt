package com.pagestoaudio.gateway.sync

import android.content.Context
import androidx.arch.core.executor.testing.InstantTaskExecutorRule
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.work.ListenableWorker
import com.pagestoaudio.gateway.network.ApiService
import com.pagestoaudio.gateway.network.CaptureCompleteResponse
import com.pagestoaudio.gateway.network.CapturePolicyResponse
import com.pagestoaudio.gateway.network.CommandResponse
import com.pagestoaudio.gateway.network.EndSignalRequest
import com.pagestoaudio.gateway.network.EndSignalResponse
import com.pagestoaudio.gateway.network.FrameUploadResponse
import com.pagestoaudio.gateway.network.HeartbeatRequest
import com.pagestoaudio.gateway.network.HeartbeatResponse
import com.pagestoaudio.gateway.network.HandwrittenStartRequest
import com.pagestoaudio.gateway.network.HandwrittenStartResponse
import com.pagestoaudio.gateway.network.HandwrittenSummaryResponse
import com.pagestoaudio.gateway.network.HelloRequest
import com.pagestoaudio.gateway.network.HelloResponse
import com.pagestoaudio.gateway.network.RgbEventRequest
import com.pagestoaudio.gateway.network.RgbEventResponse
import com.pagestoaudio.gateway.network.RgbSequenceResponse
import com.pagestoaudio.gateway.network.RgbTestCommandResponse
import com.pagestoaudio.gateway.network.SessionResultResponse
import com.pagestoaudio.gateway.network.StartSessionRequest
import com.pagestoaudio.gateway.network.StartSessionResponse
import com.pagestoaudio.gateway.spool.AppDatabase
import com.pagestoaudio.gateway.spool.PendingFrame
import com.pagestoaudio.gateway.util.Sha256Util
import java.io.File
import kotlinx.coroutines.runBlocking
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import retrofit2.Response

/**
 * Etapa 4 — UploadWorker: SHA streaming, headers, 2xx/409/5xx + retry/backoff
 *
 * Usa FakeApiService sem dependência de mockito.
 * Verifica:
 * - SHA recalculado via streaming e comparado com Room antes de enviar
 * - 2xx → markAck + delete file
 * - 409 → failure (não retry)
 * - 5xx/408/429 → retry com backoff exponencial
 * - 4xx outros → failure
 * - WorkName único já garantido por SpoolRepository.enqueueUpload (KEEP)
 */
@RunWith(RobolectricTestRunner::class)
class UploadWorkerTest {

    @get:Rule
    val instantTaskRule = InstantTaskExecutorRule()

    private lateinit var context: Context
    private lateinit var db: AppDatabase
    private lateinit var spoolDir: File

    // Fake que permite configurar resposta do uploadFrame
    class FakeApiService(
        var uploadResponse: Response<FrameUploadResponse>? = null,
        var uploadException: Exception? = null
    ) : ApiService {
        var lastUploadCall: Triple<String, String, Int>? = null
        override suspend fun hello(body: HelloRequest): Response<HelloResponse> = throw NotImplementedError()
        override suspend fun startSession(body: StartSessionRequest): Response<StartSessionResponse> = throw NotImplementedError()
        override suspend fun heartbeat(sessionId: String, body: HeartbeatRequest?): Response<HeartbeatResponse> = throw NotImplementedError()
        override suspend fun getPolicy(sessionId: String): Response<CapturePolicyResponse> = throw NotImplementedError()
        override suspend fun getCommand(sessionId: String, cursor: Long, waitMs: Long, phase: String): Response<CommandResponse> = throw NotImplementedError()
        override suspend fun uploadFrame(sessionId: String, captureId: String, frameIndex: Int, sha256: String, resolution: String, receivedAt: String, orientation: Int, file: MultipartBody.Part): Response<FrameUploadResponse> {
            lastUploadCall = Triple(sessionId, captureId, frameIndex)
            uploadException?.let { throw it }
            return uploadResponse ?: throw IllegalStateException("uploadResponse não configurado")
        }
        override suspend fun captureComplete(sessionId: String, captureId: String, receivedFrames: Int): Response<CaptureCompleteResponse> = throw NotImplementedError()
        override suspend fun endSignal(sessionId: String, body: EndSignalRequest): Response<EndSignalResponse> = throw NotImplementedError()
        override suspend fun getResult(sessionId: String, deviceId: String, cursor: Long): Response<SessionResultResponse> = throw NotImplementedError()
        override suspend fun getRgbSequence(sessionId: String, deviceId: String, sequenceId: String?): Response<RgbSequenceResponse> = throw NotImplementedError()
        override suspend fun getRgbTest(sessionId: String, afterId: Int): Response<RgbTestCommandResponse?> = throw NotImplementedError()
        override suspend fun postRgbEvent(sessionId: String, body: RgbEventRequest): Response<RgbEventResponse> = throw NotImplementedError()
        override suspend fun startHandwrittenSession(body: HandwrittenStartRequest): Response<HandwrittenStartResponse> = throw NotImplementedError()
        override suspend fun uploadHandwrittenFrame(sessionId: String, captureId: String, frameIndex: Int, sha256: String, resolution: String, receivedAt: String, orientation: Int, file: MultipartBody.Part): Response<FrameUploadResponse> = throw NotImplementedError()
        override suspend fun captureCompleteHandwritten(sessionId: String, captureId: String, receivedFrames: Int): Response<CaptureCompleteResponse> = throw NotImplementedError()
        override suspend fun endSignalHandwritten(sessionId: String, body: EndSignalRequest): Response<EndSignalResponse> = throw NotImplementedError()
        override suspend fun getHandwrittenCommand(sessionId: String, cursor: Long, waitMs: Long, phase: String): Response<CommandResponse> = throw NotImplementedError()
        override suspend fun getHandwrittenPolicy(sessionId: String): Response<CapturePolicyResponse> = throw NotImplementedError()
        override suspend fun getHandwrittenSummary(sessionId: String): Response<HandwrittenSummaryResponse> = throw NotImplementedError()
    }

    @Before
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        db = Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        spoolDir = File(context.filesDir, "spool_worker_test").apply { mkdirs() }
    }

    @After
    fun tearDown() {
        db.close()
        spoolDir.deleteRecursively()
    }

    private fun createFrameFile(sessionId: String, captureId: String, idx: Int, content: String = "jpeg-fake-$idx-${System.nanoTime()}"): Pair<File, String> {
        val dir = File(spoolDir, sessionId).apply { mkdirs() }
        val file = File(dir, "${captureId}_${idx}.jpg")
        file.writeBytes(content.toByteArray())
        val sha = Sha256Util.sha256HexStreaming(file)
        return file to sha
    }

    private fun createWorkerWithFake(frameId: String, api: ApiService): UploadWorker {
        val input = androidx.work.Data.Builder()
            .putString(UploadWorker.KEY_FRAME_ID, frameId)
            .build()
        val workerFactory = object : androidx.work.WorkerFactory() {
            override fun createWorker(
                appContext: Context,
                workerClassName: String,
                workerParameters: androidx.work.WorkerParameters
            ): androidx.work.ListenableWorker = UploadWorker(appContext, workerParameters, api, db)
        }
        return androidx.work.testing.TestListenableWorkerBuilder<UploadWorker>(context)
            .setInputData(input)
            .setWorkerFactory(workerFactory)
            .build()
    }

    @Test
    fun `recalcula SHA streaming e falha se mismatch`() = runBlocking {
        val (file, sha) = createFrameFile("S-1", "cap-001", 0, "original")
        val frame = PendingFrame(sessionId = "S-1", captureId = "cap-001", frameIndex = 0, sha256 = sha, filePath = file.absolutePath, resolution = "1280x720", orientation = 0, createdAt = System.currentTimeMillis())
        db.spoolDao().insert(frame)
        // Corromper arquivo após insert
        file.writeBytes("corrupted".toByteArray())

        val api = FakeApiService()
        val worker = createWorkerWithFake(frame.id, api)
        val result = worker.doWork()
        assertTrue(result is ListenableWorker.Result.Failure)
        assertTrue((result as ListenableWorker.Result.Failure).outputData.getString("error")!!.contains("sha mismatch"))
    }

    @Test
    fun `2xx marca ACK e apaga arquivo`() = runBlocking {
        val (file, sha) = createFrameFile("S-2", "cap-002", 0)
        val frame = PendingFrame(sessionId = "S-2", captureId = "cap-002", frameIndex = 0, sha256 = sha, filePath = file.absolutePath, resolution = "1920x1080", orientation = 90, createdAt = System.currentTimeMillis())
        db.spoolDao().insert(frame)
        assertTrue(file.exists())

        val api = FakeApiService(uploadResponse = Response.success(FrameUploadResponse(ok = true, storageKey = "sessions/S-2/frames/cap-002/0.jpg", duplicate = false)))
        val worker = createWorkerWithFake(frame.id, api)
        val result = worker.doWork()
        assertTrue(result is ListenableWorker.Result.Success)
        val after = db.spoolDao().findById(frame.id)!!
        assertTrue(after.ack)
        assertFalse(file.exists())
        assertEquals("S-2", api.lastUploadCall!!.first)
    }

    @Test
    fun `409 failure nao retry`() = runBlocking {
        val (file, sha) = createFrameFile("S-3", "cap-003", 0)
        val frame = PendingFrame(sessionId = "S-3", captureId = "cap-003", frameIndex = 0, sha256 = sha, filePath = file.absolutePath, resolution = "1280x720", orientation = 0, createdAt = System.currentTimeMillis())
        db.spoolDao().insert(frame)

        val errorBody = """{"detail":"Frame index 0 already exists with different sha256"}""".toResponseBody("application/json".toMediaType())
        val api = FakeApiService(uploadResponse = Response.error(409, errorBody))
        val worker = createWorkerWithFake(frame.id, api)
        val result = worker.doWork()
        assertTrue(result is ListenableWorker.Result.Failure)
        val after = db.spoolDao().findById(frame.id)!!
        assertEquals(1, after.attempts)
        assertFalse(after.ack)
        assertTrue(file.exists())
    }

    @Test
    fun `5xx retry com backoff`() = runBlocking {
        val (file, sha) = createFrameFile("S-4", "cap-004", 0)
        val frame = PendingFrame(sessionId = "S-4", captureId = "cap-004", frameIndex = 0, sha256 = sha, filePath = file.absolutePath, resolution = "1280x720", orientation = 0, createdAt = System.currentTimeMillis())
        db.spoolDao().insert(frame)

        val errorBody = "Internal Server Error".toResponseBody("text/plain".toMediaType())
        val api = FakeApiService(uploadResponse = Response.error(500, errorBody))
        val worker = createWorkerWithFake(frame.id, api)
        val result = worker.doWork()
        assertTrue(result is ListenableWorker.Result.Retry)
        assertEquals(1, db.spoolDao().findById(frame.id)!!.attempts)
    }

    @Test
    fun `408 e 429 retry`() = runBlocking {
        val (file, sha) = createFrameFile("S-5", "cap-005", 0)
        val frame = PendingFrame(sessionId = "S-5", captureId = "cap-005", frameIndex = 0, sha256 = sha, filePath = file.absolutePath, resolution = "1280x720", orientation = 0, createdAt = System.currentTimeMillis())
        db.spoolDao().insert(frame)

        var api = FakeApiService(uploadResponse = Response.error(408, "timeout".toResponseBody("text/plain".toMediaType())))
        var worker = createWorkerWithFake(frame.id, api)
        assertTrue(worker.doWork() is ListenableWorker.Result.Retry)

        api = FakeApiService(uploadResponse = Response.error(429, "rate limit".toResponseBody("text/plain".toMediaType())))
        worker = createWorkerWithFake(frame.id, api)
        assertTrue(worker.doWork() is ListenableWorker.Result.Retry)
    }

    @Test
    fun `4xx outros failure`() = runBlocking {
        val (file, sha) = createFrameFile("S-6", "cap-006", 0)
        val frame = PendingFrame(sessionId = "S-6", captureId = "cap-006", frameIndex = 0, sha256 = sha, filePath = file.absolutePath, resolution = "1280x720", orientation = 0, createdAt = System.currentTimeMillis())
        db.spoolDao().insert(frame)

        val api = FakeApiService(uploadResponse = Response.error(400, "bad request".toResponseBody("text/plain".toMediaType())))
        val worker = createWorkerWithFake(frame.id, api)
        val result = worker.doWork()
        assertTrue(result is ListenableWorker.Result.Failure)
    }

    @Test
    fun `arquivo inexistente failure permanente`() = runBlocking {
        val frame = PendingFrame(sessionId = "S-7", captureId = "cap-007", frameIndex = 0, sha256 = "a".repeat(64), filePath = "/nonexistent.jpg", resolution = "1280x720", orientation = 0, createdAt = System.currentTimeMillis())
        db.spoolDao().insert(frame)
        val api = FakeApiService()
        val worker = createWorkerWithFake(frame.id, api)
        val result = worker.doWork()
        assertTrue(result is ListenableWorker.Result.Failure)
    }
}
