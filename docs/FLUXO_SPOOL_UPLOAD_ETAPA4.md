# Fluxo Spool + Upload Idempotente — Etapa 4 (Android Gateway)

**Versão:** V1 — 31/08/2026  
**Fontes:** `docs/PLANO_ANDROID_ONLY.md:210` Etapa 4, `spool/*`, `sync/UploadWorker.kt`, `src/pages_to_audio/capture/frame_upload.py`, `apps/api/routers/gateway.py`

---

## 1. Ordem obrigatória (mesma do firmware)

```
1. capturar JPEG                        PhoneCameraCaptureSource.capture() → filesDir/spool/{session_id}/{captureId}_{frameIndex}.jpg
2. salvar em armazenamento privado       mkdirs + takePicture(OutputFileOptions)  [privado, sem permissão externa]
3. calcular SHA-256 streaming            Sha256Util.sha256HexStreaming(File)  [8192B buffer, não carrega 2x em RAM]
4. inserir em Room PendingFrame          SpoolRepository.save() → SpoolDao.insert(ABORT) + unique index (session_id, capture_id, frame_index)
5. enfileirar UploadWorker               WorkName "upload-{session}-{capture}-{index}" + ExistingWorkPolicy.KEEP + Constraints(NETWORK_CONNECTED) + Backoff EXPONENTIAL 5s
6. POST /gateway/session/{id}/frame      multipart "file" + headers X-Capture-Id, X-Frame-Index, X-SHA256, X-Resolution, X-Received-Android-At, X-Orientation
7. aguardar 2xx → markAck → apagar SOMENTE após ACK   dao.markAck(id) + file.delete()
```

**Invariante:** arquivo **nunca** apagado antes de `2xx` ou `duplicate=true`. `markAck()` é o único lugar que deleta.

---

## 2. Componentes Android

### 2.1 `PendingFrame.kt:26` — Entity

```kotlin
@Entity(tableName="pending_frames",
  indices=[
    Index(value=["session_id","capture_id","frame_index"], unique=true), // idempotência local
    Index(value=["ack"]), Index(value=["session_id"]), Index(value=["sha256"])
  ])
data class PendingFrame(
  @PrimaryKey id:String, sessionId, captureId, frameIndex:Int,
  sha256:String, filePath:String, resolution:String, orientation:Int,
  createdAt:Long, ack:Boolean=false, attempts:Int=0, width/height:Int
)
```

- `id` é UUID local, não confundir com `frame_db_id` do servidor.
- `unique=true` garante que duas inserções com mesmo `session/capture/index` falham com `ABORT` — SpoolRepository trata idempotente vs conflito.

### 2.2 `SpoolDao.kt:1` — Queries

| Método | SQL | Uso |
|---|---|---|
| `insert(ABORT)` | `@Insert` | save() — falha se violar unique |
| `insertIgnore(IGNORE)` | `@Insert` | alternativa para testes |
| `pending()` | `WHERE ack=0 ORDER BY createdAt ASC` | fila global para reenqueue |
| `pendingForSession(sessionId)` | `WHERE ack=0 AND session_id=:sessionId ORDER BY frame_index ASC` | drain por sessão |
| `pendingForCapture` | `WHERE ack=0 AND session_id=:sessionId AND capture_id=:captureId` | diagnóstico burst |
| `pendingCount / pendingCountForSession` | `COUNT(*)` | badge "Fila: N pendentes" + awaitSpoolDrain |
| `pendingCountFlow / pendingFlow` | `Flow` | UI reativa SessionScreen |
| `findByCaptureFrame` | `WHERE session_id=:sessionId AND capture_id=:captureId AND frame_index=:idx` | save() idempotência local |
| `findByUniqueKey` | `WHERE session_id=:sessionId AND sha256=:sha256 AND capture_id=:captureId AND frame_index=:idx` | validação extra |
| `markAck(id)` | `UPDATE pending_frames SET ack=1 WHERE id=:id` | após 2xx |
| `incrementAttempts(id)` | `UPDATE pending_frames SET attempts=attempts+1` | métrica retry |
| `pruneAcked(before)` | `DELETE WHERE ack=1 AND createdAt < :before` | limpeza 7 dias |
| `acked(limit)` | `SELECT WHERE ack=1 ORDER BY createdAt DESC` | log "Última: cap-..." |

### 2.3 `SpoolRepository.kt:30` — Orquestração

```kotlin
save(frame): Result<PendingFrame>
  1. dao.findByCaptureFrame(...) → se existe com mesmo sha → success(existing) [idempotente local]
                              → se existe com sha diferente → failure("Conflito ... criar novo capture_id")
  2. File(filePath).exists && length>0 || failure
  3. Sha256Util.sha256HexStreaming(file) == frame.sha256 || failure // integridade
  4. dao.insert(frame) // ABORT se race
  5. enqueueUpload(frame) // KEEP
  6. Result.success(frame)

markAck(id): Result<Boolean>
  dao.markAck(id); File(filePath).delete() // somente após ACK

enqueueUpload(frame)
  Data(frame.id, sessionId) + Constraints(NETWORK_CONNECTED) + Backoff EXPONENTIAL 5s
  workName = "upload-${sessionId}-${captureId}-${frameIndex}"
  WorkManager.enqueueUniqueWork(workName, KEEP, request)

reenqueueAllPending(): Int
  dao.pending().forEach { enqueueUpload(it) } // chamado no init ViewModel e onAvailable

reenqueuePendingForSession(sessionId): Int
pruneAckedOlderThan(days=7): Int
```

### 2.4 `UploadWorker.kt:1` — WorkManager

**Constraints:** `NETWORK_CONNECTED`  
**Backoff:** `EXPONENTIAL 5s → 5min` (WorkManager dobra a cada retry, cap 5h mas uso típico 5s,10s,20s...)  
**Headers obrigatórios (ApiService.kt:49):**

```kotlin
@Multipart
@POST("gateway/session/{id}/frame")
suspend fun uploadFrame(
  @Path("id") sessionId: String,
  @Header("X-Capture-Id") captureId: String,
  @Header("X-Frame-Index") frameIndex: Int,
  @Header("X-SHA256") sha256: String,
  @Header("X-Resolution") resolution: String,
  @Header("X-Received-Android-At") receivedAt: String, // Instant.now().toString() ISO-8601
  @Header("X-Orientation") orientation: Int,
  @Part file: MultipartBody.Part // createFormData("file", file.name, body)
): Response<FrameUploadResponse>
```

**Fluxo `doWork():`**

```
1. dao.findById(frameId) ?: success // já ACK/limpo → idempotente
2. if (ack) success
3. File(filePath).exists || failure("file missing") // permanente, não retry
4. computedSha = Sha256Util.sha256HexStreaming(file) catch → retry (I/O transitório)
5. if (computedSha != frame.sha256) → failure("sha mismatch ...") // permanente, não retry, log crítico
6. api.uploadFrame(...) try/catch
   - isSuccessful (2xx) → dao.markAck(id); file.delete(); success // log duplicate/storage_key
   - code==409 → dao.incrementAttempts(); failure("409 conflict ...") // mesmo capture/frame com SHA diferente → requer novo capture_id (não retry)
   - code in 400..499 && code!=408 && code!=429 → dao.incrementAttempts(); failure // cliente não-retriável
   - else (5xx || 408 || 429 || exception) → dao.incrementAttempts(); retry // backoff exponencial
```

**WorkName único:** `SpoolRepository.enqueueUpload()` usa `ExistingWorkPolicy.KEEP` — segunda chamada com mesmo `session/capture/index` não duplica fila.

### 2.5 `SessionViewModel.kt:70` — Ciclo de vida + rede

```kotlin
init {
  pendingCountFlow.collect { _uiState.pendingCount = it } // badge Fila: N pendentes
  viewModelScope.launch { spoolRepository.reenqueueAllPending() } // ao reabrir o app
  registerNetworkCallback() // após corte: onAvailable → reenqueueAllPending()
}
registerNetworkCallback()
  ConnectivityManager.registerNetworkCallback(
    NetworkRequest.Builder().addCapability(NET_CAPABILITY_INTERNET).build(),
    callback { onAvailable → reenqueueAllPending(); onLost → log }
  )
onCleared { unregisterNetworkCallback() }
```

`suspend fun awaitSpoolDrain(sessionId, timeoutMs=30_000)` — usado antes de `POST /end-signal` (Encerrar) e `STOP` do servidor.

---

## 3. Servidor — idempotência

### 3.1 `src/pages_to_audio/capture/frame_upload.py:96`

```python
async def upload_frame(request: FrameUploadRequest, storage, db_session) -> FrameUploadResult:
  _validate_mime(data, mime_type)
  if len(data) > MAX_FRAME_SIZE (10 MiB): raise 413
  actual_sha = sha256(data)
  if actual_sha != declared_sha256: raise FrameConflictError(409) # FRAME_HASH_MISMATCH
  session = select(Session).where(public_id==session_id).with_for_update() # 404 se não existe
  if SessionState(session.status).is_terminal: raise 409 SESSION_LOCKED
  capture = select(Capture).where(session_id==session.id, capture_id==request.capture_id).with_for_update()
            # criar se não existe com capture_source
  existing = select(Frame).where(capture_id==capture.id, frame_index==request.frame_index)
  if existing:
    if existing.sha256 == actual_sha:
       return FrameUploadResult(..., duplicate=True) # 200 idempotente
    else: raise FrameConflictError(409) # FRAME_DUPLICATE_CONFLICT
  dup = select(Frame).where(session_id==session.id, sha256==actual_sha, capture_id==capture.id, frame_index==request.frame_index)
  if dup: return FrameUploadResult(..., duplicate=True) # segunda guarda (session+sha+capture+index)
  storage_key = frame_key(session_id, capture_id, frame_index) # sessions/{id}/frames/{capture}/{idx}.jpg
  await storage.put_object("pages-originals", storage_key, data, mime, sha256=actual_sha, overwrite=False)
  frame = Frame(session_id=..., capture_id=..., frame_index=..., sha256=actual_sha, storage_key=..., capture_source=..., source_resolution=..., android_orientation=..., width/height, received_android_at=parse(received_android_at))
  capture.received_frames +=1
  return FrameUploadResult(frame_db_id=..., storage_key=..., sha256=..., duplicate=False)
```

**Contrato HTTP `apps/api/routers/gateway.py:531` — `POST /gateway/session/{id}/frame`:**

- Headers `X-Frame-Index, X-Capture-Id, X-SHA256, X-Received-Android-At, X-Resolution, X-Orientation` (todos obrigatórios exceto últimos 3)
- `file` multipart `image/jpeg` (valida magic bytes)
- Storage: `SupabaseStorageAdapter` se `SUPABASE_URL+SERVICE_ROLE` setados, senão `FakeStorageAdapter` (tests)
- Mapeia `FrameConflictError → 409`, `NonRetryableError → 4xx` correspondente, `StorageError → 500`
- Retorna `{"session_id","capture_id","frame_index","sha256","storage_key","frame_db_id","duplicate":bool}` — `duplicate=true` quando idempotente.

**Garantias DB (`src/pages_to_audio/db/models/frame.py:27`):**

```sql
UNIQUE(capture_id, frame_index) -- uq_frames_capture_id_frame_index
UNIQUE(session_id, sha256, capture_id, frame_index) -- uq_frames_session_id_sha256_capture_id_frame_index
CHECK(capture_source IN ('ANDROID_CAMERA','ESP32_CAMERA'))
```

Mesma `capture_id+frame_index` com `sha` diferente → `409` (nunca `200`). Reenvio com mesmo `sha` → `200` e `duplicate=true`, não duplica `LogicalPage`.

---

## 4. Checklist de teste manual (Definition of Done Etapa 4)

### 4.1 Pré-requisitos

- [ ] VPS/`docker-compose up` com `DATABASE_URL` + `SUPABASE_URL` ou `FakeStorage` para teste local
- [ ] `uv run alembic upgrade head` passou
- [ ] APK `gateway-android` instalado (USB debugging ou AVD) — `./gradlew assembleDebug` + `adb install -r app/build/outputs/apk/debug/app-debug.apk`
- [ ] `adb logcat | grep -E "Spool|UploadWorker|Gateway|SessionVM"` aberto

### 4.2 Corte de rede (coração da confiabilidade)

| Passo | Ação | Esperado | Log/Query |
|---|---|---|---|
| 1 | Iniciar sessão: `Iniciar sessão` | `201` session_id `S-...`, `CAPTURING` | `SessionVM: Sessão iniciada: S-...` + `gateway.py: session_start` |
| 2 | **Desligar internet** (avião) durante captura | Foto fica em `Fila: 1 pendentes` | `SpoolRepository: save ok ...` + `WorkManager: Constraints not met` |
| 3 | Capturar 2 frames com avião ligado | `Fila: 2 pendentes`, `Última: cap-... idx 1 ✓` | `PhoneCameraCapture: Captured file ok ... sha=...` |
| 4 | Verificar Room | `SELECT COUNT(*) FROM pending_frames WHERE ack=0` == 2 | `adb shell run-as ...` ou `AppDatabase.createInMemory` dump |
| 5 | **Religar internet** | WorkManager dispara, `Fila: 0` | `UploadWorker: Enviando frame ...` + `Upload 2xx ok duplicate=false` + `SessionVM: Rede restabelecida — re-enfileirados 2 frames` |
| 6 | Verificar servidor | `SELECT COUNT(*) FROM frames WHERE session_id=...` == 2, `storage_key` preenchido | `supabase storage ls pages-originals/sessions/S-...` |
| 7 | Reenvio manual do mesmo arquivo (mesmo `capture_id+frame_index+sha256`) via `curl` | `200 duplicate:true`, count não duplica | `frame_idempotent_hit session_id=... sha=...` |
| 8 | Reenvio com `frame_index` igual mas `sha256` diferente (editar 1 byte) | `409 CONFLICT {"detail":"Frame index 0 already exists with different sha256"}` | `UploadWorker: 409 CONFLICT ... requer novo capture_id` + `SpoolDao.incrementAttempts` |
| 9 | Reabrir app (kill + open) com 1 pendente | `init reenqueueAllPending: 1 frames` + envio automático | `SpoolRepository: reenqueueAllPending: 1 frames re-enfileirados` |

### 4.3 Comandos `curl` para validar sem APK

```bash
# Obter token se necessário: verificar apps/api/dependencies.py verify_gateway_token
export BASE=https://SEU_VPS/api/v1
export SESSION=$(curl -s -H "Authorization: Bearer $TOKEN" -X POST $BASE/gateway/session/start \
  -H "Content-Type: application/json" \
  -d '{"device_code":"GW-ANDROID-001","capture_source":"ANDROID_CAMERA","allow_new_session":true}' | jq -r .session_id)

# Frame 0
echo -n "fake-jpeg-data" > /tmp/frame0.jpg
SHA=$(sha256sum /tmp/frame0.jpg | cut -d' ' -f1)
curl -v -H "Authorization: Bearer $TOKEN" -X POST $BASE/gateway/session/$SESSION/frame \
  -H "X-Capture-Id: cap-test-001" -H "X-Frame-Index: 0" -H "X-SHA256: $SHA" \
  -H "X-Resolution: 1280x720" -H "X-Received-Android-At: $(date -u +%Y-%m-%dT%H:%M:%SZ)" -H "X-Orientation: 0" \
  -F file=@/tmp/frame0.jpg

# Reenvio idempotente (mesmo sha) → 200 duplicate:true
curl -s -H "Authorization: Bearer $TOKEN" -X POST $BASE/gateway/session/$SESSION/frame \
  -H "X-Capture-Id: cap-test-001" -H "X-Frame-Index: 0" -H "X-SHA256: $SHA" \
  -H "X-Resolution: 1280x720" -F file=@/tmp/frame0.jpg | jq .duplicate # → true

# Conflito (mesmo índice, sha diferente) → 409
echo -n "different-data" > /tmp/frame0b.jpg
SHA2=$(sha256sum /tmp/frame0b.jpg | cut -d' ' -f1)
curl -s -H "Authorization: Bearer $TOKEN" -X POST $BASE/gateway/session/$SESSION/frame \
  -H "X-Capture-Id: cap-test-001" -H "X-Frame-Index: 0" -H "X-SHA256: $SHA2" \
  -H "X-Resolution: 1280x720" -F file=@/tmp/frame0b.jpg -w "%{http_code}\n"
# → 409
```

### 4.4 Validação pós-upload

- [ ] `GET /gateway/session/{id}/capture-complete?capture_id=cap-...&received_frames=3` → `200` e `captures.received_frames` atualizado
- [ ] `POST /gateway/session/{id}/end-signal` → `LOCKED` (ver `GET /sessions/{id}` status)
- [ ] `GET /gateway/session/{id}/result?device_id=GW-ANDROID-001&cursor=0` → `RGB_SEQUENCE_READY` quando pipeline terminar

---

## 5. Testes automatizados

### 5.1 Servidor

```bash
uv run ruff check src/pages_to_audio/capture/frame_upload.py apps/api/routers/gateway.py
uv run pytest tests/unit -q # 330 passed inclui rgb canonical/policy + domain state_machine
```

`frame_upload.py` idempotência é coberta por `gateway.py` e2e; para unit, mockar `StoragePort` + `AsyncSession` com `FakeStorageAdapter`.

### 5.2 Android JVM (Robolectric)

```bat
cd apps\gateway-android
.\gradlew test --tests "com.pagestoaudio.gateway.spool.SpoolDaoTest"
.\gradlew test --tests "com.pagestoaudio.gateway.spool.SpoolRepositoryTest"
.\gradlew test --tests "com.pagestoaudio.gateway.sync.UploadWorkerTest"
.\gradlew test --tests "com.pagestoaudio.gateway.util.Sha256UtilTest"
.\gradlew connectedAndroidTest # se device/emulador disponível
adb logcat | findstr /R "Spool UploadWorker Gateway PhoneCamera SessionVM"
```

Se não houver Android SDK neste host, os testes são verificados estaticamente e a checklist manual acima é o gate.

---

## 6. Arquivos tocados nesta Etapa

- `apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/spool/PendingFrame.kt` — unique index, ack, attempts, width/height
- `apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/spool/SpoolDao.kt` — pending, markAck, prune, findByCaptureFrame, incrementAttempts
- `apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/spool/AppDatabase.kt` — Room DB + inMemory para testes
- `apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/spool/SpoolRepository.kt` — ordem obrigatória, SHA streaming check, enqueue KEEP, reenqueueAllPending, markAck+delete
- `apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/sync/UploadWorker.kt` — SHA recalc, headers, 2xx/409/4xx/5xx + retry/backoff, delete após ACK
- `apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/network/ApiService.kt` — multipart + headers X-*
- `apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/ui/SessionViewModel.kt` — init reenqueue + NetworkCallback onAvailable
- `apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/domain/SessionRepository.kt` — startSession com capture_source=ANDROID_CAMERA
- `apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/util/Sha256Util.kt` — streaming 8192B
- `src/pages_to_audio/capture/frame_upload.py` — idempotência session+capture+frame+sha, duplicate flag
- `apps/api/routers/gateway.py` — POST /frame com headers, storage put_object overwrite=False, duplicate
- `src/pages_to_audio/db/models/frame.py` — UniqueConstraints + capture_source
- Testes novos: `apps/gateway-android/app/src/test/java/.../spool/SpoolDaoTest.kt`, `spool/SpoolRepositoryTest.kt`, `sync/UploadWorkerTest.kt`, `util/Sha256UtilTest.kt`
- `apps/gateway-android/app/build.gradle.kts` — dependências de teste (robolectric, test:core)
- `docs/FLUXO_SPOOL_UPLOAD_ETAPA4.md` — este arquivo

---

## 7. O que NÃO fazer (reafirmação)

- Não abrir câmera em WorkManager/background.
- Não enviar `jpeg_quality=8` — usar `PROBE 75 / FULL 92` e `X-Resolution` real.
- Não apagar arquivo antes de `2xx` (SpoolRepository.markAck e UploadWorker garantem).
- Não reciclar `capture_id` com conteúdo diferente (409 exigirá novo `capture_id`).
- Não armazenar JPEG permanente na VPS (só Supabase + TTL local).

