package com.pagestoaudio.gateway.spool

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import java.util.UUID
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/** G06 device-side Room check; execute with connectedAndroidTest on an authorized device. */
@RunWith(AndroidJUnit4::class)
class RgbCommandPersistenceInstrumentedTest {
    private lateinit var database: AppDatabase

    @Before
    fun setUp() {
        database = Room.inMemoryDatabaseBuilder(
            ApplicationProvider.getApplicationContext<Context>(),
            AppDatabase::class.java,
        ).build()
    }

    @After
    fun tearDown() {
        database.close()
    }

    @Test
    fun commandAndCursorAreDurableWithinProcess() = runBlocking {
        val device = "CAM-G06-INSTRUMENTED"
        val command = PendingRgbCommand(
            commandId = UUID.randomUUID().toString(),
            deviceCode = device,
            kind = "TEST",
            status = "QUEUED",
            requestedJson = "{\"rgb\":[0,255,0]}",
            effectiveJson = "{\"rgb\":[0,255,0]}",
            expiresAt = "2026-09-09T12:00:00Z",
            receivedAt = 1L,
        )
        val dao = database.rgbCommandDao()
        dao.persistCloudPage(device, 10L, listOf(command))

        assertEquals(10L, dao.cursor(device)!!.cursor)
        assertTrue(dao.commandsForDevice(device).isNotEmpty())
    }
}
