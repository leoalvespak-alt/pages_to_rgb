# Fluxo de Encerramento e Painel de Respostas — Etapa 6 (Android Gateway)

**Versão:** V1 — 31/08/2026  
**Fontes:** `docs/PLANO_ANDROID_ONLY.md:284` Etapa 6, `apps/api/routers/gateway.py:446` (`POST /end-signal`), `apps/api/routers/gateway_rgb.py:62` (`GET /result`, `GET /rgb-sequence`, `POST /rgb-sequence/event`), `src/pages_to_audio/rgb/delivery.py:93`, `src/pages_to_audio/rgb/canonical.py:68`, `src/pages_to_audio/rgb/publisher.py:91`, `docs/contracts/RGB_RESULT_V1.md:1`, `src/pages_to_audio/domain/state_machine.py:18`

---

## 1. Visão do fluxo

```
Android: captura em CAPTURING  ──►  [ Encerrar ]  ──► POST /gateway/session/{id}/end-signal
                                          │
                    ┌─────────────────────┘
                    ▼
Servidor: CAPTURING ─► CAPTURE_END_CANDIDATE ─► CAPTURE_LOCKING ─► LOCKED
            (via transition_session + AuditEvent, `src/pages_to_audio/domain/state_machine.py:184`)
                    │
                    ├─► marca RESULT_PROCESSING em session_result_deliveries
                    │   (amarelo contínuo 2s no painel — `src/pages_to_audio/rgb/delivery.py:247`)
                    └─► tenta iniciar ProcessExamWorkflow (Temporal)
                          se TEMPORAL_ADDRESS vazio: só loga warning, painel ainda
                          pode publicar RGB manualmente (simulate_android / debug)
                    │
                    ▼
         Workflow (se online): IMAGE_PROCESSING → ... → GATE_1 → GATE_2
                    │
          ┌─────────┴───────────────────────┐
          ▼                                 ▼
  GATE_2 aprovado              GATE_2/GATE_1 bloqueado ou incompleto
  publish_rgb_for_session      publish_rgb_for_session → RESULT_CANCELLED
          │                                 │ (motivo: RGB_SEQUENCE_INCOMPLETE, etc.)
          ▼                                 ▼
  RGB_SEQUENCE_READY              RESULT_CANCELLED (vermelho)
  + RgbSequence (A-E)             sem RgbSequence deliverable
          │                                 │
          └───────────┬─────────────────────┘
                      ▼
              GET /result?cursor= (poll 204/200)
              GET /rgb-sequence?sequence_id=
              POST /rgb-sequence/event (COMPLETED idempotente)
```

Compatibilidade: a mesma `RgbSequence` (`src/pages_to_audio/db/models/rgb_sequence.py:1`) e `SessionResultDelivery` (`src/pages_to_audio/db/models/session_result_delivery.py:1`) que o painel lê hoje será lida pelo firmware V2.2 — **não mudar formato**. `docs/contracts/RGB_RESULT_V1.md:1` é a fonte da verdade.

---

## 2. Encerramento — `POST /gateway/session/{id}/end-signal`

**Arquivo:** `apps/api/routers/gateway.py:446`

- **Binding:** `session.public_id == {id}` + `AndroidGateway.gateway_code == gateway_id` (token `Authorization: Bearer <ANDROID_GATEWAY_TOKEN>`). Se sessão não existe → `404`. Device desabilitado → `403`.
- **Idempotência:**
  - `SessionState.is_terminal` (`COMPLETED`/`FAILED_FATAL`/`CANCELLED`) → `200 {"already_terminal": true}`.
  - `LOCKED` → `200 {"locked": true}` **e ainda garante delivery** `RESULT_PROCESSING`/`RGB_SEQUENCE_READY` via `mark_result_processing` (`src/pages_to_audio/rgb/delivery.py:247`) — protege cenário onde lock anterior succeeded mas delivery não foi criado (crash antes do flush).
- **Transições (sempre via `transition_session` — `src/pages_to_audio/domain/state_machine.py:184`):**
  ```
  CAPTURING → CAPTURE_END_CANDIDATE (payload {"end_signal":"manual"}, actor GATEWAY)
  CAPTURE_END_CANDIDATE → CAPTURE_LOCKING
  CAPTURE_LOCKING: set capture_locked_at = now(UTC) + flush → LOCKED
  ```
  Cada `transition_session` valida `ALLOWED_TRANSITIONS` (`state_machine.py:18`), grava `AuditEvent` (`STATE_TRANSITION`, `actor_type=gateway`, `stage=SYSTEM`), e faz `SELECT ... FOR UPDATE` anti-race. Transição inválida → `409 InvalidStateTransition` + `AuditEvent INVALID_TRANSITION`.
- **Após LOCKED (Etapa 6 — novo):**
  1. **Marca `RESULT_PROCESSING`** em `session_result_deliveries` via `mark_result_processing` (`delivery.py:247`). Guard: se já `RGB_SEQUENCE_READY`, não sobrescreve (evita downgrade). `cursor` monotônico + `AuditEvent RGB_RESULT_STATUS_CHANGED`.
  2. **Tenta iniciar `ProcessExamWorkflow`** via `TemporalWorkflowStarter.start_process_exam` (`src/pages_to_audio/workflows/starter.py:36`) se `settings.TEMPORAL_ADDRESS` não vazio. Falha é `warning` (Temporal offline) — não desfaz `LOCKED`. Para Android-Only sem Temporal, o painel pode publicar RGB manualmente (ver §5).

> Nota contrato: este endpoint é o `STOP` lógico do app. No firmware V2.2 o botão físico equivalente dispara `STOP` via `/v1/device/command`; aqui o app chama `POST /end-signal` após `spool.awaitDrain()` e `CommandPollWorker` receber `STOP` por `GET /command`.

---

## 3. Resultado RGB — `GET /result`, `GET /rgb-sequence`, `POST /rgb-sequence/event`

**Arquivo:** `apps/api/routers/gateway_rgb.py:1`

### 3.1 `GET /gateway/session/{id}/result?device_id=&cursor=`

- Resolve `SessionBinding` (`src/pages_to_audio/rgb/delivery.py:111`): tripla `session.public_id + device.device_code + gateway.gateway_code`. Se desalinhado → `403/404`.
- `result_snapshot` (`delivery.py:267`): se `cursor >= delivery.cursor` → `204 No Content` (sem update). Senão retorna `ResultPollResponse` (`command`, `cursor`, `session_id`, e, se `RGB_SEQUENCE_READY`, `sequence_id`, `revision`, `item_count`, `sha256`).
- **Mapeamento de estados** (`delivery.py:93` `derive_command`):
  - `CREATED/CAPTURING/CAPTURE_END_CANDIDATE/CAPTURE_LOCKING/LOCKED` sem `processing_started_at` → `RESULT_NOT_STARTED` (cursor 1 mesmo sem delivery row — stub para painel antes de `end-signal`).
  - `LOCKED` + delivery `RESULT_PROCESSING` → `RESULT_PROCESSING` (amarelo — painel deve exibir “processando”).
  - `IMAGE_PROCESSING … GATE_2 … FAILED_RECOVERABLE` → `RESULT_PROCESSING`.
  - `BLOCKED_GATE_1 / BLOCKED_GATE_2 / FAILED_FATAL / CANCELLED / READY / COMPLETED` → `RESULT_CANCELLED` (vermelho/sem sequência).
  - `RGB_SEQUENCE_READY` + `active_sequence_id` válido → `RGB_SEQUENCE_READY` com metadados.

### 3.2 `GET /gateway/session/{id}/rgb-sequence?device_id=&sequence_id=`

- Revalida `SessionBinding`, busca `RgbSequence` por `session_id + sequence_id` (`delivery.py:354`). Se status `INVALID/SUPERSEDED` → `410`.
- `sequence_payload` (`delivery.py:322`): reidrata `RgbSequencePayload` (`src/pages_to_audio/rgb/schemas.py:103`), chama `validate_payload_sha256` (`canonical.py:92`), serializa `compact_json_bytes` (`canonical.py:100`) e verifica `<= 262144` bytes (`RGB_SEQUENCE_MAX_JSON_BYTES`).

### 3.3 `POST /gateway/session/{id}/rgb-sequence/event`

- Body `RgbSequenceEventRequest` (`gateway_rgb.py:41`): `device_id`, `session_id`, `sequence_id`, `revision`, `event` (`RECEIVED/STARTED/RESUMED/COMPLETED/INVALID`), `next_index`, `item_count`, header opcional `Idempotency-Key`.
- `record_rgb_event` (`delivery.py:397`) sob `SELECT ... FOR UPDATE` na `RgbSequence`:
  - Valida `session_id` da rota == body, `item_count == sequence.item_count`, `0 <= next_index <= item_count`, `event_identity` (`{device.id}:{sequence.id}:{revision}:{event}:{next_index}` exceto `COMPLETED` sem sufixo).
  - Idempotência por `Idempotency-Key` (gateway escopo) e por `event_identity` (mesmo payload → `duplicate:true`).
  - `RECEIVED` só válido se status `READY`; `COMPLETED` exige `next_index == item_count`; regressão `next_index < last_next_index` → `409`; `COMPLETED` repetido → `200 duplicate:true` (`delivery.py:397` — exigido `PLANO_ANDROID_ONLY.md:331` gate 11).
  - Atualiza `last_next_index`, transita `READY→RECEIVED→PLAYING→COMPLETED`, grava `RgbSequenceEvent` + `AuditEvent` (`RGB_SEQUENCE_EVENT_RECEIVED` ou `RGB_SEQUENCE_INVALID`).

> Android após `STOP` deve fazer `RESULT_POLL` com `cursor` incremental (simulador `scripts/simulate_android.py:175` o faz); `204` significa “sem novo comando” — não é erro.

---

## 4. Painel — `GET /gateway/session/{id}/summary`

**Arquivo:** `apps/api/routers/gateway.py:562`

`apps/admin` hoje é apenas stub React (`apps/admin/src/.gitkeep`). Para Android-Only o painel lê **o mesmo** `RgbSequence` + `SessionResultDelivery` que o firmware lerá, via:

- **Novo endpoint painel:** `GET /gateway/session/{id}/summary` (autenticado com `Authorization: Bearer <ANDROID_GATEWAY_TOKEN>` — mesmo token do gateway; em produção trocar por `SessionCookie` admin).
- **Resposta (JSON):**
  ```json
  {
    "session_id": "S-abc123",
    "status": "LOCKED",
    "expected_pages": 30,
    "expected_questions": 70,
    "minimum_ratio": 0.90,
    "capture_source": "ANDROID_CAMERA",
    "created_at": "2026-08-31T...",
    "capture_locked_at": "2026-08-31T14:02:00Z",
    "processing_started_at": null,
    "device_code": "CAM-001",
    "gateway_code": "GW-ANDROID-001",
    "frames_count": 12,
    "questions_count": 10,
    "answers": [
      {"question_number":1, "status":"SOLVED", "answer":"C", "validated":true, "color":{"rgb":[0,255,255],"letter":"C"}},
      {"question_number":2, "status":"SOLVED", "answer":"E", "validated":true, "color":{"rgb":[255,0,0],"letter":"E"}}
    ],
    "delivery": {"command":"RESULT_PROCESSING","cursor":2,"reason_code":null,"active_sequence_id":null},
    "rgb_sequence": null
  }
  ```
  Quando `RGB_SEQUENCE_READY`, `rgb_sequence` contém `sequence_id`, `revision`, `status`, `answers`, `item_count`, `sha256`, `payload_size`; `delivery.command == "RGB_SEQUENCE_READY"` e `answers` já mapeadas para cores (`DEFAULT_PALETTE` — `src/pages_to_audio/rgb/policy.py:15`).
- **Alternativa documentada:** se o painel preferir, pode usar `GET /gateway/session/{id}/result` + `GET /gateway/session/{id}/rgb-sequence` + `FinalAnswer` diretamente; o mínimo Android-Only é que a sessão `LOCKED` dispare `ProcessExamWorkflow` **ou** marque `RESULT_PROCESSING` e que o resultado RGB possa ser publicado manualmente via `simulate_android.py` (`scripts/simulate_android.py:175`) ou via endpoint de debug.

### 4.1 Paleta padrão (`RGB_RESULT_V1.md:31` / `policy.py:15`)

| Letra | RGB | Cor visível |
|-------|-----|-------------|
| A | `[255,255,255]` | branco |
| B | `[255,255,0]`   | amarelo |
| C | `[0,255,255]`   | ciano |
| D | `[0,0,255]`     | azul |
| E | `[255,0,0]`     | vermelho |

`defaults`: `brightness_percent=12`, `on_ms=3000`, `off_ms=5000` (`src/pages_to_audio/config/settings.py:133`).

---

## 5. Compatibilidade firmware V2.2 — formato imutável

- **Schema:** `schema_version: 1` (`src/pages_to_audio/rgb/schemas.py:108` — literal 1).
- **Paleta/defaults:** acima; `overrides` esparsos por índice (0-999) quando necessário.
- **Wire JSON:** compacto `json.dumps(separators=(",",":"))` (`canonical.py:100`), `Content-Type: application/json`, tamanho `< 256 KiB` (`RGB_SEQUENCE_MAX_JSON_BYTES`).
- **SHA canônico:** `hashlib.sha256(canonical_items_bytes(payload)).hexdigest()` (`canonical.py:86`). `canonical_items_bytes` (`canonical.py:68`) empacota **exatamente 13 bytes por item**:
  ```python
  struct.pack("<BBBBBII", ord(answer), r, g, b, brightness_percent, on_ms, off_ms)
  ```
  Ordem dos campos é normativa; `on_ms`/`off_ms` little-endian. Vetores dourados (`tests/unit/rgb/test_canonical.py:30`):
  - `"A"` → `41ffffff0cb80b000088130000` (hex dos 13 bytes) → SHA `8a2b2c9188f7e8be635244c53d5b4aad52c595407ef35f7e96b2471a310ad893`
  - `"ABCDE"` → SHA `6f2f655b4ea2ee02ee009a938cc95515f6ff38309b3b2ddcb0594057a5151f17` (`RGB_RESULT_V1.md:66`)
- **Restrições firmware:** `item_count` 1–1000, `answers` só `A-E` (`answers ~ '^[A-E]+$'`), `length(answers)==item_count`, `payload_size == item_count * 13` (`migrations/versions/0003_rgb_result_delivery.py:78`).

> Não alterar nenhum campo, ordem, tamanho ou packing sem bump de `contract_version` (`gateway.py:81` hoje `2.2`) e atualização do firmware (`main/gateway_client.c:257`, `main/app_main.c:613`).

---

## 6. Validação via `curl` (sem APK)

O servidor assume `ANDROID_GATEWAY_TOKEN` setado no `.env` e `DATABASE_URL` acessível. Base padrão `http://localhost:8000/api/v1`.

```bash
export BASE=http://localhost:8000/api/v1
export TOKEN="dev-gateway-token"   # ou valor de ANDROID_GATEWAY_TOKEN
export GW="GW-ANDROID-001"
export DEV="CAM-001"

# 0) Hello (opcional, mas atualiza last_seen + capabilities)
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  -H "Content-Type: application/json" \
  -d '{"app_version":"curl-1.0","device_model":"curl","gateway_code":"'"$GW"'"}' \
  $BASE/gateway/hello | jq .

# 1) Iniciar sessão (Android)
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  -H "Content-Type: application/json" \
  -d '{"device_code":"'"$DEV"'","capture_source":"ANDROID_CAMERA","allow_new_session":true,"expected_pages":5,"expected_questions":5}' \
  $BASE/gateway/session/start | jq .
export SESSION=S-...  # copiar session_id da resposta

# 2) Enviar 3 frames (burst CAPTURE_FULL files=3 gap 180ms)
for i in 0 1 2; do
  echo -n "fake-jpeg-$i-$(date +%s)" > /tmp/frame${i}.jpg
  SHA=$(sha256sum /tmp/frame${i}.jpg | cut -d' ' -f1)
  curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
    -H "X-Capture-Id: cap-test-001" -H "X-Frame-Index: $i" -H "X-SHA256: $SHA" \
    -H "X-Resolution: 1280x720" -H "X-Orientation: 0" \
    -F file=@/tmp/frame${i}.jpg | jq .
done

# Reenvio idempotente (mesmo capture_id+frame_index+sha) → 200 duplicate:true
SHA0=$(sha256sum /tmp/frame0.jpg | cut -d' ' -f1)
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  -H "X-Capture-Id: cap-test-001" -H "X-Frame-Index: 0" -H "X-SHA256: $SHA0" \
  -F file=@/tmp/frame0.jpg | jq .duplicate  # → true

# Conflito (mesmo índice, sha diferente) → 409
echo -n "different" > /tmp/frame0b.jpg
SHA0B=$(sha256sum /tmp/frame0b.jpg | cut -d' ' -f1)
curl -s -w "\n%{http_code}\n" -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  -H "X-Capture-Id: cap-test-001" -H "X-Frame-Index: 0" -H "X-SHA256: $SHA0B" \
  -F file=@/tmp/frame0b.jpg  # → 409

# (opcional) fechar burst
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  "$BASE/gateway/session/$SESSION/capture-complete?capture_id=cap-test-001&received_frames=3" | jq .

# 3) Encerrar captura (botão Encerrar do app)
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  -X POST $BASE/gateway/session/$SESSION/end-signal | jq .
# → {"session_id":"S-...","status":"LOCKED","locked":true}
# Re-call idempotente → mesma resposta, delivery permanece PROCESSING/READY
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  -X POST $BASE/gateway/session/$SESSION/end-signal | jq .

# 4) Painel — summary (substitui GET /sessions/{id} antigo)
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  $BASE/gateway/session/$SESSION/summary | jq .

# 5) Poll de resultado (Android RESULT_POLL — curva STOP → PROCESSING → READY/CANCELLED)
#   Antes de GATE_2: RESULT_PROCESSING ou RESULT_NOT_STARTED
curl -i -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  "$BASE/gateway/session/$SESSION/result?device_id=$DEV&cursor=0"
# → 200 {"command":"RESULT_PROCESSING","cursor":2,...}
#   Cursor incremental: segundo poll com cursor atual → 204
CURSOR=$(curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  "$BASE/gateway/session/$SESSION/result?device_id=$DEV&cursor=0" | jq -r .cursor)
curl -i -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  "$BASE/gateway/session/$SESSION/result?device_id=$DEV&cursor=$CURSOR"  # → 204

# 6) Quando workflow publicar RGB (GATE_2 aprovado), o poll retorna READY
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  "$BASE/gateway/session/$SESSION/result?device_id=$DEV&cursor=$CURSOR" | jq .
# → {"command":"RGB_SEQUENCE_READY","cursor":3,"sequence_id":"rgb-...","revision":1,"item_count":5,"sha256":"6f2f..."}
export SEQUENCE_ID=$(curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  "$BASE/gateway/session/$SESSION/result?device_id=$DEV&cursor=$CURSOR" | jq -r .sequence_id)

# 7) Baixar sequência e validar SHA canônico
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  "$BASE/gateway/session/$SESSION/rgb-sequence?device_id=$DEV&sequence_id=$SEQUENCE_ID" | jq . > /tmp/rgb.json
# Validar localmente (mesmo packing que firmware)
python3 -c "
import json, hashlib, struct
p=json.load(open('/tmp/rgb.json'))
palette=p['palette']; defaults=p['defaults']
overrides={o['index']:o for o in p.get('overrides',[])}
raw=b''.join(struct.pack('<BBBBBII',
  ord(a),
  overrides.get(i,{}).get('rgb', palette[a]['rgb'])[0],
  overrides.get(i,{}).get('rgb', palette[a]['rgb'])[1],
  overrides.get(i,{}).get('rgb', palette[a]['rgb'])[2],
  overrides.get(i,{}).get('brightness_percent', defaults['brightness_percent']),
  overrides.get(i,{}).get('on_ms', defaults['on_ms']),
  overrides.get(i,{}).get('off_ms', defaults['off_ms'])
) for i,a in enumerate(p['answers']))
assert p['item_count']==len(p['answers'])
assert len(json.dumps(p, separators=(',',':')).encode()) < 262144
assert p['sha256']==hashlib.sha256(raw).hexdigest(), 'SHA mismatch'
print('SHA ok', p['sha256'], 'bytes', len(raw))
"

# 8) Eventos (COMPLETED idempotente)
for EVT in RECEIVED STARTED COMPLETED; do
  NEXT=0; [ "$EVT" = "COMPLETED" ] && NEXT=$(jq -r .item_count /tmp/rgb.json)
  curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
    -H "Idempotency-Key: curl-$EVT-$NEXT" \
    -H "Content-Type: application/json" \
    -d '{"device_id":"'"$DEV"'","session_id":"'"$SESSION"'","sequence_id":"'"$SEQUENCE_ID"'","revision":1,"event":"'"$EVT"'","next_index":'"$NEXT"',"item_count":'$(jq -r .item_count /tmp/rgb.json)'}' \
    $BASE/gateway/session/$SESSION/rgb-sequence/event | jq .
done
# Segundo COMPLETED igual → duplicate:true (gate 11 do PLANO_ANDROID_ONLY)
curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  -H "Idempotency-Key: curl-COMPLETED-$(jq -r .item_count /tmp/rgb.json)" \
  -H "Content-Type: application/json" \
  -d '{"device_id":"'"$DEV"'","session_id":"'"$SESSION"'","sequence_id":"'"$SEQUENCE_ID"'","revision":1,"event":"COMPLETED","next_index":'$(jq -r .item_count /tmp/rgb.json)',"item_count":'$(jq -r .item_count /tmp/rgb.json)'}' \
  $BASE/gateway/session/$SESSION/rgb-sequence/event | jq .duplicate  # → true
```

---

## 7. Validação via `simulate_android.py`

`scripts/simulate_android.py:1` cobre upload + polling RGB sem APK/hardware.

```bash
# Frame upload + idempotência (Etapa 4)
uv run python scripts/simulate_android.py --frames 10
uv run python scripts/simulate_android.py --frames 5 --duplicate-rate 0.3
# → accepted + duplicate_idempotent sem conflitos

# RGB E2E — precisa de uma sessão com FinalAnswers válidas:
# Opção A: deixar ProcessExamWorkflow rodar (requer Temporal + fakes + Questions/FinalAnswers)
# Opção B: publicar manualmente via publisher (sem workflow):
#   Em um shell Python com DATABASE_URL setado:
#     from src.pages_to_audio.rgb.publisher import publish_rgb_for_session
#     async with UnitOfWork() as uow:
#         # Inserir Question(1..expected_questions) + FinalAnswer(validated=true, answer in A-E)
#         # depois:
#         await publish_rgb_for_session(uow.session, session_public_id="S-abc123")
#         await uow.commit()
# Opção C: endpoint debug (sem Python shell) — requer sessão LOCKED + Questions/FinalAnswers já inseridas:
#   curl -s -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
#     -X POST $BASE/gateway/session/$SESSION/debug/publish-rgb | jq .
#   # → {"command":"RGB_SEQUENCE_READY","sequence_id":"rgb-...","revision":1,"sha256":"...","reused":false}
#   # Se conjunto incompleto → {"command":"RESULT_CANCELLED","reason_code":"RGB_SEQUENCE_INCOMPLETE"}

# Após publicar (ou após workflow), exercitar polling + download + SHA + eventos:
uv run python scripts/simulate_android.py --rgb-session-id S-abc123 --rgb-device-id CAM-001 --rgb-mode normal
# → poll PROCESSING/RGB_SEQUENCE_READY, valida SHA (< 256 KiB, A-E, item_count), RECEIVED→STARTED→COMPLETED (2x COMPLETED duplicate:true)

# Cenários negativos (devem rejeitar):
uv run python scripts/simulate_android.py --rgb-session-id S-abc123 --rgb-mode invalid-hash        # rejeita SHA
uv run python scripts/simulate_android.py --rgb-session-id S-abc123 --rgb-mode invalid-item-count # rejeita
uv run python scripts/simulate_android.py --rgb-session-id S-abc123 --rgb-mode invalid-event       # rejeita INVALID
uv run python scripts/simulate_android.py --rgb-session-id S-abc123 --rgb-mode unlinked-gateway    # 403/404
uv run python scripts/simulate_android.py --rgb-session-id S-abc123 --rgb-mode network-failure     # timeout sem sleep

# Via curl + python: mesmo fluxo acima, mas com SessionViewModel/fetchCommand separado:
# GET /command?cursor=&wait_ms=&phase= demonstra STOP após end-signal:
curl -H "Authorization: Bearer $TOKEN" -H "X-Gateway-Id: $GW" \
  "$BASE/gateway/session/$SESSION/command?cursor=0&wait_ms=25000&phase=CAPTURE" | jq .
# CAPTURING → CAPTURE_FULL/PROBE/PING; após POST /end-signal → STOP (gateway.py:376)
```

**Critério de saída da Etapa 6 (cf. `PLANO_ANDROID_ONLY.md:306`):**

- [ ] `POST /end-signal` evolui `CAPTURING → CAPTURE_END_CANDIDATE → CAPTURE_LOCKING → LOCKED` com `AuditEvent` (`transition_session`) e marca `RESULT_PROCESSING` (cursor bump).
- [ ] `GET /result?cursor=0` retorna `RESULT_PROCESSING` após LOCKED; `GET /result?cursor=<atual>` retorna `204`.
- [ ] Após `GATE_2` aprovado (ou `publish_rgb_for_session` manual), `GET /result` retorna `RGB_SEQUENCE_READY` (ou `RESULT_CANCELLED` se incompleto), `GET /rgb-sequence` retorna JSON `< 256 KiB`, `answers` só `A-E`, `sha256` bate com `canonical.py:68`.
- [ ] Painel `GET /summary` exibe `Q1→C (ciano)`, `Q2→E (vermelho)` etc. (paleta `RGB_RESULT_V1.md:31`).
- [ ] `POST /rgb-sequence/event COMPLETED` repetido → `200 duplicate:true` (idempotente, `delivery.py:397`).

---

## 8. Comandos de qualidade

```bash
# Lint (limpo após Etapa 6 — ver §7 report)
uv run ruff check apps/api/routers/gateway.py
uv run ruff check

# Tipos (pre-existentes em settings/db models; rgb/ limpo)
uv run mypy src/pages_to_audio/rgb --show-error-codes  # 33 erros pré-existentes em config/settings e db/models, 0 em rgb/*

# Testes — vetores dourados + idempotência + cursor monotônico
uv run pytest tests/unit/rgb -q  # 20 passed (canonical 8a2b…/6f2f…, policy, schemas, delivery)
uv run pytest tests/unit/api/test_gateway_rgb_contract.py -q  # 3 passed
```

---

## 9. Arquivos tocados nesta Etapa

- `apps/api/routers/gateway.py:446` — `POST /end-signal` agora transita via `transition_session` + marca `RESULT_PROCESSING` (`mark_result_processing`) + tenta `TemporalWorkflowStarter`; idempotente se `LOCKED`; novo `GET /session/{id}/summary` para painel (frames, answers+cor, delivery, rgb_sequence); novo `POST /session/{id}/debug/publish-rgb` para publicação manual sem Temporal (usa `publish_rgb_for_session`).
- `apps/api/routers/gateway_rgb.py:62` — já correto (204 handling, `RECEIVED/STARTED/COMPLETED` idempotente); apenas documentado.
- `src/pages_to_audio/rgb/delivery.py:93` / `publisher.py:91` / `canonical.py:68` — **não alterado** (compatibilidade V2.2 garantida: `"<BBBBBII"` + paleta defaults).
- `docs/FLUXO_ENCERRAMENTO_PAINEL_ETAPA6.md` — este arquivo.
- `scripts/simulate_android.py:175` — já cobre `RESULT_POLL → download → SHA → COMPLETED duplicate:true`; usado para validação sem firmware; publish manual alternativo via `POST /debug/publish-rgb`.

---

## 10. O que NÃO fazer (reafirmação V2.2)

- Não mudar `schema_version`, ordem dos 13 bytes, `palette`, ou ordenação `compact_json_bytes` sem bump `contract_version` e atualização `main/gateway_client.c`.
- Não fazer `GET /result` retornar `200` quando `cursor >= delivery.cursor` — deve ser `204` (`gateway_rgb.py:85`).
- Não armazenar JPEG permanente na VPS (`CLAUDE.md:17`); só Supabase `pages-originals` + TTL.
- Não criar fallback silencioso se Temporal/Supabase cair — propagar erro e deixar `RESULT_PROCESSING` visível até retry manual.

