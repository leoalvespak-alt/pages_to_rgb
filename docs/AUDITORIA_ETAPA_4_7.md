# Auditoria Etapas 4–7 — Android-Only

**Data:** 31/08/2026  
**Escopo:** Etapas 4,5,6,7 do `PLANO_ANDROID_ONLY.md`  
**Critério:** cruzar código real vs planejado, lacunas/parcialidades, type/lint, 11 gates

## Resumo executivo

| Etapa | Planejado | Realizado | Status | Lacunas pós-correção |
|---|---|---|---|---|
| 4 Spool | ordem `capturar→salvar→Room→SHA→enfileirar→POST→2xx→apagar` + WorkManager | `SpoolRepository.kt:39`, `UploadWorker.kt:26`, `InMemorySpool` tests | ✅ concluído | nenhuma crítica |
| 5 Polling | `GET /command?cursor=&wait_ms=&phase=` + fallback manual | `gateway.py:325` + `SessionViewModel.kt:252` + `CommandPollWorker.kt` | ✅ concluído | `wait_ms` stub (sem sleep) documentado |
| 6 Encerramento | `POST /end-signal` → `LOCKED` → `GET /result` → `GET /rgb-sequence` + painel | `gateway.py:446` + `gateway_rgb.py:62` + `GET /summary:567` + `POST /debug/publish-rgb:692` | ✅ concluído | Temporal best-effort |
| 7 Testes 11 gates | tabela 11 gates + `ruff/mypy/pytest` | `test_android_only_e2e.py` 25 testes + `android_only_e2e_check.py` + `ETAPA_7_TESTES_11_GATES.md` | ✅ concluído | nenhuma |

**Gate:** `ruff check src/ apps/` ✅ `All checks passed!`, `mypy src/` 0 erros novos (39 pré-existentes em `logging/settings/db`), `pytest` **361 passed** (336 + 25 Etapa 7, `test_gate1..11`).

---

## Etapa 4 — Spool + upload idempotente

**Código:**

- **Room:** `PendingFrame.kt:26` `@Entity(indices unique session_id,capture_id,frame_index)`, `SpoolDao.kt:11` `pending/pendingForSession/markAck/incrementAttempts/pruneAcked`, `AppDatabase.kt:8` `gateway_spool.db` + `createInMemory` para testes.
- **SpoolRepository.kt:39:** `save()` valida unicidade (`findByCaptureFrame` → mesmo sha → `success(existing)`, sha diferente → `failure(Conflito… novo capture_id)`), verifica `File.exists`, `dao.insert(ABORT)`, `enqueueUpload()` com `WorkName "upload-${session}-${capture}-${index}"` + `ExistingWorkPolicy.KEEP` + `Constraints(NETWORK_CONNECTED)` + `Backoff EXPONENTIAL 5s`. `pendingCountFlow`, `reenqueueAllPending()` no `init` + `NetworkCallback onAvailable`.
- **UploadWorker.kt:26:** recalcula `Sha256Util.sha256HexStreaming`, compara, `multipart file` (`createFormData("file",...)`) + headers `X-Capture-Id/Frame-Index/SHA256/Resolution/Received-Android-At/Orientation`, trata `2xx→markAck+delete`, `409→failure`, `5xx/408/429/exception→retry`, `400..499→failure` + `incrementAttempts`.
- **Servidor:** `capture/frame_upload.py:96` idempotente (`duplicate:true` em `FrameUploadResult:56`), `gateway.py:852` retorna `{"duplicate": result.duplicate}`, `PUT overwriteFalse`, `FrameConflictError 409`.
- **Android spool reenqueue:** `SessionViewModel.kt:70` `NetworkCallback` + `pendingCountFlow` + `reenqueueAllPending()` no `init` (corte de rede → `Fila: N pendentes` → religar → `Fila:0`).

**Testes JVM (sem SDK, válidos offline):** `SpoolDaoTest.kt`, `SpoolRepositoryTest.kt`, `UploadWorkerTest.kt` (FakeApiService, SHA mismatch, 2xx/409/5xx), `Sha256UtilTest.kt` + `docs/FLUXO_SPOOL_UPLOAD_ETAPA4.md`. `SpoolRepository.kt:56` recalcula SHA antes do insert.

**Lacunas corrigidas nesta auditoria:** `FrameUploadResult.duplicate` faltava nos hits idempotentes (agora `duplicate:true` nos dois caminhos `172,202`), `UploadWorker` multipart, `NetworkCallback` reenqueue.

**Parcialidade aceita:** `FakeStorage` por-request (DB garante idempotência); `WorkManager` único por frame (KEEP).

## Etapa 5 — Long polling

**Servidor `gateway.py:325` `GET /command`:**
- `cursor` monotônico (`_command_cursors:37`), `wait_ms 0..25000` validado, `phase` opcional. Retorno imediato (sem `asyncio.sleep`) — documentado `TODO(ETAPA5-INMEM)` vs prod `SessionResultDelivery.cursor + SELECT FOR UPDATE + sleep wait_ms`.
- Retorna exatamente um de `CAPTURE_PROBE|CAPTURE_FULL|PAUSE|RESUME|PING|STOP` (`GatewayCommandResponse:307` com `frame_size/jpeg_quality` opcionais). `CAPTURING` + `phase` prioritário (`PAUSE/RESUME/PROBE`), rotação ` %7 PAUSE/RESUME, %5 PROBE (1f 180ms 1280x720 q75), %4 PING, else FULL (3f 180ms UXGA q92)` — compatível `ANDROID_GATEWAY_CONTRACT.md`. `LOCKED/terminal→STOP`.
- Diferença vs `GET /result` (204 quando atual) documentada: `/command` sempre `200 cursor+1` (compatível `SessionViewModel.fetchCommand`).

**Android `SessionViewModel.kt:252` `pollCommands`:**
- `while(isActive){ getCommand(cursor,25000,CAPTURE); when { PROBE→handleCapture(PROBE), FULL→repeat(frames) c/ gapMs, PAUSE→unbind, RESUME→bind, PING→heartbeat, STOP→awaitSpoolDrain 30s + endSignal + unbind + stopPolling } }`, `handleServerCapture:305` `coerceIn`, `delay(gapMs)`, `spool.save`, `captureComplete`.
- **Fallback manual:** `captureManual(FULL):202` botão `SessionScreen.kt:186` habilitado `sessionId!=null && Android`, gera `cap-<uuid8>-full-<ts>`, `3f gap 180` + `save→captureComplete` mesmo sem servidor (spool local).

**`CommandPollWorker.kt:1` (opcional):** 1 iteração por execução, `apiService==null→success` (polling principal é ViewModel foreground), nunca `bindCamera` (não tenta WorkManager com câmera).

**Doc:** `docs/ETAPA_5_POLLING.md` (contrato, rotação, curl `cursor=0→1→2` vs `GET /result 204`).

**Validação:** `uv run pytest tests/unit/api/test_gateway_command.py -q` 6 testes + `test_android_only_e2e.py::test_gate2_*` + `openapi` `cursor/wait_ms/phase`.

## Etapa 6 — Encerramento e painel

**`POST /end-signal:446`:** `CAPTURING→CAPTURE_END_CANDIDATE→CAPTURE_LOCKING→LOCKED` via `transition_session:184` (`ALLOWED_TRANSITIONS` + `AuditEvent`), `capture_locked_at`, idempotente `LOCKED→locked:true` + `already_terminal`. **Adicionado:** `mark_result_processing` `rgb/delivery.py:247` (protege `RGB_SEQUENCE_READY` não downgrade) + `TemporalWorkflowStarter.start_process_exam` best-effort (`if TEMPORAL_ADDRESS`).

**`GET /result, /rgb-sequence, POST /event` `gateway_rgb.py:62`:** já existiam, confirmados `204` quando `cursor>=delivery.cursor`, `compact_json_bytes <262144`, SHA canonical `<BBBBBII`.

**Painel:** `apps/admin` era stub; **criado** `GET /summary:567` (frames_count, questions+FinalAnswers ordenadas, `DEFAULT_PALETTE` `rgb/policy.py:15` A 255,255,255 B 255,255,0 C 0,255,255 D 0,0,255 E 255,0,0, `delivery{command,cursor}`, `rgb_sequence{sequence_id,revision,sha,payload_size}`) + **`POST /debug/publish-rgb:692`** (`publish_rgb_for_session` idempotente `reused` ou `RESULT_CANCELLED` se incompleto) — cobre `mínimo Android-only LOCKED→PROCESSING + publish manual`.

**Compatibilidade V2.2:** `schema_version 1` `rgb/schemas.py:108`, palette/defaults `policy.py:15` + `settings.py:133`, `canonical_items_bytes:68` `struct.pack("<BBBBBII")` vetores `8a2b2c91...`/`6f2f655b...`.

**Doc:** `docs/FLUXO_ENCERRAMENTO_PAINEL_ETAPA6.md` (curl end-signal/summary/result/rgb-sequence, SHA `struct.pack`, `simulate_android.py:175`).

**Qualidade:** `ruff check apps/api/routers/gateway.py` ✅, `mypy src/pages_to_audio/rgb` 33 pré-existentes 0 novo, `pytest tests/unit/rgb` 20 passed, `tests/unit/api` 13 passed.

## Etapa 7 — 11 gates

**Artefatos:**
- `tests/unit/api/test_android_only_e2e.py` 25 testes (`@pytest.mark.unit`, TestClient + `FakeStorageAdapter` + `InMemorySpool`): gates 1-11 via mocks (`test_gate1_openapi_exposes_capture_source`, `test_gate9_idempotent_resend_200_not_409`, `test_gate10_conflict_same_index_diff_sha_409`, `test_gate11_canonical_sha_matches_firmware <BBBBBII` etc).
- `scripts/android_only_e2e_check.py:83` `--print-curl` lista curls 1-11 + `--run-live` httpx E2E (gates 1-5,7,9-11 com `duplicate:true`/`409`/`LOCKED`/`summary`).
- `docs/ETAPA_7_TESTES_11_GATES.md:11` tabela 11 gates (ação/curl/esperado/validacao sem ESP32) + checklist `uv run`.

**Cobertura 11 gates (validado `TestClient` sem DB):**

| # | Teste | Estado |
|---|---|---|
|1| `POST /session/start ANDROID_CAMERA` `201` | `test_gate1_*` + `run_live` OK|
|2| `GET /command?cursor=0` `PING/CAPTURE_*` | `test_gateway_command.py` + `test_gate2_*` OK|
|3| `POST /frame` `200 storage_key` | `test_gate3_frame_upload_ok` OK|
|4| burst 3 + `POST /capture-complete` | `test_gate4_burst_3_frames` OK|
|5| `POST /end-signal` `LOCKED` | `test_gate5_*` mock transition OK|
|6| `GATE_1/2` via `debug/publish-rgb` | `test_gate6_*` OK (simulado)|
|7| `GET /summary` `A-E` + cores | `test_gate7_*` palette OK|
|8| corte internet `pending==2` | `test_gate8_spool_*` `InMemorySpool` OK|
|9| reenvio idempotente `200 duplicate:true` | `test_gate9_*` OK|
|10| `409` sha diferente | `test_gate10_*` OK|
|11| `GET /result 204` + `GET /rgb-sequence` SHA `<BBBBBII 6f2f655b...` + `POST COMPLETED×2 duplicate:true` | `test_gate11_*` OK|

**Comandos:**
```
uv run ruff check tests/unit/api/test_android_only_e2e.py scripts/android_only_e2e_check.py  # All checks passed
uv run pytest tests/unit -q                                     # 361 passed
uv run pytest tests/unit/api/test_android_only_e2e.py -v         # 25 passed
uv run python scripts/android_only_e2e_check.py --print-curl
uv run python scripts/android_only_e2e_check.py --run-live        # gates 1-5,7,9-11 live
uv run python scripts/simulate_android.py --frames 10
uv run python scripts/simulate_android.py --rgb-session-id S-... --rgb-mode normal
```

**Parcialidade aceita:** `wait_ms` sem sleep, Gate 6 simulado sem Questions reais (prod usa workflow Temporal).

---

## Correções de type/lint nesta auditoria (4–7)

- `apps/api/routers/gateway.py:8` `Body` import para `heartbeat:258` `payload: dict|None = Body(default=None)` (evita 422 body inesperado)
- `ApiService.kt:49` `uploadFrame` `multipart file` + `UploadWorker.kt:84` `MultipartBody.Part`
- `ApiService.kt:96` `HelloRequest gateway_code/app_version/device_model` + `gateway_code` em `StartSessionRequest`
- `ApiService.kt:137` `CapturePolicyResponse` completo (`lease_id/valid_until/probe_*/full_*/end`)
- `ApiService.kt:62` `captureComplete` `@Query(capture_id, received_frames)`
- `frame_upload.py:56` `duplicate: bool` nos two hits idempotentes
- `gateway.py:852` `{"duplicate": result.duplicate}`

**Pós-correção:** `ruff check src/ apps/` ✅ `All checks passed`, `ruff check src/ apps/ tests/ scripts/` 30 erros restantes são `S105/B017/E501` legados (`benchmark_providers.py`, `simulate_exam.py:4`, `test_settings.py:26`) não introduzidos por 4–7.

---

## Checklist final (0–7) Android-Only sem ESP32

- [x] Migration `0004` + `capture_source`
- [x] `POST /frame` idempotente + `409`
- [x] APK `gateway-android` seletor `Android/ESP32` + CameraX determinística
- [x] Spool `WorkName KEEP` + `NetworkCallback` reenqueue
- [x] `GET /command` 6 comandos + fallback manual 3f 180ms
- [x] `POST /end-signal` → `LOCKED` + `GET /summary` + `POST /debug/publish-rgb`
- [x] `GET /result 204` + `POST /event COMPLETED duplicate:true` + SHA `<BBBBBII`
- [x] 11 gates testáveis via `curl` + `TestClient` + `simulate_android.py` sem hardware
- [x] `PLANO_ANDROID_ONLY.md` espelhado, `AUDITORIA 0-3` + `AUDITORIA 4-7` completas
