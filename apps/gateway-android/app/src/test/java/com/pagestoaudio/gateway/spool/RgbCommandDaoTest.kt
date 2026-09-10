package com.pagestoaudio.gateway.spool

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import java.util.UUID
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** G06 JVM persistence tests for command reception, cursor, and event outbox. */
@RunWith(RobolectricTestRunner::class)
class RgbCommandDaoTest {

    private lateinit var database: AppDatabase
    private lateinit var dao: RgbCommandDao

    @Before
    fun setUp() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        database = Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        dao = database.rgbCommandDao()
    }

    @After
    fun tearDown() {
        database.close()
    }

    private fun command(
        id: String = UUID.randomUUID().toString(),
        status: String = "QUEUED",
    ) = PendingRgbCommand(
        commandId = id,
        deviceCode = "CAM-G06-001",
        kind = "TEST",
        status = status,
        requestedJson = "{\"rgb\":[255,0,0]}",
        effectiveJson = "{\"rgb\":[255,0,0]}",
        expiresAt = "2026-09-09T12:00:00Z",
        receivedAt = 1000L,
    )

    @Test
    fun `cloud page persists command before cursor`() = runBlocking {
        val first = command()
        dao.persistCloudPage(first.deviceCode, 1234L, listOf(first))

        assertEquals(1234L, dao.cursor(first.deviceCode)!!.cursor)
        assertEquals(first.commandId, dao.command(first.commandId)!!.commandId)
    }

    @Test
    fun `duplicate command is ignored and local state survives replay`() = runBlocking {
        val first = command(status = "RECEIVED")
        dao.insertCommandIfAbsent(first)
        dao.insertCommandIfAbsent(first.copy(status = "QUEUED"))

        assertEquals("RECEIVED", dao.command(first.commandId)!!.status)
        assertEquals(1, dao.commandsForDevice(first.deviceCode).size)
    }

    @Test
    fun `event outbox is unique and remains pending until cloud ack`() = runBlocking {
        val first = command()
        dao.insertCommandIfAbsent(first)
        val event = RgbEventOutbox(
            commandId = first.commandId,
            deviceCode = first.deviceCode,
            idempotencyKey = "${first.commandId}:RECEIVED",
            event = "RECEIVED",
            payloadJson = "{}",
            effectivePayloadJson = "{\"status\":\"RECEIVED\"}",
            createdAt = 1001L,
        )

        assertEquals(1L, dao.insertEventIfAbsent(event))
        assertEquals(-1L, dao.insertEventIfAbsent(event))
        assertEquals(1, dao.pendingEvents().size)
        assertNotNull(dao.event(first.commandId, event.idempotencyKey))

        dao.markEventSent(first.commandId, event.idempotencyKey, 2000L)
        assertTrue(dao.pendingEvents().isEmpty())
    }
}
