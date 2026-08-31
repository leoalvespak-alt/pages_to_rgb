# ETAPA 7 — 11 Gates Obrigatorios (Android-Only sem ESP32)

**Data:** 31/08/2026  
**Fontes:** `docs/PLANO_ANDROID_ONLY.md:314` Etapa 7, `apps/api/routers/gateway.py`, `src/pages_to_audio/capture/frame_upload.py`, `src/pages_to_audio/rgb/delivery.py`, `docs/FLUXO_SPOOL_UPLOAD_ETAPA4.md`, `docs/ETAPA_5_POLLING.md`, `docs/FLUXO_ENCERRAMENTO_PAINEL_ETAPA6.md`  
**Validacao sem hardware:** todos os gates tem equivalente `curl` + `TestClient` via `tests/unit/api/test_android_only_e2e.py` + `scripts/android_only_e2e_check.py` + `scripts/simulate_android.py`.

---

## 1. Visao geral

| # | Acao | Esperado | Como validar sem ESP32 |
|---|---|---|---|
| 1 | `POST /gateway/session/start` `capture_source=ANDROID_CAMERA` | `201`/`200` `session_id` S-... | `curl` + `TestClient` mock UoW |
| 2 | `GET /command?cursor=0` | `CAPTURE_PROBE`/`CAPTURE_FULL` ou `PING` | `curl` com `cursor+phase` |
| 3 | `POST /frame` JPEG real | `200` `storage_key=sessions/.../0.jpg` | `curl -F file` + `upload_frame` unit |
| 4 | Burst `CAPTURE_FULL frames=3` + `POST /capture-complete` | 3 frames `200` + `200` | loop 3x `POST /frame` + `capture-complete` |
| 5 | `POST /end-signal` | `LOCKED` | `curl POST /end-signal` |
| 6 | Workflow `GATE_1`/`GATE_2` ou degradado | `RGB_SEQUENCE_READY` ou `RESULT_CANCELLED` via `debug/publish-rgb` | `POST /debug/publish-rgb` |
| 7 | `GET /summary` | lista `A-E` + cores | `curl /summary` + palette check |
| 8 | Corte internet frame `1/3` | spool fila `pending==1` | `InMemorySpool` + `UploadWorker` retry |
| 9 | Reabrir app com rede | reenvio idempotente `200` nao `409` | `POST /frame` mesmo `sha` -> `duplicate:true` |
| 10 | Reenvio `frame_index` igual `sha` diferente | `409 CONFLICT` | `POST /frame` conflito |
| 11 | `GET /result?cursor=old` -> `GET /rgb-sequence` -> `POST /event COMPLETED` repetido | segundo `COMPLETED` -> `200 duplicate:true` | `curl` poll + `delivery.record_rgb_event` |

Prerequisitos servidor local:

```bash
export BASE=http://localhost:8000/api/v1
export TOKEN="dev-gateway-token"   # ou ANDROID_GATEWAY_TOKEN do .env
export GW="GW-ANDROID-001"
export DEV="CAM-001"
uv run alembic upgrade head
uv run uvicorn apps.api.main:create_app --factory --host 0.0.0.0 --port 8000
```

---

## 2. Gate 1 — Iniciar sessao ANDROID_CAMERA

**Acao:** `POST /api/v1/gateway/session/start` com `capture_source=ANDROID_CAMERA`.

**Curl:**

```bash
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  -H "Content-Type: application/json" \
  -d '{"device_code":"CAM-001","capture_source":"ANDROID_CAMERA","allow_new_session":true,"expected_pages":5,"expected_questions":5}' \
  $BASE/gateway/session/start | jq .
# -> {"session_id":"abc123hex...","status":"CAPTURING","expected_pages":5,"expected_questions":5}
export SESSION=$(curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" -H "Content-Type: application/json" -d '{"device_code":"CAM-001","capture_source":"ANDROID_CAMERA","allow_new_session":true}' $BASE/gateway/session/start | jq -r .session_id)
```

**Esperado:** `200` (ou `201`) com `session_id` hex 16 chars, `status=CAPTURING`, `capture_source` persistido em `devices/sessions/captures/frames`.

**Validacao sem ESP32:** `tests/unit/api/test_android_only_e2e.py::test_gate1_*` via `TestClient` com `get_uow` mockado; `python scripts/android_only_e2e_check.py --run-live` exercita live.

**Falhas comuns:** `403 Device disabled` se `enabled=false`; `409` se `allow_new_session=false` sem `resume_hint` e sem sessao `CAPTURING`.

---

## 3. Gate 2 — GET /command?cursor=0

**Acao:** `GET /api/v1/gateway/session/{id}/command?cursor=0&wait_ms=25000&phase=CAPTURE`.

**Curl:**

```bash
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  "$BASE/gateway/session/$SESSION/command?cursor=0&wait_ms=25000&phase=CAPTURE" | jq .
# CAPTURING -> {"command":"CAPTURE_FULL","cursor":1,"capture_id":"cap-001-full","frames":3,"gap_ms":180,"frame_size":"UXGA","jpeg_quality":92}
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  "$BASE/gateway/session/$SESSION/command?cursor=5&wait_ms=0&phase=PAUSE" | jq .
# -> {"command":"PAUSE","cursor":6}
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  "$BASE/gateway/session/$SESSION/command?cursor=6&wait_ms=0&phase=PROBE" | jq .
# -> {"command":"CAPTURE_PROBE","cursor":7,"frames":1,"frame_size":"1280x720","jpeg_quality":75}
```

**Esperado:** sempre `200` com `cursor` monotônico (`cursor` da resposta = `cursor` requisitado +1). Campos `capture_id/frames/gap_ms` apenas para `CAPTURE_*`; `PING/STOP/PAUSE/RESUME` so `command/cursor/session_id`. Diferente de `GET /result` que retorna `204` quando atual.

**Validacao sem ESP32:** `test_gate2_*` checa `GatewayCommandResponse` shapes, `wait_ms` limite `0..25000`, cursor monotônico, e `android_only_e2e_check.py` faz poll live.

---

## 4. Gate 3 — POST /frame

**Acao:** capturar JPEG e `POST /gateway/session/{id}/frame`.

**Curl:**

```bash
# Gerar JPEG minimo valido (ou usar foto real)
python3 -c "open('/tmp/frame0.jpg','wb').write(b'\xff\xd8\xff' + b'\x00'*200)"
SHA=$(sha256sum /tmp/frame0.jpg | cut -d' ' -f1)
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  -H "X-Capture-Id: cap-test-001" -H "X-Frame-Index: 0" -H "X-SHA256: $SHA" \
  -H "X-Resolution: 1280x720" -H "X-Received-Android-At: $(date -u +%Y-%m-%dT%H:%M:%SZ)" -H "X-Orientation: 0" \
  -F file=@/tmp/frame0.jpg $BASE/gateway/session/$SESSION/frame | jq .
# -> {"session_id":"...","capture_id":"cap-test-001","frame_index":0,"sha256":"...","storage_key":"sessions/.../frames/cap-test-001/0.jpg","duplicate":false}
```

**Esperado:** `200` `storage_key` preenchido, `duplicate=false` na primeira vez; `FakeStorageAdapter` ou `SupabaseStorageAdapter` com `overwrite=False`.

**Validacao sem ESP32:** `test_gate3_frame_upload_ok` chama `upload_frame` com `FakeStorageAdapter` + mock `AsyncSession`; `simulate_android.py --frames 10` envia 10 frames validos.

---

## 5. Gate 4 — Burst CAPTURE_FULL frames=3 + capture-complete

**Acao:** servidor solicita `CAPTURE_FULL frames=3 gap_ms=180`; Android envia 3 frames e `POST /capture-complete`.

**Curl:**

```bash
for i in 0 1 2; do
  python3 -c "import sys; open(f'/tmp/frame{i}.jpg','wb').write(b'\xff\xd8\xff'+bytes([10+$i])*100)"
  SHA=$(sha256sum /tmp/frame${i}.jpg | cut -d' ' -f1)
  curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
    -H "X-Capture-Id: cap-test-001" -H "X-Frame-Index: $i" -H "X-SHA256: $SHA" \
    -F file=@/tmp/frame${i}.jpg $BASE/gateway/session/$SESSION/frame | jq .
done
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  "$BASE/gateway/session/$SESSION/capture-complete?capture_id=cap-test-001&received_frames=3" | jq .
# -> {"capture_id":"cap-test-001","received_frames":3,"status":"complete"}
```

**Esperado:** 3 `POST /frame` `200`, depois `POST /capture-complete` `200` e `captures.received_frames=3`.

**Validacao sem ESP32:** `test_gate4_burst_3_frames` loopa 3 `upload_frame`; `android_only_e2e_check.py --run-live` faz burst 1+2 frames adicionais.

---

## 6. Gate 5 — POST /end-signal -> LOCKED

**Acao:** `POST /gateway/session/{id}/end-signal` (botao Encerrar).

**Curl:**

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  $BASE/gateway/session/$SESSION/end-signal | jq .
# -> {"session_id":"...","status":"LOCKED","locked":true}
# Idempotente:
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  $BASE/gateway/session/$SESSION/end-signal | jq .
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  "$BASE/gateway/session/$SESSION/command?cursor=999&phase=CAPTURE" | jq . # -> STOP
```

**Esperado:** `CAPTURING -> CAPTURE_END_CANDIDATE -> CAPTURE_LOCKING -> LOCKED` via `transition_session` + `mark_result_processing` (`RESULT_PROCESSING`). Repetir `POST` retorna mesma resposta `locked:true`; `GET /command` passa a retornar `STOP`.

**Validacao sem ESP32:** `test_gate5_*` via `TestClient` mockando `transition_session` e `mark_result_processing`.

---

## 7. Gate 6 — GATE_1 / GATE_2 (ou degradado) via debug/publish-rgb

**Acao:** Temporal `ProcessExamWorkflow`; quando offline, publicar manualmente.

**Curl debug (sem workflow):**

```bash
# Inserir Questions + FinalAnswers via UoW ou SQL, depois:
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  $BASE/gateway/session/$SESSION/debug/publish-rgb | jq .
# Completo -> {"command":"RGB_SEQUENCE_READY","sequence_id":"rgb-...","revision":1,"sha256":"...","reused":false}
# Incompleto -> {"command":"RESULT_CANCELLED","reason_code":"RGB_SEQUENCE_INCOMPLETE"}
```

**Esperado:** `GATE_2` aprovado publica `RgbSequence` imutavel `schema_version 1` (<256 KiB, `A-E`, `sha256` canonical `<BBBBBII`). `reused:true` se mesmo `answers` ja existe.

**Validacao sem ESP32:** `test_gate6_*` verifica `RgbPublicationResult`; `scripts/simulate_android.py` ja cobre validacao SHA e tamanho.

---

## 8. Gate 7 — GET /summary (painel)

**Acao:** `GET /gateway/session/{id}/summary`.

**Curl:**

```bash
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  $BASE/gateway/session/$SESSION/summary | jq .
# -> {"session_id":"...","status":"LOCKED","frames_count":3,"questions_count":5,
#     "answers":[{"question_number":1,"answer":"C","color":{"rgb":[0,255,255]}},...],
#     "delivery":{"command":"RESULT_PROCESSING","cursor":2},"rgb_sequence":null}
# Apos GATE_2: answers com A-E e cores; rgb_sequence com sha/payload_size
```

**Paleta (`RGB_RESULT_V1.md:31`):**

| A | B | C | D | E |
|---|---|---|---|---|
| 255,255,255 | 255,255,0 | 0,255,255 | 0,0,255 | 255,0,0 |
| branco | amarelo | ciano | azul | vermelho |

**Validacao sem ESP32:** `test_gate7_*` valida endpoint openapi e `DEFAULT_PALETTE`; painel `apps/admin` pode consumir mesmo JSON.

---

## 9. Gate 8 — Corte de internet durante frame 1/3 -> spool fila

**Acao:** desligar rede durante captura; frame deve ficar em spool local.

**Como validar sem ESP32 (unit):**

```bash
uv run pytest tests/unit/api/test_android_only_e2e.py::test_gate8_spool_queue_on_network_cut -v
# Simula: save f0 -> markAck (ok), save f1,f2 offline -> pending 2
# Requisitos Android Room: pending() WHERE ack=0, markAck+delete so apos 2xx, WorkManager KEEP
```

**Manual Android:** ativar modo aviao, capturar 2 paginas, verificar `Fila: 2 pendentes`, `adb shell run-as ... SELECT COUNT(*) FROM pending_frames WHERE ack=0`.

**Servidor:** nenhuma chamada `POST /frame` chega; `frames` count nao aumenta.

---

## 10. Gate 9 — Reabrir app com rede -> reenvio idempotente 200 nao 409

**Acao:** religar rede; `reenqueueAllPending()` reenvia mesmo `session_id+capture_id+frame_index+sha256`.

**Curl:**

```bash
SHA=$(sha256sum /tmp/frame0.jpg | cut -d' ' -f1)
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  -H "X-Capture-Id: cap-test-001" -H "X-Frame-Index: 0" -H "X-SHA256: $SHA" \
  -F file=@/tmp/frame0.jpg $BASE/gateway/session/$SESSION/frame | jq .duplicate
# -> true (200, nao duplica LogicalPage)
```

**Esperado:** `200` `duplicate:true`, `frames` count inalterado, `SpoolRepository.enqueueUpload` com `ExistingWorkPolicy.KEEP` nao duplica WorkManager.

**Validacao sem ESP32:** `test_gate9_idempotent_resend_200_not_409` (`upload_frame` mockado retorna `duplicate:true`) + `test_gate9_spool_reenqueue_idempotent`.

---

## 11. Gate 10 — Reenvio sha diferente -> 409 CONFLICT

**Acao:** mesmo `capture_id+frame_index` com `sha256` diferente.

**Curl:**

```bash
echo -n "different" > /tmp/frame0b.jpg
SHA2=$(sha256sum /tmp/frame0b.jpg | cut -d' ' -f1)
curl -s -w "\n%{http_code}\n" -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  -H "X-Capture-Id: cap-test-001" -H "X-Frame-Index: 0" -H "X-SHA256: $SHA2" \
  -F file=@/tmp/frame0b.jpg $BASE/gateway/session/$SESSION/frame
# -> 409 {"detail":"Frame index 0 already exists with different sha256"}
```

**Esperado:** `409` `reason_code=FRAME_DUPLICATE_CONFLICT`; Android deve criar novo `capture_id` e logar critico.

**Validacao sem ESP32:** `test_gate10_conflict_same_index_diff_sha_409`.

---

## 12. Gate 11 — Poll RGB + duplicate COMPLETED

**Acao:** `GET /result?cursor=old` -> `GET /rgb-sequence` -> `POST /rgb-sequence/event COMPLETED` repetido.

**Curl:**

```bash
curl -i -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  "$BASE/gateway/session/$SESSION/result?device_id=$DEV&cursor=0"
# -> 200 {"command":"RESULT_PROCESSING","cursor":2} ou 200 {"command":"RGB_SEQUENCE_READY","cursor":3,"sequence_id":"rgb-...","sha256":"..."}
CURSOR=$(curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" "$BASE/gateway/session/$SESSION/result?device_id=$DEV&cursor=0" | jq -r .cursor)
curl -i -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  "$BASE/gateway/session/$SESSION/result?device_id=$DEV&cursor=$CURSOR" # -> 204

SEQ=$(curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" "$BASE/gateway/session/$SESSION/result?device_id=$DEV&cursor=0" | jq -r .sequence_id)
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  "$BASE/gateway/session/$SESSION/rgb-sequence?device_id=$DEV&sequence_id=$SEQ" | jq . > /tmp/rgb.json
python3 -c "
import json,hashlib,struct
p=json.load(open('/tmp/rgb.json'))
pal=p['palette']; d=p['defaults']; ov={o['index']:o for o in p.get('overrides',[])}
raw=b''.join(struct.pack('<BBBBBII',ord(a),ov.get(i,{}).get('rgb',pal[a]['rgb'])[0],ov.get(i,{}).get('rgb',pal[a]['rgb'])[1],ov.get(i,{}).get('rgb',pal[a]['rgb'])[2],ov.get(i,{}).get('brightness_percent',d['brightness_percent']),ov.get(i,{}).get('on_ms',d['on_ms']),ov.get(i,{}).get('off_ms',d['off_ms'])) for i,a in enumerate(p['answers']))
assert p['sha256']==hashlib.sha256(raw).hexdigest()
print('SHA ok', p['sha256'], len(raw))
"
for EVT in RECEIVED STARTED COMPLETED; do NEXT=0; [ "$EVT" = "COMPLETED" ] && NEXT=$(jq -r .item_count /tmp/rgb.json); curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" -H "Idempotency-Key: chk-$EVT-$NEXT" -H "Content-Type: application/json" -d "{\"device_id\":\"$DEV\",\"session_id\":\"$SESSION\",\"sequence_id\":\"$SEQ\",\"revision\":1,\"event\":\"$EVT\",\"next_index\":$NEXT,\"item_count\":$(jq -r .item_count /tmp/rgb.json)}" $BASE/gateway/session/$SESSION/rgb-sequence/event | jq .; done
# Repetir COMPLETED -> duplicate:true
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" -H "Idempotency-Key: chk-COMPLETED-$(jq -r .item_count /tmp/rgb.json)" -H "Content-Type: application/json" -d "{\"device_id\":\"$DEV\",\"session_id\":\"$SESSION\",\"sequence_id\":\"$SEQ\",\"revision\":1,\"event\":\"COMPLETED\",\"next_index\":$(jq -r .item_count /tmp/rgb.json),\"item_count\":$(jq -r .item_count /tmp/rgb.json)}" $BASE/gateway/session/$SESSION/rgb-sequence/event | jq .duplicate
# -> true
```

**Esperado:** segundo `COMPLETED` `200` `{"duplicate":true}`; `Idempotency-Key` reutilizado com payload diferente -> `409`.

**Validacao sem ESP32:** `test_gate11_*` via `TestClient` mockando `record_rgb_event` (`delivery.py:397`).

---

## 13. Scripts e comandos de validacao

```bash
# Lint (All checks passed para arquivos novos; legado pode ter 20 S105 nao criticos)
uv run ruff check scripts/android_only_e2e_check.py tests/unit/api/test_android_only_e2e.py
uv run ruff check src/ apps/ tests/  # 20 restantes sao S105/B017 legados, nao bloqueadores

# Testes unitarios (361 = 336 + 25 novos Etapa 7)
uv run pytest tests/unit -q
uv run pytest tests/unit/api/test_android_only_e2e.py -v

# Checklist curl automatizado (sem servidor -> so imprime curls)
uv run python scripts/android_only_e2e_check.py --print-curl

# Checklist live contra servidor local
uv run python scripts/android_only_e2e_check.py --run-live --url http://localhost:8000/api/v1 --gateway-token dev-gateway-token

# Simulador legado (equivalente E2E completo)
uv run python scripts/simulate_android.py --frames 10
uv run python scripts/simulate_android.py --frames 5 --duplicate-rate 0.3
uv run python scripts/simulate_android.py --rgb-session-id S-abc123 --rgb-mode normal
uv run python scripts/simulate_android.py --rgb-session-id S-abc123 --rgb-mode invalid-hash  # deve rejeitar
```

Android local (quando APK disponivel):

```bash
./gradlew test
./gradlew connectedAndroidTest
adb logcat | grep -E "Spool|UploadWorker|Gateway"
```

---

## 14. Estado atual dos 11 gates

| Gate | Arquivo de teste | Script | Estado |
|---|---|---|---|
| 1 | `tests/unit/api/test_android_only_e2e.py::test_gate1_*` | `android_only_e2e_check.py::run_live` gate1 | OK (openapi + TestClient mock) |
| 2 | `test_gateway_command.py` + `test_gate2_*` | gate2 curl `phase` | OK (PING/CAPTURE_*) |
| 3 | `test_gate3_frame_upload_ok` | gate3 curl `X-SHA256` | OK (FakeStorage) |
| 4 | `test_gate4_burst_3_frames` | gate4 loop 3 | OK |
| 5 | `test_gate5_*` | gate5 `POST /end-signal` | OK (mock transition) |
| 6 | `test_gate6_*` + `debug/publish-rgb` | gate6 `debug/publish-rgb` | OK (simulado) |
| 7 | `test_gate7_*` | gate7 `GET /summary` | OK (palette A-E) |
| 8 | `test_gate8_spool_*` InMemorySpool | gate8 doc spool | OK (reenqueue) |
| 9 | `test_gate9_*` idempotent | gate9 curl `duplicate:true` | OK |
| 10 | `test_gate10_*` 409 | gate10 curl `409` | OK |
| 11 | `test_gate11_*` duplicate COMPLETED | gate11 `GET /result` `GET /rgb-sequence` `POST /event` | OK (`duplicate:true`) |

**Resultado `uv run pytest tests/unit -q`:** `361 passed, 1 warning` (336 legados + 25 novos).

**Resumo painel:** `GET /gateway/session/{id}/summary` e `GET /result` (204/200) + `GET /rgb-sequence` + `POST /rgb-sequence/event` sao testaveis via `curl` e `TestClient` sem ESP32; spool offline e idempotencia sao unit-testados via `InMemorySpool` + `FakeStorageAdapter`.

---

## 15. Referencias

- `docs/PLANO_ANDROID_ONLY.md:314`
- `docs/FLUXO_SPOOL_UPLOAD_ETAPA4.md`
- `docs/ETAPA_5_POLLING.md`
- `docs/FLUXO_ENCERRAMENTO_PAINEL_ETAPA6.md`
- `docs/contracts/RGB_RESULT_V1.md`
- `src/pages_to_audio/capture/frame_upload.py:96`
- `src/pages_to_audio/rgb/delivery.py:397`
- `src/pages_to_audio/rgb/canonical.py:68` (`<BBBBBII`, 13 bytes/item)
- `scripts/simulate_android.py:175` (poll + SHA + COMPLETED duplicate)
