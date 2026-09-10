package com.pagestoaudio.gateway.diag

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * D02/D04 — estado de teste no app + botão local de parada.
 *
 * Mostra diagnóstico ativo/modo/prazo e permite parar localmente.
 * Heartbeat de controle a cada 10 s enquanto a tela estiver visível;
 * sem ele, o servidor expira a autorização em 30 s (segurança independe
 * do navegador). Recupera pendências duráveis sem reiniciar câmera.
 */
data class DiagUiState(
    val enabled: Boolean = DiagConfig.diagnosticsEnabled,
    val active: Boolean = false,
    val diagnosticId: String? = null,
    val mode: String? = null,
    val deviceId: String? = null,
    val secondsLeft: Long = 0L,
    val lastResult: String? = null,
)

class DiagViewModel(
    private val forwarder: CameraDiagnosticsForwarder,
) : ViewModel() {
    private val _ui = MutableStateFlow(DiagUiState())
    val ui: StateFlow<DiagUiState> = _ui.asStateFlow()
    private var tickJob: Job? = null

    fun setEnabled(enabled: Boolean) {
        DiagConfig.diagnosticsEnabled = enabled
        _ui.update { it.copy(enabled = enabled) }
    }

    fun onRemoteStart(req: DiagRequest) {
        viewModelScope.launch {
            val ok = forwarder.start(req)
            _ui.update {
                it.copy(active = ok, diagnosticId = req.diagnosticId,
                    mode = req.mode.name, deviceId = req.deviceId,
                    lastResult = if (ok) "teste iniciado" else "teste recusado (ocupado/flag)")
            }
            if (ok) startTick(req)
        }
    }

    fun stopLocal() {
        viewModelScope.launch {
            val id = _ui.value.diagnosticId ?: return@launch
            val ok = forwarder.stop("local-stop")
            tickJob?.cancel()
            _ui.update { it.copy(active = false, lastResult = if (ok) "parado" else "parada solicitada") }
        }
    }

    private fun startTick(req: DiagRequest) {
        tickJob?.cancel()
        tickJob = viewModelScope.launch {
            while (isActive) {
                val left = ((req.deadlineMs - System.currentTimeMillis()) / 1000L).coerceAtLeast(0L)
                _ui.update { it.copy(secondsLeft = left, active = forwarder.isActive(req.diagnosticId)) }
                // Heartbeat de controle a cada 10 s (tela visível).
                try { forwarder.heartbeat(req.diagnosticId) } catch (_: Exception) {}
                if (left <= 0L) {
                    _ui.update { it.copy(active = false, lastResult = "prazo local encerrado") }
                    break
                }
                delay(10_000L)
            }
        }
    }
}
