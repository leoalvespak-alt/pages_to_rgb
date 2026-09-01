package com.pagestoaudio.gateway.ui

import android.util.Log
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Divider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.viewmodel.compose.viewModel
import com.pagestoaudio.gateway.GatewayApplication
import com.pagestoaudio.gateway.camera.CaptureMode

/**
 * Tela principal — PLANO_ANDROID_ONLY.md §2.2
 *
 * ```
 * [TopBar]  Sessão: S-abc123  •  Conectado ●  |  [Android █] [ESP32 ]
 * [Preview]  (CameraX PreviewView — só quando session CAPTURING)
 * [Linha 1]  Páginas: 12  |  Fila: 2 pendentes  |  Última: cap-017 idx 2 ✓
 * [Linha 2]  Estado servidor: CAPTURE_FULL (cursor 118)
 * [Ações]   [ Iniciar sessão ]  [ Encerrar ]  (Encerrar → POST /end-signal)
 * [Log]     14:02:11 frame 0 sha=abc... ACK
 * ```
 *
 * Seletor Câmera do celular / ESP32 → troca CaptureSource.
 * App precisa estar em foreground durante captura (restrição oficial).
 */
@Composable
fun SessionScreen(
    hasCameraPermission: Boolean,
    onRequestPermission: () -> Unit,
    viewModel: SessionViewModel = viewModel(
        factory = SessionViewModelFactory(
            (LocalContext.current.applicationContext as GatewayApplication)
        )
    )
) {
    val uiState by viewModel.uiState.collectAsState()
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current

    // Vincular câmera quando sessão está CAPTURING e permissão concedida
    LaunchedEffect(uiState.sessionId, uiState.isCapturing, hasCameraPermission) {
        if (hasCameraPermission && uiState.isCapturing) {
            Log.i("SessionScreen", "Solicitando bind da câmera hasPerm=$hasCameraPermission capturing=${uiState.isCapturing}")
            viewModel.bindCamera(lifecycleOwner)
        } else if (!uiState.isCapturing) {
            viewModel.unbindCamera()
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        // ── TopBar ────────────────────────────────────────────────────────
        TopBar(
            sessionId = uiState.sessionId,
            isConnected = uiState.isConnected,
            captureSource = uiState.captureSourceLabel,
            onSelectSource = { viewModel.selectCaptureSource(it) }
        )

        Divider()

        uiState.rgbTest?.let { test ->
            val scale = test.brightnessPercent / 100f
            val displayColor = if (test.active) Color(
                red = (test.red * scale).toInt(),
                green = (test.green * scale).toInt(),
                blue = (test.blue * scale).toInt()
            ) else Color.Black
            Card(
                modifier = Modifier.fillMaxWidth().height(180.dp),
                colors = CardDefaults.cardColors(containerColor = displayColor)
            ) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(
                        "TESTE RGB #${test.commandId}\n${test.red}, ${test.green}, ${test.blue} • ${test.brightnessPercent}%\nON ${test.onMs} ms • OFF ${test.offMs} ms",
                        color = if (test.active && scale > .55f) Color.Black else Color.White,
                        style = MaterialTheme.typography.titleMedium
                    )
                }
            }
        }

        // ── Preview (só quando CAPTURING e permissão ok) ─────────────────
        if (hasCameraPermission && uiState.isCapturing) {
            CameraPreview(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(260.dp),
                onPreviewViewReady = { previewView -> viewModel.attachPreviewView(previewView) }
            )
        } else if (!hasCameraPermission) {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(160.dp),
                colors = CardDefaults.cardColors(containerColor = Color(0xFFFFEBEE))
            ) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("Permissão de câmera necessária", color = Color(0xFFC62828))
                        Spacer(modifier = Modifier.height(8.dp))
                        Button(onClick = onRequestPermission) { Text("Conceder permissão") }
                    }
                }
            }
        } else {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(160.dp),
                colors = CardDefaults.cardColors(containerColor = Color(0xFFECEFF1))
            ) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("Preview aparecerá quando a sessão estiver em CAPTURING", color = Color.Gray)
                }
            }
        }

        // ── Linha 1: contadores ───────────────────────────────────────────
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text("Páginas: ${uiState.pageCount}", style = MaterialTheme.typography.bodyMedium)
            Text("Fila: ${uiState.pendingCount} pendentes", style = MaterialTheme.typography.bodyMedium)
            Text(
                text = uiState.lastFrameLabel ?: "Última: —",
                style = MaterialTheme.typography.bodyMedium,
                color = if (uiState.lastFrameAck) Color(0xFF2E7D32) else Color(0xFFF57F17)
            )
        }

        // ── Linha 2: estado servidor ──────────────────────────────────────
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                "Estado servidor: ${uiState.serverCommand} (cursor ${uiState.cursor})",
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.weight(1f)
            )
            if (uiState.isPolling) {
                CircularProgressIndicator(modifier = Modifier.width(16.dp).height(16.dp), strokeWidth = 2.dp)
            }
        }

        Divider()

        // ── Seletor modo EXAM / HANDWRITTEN_WORD (isolado, não toca EXAM) ──
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("Modo:", style = MaterialTheme.typography.labelLarge)
            OutlinedButton(
                onClick = { viewModel.selectSessionType("EXAM") },
                enabled = uiState.sessionId == null,
                modifier = Modifier.weight(1f)
            ) {
                Text(if (uiState.sessionType == "EXAM") "● Prova EXAM" else "Prova EXAM")
            }
            OutlinedButton(
                onClick = { viewModel.selectSessionType("HANDWRITTEN_WORD") },
                enabled = uiState.sessionId == null,
                modifier = Modifier.weight(1f)
            ) {
                Text(if (uiState.sessionType == "HANDWRITTEN_WORD") "● Teste Manuscrito" else "Teste Manuscrito")
            }
        }
        if (uiState.sessionType == "HANDWRITTEN_WORD") {
            Text(
                "Quantidade, palavras e cores definidas no painel Admin",
                color = Color(0xFF1565C0),
                style = MaterialTheme.typography.bodySmall
            )
        }

        // ── Ações ─────────────────────────────────────────────────────────
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Button(
                onClick = { viewModel.startSession() },
                enabled = !uiState.isStartingSession && uiState.sessionId == null,
                modifier = Modifier.weight(1f)
            ) {
                if (uiState.isStartingSession) {
                    CircularProgressIndicator(modifier = Modifier.width(16.dp).height(16.dp), strokeWidth = 2.dp)
                    Spacer(modifier = Modifier.width(8.dp))
                }
                Text(if (uiState.sessionType == "HANDWRITTEN_WORD") "Iniciar teste" else "Iniciar sessão")
            }

            // Botão manual para modo teste sem servidor (fallback do plano §5)
            OutlinedButton(
                onClick = { viewModel.captureManual(CaptureMode.FULL) },
                enabled = uiState.sessionId != null && uiState.captureSourceLabel == "Android",
                modifier = Modifier.weight(1f)
            ) {
                Text("Capturar página")
            }

            Button(
                onClick = { viewModel.endSession() },
                enabled = uiState.sessionId != null && !uiState.isEndingSession,
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFC62828)),
                modifier = Modifier.weight(1f)
            ) {
                Text("Encerrar")
            }
        }

        // Seletor de fonte — ESP32 fica desabilitado com aviso aguardando hardware
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("Fonte:", style = MaterialTheme.typography.labelLarge)
            OutlinedButton(
                onClick = { viewModel.selectCaptureSource("Android") },
                enabled = true,
                modifier = Modifier.weight(1f)
            ) {
                Text(if (uiState.captureSourceLabel == "Android") "● Android" else "Android")
            }
            OutlinedButton(
                onClick = { viewModel.selectCaptureSource("ESP32") },
                enabled = uiState.sessionType != "HANDWRITTEN_WORD",
                modifier = Modifier.weight(1f)
            ) {
                Text(if (uiState.captureSourceLabel == "ESP32") "● ESP32" else "ESP32 (aguard. HW)")
            }
        }
        if (uiState.captureSourceLabel == "ESP32") {
            Text(
                "ESP32 não conectado — selecione \"Android\" para capturar. (ports 8786/8787)",
                color = Color(0xFFE65100),
                style = MaterialTheme.typography.bodySmall
            )
        }

        if (uiState.errorMessage != null) {
            Card(colors = CardDefaults.cardColors(containerColor = Color(0xFFFFEBEE)), modifier = Modifier.fillMaxWidth()) {
                Text(
                    uiState.errorMessage!!,
                    color = Color(0xFFC62828),
                    modifier = Modifier.padding(8.dp),
                    style = MaterialTheme.typography.bodySmall
                )
            }
        }

        // ── Log ───────────────────────────────────────────────────────────
        Text("Log:", style = MaterialTheme.typography.labelLarge)
        LazyColumn(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f)
                .background(Color(0xFFFAFAFA))
                .padding(6.dp),
            verticalArrangement = Arrangement.spacedBy(2.dp)
        ) {
            items(uiState.logs) { line ->
                Text(line, style = MaterialTheme.typography.bodySmall, color = Color(0xFF37474F))
            }
        }
    }
}

@Composable
private fun TopBar(
    sessionId: String?,
    isConnected: Boolean,
    captureSource: String,
    onSelectSource: (String) -> Unit
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = if (sessionId != null) "Sessão: $sessionId" else "Sessão: —",
            style = MaterialTheme.typography.titleSmall
        )
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                modifier = Modifier
                    .width(8.dp)
                    .height(8.dp)
                    .background(if (isConnected) Color(0xFF2E7D32) else Color(0xFFBDBDBD), shape = MaterialTheme.shapes.small)
            )
            Spacer(modifier = Modifier.width(4.dp))
            Text(if (isConnected) "Conectado" else "Desconectado", style = MaterialTheme.typography.bodySmall)
            Spacer(modifier = Modifier.width(12.dp))
            Text(
                if (captureSource == "Android") "[Android █]" else "[ESP32 █]",
                style = MaterialTheme.typography.labelSmall,
                color = Color(0xFF1565C0)
            )
        }
    }
}

@Composable
private fun CameraPreview(
    modifier: Modifier = Modifier,
    onPreviewViewReady: (PreviewView) -> Unit
) {
    val context = LocalContext.current
    val previewView = remember { PreviewView(context).apply { scaleType = PreviewView.ScaleType.FILL_CENTER } }

    DisposableEffect(previewView) {
        onPreviewViewReady(previewView)
        onDispose { }
    }

    AndroidView(
        factory = { previewView },
        modifier = modifier.background(Color.Black)
    )
}
