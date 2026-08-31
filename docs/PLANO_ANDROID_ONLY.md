# Plano Android-Only — Pages to Audio (sem ESP32)

**Versão:** 1.0 — 31/08/2026  
**Objetivo:** rodar o fluxo completo `câmera do celular → Gateway Android → servidor → painel RGB/áudio` sem hardware ESP32, mantendo compatibilidade total com o futuro `ESP32-CAM → Gateway → servidor`.  
**Repositórios alvo:**
- `C:\Users\Lenovo\Downloads\pagestoaudio_servidor` (VPS / API / processamento)
- `C:\Users\Lenovo\Downloads\Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1` (firmware + `docs/ANDROID_GATEWAY_CONTRACT.md:1`)
- App Android Gateway (novo — Kotlin + CameraX, a criar em repo dedicado)

> Este plano é **enxuto e executável**. Não duplica o `Pages_to_Audio_Resposta_IMPLEMENTATION_PLAN.md:1`; apenas recorta o mínimo para validar E2E enquanto a ESP32 não chega. Toda regra de `CLAUDE.md:1` (migrations, idempotência, timeouts) continua válida.

---

## 0. Visão e contrato lógico

### Fluxos

```text
[TEMPORÁRIO — agora]  Câmera Android → app Gateway → HTTPS → servidor → painel
[FUTURO — com ESP32]  ESP32-CAM → app Gateway (8786/8787) → HTTPS → servidor → RGB WS2812
```

O servidor enxerga os dois como **mesmo tipo lógico de dispositivo**. Muda só `capture_source`.

### Variantes de `CaptureSource` (Android)

```kotlin
interface CaptureSource {
  suspend fun capture(mode: CaptureMode): CapturedFrame
  fun availableResolutions(): List<Size>
}
class PhoneCameraCaptureSource(...) : CaptureSource   // AGORA
class Esp32GatewayCaptureSource(...) : CaptureSource  // FUTURO — ports 8786/8787
```

Ambas produzem o mesmo envelope (compatível com `ANDROID_GATEWAY_CONTRACT.md:86`):

```
device_id, session_id, capture_id, frame_index, resolução real,
JPEG bytes, SHA-256, timestamp, orientação, estado da captura
```

> `tools/mock_gateway_v2.py:1` **não serve** para este teste — só simula PING, não tem câmera nem processamento real.

---

## Etapa 1 — Servidor: expor contrato HTTPS completo (2–3 dias)

**Estado atual verificado:**
- `apps/api/routers/gateway.py:1` já tem `POST /gateway/hello`, `POST /gateway/session/start`, `POST /gateway/session/{id}/frame` (stub com `FakeStorageAdapter`), `POST /gateway/session/{id}/capture-complete` (stub), `GET /gateway/session/{id}/result` via `gateway_rgb.py:1`.
- Falta: `capture_source` no modelo, policy real, heartbeat/command long-polling, storage real, confirmação de captura.

### 1.1 Migration (obrigatória — `CLAUDE.md:1`)

Criar `migrations/versions/0004_android_capture_source.py` (não editar `0001_initial_schema.py:1` nem `0003_rgb_result_delivery.py:1`):

```sql
ALTER TABLE devices ADD COLUMN capture_source TEXT NOT NULL DEFAULT 'ESP32_CAMERA'
  CHECK (capture_source IN ('ANDROID_CAMERA','ESP32_CAMERA'));
ALTER TABLE sessions ADD COLUMN capture_source TEXT NOT NULL DEFAULT 'ANDROID_CAMERA';
ALTER TABLE captures ADD COLUMN capture_source TEXT NOT NULL DEFAULT 'ANDROID_CAMERA';
ALTER TABLE frames ADD COLUMN capture_source TEXT NOT NULL DEFAULT 'ANDROID_CAMERA';
CREATE INDEX ix_sessions_capture_source ON sessions(capture_source);
```

Opcional (se quiser auditar origem por frame já na V1):
```sql
ALTER TABLE frames ADD COLUMN android_orientation INT NULL;
ALTER TABLE frames ADD COLUMN source_resolution TEXT NULL;
```

### 1.2 Endpoints a fechar (namespace `/api/v1` — `Pages_to_Audio_Resposta_IMPLEMENTATION_PLAN.md:868`)

| Método | Rota | Já existe? | O que falta |
|---|---|---|---|
| `POST` | `/gateway/hello` | sim `gateway.py:32` | anotar `capture_source` no `metadata_` do gateway |
| `POST` | `/gateway/session/start` | sim `gateway.py:95` | aceitar `capture_source`, `allow_new_session`, `resume_hint`; respeitar regra `allow_new_session=false` só retoma (`ANDROID_GATEWAY_CONTRACT.md:55`) |
| `POST` | `/gateway/session/{id}/heartbeat` | stub `gateway.py:167` | persistir `last_seen_at`, retornar `policy_valid` |
| `GET`  | `/gateway/session/{id}/policy` | não | retornar `CapturePolicy` versionado (`capture/policy.py:1` já existe como modelo) |
| `GET`  | `/gateway/session/{id}/command?cursor=&wait_ms=&phase=` | não (só RGB `gateway_rgb.py:62`) | long-polling stub que retorna `CAPTURE_PROBE / CAPTURE_FULL / PAUSE / RESUME / PING / STOP` (`ANDROID_GATEWAY_CONTRACT.md:75`) |
| `POST` | `/gateway/session/{id}/frame` | parcial `gateway.py:203` | trocar `FakeStorageAdapter` por `SupabaseStorageAdapter`, validar `X-SHA256`, aplicar idempotência `session_id+capture_id+frame_index+sha256` (`ANDROID_GATEWAY_CONTRACT.md:122`), persistir `Frame` + `Capture` reais |
| `POST` | `/gateway/session/{id}/capture-complete` | stub | validar todos os frames chegaram, fechar `Capture` |
| `POST` | `/gateway/session/{id}/end-signal` | não | botão `Encerrar` do Android chama aqui → `LOCKED` |
| `GET`  | `/gateway/session/{id}/result` | sim `gateway_rgb.py:62` | já pronto — manter |
| `GET`  | `/gateway/session/{id}/rgb-sequence` | sim | já pronto |
| `POST` | `/gateway/session/{id}/rgb-sequence/event` | sim | já pronto |

### 1.3 `capture/frame_upload.py:71` — completar

Hoje o arquivo valida MIME/SHA mas não persiste `Frame` (query placeholder `frame_upload.py:116`). Fechar:

1. `select(Session).where(public_id==...)` + lock.
2. `select(Capture).where(session_id==..., capture_id==...)` — criar se não existir.
3. `select(Frame).where(capture_id==..., frame_index==..., sha256==...)` — se existe → `200 idempotente` (não reenviar ao Storage).
4. Se mesmo `capture_id+frame_index` com `sha256` diferente → `409 CONFLICT` (`common/errors.py` já tem `FrameConflictError`).
5. Só então `storage.put_object(...)` com `overwrite=False` e inserir `Frame`.
6. `config/settings.py:100` já tem `RGB_*`; adicionar `CAPTURE_*` se precisar tunar `MAX_FRAME_SIZE`.

### 1.4 Policy para Android (adaptar `capture/policy.py:21`)

Android não usa `jpeg_quality=8` da OV2640. Servidor trabalha com **perfis**:

```json
{ "probe": {"resolution":"1280x720","quality":75}, "full": {"resolution":"highest_available","quality":92} }
```

Android informa `X-Resolution` real; servidor grava `source_resolution` e `width/height` (para auditoria e pré-processamento futuro).

### 1.5 Critério de saída da Etapa 1

- [ ] `make migrate` / `uv run alembic upgrade head` passa.
- [ ] `simulate_android.py` consegue `POST /gateway/session/start` → `POST /gateway/session/{id}/frame` → `POST /capture-complete` com storage real (ou fake injetado em teste) e `200` idempotente no reenvio.
- [ ] `GET /gateway/session/{id}/command` retorna `cursor` monotônico.

---

## Etapa 2 — App Android Gateway: modo “Câmera do celular” (5–7 dias)

Novo projeto Kotlin (minSdk 26, target 34). Pacote sugerido: `com.pagestoaudio.gateway`.

### 2.1 Estrutura de módulos

```
app/
 ├─ ui/         MainActivity, SessionScreen (Compose), CameraPreview
 ├─ camera/     CaptureSource, PhoneCameraCaptureSource (CameraX)
 ├─ spool/      Room DB + File spool (JPEG + metadados)
 ├─ network/    Retrofit/OkHttp → ApiService (HTTPS)
 ├─ sync/       WorkManager UploadWorker + CommandPollWorker
 └─ domain/     SessionRepository, SpoolRepository
```

### 2.2 Tela principal (requisito do plano ChatGPT §2)

```
[TopBar]  Sessão: S-abc123  •  Conectado ●  |  [Android █] [ESP32 ]
[Preview]  (CameraX PreviewView — só quando session CAPTURING)
[Linha 1]  Páginas: 12  |  Fila: 2 pendentes  |  Última: cap-017 idx 2 ✓
[Linha 2]  Estado servidor: CAPTURE_FULL (cursor 118)
[Ações]   [ Iniciar sessão ]  [ Encerrar ]  (Encerrar → POST /end-signal)
[Log]     14:02:11 frame 0 sha=abc... ACK
```

- Seletor `Câmera do celular / ESP32` → troca `CaptureSource`. ESP32 fica desabilitado com aviso “aguardando hardware”.
- App **precisa estar em foreground** durante captura (restrição oficial de câmera em background — não tentar `ForegroundService` com câmera).

### 2.3 Dependências

```kotlin
// CameraX
androidx.camera:camera-core:1.4.x
androidx.camera:camera-camera2:1.4.x
androidx.camera:camera-lifecycle:1.4.x
androidx.camera:camera-view:1.4.x
// Spool
androidx.room:room-runtime:2.6.x
androidx.work:work-runtime-ktx:2.9.x
// Net
com.squareup.retrofit2:retrofit, okhttp3
// DI
org.jetbrains.kotlinx:kotlinx-coroutines
```

Permissões: `CAMERA`, `INTERNET`, `ACCESS_NETWORK_STATE`. Não precisa `RECORD_AUDIO` nem `BLUETOOTH`.

### 2.4 Critério de saída

- [ ] App abre, pede permissão, mostra Preview.
- [ ] Troca `PhoneCameraCaptureSource ↔ Esp32GatewayCaptureSource` sem quebrar build (segunda é stub que loga “ESP32 não conectado”).

---

## Etapa 3 — Câmera: captura determinística (dentro da Etapa 2)

### 3.1 PhoneCameraCaptureSource — passos exatos

1. `ProcessCameraProvider.getInstance(context)`
2. `Preview` + `ImageCapture` com `CAPTURE_MODE_MAXIMIZE_QUALITY`, `JPEG_QUALITY=92` (ou 75 para PROBE se servidor pedir).
3. Ao receber `CAPTURE_FULL` (ou clique manual “Capturar página” no modo teste):
   ```kotlin
   val file = spoolDir.resolve("${captureId}_${frameIndex}.jpg")
   imageCapture.takePicture(OutputFileOptions.Builder(file).build(), executor, callback)
   ```
4. No `onImageSaved`:
   - ler `ExifInterface` → corrigir orientação (rotacionar bitmap se `ORIENTATION_ROTATE_90/270`).
   - gravar JPEG já orientado (ou manter original + anotar `orientation` no header).
   - calcular `SHA-256` (stream, não carregar 2x em RAM).
   - extrair `width/height` via `BitmapFactory.Options.inJustDecodeBounds`.
   - obter `capture_id = "cap-${seq}-${mode}-${timestamp}"` (UUID curto, único por burst).
5. Produzir `PendingFrame(capture_id, frame_index, sha256, resolution="WxH", bytes, createdAt)`.

### 3.2 Regras de qualidade

- `jpeg_quality=8` da OV2640 ≠ Android. Mapear: `PROBE→quality 70-75 / 720p`, `FULL→quality 90-95 / máxima disponível`. Servidor só valida que `X-Resolution` foi informado.
- Fixar `AF` + `AE` antes do disparo quando possível (`CameraControl.startFocusAndMetering`).
- Não aplicar filtro nativo; correção de perspectiva/CLAHE fica no servidor (pipeline `image/*` futuro).

### 3.3 Orientação

Sempre gravar `orientation` e enviar `X-Orientation` (custom). Servidor pode ignorar na V1 mas o dado já fica para `IMAGE_PROCESSING` não girar página errada.

### 3.4 Critério de saída

- [ ] Foto capturada tem `sha256` estável (ler arquivo 2x → mesmo hash).
- [ ] `width/height` bate com `X-Resolution` informado.
- [ ] Imagem aparece correta (não de lado) no preview de “última enviada”.

---

## Etapa 4 — Spool local + upload idempotente (coração da confiabilidade)

Ordem **obrigatória** (mesma do firmware: salvar antes de enviar):

```
1. capturar JPEG
2. salvar em armazenamento privado (getFilesDir()/spool/{session_id}/)
3. inserir em Room: PendingFrame(session_id, capture_id, frame_index, sha256, path, attempts, createdAt)
4. calcular SHA-256 (se ainda não)
5. enfileirar UploadWorker (ou envio direto se online)
6. POST /gateway/session/{id}/frame  (headers: X-Capture-Id, X-Frame-Index, X-SHA256, X-Resolution, X-Received-Android-At)
7. aguardar 2xx → marcar como ACK → apagar arquivo SOMENTE após ACK
```

### 4.1 Schema Room (mínimo)

```kotlin
@Entity(indices=[Index(value=["session_id","capture_id","frame_index"], unique=true)])
data class PendingFrame(
  @PrimaryKey val id:String = UUID.randomUUID().toString(),
  val session_id:String, val capture_id:String, val frame_index:Int,
  val sha256:String, val filePath:String, val resolution:String,
  val orientation:Int, val createdAt:Long, val ack:Boolean=false
)
```

### 4.2 WorkManager

- `UploadWorker` com `Constraints(NETWORK_CONNECTED)`, `BackoffPolicy.EXPONENTIAL` (5s → 5min), `ExistingWorkPolicy.APPEND`.
- **Não** usar WorkManager para abrir câmera — só para retry de upload.
- Ao reabrir o app, `SpoolRepository.pending()` re-enfileira tudo não ACK. Reenvio com **mesmo** `session_id+capture_id+frame_index+sha256` → servidor responde `200` idempotente, não duplica `LogicalPage`.

### 4.3 Idempotência

Servidor já tem `Frame` com `UNIQUE(session_id, sha256, capture_id, frame_index)` (`db/models/frame.py:27`). Android deve:

- nunca reciclar `capture_id` para conteúdo diferente;
- nunca reutilizar `frame_index` dentro do mesmo `capture_id` com hash diferente (se acontecer → `409`, criar evento crítico e pedir novo `capture_id`).

### 4.4 Critério de saída

- [ ] Desligar internet durante captura → foto fica em “Fila: 1 pendente”.
- [ ] Religar → WorkManager envia e `Fila: 0`.
- [ ] Reenvio manual do mesmo arquivo → servidor retorna `200` sem criar duplicata (verificar no banco `frames`).

---

## Etapa 5 — Comandos do servidor (long polling leve)

Enquanto a sessão está `CAPTURING`, o app faz:

```kotlin
while (sessionActive) {
  val cmd = api.getCommand(sessionId, cursor, waitMs=25000, phase="CAPTURE")
  cursor = cmd.cursor
  when (cmd.command) {
    "CAPTURE_PROBE" -> captureSource.capture(mode=PROBE, frames=1)
    "CAPTURE_FULL"  -> repeat(cmd.frames) { i -> captureSource.capture(mode=FULL, frameIndex=i, gapMs=cmd.gapMs) ; upload() }
    "PAUSE"         -> pausePreview()
    "RESUME"        -> resumePreview()
    "PING"          -> heartbeat()
    "STOP"          -> spool.awaitDrain(); api.postEndSignal(sessionId); showResultPollingUI()
  }
}
```

Notas:

- `wait_ms` até 25 s é ok (`httpx` no servidor já tem timeout explícito — `CLAUDE.md:9`).
- Se servidor ainda não implementou `GET /command` de captura, fallback: modo **manual** — botão “Capturar página” gera `CAPTURE_FULL` localmente (3 frames, 180 ms gap) e envia. Isso já valida todo o pipeline sem depender de policy.
- Polling de resultado RGB depois de `STOP` usa `GET /gateway/session/{id}/result?device_id=&cursor=` (`gateway_rgb.py:62`) com `204` quando sem update — já implementado.

---

## Etapa 6 — Encerramento e painel de respostas (servidor)

### 6.1 Fluxo de fim de captura

1. Android: `POST /gateway/session/{id}/end-signal` (ou `POST /sessions/{id}/finish-capture` se admin).
2. Servidor: `CAPTURE_LOCKING → LOCKED` (`capture/lock.py:1` já tem lógica) → inicia `ProcessExamWorkflow` (Temporal).
3. Enquanto processa, `GET /result` retorna `RESULT_PROCESSING` (amarelo).
4. Ao final (`GATE_2` aprovado), `rgb/publisher.py:1` publica `RGB_SEQUENCE_READY` (ou `RESULT_CANCELLED` se incompleto — ver `rgb/policy.py:1`).
5. Android em `RESULT_POLL` baixa `GET /rgb-sequence` e valida SHA canônico (`rgb/canonical.py:68` — `struct.pack("<BBBBBII")`).

### 6.2 Painel do servidor (onde o usuário vê sem ESP32)

Já existe `apps/admin/*` (React+Vite). Para o teste Android-only, o mínimo é:

- `GET /sessions/{id}` → mostra `expected_pages/questions`, `status`, `frames recebidos`, `LogicalPages`.
- `GET /sessions/{id}/summary` → lista `Question.question_number → FinalAnswer.answer (A-E) + cor` (mesma paleta `RGB_RESULT_V1.md:31`).
- Sem painel pronto, usar `simulate_android.py --rgb-session-id S-...` que já valida o fluxo RGB E2E (`scripts/simulate_android.py:175`).

### 6.3 Compatibilidade futura

A mesma `RgbSequence` (`db/models/rgb_sequence.py:1`) e `SessionResultDelivery` (`db/models/session_result_delivery.py:1`) que o painel lê hoje será lida pelo firmware V2.2 amanhã — **não mudar formato** (`docs/contracts/RGB_RESULT_V1.md:1` é a fonte da verdade).

### 6.4 Critério de saída

- [ ] Após `STOP`, `GET /result` evolui `NOT_STARTED → PROCESSING → RGB_SEQUENCE_READY` (ou `CANCELLED`).
- [ ] `GET /rgb-sequence` retorna JSON < 256 KiB, `answers` só `A-E`, `sha256` bate com `canonical.py:86`.
- [ ] Painel (ou `simulate_android.py`) exibe `Q1→C (ciano)`, `Q2→E (vermelho)` etc.

---

## Etapa 7 — Testes obrigatórios (Definition of Done)

Executar **na ordem** — cada linha é um gate:

| # | Ação | Esperado |
|---|---|---|
| 1 | Android: `Iniciar sessão` (`POST /gateway/session/start` com `capture_source=ANDROID_CAMERA`) | `201` com `session_id` S-... |
| 2 | Servidor: `GET /command?cursor=0` | `CAPTURE_PROBE` ou `CAPTURE_FULL` (ou `PING` se sem policy) |
| 3 | Android: captura + `POST /frame` | `200` com `storage_key=sessions/S-.../frames/cap-.../0.jpg` |
| 4 | Servidor: solicitar burst (`CAPTURE_FULL frames=3`) | Android envia 3 frames, `POST /capture-complete` → `200` |
| 5 | Android: `Encerrar` → `POST /end-signal` | Sessão `LOCKED` |
| 6 | Servidor: Temporal `ProcessExamWorkflow` | `GATE_1` e `GATE_2` aprovados (ou degradado) |
| 7 | Painel: `GET /sessions/S-.../summary` | Lista de respostas `A-E` + cores |
| 8 | **Corte de internet** durante `frame 1/3` | Frame fica em spool |
| 9 | Reabrir app com rede | Reenvio idempotente → `200` (não `409`), `frames` count não duplica |
| 10 | Reenvio com `frame_index` igual mas `sha256` diferente | `409 CONFLICT` |
| 11 | `GET /result?cursor=old` → `GET /rgb-sequence` → `POST /rgb-sequence/event COMPLETED` repetido | Segundo `COMPLETED` → `200 duplicate:true` (`delivery.py:397`) |

**Comandos de validação** (`CLAUDE.md:32`):

```bash
make lint
make typecheck
make test-unit        # inclui tests/unit/rgb — vetores dourados 41ffffff0cb80b... / 6f2f655b...
make test             # + integration (idempotência, cursor monotônico)
make migrate
uv run python scripts/simulate_android.py --frames 10
uv run python scripts/simulate_android.py --rgb-session-id S-... --rgb-mode normal
uv run python scripts/simulate_android.py --rgb-session-id S-... --rgb-mode invalid-hash  # deve rejeitar
```

Android local:

```bash
./gradlew test
./gradlew connectedAndroidTest   # CameraX + Room + WorkManager
adb logcat | grep -E "Spool|UploadWorker|Gateway"
```

---

## O que NÃO fazer

- Não usar `mock_gateway_v2.py:1` para este plano (só PING).
- Não fazer Android enviar `jpeg_quality=8` — usar perfis `PROBE/FULL` e informar `X-Resolution` real.
- Não armazenar JPEG permanentemente no disco da VPS (`CLAUDE.md:17`); só Supabase Storage + TTL local.
- Não abrir câmera em background/WorkManager (`WorkManager.html` — só para retry).
- Não criar fallback silencioso se `PaddleOCR`/`Supabase` cair (`CLAUDE.md:4`).

---

## Ordem de execução recomendada (2 semanas enxutas)

**Semana 1 — Servidor + Camera stub**
1. Migration `0004` + fechar `frame_upload.py:71` + `gateway.py:95` (1 dia)
2. Implementar `GET /command` + `GET /policy` mínimos (1 dia)
3. Criar projeto Android, `PhoneCameraCaptureSource`, preview (2 dias)
4. Spool Room + `UploadWorker` + `X-SHA256` (1 dia)

**Semana 2 — Integração E2E**
5. Long polling de comandos + `end-signal` (1 dia)
6. Painel `summary` ou validação via `simulate_android.py:175` (1 dia)
7. Bateria de testes §7 + corte de rede/idempotência (2 dias)
8. Doc final + gravação de vídeo E2E para aceite (1 dia)

---

## Entregáveis

- [ ] Migration `0004` aplicada.
- [ ] `POST /frame` com storage real e idempotência `session_id+capture_id+frame_index+sha256`.
- [ ] APK `gateway-android-only` com seletor `Câmera do celular / ESP32`.
- [ ] Spool durável + WorkManager retry + teste de corte de rede passando.
- [ ] Painel (ou `simulate_android.py`) exibindo respostas `A-E` com cores da paleta padrão (`PLANO_IMPLEMENTACAO_RGB_RESPOSTAS.md:42`).
- [ ] `PLANO_ANDROID_ONLY.md` espelhado em ambos os repos (este arquivo).

---

## Referências cruzadas (leitura obrigatória antes de codar)

- `pagestoaudio_servidor/CLAUDE.md:1` — regras invioláveis.
- `Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/docs/ANDROID_GATEWAY_CONTRACT.md:1` — contrato V2.2 (ports 8786/8787, idempotência, `STOP`→deep sleep 300s).
- `pagestoaudio_servidor/docs/contracts/RGB_RESULT_V1.md:1` — formato RGB schema 1 + SHA canônico.
- `pagestoaudio_servidor/PLANO_ALINHAMENTO_SERVIDOR_RGB_FIRMWARE_V2_2.md:1` — detalhes de `session_result_deliveries` / `rgb_sequences` / `rgb_sequence_events`.
- `pagestoaudio_servidor/src/pages_to_audio/rgb/canonical.py:68` — packing `<BBBBBII` e vetores dourados (`8a2b2c91...` / `6f2f655b...`).
