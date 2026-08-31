package com.pagestoaudio.gateway.ui

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.util.Log
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.pagestoaudio.gateway.GatewayApplication
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    companion object {
        private const val TAG = "MainActivity"
    }

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            Log.i(TAG, "Permissão CAMERA concedida")
            // Recompor SessionScreen — Preview será vinculado
            recreate()
        } else {
            Log.w(TAG, "Permissão CAMERA negada")
            Toast.makeText(this, "Permissão de câmera é necessária para capturar páginas", Toast.LENGTH_LONG).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val app = application as GatewayApplication
        // Ao reabrir, re-enfileira pendentes não-ACK
        lifecycleScope.launch {
            try {
                val count = app.spoolRepository.reenqueueAllPending()
                if (count > 0) Log.i(TAG, "Re-enfileirados $count frames pendentes ao abrir o app")
            } catch (e: Exception) {
                Log.w(TAG, "reenqueueAllPending falhou", e)
            }
        }

        if (!hasCameraPermission()) {
            requestPermissionLauncher.launch(Manifest.permission.CAMERA)
        }

        setContent {
            MaterialTheme {
                Surface {
                    SessionScreen(
                        hasCameraPermission = hasCameraPermission(),
                        onRequestPermission = { requestPermissionLauncher.launch(Manifest.permission.CAMERA) }
                    )
                }
            }
        }
    }

    private fun hasCameraPermission(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
}
