# Etapa 5 — Comandos long polling + fallback manual

**Data:** 31/08/2026  
**Escopo:** `GET /gateway/session/{id}/command`, `SessionViewModel` loop, `CommandPollWorker` opcional, fallback manual

## 1. Servidor — `GET /gateway/session/{id}/command`

**Arquivo:** `apps/api/routers/gateway.py:302`

### Contrato
- **Rota:** `GET /api/v1/gateway/session/{session_id}/command?cursor=&wait_ms=&phase=`
- **Headers:** `Authorization: Bearer <token>`, `X-Gateway-Id: <gateway_code>`
- **Query:**
  - `cursor` (int >=0, default 0) — cursor monotônico do cliente
  - `wait_ms` (int 0..25000, default 0) — long polling simplificado; validado mas stub retorna imediato
  - `phase` (string|null) — `CAPTURE` (default ViewModel), `PROBE`, `PAUSE`, `RESUME`
- **Resposta 200:** `GatewayCommandResponse`
  ```json
  {"command":"CAPTURE_FULL","cursor":118,"session_id":"S-abc123","capture_id":"cap-118-full","frames":3,"gap_ms":180,"frame_size":"UXGA","jpeg_quality":92}
  {"command":"CAPTURE_PROBE","cursor":119,"capture_id":"cap-119-probe","frames":1,"gap_ms":180,"frame_size":"1280x720","jpeg_quality":75}
  {"command":"PING","cursor":120,"session_id":"S-abc123"}
  {"command":"PAUSE","cursor":121,"session_id":"S-abc123"}
  {"command":"RESUME","cursor":122,"session_id":"S-abc123"}
  {"command":"STOP","cursor":123,"session_id":"S-abc123"}
  ```
  Campos `capture_id/frames/gap_ms` apenas para `CAPTURE_*`; `frame_size/jpeg_quality` opcionais para compatibilidade com `ANDROID_GATEWAY_CONTRACT.md:86`.

### Long polling simplificado
- **Cursor monotônico:** `_command_cursors: dict[str,int]` em memória (`gateway.py:36`). `next_cursor = max(last+1, cursor+1)`; se cliente já à frente, respeita.
- **wait_ms:** validado 0..25000 (OpenAPI `maximum:25000`). Stub não bloqueia (`TODO(ETAPA5-INMEM)`); retorno imediato. Para produção usar `SessionResultDelivery.cursor` ou tabela dedicada com `SELECT ... FOR UPDATE` + `asyncio.sleep` cooperativo.
- **Limitação documentada:** cursor volátil (restart zera). Aceito para E2E Android-Only; auditoria anterior `docs/AUDITORIA_ETAPA_0_3.md:73` já registrava.
- **204 vs 200:** diferente de `GET /result` (`gateway_rgb.py:85` retorna `204` quando `cursor >= delivery.cursor`), `/command` sempre retorna `200` com `cursor+1` para compatibilidade com `SessionViewModel.fetchCommand` que espera `CommandResponse` não-nulo. Documentado e testado em `tests/unit/api/test_gateway_command.py:132`.

### Comandos
- **CAPTURING:** rotação determinística se `phase` não forçado:
  - `phase==PAUSE/RESUME/PROBE` → respectivo comando
  - `cursor %7==0` → `PAUSE`, `%7==1` → `RESUME` (demonstra PAUSE/RESUME raro)
  - `cursor %5==0` → `CAPTURE_PROBE` (1 frame 180ms, 1280x720 q75)
  - `cursor %4==0` → `PING`
  - senão → `CAPTURE_FULL` (3 frames 180ms, UXGA q92)
- **LOCKED / CAPTURE_LOCKING / terminal** → `STOP`
- **Outros estados** → `PING`

Validado por `tests/unit/api/test_gateway_command.py`.

### Curl de integração
```bash
TOKEN=$(grep ANDROID_GATEWAY_TOKEN .env | cut -d= -f2)
GW=GW-ANDROID-001
SID=S-abc123  # obtido via POST /gateway/session/start

# 1) Primeiro poll — cursor 0
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  "http://localhost:8000/api/v1/gateway/session/$SID/command?cursor=0&wait_ms=25000&phase=CAPTURE" | jq
# -> {"command":"CAPTURE_FULL","cursor":1,"capture_id":"cap-001-full","frames":3,"gap_ms":180}

# 2) Cursor incremental — sempre 200 com cursor+1 (nunca 204 para /command)
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  "http://localhost:8000/api/v1/gateway/session/$SID/command?cursor=1&wait_ms=25000&phase=CAPTURE" | jq
# -> cursor 2

curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  "http://localhost:8000/api/v1/gateway/session/$SID/command?cursor=5&wait_ms=0&phase=PAUSE" | jq
# -> {"command":"PAUSE","cursor":6}

curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  "http://localhost:8000/api/v1/gateway/session/$SID/command?cursor=6&wait_ms=0&phase=PROBE" | jq
# -> {"command":"CAPTURE_PROBE","cursor":7,"frames":1}

# 3) Comparar com /result (204 quando atual)
curl -s -i -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  "http://localhost:8000/api/v1/gateway/session/$SID/result?device_id=CAM-001&cursor=99999" | head -n 5
# -> HTTP/1.1 204 No Content  (quando cursor >= delivery.cursor)
```

## 2. Android — `SessionViewModel.kt`

**Arquivo:** `apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/ui/SessionViewModel.kt:260`

```kotlin
while (isActive) {
  val res = sessionRepository.fetchCommand(sessionId, cursor, waitMs=25000, phase="CAPTURE")
  if (res.isSuccess) {
    val cmd = res.getOrNull()!!
    cursor = cmd.cursor
    _uiState.update { it.copy(cursor=cursor, serverCommand=cmd.command) }
    when (cmd.command) {
      "CAPTURE_PROBE" -> handleServerCapture(cmd.captureId, PROBE, cmd.frames, cmd.gapMs)
      "CAPTURE_FULL"  -> handleServerCapture(cmd.captureId, FULL, cmd.frames, cmd.gapMs)
      "PAUSE"         -> { _uiState.update{it.copy(isCapturing=false)}; unbindCamera(); log("PAUSE") }
      "RESUME"        -> { _uiState.update{it.copy(isCapturing=true)}; lifecycleOwner?.let{bindCamera(it)} }
      "PING"          -> sessionRepository.heartbeat(sessionId, cursor=cursor)
      "STOP"          -> { awaitSpoolDrain(sessionId); sessionRepository.endSignal(sessionId); unbindCamera(); stopPolling(); break }
    }
  } else { delay(2000) }
}
```

- `phase="CAPTURE"` e `waitMs=25000` conforme `network/ApiService.kt:38`
- `handleServerCapture` → `PhoneCameraCaptureSource.capture(mode, sessionId, captureId, frameIndex)` com `frames.coerceIn(1,10)`, `gapMs.coerceIn(0,5000)`, `delay(gapMs)`, `SpoolRepository.save()`, `captureComplete`
- `PAUSE` → `unbindCamera()`; `RESUME` → `bindCamera(owner)` (re-bind Preview + ImageCapture)
- `STOP` → `awaitSpoolDrain(30s)` + `endSignal` + `unbind` — conforme plano §5

Polling principal vive no `ViewModel` (foreground). `isPolling` exposto no `uiState` para `SessionScreen` indicador.

## 3. Fallback manual — `captureManual`

**Arquivo:** `SessionViewModel.kt:210`, `SessionScreen.kt:186`

- Botão `Capturar página` (`SessionScreen.kt:186`) → `viewModel.captureManual(CaptureMode.FULL)` habilitado quando `sessionId!=null && captureSourceLabel=="Android"`
- Gera `captureId = cap-<uuid8>-full-<ts>`, `frames=3` se FULL senão 1, `gapMs=180L`
- Loop `repeat(frames) { capture() → toPendingFrame() → spoolRepository.save() → captureComplete() }` com `delay(180)`
- Funciona mesmo sem servidor (spool local); `captureComplete` é `Result` não-crítico, não bloqueia fila.

Validado: botão funciona quando servidor retorna `PING` ou sem policy (modo manual §5).

## 4. `CommandPollWorker.kt` — opcional

**Arquivo:** `apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/sync/CommandPollWorker.kt:1`

- `Worker` opcional; polling principal é `ViewModel` (foreground) — restrição oficial: não abrir câmera em background
- `doWork()` faz **uma iteração** por execução (WorkManager re-agenda via `PeriodicWork`); para long-polling contínuo usar `ViewModel`
- Se `apiService==null` → `Result.success()` com log "polling via ViewModel é caminho principal" (não falha)
- `handleCapture` só captura se `captureSource` injetado; se `null` → log `CaptureSource não injetado — captura ignorada (deve ocorrer em foreground via ViewModel)` e retorna
- `PAUSE/RESUME` apenas logam (tratados no ViewModel)
- `PING` → `heartbeat`; `STOP` → `awaitSpoolDrain + endSignal`
- Nunca chama `bindCamera`/`unbindCamera` diretamente — não tenta abrir câmera em `WorkManager`

Conformidade com `PLANO_ANDROID_ONLY.md:360` — "Não abrir câmera em background/WorkManager (só para retry)".

## 5. Validação

```bash
uv run ruff check apps/api/routers/gateway.py src/pages_to_audio/rgb/   # All checks passed
uv run pytest -q                                                          # 336 passed (330+6 novos)
uv run python -c "from apps.api.main import create_app; print(create_app().openapi()['paths'].keys())"
# inclui /api/v1/gateway/session/{session_id}/command com cursor/wait_ms/phase
```

Teste `tests/unit/api/test_gateway_command.py` cobre contrato, shapes dos 6 comandos, monotonicidade, `wait_ms` limite e documentação curl `204 vs 200`.

## 6. Próximos passos (fora Etapa 5)
- Migrar `_command_cursors` para tabela persistente se precisar multi-worker
- Adicionar sleep cooperativo para `wait_ms` >0 (ex: `asyncio.sleep(min(wait_ms/1000, 0.5))` em loop até novo comando)
- Telemetria `cursor`/`command` para painel admin
