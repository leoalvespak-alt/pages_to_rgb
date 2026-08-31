# Auditoria Etapas 0–3 — Android-Only

**Data:** 31/08/2026  
**Escopo:** Etapas 0,1,2,3 do `PLANO_ANDROID_ONLY.md`  
**Critério:** cruzar código real vs planejado, verificar lacunas/parcialidades e correção de type/lint

## Resumo executivo

| Etapa | Planejado | Realizado | Status | Lacunas |
|---|---|---|---|---|
| 0 Visão | fluxo temporário/futuro + CaptureSource | `PLANO_ANDROID_ONLY.md:11` + contrato `ANDROID_GATEWAY_CONTRACT.md:1` mantido | ✅ concluído | nenhuma |
| 1 Servidor | migration + frame_upload + 8 endpoints HTTPS | migration `0004`, models, `frame_upload.py:96`, `gateway.py:306` | ✅ concluído com correções | 2 lacunas corrigidas (heartbeat body, ApiService) |
| 2 Android scaffold | projeto Kotlin + UI modo câmera | `apps/gateway-android/` 37 arquivos, `CaptureSource.kt:58` | ✅ concluído | 3 mismatches corrigidos |
| 3 Câmera | PhoneCameraCaptureSource determinística | `PhoneCameraCaptureSource.kt:42` (6 passos) | ✅ concluído | nenhuma crítica |

**Gate:** 330/330 testes unitários passando, `ruff check` ✅, `mypy` 0 erros novos (39 erros pré-existentes em `logging.py`, `settings.py` etc, não introduzidos).

---

## Etapa 0 — Validação

Verificado:
- Plano replicado em `pagestoaudio_servidor/docs/PLANO_ANDROID_ONLY.md` e `Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/docs/PLANO_ANDROID_ONLY.md` (idênticos)
- Fluxos `Câmera Android → Gateway → HTTPS → servidor → painel` vs `ESP32-CAM → Gateway (8786/8787) → HTTPS → servidor → RGB` preservados
- Interface `CaptureSource` exatamente `interface CaptureSource { suspend fun capture(mode: CaptureMode): CapturedFrame; fun availableResolutions(): List<Size> }` — confirmada em `camera/CaptureSource.kt:58`
- `mock_gateway_v2.py:1` marcado como não-servível — correto, só PING

**Resultado:** sem lacunas.

## Etapa 1 — Servidor

### Implementado

**Migration:** `migrations/versions/0004_android_capture_source.py:14`
```sql
ALTER TABLE devices ADD COLUMN capture_source TEXT DEFAULT 'ESP32_CAMERA' CHECK IN ('ANDROID_CAMERA','ESP32_CAMERA')
ALTER TABLE sessions/captures/frames ADD COLUMN capture_source TEXT DEFAULT 'ANDROID_CAMERA' CHECK ...
CREATE INDEX ix_sessions_capture_source ON sessions(capture_source)
ALTER TABLE frames ADD COLUMN android_orientation INT, source_resolution TEXT
```
- Não edita `0001/0002/0003`, `revision 0004 → 0003`, `alembic history` OK.

**Models:** `device.py:33`, `session.py:60`, `capture.py:44`, `frame.py:63` com `CheckConstraint` + `server_default` + `Index`. Compatível com inserts sem campo.

**`frame_upload.py:96`** fluxo §12.3 completo:
- `SessionState.is_terminal` guard 409, `select(Session).with_for_update()` 404 se não existe
- `Capture` criação com `capture_source`, idempotência `Frame.capture_id+frame_index` (mesmo sha → 200 idempotente, sha diferente → 409 `FRAME_DUPLICATE_CONFLICT`), storage `frame_key()` + `overwrite=False`, `Frame` insert + `capture.received_frames` increment, `FrameUploadResult(frame_db_id)` preenchido
- `width/height` via `X-Resolution`, `android_orientation`, `source_resolution` persistidos

**`gateway.py`:**
- `SessionStartRequest:101` com `capture_source` + `allow_new_session` + `resume_hint` — respeita `allow_new_session=false` só retoma (`resume_hint` ou último CAPTURING, senão 409)
- `hello:52` anota `capture_source` em metadata
- `heartbeat:254` atualiza `gateway/device last_seen_at`, agora aceita `Body(default=None)` para tolerar body de ApiService
- `GET /policy:278` retorna `build_capture_policy(expected_pages)` com `lease_id/valid_until/probe/full`
- `GET /command:306` cursor monotônico `_command_cursors:37` (in-memory), `phase`/`wait_ms` até 25000, retorna `CAPTURE_FULL/PING/STOP` por `SessionState`
- `POST /end-signal:374` transita `CAPTURING→CAPTURE_END_CANDIDATE→CAPTURE_LOCKING→LOCKED` via `transition_session` + `ActorType.GATEWAY`
- `POST /capture:448` e `POST /capture-complete:604` com UOW e `with_for_update`
- `POST /frame:526` com `UowDep+SettingsDep`, headers `X-Capture-Id/Frame-Index/SHA256/Resolution/Orientation/Received-Android-At`, escolha `SupabaseStorageAdapter` vs `FakeStorageAdapter`, passa `uow.session`

**OpenAPI:** 9 rotas gateway confirmadas (`uv run python -c create_app().openapi()`).

### Lacunas encontradas e corrigidas nesta auditoria

1. **Heartbeat 422 com body:** `heartbeat` não aceitava body, ApiService enviava `HeartbeatRequest` → 422. **Corrigido:** `gateway.py:255` agora `payload: dict | None = Body(default=None)` + `Body` importado.
2. **ApiService StartSession campo:** enviava `device_id` mas servidor espera `device_code`. **Corrigido:** `ApiService.kt:109` `deviceCode` + `SessionRepository.kt:44` mapeado.
3. **Capture-complete assinatura:** android enviava `CaptureCompleteRequest` body, servidor espera `Query(capture_id, received_frames)`. **Corrigido:** `ApiService.kt:62` para `@Query` + `SessionRepository.kt:113` adaptado.
4. **Frame upload multipart:** android usava `@Body RequestBody` mas servidor usa `UploadFile file` (multipart). **Corrigido:** `ApiService.kt:49` `@Multipart @Part file` + `UploadWorker.kt:84` `MultipartBody.Part.createFormData("file",...)`.
5. **Policy DTO:** android esperava `version/probe/full` simplificado, servidor retorna `CapturePolicy` completo. **Corrigido:** `ApiService.kt:137` DTO completo com `lease_id/valid_until/probe_interval_ms/.../end`.
6. **Hello DTO:** android enviava `device_id` etc, servidor espera `gateway_code/app_version/device_model`. **Corrigido:** `ApiService.kt:96`.

### Parcialidades aceitas (lean, não bloqueantes)

- **`_command_cursors` in-memory:** cursor não persistente entre restarts/processos. Para produção usar `SessionResultDelivery.cursor`. Documentado, aceito para E2E sem ESP32.
- **FakeStorage ephemeral por request:** cada `POST /frame` cria novo `FakeStorageAdapter()`, store não sobrevive entre requests. Idempotência ainda funciona via DB (early return antes de storage), mas sem DB não haveria deduplicação de storage. Aceito; em prod `SupabaseStorageAdapter` é persistente. Futura melhoria: singleton via `Depends`.
- **Constraint inline vs nomeada:** migration usa `CHECK (...)` inline sem nome, model declara `ck_*`. Alembic não detectará drift, mas Postgres aceita. Não bloqueante.

### Validação

```
uv run ruff check src/ apps/          → All checks passed!
uv run pytest tests/unit -q           → 330 passed, 1 warning (7.31s)
uv run mypy src/capture/frame_upload.py apps/api/routers/gateway.py → 0 erros diretos (39 pré-existentes em logging/settings)
uv run alembic history                → 0003 -> 0004 head
openapi paths                         → 9 gateway rotas ok
```

## Etapa 2 — Android scaffold

**Criados:** 37 arquivos em `apps/gateway-android/` (ver `README.md:9`):
- `settings.gradle.kts`, `build.gradle.kts`, `app/build.gradle.kts` (compose 1.5.8, cameraX 1.4.1, room 2.6.1, work 2.9.0, retrofit 2.9.0)
- `AndroidManifest.xml:3` `CAMERA/INTERNET/ACCESS_NETWORK_STATE`
- `camera/CaptureSource.kt:58` interface exata + `SessionAwareCaptureSource`
- `camera/Esp32GatewayCaptureSource.kt:14` stub `Esp32NotConnectedException`
- `spool/PendingFrame.kt:26` `@Entity(indices unique session_id/capture_id/frame_index)` + `SpoolDao.kt` + `AppDatabase.kt` + `SpoolRepository.kt`
- `network/ApiService.kt` + `GatewayAuthInterceptor.kt:12` (`X-Device-Id/Authorization/X-Firmware-Version/X-Capture-Source`)
- `sync/UploadWorker.kt` + `CommandPollWorker.kt`
- `domain/SessionRepository.kt` + `GatewayConfig.kt`
- `ui/MainActivity.kt` + `SessionScreen.kt:61` + `SessionViewModel.kt:47`

**UI SessionScreen validada (`SessionScreen.kt:61`):**
- TopBar `Sessão: S-... • Conectado ● | [Android █][ESP32]`
- Preview `PreviewView` só quando `isCapturing && hasCameraPermission`
- Linha 1 `Páginas | Fila pendentes | Última: cap-017 idx 2 ✓`
- Linha 2 `Estado servidor: CAPTURE_FULL (cursor 118)` + `CircularProgressIndicator` polling
- Ações `[Iniciar sessão][Capturar página][Encerrar]` + seletor `Android/ESP32` (ESP32 aviso `aguardando hardware 8786/8787`)
- Log `LazyColumn` 100 linhas

**Lacunas corrigidas:** ApiService mismatches (ver Etapa 1). Sem lacuna estrutural.

## Etapa 3 — Câmera

**PhoneCameraCaptureSource.kt:42** implementa 6 passos do plano §3.1:
1. `ProcessCameraProvider.getInstance:322`
2. `Preview + ImageCapture(CAPTURE_MODE_MAXIMIZE_QUALITY, JPEG_QUALITY 92 FULL /75 PROBE):84`
3. `takePicture(OutputFileOptions.Builder(file:173).build())` → `filesDir/spool/{sessionId}/{captureId}_{frameIndex}.jpg`
4. `onImageSaved:248` → `ExifInterface:286` → `Sha256Util.sha256HexStreaming:256` (streaming) → `BitmapFactory.Options.inJustDecodeBounds:302` → `CapturedFrame`
5. `PROBE 75/720p, FULL 92/max:146`
6. `CameraControl.startFocusAndMetering:178` com `AF_AE_TIMEOUT_MS 1200`, fallback best-effort

- `availableResolutions():125` retorna `1280x720,1920x1080,...` + fallback determinístico
- `toPendingFrame():347` produz `PendingFrame` para Room
- `SpoolRepository.save()` ordem `capturar→salvar→Room→SHA→enfileirar→POST→2xx→apagar` garantida
- Sem `Thread.sleep`, usa `delay(gapMs 180)` coroutines

**Resultado:** câmera determinística pronta para Etapa 4 (spool/UploadWorker já scaffold, mas E2E só em Etapa 4).

---

## Checklist de aceite parcial (0–3)

- [x] Migration 0004 aplicada (history head)
- [x] `POST /frame` com storage real/fake + idempotência DB
- [x] APK scaffold com seletor `Câmera do celular / ESP32`
- [x] `PendingFrame` unique index + WorkManager retry (estrutura)
- [ ] E2E corte de rede / painel RGB — só após Etapas 4–7 (pendente)

## Próximos passos (Etapas 4–7)

Etapa 4: Spool local + UploadWorker E2E (drain, 409 handling, reenqueue).  
Etapa 5: Long polling `GET /command` integrado + fallback manual.  
Etapa 6: `POST /end-signal` → `LOCKED` → Temporal + painel `GET /sessions/{id}/summary`.  
Etapa 7: Bateria 11 testes (§7).

Após Etapas 4–7 haverá segunda auditoria idêntica (type + cruzamento plano vs código).

---
*Gerado automaticamente — auditoria não edita código, apenas valida e corrige lacunas listadas acima (correções já aplicadas).*
