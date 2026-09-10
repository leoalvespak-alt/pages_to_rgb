package com.pagestoaudio.gateway.ui

import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.util.Log
import androidx.camera.view.PreviewView
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.pagestoaudio.gateway.GatewayApplication
import com.pagestoaudio.gateway.camera.CaptureMode
import com.pagestoaudio.gateway.camera.Esp32GatewayCaptureSource
import com.pagestoaudio.gateway.camera.PhoneCameraCaptureSource
import com.pagestoaudio.gateway.camera.SessionAwareCaptureSource
import com.pagestoaudio.gateway.domain.SessionRepository
import java.io.File
import java.net.SocketTimeoutException
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

data class SessionUiState(
    val sessionId: String? = null,
    val cursor: Long = 0,
    val isConnected: Boolean = false,
    val isCapturing: Boolean = false,
    val isStartingSession: Boolean = false,
    val isEndingSession: Boolean = false,
    val isPolling: Boolean = false,
    val captureSourceLabel: String = "Android", // Android | ESP32
    val sessionType: String = "EXAM", // EXAM | HANDWRITTEN_WORD
    val pageCount: Int = 0,
    val pendingCount: Int = 0,
    val lastFrameLabel: String? = null,
    val lastFrameAck: Boolean = false,
    val serverCommand: String = "—",
    val camera: CameraUiState = CameraUiState(),
    val rgbTest: RgbTestUi? = null,
    val logs: List<String> = emptyList(),
    val errorMessage: String? = null
)

data class RgbTestUi(
    val commandId: Int,
    val red: Int,
    val green: Int,
    val blue: Int,
    val brightnessPercent: Int,
    val onMs: Long,
    val offMs: Long,
    val active: Boolean = true,
    val status: String = "RECEIVED",
)

class SessionViewModel(
    private val app: GatewayApplication
) : ViewModel() {

    companion object {
        private const val TAG = "SessionVM"
    }

    private val _uiState = MutableStateFlow(SessionUiState())
    val uiState: StateFlow<SessionUiState> = _uiState.asStateFlow()

    private var phoneSource: PhoneCameraCaptureSource? = null
    private var esp32Source: Esp32GatewayCaptureSource = Esp32GatewayCaptureSource()
    private var previewView: PreviewView? = null
    private var lifecycleOwner: LifecycleOwner? = null

    private var pollJob: Job? = null
    private var heartbeatJob: Job? = null
    private var rgbTestJob: Job? = null
    private var networkCallback: ConnectivityManager.NetworkCallback? = null

    private val sessionRepository: SessionRepository get() = app.sessionRepository
    private val spoolRepository get() = app.spoolRepository

    private val timeFmt = SimpleDateFormat("HH:mm:ss", Locale.getDefault())

    init {
        // Observar fila pendente
        viewModelScope.launch {
            spoolRepository.pendingCountFlow().collect { count ->
                _uiState.update { it.copy(pendingCount = count) }
            }
        }
        // Re-enfileirar pendentes ao iniciar (ordem obrigatória: reenvio idempotente  → 200)
        viewModelScope.launch {
            try {
                val n = spoolRepository.reenqueueAllPending()
                if (n > 0) Log.i(TAG, "init reenqueueAllPending: $n frames")
            } catch (e: Exception) {
                Log.w(TAG, "reenqueue pendentes falhou", e)
            }
        }
        // Após corte de rede → quando voltar, re-enfileirar (Etapa 4 critério: religar → Fila: 0)
        registerNetworkCallback()
    }

    fun attachPreviewView(view: PreviewView) {
        previewView = view
        // Se já temos lifecycleOwner e estamos capturando, re-bind
        lifecycleOwner?.let { owner ->
            if (_uiState.value.isCapturing) {
                viewModelScope.launch { bindCamera(owner) }
            }
        }
    }

    suspend fun bindCamera(owner: LifecycleOwner) {
        lifecycleOwner = owner
        val view = previewView
        if (view == null) {
            Log.w(TAG, "bindCamera: previewView ainda não anexado")
            return
        }
        // S04.1: reutiliza binding durante a sessão (sem rebind por frame/tela).
        val spoolDir = File(app.filesDir, "spool")
        val source = phoneSource ?: PhoneCameraCaptureSource(app, owner, spoolDir, view).also {
            phoneSource = it
        }
        val result = source.bindCamera()
        if (result.isFailure) {
            log("Falha ao vincular câmera: ${result.exceptionOrNull()?.message}")
            _uiState.update { it.copy(errorMessage = "Falha ao abrir câmera: ${result.exceptionOrNull()?.message}") }
        } else {
            log("Câmera vinculada — Preview ativo")
            _uiState.update { it.copy(errorMessage = null) }
        }
    }

    fun unbindCamera() {
        try {
            phoneSource?.unbindCamera()
        } catch (e: Exception) {
            Log.w(TAG, "unbindCamera erro", e)
        }
    }

    fun setCameraMode(mode: String) {
        val normalized = if (mode == "PHOTO") "PHOTO" else "OCR"
        _uiState.update { it.copy(camera = it.camera.copy(mode = normalized), errorMessage = null) }
        log("Modo de camera solicitado: $normalized")
    }

    fun setCameraResolution(resolution: String) {
        if (resolution !in setOf("QVGA", "VGA", "SVGA", "XGA", "SXGA", "UXGA")) return
        _uiState.update { it.copy(camera = it.camera.copy(requestedResolution = resolution), errorMessage = null) }
    }

    fun setCameraJpegQuality(quality: Int) {
        _uiState.update { it.copy(camera = it.camera.copy(requestedJpegQuality = quality.coerceIn(8, 12))) }
    }

    fun setCameraTuning(name: String, value: Int) {
        val adjusted = value.coerceIn(-2, 2)
        _uiState.update { state ->
            state.copy(camera = when (name) {
                "brightness" -> state.camera.copy(brightness = adjusted)
                "contrast" -> state.camera.copy(contrast = adjusted)
                "saturation" -> state.camera.copy(saturation = adjusted)
                else -> state.camera
            })
        }
    }

    fun setCameraToggle(name: String, enabled: Boolean) {
        _uiState.update { state ->
            val camera = state.camera
            if (camera.unavailable.containsKey(name)) return@update state
            state.copy(camera = when (name) {
                "awb" -> camera.copy(awb = enabled)
                "awb_gain" -> camera.copy(awbGain = enabled)
                "aec" -> camera.copy(aec = enabled)
                "agc" -> camera.copy(agc = enabled)
                "bpc" -> camera.copy(bpc = enabled)
                "wpc" -> camera.copy(wpc = enabled)
                "raw_gamma" -> camera.copy(rawGamma = enabled)
                "lens_correction" -> camera.copy(lensCorrection = enabled)
                "dcw" -> camera.copy(dcw = enabled)
                "hmirror" -> camera.copy(hmirror = enabled)
                "vflip" -> camera.copy(vflip = enabled)
                "colorbar" -> camera.copy(colorbar = enabled)
                else -> camera
            })
        }
    }

    fun toggleCameraAdvanced() {
        _uiState.update { it.copy(camera = it.camera.copy(advancedExpanded = !it.camera.advancedExpanded)) }
    }

    /** Errors are rendered as OFFLINE/TIMEOUT and never converted into fake support. */
    fun refreshCameraCapabilities() {
        _uiState.update {
            it.copy(camera = it.camera.copy(
                capabilityStatus = "CHECKING",
                capabilityMessage = "Consultando capabilities do Gateway...",
            ))
        }
        viewModelScope.launch {
            val result = sessionRepository.cameraCapabilities(advertisedVersion = "v2")
            val capabilities = result.getOrNull()
            if (capabilities != null) {
                _uiState.update {
                    it.copy(camera = it.camera.copy(
                        capabilityStatus = if (capabilities.compatible) "ONLINE" else "INCOMPATIBLE",
                        capabilityMessage = capabilities.message.ifBlank {
                            if (capabilities.compatible) "Capabilities compativeis." else "Firmware incompativel com camera v2."
                        },
                        unavailable = capabilities.unavailable,
                        firmwareVersion = capabilities.firmwareVersion,
                        capabilitiesVersion = capabilities.version,
                    ))
                }
            } else {
                val error = result.exceptionOrNull()
                val timedOut = error is SocketTimeoutException || error?.cause is SocketTimeoutException
                _uiState.update {
                    it.copy(camera = it.camera.copy(
                        capabilityStatus = if (timedOut) "TIMEOUT" else "OFFLINE",
                        capabilityMessage = if (timedOut) {
                            "Timeout ao consultar capabilities; controles nao sao enviados."
                        } else {
                            "Gateway offline; controles nao sao enviados."
                        },
                    ))
                }
            }
        }
    }

    /** Stops only the local preview; APPLIED/OFF from the ESP remains the physical confirmation. */
    fun stopRgbTest() {
        val current = _uiState.value.rgbTest ?: return
        _uiState.update { it.copy(rgbTest = current.copy(active = false, status = "OFF")) }
        log("STOP visual local solicitado; confirmacao fisica depende de OFF da ESP")
    }

    fun selectCaptureSource(label: String) {
        // HANDWRITTEN_WORD só permite Android
        if (_uiState.value.sessionType == "HANDWRITTEN_WORD" && label == "ESP32") {
            _uiState.update { it.copy(errorMessage = "Teste manuscrito só em Android") }
            return
        }
        // S03.10: modo ESP somente após serviço pronto (readiness da ponte local).
        if (label == "ESP32" && !com.pagestoaudio.gateway.esp.EspBridgeService.isRunning) {
            _uiState.update { it.copy(errorMessage = "Ponte ESP não pronta — serviço local 8786/8787 indisponível") }
            log("ESP32 bloqueado: EspBridgeService não está em execução")
            return
        }
        _uiState.update { it.copy(captureSourceLabel = label, errorMessage = null) }
        log("Fonte selecionada: $label")
        if (label == "ESP32") {
            unbindCamera()
            _uiState.update { it.copy(isCapturing = false) }
        }
    }

    /** S03.10: habilita modo ESP com ForegroundService + permissões/notificação. */
    fun enableEspBridge(): Boolean {
        return try {
            val intent = android.content.Intent(app, com.pagestoaudio.gateway.esp.EspBridgeService::class.java)
            intent.action = com.pagestoaudio.gateway.esp.EspBridgeService.ACTION_START
            androidx.core.content.ContextCompat.startForegroundService(app, intent)
            // S04.7: retenção explícita — limpa ACKs antigos sem tocar pendências.
            viewModelScope.launch {
                try { spoolRepository.pruneAckedOlderThan(7) } catch (e: Exception) {
                    Log.w(TAG, "pruneAcked falhou", e)
                }
            }
            log("Ponte ESP habilitada — discovery 8786 + local 8787")
            true
        } catch (e: Exception) {
            _uiState.update { it.copy(errorMessage = "Falha ao iniciar ponte ESP: ${e.message}") }
            Log.w(TAG, "enableEspBridge falhou", e)
            false
        }
    }

    fun disableEspBridge() {
        try {
            val intent = android.content.Intent(app, com.pagestoaudio.gateway.esp.EspBridgeService::class.java)
            intent.action = com.pagestoaudio.gateway.esp.EspBridgeService.ACTION_STOP
            app.startService(intent)
        } catch (e: Exception) {
            Log.w(TAG, "disableEspBridge falhou", e)
        }
        if (_uiState.value.captureSourceLabel == "ESP32") {
            _uiState.update { it.copy(captureSourceLabel = "Android") }
        }
    }

    fun selectSessionType(type: String) {
        if (_uiState.value.sessionId != null) {
            _uiState.update { it.copy(errorMessage = "Encerre a sessão atual antes de trocar o modo") }
            return
        }
        val norm = if (type == "HANDWRITTEN_WORD") "HANDWRITTEN_WORD" else "EXAM"
        _uiState.update { it.copy(sessionType = norm, captureSourceLabel = if (norm == "HANDWRITTEN_WORD") "Android" else it.captureSourceLabel) }
        log("Modo selecionado: $norm")
    }

    private fun activeSource(): SessionAwareCaptureSource? {
        return when (_uiState.value.captureSourceLabel) {
            "ESP32" -> null // Esp32GatewayCaptureSource não é SessionAware; tratado como erro controlado
            else -> phoneSource
        }
    }

    fun startSession() {
        if (_uiState.value.isStartingSession) return
        viewModelScope.launch {
            _uiState.update { it.copy(isStartingSession = true, errorMessage = null) }
            val st = _uiState.value.sessionType
            val camera = _uiState.value.camera
            log("Iniciando sessão $st …")
            val result = if (st == "HANDWRITTEN_WORD") sessionRepository.startHandwrittenSession() else sessionRepository.startSession(
                allowNewSession = true,
                cameraMode = camera.mode,
                cameraCapabilitiesVersion = "v2",
            )
            when (result) {
                is SessionRepository.SessionResult.Success -> {
                    val s = result.state
                    _uiState.update {
                        it.copy(
                            sessionId = s.sessionId,
                            cursor = s.cursor,
                            isConnected = true,
                            isCapturing = true,
                            isStartingSession = false,
                            serverCommand = "CAPTURING",
                            pageCount = 0,
                            camera = it.camera.copy(
                                capabilityStatus = "ONLINE",
                                capabilityMessage = "Snapshot da sessão recebido; efetivo confirmado pelo backend.",
                                effectiveResolution = s.effectiveCameraConfig?.frameSize,
                                effectiveJpegQuality = s.effectiveCameraConfig?.androidJpegQualityPercent
                                    ?: s.effectiveCameraConfig?.espJpegQuality,
                                firmwareVersion = s.firmwareVersion,
                                capabilitiesVersion = s.capabilitiesVersion,
                            ),
                        )
                    }
                    log("Sessão iniciada: ${s.sessionId} resumed=${s.resumed}")
                    // Bind câmera agora que temos sessão
                    lifecycleOwner?.let { bindCamera(it) }
                    startPolling(s.sessionId, s.cursor)
                    startHeartbeat(s.sessionId)
                    startRgbTestPolling(s.sessionId)
                }
                is SessionRepository.SessionResult.Error -> {
                    _uiState.update { it.copy(isStartingSession = false, errorMessage = result.message) }
                    log("Erro ao iniciar sessão: ${result.message}")
                }
            }
        }
    }

    fun endSession() {
        val sid = _uiState.value.sessionId ?: return
        if (_uiState.value.isEndingSession) return
        viewModelScope.launch {
            _uiState.update { it.copy(isEndingSession = true) }
            // S04.3: parar produtor ANTES de drenar — nenhuma captura nova após drenagem.
            stopPolling()
            _uiState.update { it.copy(isCapturing = false) }
            try { unbindCamera() } catch (_: Exception) {}
            app.getSharedPreferences("close_intent", 0).edit().putString("closing_session", sid).apply()
            log("Encerrando sessão $sid — produtor parado, drenando spool…")
            val drained = awaitSpoolDrain(sid)
            if (!drained) {
                // S04.3/S04.4: timeout com pendências mantém fechamento pendente (nunca fecha).
                _uiState.update { it.copy(isEndingSession = false, errorMessage = "Fila com pendências — fechamento pendente, tente de novo") }
                log("Fechamento pendente: spool não drenou — sessão preservada")
                return@launch
            }
            val st = _uiState.value.sessionType
            val res = if (st == "HANDWRITTEN_WORD") sessionRepository.endHandwrittenSignal(sid) else sessionRepository.endSignal(sid)
            // S04.4: Result.failure tratado efetivamente (não só try/catch).
            if (res.isSuccess) {
                log("Sessão encerrada: $sid → LOCKED")
                _uiState.update { it.copy(isCapturing = false, isConnected = false, isEndingSession = false, serverCommand = "STOP") }
                stopHeartbeat()
                stopRgbTestPolling()
                app.getSharedPreferences("close_intent", 0).edit().remove("closing_session").apply()
            } else {
                val msg = res.exceptionOrNull()?.message ?: "erro desconhecido"
                _uiState.update { it.copy(isEndingSession = false, errorMessage = msg) }
                log("Falha ao encerrar: $msg — intenção de fechamento preservada")
            }
        }
    }

    /**
     * Modo manual — botão Capturar página gera CAPTURE_FULL localmente (3 frames, 180ms gap) e envia.
     * Usado quando servidor ainda não implementou GET /command de captura (fallback do plano §5).
     */
    fun captureManual(mode: CaptureMode) {
        val sid = _uiState.value.sessionId ?: run {
            _uiState.update { it.copy(errorMessage = "Inicie uma sessão antes de capturar") }
            return
        }
        if (_uiState.value.captureSourceLabel == "ESP32") {
            _uiState.update { it.copy(errorMessage = "ESP32 não conectado") }
            log("ESP32 não conectado — captura ignorada")
            return
        }
        val source = phoneSource ?: run {
            _uiState.update { it.copy(errorMessage = "Câmera não vinculada — aguarde Preview") }
            return
        }
        viewModelScope.launch {
            val captureId = "cap-${UUID.randomUUID().toString().take(8)}-${mode.name.lowercase()}-${System.currentTimeMillis()}"
            val frames = if (mode == CaptureMode.FULL) 3 else 1
            val gapMs = 180L
            log("Captura manual $mode: $captureId frames=$frames")
            repeat(frames) { idx ->
                try {
                    val st = _uiState.value.sessionType
                    val captured = source.capture(mode, sid, captureId, idx)
                    val pending = source.toPendingFrame(captured, sid, st)
                    val saveRes = spoolRepository.save(pending)
                    if (saveRes.isSuccess) {
                        _uiState.update {
                            it.copy(
                                pageCount = it.pageCount + 1,
                                lastFrameLabel = "Última: $captureId idx $idx ✓",
                                lastFrameAck = false
                            )
                        }
                        log("${ts()} frame $idx sha=${captured.sha256.take(12)}... ACK pendente → fila")
                    } else {
                        log("Falha ao salvar spool: ${saveRes.exceptionOrNull()?.message}")
                    }
                    if (idx == frames - 1) {
                        // S04.4/S04.6: capture-complete SOMENTE após confirmações; Result verificado.
                        val st2 = _uiState.value.sessionType
                        val cc = if (st2 == "HANDWRITTEN_WORD") sessionRepository.captureCompleteHandwritten(sid, captureId, frames) else sessionRepository.captureComplete(sid, captureId, frames)
                        if (cc.isSuccess) {
                            log("capture-complete enviado: $captureId type=$st2")
                        } else {
                            log("capture-complete FALHOU: ${cc.exceptionOrNull()?.message} — pendência preservada, sem fechar")
                            _uiState.update { it.copy(errorMessage = cc.exceptionOrNull()?.message) }
                        }
                    }
                    if (idx < frames - 1) delay(gapMs)
                } catch (e: Exception) {
                    log("Falha captura manual frame $idx: ${e.message}")
                    _uiState.update { it.copy(errorMessage = e.message) }
                }
            }
        }
    }

    private fun startPolling(sessionId: String, initialCursor: Long) {
        stopPolling()
        pollJob = viewModelScope.launch {
            // S04.5: cursor recuperado de armazenamento persistente (sobrevive a reinício).
            var cursor = loadCursor(sessionId, initialCursor)
            _uiState.update { it.copy(isPolling = true, cursor = cursor) }
            while (isActive) {
                try {
                    val st = _uiState.value.sessionType
                    val res = if (st == "HANDWRITTEN_WORD") sessionRepository.fetchHandwrittenCommand(sessionId, cursor, waitMs = 25000, phase = "CAPTURE") else sessionRepository.fetchCommand(sessionId, cursor, waitMs = 25000, phase = "CAPTURE")
                    if (res.isSuccess) {
                        val cmd = res.getOrNull()!!
                        log("CMD ${cmd.command} cursor=${cmd.cursor} cap=${cmd.captureId} frames=${cmd.frames}")

                        var effectOk = true
                        when (cmd.command) {
                            "CAPTURE_PROBE" -> effectOk = handleServerCapture(cmd.captureId, CaptureMode.PROBE, cmd.frames, cmd.gapMs, sessionId)
                            "CAPTURE_FULL" -> effectOk = handleServerCapture(cmd.captureId, CaptureMode.FULL, cmd.frames, cmd.gapMs, sessionId)
                            "PAUSE" -> {
                                _uiState.update { it.copy(isCapturing = false) }
                                unbindCamera()
                                log("PAUSE — preview pausado")
                            }
                            "RESUME" -> {
                                _uiState.update { it.copy(isCapturing = true) }
                                lifecycleOwner?.let { bindCamera(it) }
                                log("RESUME — preview retomado")
                            }
                            "PING" -> sessionRepository.heartbeat(sessionId, cursor = cursor)
                            "STOP" -> {
                                log("STOP do servidor — drain + end-signal")
                                endSession()
                                break
                            }
                            else -> {
                                // Comando desconhecido: nunca consome cursor (contrato §3.9).
                                Log.w(TAG, "Comando desconhecido ${cmd.command} — cursor preservado")
                                effectOk = false
                            }
                        }
                        // S04.5: cursor avança SOMENTE após efeito durável + ACK.
                        if (effectOk) {
                            try {
                                sessionRepository.ackCommand(sessionId, cmd.cursor)
                            } catch (e: Exception) {
                                Log.w(TAG, "ackCommand falhou cursor=${cmd.cursor}", e)
                            }
                            cursor = cmd.cursor
                            saveCursor(sessionId, cursor)
                            _uiState.update { it.copy(cursor = cursor, serverCommand = cmd.command) }
                        }
                    } else {
                        val err = res.exceptionOrNull()?.message
                        Log.w(TAG, "poll erro: $err — retry em 2s")
                        delay(2000)
                    }
                } catch (e: Exception) {
                    if (!isActive) break
                    Log.w(TAG, "poll exceção", e)
                    delay(2000)
                }
            }
            _uiState.update { it.copy(isPolling = false) }
        }
    }

    private fun cursorPrefs() = app.getSharedPreferences("cmd_cursor", 0)

    private fun loadCursor(sessionId: String, fallback: Long): Long {
        return try {
            val saved = cursorPrefs().getLong("cursor_$sessionId", -1L)
            if (saved >= 0) saved else fallback
        } catch (_: Exception) { fallback }
    }

    private fun saveCursor(sessionId: String, cursor: Long) {
        try {
            cursorPrefs().edit().putLong("cursor_$sessionId", cursor).apply()
        } catch (e: Exception) {
            Log.w(TAG, "saveCursor falhou", e)
        }
    }

    private suspend fun handleServerCapture(
        captureIdRaw: String?,
        mode: CaptureMode,
        frames: Int,
        gapMs: Long,
        sessionId: String
    ): Boolean {
        if (_uiState.value.captureSourceLabel == "ESP32") {
            log("ESP32 não conectado — comando $mode ignorado (captureId=$captureIdRaw)")
            return false
        }
        val source = phoneSource ?: run {
            log("Câmera não pronta para comando $mode")
            return false
        }
        val captureId = captureIdRaw ?: "cap-${UUID.randomUUID().toString().take(8)}-${mode.name.lowercase()}"
        val n = frames.coerceIn(1, 10)
        val gap = gapMs.coerceIn(0, 5000)
        var allOk = true
        repeat(n) { idx ->
            try {
                val st = _uiState.value.sessionType
                val captured = source.capture(mode, sessionId, captureId, idx)
                val pending = source.toPendingFrame(captured, sessionId, st)
                // S04.4: Result.failure tratado efetivamente.
                val saveRes = spoolRepository.save(pending)
                if (saveRes.isFailure) {
                    allOk = false
                    log("Spool save FALHOU frame $idx: ${saveRes.exceptionOrNull()?.message} — sem captura duplicada")
                } else {
                    log("${ts()} srv frame $idx/$n sha=${captured.sha256.take(12)}... ${captured.resolution}")
                    // S04.6: contador = enfileirados (ACKs chegam via UploadWorker); nunca
                    // chama captura concluída antes das confirmações (ver abaixo).
                    _uiState.update { it.copy(pageCount = it.pageCount + 1, lastFrameLabel = "Última: $captureId idx $idx ✓") }
                }
                if (idx < n - 1) delay(gap)
            } catch (e: Exception) {
                allOk = false
                log("Falha captura srv frame $idx: ${e.message}")
            }
        }
        try {
            val st = _uiState.value.sessionType
            // S04.6: só confirma conclusão quando todos os frames foram persistidos.
            if (!allOk) {
                log("capture-complete ADIADO: nem todos os frames persistidos p/ $captureId")
                return false
            }
            val cc = if (st == "HANDWRITTEN_WORD") sessionRepository.captureCompleteHandwritten(sessionId, captureId, n) else sessionRepository.captureComplete(sessionId, captureId, n)
            if (cc.isFailure) {
                log("captureComplete falhou: ${cc.exceptionOrNull()?.message} — pendência preservada")
                return false
            }
        } catch (e: Exception) {
            Log.w(TAG, "captureComplete falhou", e)
            return false
        }
        return true
    }

    private fun startHeartbeat(sessionId: String) {
        stopHeartbeat()
        heartbeatJob = viewModelScope.launch {
            while (isActive) {
                delay(20_000)
                sessionRepository.heartbeat(sessionId, cursor = _uiState.value.cursor)
            }
        }
    }

    private fun stopPolling() {
        pollJob?.cancel()
        pollJob = null
        _uiState.update { it.copy(isPolling = false) }
    }

    private fun stopHeartbeat() {
        heartbeatJob?.cancel()
        heartbeatJob = null
    }

    private fun startRgbTestPolling(sessionId: String) {
        stopRgbTestPolling()
        rgbTestJob = viewModelScope.launch {
            var afterId = 0
            while (isActive) {
                val result = sessionRepository.fetchRgbTest(sessionId, afterId)
                val command = result.getOrNull()
                if (command != null && command.rgb.size == 3) {
                    afterId = command.commandId
                    val item = RgbTestUi(
                        commandId = command.commandId,
                        red = command.rgb[0].coerceIn(0, 255),
                        green = command.rgb[1].coerceIn(0, 255),
                        blue = command.rgb[2].coerceIn(0, 255),
                        brightnessPercent = command.brightnessPercent.coerceIn(0, 100),
                        onMs = command.onMs,
                        offMs = command.offMs,
                        active = true,
                        status = "RECEIVED",
                    )
                    _uiState.update { it.copy(rgbTest = item) }
                    log("RGB TEST #${item.commandId}: ${item.red},${item.green},${item.blue} brilho=${item.brightnessPercent}% on=${item.onMs}ms")
                    delay(item.onMs)
                    _uiState.update { state -> state.copy(rgbTest = item.copy(active = false, status = "OFF")) }
                    delay(item.offMs)
                    _uiState.update { state -> state.copy(rgbTest = null) }
                } else {
                    delay(1000)
                }
            }
        }
    }

    private fun stopRgbTestPolling() {
        rgbTestJob?.cancel()
        rgbTestJob = null
        _uiState.update { it.copy(rgbTest = null) }
    }

    private suspend fun awaitSpoolDrain(sessionId: String, timeoutMs: Long = 30_000): Boolean {
        val start = System.currentTimeMillis()
        while (System.currentTimeMillis() - start < timeoutMs) {
            val pending = spoolRepository.pendingCountForSession(sessionId)
            if (pending == 0) {
                log("Spool drain completo")
                return true
            }
            delay(1000)
        }
        log("Spool drain timeout — fechamento pendente, SEM fechar com pendências")
        return false
    }

    private fun log(msg: String) {
        val line = "${ts()} $msg"
        Log.i(TAG, line)
        _uiState.update { it.copy(logs = (it.logs + line).takeLast(100)) }
    }

    private fun ts(): String = timeFmt.format(Date())

    // ── Rede: reenqueue após corte (Etapa 4) ───────────────────────────────
    private fun registerNetworkCallback() {
        try {
            val cm = app.getSystemService(ConnectivityManager::class.java) ?: return
            val request = NetworkRequest.Builder()
                .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                .build()
            val callback = object : ConnectivityManager.NetworkCallback() {
                override fun onAvailable(network: Network) {
                    viewModelScope.launch {
                        try {
                            val n = spoolRepository.reenqueueAllPending()
                            if (n > 0) {
                                Log.i(TAG, "network onAvailable → reenqueueAllPending: $n frames")
                                log("Rede restabelecida — re-enfileirados $n frames")
                            }
                        } catch (e: Exception) {
                            Log.w(TAG, "reenqueue após rede falhou", e)
                        }
                    }
                }
                override fun onLost(network: Network) {
                    Log.i(TAG, "network onLost — spool continuará enfileirado para retry")
                }
            }
            networkCallback = callback
            cm.registerNetworkCallback(request, callback)
            Log.d(TAG, "NetworkCallback registrado para reenqueue após corte")
        } catch (e: Exception) {
            Log.w(TAG, "falha ao registrar NetworkCallback", e)
        }
    }

    private fun unregisterNetworkCallback() {
        try {
            val cm = app.getSystemService(ConnectivityManager::class.java)
            networkCallback?.let { cm?.unregisterNetworkCallback(it) }
        } catch (e: Exception) {
            Log.w(TAG, "falha ao desregistrar NetworkCallback", e)
        } finally {
            networkCallback = null
        }
    }

    override fun onCleared() {
        super.onCleared()
        stopPolling()
        stopHeartbeat()
        stopRgbTestPolling()
        unbindCamera()
        unregisterNetworkCallback()
    }
}

class SessionViewModelFactory(private val app: GatewayApplication) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        if (modelClass.isAssignableFrom(SessionViewModel::class.java)) {
            return SessionViewModel(app) as T
        }
        throw IllegalArgumentException("Unknown ViewModel class")
    }
}
