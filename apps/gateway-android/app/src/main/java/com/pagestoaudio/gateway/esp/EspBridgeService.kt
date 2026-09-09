package com.pagestoaudio.gateway.esp

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import com.pagestoaudio.gateway.GatewayApplication
import com.pagestoaudio.gateway.R
import com.pagestoaudio.gateway.domain.SessionRepository
import com.pagestoaudio.gateway.spool.PendingFrame
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/**
 * S03.1/S03.10 — ponte local ESP como ForegroundService.
 *
 * Ciclo de vida: criado somente quando o modo ESP é habilitado com serviço
 * pronto (modo ESP nunca selecionável sem readiness). Mantém discovery UDP
 * 8786 + HTTP local 8787, WakeLock parcial, notificação persistente, e
 * reconcilia spool antes do primeiro ACK após reinício.
 */
class EspBridgeService : Service() {

    companion object {
        private const val TAG = "EspBridge"
        private const val CHANNEL_ID = "esp_bridge"
        private const val NOTIF_ID = 8787
        const val ACTION_START = "com.pagestoaudio.gateway.esp.START"
        const val ACTION_STOP = "com.pagestoaudio.gateway.esp.STOP"

        @Volatile
        var isRunning: Boolean = false
            private set
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var discovery: EspDiscoveryResponder? = null
    private var server: EspHttpServer? = null
    private var wakeLock: PowerManager.WakeLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createChannel()
        startForeground(NOTIF_ID, buildNotification("Ponte ESP pronta"))
        val app = application as GatewayApplication
        val provisioning = EspProvisioning(this)
        discovery = EspDiscoveryResponder(provisioning, scope).also { it.start() }
        val bridge = object : EspHttpServer.EspCloudBridge {
            override suspend fun startForDevice(deviceId: String, resumeHint: Boolean, lastSessionId: String?): EspHttpServer.CloudSession {
                val res = app.sessionRepository.startSession(
                    allowNewSession = !resumeHint,
                    resumeHint = lastSessionId,
                    lastSessionId = lastSessionId
                )
                val success = res as? SessionRepository.SessionResult.Success
                    ?: throw IllegalStateException("cloud start failed: $res")
                val state = success.state
                return EspHttpServer.CloudSession(state.sessionId, state.resumed, state.cursor)
            }

            override suspend fun enqueueCloudUpload(frame: PendingFrame) {
                app.spoolRepository.enqueueUpload(frame)
            }

            override suspend fun cloudCaptureComplete(sessionId: String, captureId: String, frames: Int): Boolean {
                // Efetiva cloud somente com recebidos conciliados: confere spool local.
                val pending = app.spoolRepository.pendingForSession(sessionId).count {
                    it.captureId == captureId && !it.ack
                }
                if (pending > 0) return false
                return app.sessionRepository.captureComplete(sessionId, captureId, frames).isSuccess
            }

            override suspend fun cloudCommand(sessionId: String, cursor: Long): EspHttpServer.CloudCommand? {
                val res = app.sessionRepository.fetchCommand(sessionId, cursor, waitMs = 0, phase = "CAPTURE")
                val cmd = res.getOrNull() ?: return null
                return EspHttpServer.CloudCommand(cmd.command, cmd.cursor, "{}")
            }

            override suspend fun cloudResult(sessionId: String, cursor: Long): String? {
                val res = app.sessionRepository.fetchResult(sessionId, cursor)
                val body = res.getOrNull() ?: return null
                return org.json.JSONObject()
                    .put("command", body?.command)
                    .put("cursor", body?.cursor)
                    .toString()
            }
        }
        server = EspHttpServer(provisioning, app.spoolRepository, filesDir, scope, cloud = bridge).also { it.start() }
        wakeLock = (getSystemService(POWER_SERVICE) as PowerManager)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "PagesToAudio:EspBridge").apply {
                try { acquire(10 * 60 * 60 * 1000L) } catch (_: Exception) {}
            }
        // S03.5: reconcilia arquivo/Room antes do primeiro ACK após (re)início.
        scope.launchWithReconcile(app)
        isRunning = true
        Log.i(TAG, "EspBridgeService iniciado (discovery 8786 + local 8787)")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        return START_STICKY
    }

    override fun onDestroy() {
        try { discovery?.stop() } catch (_: Exception) {}
        try { server?.stop() } catch (_: Exception) {}
        try {
            if (wakeLock?.isHeld == true) wakeLock?.release()
        } catch (_: Exception) {}
        scope.cancel()
        isRunning = false
        Log.i(TAG, "EspBridgeService encerrado de forma limpa")
        super.onDestroy()
    }

    private fun CoroutineScope.launchWithReconcile(app: GatewayApplication) {
        launch {
            try {
                val report = app.spoolRepository.reconcileLocalSpool()
                Log.i(TAG, "reconcileLocalSpool: checked=${report.pendingChecked} missing=${report.missingFiles}")
            } catch (e: Exception) {
                Log.w(TAG, "reconcile falhou", e)
            }
        }
    }

    private fun createChannel() {
        try {
            val nm = getSystemService(NotificationManager::class.java) ?: return
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "Ponte ESP", NotificationManager.IMPORTANCE_LOW)
            )
        } catch (_: Exception) {}
    }

    private fun buildNotification(text: String): Notification {
        return try {
            NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("Pages to Audio — ponte ESP")
                .setContentText(text)
                .setSmallIcon(R.mipmap.ic_launcher)
                .setOngoing(true)
                .build()
        } catch (_: Exception) {
            Notification.Builder(this, CHANNEL_ID)
                .setContentTitle("Pages to Audio — ponte ESP")
                .setContentText(text)
                .build()
        }
    }
}
