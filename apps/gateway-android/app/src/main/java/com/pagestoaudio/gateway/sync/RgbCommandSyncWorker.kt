package com.pagestoaudio.gateway.sync

import android.content.Context
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.pagestoaudio.gateway.GatewayApplication
import androidx.work.Data

/** Polls cloud RGB commands and drains the local ESP event outbox. */
class RgbCommandSyncWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {

    companion object {
        private const val TAG = "RgbCommandSyncWorker"
        const val KEY_DEVICE_ID = "device_id"
        const val KEY_CURSOR = "cursor"
    }

    override suspend fun doWork(): Result {
        val deviceCode = inputData.getString(KEY_DEVICE_ID)
            ?: return Result.failure()
        val app = applicationContext as? GatewayApplication
            ?: return Result.failure()
        return try {
            val polled = app.rgbCommandRepository.pollDevice(deviceCode)
            if (polled.isFailure) {
                Log.w(TAG, "RGB command poll failed for $deviceCode", polled.exceptionOrNull())
                return Result.retry()
            }
            val drained = app.rgbCommandRepository.drainEvents()
                .getOrElse { error ->
                    Log.w(TAG, "RGB event drain failed", error)
                    return Result.retry()
                }
            val result = polled.getOrThrow()
            if (drained.retryableFailure) {
                return Result.retry()
            }
            Result.success(
                Data.Builder()
                    .putString(KEY_DEVICE_ID, deviceCode)
                    .putLong(KEY_CURSOR, result.cursor)
                    .putInt("received", result.received)
                    .putInt("events_sent", drained.sent)
                    .build()
            )
        } catch (error: Exception) {
            Log.w(TAG, "RGB command sync failed", error)
            Result.retry()
        }
    }
}
