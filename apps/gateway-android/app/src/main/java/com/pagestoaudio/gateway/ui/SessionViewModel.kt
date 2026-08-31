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
    val logs: List<String> = emptyList(),
    val errorMessage: String? = null
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
        val spoolDir = File(app.filesDir, "spool")
        val source = PhoneCameraCaptureSource(app, owner, spoolDir, view)
        phoneSource = source
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

    fun selectCaptureSource(label: String) {
        // HANDWRITTEN_WORD só permite Android
        if (_uiState.value.sessionType == "HANDWRITTEN_WORD" && label == "ESP32") {
            _uiState.update { it.copy(errorMessage = "Teste manuscrito só em Android") }
            return
        }
        _uiState.update { it.copy(captureSourceLabel = label, errorMessage = if (label == "ESP32") "ESP32 não conectado — aguardando hardware (ports 8786/8787)" else null) }
        log("Fonte selecionada: $label")
        if (label == "ESP32") {
            unbindCamera()
            _uiState.update { it.copy(isCapturing = false) }
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
            log("Iniciando sessão $st …")
            val result = if (st == "HANDWRITTEN_WORD") sessionRepository.startHandwrittenSession(10) else sessionRepository.startSession(allowNewSession = true)
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
                            pageCount = 0
                        )
                    }
                    log("Sessão iniciada: ${s.sessionId} resumed=${s.resumed}")
                    // Bind câmera agora que temos sessão
                    lifecycleOwner?.let { bindCamera(it) }
                    startPolling(s.sessionId, s.cursor)
                    startHeartbeat(s.sessionId)
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
            log("Encerrando sessão $sid — aguardando spool drain…")
            awaitSpoolDrain(sid)
            val st = _uiState.value.sessionType
            val res = if (st == "HANDWRITTEN_WORD") sessionRepository.endHandwrittenSignal(sid) else sessionRepository.endSignal(sid)
            if (res.isSuccess) {
                log("Sessão encerrada: $sid → LOCKED")
                _uiState.update { it.copy(isCapturing = false, isConnected = false, isEndingSession = false, serverCommand = "STOP") }
                stopPolling()
                stopHeartbeat()
                unbindCamera()
            } else {
                val msg = res.exceptionOrNull()?.message ?: "erro desconhecido"
                _uiState.update { it.copy(isEndingSession = false, errorMessage = msg) }
                log("Falha ao encerrar: $msg")
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
                        val st2 = _uiState.value.sessionType
                        if (st2 == "HANDWRITTEN_WORD") sessionRepository.captureCompleteHandwritten(sid, captureId, frames) else sessionRepository.captureComplete(sid, captureId, frames)
                        log("capture-complete enviado: $captureId type=$st2")
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
            var cursor = initialCursor
            _uiState.update { it.copy(isPolling = true) }
            while (isActive) {
                try {
                    val st = _uiState.value.sessionType
                    val res = if (st == "HANDWRITTEN_WORD") sessionRepository.fetchHandwrittenCommand(sessionId, cursor, waitMs = 25000, phase = "CAPTURE") else sessionRepository.fetchCommand(sessionId, cursor, waitMs = 25000, phase = "CAPTURE")
                    if (res.isSuccess) {
                        val cmd = res.getOrNull()!!
                        cursor = cmd.cursor
                        _uiState.update { it.copy(cursor = cursor, serverCommand = cmd.command) }
                        log("CMD ${cmd.command} cursor=$cursor cap=${cmd.captureId} frames=${cmd.frames}")

                        when (cmd.command) {
                            "CAPTURE_PROBE" -> handleServerCapture(cmd.captureId, CaptureMode.PROBE, cmd.frames, cmd.gapMs, sessionId)
                            "CAPTURE_FULL" -> handleServerCapture(cmd.captureId, CaptureMode.FULL, cmd.frames, cmd.gapMs, sessionId)
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
                                awaitSpoolDrain(sessionId)
                                val st2 = _uiState.value.sessionType
                                if (st2 == "HANDWRITTEN_WORD") sessionRepository.endHandwrittenSignal(sessionId) else sessionRepository.endSignal(sessionId)
                                _uiState.update { it.copy(isCapturing = false, serverCommand = "STOP") }
                                unbindCamera()
                                stopPolling()
                                break
                            }
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

    private suspend fun handleServerCapture(
        captureIdRaw: String?,
        mode: CaptureMode,
        frames: Int,
        gapMs: Long,
        sessionId: String
    ) {
        if (_uiState.value.captureSourceLabel == "ESP32") {
            log("ESP32 não conectado — comando $mode ignorado (captureId=$captureIdRaw)")
            return
        }
        val source = phoneSource ?: run {
            log("Câmera não pronta para comando $mode")
            return
        }
        val captureId = captureIdRaw ?: "cap-${UUID.randomUUID().toString().take(8)}-${mode.name.lowercase()}"
        val n = frames.coerceIn(1, 10)
        val gap = gapMs.coerceIn(0, 5000)
        repeat(n) { idx ->
            try {
                val st = _uiState.value.sessionType
                val captured = source.capture(mode, sessionId, captureId, idx)
                val pending = source.toPendingFrame(captured, sessionId, st)
                spoolRepository.save(pending)
                log("${ts()} srv frame $idx/$n sha=${captured.sha256.take(12)}... ${captured.resolution}")
                _uiState.update { it.copy(pageCount = it.pageCount + 1, lastFrameLabel = "Última: $captureId idx $idx ✓") }
                if (idx < n - 1) delay(gap)
            } catch (e: Exception) {
                log("Falha captura srv frame $idx: ${e.message}")
            }
        }
        try {
            val st = _uiState.value.sessionType
            if (st == "HANDWRITTEN_WORD") sessionRepository.captureCompleteHandwritten(sessionId, captureId, n) else sessionRepository.captureComplete(sessionId, captureId, n)
        } catch (e: Exception) {
            Log.w(TAG, "captureComplete falhou", e)
        }
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

    private suspend fun awaitSpoolDrain(sessionId: String, timeoutMs: Long = 30_000) {
        val start = System.currentTimeMillis()
        while (System.currentTimeMillis() - start < timeoutMs) {
            val pending = spoolRepository.pendingCountForSession(sessionId)
            if (pending == 0) {
                log("Spool drain completo")
                return
            }
            delay(1000)
        }
        log("Spool drain timeout — prosseguindo")
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
