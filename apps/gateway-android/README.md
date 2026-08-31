# Gateway Android — Pages to Audio (modo Câmera do celular)

Projeto Android **Etapas 2 e 3** do `docs/PLANO_ANDROID_ONLY.md` — modo `ANDROID_CAMERA` sem hardware ESP32, compatível com o futuro `ESP32-CAM → Gateway (8786/8787) → servidor`.

## Pacote

`com.pagestoaudio.gateway` — minSdk 26, targetSdk 34, Kotlin 1.9.22, Compose BOM 2024.02.00.

## Estrutura

```
apps/gateway-android/
  build.gradle.kts (root) + settings.gradle.kts
  gradle/wrapper/gradle-wrapper.properties
  gradlew / gradlew.bat
  app/build.gradle.kts
  app/src/main/AndroidManifest.xml  (CAMERA, INTERNET, ACCESS_NETWORK_STATE)
  app/src/main/java/com/pagestoaudio/gateway/
    GatewayApplication.kt
    ui/MainActivity.kt, ui/SessionScreen.kt, ui/SessionViewModel.kt
    camera/CaptureSource.kt                (interface exatamente do plano)
    camera/PhoneCameraCaptureSource.kt     (CameraX determinístico)
    camera/Esp32GatewayCaptureSource.kt    (stub "ESP32 não conectado")
    spool/PendingFrame.kt (Room Entity), SpoolDao.kt, AppDatabase.kt, SpoolRepository.kt
    network/ApiService.kt (Retrofit), GatewayAuthInterceptor.kt
    sync/UploadWorker.kt (WorkManager), sync/CommandPollWorker.kt
    domain/SessionRepository.kt, GatewayConfig.kt
    util/Sha256Util.kt
  app/src/main/res/...
  README.md
```

## Dependências (versões exigidas)

- `androidx.camera:camera-*:1.4.1` (camera-core/camera2/lifecycle/view)
- `androidx.room:room-*:2.6.1` (runtime/ktx, kapt compiler)
- `androidx.work:work-runtime-ktx:2.9.0`
- `com.squareup.retrofit2:retrofit:2.9.0` + `okhttp3:4.12.0` + `converter-gson`
- `org.jetbrains.kotlinx:kotlinx-coroutines:1.7.3`
- `androidx.exifinterface:exifinterface:1.3.7`

Plugins: `kotlin-android`, `kapt`, `parcelize`, Compose (`kotlinCompilerExtensionVersion 1.5.8`).

## Contrato lógico

- Servidor enxerga `ANDROID_CAMERA` e `ESP32_CAMERA` como mesmo tipo lógico; muda só `capture_source`.
- Interface `CaptureSource` exatamente como no plano:

  ```kotlin
  interface CaptureSource { suspend fun capture(mode: CaptureMode): CapturedFrame; fun availableResolutions(): List<Size> }
  enum CaptureMode { PROBE, FULL }
  data class CapturedFrame(captureId, frameIndex, sha256, resolution, bytes, createdAt, orientation)
  ```

- `PhoneCameraCaptureSource`:
  1. `ProcessCameraProvider.getInstance`
  2. `Preview` + `ImageCapture(CAPTURE_MODE_MAXIMIZE_QUALITY, JPEG_QUALITY 92 FULL / 75 PROBE)`
  3. `takePicture(OutputFileOptions.Builder(file).build())` → `filesDir/spool/{session_id}/{captureId}_{frameIndex}.jpg`
  4. `onImageSaved`: `ExifInterface` → orientação, `MessageDigest` streaming → SHA-256, `BitmapFactory.Options.inJustDecodeBounds` → width/height, produz `PendingFrame`
  5. `PROBE→75/720p`, `FULL→92/máxima`
  6. `CameraControl.startFocusAndMetering` (AF+AE) antes do disparo
- `Esp32GatewayCaptureSource`: stub que loga `"ESP32 não conectado"` e lança `Esp32NotConnectedException` (erro controlado).

## Spool + Upload idempotente (Etapa 4)

Ordem obrigatória: `capturar → salvar privado → Room insert → SHA → enfileirar → POST → aguardar 2xx → apagar somente após ACK`.

- `PendingFrame` `@Entity(indices=[Index(value=["session_id","capture_id","frame_index"], unique=true)])` com campos `id, session_id, capture_id, frame_index, sha256, filePath, resolution, orientation, createdAt, ack`.
- `SpoolRepository.save()/pending()/markAck()/reenqueueAllPending()` — reenvio com mesmo `session_id+capture_id+frame_index+sha256` → `200` idempotente; mesmo índice com `sha` diferente → `409 CONFLICT`.
- `UploadWorker` com `Constraints(NETWORK_CONNECTED)`, `BackoffPolicy.EXPONENTIAL` (5s), headers `X-Capture-Id, X-Frame-Index, X-SHA256, X-Resolution, X-Received-Android-At, X-Orientation`.

## Tela SessionScreen

- `PreviewView` (CameraX) só quando sessão `CAPTURING`
- Linha 1: `Páginas: 12 | Fila: 2 pendentes | Última: cap-017 idx 2 ✓`
- Linha 2: `Estado servidor: CAPTURE_FULL (cursor 118)`
- Ações: `[Iniciar sessão] [Capturar página] [Encerrar]` — Encerrar → `POST /end-signal`
- Seletor `Android / ESP32` (ESP32 desabilitado com aviso “aguardando hardware”)
- Log: `14:02:11 frame 0 sha=abc... ACK`

O app **precisa estar em foreground** durante captura (restrição oficial — não tentar `ForegroundService` com câmera). WorkManager só para retry de upload.

## Build

### Pré-requisitos

- JDK 17
- Android SDK 34 + Build-Tools 34.0.0
- `ANDROID_HOME` apontando para o SDK (ex: `C:\Android\Sdk` ou `%LOCALAPPDATA%\Android\Sdk`)

### Comandos

```bat
cd apps\gateway-android

REM primeira vez: garantir wrapper jar (se não estiver presente)
gradle wrapper --gradle-version 8.6

REM build debug
.\gradlew assembleDebug

REM instalar em device/emulador (USB debugging ou AVD)
adb install -r app\build\outputs\apk\debug\app-debug.apk

REM ver logs
adb logcat | findstr /R "Spool UploadWorker Gateway PhoneCamera SessionVM"

REM testes unitários (JVM)
.\gradlew test

REM testes instrumentados (device/emulador necessário)
.\gradlew connectedAndroidTest
```

Se não houver Android SDK neste host, o scaffold continua válido para inspeção estática e será compilado no CI com SDK.

### Configuração do servidor

Editar `domain/GatewayConfig.kt` ou `local.properties`:

```properties
gateway.baseUrl=https://SEU_VPS/api/v1/
gateway.deviceId=GW-ANDROID-001
gateway.deviceSecret=...
```

`GatewayAuthInterceptor` envia `X-Device-Id`, `Authorization: Bearer <secret>`, `X-Firmware-Version`.

## Fluxo E2E (sem ESP32)

1. Abrir app → conceder `CAMERA` → `Iniciar sessão` → `POST /gateway/session/start` com `capture_source=ANDROID_CAMERA`.
2. Servidor retorna `session_id` + `cursor`.
3. Polling `GET /gateway/session/{id}/command?cursor=&wait_ms=25000` → `CAPTURE_FULL` / `CAPTURE_PROBE` ou fallback botão “Capturar página”.
4. Captura → `PendingFrame` → `UploadWorker` → `POST /gateway/session/{id}/frame` (JPEG bruto + headers `X-*`).
5. `Encerrar` → `POST /gateway/session/{id}/end-signal` → `LOCKED` → Temporal `ProcessExamWorkflow` → `GET /gateway/session/{id}/result` → `GET /rgb-sequence`.

Para validar sem painel, usar `scripts/simulate_android.py` no servidor.

## Verificação sintática (sem SDK)

```bash
# checagem de sintaxe Kotlin (se kotlinc disponível)
kotlinc -classpath . -d /tmp/check app/src/main/java/com/pagestoaudio/gateway/**/*.kt

# ou apenas listagem de arquivos
find apps/gateway-android -type f | sort
```

## O que NÃO fazer

- Não usar `tools/mock_gateway_v2.py` (só PING).
- Não enviar `jpeg_quality=8` (usar perfis PROBE 75 / FULL 92 e informar `X-Resolution` real).
- Não abrir câmera em WorkManager/background.
- Não armazenar JPEG permanente na VPS (só Supabase Storage + TTL local).

## Referências

- `docs/PLANO_ANDROID_ONLY.md` — plano enxuto E2E
- `docs/ANDROID_GATEWAY_CONTRACT.md` (no repo firmware) — contrato V2.2 (ports 8786/8787, idempotência, STOP→deep sleep 300s)
- `docs/contracts/RGB_RESULT_V1.md` — schema RGB + SHA canônico
