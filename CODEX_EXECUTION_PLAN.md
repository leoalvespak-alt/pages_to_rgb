# Pages_to_Audio_Resposta — Plano de Execução para o Codex

## Extensão executada — firmware V2.2 RGB

Foi implementado o alinhamento do servidor com o canal de resultados RGB do firmware V2.2: schemas e policy em `src/pages_to_audio/rgb`, migration `0003_rgb_result_delivery`, publicação após Gate 2, endpoints autenticados de polling/download/eventos, idempotência de `COMPLETED`, simulador e contrato em `docs/contracts/RGB_RESULT_V1.md`. O hash usa exatamente `<BBBBBII` little-endian e o servidor não entrega sequências parciais.

**Versão:** 1.0
**Data:** 15/08/2026
**Documento-fonte (fonte de verdade arquitetural):** `Pages_to_Audio_Resposta_IMPLEMENTATION_PLAN.md` (renomeado para `IMPLEMENTATION_PLAN.md` na raiz, conforme §76).
**Natureza deste documento:** plano operacional de execução. Ele **não substitui** o documento-fonte; ele o traduz em Fases → Etapas → Passos atômicos, verificáveis e ordenados, para que o Codex implemente 100% do escopo com fidelidade.

> **Regra de precedência:** em qualquer conflito entre este plano e o `IMPLEMENTATION_PLAN.md`, **o `IMPLEMENTATION_PLAN.md` vence**. Divergências detectadas estão catalogadas e resolvidas no **Anexo B**; nenhuma delas pode ser resolvida por improviso durante a execução.

---

## Índice

- [0. Como o Codex deve usar este plano](#0-como-o-codex-deve-usar-este-plano)
- [1. Convenções globais de execução](#1-convenções-globais-de-execução)
- [2. Mapa de fases e milestones](#2-mapa-de-fases-e-milestones)
- [FASE 0 — Bootstrap](#fase-0--bootstrap)
- [FASE 1 — Banco, domínio e estados](#fase-1--banco-domínio-e-estados)
- [FASE 2 — Storage e ingestão](#fase-2--storage-e-ingestão)
- [FASE 3 — Capture Controller](#fase-3--capture-controller)
- [FASE 4 — Temporal skeleton](#fase-4--temporal-skeleton)
- [FASE 5 — Imagem + OCR](#fase-5--imagem--ocr)
- [FASE 6 — Reconstrução + Gate 1](#fase-6--reconstrução--gate-1)
- [FASE 7 — Knowledge + RAG](#fase-7--knowledge--rag)
- [FASE 8 — Solver / Verifier / Arbiter](#fase-8--solver--verifier--arbiter)
- [FASE 9 — Gate 2 + TTS + Áudio](#fase-9--gate-2--tts--áudio)
- [FASE 10 — Painel administrativo](#fase-10--painel-administrativo)
- [FASE 11 — Hardening](#fase-11--hardening)
- [FASE 12 — Deploy](#fase-12--deploy)
- [FASE 13 — Aceite final V1](#fase-13--aceite-final-v1)
- [Anexo A — Matriz de rastreabilidade](#anexo-a--matriz-de-rastreabilidade-seção-do-spec--fase)
- [Anexo B — Divergências do spec e resoluções](#anexo-b--divergências-do-spec-e-resoluções-obrigatórias)
- [Anexo C — Prompt-base por fase](#anexo-c--prompt-base-por-fase-para-o-codex)
- [Anexo D — Convenções de Git, commit e PR](#anexo-d--convenções-de-git-commit-e-pr)
- [Anexo E — Checklist mestre de conclusão](#anexo-e--checklist-mestre-de-conclusão)

---

## 0. Como o Codex deve usar este plano

### 0.1 Leitura obrigatória antes de qualquer fase

1. `IMPLEMENTATION_PLAN.md` — integralmente, sem pular seções.
2. `CLAUDE.md` — regras invioláveis.
3. Este arquivo — a fase corrente e o **Anexo B**.
4. `docs/` existente e ADRs já escritos.

### 0.2 Protocolo de execução de uma fase (§64 do spec)

Para **cada** fase, nesta ordem exata:

1. **Planejar** — resumir escopo, listar arquivos a criar/alterar, listar riscos, listar invariantes (§10) aplicáveis. Não editar nada nesta etapa.
2. **Implementar** — etapa por etapa, passo por passo, na ordem escrita.
3. **Verificar** — `make lint`, `make typecheck`, `make test` verdes. Sem exceções.
4. **Documentar** — atualizar `docs/` e o registro de progresso.
5. **Registrar desvios** — qualquer decisão arquitetural não prevista vira `docs/decisions/ADR-xxxx.md`.
6. **Commitar** — conforme Anexo D.

### 0.3 Regras de fronteira entre fases

- **Nunca** implementar funcionalidade de fase futura, salvo *interface/stub estritamente necessário* para a fase atual compilar e testar.
- **Nunca** avançar de fase com teste vermelho, lint vermelho ou critério de aceite pendente.
- **Nunca** compensar defeito estrutural de fase anterior em fase posterior (§4). Se um defeito anterior aparecer, voltar, corrigir na fase de origem, re-rodar os testes daquela fase.

### 0.4 Registro de progresso obrigatório

Criar e manter `docs/progress/PHASE_STATUS.md` com uma linha por etapa:

```text
| Fase | Etapa | Status | Commit | Testes | Data | Observação |
```

Status permitidos: `NOT_STARTED`, `IN_PROGRESS`, `DONE`, `BLOCKED`.
Uma etapa só vira `DONE` quando **todos** os seus passos estiverem concluídos e os testes da etapa verdes.

### 0.5 Vocabulário deste plano

- **Fase** — unidade de entrega com DoD próprio (mapeia 1:1 com §53 do spec).
- **Etapa** — bloco coeso dentro da fase; termina em um commit.
- **Passo** — ação atômica e verificável; normalmente 1 arquivo ou 1 conceito.
- **DoD** — Definition of Done, condição binária de conclusão.
- **CA** — Critério de Aceite, observável e testável.

---

## 1. Convenções globais de execução

### 1.1 Estrutura do repositório

Criar exatamente a árvore de §5 do spec, na raiz do repositório atual. O nome lógico do projeto é `pages-to-audio`; o diretório físico atual (`pagestoaudio_servidor`) permanece como está — **não renomear o diretório**, apenas usar `pages-to-audio` como nome de pacote/imagem/rede.

### 1.2 Padrões de código não negociáveis

| Item | Regra |
|---|---|
| Python | 3.12+ |
| Tipagem | 100% das funções públicas tipadas; `mypy --strict` no pacote `src/pages_to_audio` |
| Lint | `ruff check` + `ruff format`, zero warnings |
| Async | Nada de I/O bloqueante no event loop; CPU-bound via `run_in_executor` dedicado |
| Imports | Camada `domain/` **não** importa SDK de vendor, ORM, FastAPI nem Temporal |
| Segredos | Nunca em código, teste, fixture ou log |
| Chamada externa | Timeout explícito + retry policy explícita + reason_code em falha |
| Mutação | Idempotente, com chave de idempotência ou identidade natural |
| Estado de sessão | Alterado **somente** por `transition_session()` |
| LLM | Saída sempre validada por Pydantic; **nunca** regex para extrair resposta |
| Fallback | Sempre explícito, sempre auditado, nunca silencioso |

### 1.3 Arquitetura em camadas (direção de dependência)

```text
apps/api ──► src/pages_to_audio/{workflows,capture,ocr,rag,llm,audio,image}
                        │
                        ├──► domain/      (entidades, enums, invariantes, portas)
                        ├──► db/          (SQLAlchemy, repositories)
                        ├──► storage/     (Supabase adapter)
                        ├──► config/      (settings)
                        └──► common/      (errors, reason codes, retry, breaker, ids)

domain/ não importa nada acima dele.
```

### 1.4 Portas (Protocols) que existem desde o início

Mesmo antes de terem implementação real, estas interfaces devem existir e ser estáveis (§71):

```text
domain/ports/storage.py        StoragePort
domain/ports/ocr.py            OCRProvider          (§19)
domain/ports/vision.py         VisionProvider       (§20)
domain/ports/embedding.py      EmbeddingProvider    (§24.3)
domain/ports/reasoning.py      ReasoningProvider    (§26)
domain/ports/tts.py            TTSProvider          (§35)
domain/ports/clock.py          Clock                (testabilidade)
domain/ports/events.py         EventPublisher       (SSE, §38)
```

### 1.5 Política de erros

- Hierarquia única em `common/errors.py`: `AppError` → `RetryableError` / `NonRetryableError` (classificação de §17.3).
- Todo erro carrega `reason_code: ReasonCode` (enum central, §40).
- **Nunca** usar string livre como chave de lógica.

### 1.6 Política de testes (aplicável a todas as fases)

| Tipo | Diretório | Regra |
|---|---|---|
| unit | `tests/unit/` | Sem I/O, sem rede, sem banco. Rápido. |
| contracts | `tests/contracts/` | Providers mockados, matriz de falhas (§50.2) |
| integration | `tests/integration/` | Banco de teste real, storage fake ou bucket de teste |
| workflows | `tests/workflows/` | Temporal time-skipping test environment |
| e2e | `tests/e2e/` | Providers fake determinísticos, dataset dourado |
| fixtures | `tests/fixtures/` | Golden dataset, imagens, OCR gravado |

- `USE_REAL_ANTHROPIC`, `USE_REAL_DEEPSEEK`, `USE_REAL_OCR`, `USE_REAL_TTS` são `false` por padrão. **Teste unitário nunca gasta API** (§55).
- Cobertura mínima exigida por fase: **85%** em `src/pages_to_audio/domain/` e **75%** global do pacote.

### 1.7 Configurabilidade obrigatória (§70)

Nada da lista de §70 pode ser hardcode. Toda sessão grava `config_snapshot` e `provider_snapshot` no momento do LOCK.

---

## 2. Mapa de fases e milestones

| Fase | Nome | Milestone do spec | Entrega observável |
|---|---|---|---|
| 0 | Bootstrap | — | App sobe, health OK, quality gates verdes |
| 1 | Banco, domínio, estados | — | Sessão inteira representável no banco |
| 2 | Storage e ingestão | — | 100 frames com retries, sem perda/duplicata |
| 3 | Capture Controller | **1ª milestone (§66)** | Simulador gera N páginas lógicas e trava a sessão |
| 4 | Temporal skeleton | — | Workflow durável percorre 20 etapas com fakes |
| 5 | Imagem + OCR | — | OCR normalizado auditável de página real |
| 6 | Reconstrução + Gate 1 | **2ª milestone (§67)** | Questões estruturadas + Gate 1 correto |
| 7 | Knowledge + RAG | — | Retrieval híbrido medido |
| 8 | Solver/Verifier/Arbiter | **3ª milestone (§68)** | Respostas finais com política de fallback |
| 9 | Gate 2 + TTS + Áudio | — | MP3 final validado |
| 10 | Painel | **4ª milestone (§69)** | Operador audita sessão inteira no navegador |
| 11 | Hardening | — | Chaos suite sem perda silenciosa |
| 12 | Deploy | — | Deploy repetível e reversível |
| 13 | Aceite final | §65 | DoD global assinado |

**Ordem inegociável** (§80): fundação → dados → ingestão → captura → workflow → OCR → reconstrução → Gate 1 → RAG → IA → Gate 2 → áudio → painel → hardening → deploy.

---

# FASE 0 — Bootstrap

**Objetivo (§53/FASE 0):** o projeto sobe localmente e passa em todos os quality checks.
**Fora de escopo:** banco real, OCR, LLM, frontend funcional.
**Seções do spec cobertas:** §3, §5, §6, §7, §39.1, §39.2, §44 (parcial), §54, §55.

---

## Etapa 0.1 — Fundação do repositório e documentos normativos

**Passo 0.1.1** — Garantir branch de trabalho.
```bash
git checkout -b develop
```
Se `develop` já existir, usar. Nunca trabalhar direto em `master`.

**Passo 0.1.2** — Copiar o documento-fonte para a raiz com o nome canônico:
- criar `IMPLEMENTATION_PLAN.md` com o conteúdo integral de `Pages_to_Audio_Resposta_IMPLEMENTATION_PLAN.md`;
- manter o arquivo original no repositório (não apagar);
- não editar o conteúdo copiado.

**Passo 0.1.3** — Criar `CLAUDE.md` na raiz contendo, **literalmente e sem reordenar**, as 20 regras do bloco de §6. Acrescentar abaixo, em seção separada intitulada `## Operacional`:
- link para `IMPLEMENTATION_PLAN.md` e para este `CODEX_EXECUTION_PLAN.md`;
- comandos do Makefile (§54);
- regra: "toda alteração de schema exige migration Alembic nova; migration aplicada é imutável" (§47).

**Passo 0.1.4** — Criar `.gitignore` cobrindo: `.env`, `.env.*` (exceto `.env.example`), `__pycache__/`, `.venv/`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `node_modules/`, `dist/`, `*.mp3`, `*.jpg`, `*.jpeg`, `*.png` sob `tests/fixtures/golden/` (ver Passo 6.9.2), `credentials*.json`, `*.pem`.

**Passo 0.1.5** — Criar a árvore vazia de diretórios de §5, com `.gitkeep` onde necessário. Nenhum diretório da §5 pode faltar.

**Passo 0.1.6** — Criar `README.md` com: propósito, requisitos (Python 3.12+, Docker, uv), setup local, comandos do Makefile, aviso de que `IMPLEMENTATION_PLAN.md` é a fonte de verdade.

**Passo 0.1.7** — Criar os 10 ADRs de §77 em `docs/decisions/`, no formato:
```markdown
# ADR-0001 — Supabase as application DB/storage
- Status: Accepted
- Data: <data>
- Contexto: <extrair de §2.2 / §12>
- Decisão: <...>
- Consequências: <...>
- Alternativas consideradas: <...>
```
Os 10 ADRs (0001..0010) devem sair desta fase **preenchidos**, não como stub vazio — o conteúdo já existe disperso no spec.

**Passo 0.1.8** — Criar os arquivos-esqueleto de `docs/`: `architecture.md`, `api_contracts.md`, `android_contract.md`, `workflow.md`, `operations.md`, `security.md`, e a pasta `docs/runbooks/`. Nesta fase, cada um recebe sumário e "TODO por fase" com referência à fase que o preenche.

**Passo 0.1.9** — Criar `docs/progress/PHASE_STATUS.md` conforme §0.4 deste plano.

**CA da Etapa 0.1:** `IMPLEMENTATION_PLAN.md`, `CLAUDE.md`, 10 ADRs e árvore de §5 existem e estão versionados.

---

## Etapa 0.2 — Toolchain Python e qualidade

**Passo 0.2.1** — Criar `pyproject.toml` com:
- `[project]`: nome `pages-to-audio`, `requires-python = ">=3.12"`;
- dependências exatamente da lista de §3 (FastAPI, Pydantic v2, pydantic-settings, SQLAlchemy 2.x async, Alembic, asyncpg, httpx, temporalio, opencv-python-headless, Pillow, structlog, opentelemetry-*, sentry-sdk, argon2-cffi, python-multipart);
- `[dependency-groups]`/extras: `dev` (pytest, pytest-asyncio, pytest-cov, ruff, mypy, respx, freezegun), `ocr`, `audio`, `rag`;
- `[tool.ruff]`: `line-length = 100`, regras `E,F,I,N,UP,B,S,ASYNC,RUF`;
- `[tool.mypy]`: `strict = true`, `plugins = ["pydantic.mypy"]`, escopo `src/pages_to_audio`;
- `[tool.pytest.ini_options]`: `asyncio_mode = "auto"`, `testpaths = ["tests"]`, markers `unit`, `integration`, `contracts`, `workflows`, `e2e`, `slow`.

**Passo 0.2.2** — Gerar `uv.lock`:
```bash
uv sync --all-extras
```

**Passo 0.2.3** — Criar `Makefile` com **todos** os alvos de §54, sem exceção:
`install`, `dev`, `test`, `test-unit`, `test-integration`, `lint`, `typecheck`, `migrate`, `migration name="..."`, `api`, `worker`, `admin`, `simulator`, `e2e`, `benchmark`.
Alvos ainda sem implementação real devem existir e falhar com mensagem clara indicando a fase que os habilita (ex.: `worker: @echo "Disponível a partir da FASE 4"; exit 1`). Isso mantém §54 verdadeiro desde o início.

**CA da Etapa 0.2:** `make install`, `make lint`, `make typecheck` executam com saída verde.

---

## Etapa 0.3 — Configuração tipada

**Passo 0.3.1** — Criar `.env.example` com **todas** as chaves de §7, na mesma ordem, mais as chaves faltantes catalogadas no **Anexo B** (B-2, B-3, B-4, B-5, B-6, B-7). Nenhum valor real.

**Passo 0.3.2** — Criar `src/pages_to_audio/config/settings.py` usando `pydantic-settings`, organizado em sub-modelos aninhados:
`AppSettings`, `DatabaseSettings`, `SupabaseSettings`, `AuthSettings`, `TemporalSettings`, `AnthropicSettings`, `DeepSeekSettings`, `OCRSettings`, `TTSSettings`, `RAGSettings`, `CaptureDefaults`, `TempSettings`, `ConcurrencySettings`, `TimeoutSettings`, `RetrySettings`, `RetentionSettings`, `ObservabilitySettings`, `FeatureFlags`.

**Passo 0.3.3** — Regras de validação (§7):
- fail-fast: se `APP_ENV=production` e faltar `DATABASE_URL`, `SUPABASE_*`, `SESSION_SECRET`, `TEMPORAL_ADDRESS` → erro na inicialização, com mensagem que **não** imprime o valor;
- todo campo de segredo é `SecretStr`;
- `DEFAULT_MINIMUM_RATIO` validado em `0 < x <= 1`;
- concorrências validadas `>= 1`;
- `__repr__`/`model_dump` de settings **nunca** revela segredo.

**Passo 0.3.4** — Criar `get_settings()` com cache (`lru_cache`) e função `reset_settings_cache()` para testes.

**Passo 0.3.5** — Testes `tests/unit/config/test_settings.py`:
- carrega `.env.example` sem erro em `APP_ENV=development`;
- falha em produção sem segredo crítico;
- `repr` não vaza segredo;
- valores default corretos (30 páginas, 70 questões, 0.90).

**CA da Etapa 0.3:** settings falham rápido e não vazam segredo.

---

## Etapa 0.4 — Logging JSON e redaction

**Passo 0.4.1** — Criar `src/pages_to_audio/observability/logging.py` com structlog em modo JSON, contendo **exatamente** os campos de §39.1: `timestamp, level, service, request_id, trace_id, session_id, question_id, capture_id, frame_id, stage, provider, attempt, duration_ms, reason_code`.

**Passo 0.4.2** — Criar processor de redaction que remove/mascara os itens de §39.2: API keys, passwords, gateway token, bearer token, raw reasoning, URLs assinadas completas (manter apenas host + path sem query), campos marcados como sensíveis.

**Passo 0.4.3** — Criar `contextvars` para `request_id`, `session_id`, `trace_id`, com helper `bind_log_context(...)`.

**Passo 0.4.4** — Criar middleware `apps/api/middleware/request_context.py` que gera `request_id` (ou reaproveita header `X-Request-ID`) e loga início/fim com `duration_ms`.

**Passo 0.4.5** — Testes `tests/unit/observability/test_logging_redaction.py`:
- logar dict com `api_key`, `authorization`, `password`, `signed_url` → nenhum valor aparece na saída;
- saída é JSON válido;
- campos obrigatórios presentes.

**CA da Etapa 0.4:** teste de redaction prova que nenhum segredo atravessa o logger.

---

## Etapa 0.5 — Aplicação FastAPI e health

**Passo 0.5.1** — Criar `apps/api/main.py` com factory `create_app()`: lifespan, middlewares (request context, CORS restrito, security headers básicos), routers, handler global de exceção que converte `AppError` em resposta com `reason_code` e **sem** stack para o cliente.

**Passo 0.5.2** — Criar `apps/api/dependencies.py` com container de dependências (settings, futuros: db session, storage, event bus). Nesta fase, apenas settings e clock.

**Passo 0.5.3** — Criar `apps/api/routers/health.py` (§13.1):
- `GET /api/v1/health/live` → 200 imediato, sem I/O;
- `GET /api/v1/health/ready` → checa apenas dependências essenciais com timeout curto (≤ 2s no total); nesta fase retorna `{"status":"ready","checks":{}}`;
- `GET /api/v1/health/dependencies` → detalhamento por dependência, cada uma com `status`, `latency_ms`, `checked_at`; nesta fase lista as dependências como `not_configured`.

**Passo 0.5.4** — Definir o prefixo global `/api/v1` (§13) em um único lugar (`apps/api/routers/__init__.py`).

**Passo 0.5.5** — Testes `tests/unit/api/test_health.py`: `live` 200; `ready` 200 e sem chamada externa; `dependencies` com shape estável; app importa sem efeito colateral.

**CA da Etapa 0.5:** `uvicorn` sobe e os três endpoints respondem.

---

## Etapa 0.6 — Docker e execução local

**Passo 0.6.1** — Criar `infra/docker/api.Dockerfile` multi-stage: builder com `uv`, runtime slim, usuário **não-root**, `PYTHONDONTWRITEBYTECODE`, healthcheck apontando para `/api/v1/health/live`, sem segredo na imagem (§49).

**Passo 0.6.2** — Criar `infra/docker/worker.Dockerfile` (mesma base; comando ainda placeholder até a Fase 4).

**Passo 0.6.3** — Criar `infra/docker-compose.dev.yml` com serviço `pages-api` publicando **`127.0.0.1:18180:8000`** (§3). Não incluir PostgreSQL, MinIO, Elasticsearch nem LLM local (§45).

**Passo 0.6.4** — Documentar em `docs/operations.md` que o proxy externo é responsável por domínio, TLS, HTTP/2, limites de upload e headers de segurança (§3).

**Passo 0.6.5** — Validar:
```bash
docker build -f infra/docker/api.Dockerfile -t pages-to-audio-api:dev .
```

**CA da Etapa 0.6:** imagem builda, container sobe e responde em `127.0.0.1:18180`.

---

## Etapa 0.7 — CI mínima

**Passo 0.7.1** — Criar `.github/workflows/ci.yml` com os passos de §46 que já existem: checkout → setup Python 3.12 → install uv → `uv sync` → ruff → mypy → `pytest -m unit` → build Docker.
Os estágios `pytest integration` e `frontend lint/test/build` entram como jobs **declarados e desabilitados por condição**, habilitados nas Fases 1 e 10 respectivamente.

**Passo 0.7.2** — Configurar cache de `uv` e falha do job em qualquer erro de lint/type/test.

**CA da Etapa 0.7:** pipeline verde no push da branch.

---

## DoD da FASE 0

- [ ] `make test` verde
- [ ] `make lint` verde
- [ ] `make typecheck` verde
- [ ] `docker build` verde
- [ ] `/api/v1/health/live`, `/ready`, `/dependencies` respondendo
- [ ] `CLAUDE.md` com as 20 regras literais de §6
- [ ] `.env.example` completo, sem segredo real
- [ ] Teste provando redaction de segredos em log
- [ ] 10 ADRs preenchidos
- [ ] Árvore de §5 criada integralmente
- [ ] CI verde

---

# FASE 1 — Banco, domínio e estados

**Objetivo:** o banco pode representar integralmente uma sessão, sem nenhum provider.
**Fora de escopo:** storage real, captura, OCR, LLM, áudio.
**Seções do spec cobertas:** §8, §9, §10 (invariantes estruturais), §14, §40, §47.

---

## Etapa 1.1 — Camada de persistência base

**Passo 1.1.1** — Criar `src/pages_to_audio/db/base.py`: `DeclarativeBase` com `MetaData` e naming convention determinística:
```python
{"ix": "ix_%(column_0_label)s", "uq": "uq_%(table_name)s_%(column_0_name)s",
 "ck": "ck_%(table_name)s_%(constraint_name)s", "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
 "pk": "pk_%(table_name)s"}
```

**Passo 1.1.2** — Criar `src/pages_to_audio/db/engine.py`: engine assíncrona (asyncpg), `async_sessionmaker`, pool dimensionado para VPS pequena (`pool_size=5`, `max_overflow=5`), `pool_pre_ping=True`.

**Passo 1.1.3** — Criar `src/pages_to_audio/db/uow.py`: Unit of Work assíncrona com `async with`, commit/rollback explícitos, e proibição de commit implícito dentro de repositories.

**Passo 1.1.4** — Criar `src/pages_to_audio/db/types.py`: tipos reutilizáveis (`UUIDPk`, `TimestampTZ` com `server_default=now()`, `JSONBDict`, `Sha256Char`).

**Passo 1.1.5** — Inicializar Alembic em `migrations/`, com `env.py` assíncrono lendo `DATABASE_URL` do settings, `compare_type=True` e `compare_server_default=True`.

---

## Etapa 1.2 — Enums e vocabulário de domínio

**Passo 1.2.1** — `domain/enums/session_state.py`: enum com **exatamente** os 24 estados de §9, na ordem do spec.

**Passo 1.2.2** — `domain/enums/question_status.py`: `DISCOVERED, INCOMPLETE, RESCUING, READY, FAILED` (§8.10).

**Passo 1.2.3** — `domain/enums/reason_code.py`: enum central com **todos** os códigos listados em §40, mais os necessários para completar as políticas (prefixados por área, ex.: `STORAGE_*`, `OCR_*`, `LLM_*`, `AUDIO_*`, `CAPTURE_*`, `GATE_*`). Nenhum código pode ser criado ad hoc fora deste arquivo.

**Passo 1.2.4** — `domain/enums/artifact_type.py`: os 8 tipos de §8.8 (`original, deskew, perspective, contrast, denoise, crop, question_crop, media_crop`).

**Passo 1.2.5** — `domain/enums/roles.py`: `AnswerRole = solver|verifier|arbiter` (§8.14); `PageFrameRole = primary|alternate` (§8.7); `ActorType = admin|gateway|system|workflow` (§11.1).

**Passo 1.2.6** — `domain/enums/end_reason.py`: `EXPECTED_PAGES_REACHED, MANUAL, VISUAL_MARKER, OPEN_HAND, HARD_IDLE, ADMIN_CANCEL` (§16).

**Passo 1.2.7** — `domain/enums/audit.py`: `event_type`, `stage`, `severity` (§8.17) — vocabulário fechado.

---

## Etapa 1.3 — Modelos ORM

**Passo 1.3.1 a 1.3.17** — Criar um módulo por entidade em `src/pages_to_audio/db/models/`, campo a campo, **idêntico** a §8.1–§8.17:

| Passo | Entidade | Seção | Constraints obrigatórias |
|---|---|---|---|
| 1.3.1 | `Device` | §8.1 | `UNIQUE(device_code)` |
| 1.3.2 | `AndroidGateway` | §8.2 | `UNIQUE(gateway_code)` |
| 1.3.3 | `Session` | §8.3 | `UNIQUE(public_id)`, FKs device/gateway, `degraded_mode default false` |
| 1.3.4 | `Capture` | §8.4 | `UNIQUE(session_id, capture_id)` |
| 1.3.5 | `Frame` | §8.5 | `UNIQUE(capture_id, frame_index)` e `UNIQUE(session_id, sha256, capture_id, frame_index)` (ver Anexo B-1) |
| 1.3.6 | `LogicalPage` | §8.6 | `UNIQUE(session_id, logical_index)` |
| 1.3.7 | `LogicalPageFrame` | §8.7 | PK composta `(logical_page_id, frame_id)`, `role`, `rank` |
| 1.3.8 | `ImageArtifact` | §8.8 | índice por `(session_id, artifact_type)` |
| 1.3.9 | `OCRRun` | §8.9 | índice por `(logical_page_id, provider, attempt)` |
| 1.3.10 | `Question` | §8.10 | `UNIQUE(session_id, question_number)` |
| 1.3.11 | `KnowledgeDocument` | §8.11 | índice por `discipline, subject, active` |
| 1.3.12 | `KnowledgeChunk` | §8.12 | `fts TSVECTOR`, `embedding VECTOR(dim)` — dim via Anexo B-8 |
| 1.3.13 | `RetrievalRun` | §8.13 | índice por `question_id` |
| 1.3.14 | `AnswerAttempt` | §8.14 | índice por `(question_id, role, attempt)` |
| 1.3.15 | `FinalAnswer` | §8.15 | `UNIQUE(question_id)` |
| 1.3.16 | `AudioArtifact` | §8.16 | índice por `(session_id, artifact_type)` |
| 1.3.17 | `AuditEvent` | §8.17 | `BIGSERIAL`, índices por `session_id, created_at` e por `event_type` |

**Passo 1.3.18** — Criar `IdempotencyKey` (§14): `key, scope, request_hash, response_status, response_body, created_at, expires_at`, com `UNIQUE(key, scope)` e índice em `expires_at`.

**Passo 1.3.19** — Nenhum modelo pode ter `default` de negócio no Python que divirja do `server_default` — evitar drift entre ORM e migration.

---

## Etapa 1.4 — Migration inicial

**Passo 1.4.1** — Gerar a migration inicial:
```bash
make migration name="0001_initial_schema"
```

**Passo 1.4.2** — Editar a migration para incluir, no topo, as extensões necessárias: `CREATE EXTENSION IF NOT EXISTS vector;`, `pg_trgm`, `unaccent`.

**Passo 1.4.3** — Revisar a migration linha a linha contra §8. Toda divergência é bug de modelo, não de migration.

**Passo 1.4.4** — Validar `upgrade` e `downgrade` completos contra um banco limpo.

**Passo 1.4.5** — Registrar em `CLAUDE.md`/`docs/operations.md`: **migration aplicada é imutável** (§47); correções vêm sempre em migration nova.

---

## Etapa 1.5 — Máquina de estados da sessão

**Passo 1.5.1** — Criar `domain/state_machine.py` com o mapa explícito `ALLOWED_TRANSITIONS: dict[SessionState, frozenset[SessionState]]` cobrindo o fluxo de §9 + §58:

```text
CREATED → CAPTURING | CANCELLED
CAPTURING → CAPTURE_END_CANDIDATE | CANCELLED | FAILED_RECOVERABLE
CAPTURE_END_CANDIDATE → CAPTURING | CAPTURE_LOCKING | CANCELLED
CAPTURE_LOCKING → LOCKED | FAILED_RECOVERABLE | CANCELLED
LOCKED → IMAGE_PROCESSING | CANCELLED
IMAGE_PROCESSING → OCR_PROCESSING | FAILED_RECOVERABLE
OCR_PROCESSING → RECONSTRUCTING | FAILED_RECOVERABLE
RECONSTRUCTING → RESCUE_PROCESSING | GATE_1 | FAILED_RECOVERABLE
RESCUE_PROCESSING → GATE_1 | FAILED_RECOVERABLE
GATE_1 → BLOCKED_GATE_1 | RAG_RETRIEVING
BLOCKED_GATE_1 → STATUS_AUDIO | FAILED_FATAL
RAG_RETRIEVING → SOLVING | FAILED_RECOVERABLE
SOLVING → VERIFYING | FAILED_RECOVERABLE
VERIFYING → ARBITRATING | GATE_2 | FAILED_RECOVERABLE
ARBITRATING → GATE_2 | RESCUE_PROCESSING | FAILED_RECOVERABLE
GATE_2 → BLOCKED_GATE_2 | STATUS_AUDIO | TTS_GENERATING
BLOCKED_GATE_2 → STATUS_AUDIO | FAILED_FATAL
STATUS_AUDIO → TTS_GENERATING | COMPLETED | FAILED_FATAL
TTS_GENERATING → AUDIO_ASSEMBLING | FAILED_RECOVERABLE
AUDIO_ASSEMBLING → AUDIO_VALIDATING | FAILED_RECOVERABLE
AUDIO_VALIDATING → READY | FAILED_RECOVERABLE
READY → COMPLETED
FAILED_RECOVERABLE → <estado de retomada permitido> | FAILED_FATAL | CANCELLED
COMPLETED, FAILED_FATAL, CANCELLED → terminais
```
> Este mapa é normativo para a implementação. Se a execução exigir transição não listada, isso é um desvio arquitetural → ADR + atualização deste plano, nunca edição silenciosa.

**Passo 1.5.2** — Implementar a função única de §9:
```python
async def transition_session(uow, session, target_state, *, reason: ReasonCode | None,
                             actor: ActorType, payload: dict | None = None) -> Session
```
Comportamento obrigatório, na ordem: (1) validar transição permitida; (2) atualizar estado; (3) gerar `AuditEvent`; (4) persistir atomicamente (mesma transação).

**Passo 1.5.3** — Bloquear alteração direta: `Session.status` só é escrito por essa função. Adicionar teste que faz grep/AST scan no pacote e falha se `session.status =` aparecer fora de `state_machine.py`/repository.

**Passo 1.5.4** — Usar bloqueio pessimista (`SELECT ... FOR UPDATE`) na leitura da sessão dentro da transição, para evitar corrida entre API e worker.

**Passo 1.5.5** — Transição inválida levanta `InvalidStateTransition(NonRetryableError)` com `reason_code` dedicado e gera `AuditEvent` de severidade `error`.

---

## Etapa 1.6 — Repositories

**Passo 1.6.1** — Criar `db/repositories/` com um repository por agregado: `sessions`, `devices`, `gateways`, `captures`, `frames`, `logical_pages`, `image_artifacts`, `ocr_runs`, `questions`, `answers`, `audio`, `audit`, `knowledge`, `idempotency`.

**Passo 1.6.2** — Regras: repository recebe a sessão da UoW; não abre transação própria; não faz commit; retorna entidades de domínio ou modelos ORM, nunca dicts soltos.

**Passo 1.6.3** — Criar `audit.record(...)` como único ponto de escrita de `AuditEvent`, com assinatura fechada (`event_type`, `stage`, `severity`, `reason_code`, `payload`, ids).

---

## Etapa 1.7 — Idempotência

**Passo 1.7.1** — Criar `common/idempotency.py` com o serviço (§14):
- chave = header `Idempotency-Key` (UUID) + `scope` (nome lógico da operação);
- `request_hash` = SHA-256 do corpo canônico + parâmetros relevantes;
- se chave existe e `request_hash` **igual** → retorna `response_status`/`response_body` gravados, sem reexecutar;
- se chave existe e `request_hash` **diferente** → `409 CONFLICT` com `reason_code=IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD`;
- `expires_at` configurável (default 48h) + job de limpeza.

**Passo 1.7.2** — Criar dependência FastAPI `idempotent(scope)` reutilizável por qualquer endpoint de ingestão.

**Passo 1.7.3** — Definir a identidade natural adicional de frames (§14): `session_id + capture_id + frame_index + sha256`. Este caminho funciona **mesmo sem** header de idempotência.

---

## Etapa 1.8 — Testes da FASE 1

**Passo 1.8.1** — `tests/unit/domain/test_state_machine.py`: para **cada** par (origem, destino) do mapa 1.5.1 → permitido; para uma amostra exaustiva de pares fora do mapa → `InvalidStateTransition`. Teste parametrizado, sem exceção manual.

**Passo 1.8.2** — Teste: toda transição bem-sucedida cria exatamente 1 `AuditEvent` e o commit é atômico (falha ao gravar audit ⇒ estado não muda).

**Passo 1.8.3** — `tests/integration/db/test_constraints.py`: cada UNIQUE de §8 é violado propositalmente e o erro esperado ocorre.

**Passo 1.8.4** — `tests/integration/db/test_idempotency.py`: mesma chave + mesmo payload → mesma resposta, 1 efeito; mesma chave + payload diferente → 409; chave expirada → reexecução.

**Passo 1.8.5** — Teste de migração: `upgrade head` → `downgrade base` → `upgrade head` em banco limpo.

**Passo 1.8.6** — Teste estrutural: `session.status` não é atribuído fora do módulo autorizado (Passo 1.5.3).

**Passo 1.8.7** — Habilitar o job `pytest integration` na CI (Passo 0.7.1), com serviço Postgres+pgvector no workflow.

## DoD da FASE 1

- [ ] Todos os modelos de §8.1–§8.17 + `idempotency_keys` implementados e migrados
- [ ] Máquina de estados com transições válidas e inválidas testadas exaustivamente
- [ ] `transition_session()` é o único caminho de mudança de estado, com teste que prova
- [ ] `AuditEvent` gerado em toda transição, atomicamente
- [ ] Idempotência funcionando com os três cenários (repetição, conflito, expiração)
- [ ] `upgrade`/`downgrade` reproduzíveis
- [ ] Uma sessão completa pode ser representada no banco sem nenhum provider

---

# FASE 2 — Storage e ingestão

**Objetivo:** o simulador Android envia 100 frames com retries e banco + storage terminam corretos.
**Fora de escopo:** análise de qualidade, páginas lógicas, OCR.
**Seções do spec cobertas:** §11.2, §11.3, §12, §13.4 (parcial), §14, §49 (upload).

---

## Etapa 2.1 — Adapter de Supabase Storage

**Passo 2.1.1** — Definir `domain/ports/storage.py`:
```python
class StoragePort(Protocol):
    async def put_object(self, bucket: str, key: str, data: bytes, content_type: str,
                         *, sha256: str, overwrite: bool = False) -> StoredObject: ...
    async def object_exists(self, bucket: str, key: str) -> bool: ...
    async def get_object(self, bucket: str, key: str) -> bytes: ...
    async def create_signed_url(self, bucket: str, key: str, ttl_seconds: int) -> str: ...
    async def delete_object(self, bucket: str, key: str) -> None: ...
```

**Passo 2.1.2** — Implementar `storage/supabase_storage.py` com httpx assíncrono, timeout de 30s (§42), retry exponencial com jitter, e classificação de erro por `ReasonCode`.

**Passo 2.1.3** — Implementar `storage/keys.py` com as convenções **literais** de §12.2 (funções puras, testadas):
```text
sessions/{sid}/frames/{capture_id}/{frame_index}.jpg
sessions/{sid}/pages/{logical_index}/original.jpg
sessions/{sid}/derived/{artifact_type}/{id}.jpg
sessions/{sid}/ocr/{provider}/{logical_index}.json
sessions/{sid}/audio/status/{id}.mp3
sessions/{sid}/audio/final/{id}.mp3
```

**Passo 2.1.4** — Implementar `storage/buckets.py` com os 6 buckets de §12.1 (`pages-originals, pages-derived, ocr-raw, knowledge, audio, audit-exports`), mapeados a partir de settings (Anexo B-2). Todos privados.

**Passo 2.1.5** — Regra de imutabilidade (Invariante 8, §10): `put_object` com `overwrite=False` para bucket `pages-originals`; tentativa de sobrescrita levanta erro e gera `AuditEvent` crítico.

**Passo 2.1.6** — Signed URLs: TTL curto e configurável (default 300s); **nunca** URL pública permanente; URL assinada nunca é logada inteira (§39.2).

**Passo 2.1.7** — Criar `storage/fake_storage.py` (in-memory) para testes, implementando a mesma porta com a mesma semântica de erro.

**Passo 2.1.8** — Criar script `scripts/bootstrap_buckets.py` que verifica/cria os 6 buckets como privados (idempotente).

---

## Etapa 2.2 — Autenticação do gateway e do device

**Passo 2.2.1** — Implementar `auth/gateway.py` (§11.2): validação de `Authorization: Bearer <gateway-token>` + `X-Gateway-Id`, comparação em tempo constante, token armazenado como hash, suporte a **rotação** (dois tokens válidos simultaneamente durante janela configurável).

**Passo 2.2.2** — Implementar `auth/device.py` (§11.3): validação de assinatura/atestado HMAC do gateway sobre `device_id + capture_id + frame_index + sha256 + timestamp`, usando `DEVICE_HMAC_MASTER_KEY` com derivação por device. Janela de replay configurável (default 300s) + rejeição de nonce repetido.

**Passo 2.2.3** — Regra explícita de §11.3: **não confiar em `device_id` arbitrário**. Device desconhecido ou `enabled=false` → 403 com `reason_code` dedicado, e `AuditEvent`.

**Passo 2.2.4** — Rate limit por gateway (por IP e por `gateway_id`), configurável, com resposta 429 e header `Retry-After`.

**Passo 2.2.5** — Testes: token válido, token inválido, token rotacionado, gateway desabilitado, assinatura inválida, replay, device desconhecido.

---

## Etapa 2.3 — Pipeline de upload de frame

**Passo 2.3.1** — Implementar validação de conteúdo (§49/Upload): allowlist de MIME (`image/jpeg`, `image/png`, `image/webp`), verificação de **magic bytes** (nunca extensão), tamanho máximo configurável, dimensões mínimas/máximas.

**Passo 2.3.2** — Implementar o fluxo **obrigatório** de §12.3, nesta ordem exata:
```text
recebe upload → calcula/verifica SHA-256 → valida limites → envia ao Supabase Storage
→ confirma objeto (HEAD) → grava DB → retorna sucesso
```

**Passo 2.3.3** — Falha de storage ⇒ **não** criar frame como persistido (§12.3). Retornar erro retryable com `reason_code=STORAGE_UPLOAD_FAILED`.

**Passo 2.3.4** — Falha de DB após storage OK ⇒ registrar **orphan object** em tabela `storage_orphans` (`bucket, key, sha256, session_id, created_at, resolved_at, resolution`), acionar retry e deixar para o job de reconciliação (§12.3).

**Passo 2.3.5** — Hash divergente do declarado pelo Android ⇒ `409` + `reason_code=FRAME_HASH_MISMATCH` + `AuditEvent` severidade `critical`, **sem** gravar frame.

**Passo 2.3.6** — Mesmo `capture_id/frame_index` com hash diferente ⇒ `409 CONFLICT` + `FRAME_DUPLICATE_CONFLICT` + evento crítico + **não sobrescrever** (§14).

**Passo 2.3.7** — Reenvio idêntico (mesmo sha256) ⇒ mesma resposta, sem duplicar linha e sem reupload de storage (§14).

---

## Etapa 2.4 — Endpoints de gateway (ingestão)

Implementar em `apps/api/routers/gateway.py`, todos autenticados por 2.2 e auditados:

**Passo 2.4.1** — `POST /api/v1/gateway/hello` — registra/atualiza `AndroidGateway` (app_version, device_model), atualiza `last_seen_at`, devolve capacidades do servidor e versão de contrato.

**Passo 2.4.2** — `POST /api/v1/gateway/session/start` — cria ou **retoma** sessão (idempotente por `Idempotency-Key`), grava `expected_pages`, `expected_questions`, `minimum_ratio` a partir de settings (§7) e do payload, cria `config_snapshot` inicial, transiciona `CREATED → CAPTURING`.

**Passo 2.4.3** — `POST /api/v1/gateway/session/{id}/heartbeat` — atualiza `last_seen_at` de device e gateway, devolve estado atual e se a política ainda é válida.

**Passo 2.4.4** — `POST /api/v1/gateway/session/{id}/capture` — abre um `Capture` (§8.4) com `capture_id` fornecido pelo Android, `mode`, `command_cursor`, `requested_frames`. Idempotente por `UNIQUE(session_id, capture_id)`.

**Passo 2.4.5** — `POST /api/v1/gateway/session/{id}/frame` — ingestão do JPEG (multipart), executa 2.3 inteiro. Aceita `Idempotency-Key`.

**Passo 2.4.6** — `POST /api/v1/gateway/session/{id}/capture-complete` — fecha o burst, compara `received_frames` × `requested_frames`, marca `Capture.status`. Burst incompleto ⇒ `CAPTURE_INCOMPLETE` registrado (o tratamento é da Fase 3).

**Passo 2.4.7** — Invariante 1 (§10): sessão `LOCKED` **não** aceita frame silenciosamente. Resposta `409` com `reason_code=SESSION_LOCKED`; o objeto pode ir para área de auditoria (`audit-exports`), marcado `late_upload=true`, sem alterar páginas lógicas.

**Passo 2.4.8** — Documentar todos os contratos em `docs/android_contract.md`: método, headers, corpo, respostas 2xx/4xx/5xx, semântica de retry do cliente, e comportamento offline (§15.2).

---

## Etapa 2.5 — Reconciliação e limpeza

**Passo 2.5.1** — Criar `scripts/reconcile_storage.py`: varre `storage_orphans`, verifica existência do objeto, tenta recriar a linha do banco, ou marca para descarte. Idempotente e seguro para rodar repetido.

**Passo 2.5.2** — Criar `scripts/cleanup_temp.py` (janitor local, §18.4): remove diretórios de sessão expirados por `LOCAL_TEMP_TTL_HOURS` e reduz uso abaixo de `LOCAL_TEMP_MAX_GB`.

---

## Etapa 2.6 — Simulador Android

**Passo 2.6.1** — Criar `scripts/simulate_android.py` (CLI) capaz de: hello → start → N capturas × M frames → capture-complete, usando imagens de `tests/fixtures/`.

**Passo 2.6.2** — Flags obrigatórias: `--frames`, `--duplicate-rate`, `--corrupt-hash-rate`, `--drop-rate`, `--retry`, `--offline-burst` (simula perda de 4G e sincronização posterior, §15.2), `--concurrency`.

**Passo 2.6.3** — O simulador deve reportar ao final: frames enviados, aceitos, duplicados idempotentes, conflitos, erros — e comparar com o estado do banco.

---

## Etapa 2.7 — Testes da FASE 2

**Passo 2.7.1** — Contratos: frame válido; frame duplicado idêntico; conflito de hash; hash declarado errado; MIME inválido; magic bytes inválidos; arquivo acima do limite; storage timeout; DB falhando após storage.

**Passo 2.7.2** — Integração: 100 frames com `--duplicate-rate 0.2 --drop-rate 0.1 --retry` ⇒ zero perda, zero duplicata, storage e DB consistentes.

**Passo 2.7.3** — Invariante 1: upload após LOCK não altera páginas lógicas.

**Passo 2.7.4** — Invariante 8: sobrescrita de original é rejeitada.

**Passo 2.7.5** — Invariante 9: repetição com mesma idempotency key produz o mesmo efeito lógico.

## DoD da FASE 2

- [ ] Simulador envia 100 frames com retries e banco/storage ficam corretos
- [ ] Duplicata é idempotente; conflito de hash bloqueia com 409 e evento crítico
- [ ] Falha de storage nunca cria frame persistido
- [ ] Orphan reconciliation implementado e testado
- [ ] Autenticação de gateway + atestado de device funcionando, com rotação de token
- [ ] `docs/android_contract.md` completo

---

# FASE 3 — Capture Controller

**Objetivo:** o simulador produz N páginas lógicas corretamente e a sessão trava de forma redundante.
**Fora de escopo:** Temporal, OCR, LLM.
**Seções do spec cobertas:** §15, §16, §18.1–§18.4 (parcial), §10 (invariantes 1, 2, 3).

> **Regra estrutural de §15.1:** o Capture Controller é camada **leve de runtime** na API — `Android ↔ API Capture Coordinator ↔ Supabase`. **Nenhum PROBE vira Activity do Temporal.**

---

## Etapa 3.1 — Primitivas de imagem para captura

**Passo 3.1.1** — `image/fingerprint.py`: perceptual hash (pHash/dHash) + distância de Hamming; funções puras e determinísticas; thresholds vindos de config (§71).

**Passo 3.1.2** — `image/quality.py`: `FrameQualityScorer` (§15.6) calculando **componentes separados**: variance of Laplacian (blur), glare/clipping, histograma/exposição, cobertura de fronteira do documento, perspectiva, motion proxy, área útil de pixels.

**Passo 3.1.3** — Regra de §15.6: o score **não** finge ser probabilidade. Persistir cada componente em `Frame.quality_metrics` (JSONB) junto com o score agregado e a **versão do scorer**.

**Passo 3.1.4** — `image/document.py`: detecção de presença/limites do documento, orientação estimada e flag `document_present`.

**Passo 3.1.5** — Todo processamento OpenCV roda em executor separado com `MAX_IMAGE_PROCESSING_CONCURRENCY` (§18.3, default 1), nunca no event loop.

**Passo 3.1.6** — Testes com imagens sintéticas: nítida vs borrada, com/sem documento, com glare, rotacionada, e pares quase-idênticos (distância pHash pequena).

---

## Etapa 3.2 — CapturePolicy versionada

**Passo 3.2.1** — Criar `capture/policy.py` com o modelo Pydantic **exatamente** com os campos do JSON de §15.2 (`version, lease_id, valid_until, probe_interval_ms, probe_resolution, probe_jpeg_quality, stable_probe_count, full_frames, full_resolution, full_jpeg_quality, full_gap_ms, expected_pages, end{manual_enabled, visual_marker_enabled, open_hand_enabled, soft_idle_seconds, hard_idle_seconds}`).

**Passo 3.2.2** — Construir a policy a partir de settings + overrides da sessão; gravar a policy emitida em `Session.config_snapshot` (§70).

**Passo 3.2.3** — Implementar **lease**: `lease_id` + `valid_until` curtos; renovação por heartbeat; expiração não derruba a captura, apenas impede o Android de assumir novas regras (§15.2).

**Passo 3.2.4** — `GET /api/v1/gateway/session/{id}/policy` retorna a policy corrente com `version` e `lease`.

**Passo 3.2.5** — Comportamento offline documentado e testado: sem 4G, o Android opera dentro da policy vigente, armazena localmente e sincroniza ao reconectar; o servidor aceita eventos com `received_android_at` no passado, ordenando por esse campo.

---

## Etapa 3.3 — Análise de PROBE

**Passo 3.3.1** — `POST /api/v1/gateway/session/{id}/probe-analysis`: recebe probe (imagem pequena e/ou metadados) e calcula os sinais de §15.3: document presence, blur, perceptual hash, exposição, orientação, estabilidade, provável mudança de página, possível END.

**Passo 3.3.2** — Regra de §15.3: **não** executar OCR completo em probes.

**Passo 3.3.3** — Manter estado de captura por sessão em `capture/state.py`: último pHash aceito, contador de estabilidade, timestamps de atividade, burst em andamento. Persistir o mínimo necessário no Postgres para sobreviver a restart da API (Invariante: reinício da API não corrompe, §61).

**Passo 3.3.4** — Probes **não** são armazenados como frames de prova; se guardados, vão para `audit-exports` com TTL curto e nunca viram `LogicalPage`.

---

## Etapa 3.4 — Detecção de candidato e ciclo FULL

**Passo 3.4.1** — Implementar o critério configurável de §15.4:
```text
document_present AND stability_count >= N AND perceptual_distance >= threshold AND NOT end_marker
```
Cada termo com parâmetro próprio em config.

**Passo 3.4.2** — Ao detectar candidato, emitir comando `CAPTURE_FULL` (§15.5) com `full_frames=3`, `full_resolution=UXGA`, `full_jpeg_quality`, `full_gap_ms`, e `command_cursor` monotônico.

**Passo 3.4.3** — Aguardar burst completo **ou** timeout recuperável. Timeout ⇒ `CAPTURE_INCOMPLETE`, com política de novo burst (não avança página).

**Passo 3.4.4** — O `command_cursor` garante que comandos duplicados/atrasados do Android não gerem bursts extras.

---

## Etapa 3.5 — Materialização de página lógica

**Passo 3.5.1** — Ao fechar burst, pontuar todos os frames (3.1.2) e aplicar limiar de aceitação configurável.

**Passo 3.5.2** — Se **pelo menos um** frame passar (§15.7): rankear, definir `primary`, os demais como `alternate` (com `rank`), criar `LogicalPage` com `logical_index += 1`, gravar `LogicalPageFrame`, e criar `ImageArtifact` tipo `original` apontando para a key de `pages/{logical_index}/original.jpg`.

**Passo 3.5.3** — Se **nenhum** passar: solicitar novo burst do mesmo candidato e **não** incrementar `logical_index`. Após K tentativas (configurável), registrar `NO_USABLE_FRAME` e decidir por política (seguir com melhor frame marcado como degradado **ou** pular com falha — comportamento configurável, default: seguir marcando `LogicalPage.status=degraded`).

**Passo 3.5.4** — Invariante 2 (§10): `LogicalPage` só nasce de burst FULL válido ou recuperação equivalente. Teste dedicado.

**Passo 3.5.5** — Invariante 3 (§10): o marcador de FIM **nunca** vira página lógica. Teste dedicado.

**Passo 3.5.6** — Emitir evento `logical_page.accepted` no event bus (consumido pelo SSE na Fase 10).

---

## Etapa 3.6 — Encerramento redundante

**Passo 3.6.1** — Implementar `capture/end_detection.py` avaliando as 5 condições na **ordem de prioridade** de §16:
1. `logical_pages >= expected_pages`
2. finalização manual
3. marcador visual
4. mão aberta validada
5. inatividade conservadora

**Passo 3.6.2** — Mão aberta (§16.1) exige **todas** as condições, nunca detecção única:
```text
open_hand_confidence >= threshold AND no_exam_document
AND confirmations >= 2 AND confirmations_window <= 5s
```

**Passo 3.6.3** — `soft_idle` (§16.2): apenas alerta/evento, **não** encerra.

**Passo 3.6.4** — `hard_idle` (§16.2): só encerra se **todas**: nenhum upload pendente, nenhum FULL em andamento, nenhuma mudança recente, consenso de cena.

**Passo 3.6.5** — `POST /api/v1/gateway/session/{id}/end-signal` e `POST /api/v1/sessions/{id}/finish-capture` (admin) convergem para o mesmo caminho de código, com `end_reason` distinto.

**Passo 3.6.6** — Transição para `CAPTURE_END_CANDIDATE` antes de travar; condição refutada volta para `CAPTURING` com evento.

---

## Etapa 3.7 — LOCK_SESSION

**Passo 3.7.1** — Implementar `capture/lock.py` executando **em uma transação**, na ordem exata de §16.3:
1. confirmar `end_reason`;
2. status `CAPTURE_LOCKING`;
3. validar captures (bursts fechados, sem pendência);
4. fechar o conjunto de frames;
5. criar snapshot (`config_snapshot` + `provider_snapshot`);
6. status `LOCKED`;
7. iniciar `ProcessExamWorkflow`.

**Passo 3.7.2** — Nesta fase, o passo 7 é um **hook injetável** (`WorkflowStarter` port) com implementação no-op registrando evento; a implementação real chega na Fase 4. Isso mantém a fronteira de fases.

**Passo 3.7.3** — Idempotência do LOCK: chamar duas vezes produz o mesmo resultado e **um** disparo de workflow (usar `workflow_id = f"process-exam-{session_public_id}"`).

**Passo 3.7.4** — Após `LOCKED`, o conjunto de frames é imutável (Invariante 1).

---

## Etapa 3.8 — Simulador de prova e testes

**Passo 3.8.1** — Criar `scripts/simulate_exam.py`: encena uma prova completa — sequência de probes, mudanças de página, bursts, página repetida, burst ruim, marcador de fim, mão aberta, inatividade.

**Passo 3.8.2** — Testes obrigatórios (§53/FASE 3): página duplicada não cria nova `LogicalPage`; página nova cria; burst inteiramente ruim não incrementa índice; encerramento manual; `expected_pages` atingido; evento de mão aberta falso (1 confirmação) **não** encerra; mão aberta válida encerra; `soft_idle` não encerra; `hard_idle` com upload pendente não encerra.

**Passo 3.8.3** — Teste de restart: derrubar a API no meio da captura e retomar sem corromper contadores nem duplicar páginas.

## DoD da FASE 3

- [ ] Simulador produz N páginas lógicas corretamente
- [ ] Nenhum PROBE gera Activity de Temporal
- [ ] Invariantes 1, 2 e 3 com teste próprio e verde
- [ ] As 5 condições de encerramento implementadas com a prioridade de §16
- [ ] LOCK_SESSION atômico, idempotente e com snapshot
- [ ] **1ª milestone (§66) atingida**

---

# FASE 4 — Temporal skeleton

**Objetivo:** após LOCK, o workflow percorre todos os estados com providers fake e **retoma após restart do worker**.
**Fora de escopo:** lógica real de OCR/LLM/áudio.
**Seções do spec cobertas:** §2.3, §17, §42, §43.

---

## Etapa 4.1 — Cliente e configuração

**Passo 4.1.1** — `workflows/client.py`: conexão com `TEMPORAL_ADDRESS`, `TEMPORAL_NAMESPACE`, TLS opcional. **Nenhuma** dependência de detalhe de hospedagem (§2.3).

**Passo 4.1.2** — Data converter com payload compacto; proibir passagem de blobs (§17.2) — validado por teste que falha se algum tipo de entrada/saída de Activity contiver `bytes` acima de N KB.

**Passo 4.1.3** — Implementar `WorkflowStarter` real, substituindo o no-op do Passo 3.7.2, com `workflow_id` determinístico e política de reuso que impede duplicidade.

---

## Etapa 4.2 — Worker

**Passo 4.2.1** — `workflows/worker.py`: registra workflow e activities, task queue de `TEMPORAL_TASK_QUEUE`, limites de concorrência vindos de §44 (`image=1`, `ocr=3`, `llm=4–6`, `audio=1–2`).

**Passo 4.2.2** — Executor separado para activities CPU-bound; activities de I/O em asyncio.

**Passo 4.2.3** — Shutdown gracioso (drenar activities em execução, respeitar heartbeat).

**Passo 4.2.4** — Habilitar o alvo `make worker` (substituindo o stub da Fase 0) e o serviço `pages-worker` no compose de dev.

---

## Etapa 4.3 — `ProcessExamWorkflow`

**Passo 4.3.1** — Implementar `workflows/process_exam.py` com as **20 etapas** de §17.1, na ordem exata:
```text
1 ValidateLockedSession        11 VerifyQuestions
2 MaterializeLogicalPages      12 ArbitrateDisagreements
3 PreprocessPages              13 RescueFailedAnswers
4 RunOCR                       14 EvaluateGate2
5 ReconstructExam              15 EmitPostCorrectionStatus
6 RescueIncompleteQuestions    16 GenerateAnswerAudio
7 EvaluateGate1                17 AssembleFinalAudio
8 EmitPreCorrectionStatus      18 ValidateFinalAudio
9 RetrieveKnowledge            19 PublishFinalAudio
10 SolveQuestions              20 CompleteSession
```

**Passo 4.3.2** — Cada etapa chama `transition_session()` no estado correspondente de §9, via activity dedicada (o workflow não toca no banco diretamente).

**Passo 4.3.3** — Implementar os **desvios de gate** dentro do workflow (§23, §33, §58): Gate 1 reprovado ⇒ `BLOCKED_GATE_1` → status audio → encerra sem RAG/Solver. Gate 2 reprovado ⇒ `BLOCKED_GATE_2` → status audio de falha → encerra sem áudio de gabarito.

**Passo 4.3.4** — Invariante 5 (§10): estruturalmente impossível chamar `SolveQuestions` sem Gate 1 aprovado — garantir por fluxo de código **e** por checagem defensiva dentro da activity.

**Passo 4.3.5** — Invariante 6 (§10): mesma garantia para TTS de gabarito × Gate 2.

**Passo 4.3.6** — Todas as activities desta fase são **fake determinísticas** (`workflows/activities/fakes.py`), lendo/gravando estado real no banco onde já existe (sessão, eventos) e simulando o resto.

---

## Etapa 4.4 — Políticas de timeout, retry e heartbeat

**Passo 4.4.1** — Criar `workflows/policies.py` centralizando timeouts de §42:
```text
HTTP connect 10s | HTTP read 60s | Google OCR 90s | Azure OCR 90s
Anthropic solver 180s | Anthropic arbiter 240s | DeepSeek 240s
Supabase 30s | FFmpeg 120s
```
Regra de §42: `activity timeout > provider timeout + retries internos`. Implementar como função que **calcula** o timeout da activity a partir do timeout do provider e do retry budget — não como número mágico.

**Passo 4.4.2** — Retry budget de §43 em um único lugar: `provider internal retries = 2`, `Temporal activity attempts = 3`, `rescue rounds = 3`, com **limite global** que impede a multiplicação sair de controle. Persistir `attempt` em toda entidade que tem o campo.

**Passo 4.4.3** — Classificação de §17.3: mapear `RetryableError` → retryable e `NonRetryableError` → `non_retryable_error_types` do Temporal. Teste que prova que `invalid schema`, `unsupported image`, `missing session data`, `auth error` e `bad request` **não** são retentados.

**Passo 4.4.4** — Heartbeat obrigatório (§17.4) em activities longas: OCR local, FFmpeg, ingestion de conhecimento. Implementar helper `with_heartbeat(...)` e usá-lo já nas fakes longas.

---

## Etapa 4.5 — Versionamento de workflow

**Passo 4.5.1** — Adotar `workflow.patched()`/`get_version` desde o início, com registro em `docs/workflow.md` de cada patch id.

**Passo 4.5.2** — Regra: mudança incompatível exige patch versionado (§17.5). **Nunca** alterar lógica de workflow que pode estar em execução sem patch.

---

## Etapa 4.6 — Testes da FASE 4

**Passo 4.6.1** — `tests/workflows/test_process_exam_happy.py` com time-skipping: percorre as 20 etapas e termina em `COMPLETED`.

**Passo 4.6.2** — Caminhos de gate: Gate 1 reprovado; Gate 2 reprovado; degradado 90–99% em ambos.

**Passo 4.6.3** — Retry: activity que falha 2× e sucede na 3ª; activity com erro não-retryable falha imediatamente.

**Passo 4.6.4** — **Durabilidade**: matar e reiniciar o worker no meio da execução; o workflow retoma do ponto correto sem repetir efeito colateral (idempotência das activities).

**Passo 4.6.5** — Teste que nenhuma activity recebe/retorna blob grande (§17.2).

## DoD da FASE 4

- [ ] Após LOCK, o workflow percorre todos os estados com providers fake
- [ ] Restart do worker retoma sem duplicar efeito
- [ ] Timeouts derivados por fórmula, não hardcode disperso
- [ ] Retry budget global respeitado
- [ ] Erros não-retryable não são retentados
- [ ] Invariantes 5 e 6 garantidas estruturalmente

---

# FASE 5 — Imagem + OCR

**Objetivo:** uma página real gera OCR normalizado, armazenado e auditável.
**Seções do spec cobertas:** §18, §19, §41 (parcial), §42, §59 (OCR).

---

## Etapa 5.1 — Gerenciador de arquivos temporários

**Passo 5.1.1** — `common/temp_manager.py`: diretório por sessão `LOCAL_TEMP_ROOT/{session_id}/` (§18.4), context manager que apaga em `finally`, sempre.

**Passo 5.1.2** — Quota: uso total ≤ `LOCAL_TEMP_MAX_GB` (default 2 GB). Ao exceder: **interromper geração de derivados não essenciais** e emitir alerta (§18.4).

**Passo 5.1.3** — Janitor periódico por `LOCAL_TEMP_TTL_HOURS`, reusando `scripts/cleanup_temp.py`.

**Passo 5.1.4** — Métrica `local_temp_bytes` exposta (§39.5).

---

## Etapa 5.2 — Pré-processamento de imagem

**Passo 5.2.1** — `image/preprocess.py` com operações de §18.2, cada uma isolada e opcional: `corrected_orientation`, `perspective`, `CLAHE`, `denoise`, `sharpen`, `threshold`.

**Passo 5.2.2** — Regra de §18.1/Invariante 8: **ORIGINAL nunca é modificado**. Todo derivado gera um novo `ImageArtifact` com `artifact_type` de §8.8 e key de §12.2.

**Passo 5.2.3** — Derivados são criados **apenas quando necessários** (§18.2) — pipeline dirigido por necessidade do OCR/reconstrução, não por padrão.

**Passo 5.2.4** — `image/crops.py`: recorte de região de questão (`question_crop`) e de mídia (`media_crop`), com coordenadas rastreáveis até a página original.

**Passo 5.2.5** — Toda operação OpenCV via executor dedicado, `MAX_IMAGE_PROCESSING_CONCURRENCY=1` (§18.3).

**Passo 5.2.6** — Activity real `PreprocessPages` substituindo a fake, com heartbeat.

---

## Etapa 5.3 — Abstração de OCR

**Passo 5.3.1** — `domain/ports/ocr.py` com a interface **literal** de §19:
```python
class OCRProvider(Protocol):
    async def analyze_page(self, request: OCRRequest) -> OCRResult: ...
```

**Passo 5.3.2** — `OCRRequest` (§19): original storage ref, derived refs, page index, hints, requested features.

**Passo 5.3.3** — `NormalizedOCRResult` (§19): text, blocks, lines, tokens, bounding boxes, reading order, tables, formulas (quando disponível), provider confidence, raw result ref.

**Passo 5.3.4** — Regra de §19.3: o formato bruto do vendor **não** trafega pelo domínio. Raw vai para o bucket `ocr-raw` (key de §12.2) e só a referência entra em `OCRRun.raw_storage_key`. A reconstrução consome **apenas** `NormalizedOCRResult`.

---

## Etapa 5.4 — Providers de OCR

**Passo 5.4.1** — `ocr/providers/google_document_ai.py` (§19.1): autenticação por `GOOGLE_APPLICATION_CREDENTIALS`, processor configurável, timeout 90s, mapeamento completo para `NormalizedOCRResult`, erros → `ReasonCode` (`OCR_PROVIDER_TIMEOUT`, `OCR_LOW_CONFIDENCE`, etc.).

**Passo 5.4.2** — `ocr/providers/azure_document_intelligence.py`: mesma porta, mesmo normalizador de saída, timeout 90s.

**Passo 5.4.3** — `ocr/providers/paddle.py`: implementação **opcional**, respeitando `PADDLE_OCR_ENABLED=false` por padrão (§19.2). Deve funcionar em dois modos: local (desabilitado por default na VPS de 2 vCPU) e **remoto** (worker HTTP em outra máquina) — a escolha é de configuração.

**Passo 5.4.4** — Regra de CLAUDE.md: **o servidor continua funcionando com PaddleOCR desabilitado**. Teste dedicado provando isso.

**Passo 5.4.5** — `ocr/providers/fake.py`: provider determinístico para testes, capaz de simular sucesso, baixa confiança, timeout, 500 e schema inválido.

---

## Etapa 5.5 — Política de seleção e fallback de OCR

**Passo 5.5.1** — `ocr/policy.py` implementando §19.2 e a cadeia de §59:
```text
Google → retry → Azure → alternate frame → preprocessing variant → Vision → Paddle (opcional) → failed
```

**Passo 5.5.2** — Caso "incerteza" (§19.2): rodar segundo provider quando a confiança normalizada ficar abaixo do limiar configurável, e registrar ambos os `OCRRun`.

**Passo 5.5.3** — Circuit breaker por provider (§41): N falhas consecutivas ⇒ abre; direciona ao fallback; half-open depois de janela configurável. **Nunca** insistir dezenas de vezes por página.

**Passo 5.5.4** — Nenhum fallback silencioso: cada troca de provider gera `AuditEvent` com `reason_code` e aparece no painel (§59).

**Passo 5.5.5** — Activity real `RunOCR` com paralelismo limitado por `MAX_OCR_CONCURRENCY=3` (§44).

---

## Etapa 5.6 — Testes da FASE 5

**Passo 5.6.1** — Contratos por provider: sucesso; timeout; 429; 5xx; resposta malformada; confiança baixa.

**Passo 5.6.2** — Fallback: Google indisponível ⇒ Azure assume e o evento é registrado.

**Passo 5.6.3** — Circuit breaker: abre, desvia, e volta em half-open.

**Passo 5.6.4** — Imutabilidade do original após todo o pipeline de derivados.

**Passo 5.6.5** — Quota de temp: exceder limite interrompe derivados não essenciais e alerta.

**Passo 5.6.6** — Smoke test opcional com provider real, marcado `@pytest.mark.slow` e ativado só por `USE_REAL_OCR=true`.

## DoD da FASE 5

- [ ] Página real gera OCR normalizado armazenado e auditável
- [ ] Raw do vendor fora do domínio, apenas por referência
- [ ] Fallback Google→Azure funcionando e visível
- [ ] Sistema roda com `PADDLE_OCR_ENABLED=false`
- [ ] Original nunca sobrescrito
- [ ] Temp com TTL, quota e limpeza garantida em `finally`

---

# FASE 6 — Reconstrução + Gate 1

**Objetivo:** o dataset dourado reconstrói números e alternativas dentro da meta, e o Gate 1 decide corretamente.
**Seções do spec cobertas:** §20, §21, §22, §23, §34 (mensagens de Gate 1), §51, §60.

---

## Etapa 6.1 — Contratos de reconstrução

**Passo 6.1.1** — Criar `domain/models/reconstruction.py` com o schema **exato** de §21.2: `questions[]` com `question_number, text, alternatives{}, page_refs[], media_refs[], source_regions[], completeness, flags[]`.

**Passo 6.1.2** — Validar tudo com Pydantic (§21.2). Nenhuma extração por regex (CLAUDE.md).

**Passo 6.1.3** — Definir vocabulário fechado para `completeness` (`complete|partial|missing`) e para `flags` (ligados aos `ReasonCode` de §40).

---

## Etapa 6.2 — Prompts versionados

**Passo 6.2.1** — Criar `prompts/reconstruction/v1.md` (§21.3). **Proibido** prompt hardcoded em Python.

**Passo 6.2.2** — Criar `llm/prompt_registry.py`: carrega prompt do disco, calcula SHA-256, expõe `prompt_version` e `prompt_hash`, e grava ambos em `Question.reconstruction_metadata` e `AnswerAttempt.prompt_version`.

**Passo 6.2.3** — Teste: alterar o arquivo de prompt muda o hash registrado; prompt ausente falha rápido.

---

## Etapa 6.3 — Visual Understanding

**Passo 6.3.1** — `domain/ports/vision.py` com a interface literal de §20:
```python
class VisionProvider(Protocol):
    async def analyze_region(self, request: VisionRequest) -> VisionResult: ...
```

**Passo 6.3.2** — Implementar `vision/anthropic_vision.py` cobrindo os usos de §20: gráfico, química, circuito, geometria, tirinha, mapa, fotografia, tabela complexa, região com OCR conflitante.

**Passo 6.3.3** — Regra de §20: **Vision não é o Solver**. A saída alimenta a reconstrução/evidência; nunca produz resposta final.

**Passo 6.3.4** — Provider fake determinístico para testes.

---

## Etapa 6.4 — Motor de reconstrução

**Passo 6.4.1** — Montar o input de §21.1 por página, em ordem: primary original, alternates, OCR normalizado, layout, crops, page number inferido.

**Passo 6.4.2** — Implementar `reconstruction/engine.py` com janelamento por páginas (com sobreposição), para suportar **questão que atravessa páginas**.

**Passo 6.4.3** — Chamar o LLM com structured output validado; falha de schema segue a política de §28 (repair → fallback → FAILED).

**Passo 6.4.4** — Persistir `Question` com status inicial `DISCOVERED`/`INCOMPLETE`, `page_refs`, `media_refs`, `ocr_refs`, `reconstruction_metadata` (prompt version/hash, provider, custo, latência).

---

## Etapa 6.5 — Validações determinísticas

**Passo 6.5.1** — Implementar `reconstruction/validators.py` com **todas** as checagens de §21.4: números de questão únicos; ordem plausível; alternativas não vazias; números esperados; lacunas; duplicatas; continuidade.

**Passo 6.5.2** — Cada falha marca a questão como `INCOMPLETE` com `failure_reason` = `ReasonCode` (`QUESTION_NUMBER_MISSING`, `QUESTION_ALTERNATIVES_INCOMPLETE`, `QUESTION_VISUAL_AMBIGUITY`, …).

**Passo 6.5.3** — Regra de §60: **não preencher lacuna**, não inferir alternativa ausente sem evidência, não mascarar OCR ruim. Teste que prova que uma alternativa faltante não é inventada.

---

## Etapa 6.6 — Motor de rescue

**Passo 6.6.1** — Implementar `reconstruction/rescue.py` com as 9 estratégias de §22, **na ordem**:
1. alternate frame; 2. novo pré-processamento; 3. OCR secundário; 4. crop dirigido; 5. Vision Provider; 6. páginas anterior/posterior; 7. reconstrução específica; 8. comparação de variantes; 9. tentativa final multimodal.

**Passo 6.6.2** — Budget: `MAX_RECONSTRUCTION_RESCUE_ROUNDS=3` (§22, configurável — ver Anexo B-3). Loop infinito é proibido; contador persistido.

**Passo 6.6.3** — Cada tentativa registra `reason_code`, estratégia usada, resultado, custo e latência.

**Passo 6.6.4** — Estados: `INCOMPLETE → RESCUING → READY|FAILED`. Questão só vira `READY` se passar em todas as validações de 6.5.

**Passo 6.6.5** — Activity real `RescueIncompleteQuestions`, com paralelismo limitado e heartbeat.

---

## Etapa 6.7 — Gate 1

**Passo 6.7.1** — Implementar `domain/gates.py` com a fórmula **literal** de §23:
```python
required = ceil(expected_questions * minimum_ratio)
ready = count(Question.status == READY)
```

**Passo 6.7.2** — Três desfechos (§23):
| Condição | Ação |
|---|---|
| `ready == expected` | success; áudio "70 de 70…" |
| `required <= ready < expected` | prosseguir; `session.degraded_mode = true`; registrar falhas; áudio informa quantidade |
| `ready < required` | `BLOCKED_GATE_1`; **não** iniciar RAG/Solver; status de falha; encerrar processamento acadêmico |

**Passo 6.7.3** — Testes numéricos obrigatórios (§61): com `expected=70` e `ratio=0.90` ⇒ `required=63`; **63/70 passa**, **62/70 bloqueia**, 70/70 é success, 69/70 é degradado.

**Passo 6.7.4** — Registrar métrica `gate1_ratio` e `AuditEvent` com o cálculo completo (valores de entrada, required, ready, decisão).

---

## Etapa 6.8 — Mensagens de status (Gate 1)

**Passo 6.8.1** — Criar `audio/messages.py` com os textos **literais** de §34 para os três casos de Gate 1, parametrizados por números:
```text
"Captura validada. {ready} de {expected} questões reconhecidas. Iniciando correção."
"{ready} de {expected} questões reconhecidas. {failed} falhas registradas. Iniciando correção."
"Falha de processamento. {ready} de {expected} questões válidas. {failed} falhas. Processo encerrado."
```

**Passo 6.8.2** — Activity `EmitPreCorrectionStatus` publica a mensagem como evento (o áudio em si é da Fase 9; nesta fase o texto é gerado e auditado).

---

## Etapa 6.9 — Dataset dourado e métricas

**Passo 6.9.1** — Criar `tests/fixtures/golden/` (§51) com: imagens, páginas lógicas esperadas, questões esperadas, respostas esperadas, flags esperadas.

**Passo 6.9.2** — Regra de §51: **não versionar material confidencial em repositório público**. Definir política: dataset pequeno sintético/anonimizado no Git; dataset real fora do Git (Supabase `audit-exports` ou storage privado), baixado por script `scripts/fetch_golden_dataset.py` com credencial local.

**Passo 6.9.3** — Criar `scripts/eval_golden.py` que mede as métricas de §51: page detection precision/recall, question reconstruction rate, answer accuracy, Gate 1 ratio, Gate 2 ratio, runtime, provider fallback rate. Saída em JSON versionável em `docs/benchmarks/`.

**Passo 6.9.4** — E2E simulado pequeno de §50.4: **5 páginas / 10 questões**, providers fake determinísticos, sem API real.

## DoD da FASE 6

- [ ] Golden dataset reconstrói números e alternativas dentro da meta definida
- [ ] Prompt em arquivo, versionado por hash
- [ ] Todas as 7 validações determinísticas de §21.4 implementadas
- [ ] Rescue com budget finito e `reason_code` registrado
- [ ] Gate 1 testado em 100%, 90% (63/70) e 89% (62/70)
- [ ] Nenhuma lacuna preenchida por inferência
- [ ] **2ª milestone (§67) atingida**

---

# FASE 7 — Knowledge + RAG

**Objetivo:** queries de benchmark recuperam os chunks corretos, com métricas registradas.
**Seções do spec cobertas:** §8.11–§8.13, §13.6, §24, §25, §74.

---

## Etapa 7.1 — Ingestão de documentos

**Passo 7.1.1** — Implementar o pipeline **exato** de §24:
```text
upload → extract → normalize → split → metadata → embed → pgvector → FTS → validate → active
```
Cada estágio é uma função isolada e testável; o documento só vira `active=true` no fim.

**Passo 7.1.2** — Extractors de §24.1 (V1): PDF, Markdown, TXT, CSV, texto colado. DOCX **fora** da V1 (registrar como backlog explícito).

**Passo 7.1.3** — Upload do arquivo original para o bucket `knowledge`, com sha256; deduplicação por hash.

**Passo 7.1.4** — Ingestão longa roda como job com heartbeat (§17.4).

---

## Etapa 7.2 — Chunking estrutural

**Passo 7.2.1** — Implementar `rag/chunking.py` que **preserva** (§24.2): títulos, capítulos, seções, páginas, tabelas, tópicos.

**Passo 7.2.2** — Regra de §24.2: tamanho fixo ingênuo **não** pode ser a única regra. Estratégia: split hierárquico por estrutura → agrupamento por orçamento de tokens → overlap configurável.

**Passo 7.2.3** — Cada chunk grava `page_number`, `section`, `metadata` (disciplina, assunto, origem) e `chunk_index`.

---

## Etapa 7.3 — Embeddings

**Passo 7.3.1** — `domain/ports/embedding.py` conforme §24.3:
```python
class EmbeddingProvider(Protocol):
    async def embed_documents(...)
    async def embed_query(...)
```

**Passo 7.3.2** — Implementar ao menos dois providers configuráveis para o benchmark de §24.3 (português + conteúdo acadêmico) + um fake determinístico.

**Passo 7.3.3** — Regra de §24.3: **o schema não pode depender da marca do provider**. A dimensão do vetor é configuração de migration (Anexo B-8); trocar de provider com dimensão diferente exige migration nova e reindexação, documentada em runbook.

**Passo 7.3.4** — Registrar em `KnowledgeChunk.metadata` qual provider/modelo/dimensão gerou o embedding.

---

## Etapa 7.4 — Índices no Postgres

**Passo 7.4.1** — Migration com: coluna `embedding VECTOR(dim)`, índice **HNSW** quando fizer sentido (§74), coluna `fts TSVECTOR` gerada com configuração `portuguese` + `unaccent`, e índice GIN sobre `fts`.

**Passo 7.4.2** — Trigger/generated column mantendo `fts` sincronizado com `text`.

**Passo 7.4.3** — Regra de §25/§74: usar Postgres + pgvector + tsvector. **Não** depender de Vector Buckets alpha.

---

## Etapa 7.5 — Retrieval híbrido

**Passo 7.5.1** — Implementar `rag/retrieval.py` com os 7 estágios de §25, na ordem:
1. query expansion curta; 2. FTS; 3. vector search; 4. **Reciprocal Rank Fusion**; 5. filtros por disciplina/assunto; 6. reranking; 7. top evidence.

**Passo 7.5.2** — RRF implementado como função pura e testada isoladamente (entrada: listas ranqueadas; saída: ranking fundido).

**Passo 7.5.3** — Contrato de saída **exato** de §25.1: `{question_id, query, hits[{chunk_id, document_id, score, text, page, source}]}`.

**Passo 7.5.4** — Reranker plugável (cross-encoder ou LLM leve), desabilitável por config.

**Passo 7.5.5** — Persistir cada execução em `RetrievalRun` (§8.13) para auditoria.

---

## Etapa 7.6 — Endpoints de conhecimento

**Passo 7.6.1** — Implementar §13.6, todos sob autenticação admin (a auth completa chega na Fase 10; nesta fase usar a dependência de auth já existente, mesmo que mínima):
```text
POST   /api/v1/knowledge/documents
GET    /api/v1/knowledge/documents
GET    /api/v1/knowledge/documents/{id}
DELETE /api/v1/knowledge/documents/{id}
POST   /api/v1/knowledge/documents/{id}/reindex
POST   /api/v1/knowledge/search-test
```

**Passo 7.6.2** — `search-test` (§25.2) mede retrieval **sem chamar LLM** de solução, retornando hits, scores por estágio e latência.

**Passo 7.6.3** — `DELETE` é lógico (`active=false`) por padrão; remoção física exige flag explícita e audit event.

---

## Etapa 7.7 — Activity e benchmark

**Passo 7.7.1** — Activity real `RetrieveKnowledge`, executada **somente após Gate 1 aprovado** (§17.1, ordem 7→9).

**Passo 7.7.2** — Criar `scripts/benchmark_providers.py` (parte RAG, §52): A/B de embedding model, chunk size, RRF, top-K, reranker. Saída em `docs/benchmarks/rag_*.json`.

**Passo 7.7.3** — Testes: RRF determinístico; FTS em português com acentuação; filtro por disciplina; contrato de saída; `RetrievalRun` gravado; reindex idempotente.

## DoD da FASE 7

- [ ] Pipeline de ingestão completo com os 10 estágios de §24
- [ ] Chunking estrutural preservando títulos/seções/páginas/tabelas
- [ ] pgvector + FTS português + RRF funcionando no próprio Postgres
- [ ] `search-test` mede retrieval sem LLM
- [ ] Benchmark de pelo menos 2 modelos de embedding registrado
- [ ] Schema independente da marca do provider

---

# FASE 8 — Solver / Verifier / Arbiter

**Objetivo:** nenhuma questão obtém resposta final fora da política.
**Seções do spec cobertas:** §26, §27, §28, §29, §30, §31, §32, §41, §43, §59 (LLM), §60, §73.

---

## Etapa 8.1 — Porta de raciocínio

**Passo 8.1.1** — `domain/ports/reasoning.py` com a interface **literal** de §26:
```python
class ReasoningProvider(Protocol):
    async def solve(self, request: SolveRequest) -> SolveResult: ...
    async def verify(self, request: VerifyRequest) -> VerifyResult: ...
    async def arbitrate(self, request: ArbitrateRequest) -> ArbitrateResult: ...
```

**Passo 8.1.2** — Regra de §26: **nunca** importar SDK de vendor na camada de domínio. Teste estrutural que falha se `anthropic`/`openai`/`deepseek` aparecer em `domain/`.

**Passo 8.1.3** — Modelos de request/response neutros de vendor, com `evidence_refs`, `prompt_version`, `effort`, `provider`, `model`.

---

## Etapa 8.2 — Structured outputs

**Passo 8.2.1** — Implementar os três schemas **exatos** de §28:
- Solver: `{question_number, answer, evidence_ids[], needs_visual_recheck, ambiguity_flags[]}`
- Verifier: `{question_number, answer, evidence_ids[], verification_status, ambiguity_flags[]}`
- Arbiter: `{question_number, answer, decision, evidence_ids[], ambiguity_flags[]}`

**Passo 8.2.2** — Validação por Pydantic. Sequência de falha de §28, nesta ordem: (1) **repair retry**; (2) se continuar inválido, **provider fallback**; (3) se falhar, marcar attempt `FAILED`.

**Passo 8.2.3** — Invariante 7 (§10): a resposta final precisa ser **uma alternativa permitida pela questão**. Validação determinística após o parsing; letra fora do conjunto ⇒ attempt inválido, nunca aceito.

**Passo 8.2.4** — Proibição literal de CLAUDE.md: **nenhum regex** para extrair resposta.

---

## Etapa 8.3 — Provider Anthropic

**Passo 8.3.1** — `llm/providers/anthropic_provider.py` usando modelos de `ANTHROPIC_MODEL_SOLVER|VERIFIER|ARBITER` (§27.1). **Nenhum** ID de modelo hardcoded fora do settings.

**Passo 8.3.2** — Timeouts de §42: solver 180s, arbiter 240s. Retries internos = 2 (§43). Respeitar 429 e headers de retry (§32).

**Passo 8.3.3** — Entrada multimodal: texto da questão, alternativas, media crops, região original, evidências OCR e RAG (§29).

**Passo 8.3.4** — §27.6: **não armazenar chain-of-thought bruto**. Persistir apenas resposta estruturada, evidências, metadados e — se configurado — um rationale curto para auditoria. O funcionamento **nunca** depende de reasoning privado.

---

## Etapa 8.4 — Provider DeepSeek

**Passo 8.4.1** — `llm/providers/deepseek_provider.py` com model id configurável, default `deepseek-v4-pro` (§27.2, §73).

**Passo 8.4.2** — Suportar (§73): thinking enabled; reasoning effort `high`; `max` em arbitragem/fallback de alta complexidade quando configurado; parsing JSON/estruturado validado localmente; timeouts (240s); 429; retries; circuit breaker.

**Passo 8.4.3** — Adapter isolado: trocar de modelo **não** pode exigir mudança em Solver/Verifier/Arbiter (§73). Teste que prova o isolamento.

---

## Etapa 8.5 — Política de fallback e resiliência

**Passo 8.5.1** — Implementar `llm/fallback_policy.py` com os gatilhos **exatos** de §27.3. Fallback é acionado por: timeout após retry budget; 429 persistente; 5xx persistente; provider indisponível; resposta sem conformidade de schema após repair retry; erro técnico do provider.

**Passo 8.5.2** — Regra explícita de §27.3: **fallback não é acionado porque o Claude escolheu uma letra inesperada**. Teste que prova que divergência de resposta **não** dispara fallback (dispara Arbiter).

**Passo 8.5.3** — Cadeia completa de §59:
```text
Claude Opus 5 → retry → schema repair → retry → DeepSeek V4 Pro → retry → failed
```

**Passo 8.5.4** — Modo degradado (§27.4): uso de DeepSeek ⇒ `session.degraded_mode = true` e `answer_attempt.degraded_provider = true`; painel exibe "Fallback de IA utilizado em N questões".

**Passo 8.5.5** — Falha dos dois (§27.5): questão **não recebe letra**, status `FAILED`, entra em rescue/retry, e o Gate 2 decide.

**Passo 8.5.6** — Circuit breaker por provider (§41): falhas consecutivas abrem o circuito, direcionam ao fallback, half-open depois.

**Passo 8.5.7** — Flag opcional `DEEPSEEK_CROSSCHECK_ON_HIGH_RISK=false` (§27.3) implementada como configuração desligada por padrão.

---

## Etapa 8.6 — Concorrência

**Passo 8.6.1** — Semáforo **por provider** (§32), limite `MAX_LLM_CONCURRENCY` começando em **4** e medindo antes de subir para 6.

**Passo 8.6.2** — Proibido disparar 70 Solver + 70 Verifier simultâneos (§32). Teste que prova o teto de concorrência.

**Passo 8.6.3** — Respeitar 429 e `Retry-After` com backoff exponencial + jitter (§41).

---

## Etapa 8.7 — Solver

**Passo 8.7.1** — Prompt em `prompts/solver/v1.md`, versionado por hash (mesma mecânica de 6.2).

**Passo 8.7.2** — Input de §29: texto da questão, alternativas, media crops, região original, evidências OCR, evidências RAG, versão do prompt.

**Passo 8.7.3** — Saída: **somente uma das alternativas permitidas**; não pedir texto longo (§29).

**Passo 8.7.4** — Persistir `AnswerAttempt` com `role=solver`, provider, model, effort, prompt_version, latência, tokens e custo estimado (§8.14).

---

## Etapa 8.8 — Verifier independente

**Passo 8.8.1** — Prompt em `prompts/verifier/v1.md`.

**Passo 8.8.2** — Regra crítica de §30: o Verifier **resolve independentemente**. É proibido enviar a conclusão do Solver ("O Solver respondeu C. Confirme."). Implementar teste que inspeciona o payload do Verifier e **falha** se a resposta do Solver aparecer nele.

**Passo 8.8.3** — Comparação **determinística** entre Solver e Verifier feita em código, fora do LLM (§30).

---

## Etapa 8.9 — Arbiter

**Passo 8.9.1** — Prompt em `prompts/arbiter/v1.md`.

**Passo 8.9.2** — Gatilhos de §31: solver ≠ verifier; ambiguity flag crítico; OCR conflitante; dependência visual crítica; conflito de evidência.

**Passo 8.9.3** — Input do Arbiter pode conter (§31): resultado do Solver, resultado do Verifier, evidências, crops adicionais, OCRs divergentes.

**Passo 8.9.4** — Se continuar ambíguo (§31): rescue → nova arbitragem **dentro do budget** → `FAILED` se não resolver. `ARBITRATION_UNRESOLVED` registrado.

---

## Etapa 8.10 — Resposta final

**Passo 8.10.1** — Implementar `llm/finalize.py` gravando `FinalAnswer` (§8.15) com `decision_source` (`solver_verifier_agreement | arbiter | rescue`), `validated`, `degraded_provider`, `evidence_refs`.

**Passo 8.10.2** — Invariante 4 (§10): questão `FAILED` **nunca** recebe `FinalAnswer`. Garantir por constraint/checagem + teste.

**Passo 8.10.3** — Invariante 10 (§10): falha de provider **nunca** vira "resposta provável". Teste que prova que timeout duplo ⇒ `FAILED`, não uma letra.

**Passo 8.10.4** — Activity real `RescueFailedAnswers`, com budget e reason codes.

---

## Etapa 8.11 — Testes da FASE 8

Matriz obrigatória (§50.2, §53/FASE 8):

**Passo 8.11.1** — Opus success (caminho feliz).
**Passo 8.11.2** — Opus timeout → DeepSeek assume, `degraded_provider=true`.
**Passo 8.11.3** — Opus 429 persistente → DeepSeek.
**Passo 8.11.4** — Schema inválido → repair retry → fallback → FAILED.
**Passo 8.11.5** — Disagreement solver≠verifier → Arbiter decide (sem fallback de provider).
**Passo 8.11.6** — Ambos falham → questão `FAILED`, sem letra.
**Passo 8.11.7** — Letra fora das alternativas permitidas → rejeitada (Invariante 7).
**Passo 8.11.8** — Verifier não recebe a resposta do Solver (inspeção de payload).
**Passo 8.11.9** — Nenhum reasoning bruto persistido (varredura do banco e dos logs).
**Passo 8.11.10** — Teto de concorrência respeitado.

## DoD da FASE 8

- [ ] Opus primary, DeepSeek fallback **técnico** (nunca por divergência de letra)
- [ ] Verifier comprovadamente independente
- [ ] Arbiter acionado pelos 5 gatilhos de §31
- [ ] Structured outputs validados por Pydantic, sem regex
- [ ] Nenhum reasoning privado armazenado
- [ ] Invariantes 4, 7 e 10 testadas
- [ ] **3ª milestone (§68) atingida**

---

# FASE 9 — Gate 2 + TTS + Áudio

**Objetivo:** o áudio final contém exatamente as respostas validadas, com as pausas corretas.
**Seções do spec cobertas:** §13.7, §33, §34 (Gate 2), §35, §36, §59 (TTS).

---

## Etapa 9.1 — Gate 2

**Passo 9.1.1** — Implementar em `domain/gates.py` a fórmula **literal** de §33:
```python
validated = count(FinalAnswer.validated == True)
required  = ceil(expected_questions * minimum_ratio)
```

**Passo 9.1.2** — Desfechos (§33.1–§33.3):
| Condição | Ação |
|---|---|
| 100% | áudio completo |
| 90–99% | prossegue com aviso; áudio contém **somente** as validadas |
| <90% | `BLOCKED_GATE_2`; **sem** áudio de gabarito; apenas áudio de falha/status |

**Passo 9.1.3** — Regra de §33.2: **não** inserir "Questão 17, sem resposta" no gabarito. Teste que prova a ausência de itens não validados.

**Passo 9.1.4** — Testes numéricos: 70/70; 63/70 (passa); 62/70 (bloqueia).

**Passo 9.1.5** — Métrica `gate2_ratio` + `AuditEvent` com o cálculo completo.

---

## Etapa 9.2 — Abstração e providers de TTS

**Passo 9.2.1** — `domain/ports/tts.py` com a interface literal de §35:
```python
class TTSProvider(Protocol):
    async def synthesize(self, request: TTSRequest) -> TTSSegment: ...
```

**Passo 9.2.2** — `audio/providers/google_tts.py` e `audio/providers/azure_tts.py` (§35), selecionados por `TTS_PROVIDER` / `TTS_FALLBACK_PROVIDER` (Anexo B-4).

**Passo 9.2.3** — Cadeia de fallback de §59: `Google → retry → Azure → failed`, com `TTS_PROVIDER_FAILED` e evento visível.

**Passo 9.2.4** — Provider fake determinístico (gera silêncio com duração proporcional ao texto) para testes sem API.

**Passo 9.2.5** — Benchmark de português brasileiro antes de congelar a voz (§35, §52), registrado em `docs/benchmarks/tts_*.md`.

---

## Etapa 9.3 — Plano de áudio

**Passo 9.3.1** — Implementar `audio/plan.py` gerando o roteiro determinístico do MP3 final conforme §36:
- **Rodada 1**: voz levemente mais lenta, **2 segundos** entre itens;
- **após a última resposta da rodada 1**: **20 segundos** de silêncio;
- **Rodada 2**: velocidade normal, **1 segundo** entre itens.

**Passo 9.3.2** — Texto de cada item, formato **literal** de §36.1:
```text
Questão 1. Letra B.
```
Sem explicações. Somente número da questão + alternativa (§1 do spec, item 13).

**Passo 9.3.3** — O plano é um objeto serializável (lista de segmentos + silêncios) validado antes de qualquer síntese — permite testar toda a estrutura sem chamar TTS.

**Passo 9.3.4** — Apenas questões com `FinalAnswer.validated=true` entram no plano.

---

## Etapa 9.4 — Montagem com FFmpeg

**Passo 9.4.1** — Implementar `audio/assemble.py` com o fluxo de §36:
```text
cada frase → TTS segment → normalizar áudio → FFmpeg concat → inserir silêncio físico → validar duração
```

**Passo 9.4.2** — Regra de §36: **não depender apenas de SSML para pausas** — o silêncio é físico, gerado como arquivo e concatenado.

**Passo 9.4.3** — FFmpeg com timeout de 120s (§42), heartbeat no Temporal (§17.4), e execução em subprocess sem shell.

**Passo 9.4.4** — Normalização de loudness consistente entre segmentos.

**Passo 9.4.5** — Temp files sob `TempManager` (5.1), apagados em `finally`.

---

## Etapa 9.5 — Validação do áudio

**Passo 9.5.1** — Implementar `audio/validate.py` com **todas** as checagens de §36.2, antes de `READY`:
- arquivo existe;
- tamanho > mínimo;
- duração plausível;
- FFprobe válido;
- SHA-256 calculado;
- número de segmentos esperado;
- **20 s centrais presentes dentro de tolerância**.

**Passo 9.5.2** — Falha ⇒ `AUDIO_VALIDATION_FAILED`, retry pela política do Temporal, e **nunca** publicar áudio inválido.

**Passo 9.5.3** — Detecção do silêncio de 20s por análise real do arquivo (FFmpeg `silencedetect`), não por confiança no plano.

---

## Etapa 9.6 — Status audio e publicação

**Passo 9.6.1** — Completar `audio/messages.py` com os textos **literais** de §34 para Gate 2 (100%, degradado, falha).

**Passo 9.6.2** — Regra de §34: o Android também consegue usar TTS local para mensagens críticas; o servidor gera status audio como **opcional**. Implementar como flag configurável.

**Passo 9.6.3** — Publicar em `AudioArtifact` com `artifact_type` (`status` | `final`), key de §12.2, sha256 e duração.

**Passo 9.6.4** — Implementar §13.7:
```text
GET /api/v1/sessions/{id}/audio          → áudio final (signed URL curta)
GET /api/v1/sessions/{id}/audio/status   → áudio de status
```

**Passo 9.6.5** — Activities reais `GenerateAnswerAudio`, `AssembleFinalAudio`, `ValidateFinalAudio`, `PublishFinalAudio`, `CompleteSession`, com `MAX_AUDIO_CONCURRENCY` (1–2, §44).

---

## Etapa 9.7 — Testes da FASE 9

**Passo 9.7.1** — Plano de áudio: 70 respostas ⇒ 140 itens (2 rodadas) + silêncios corretos.
**Passo 9.7.2** — Gate 2 degradado: apenas validadas entram; nenhuma menção a questão sem resposta.
**Passo 9.7.3** — Gate 2 bloqueado: nenhum áudio de gabarito é gerado; apenas status.
**Passo 9.7.4** — Validação de duração e presença dos 20s (com provider fake determinístico).
**Passo 9.7.5** — Fallback Google→Azure no TTS.
**Passo 9.7.6** — Restart no meio do FFmpeg (§50.5) ⇒ retoma sem corromper e sem publicar parcial.

## DoD da FASE 9

- [ ] Áudio final contém exatamente as respostas validadas
- [ ] Pausas: 2s (rodada 1), 20s central, 1s (rodada 2) — verificadas no arquivo
- [ ] Formato "Questão N. Letra X." sem explicações
- [ ] Checksum e validação completa de §36.2
- [ ] Gate 2 bloqueia áudio de gabarito abaixo de 90%
- [ ] Fallback de TTS visível e auditado

---

# FASE 10 — Painel administrativo

**Objetivo:** o operador executa e audita a sessão inteira pelo navegador.
**Seções do spec cobertas:** §11.1, §13.2, §13.3, §13.5, §37, §38.

---

## Etapa 10.1 — Autenticação do admin

**Passo 10.1.1** — Implementar `auth/admin.py` conforme §11.1: login e-mail + senha, hash **Argon2id**, cookie **HttpOnly + Secure + SameSite=Strict**, expiração de sessão, CSRF token para ações mutáveis, rate limit de login.

**Passo 10.1.2** — Endpoints §13.2: `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`.

**Passo 10.1.3** — Sem RBAC complexo na V1, mas com `actor_type` modelado nos logs e audit (§11.1).

**Passo 10.1.4** — `scripts/seed_admin.py` cria o admin a partir de `ADMIN_EMAIL` + `ADMIN_PASSWORD_HASH` (o hash é gerado fora e injetado; a senha em claro nunca entra no repositório).

**Passo 10.1.5** — Testes: login válido/inválido, brute force limitado, CSRF ausente ⇒ 403, cookie com todas as flags, sessão expirada.

---

## Etapa 10.2 — Eventos em tempo real (SSE)

**Passo 10.2.1** — Implementar `GET /api/v1/sessions/{id}/stream` com Server-Sent Events (§38).

**Passo 10.2.2** — Tipos de evento **exatos** de §38: `session.state_changed`, `capture.received`, `logical_page.accepted`, `question.updated`, `gate.result`, `provider.fallback`, `audio.ready`, `error`.

**Passo 10.2.3** — Suporte a `Last-Event-ID` para reconexão sem perda (§38); event id monotônico derivado de `AuditEvent.id`.

**Passo 10.2.4** — Event bus interno (`domain/ports/events.py`) alimentado pelo repositório de audit — fonte única de verdade, sem duplicação de emissão.

**Passo 10.2.5** — Backpressure: cliente lento não pode travar o servidor; buffer limitado e drop com aviso.

---

## Etapa 10.3 — API de leitura e ações admin

**Passo 10.3.1** — Implementar §13.3:
```text
POST   /api/v1/sessions
GET    /api/v1/sessions
GET    /api/v1/sessions/{id}
POST   /api/v1/sessions/{id}/finish-capture
POST   /api/v1/sessions/{id}/cancel
POST   /api/v1/sessions/{id}/pause
POST   /api/v1/sessions/{id}/resume
GET    /api/v1/sessions/{id}/events
GET    /api/v1/sessions/{id}/summary
```

**Passo 10.3.2** — Implementar §13.5 (admin/debug), todos exigindo auth admin **e** audit event:
```text
POST /api/v1/sessions/{id}/reprocess/stage/{stage}
POST /api/v1/questions/{id}/retry
POST /api/v1/questions/{id}/reconstruct
GET  /api/v1/questions/{id}
```

**Passo 10.3.3** — `reprocess/stage/{stage}` valida o estágio contra o vocabulário das 20 etapas de §17.1 e usa signal/child workflow — nunca reexecuta o workflow inteiro por acidente.

**Passo 10.3.4** — Toda ação admin gera `AuditEvent` com `actor_type=admin` (§37).

**Passo 10.3.5** — Visualização de imagem/áudio sempre por **signed URL de curta duração** (§12.1), nunca URL permanente.

---

## Etapa 10.4 — Frontend

**Passo 10.4.1** — Scaffold em `apps/admin/` com React + TypeScript + Vite, build **estático** (§3). Sem servidor Node em produção.

**Passo 10.4.2** — Tela principal (§37) com os 12 cards, nomes exatos: `Dispositivo, Android, VPS, Sessão atual, Páginas lógicas, Questões, Gate 1, Solver, Verifier, Arbitragem, Gate 2, Áudio`.

**Passo 10.4.3** — Session detail com **timeline** de eventos (formato de §37, com timestamp + evento).

**Passo 10.4.4** — Tabela de questões com as colunas **exatas** de §37: `Nº | status | páginas | solver | verifier | arbiter | final | provider fallback`.

**Passo 10.4.5** — Question detail (§37): imagens, crops, OCR, RAG hits, answer attempts, final answer, erros, retries. **Não exibir reasoning privado** (§37, §27.6).

**Passo 10.4.6** — Ações admin na UI (§37): finalizar captura, pausar, retomar, cancelar, reprocessar estágio, retry questão, baixar logs, baixar áudio — cada uma com confirmação explícita.

**Passo 10.4.7** — Consumo de SSE com reconexão automática via `Last-Event-ID`.

**Passo 10.4.8** — Indicador de modo degradado: "Fallback de IA utilizado em N questões" (§27.4).

**Passo 10.4.9** — Servir o build estático pelo backend (ou pelo proxy), sem processo Node adicional.

---

## Etapa 10.5 — Testes da FASE 10

**Passo 10.5.1** — Testes de API: auth, CSRF, cada endpoint de §13.3 e §13.5, audit gerado em toda ação mutável.
**Passo 10.5.2** — Teste de SSE: entrega de eventos, reconexão com `Last-Event-ID` sem lacuna.
**Passo 10.5.3** — Frontend: lint + typecheck + testes de componente; habilitar o job de frontend na CI (Passo 0.7.1).
**Passo 10.5.4** — Teste que garante que nenhum campo de reasoning privado é servido pela API do painel.

## DoD da FASE 10

- [ ] Operador executa e audita uma sessão inteira pelo navegador
- [ ] SSE com reconexão sem perda
- [ ] Todas as ações admin auditadas
- [ ] Build estático, sem Node em produção
- [ ] Reasoning privado não aparece em lugar nenhum
- [ ] **4ª milestone (§69) atingida**

---

# FASE 11 — Hardening

**Objetivo:** fault injection não causa perda silenciosa nem resposta inventada.
**Seções do spec cobertas:** §39, §41, §44, §48, §49, §50.5, §63.

---

## Etapa 11.1 — Observabilidade completa

**Passo 11.1.1** — Sentry (§39.3): exceptions, release, environment, trace, `session_public_id` como tag. Scrubbing de dados sensíveis ativado.

**Passo 11.1.2** — OpenTelemetry (§39.4): instrumentar FastAPI, httpx, SQLAlchemy, Temporal e chamadas de provider. Exportar via `OTEL_EXPORTER_OTLP_ENDPOINT` quando configurado.

**Passo 11.1.3** — Métricas (§39.5): expor `/metrics` **apenas internamente** com **todas** as 14 métricas listadas: `sessions_total, sessions_failed_total, frames_received_total, frame_upload_retries_total, logical_pages_total, ocr_requests_total, ocr_failures_total, llm_requests_total, llm_fallback_total, gate1_ratio, gate2_ratio, processing_duration_seconds, provider_latency_seconds, audio_generation_seconds, local_temp_bytes`.

**Passo 11.1.4** — Teste automatizado de §39.2: varredura de logs de uma execução completa procurando padrões de segredo (chaves, bearer, query de signed URL) ⇒ zero ocorrência.

---

## Etapa 11.2 — Resiliência e limites

**Passo 11.2.1** — Consolidar o circuit breaker (§41) em `common/circuit_breaker.py`, usado por **todos** os providers externos (OCR, LLM, TTS, Storage), com métricas de estado.

**Passo 11.2.2** — Revisar todos os timeouts contra §42 e a fórmula de activity timeout (Passo 4.4.1).

**Passo 11.2.3** — Revisar o retry budget global (§43) e provar por teste que a combinação não excede o limite.

**Passo 11.2.4** — Rate limits de API (admin login, gateway) e security headers no backend (complementares ao proxy, §3/§49).

---

## Etapa 11.3 — Recursos e disco

**Passo 11.3.1** — Implementar guarda de disco (§44): alerta em **free disk < 15 GB**; bloquear processamento pesado opcional em **free disk < 10 GB**.

**Passo 11.3.2** — Pré-checagem antes de sessão real (§75): free disk ≥ 15 GB, memória disponível ≥ margem, Temporal alcançável, Supabase alcançável, Anthropic **ou** DeepSeek alcançável, OCR provider alcançável. Regra de §75: **não** exigir todos os providers simultaneamente se houver fallback válido.

**Passo 11.3.3** — Expor essa pré-checagem em `GET /api/v1/health/dependencies` e como comando `make preflight`.

**Passo 11.3.4** — Concorrências finais de §44 aplicadas e documentadas: image 1, OCR 3, LLM 4–6, audio 1–2; API com 1 container e 1 worker uvicorn.

---

## Etapa 11.4 — Retenção e backup

**Passo 11.4.1** — Implementar política de retenção **configurável** (§48), com os defaults: originals 30d, derived 14d, ocr raw 30d, audit metadata 180d, final answer/audio 30d. Materiais de RAG são **persistentes**.

**Passo 11.4.2** — Job de retenção idempotente, com dry-run obrigatório antes da execução real e audit de tudo que apagar.

**Passo 11.4.3** — Backup (§48): habilitar backups do Supabase conforme plano e criar export periódico das tabelas críticas para `audit-exports`.

**Passo 11.4.4** — **Testar a restauração** — backup não testado não conta (§65).

---

## Etapa 11.5 — Chaos / fault injection

**Passo 11.5.1** — Criar `tests/e2e/chaos/` implementando **todos** os 13 cenários de §50.5, um teste por cenário:
1. matar API; 2. matar worker; 3. reiniciar worker; 4. duplicar frames; 5. hash errado; 6. storage timeout; 7. OCR 500; 8. Anthropic timeout; 9. Anthropic 429; 10. DeepSeek timeout; 11. TTS timeout; 12. **restart no meio da questão 37**; 13. **restart no meio do FFmpeg**.

**Passo 11.5.2** — Critério comum a todos: **nenhuma perda silenciosa** e **nenhuma resposta inventada**. Cada cenário verifica o estado final do banco, os audit events e a ausência de `FinalAnswer` indevido.

**Passo 11.5.3** — E2E completo de §50.4 com dataset de **30 páginas / 70 questões** e providers fake determinísticos.

**Passo 11.5.4** — Registrar resultados em `docs/benchmarks/chaos_report.md`.

---

## Etapa 11.6 — Runbooks

**Passo 11.6.1** — Criar os **9 runbooks** de §63, cada um com as 6 seções obrigatórias (sintomas, diagnóstico, comandos, impacto, recuperação, como verificar):
```text
docs/runbooks/anthropic_outage.md      docs/runbooks/disk_low.md
docs/runbooks/deepseek_outage.md       docs/runbooks/session_stuck.md
docs/runbooks/ocr_outage.md            docs/runbooks/reprocess_question.md
docs/runbooks/supabase_outage.md       docs/runbooks/rollback.md
docs/runbooks/temporal_worker_down.md
```

**Passo 11.6.2** — Cada runbook precisa ter sido **executado ao menos uma vez** contra o ambiente de staging; anotar a data da validação no próprio arquivo.

## DoD da FASE 11

- [ ] 13 cenários de chaos implementados e verdes
- [ ] Nenhuma perda silenciosa; nenhuma resposta inventada
- [ ] 14 métricas expostas internamente
- [ ] Sentry + OTel ativos
- [ ] Guarda de disco em 15 GB / 10 GB
- [ ] Retenção configurável e backup **restaurado com sucesso**
- [ ] 9 runbooks escritos e validados

---

# FASE 12 — Deploy

**Objetivo:** deploy repetível, sem intervenção manual em código, com rollback testado.
**Seções do spec cobertas:** §3 (proxy), §44, §45, §46, §47, §49, §56, §57, §75.

---

## Etapa 12.1 — Compose de produção

**Passo 12.1.1** — Criar `infra/docker-compose.prod.yml` com **apenas** (§45): `pages-api`, `pages-worker`, e opcionalmente `pages-admin-static`.

**Passo 12.1.2** — Proibido incluir (§45): PostgreSQL, MinIO, Elasticsearch, modelos LLM. Com Temporal Cloud, **nenhum** container Temporal; self-host futuro fica em arquivo compose separado.

**Passo 12.1.3** — Limites de recurso (§45): `api: 1.0 GB RAM`, `worker: 2.0–2.5 GB RAM`, CPU shares limitadas. Nunca reservar toda a RAM da VPS.

**Passo 12.1.4** — Rede Docker própria (§75), portas reservadas, bind em `127.0.0.1:18180` (§3).

**Passo 12.1.5** — Containers **não-root**, filesystem read-only onde possível, secrets fora da imagem (§49).

---

## Etapa 12.2 — Pipeline de CI/CD

**Passo 12.2.1** — Completar `.github/workflows/ci.yml` com a sequência **exata** de §46:
```text
checkout → setup Python → install uv → sync → ruff → typecheck
→ pytest unit → pytest integration → build Docker → frontend lint/test/build
```

**Passo 12.2.2** — Criar `.github/workflows/deploy.yml`: deploy **somente após sucesso** da CI; SSH → pull image → **migration** → rolling/restart → **health check** (§46).

**Passo 12.2.3** — Proibição literal de §46: **nunca** `git pull && docker compose down` sem health/recovery. O job deve falhar se o health check pós-deploy não passar, e disparar rollback.

**Passo 12.2.4** — Ordem de migração de §47: (1) migration forward; (2) deploy de código compatível; (3) limpeza em release futuro. Migration destrutiva exige backup + verificação de compatibilidade antes.

**Passo 12.2.5** — Rollback automatizado: voltar à imagem anterior + verificar health; documentado em `docs/runbooks/rollback.md`.

---

## Etapa 12.3 — Staging

**Passo 12.3.1** — Provisionar staging conforme §56: projeto/schema Supabase separado, bucket separado, namespace Temporal separado, API keys com orçamento, domínio de staging.

**Passo 12.3.2** — Regra de §56: **nunca** testar migration perigosa direto em produção. Toda migration passa por staging primeiro.

**Passo 12.3.3** — Rodar o E2E completo (30 páginas / 70 questões) em staging antes de qualquer go-live.

---

## Etapa 12.4 — Integração com o proxy existente

**Passo 12.4.1** — Documentar em `docs/operations.md` a configuração esperada do proxy (sem assumir Nginx/Caddy/Traefik, §3): upstream `127.0.0.1:18180`, TLS, HTTP/2, limite de upload compatível com o tamanho máximo de frame, headers de segurança, timeouts compatíveis com §42.

**Passo 12.4.2** — Fornecer exemplos de configuração para Nginx, Caddy e Traefik como **anexos**, deixando claro que são exemplos, não requisitos.

---

## Etapa 12.5 — Plano operacional da VPS

**Passo 12.5.1** — Executar os 10 passos de §75, na ordem, registrando as medições em `docs/operations.md`:
1. medir baseline de RAM/CPU/disco; 2. reservar portas; 3. criar rede Docker própria; 4. subir **somente** a API; 5. medir; 6. adicionar worker; 7. medir; 8. habilitar processing real; 9. definir limites; 10. criar alerta de disco.

**Passo 12.5.2** — Só aumentar concorrência **após** teste de recursos (regra literal de CLAUDE.md).

---

## Etapa 12.6 — Documentação operacional final

**Passo 12.6.1** — Completar `docs/architecture.md`, `docs/api_contracts.md`, `docs/android_contract.md`, `docs/workflow.md`, `docs/operations.md`, `docs/security.md` — todos com o conteúdo real, não TODO.

**Passo 12.6.2** — Checklist de §79 (antes de usar APIs reais) transformado em documento executável em `docs/operations.md`, com caixas marcáveis.

**Passo 12.6.3** — Checklist de §57 (produção) validado item a item: `pytest`, integration, migrations dry run, storage test, provider smoke tests, disk free, memory available.

## DoD da FASE 12

- [ ] Deploy repetível sem intervenção manual em código
- [ ] Compose de produção só com api/worker/admin-static, com limites de RAM
- [ ] Migration → deploy → health check → rollback testado
- [ ] Staging isolado e usado para toda migration
- [ ] Plano operacional da VPS executado e medido
- [ ] Documentação operacional completa

---

# FASE 13 — Aceite final V1

**Objetivo:** fechar formalmente o DoD global de §65.

## Etapa 13.1 — Verificação item a item de §65

Executar e registrar evidência (log, print, arquivo de resultado) para **cada** item:

**Passo 13.1.1** — Fases 0–12 finalizadas (`PHASE_STATUS.md` todo `DONE`).
**Passo 13.1.2** — Migrations reproduzíveis (`upgrade`/`downgrade` em banco limpo).
**Passo 13.1.3** — E2E com golden dataset executado.
**Passo 13.1.4** — Gate 1 testado em **100%, 90% e 89%**.
**Passo 13.1.5** — Gate 2 testado em **100%, 90% e 89%**.
**Passo 13.1.6** — Anthropic outage simulado.
**Passo 13.1.7** — DeepSeek fallback confirmado.
**Passo 13.1.8** — OCR primary outage simulado.
**Passo 13.1.9** — Restart de worker validado.
**Passo 13.1.10** — Restart de API validado.
**Passo 13.1.11** — Áudio validado (estrutura, pausas, checksum).
**Passo 13.1.12** — Painel funcional.
**Passo 13.1.13** — Logs auditáveis.
**Passo 13.1.14** — **Nenhum segredo no Git** (varredura de histórico com ferramenta de secret scanning).
**Passo 13.1.15** — Recursos da VPS medidos.
**Passo 13.1.16** — Runbooks prontos.
**Passo 13.1.17** — Backup testado.
**Passo 13.1.18** — Rollback testado.

## Etapa 13.2 — Verificação dos critérios de aceite de §61

**Passo 13.2.1** — Captura: nenhum frame persistido perdido; duplicatas idempotentes; hash mismatch bloqueia; páginas lógicas corretas; end redundante; lock imutável.
**Passo 13.2.2** — Processamento: original preservado; OCR normalizado; questão multi-página suportada; visual assets suportados; rescue limitado e auditado.
**Passo 13.2.3** — Gates: 63/70 passa; 62/70 bloqueia; mesma regra no Gate 2; nenhum gabarito abaixo de 90%.
**Passo 13.2.4** — IA: Opus primary; DeepSeek fallback técnico; verifier independente; arbiter; structured outputs; nenhum reasoning privado armazenado.
**Passo 13.2.5** — Áudio: número + letra; 2s; 20s; 1s; checksum.
**Passo 13.2.6** — Operações: restart de worker retoma; restart de API não corrompe; storage retry; logs; painel; backup; resource limits.

## Etapa 13.3 — Verificação das 10 invariantes de §10

**Passo 13.3.1** — Confirmar que **cada uma** das 10 invariantes tem teste próprio, nomeado explicitamente (`test_invariant_01_...` … `test_invariant_10_...`), e todos verdes. Esta é uma exigência literal de §10 ("Estas invariantes devem ter testes próprios").

## Etapa 13.4 — Métricas de performance inicial

**Passo 13.4.1** — Medir e registrar (§62): captura finalizada → Gate 1; Gate 1 → answers final; answers → audio READY; total.
**Passo 13.4.2** — Regra de §62: **não** definir SLA agressivo antes de benchmark real; qualidade tem prioridade sobre tempo.

## DoD da FASE 13 (= DoD do V1)

- [ ] Todos os 18 itens de §65 com evidência registrada
- [ ] Todos os critérios de §61 verificados
- [ ] As 10 invariantes de §10 com teste próprio e verde
- [ ] Benchmarks de §52 executados (captura, OCR, RAG, LLM, TTS)
- [ ] Nenhum item de §72 alterado sem ADR

---

# Anexo A — Matriz de rastreabilidade (seção do spec → fase)

| Seção do spec | Tema | Fase(s) |
|---|---|---|
| §1, §2 | Contexto e restrições | 0 (documentação), transversal |
| §3 | Decisões técnicas / stack | 0, 10, 12 |
| §4 | Filosofia de implementação | transversal |
| §5 | Estrutura do monorepo | 0 |
| §6 | CLAUDE.md | 0 |
| §7 | Configuração e env | 0 |
| §8 | Modelo de domínio | 1 |
| §9 | Estados da sessão | 1 |
| §10 | Invariantes | 1–9 (teste próprio), 13 (auditoria) |
| §11 | Autenticação | 2 (gateway/device), 10 (admin) |
| §12 | Storage | 2 |
| §13 | API REST | 0 (health), 2 (gateway), 7 (knowledge), 9 (audio), 10 (admin) |
| §14 | Idempotência | 1, 2 |
| §15 | Capture Controller | 3 |
| §16 | Encerramento redundante | 3 |
| §17 | Temporal | 4 |
| §18 | Processamento de imagem | 3 (quality), 5 (preprocess) |
| §19 | OCR abstraction | 5 |
| §20 | Visual understanding | 6 |
| §21 | Reconstrução | 6 |
| §22 | Rescue de reconstrução | 6 |
| §23 | Gate 1 | 6 |
| §24 | Knowledge ingestion | 7 |
| §25 | Hybrid RAG | 7 |
| §26 | LLM abstraction | 8 |
| §27 | Política Anthropic→DeepSeek | 8 |
| §28 | Structured outputs | 8 |
| §29 | Solver | 8 |
| §30 | Verifier | 8 |
| §31 | Arbiter | 8 |
| §32 | Paralelismo LLM | 8 |
| §33 | Gate 2 | 9 |
| §34 | Status audio | 6 (Gate 1), 9 (Gate 2) |
| §35 | TTS abstraction | 9 |
| §36 | Áudio final | 9 |
| §37 | Painel | 10 |
| §38 | SSE | 10 |
| §39 | Observabilidade | 0 (logs), 11 (completo) |
| §40 | Reason codes | 1 |
| §41 | Circuit breaker | 5, 8, 11 |
| §42 | Timeouts | 4, 11 |
| §43 | Retry budget | 4, 11 |
| §44 | Resource budgets | 11, 12 |
| §45 | Compose produção | 12 |
| §46 | GitHub Actions | 0 (mínima), 12 (completa) |
| §47 | Migrations | 1, 12 |
| §48 | Backup e retenção | 11 |
| §49 | Segurança | 2 (upload), 11, 12 |
| §50 | Testes | transversal, 11 (chaos) |
| §51 | Golden dataset | 6 |
| §52 | Benchmarks | 6, 7, 9, 13 |
| §53 | Fases | este plano |
| §54 | Makefile | 0 (todos os alvos) |
| §55 | Dev local | 0 |
| §56 | Staging | 12 |
| §57 | Produção | 12 |
| §58 | Fluxo E2E | 4 (esqueleto), 13 (validação) |
| §59 | Fallbacks | 5, 8, 9 |
| §60 | Qualidade acadêmica | 6, 8 |
| §61 | Critérios de aceite | 13 |
| §62 | Performance | 13 |
| §63 | Runbooks | 11 |
| §64 | Sequência de trabalho | este plano, §0.2 |
| §65 | DoD global | 13 |
| §66–§69 | Milestones | 3, 6, 8, 10 |
| §70 | Configuráveis | 0, transversal |
| §71 | Não bloqueiam início | 5, 7, 9 (benchmark) |
| §72 | Congelar antes de produção | 1–9, verificado em 13 |
| §73 | DeepSeek V4 Pro | 8 |
| §74 | Supabase RAG | 7 |
| §75 | Plano operacional VPS | 12 |
| §76 | Documento na raiz | 0 |
| §77 | ADRs | 0 |
| §78 | Checklist Fase 0 | 0 |
| §79 | Checklist APIs reais | 12 |
| §80 | Resumo executivo | transversal |

---

# Anexo B — Divergências do spec e resoluções obrigatórias

Estes pontos apresentam ambiguidade, lacuna ou conflito interno no documento-fonte. As resoluções abaixo são **normativas para a execução**. Cada uma exige um ADR curto registrando a decisão. **Nenhuma pode ser resolvida por improviso durante a implementação.**

### B-1 — Constraints redundantes em `Frame` (§8.5)
`UNIQUE(capture_id, frame_index)` já implica unicidade dentro de `UNIQUE(session_id, sha256, capture_id, frame_index)`, tornando a segunda constraint inefetiva para deduplicar por hash.
**Resolução:** implementar **as duas exatamente como especificado** (fidelidade ao spec) e **adicionar** um índice não-único `(session_id, sha256)` para suportar a detecção de reenvio idêntico exigida por §14. A lógica de idempotência de frame usa a identidade natural `session_id + capture_id + frame_index + sha256` no nível de aplicação (Passo 1.7.3).

### B-2 — Buckets: §7 declara 2, §12.1 declara 6
`.env.example` tem `SUPABASE_STORAGE_BUCKET` e `SUPABASE_KNOWLEDGE_BUCKET`; §12.1 lista 6 buckets privados.
**Resolução:** §12.1 prevalece. Criar variáveis dedicadas — `SUPABASE_BUCKET_PAGES_ORIGINALS`, `SUPABASE_BUCKET_PAGES_DERIVED`, `SUPABASE_BUCKET_OCR_RAW`, `SUPABASE_BUCKET_KNOWLEDGE`, `SUPABASE_BUCKET_AUDIO`, `SUPABASE_BUCKET_AUDIT_EXPORTS` — mantendo as duas chaves originais como *defaults* de compatibilidade.

### B-3 — `MAX_RECONSTRUCTION_RESCUE_ROUNDS` ausente do `.env.example`
Citado em §22, ausente em §7.
**Resolução:** adicionar ao `.env.example` com default `3`.

### B-4 — `TTS_FALLBACK_PROVIDER` ausente do `.env.example`
Citado em §35, ausente em §7.
**Resolução:** adicionar com default `azure`.

### B-5 — Flags `USE_REAL_*` ausentes do `.env.example`
Citadas em §55.
**Resolução:** adicionar `USE_REAL_ANTHROPIC=false`, `USE_REAL_DEEPSEEK=false`, `USE_REAL_OCR=false`, `USE_REAL_TTS=false`.

### B-6 — `DEEPSEEK_CROSSCHECK_ON_HIGH_RISK` ausente do `.env.example`
Citada em §27.3 como configuração futura.
**Resolução:** adicionar com default `false`.

### B-7 — Porta de bind ausente do `.env.example`
§3 fixa `127.0.0.1:18180`.
**Resolução:** adicionar `API_BIND_HOST=127.0.0.1` e `API_BIND_PORT=18180`.

### B-8 — Dimensão do vetor indefinida (§8.12: `embedding VECTOR(...)`)
pgvector exige dimensão fixa na coluna, mas §24.3 exige independência de provider.
**Resolução:** definir `EMBEDDING_DIM` em configuração e criar a coluna com esse valor na migration. Troca de modelo com dimensão diferente ⇒ **migration nova + reindexação completa**, documentada em `docs/runbooks/`. A independência exigida por §24.3 é da *interface e do schema lógico*, não da largura física da coluna. Registrar como ADR-0011.

### B-9 — Área de auditoria para uploads pós-LOCK (§10, Invariante 1)
O spec permite armazenar upload atrasado em "área de auditoria" mas não nomeia o destino.
**Resolução:** bucket `audit-exports`, prefixo `sessions/{sid}/late/`, com registro em `AuditEvent` e flag `late_upload=true`. Não cria `Frame` de prova nem altera `LogicalPage`.

### B-10 — Endpoint SSE não listado em §13
§38 define `GET /api/v1/sessions/{id}/stream`, ausente da lista de rotas de §13.3.
**Resolução:** implementar conforme §38; §13.3 é lista não exaustiva.

### B-11 — WebSocket do gateway (§13.4)
`WS /gateway/ws` é marcado como opcional e "acelerador, não dependência".
**Resolução:** **fora da V1**. O Android deve funcionar apenas com HTTP. Registrar como backlog explícito, sem código morto no repositório.

### B-12 — DOCX na ingestão (§24.1)
"DOCX pode entrar depois".
**Resolução:** fora da V1. Interface de extractor preparada para receber o formato sem mudança estrutural.

### B-13 — `MAX_LLM_CONCURRENCY`: 6 no `.env.example`, "começar com 4" em §32
**Resolução:** default operacional **4**; `.env.example` mantém 6 como teto permitido, com comentário explicando que só se sobe após medição (§44, CLAUDE.md).

### B-14 — Status audio: servidor vs Android (§34)
O Android pode usar TTS local; o servidor "também poderá" gerar.
**Resolução:** o servidor **gera** status audio, controlado por flag `STATUS_AUDIO_SERVER_ENABLED=true`. O Android mantém TTS local como caminho independente para mensagens críticas.

### B-15 — Frontend: React vs HTMX (§3)
§3 aceita HTMX/Jinja como alternativa "se ficar significativamente mais simples".
**Resolução:** **React + TypeScript + Vite**, conforme ADR-0008. Sem reavaliação durante a execução.

### B-16 — `LogicalPage` sem frame utilizável (§15.7)
§15.7 manda pedir novo burst, mas não define o comportamento após esgotar tentativas.
**Resolução:** após K tentativas (configurável, default 3), seguir com o melhor frame disponível marcando `LogicalPage.status=degraded` e registrando `NO_USABLE_FRAME`. Comportamento alternativo (pular a página) fica atrás de flag. Registrar como ADR-0012.

---

# Anexo C — Prompt-base por fase para o Codex

Usar **literalmente** este prompt no início de cada fase, substituindo `X` (§64 do spec, expandido):

```text
Leia integralmente CLAUDE.md, IMPLEMENTATION_PLAN.md e CODEX_EXECUTION_PLAN.md
(incluindo o Anexo B deste último).

Implemente somente a FASE X, seguindo suas Etapas e Passos na ordem escrita.
Não implemente funcionalidades de fases futuras, salvo interfaces/stubs
estritamente necessários para esta fase compilar e ser testada.

Antes de alterar qualquer arquivo:
1. resuma o escopo da fase e o que está fora de escopo;
2. liste os arquivos que pretende criar/alterar, com caminho completo;
3. identifique riscos e pontos de ambiguidade;
4. confirme quais invariantes de §10 se aplicam a esta fase e como serão garantidas;
5. confirme quais itens do Anexo B afetam esta fase.

Depois:
1. implemente etapa por etapa, commitando ao final de cada Etapa;
2. execute make lint, make typecheck e make test;
3. corrija todos os erros — não prossiga com nada vermelho;
4. mostre os resultados dos testes;
5. atualize docs/ e docs/progress/PHASE_STATUS.md;
6. registre qualquer desvio arquitetural em docs/decisions/ADR-xxxx.md;
7. não marque a fase como concluída se algum critério de aceite ou item do
   DoD da fase estiver pendente.

Restrições permanentes:
- nenhum segredo real em código, teste ou log;
- nenhuma alteração de schema sem migration nova;
- nenhuma migration já aplicada pode ser editada;
- nenhum fallback silencioso;
- toda chamada externa com timeout e retry policy explícitos;
- toda operação mutável idempotente;
- saída de LLM sempre validada por Pydantic, nunca por regex.
```

---

# Anexo D — Convenções de Git, commit e PR

## D.1 Branches

```text
master            → produção
develop           → integração
feature/fase-N-<slug>   → uma branch por fase
fix/<slug>        → correção pontual
```

## D.2 Commits

Conventional Commits, com escopo de fase:

```text
feat(fase-2/storage): adapter Supabase Storage com buckets privados
test(fase-2/ingest): idempotência de frame duplicado
fix(fase-1/state): bloqueia transição LOCKED→CAPTURING
docs(fase-0): ADR-0004 Claude primary, DeepSeek fallback
chore(fase-0): configura ruff e mypy strict
```

Regra: **um commit por Etapa concluída**, com os testes daquela etapa verdes.

## D.3 Pull Request por fase

Template obrigatório:

```markdown
## Fase
FASE X — <nome>

## Escopo entregue
- Etapa X.1 ...

## Fora de escopo (confirmado)
- ...

## Invariantes garantidas nesta fase
- Invariante N: <como foi garantida> — teste `test_invariant_N_...`

## Itens do Anexo B aplicados
- B-n: <resolução aplicada>

## Resultados
- make lint: OK
- make typecheck: OK
- make test: N passed
- Cobertura: X%

## DoD da fase
- [ ] item 1
- [ ] item 2

## ADRs criados/alterados
- ADR-00xx
```

## D.4 Regra de rollback de fase

Se um defeito estrutural de fase anterior for descoberto: abrir `fix/fase-N-<slug>`, corrigir **na fase de origem**, re-rodar a suíte daquela fase e as posteriores, e só então retomar. Proibido remendar na fase corrente (§4).

---

# Anexo E — Checklist mestre de conclusão

## E.1 Por fase

- [ ] **FASE 0** — bootstrap, quality gates verdes, CLAUDE.md, 10 ADRs, árvore §5
- [ ] **FASE 1** — schema §8 completo, estados §9, invariantes estruturais, idempotência
- [ ] **FASE 2** — storage, ingestão, auth gateway/device, 100 frames sem perda
- [ ] **FASE 3** — capture controller, encerramento redundante, LOCK atômico *(milestone 1)*
- [ ] **FASE 4** — Temporal durável, 20 etapas, restart do worker
- [ ] **FASE 5** — preprocess + OCR normalizado + fallback Google/Azure
- [ ] **FASE 6** — reconstrução + rescue + Gate 1 *(milestone 2)*
- [ ] **FASE 7** — knowledge + RAG híbrido + search-test
- [ ] **FASE 8** — Solver/Verifier/Arbiter + fallback DeepSeek *(milestone 3)*
- [ ] **FASE 9** — Gate 2 + TTS + áudio validado
- [ ] **FASE 10** — painel completo com SSE *(milestone 4)*
- [ ] **FASE 11** — observabilidade, chaos, retenção, runbooks
- [ ] **FASE 12** — deploy repetível, staging, rollback
- [ ] **FASE 13** — aceite final V1 (§65)

## E.2 Invariantes (§10) — cada uma com teste próprio

- [ ] 1. Sessão LOCKED não aceita frame silenciosamente
- [ ] 2. LogicalPage só nasce de burst FULL válido
- [ ] 3. Marcador de FIM nunca vira página lógica
- [ ] 4. Questão FAILED nunca recebe FinalAnswer
- [ ] 5. Solver não inicia sem Gate 1 aprovado
- [ ] 6. TTS de gabarito não inicia sem Gate 2 aprovado
- [ ] 7. Resposta final é sempre alternativa permitida
- [ ] 8. Imagem original nunca é sobrescrita
- [ ] 9. Mesma idempotency key ⇒ mesmo efeito lógico
- [ ] 10. Falha de provider nunca vira "resposta provável"

## E.3 Itens congelados antes da produção (§72)

- [ ] schema  - [ ] invariantes  - [ ] estados  - [ ] idempotência
- [ ] locking  - [ ] Gate 1  - [ ] Gate 2  - [ ] provider fallback
- [ ] storage policy  - [ ] audit events  - [ ] retry limits  - [ ] segurança

## E.4 Benchmarks obrigatórios (§52)

- [ ] Captura: JPEG quality, blur thresholds, 2 vs 3 frames, probe cadence
- [ ] OCR: Google, Azure, Paddle em worker disponível
- [ ] RAG: embedding A/B, chunk size, RRF, top-K, reranker
- [ ] LLM: Opus primary, DeepSeek fallback, casos de divergência
- [ ] TTS: Google vs Azure, clareza na JBL, velocidade

---

## Regra central, repetida ao final por ser inegociável (§80)

> **Qualidade máxima, zero falha silenciosa, nenhuma resposta inventada por falha técnica e nenhuma execução abaixo do piso de 90% chegando ao áudio de gabarito.**
