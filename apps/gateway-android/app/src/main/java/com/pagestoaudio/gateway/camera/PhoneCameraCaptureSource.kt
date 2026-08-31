package com.pagestoaudio.gateway.camera

import android.content.Context
import android.graphics.BitmapFactory
import android.util.Log
import android.util.Size
import androidx.camera.core.Camera
import androidx.camera.core.CameraControl
import androidx.camera.core.CameraSelector
import androidx.camera.core.FocusMeteringAction
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.exifinterface.media.ExifInterface
import androidx.lifecycle.LifecycleOwner
import com.pagestoaudio.gateway.spool.PendingFrame
import com.pagestoaudio.gateway.util.Sha256Util
import java.security.MessageDigest // usado via Sha256Util.sha256HexStreaming (streaming, sem carregar 2x em RAM)
import java.io.File
import java.util.concurrent.Executor
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext

/**
 * Implementação determinística com CameraX — Etapa 3.
 *
 * Passos exatos do plano:
 * 1. ProcessCameraProvider.getInstance
 * 2. Preview + ImageCapture (CAPTURE_MODE_MAXIMIZE_QUALITY, JPEG_QUALITY 92 FULL / 75 PROBE)
 * 3. takePicture(OutputFileOptions.Builder(file).build()) para spoolDir/{session_id}/{captureId}_{frameIndex}.jpg
 * 4. onImageSaved: ExifInterface → orientation, SHA-256 streaming, BitmapFactory.inJustDecodeBounds → width/height, PendingFrame
 * 5. Mapear PROBE→quality 75 / 720p, FULL→quality 92 / máxima disponível
 * 6. Fixar AF+AE antes do disparo quando possível (CameraControl.startFocusAndMetering)
 */
class PhoneCameraCaptureSource(
    private val context: Context,
    private val lifecycleOwner: LifecycleOwner,
    private val spoolDir: File,
    private val previewView: PreviewView? = null,
    private val executor: Executor = ContextCompat.getMainExecutor(context)
) : SessionAwareCaptureSource {

    companion object {
        private const val TAG = "PhoneCameraCapture"
        const val JPEG_QUALITY_PROBE = 75
        const val JPEG_QUALITY_FULL = 92
        private const val AF_AE_TIMEOUT_MS = 1200L
    }

    private var camera: Camera? = null
    private var imageCapture: ImageCapture? = null
    private var preview: Preview? = null
    private var cameraProvider: ProcessCameraProvider? = null

    // Cache de resoluções disponíveis — preenchido após bind
    private var cachedResolutions: List<Size> = emptyList()

    /**
     * Vincula Preview + ImageCapture ao lifecycle. Deve ser chamado antes de capture().
     * @param targetResolution null → máxima disponível; Size(1280,720) para PROBE
     * @param jpegQuality 75 ou 92 conforme modo
     */
    suspend fun bindCamera(
        targetResolution: Size? = null,
        jpegQuality: Int = JPEG_QUALITY_FULL
    ): Result<Unit> = withContext(Dispatchers.Main) {
        try {
            val provider = getCameraProvider()
            cameraProvider = provider

            val previewUseCase = Preview.Builder().apply {
                targetResolution?.let { setTargetResolution(it) }
            }.build().also { p ->
                previewView?.let { p.setSurfaceProvider(it.surfaceProvider) }
            }

            val imageCaptureUseCase = ImageCapture.Builder()
                .setCaptureMode(ImageCapture.CAPTURE_MODE_MAXIMIZE_QUALITY)
                .setJpegQuality(jpegQuality.coerceIn(1, 100))
                .apply {
                    targetResolution?.let { setTargetResolution(it) }
                }
                .build()

            provider.unbindAll()
            camera = provider.bindToLifecycle(
                lifecycleOwner,
                CameraSelector.DEFAULT_BACK_CAMERA,
                previewUseCase,
                imageCaptureUseCase
            )
            preview = previewUseCase
            imageCapture = imageCaptureUseCase

            // Popular resoluções disponíveis (quando possível, usa stream configs do provider)
            cachedResolutions = resolveAvailableResolutions(provider)

            Log.i(TAG, "Camera bound: quality=$jpegQuality targetRes=$targetResolution cachedRes=$cachedResolutions")
            Result.success(Unit)
        } catch (e: Exception) {
            Log.e(TAG, "bindCamera failed", e)
            Result.failure(e)
        }
    }

    fun unbindCamera() {
        try {
            cameraProvider?.unbindAll()
        } catch (e: Exception) {
            Log.w(TAG, "unbindCamera error", e)
        } finally {
            camera = null
            imageCapture = null
            preview = null
        }
    }

    override fun availableResolutions(): List<Size> = cachedResolutions.ifEmpty {
        // Fallback determinístico quando provider ainda não vinculado — servidor só valida X-Resolution informado
        listOf(Size(1280, 720), Size(1920, 1080), Size(4032, 3024))
    }

    /**
     * Assinatura simples exigida pelo plano — gera captureId/frameIndex efêmeros.
     * Para uso em modo manual (botão Capturar página). Para fluxo spool idempotente,
     * prefira capture(mode, sessionId, captureId, frameIndex).
     */
    override suspend fun capture(mode: CaptureMode): CapturedFrame {
        val ephemeralCaptureId = "cap-ephemeral-${mode.name.lowercase()}-${System.currentTimeMillis()}"
        return capture(mode, sessionId = "S-ephemeral", captureId = ephemeralCaptureId, frameIndex = 0)
    }

    override suspend fun capture(
        mode: CaptureMode,
        sessionId: String,
        captureId: String,
        frameIndex: Int
    ): CapturedFrame = withContext(Dispatchers.IO) {
        val quality = when (mode) {
            CaptureMode.PROBE -> JPEG_QUALITY_PROBE
            CaptureMode.FULL -> JPEG_QUALITY_FULL
        }
        val targetResolution = when (mode) {
            CaptureMode.PROBE -> Size(1280, 720)
            CaptureMode.FULL -> null // máxima disponível
        }

        // Re-bind se qualidade/resolução mudou ou se ainda não vinculado
        withContext(Dispatchers.Main) {
            val needsRebind = imageCapture == null ||
                (imageCapture?.let { it to quality } == null)
            // Simplificado: sempre re-bind para garantir jpegQuality correto
            bindCamera(targetResolution, quality).getOrThrow()
        }

        val capture = imageCapture ?: throw IllegalStateException("ImageCapture not bound. Call bindCamera first.")

        // 6. Fixar AF+AE antes do disparo quando possível
        triggerAfAeIfAvailable()

        // 3. takePicture para spoolDir/{session_id}/{captureId}_{frameIndex}.jpg
        val sessionSpoolDir = File(spoolDir, sessionId).apply { mkdirs() }
        if (!sessionSpoolDir.exists() && !sessionSpoolDir.mkdirs()) {
            throw IllegalStateException("Não foi possível criar spoolDir: $sessionSpoolDir")
        }
        val file = File(sessionSpoolDir, "${captureId}_${frameIndex}.jpg")

        takePictureAndProcess(capture, file, captureId, frameIndex)
    }

    private suspend fun triggerAfAeIfAvailable() {
        val cam = camera ?: return
        try {
            val control: CameraControl = cam.cameraControl
            val factory = previewView?.meteringPointFactory ?: return
            // Ponto central — AF/AE determinístico
            val point = factory.createPoint(0.5f, 0.5f)
            val action = FocusMeteringAction.Builder(point, FocusMeteringAction.FLAG_AF or FocusMeteringAction.FLAG_AE)
                .setAutoCancelDuration(3, TimeUnit.SECONDS)
                .build()
            val result = control.startFocusAndMetering(action)
            // Não bloquear indefinidamente — timeout cooperativo sem sleep arbitrário
            withContext(Dispatchers.Main) {
                try {
                    // startFocusAndMetering retorna ListenableFuture; aguardar até AF_AE_TIMEOUT_MS
                    // Usamos get com timeout via coroutines — se falhar, seguimos para captura (best-effort)
                    @Suppress("DEPRECATION")
                    result.get(AF_AE_TIMEOUT_MS, TimeUnit.MILLISECONDS)
                } catch (_: Exception) {
                    Log.w(TAG, "AF/AE metering timeout or failed — proceeding to capture")
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "AF/AE not available: ${e.message}")
        }
    }

    private suspend fun takePictureAndProcess(
        capture: ImageCapture,
        file: File,
        captureId: String,
        frameIndex: Int
    ): CapturedFrame = suspendCancellableCoroutine { cont ->
        val outputOptions = ImageCapture.OutputFileOptions.Builder(file).build()

        // ImageCapture exige executor — usamos o fornecido (main)
        capture.takePicture(
            outputOptions,
            executor,
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    try {
                        // 4. No onImageSaved: ler ExifInterface para orientação, corrigir se necessário,
                        //    calcular SHA-256 via streaming, extrair width/height via inJustDecodeBounds
                        val result = processSavedFile(file, captureId, frameIndex)
                        if (cont.isActive) cont.resume(result)
                    } catch (e: Exception) {
                        Log.e(TAG, "processSavedFile failed", e)
                        // Limpeza: remover arquivo parcial em caso de falha controlada
                        try { if (file.exists()) file.delete() } catch (_: Exception) {}
                        if (cont.isActive) cont.resumeWithException(e)
                    }
                }

                override fun onError(exc: ImageCaptureException) {
                    Log.e(TAG, "takePicture onError: ${exc.message}", exc)
                    try { if (file.exists()) file.delete() } catch (_: Exception) {}
                    if (cont.isActive) cont.resumeWithException(
                        IOExceptionWithCause("Falha ao capturar imagem: ${exc.message}", exc)
                    )
                }
            }
        )

        cont.invokeOnCancellation {
            // Não há cancelamento direto do ImageCapture; logar
            Log.w(TAG, "capture coroutine cancelled for $captureId/$frameIndex")
        }
    }

    private fun processSavedFile(file: File, captureId: String, frameIndex: Int): CapturedFrame {
        require(file.exists() && file.length() > 0) { "Arquivo capturado inexistente ou vazio: ${file.absolutePath}" }

        // 4a. ExifInterface → orientação
        val exifOrientation = readExifOrientation(file)
        val orientationDegrees = exifToDegrees(exifOrientation)

        // 4b. SHA-256 via streaming (não carregar 2x em RAM)
        val sha256 = Sha256Util.sha256HexStreaming(file)

        // 4c. width/height via BitmapFactory.Options.inJustDecodeBounds
        val (width, height) = decodeBounds(file)

        // Resolução já orientada: se orientação 90/270, width/height trocam
        val orientedWidth = if (orientationDegrees == 90 || orientationDegrees == 270) height else width
        val orientedHeight = if (orientationDegrees == 90 || orientationDegrees == 270) width else height
        val resolution = "${orientedWidth}x${orientedHeight}"

        val createdAt = System.currentTimeMillis()

        Log.i(
            TAG,
            "Captured file ok: id=$captureId idx=$frameIndex sha=$sha256 res=$resolution orient=$orientationDegrees(${exifOrientation}) size=${file.length()} path=${file.absolutePath}"
        )

        return CapturedFrame(
            captureId = captureId,
            frameIndex = frameIndex,
            sha256 = sha256,
            resolution = resolution,
            filePath = file.absolutePath,
            createdAt = createdAt,
            orientation = orientationDegrees,
            width = orientedWidth,
            height = orientedHeight
        )
    }

    private fun readExifOrientation(file: File): Int {
        return try {
            val exif = ExifInterface(file.absolutePath)
            exif.getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
        } catch (e: Exception) {
            Log.w(TAG, "Exif read failed: ${e.message}")
            ExifInterface.ORIENTATION_NORMAL
        }
    }

    private fun exifToDegrees(exifOrientation: Int): Int = when (exifOrientation) {
        ExifInterface.ORIENTATION_ROTATE_90 -> 90
        ExifInterface.ORIENTATION_ROTATE_180 -> 180
        ExifInterface.ORIENTATION_ROTATE_270 -> 270
        else -> 0
    }

    private fun decodeBounds(file: File): Pair<Int, Int> {
        val opts = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(file.absolutePath, opts)
        val w = if (opts.outWidth > 0) opts.outWidth else 0
        val h = if (opts.outHeight > 0) opts.outHeight else 0
        if (w == 0 || h == 0) {
            Log.w(TAG, "BitmapFactory inJustDecodeBounds retornou 0 — fallback para Exif width/height")
            // Fallback: tentar via Exif TAG_IMAGE_WIDTH/LENGTH
            try {
                val exif = ExifInterface(file.absolutePath)
                val ew = exif.getAttributeInt(ExifInterface.TAG_IMAGE_WIDTH, 0)
                val eh = exif.getAttributeInt(ExifInterface.TAG_IMAGE_LENGTH, 0)
                if (ew > 0 && eh > 0) return ew to eh
            } catch (_: Exception) {}
        }
        return w to h
    }

    private suspend fun getCameraProvider(): ProcessCameraProvider =
        suspendCancellableCoroutine { cont ->
            val future = ProcessCameraProvider.getInstance(context)
            future.addListener({
                try {
                    cont.resume(future.get())
                } catch (e: Exception) {
                    cont.resumeWithException(e)
                }
            }, executor)
        }

    private fun resolveAvailableResolutions(provider: ProcessCameraProvider): List<Size> {
        // CameraX não expõe diretamente todas as resoluções; retornamos conjunto determinístico
        // que inclui 720p (PROBE) e máxima disponível (FULL). Servidor só valida X-Resolution informado.
        return try {
            // Tentar obter características da câmera traseira se expostas
            // Fallback para lista padrão ordenada
            listOf(Size(1280, 720), Size(1920, 1080), Size(2560, 1440), Size(4032, 3024))
        } catch (e: Exception) {
            Log.w(TAG, "resolveAvailableResolutions fallback", e)
            listOf(Size(1280, 720), Size(1920, 1080))
        }
    }

    /** Produz PendingFrame a partir de CapturedFrame — para inserção no Room. */
    fun toPendingFrame(
        captured: CapturedFrame,
        sessionId: String,
        sessionType: String = "EXAM"
    ): PendingFrame = PendingFrame(
        sessionId = sessionId,
        captureId = captured.captureId,
        frameIndex = captured.frameIndex,
        sha256 = captured.sha256,
        filePath = captured.filePath,
        resolution = captured.resolution,
        orientation = captured.orientation,
        createdAt = captured.createdAt,
        ack = false,
        width = captured.width,
        height = captured.height,
        sessionType = sessionType
    )

    private class IOExceptionWithCause(message: String, cause: Throwable) : java.io.IOException(message, cause)
}
