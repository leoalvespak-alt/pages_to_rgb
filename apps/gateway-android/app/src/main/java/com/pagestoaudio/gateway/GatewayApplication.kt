package com.pagestoaudio.gateway

import android.app.Application
import android.util.Log
import com.pagestoaudio.gateway.BuildConfig
import androidx.work.Configuration
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import com.pagestoaudio.gateway.domain.GatewayConfig
import com.pagestoaudio.gateway.domain.RgbCommandRepository
import com.pagestoaudio.gateway.domain.SessionRepository
import com.pagestoaudio.gateway.network.ApiService
import com.pagestoaudio.gateway.network.FallbackDns
import com.pagestoaudio.gateway.network.GatewayAuthInterceptor
import com.pagestoaudio.gateway.spool.AppDatabase
import com.pagestoaudio.gateway.spool.SpoolRepository
import com.pagestoaudio.gateway.sync.UploadWorker
import okhttp3.Dns
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.dnsoverhttps.DnsOverHttps
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.net.InetAddress
import java.util.concurrent.TimeUnit

class GatewayApplication : Application(), Configuration.Provider {

    companion object {
        private const val TAG = "GatewayApp"
    }

    lateinit var config: GatewayConfig
        private set

    lateinit var database: AppDatabase
        private set

    lateinit var spoolRepository: SpoolRepository
        private set

    lateinit var apiService: ApiService
        private set

    lateinit var sessionRepository: SessionRepository
        private set

    lateinit var rgbCommandRepository: RgbCommandRepository
        private set

    lateinit var okHttpClient: OkHttpClient
        private set

    override fun onCreate() {
        super.onCreate()
        config = GatewayConfig.fromEnv()
        database = AppDatabase.getInstance(this)

        okHttpClient = buildOkHttpClient()

        val retrofit = Retrofit.Builder()
            .baseUrl(config.baseUrl)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()

        apiService = retrofit.create(ApiService::class.java)
        rgbCommandRepository = RgbCommandRepository(apiService, database)
        sessionRepository = SessionRepository(apiService, config.deviceId, config.deviceSecret, database.sessionHistoryDao())
        spoolRepository = SpoolRepository(this, database.spoolDao(), WorkManager.getInstance(this))

        Log.i(TAG, "GatewayApplication initialized baseUrl=${config.baseUrl} deviceId=${config.deviceId}")
    }

    /** Reconciles cloud commands without requiring an Activity or open screen. */
    fun enqueueRgbCommandSync(deviceCode: String) {
        if (!config.isProvisioned || deviceCode.isBlank()) return
        val request = OneTimeWorkRequestBuilder<com.pagestoaudio.gateway.sync.RgbCommandSyncWorker>()
            .setInputData(
                androidx.work.Data.Builder()
                    .putString(com.pagestoaudio.gateway.sync.RgbCommandSyncWorker.KEY_DEVICE_ID, deviceCode)
                    .build()
            )
            .setConstraints(
                Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()
            )
            .setBackoffCriteria(
                androidx.work.BackoffPolicy.EXPONENTIAL,
                5,
                java.util.concurrent.TimeUnit.SECONDS,
            )
            .addTag("rgb-command-sync")
            .addTag("device:$deviceCode")
            .build()
        WorkManager.getInstance(this).enqueueUniqueWork(
            "rgb-command-sync-$deviceCode",
            ExistingWorkPolicy.KEEP,
            request,
        )
    }

    private fun buildOkHttpClient(): OkHttpClient {
        val logging = HttpLoggingInterceptor { msg -> Log.d("OkHttp", msg) }.apply {
            // BODY logging can expose signed headers and captured images. Keep it
            // disabled in release; verbose diagnostics are debug-only.
            level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.BASIC else HttpLoggingInterceptor.Level.NONE
        }
        val bootstrapClient = OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(10, TimeUnit.SECONDS)
            .build()
        val dnsOverHttps = DnsOverHttps.Builder()
            .client(bootstrapClient)
            .url("https://cloudflare-dns.com/dns-query".toHttpUrl())
            .bootstrapDnsHosts(
                InetAddress.getByName("1.1.1.1"),
                InetAddress.getByName("1.0.0.1")
            )
            .build()
        val resilientDns = FallbackDns(Dns.SYSTEM, dnsOverHttps) { hostname, failure ->
            Log.w(TAG, "DNS do Android falhou para $hostname; usando DNS seguro alternativo", failure)
        }
        return OkHttpClient.Builder()
            .dns(resilientDns)
            .addInterceptor(GatewayAuthInterceptor(
                deviceIdProvider = { config.deviceId },
                deviceSecretProvider = { config.deviceSecret },
                firmwareVersionProvider = { "gateway-android/${BuildConfig.VERSION_NAME}" },
                // S01.3: identidade cloud provisionada (X-Gateway-Id + Bearer).
                gatewayIdProvider = { config.gatewayId ?: config.deviceId },
                gatewaySecretProvider = { config.gatewaySecret ?: config.deviceSecret }
            ))
            .addInterceptor(logging)
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS) // long-polling wait_ms=25000 precisa >25s
            .writeTimeout(30, TimeUnit.SECONDS)
            .build()
    }

    // WorkManager config — permite injeção custom de ApiService no UploadWorker via WorkerFactory
    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder()
            .setMinimumLoggingLevel(Log.INFO)
            .setWorkerFactory(GatewayWorkerFactory(apiService, database))
            .build()
}

/**
 * WorkerFactory para injetar ApiService e Database nos Workers.
 */
class GatewayWorkerFactory(
    private val apiService: ApiService,
    private val database: AppDatabase
) : androidx.work.WorkerFactory() {
    override fun createWorker(
        appContext: android.content.Context,
        workerClassName: String,
        workerParameters: androidx.work.WorkerParameters
    ): androidx.work.ListenableWorker? {
        return when (workerClassName) {
            UploadWorker::class.java.name -> UploadWorker(appContext, workerParameters, apiService, database)
            com.pagestoaudio.gateway.sync.CommandPollWorker::class.java.name ->
                com.pagestoaudio.gateway.sync.CommandPollWorker(appContext, workerParameters, apiService, null, null, null)
            com.pagestoaudio.gateway.sync.RgbCommandSyncWorker::class.java.name ->
                com.pagestoaudio.gateway.sync.RgbCommandSyncWorker(appContext, workerParameters)
            else -> null // fallback para default factory
        }
    }
}
