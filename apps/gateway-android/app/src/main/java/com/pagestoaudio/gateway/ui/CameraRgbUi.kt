package com.pagestoaudio.gateway.ui

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTag
import androidx.compose.ui.unit.dp

/** UI-only state for camera controls. Values are requested until a session snapshot confirms effective values. */
data class CameraUiState(
    val mode: String = "OCR",
    val requestedResolution: String = "UXGA",
    val requestedJpegQuality: Int = 12,
    val brightness: Int = 0,
    val contrast: Int = 0,
    val saturation: Int = 0,
    val awb: Boolean = true,
    val awbGain: Boolean = true,
    val aec: Boolean = true,
    val agc: Boolean = true,
    val bpc: Boolean = false,
    val wpc: Boolean = false,
    val rawGamma: Boolean = false,
    val lensCorrection: Boolean = true,
    val dcw: Boolean = true,
    val hmirror: Boolean = false,
    val vflip: Boolean = false,
    val colorbar: Boolean = false,
    val advancedExpanded: Boolean = false,
    val capabilityStatus: String = "OFFLINE",
    val capabilityMessage: String = "Sem conexão com o Gateway; controles aguardam capabilities.",
    val unavailable: Map<String, String> = emptyMap(),
    val effectiveResolution: String? = null,
    val effectiveJpegQuality: Int? = null,
    val firmwareVersion: String? = null,
    val capabilitiesVersion: String? = null,
)

private val resolutionOptions = listOf("QVGA", "VGA", "SVGA", "XGA", "SXGA", "UXGA")

@Composable
fun CameraSettingsPanel(
    state: CameraUiState,
    onModeChange: (String) -> Unit,
    onResolutionChange: (String) -> Unit,
    onJpegQualityChange: (Int) -> Unit,
    onBrightnessChange: (Int) -> Unit,
    onContrastChange: (Int) -> Unit,
    onSaturationChange: (Int) -> Unit,
    onToggle: (String, Boolean) -> Unit,
    onToggleAdvanced: () -> Unit,
    onRefreshCapabilities: () -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Row(modifier = Modifier.fillMaxWidth()) {
                Text("Câmera", style = MaterialTheme.typography.titleMedium)
                Spacer(modifier = Modifier.weight(1f))
                Text(state.capabilityStatus, style = MaterialTheme.typography.labelMedium)
            }
            Text(state.capabilityMessage, style = MaterialTheme.typography.bodySmall)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { onModeChange("OCR") }) {
                    Text(if (state.mode == "OCR") "● OCR" else "OCR")
                }
                OutlinedButton(onClick = { onModeChange("PHOTO") }) {
                    Text(if (state.mode == "PHOTO") "● Foto" else "Foto")
                }
                Button(onClick = onRefreshCapabilities) { Text("Atualizar") }
            }

            Text("Resolução solicitada: ${state.requestedResolution}", style = MaterialTheme.typography.labelLarge)
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                resolutionOptions.forEach { option ->
                    OutlinedButton(onClick = { onResolutionChange(option) }) { Text(option) }
                }
            }

            Text("JPEG Android solicitado: ${state.requestedJpegQuality}", style = MaterialTheme.typography.labelLarge)
            Slider(
                value = state.requestedJpegQuality.toFloat(),
                onValueChange = { onJpegQualityChange(it.toInt().coerceIn(8, 12)) },
                valueRange = 8f..12f,
                steps = 3,
                modifier = Modifier.semantics { testTag = "camera-jpeg-quality" },
            )

            Text("Ajustes básicos", style = MaterialTheme.typography.labelLarge)
            TuningSlider("Brilho", state.brightness, onBrightnessChange, "camera-brightness")
            TuningSlider("Contraste", state.contrast, onContrastChange, "camera-contrast")
            TuningSlider("Saturação", state.saturation, onSaturationChange, "camera-saturation")
            ToggleRow("AWB", "awb", state.awb, onToggle)
            ToggleRow("AEC", "aec", state.aec, onToggle)
            ToggleRow("AGC", "agc", state.agc, onToggle)

            Text(
                "Solicitado: ${state.requestedResolution} / JPEG ${state.requestedJpegQuality}",
                style = MaterialTheme.typography.bodySmall,
            )
            Text(
                "Efetivo: ${state.effectiveResolution ?: "aguardando sessão"} / JPEG ${state.effectiveJpegQuality ?: "—"}",
                style = MaterialTheme.typography.bodySmall,
            )
            Text(
                "Firmware: ${state.firmwareVersion ?: "—"} · Capabilities: ${state.capabilitiesVersion ?: "—"}",
                style = MaterialTheme.typography.bodySmall,
            )

            OutlinedButton(onClick = onToggleAdvanced, modifier = Modifier.fillMaxWidth()) {
                Text(if (state.advancedExpanded) "Ocultar área técnica" else "Mostrar área técnica")
            }
            if (state.advancedExpanded) {
                Text("Área técnica protegida (somente leitura)", style = MaterialTheme.typography.labelLarge)
                Text("XCLK 10 MHz · buffer 655.360 · fb_count 1 · PSRAM · DMA", style = MaterialTheme.typography.bodySmall)
                Text("Flash branco: bloqueado", style = MaterialTheme.typography.bodySmall)
                ToggleRow("BPC", "bpc", state.bpc, onToggle, state.unavailable)
                ToggleRow("WPC", "wpc", state.wpc, onToggle, state.unavailable)
                ToggleRow("Raw Gamma", "raw_gamma", state.rawGamma, onToggle, state.unavailable)
                ToggleRow("Lens Correction", "lens_correction", state.lensCorrection, onToggle, state.unavailable)
                ToggleRow("DCW", "dcw", state.dcw, onToggle, state.unavailable)
                ToggleRow("Hmirror", "hmirror", state.hmirror, onToggle, state.unavailable)
                ToggleRow("Vflip", "vflip", state.vflip, onToggle, state.unavailable)
                ToggleRow("Colorbar (avançado)", "colorbar", state.colorbar, onToggle, state.unavailable)
                state.unavailable.forEach { (control, reason) ->
                    Text("$control indisponível: $reason", color = Color(0xFFE65100), style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

@Composable
private fun TuningSlider(label: String, value: Int, onChange: (Int) -> Unit, tag: String) {
    Text("$label: $value", style = MaterialTheme.typography.bodySmall)
    Slider(
        value = value.toFloat(),
        onValueChange = { onChange(it.toInt().coerceIn(-2, 2)) },
        valueRange = -2f..2f,
        steps = 3,
        modifier = Modifier.semantics { testTag = tag },
    )
}

@Composable
private fun ToggleRow(
    label: String,
    key: String,
    checked: Boolean,
    onToggle: (String, Boolean) -> Unit,
    unavailable: Map<String, String> = emptyMap(),
) {
    val enabled = !unavailable.containsKey(key)
    Row(modifier = Modifier.fillMaxWidth()) {
        Text(label, modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
        Checkbox(
            checked = checked,
            onCheckedChange = if (enabled) ({ value -> onToggle(key, value) }) else null,
            enabled = enabled,
            modifier = Modifier.semantics { testTag = "camera-$key" },
        )
    }
}

@Composable
fun RgbPhysicalPanel(
    isConnected: Boolean,
    test: RgbTestUi?,
    onStop: () -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(modifier = Modifier.fillMaxWidth()) {
                Text("RGB físico · prévia", style = MaterialTheme.typography.titleMedium)
                Spacer(modifier = Modifier.weight(1f))
                Text(if (isConnected) "ONLINE" else "OFFLINE", style = MaterialTheme.typography.labelMedium)
            }
            if (test == null) {
                Text("Nenhum comando RGB recebido.", style = MaterialTheme.typography.bodySmall)
            } else {
                val scale = test.brightnessPercent / 100f
                val preview = Color(test.red / 255f * scale, test.green / 255f * scale, test.blue / 255f * scale)
                Card(colors = CardDefaults.cardColors(containerColor = if (test.active) preview else Color.Black)) {
                    Column(modifier = Modifier.padding(10.dp)) {
                        Text("Prévia #${test.commandId}: RGB ${test.red},${test.green},${test.blue}")
                        Text("Brilho ${test.brightnessPercent}% · ON ${test.onMs} ms · OFF ${test.offMs} ms")
                        Text("Estado: ${test.status}")
                    }
                }
                when (test.status) {
                    "APPLIED" -> Text("Aplicado pela ESP; confirmação física recebida.", color = Color(0xFF2E7D32))
                    "OFF" -> Text("Desligado confirmado pela ESP.", color = Color(0xFF2E7D32))
                    "TIMEOUT" -> Text("Timeout: sem confirmação física; não simular sucesso.", color = Color(0xFFE65100))
                    "INCOMPATIBLE" -> Text("RGB incompatível: comando não enviado.", color = Color(0xFFC62828))
                    else -> Text("Aguardando APPLIED da ESP; a cor acima é somente prévia.", color = Color(0xFFE65100))
                }
                Button(onClick = onStop, enabled = test.active, modifier = Modifier.fillMaxWidth()) {
                    Text("Parar")
                }
            }
        }
    }
}
