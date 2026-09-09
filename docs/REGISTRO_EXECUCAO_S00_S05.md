# Registro de execução S00-S05 — 09/09/2026

Referência auditada: branch `main`, HEAD `a6b2deaad3493d6ff4f5821008a2ead93ca20d33`,
remote `https://github.com/leoalvespak-alt/pages_to_rgb.git` (confirmado antes das edições;
`git status` mostrava apenas os 3 docs de planejamento/auditoria como novos + 1 modificado).

## S00 — baseline e ambiente real

- Python de execução dos testes: WSL `/home/deploy/pages_to_audio_server_venv/bin/python` (3.14 —
  registrado como divergência do container 3.12; validação 3.12 pendente no build Docker).
- Python Windows local: 3.13/3.14 (sem pytest); `.venv` do repo é symlink WSL (Python 3.13 linux).
- Node Windows: v24.16.0. JDK/SDK Android e Docker: indisponíveis neste ambiente
  (sem `java`, sem `docker`) — builds APK/imagem NÃO validados aqui.
- Credenciais: apenas nomes/localização inventariados (`.env.example`, `AppSettings`,
  `ADMIN_SETTINGS_ENCRYPTION_KEY`, `ANDROID_GATEWAY_TOKEN[_PREVIOUS]`, `DEVICE_HMAC_MASTER_KEY`,
  `R2_*`, `SUPABASE_*`, `TEMPORAL_*`, GOOGLE_*); nenhum valor impresso.
- Banco/storage/Temporal de produção: não tocados; nenhuma indisponibilidade nova medida
  (baseline de latência/filas/CPU fica para ambiente com serviços reais — S10).
- IDs de validação desta execução: sessão de teste `abc123hex123456` (mocks), gateway
  `GW-TEST-001`. Evidências: `tests/unit` 411 passed + 1 skipped (prod-only).

## O que foi implementado por etapa

| Etapa | Commit | Evidência | Resultado |
|---|---|---|---|
| S00 | este registro | `docs/REGISTRO_EXECUCAO_S00_S05.md` | DONE (parcial: sem medição física) |
| S01 | idem | `test_s00_s05_contract.py` (12 testes) + schemas | DONE código; H0 com firmware pendente |
| S02 | idem + migration `0011` | models `workflow_outbox`/`gateway_commands`, dispatcher, comandos persistentes | DONE código; dispatcher restart real pendente de Temporal |
| S03 | idem | `esp/` (provisioning, discovery 8786, HTTP 8787, ForegroundService) | PARCIAL: sem TLS/cert ESP-IDF, sem teste físico |
| S04 | idem | ViewModel drain/Result/cursor, câmera reuse, worker teto | DONE código; medição física pendente |
| S05 | idem | `activities/real.py`, worker real, starter, factory, OCR, áudio, Dockerfile | DONE código; missão real pendente |

## S01 — contratos, autenticação e schemas

- `common/contract_ids.py` novo: IDs ESP 1-63, sequence 1-64 (sem truncar), cursor 0..2^53-1.
- `gateway.py`/`handwritten.py`: limites (`expected_pages` 1-100, `minimum_ratio` (0,1],
  `frame_index` 0-10000, SHA hex 64, capture/device 63 + pattern), `resumed`+`cursor`
  autoritativos, hint inválido/encerrado → 409 (sem fallback silencioso), tradução
  `resume_requested`+`last_session_id`, `capture-complete` com contagem do banco
  (`declared_frames` só auditoria), comando `Literal` fechado, `/command/ack`,
  leitura de corpo em chunks com 413 antes de carga integral.
- `gateway_rgb.py`: cursor 2^53-1, IDs ESP 63/pattern.
- `frame_upload.py`: índice ≥0, JPEG decodificado real (415 truncado, 422 dimensões),
  dimensões do conteúdo (não do header), idempotência antes do gate de fechamento.
- `handwritten.py`: `expected_words=None` herda admin (A20); null explícito limpa
  nuláveis em `settings_service.py` (A23).
- `delivery.py`: cursor virtual inicial 0 (A17); `mark_result_processing` preserva
  CANCELLED (cerca S02.10).
- Android: interceptor envia `X-Gateway-Id` + `Authorization` (A02); `GatewayConfig`
  com `gatewayId/gatewaySecret` + `requireProvisioned()`; DTOs alinhados
  (`command`, answers `String`, evento com `session_id/next_index/item_count`,
  `resume_requested`, `ackCommand`) (A03).

## S02 — durabilidade

- Migration `0011_workflow_outbox_commands` (nova; nenhuma antiga editada): tabelas
  `workflow_outbox` e `gateway_commands`.
- `capture/dispatcher.py`: intent na mesma transação do LOCK + `dispatch_pending`
  com ID determinístico e retry observável; `end-signal` (EXAM + handwritten) usa
  outbox e só então tenta despacho (falha → PENDING, nunca "locked" sem intent).
- `capture/commands.py`: comandos persistentes, GET sem efeito, long-poll cooperativo
  (teto 25s), controle STOP/RESUME nunca preso pela pausa, ACK de efeito durável.
- `frame_upload.py`: `UPLOAD_OPEN_STATES` (CAPTURING/CANDIDATE/LOCKING); duplicata
  idêntica confirmada mesmo após fechamento; objeto existente + mesmo hash revincula
  (A15); storage imutável por papel lógico incl. custom (A32); HEAD só-404=ausente.
- `storage/__init__.py` + `r2_storage.py`: produção sem fallback em memória (A16),
  `is_configured`, erro explícito.
- Cancelamento: `delivery`/`publisher` com cerca CANCELLED + `workflows/cancellation.py`
  (solicita cancel Temporal; barreira no banco impede avanço tardio) (A18).

## S03 — ponte Android real

- `esp/EspProvisioning.kt`: identidade estável + segredo por dispositivo (tempo constante).
- `esp/EspDiscoveryResponder.kt`: UDP 8786 (só localização).
- `esp/EspHttpServer.kt`: HTTP 8787 com HELLO/start/frame-bruto/capture-complete/
  command/result/event; JPEG sem transformação; tmp→rename + Room + reconciliação
  antes do ACK (200/201/208); duplicata idêntica → 208; conflito → 409; validação
  antes de aceitar; outbox-arquivo de eventos (S03.8).
- `esp/EspBridgeService.kt`: ForegroundService (notificação, WakeLock, ciclo limpo),
  reconciliação no (re)início; `AndroidManifest` com service + permissões.
- PENDENTE (H1): TLS com confiança provisionada validada no ESP-IDF + relógio/rotação
  (HTTP atual só para bancada isolada), teste físico discovery→upload→reinício→cloud.

## S04 — captura, fila e sessão

- `PhoneCameraCaptureSource`: reutiliza binding por perfil (S04.1); AF fora do Main com
  timeout cancelável; EXIF/hash/I-O em `Dispatchers.IO` com cancelamento (S04.2).
- `SessionViewModel`: para produtor antes de drenar; intenção de fechamento persistida;
  timeout NÃO fecha com pendências; `Result.failure` verificado (capture-complete,
  save, end-signal); cursor persiste (SharedPreferences) e avança após efeito+ACK;
  comando desconhecido preserva cursor; `capture-complete` adiado sem persistência
  total; `bindCamera` reutiliza source; `pruneAcked` retenção 7d (S04.7).
- `CommandPollWorker`: mesmo padrão cursor/ACK/drain/STOP.
- `SpoolRepository`: `writeAtomically` tmp→rename+fsync; `reconcileLocalSpool`;
  `UploadWorker` com teto `MAX_ATTEMPTS=25` (sem retry infinito) e incremento no
  caminho api-nula.

## S05 — workflow e processamento reais

- `workflows/activities/real.py` (20 atividades reais, sem sucesso fabricado; Gate 1
  pré-Solver, Gate 2 pré-áudio, cerca CANCELLED, telemetria etapa/duração/tentativa);
  `worker.py` registra SOMENTE reais; `fakes.py` marcado TEST-ONLY; `process_exam.py`
  usa reais.
- `starter.py`: fila explícita `get_settings().TEMPORAL_TASK_QUEUE` (sem
  `client._config`); `WorkflowAlreadyStartedError` tratado.
- `ai/factory.py`: snapshot integral (projeto/localização/processador/versão) (A22).
- `ocr/credentials.py`: loader único JSON/caminho + token com reuso e refresh em
  thread; `admin_settings.py` verify usa o mesmo (A27); `google_document_ai.py`
  persiste bruto sob sessão real antes de anunciar chave (A28).
- `ai/confidence.py` + `question_pipeline.py`: confiança <0.50 → MANUAL e resolvedor
  recusado sob revisão manual (A29).
- `image/preprocess.py`: nomes por sessão + `applied/skipped/failed` (A30).
- `audio/assemble.py` + `validate.py`: kill/wait/reap + pipes fechados; sem `0.0`/`[]`
  mascarados (A31).
- `Dockerfile.pages-rgb`: `--group ocr/audio/rag` (não `--all-extras`), `ffmpeg`
  via apt, verificação de imports/executáveis (A07).

## Testes

- `tests/unit`: **411 passed, 1 skipped** (skip = produção-sem-fake, exige APP_ENV).
- Novos: `tests/unit/api/test_s00_s05_contract.py` (12 testes).
- Atualizados: `test_gateway_command.py` (Literal rejeita UNKNOWN_X),
  `test_android_only_e2e.py` (JPEG real + mock de comandos persistentes).
- `ruff check` verde em `src/` + `apps/api/` + testes tocados.
- NÃO executados aqui: integração Postgres/storage/Temporal reais, build Docker,
  Gradle/APK, missão física (sem JDK/Docker/serviços neste ambiente).

---

# Apêndice S06–S12 — 09/09/2026 (autorização total do usuário)

## S06 — conhecimento, consultas e configuração — DONE (código)

- `routers/knowledge.py`: auth admin em leitura E escrita (A08); persistência real
  `KnowledgeDocument`/`KnowledgeChunk` + upload do original (A09, sem chave sem
  upload); limites (20 MB, título 1–300); extração em `asyncio.to_thread` (A26);
  `reindex` real com contagens + `AuditEvent` (verificável); `search-test` via
  `HybridRetriever` persistente com 503 explícito em falha (nunca vazio mascarado).
- `rag/retrieval.py`: `CAST(:embedding AS vector)` tipado (A24); FTS por
  `websearch_to_tsquery` + `begin_nested` por estágio (A25: pontuação não aborta,
  falha ≠ vazio); `retrieve_for_session` para o workflow.
- `admin_settings.py` + `schemas/admin.py` + painel `config/page.tsx`: save-and-verify
  testa a PROPOSTA do formulário (api_key/projeto/location/processor/credentials
  opcionais), sem salvar antes (A23/S06.6).

## S07 — publicação e entrega RGB — DONE (código)

- `rgb/policy.py`: perfil low-power 12%/150 ms/2850 ms nomeado; payloads antigos
  3000/5000 intactos (imutáveis por sequência).
- `gateway.py` + `handwritten.py`: novas sessões carimbam `rgb_profile low-power`
  + 12/150/2850 explicitamente; `publisher._defaults` já preferia o snapshot.
- Painel: "Mínimo Gate 2 — áudio" + nota de que RGB exige 100% (A21).
- Fixture low-power separada em `test_canonical.py` (vetor legado preservado).
- Ordem publicar (persistir → flush → anunciar), digest binário validado,
  idempotência COMPLETED e cerca CANCELLED já cobertos (S02.10).

## S08 — observabilidade, painel e saúde — DONE (código)

- `routers/health.py`: `/ready` verifica banco/storage/Temporal+outbox com timeouts
  (503 + `failing` quando requerido cai; produção exige Temporal) (A06); `/live`
  segue trivial; `/dependencies` com storage real + `workflow_outbox.pending`;
  novo `/health/worker` prova polling da fila (pollers>0).
- `admin_sessions.session_detail`: `frames_page/limit` + `logs_page/limit` com totais
  (S08.4); schema estendido de forma aditiva.
- Painel `[id]/page.tsx`: polling 5 s enquanto ativa, `AbortController` por request,
  para após terminal (S08.3); controles de paginação fotos/registros (S08.4).
- `lib/api.ts`: respeita sinal externo (S08.3).
- S08.5 (reteste navegador) e S08.6 (medição vs S00): PENDENTES de ambiente com
  serviços (sem browser/serviços aqui).

## S09 — qualidade e builds — DONE (código/CI; device builds pendentes de runner)

- `ci.yml`: job `integration` ATIVO (pgvector/pg16 + setup Python 3.12 + uv +
  migrate + testes; falha impede promoção); `uv sync --all-extras --all-groups`;
  job `docker` builda a imagem EFETIVA + verifica imports/`ffmpeg`/`ffprobe`;
  job `admin` roda `npm test` (novo teste funcional `__tests__/flows.test.mjs`:
  proposta, abort/polling, paginação, nota RGB — 5 testes verdes).
- `deploy-pages-rgb.yml`: `uv sync` com grupos; digests SHA registrados como
  artefatos + summary (S11.7).
- `Makefile`: `install` com grupos; `admin` real (ci+typecheck+test+build);
  `benchmark` real; sem stubs como comprovação (S09: `e2e` exige `tests/e2e/`).
- `Dockerfile.pages-rgb` (S05.13, válido p/ S09.4).
- S09.6 (Gradle/APK): job CI existente mantido; execução PENDENTE de runner com
  JDK 17/SDK (indisponíveis aqui).
- S09.7 (keystore): BLOQUEADO com registro — nenhum keystore/mecanismo no repo;
  release exige chave operacional existente; NENHUMA chave foi inventada.

## S10 — validação física — PROTOCOLO PRONTO, execução BLOQUEADA

- `docs/runbooks/missao-fisica-S10.md`: registro pré-missão, missão multi-comando,
  6 cenários de recuperação, métricas vs baseline.
- Motivo do bloqueio: sem telefone/ESP/credenciais/serviços neste ambiente
  (H1–H2 exigem os dois executores + hardware). Nenhum mock conta como aceite.

## S11 — push, imagens e deploy — DONE (código/workflow) + execução pendente

- Workflow publica por SHA + digest e agora EXECUTA deploy (`deploy` job: backup,
  `git checkout <sha>`, `scripts/deploy-pages-rgb.sh`, smoke ready/worker/versão).
- `scripts/deploy-pages-rgb.sh` (único): lock, projeto explícito, env validado,
  pull obrigatório (sem `|| true`), migrate uma vez, health por
  `127.0.0.1:8081` + `Host: ptr.rotadeataque.com.br` + `/ready`, smoke externo;
  latest PROIBIDO.
- `infra/docker-compose.pages-rgb.prod.yml`: `name: pages-rgb`, IMAGE_TAG
  obrigatório, `pages-rgb-worker` (mesma imagem, comando worker, mesma fila),
  TEMPORAL obrigatório, sem remoção de contrato legado.
- `scripts/backup-db.sh` (pg_dump pré-rollout) + `scripts/rollback-pages-rgb.sh`.
- Commit + push desta branch: ver S11.6 abaixo. APK assinado (S11.13) e smoke H4
  (S11.14): PENDENTES de runner/VPS/hardware.

## S12 — rollback e entrega — DONE (docs/scripts)

- `docs/runbooks/rollback-S12.md` + `scripts/rollback-pages-rgb.sh`: sem perda de
  dados, sem downgrade destrutivo, APK mesma assinatura, reteste pós-rollback.

## Testes (final)

- `tests/unit`: **425 passed, 1 skipped**.
- Novos: `test_s06_s12_contract.py` (13 testes), `__tests__/flows.test.mjs` (5 testes).
- Atualizados: `test_health.py` (novo contrato ready/dependencies), `test_canonical.py`
  (fixture low-power).
- `ruff check` verde no escopo alterado; `ruff format` aplicado nos tocados.
- Achado real dos testes: `parse_frame_key` esperava 4 segmentos (bug) — corrigido
  para 5 (`sessions/{sid}/frames/{capture_id}/{idx}.jpg`) via teste.
