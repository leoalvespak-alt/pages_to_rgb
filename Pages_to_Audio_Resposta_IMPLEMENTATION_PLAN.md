# Pages_to_Audio_Resposta — Plano de Implementação Completo do Servidor

## Extensão V2.2 — entrega de resultado RGB

O backend também publica o resultado final ao Android Gateway para o canal WS2812 do firmware V2.2. A implementação segue `docs/contracts/RGB_RESULT_V1.md` e o ADR-0011: sequência imutável, revisão, cursor, eventos idempotentes e SHA-256 sobre itens packed `<BBBBBII`. O canal RGB é assíncrono e não substitui o áudio.

**Versão:** 1.0  
**Data-base:** 14/08/2026  
**Objetivo do documento:** servir como plano mestre de implementação para o Claude Code, cobrindo backend, banco, storage, orquestração, captura, OCR/VLM, reconstrução, RAG, correção, validação, áudio, painel, observabilidade, testes e implantação.

---

# 1. Contexto congelado

O sistema `Pages_to_Audio_Resposta` recebe capturas de páginas de provas/simulados feitas por um dispositivo ESP32-S3-CAM com OV2640. O dispositivo se conecta ao hotspot Wi‑Fi de um smartphone Android, que funciona como gateway local e ponte para o VPS via 4G/5G.

O sistema deve:

1. receber capturas automaticamente;
2. formar páginas lógicas;
3. encerrar a captura de forma redundante;
4. preservar todas as imagens relevantes;
5. processar qualidade, layout, OCR e conteúdo multimodal;
6. reconstruir as questões;
7. tentar resgates automáticos quando houver falhas;
8. bloquear a correção se menos de 90% das questões esperadas estiverem prontas;
9. resolver as questões com Claude Opus 5 como IA principal;
10. usar DeepSeek V4 Pro como fallback de IA;
11. validar as respostas com Solver + Verifier + Arbiter;
12. bloquear o áudio se menos de 90% das respostas esperadas forem validadas;
13. gerar áudio contendo apenas número da questão + alternativa correta;
14. entregar o áudio ao Android, que reproduz na JBL;
15. registrar tudo que for necessário para auditoria.

A meta operacional é **100% das questões**. O valor de 90% é apenas o piso de segurança para não prosseguir em uma execução degradada demais.

---

# 2. Restrições reais de infraestrutura

## 2.1 VPS atual

- Ubuntu 24.04 LTS
- Docker disponível
- 2 vCPU
- 8 GB RAM
- 100 GB de disco
- aproximadamente 23 GB livres
- VPS compartilhada com uma plataforma de estudos e outros projetos

## 2.2 Consequências arquiteturais

O projeto **não deve monopolizar CPU, RAM ou disco**.

Portanto:

- não armazenar permanentemente imagens no disco local;
- usar Supabase Storage como armazenamento definitivo;
- usar Supabase PostgreSQL para dados da aplicação;
- usar pgvector no Supabase para RAG;
- limitar processamento CPU-bound local;
- limitar concorrência dos workers;
- usar serviços externos para OCR pesado quando apropriado;
- manter PaddleOCR/PaddleOCR-VL como worker opcional, preferencialmente remoto ou habilitado somente quando houver capacidade;
- arquivos temporários locais devem possuir TTL e limpeza automática;
- evitar Redis, Elasticsearch e outros serviços persistentes enquanto não forem necessários;
- não executar banco PostgreSQL da aplicação dentro da VPS;
- não executar modelos LLM locais na VPS atual.

## 2.3 Orquestração

A arquitetura continua baseada em Temporal porque o workflow precisa ser durável.

Por causa dos recursos limitados da VPS, a ordem de preferência para produção será:

1. **Temporal Cloud**;
2. Temporal self-hosted em infraestrutura separada;
3. Temporal self-hosted mínimo na VPS somente após benchmark de recursos.

O código não poderá depender de detalhes de hospedagem do Temporal.

`TEMPORAL_ADDRESS` e `TEMPORAL_NAMESPACE` serão apenas configuração.

O banco Supabase da aplicação **não deve ser usado como banco interno do Temporal**.

---

# 3. Decisões técnicas principais

## Backend

- Python 3.12+
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x assíncrono
- Alembic
- httpx
- Temporal Python SDK
- PostgreSQL/Supabase
- Supabase Storage
- pgvector
- OpenCV
- Pillow
- structlog ou logging JSON
- OpenTelemetry
- Sentry
- pytest
- pytest-asyncio
- Ruff
- mypy ou pyright

## Painel

Para reduzir consumo no VPS:

- React + TypeScript + Vite;
- build estático;
- servido pelo proxy existente ou pelo backend;
- sem servidor Node.js em produção.

Alternativa aceitável: HTMX/Jinja, se a implementação ficar significativamente mais simples.

## Reverse proxy

Não assumir Nginx/Caddy/Traefik específico, pois a VPS já hospeda outros projetos.

O container do backend deverá expor uma porta local configurável, por exemplo:

```text
127.0.0.1:18180
```

e o proxy já existente ficará responsável por:

- domínio;
- TLS;
- HTTP/2;
- limites de upload;
- cabeçalhos de segurança.

---

# 4. Filosofia de implementação

O Claude Code **não deve implementar o sistema inteiro em uma única execução**.

Cada fase precisa possuir:

- escopo;
- fora de escopo;
- contratos;
- migrations;
- testes;
- critérios de aceite;
- Definition of Done.

Só avançar após os testes da fase atual estarem verdes.

Regra:

> nenhuma fase posterior pode compensar um defeito estrutural de uma fase anterior.

---

# 5. Estrutura do monorepo

```text
pages-to-audio/
├── README.md
├── CLAUDE.md
├── IMPLEMENTATION_PLAN.md
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
├── Makefile
│
├── apps/
│   ├── api/
│   │   ├── main.py
│   │   ├── dependencies.py
│   │   ├── middleware/
│   │   ├── routers/
│   │   └── schemas/
│   │
│   └── admin/
│       ├── package.json
│       ├── src/
│       └── vite.config.ts
│
├── src/
│   └── pages_to_audio/
│       ├── config/
│       ├── domain/
│       ├── db/
│       ├── storage/
│       ├── auth/
│       ├── capture/
│       ├── image/
│       ├── ocr/
│       ├── reconstruction/
│       ├── rag/
│       ├── llm/
│       ├── audio/
│       ├── workflows/
│       ├── observability/
│       └── common/
│
├── prompts/
│   ├── reconstruction/
│   ├── solver/
│   ├── verifier/
│   └── arbiter/
│
├── migrations/
│   └── versions/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contracts/
│   ├── workflows/
│   ├── fixtures/
│   └── e2e/
│
├── scripts/
│   ├── seed_admin.py
│   ├── ingest_knowledge.py
│   ├── cleanup_temp.py
│   ├── simulate_android.py
│   ├── simulate_exam.py
│   └── benchmark_providers.py
│
├── infra/
│   ├── docker/
│   ├── docker-compose.dev.yml
│   ├── docker-compose.prod.yml
│   └── systemd/
│
└── docs/
    ├── architecture.md
    ├── api_contracts.md
    ├── android_contract.md
    ├── workflow.md
    ├── operations.md
    ├── security.md
    └── runbooks/
```

---

# 6. CLAUDE.md obrigatório

Criar um `CLAUDE.md` na raiz contendo regras para o Claude Code.

Conteúdo mínimo:

```text
- Nunca apagar migrations antigas.
- Nunca alterar schema sem migration.
- Nunca colocar segredo real no código.
- Nunca criar fallback silencioso.
- Nunca marcar questão FAILED como respondida.
- Nunca iniciar Solver antes do Gate 1.
- Nunca gerar áudio se Gate 2 < minimum_ratio.
- Nunca sobrescrever imagem ORIGINAL.
- Toda chamada externa deve ter timeout explícito.
- Toda chamada externa deve possuir retry policy explícita.
- Toda operação mutável deve ser idempotente.
- Toda nova feature precisa de testes.
- Não usar sleeps arbitrários para sincronização.
- Não usar regex para extrair resposta final de LLM.
- LLM deve usar schema estruturado validado por Pydantic.
- Não registrar API keys, tokens ou conteúdo de reasoning privado.
- Não armazenar imagens permanentemente no disco local.
- Não aumentar concurrency sem teste de recursos.
- O servidor deve continuar funcionando se PaddleOCR estiver desabilitado.
- Claude Opus 5 é primary; DeepSeek V4 Pro é fallback.
```

---

# 7. Configuração e variáveis de ambiente

Criar configuração tipada em `src/pages_to_audio/config/settings.py`.

Usar `pydantic-settings`.

Exemplo de `.env.example`:

```dotenv
APP_ENV=development
APP_NAME=pages-to-audio
APP_BASE_URL=http://localhost:8000
LOG_LEVEL=INFO

DATABASE_URL=
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_STORAGE_BUCKET=pages-to-audio
SUPABASE_KNOWLEDGE_BUCKET=knowledge

ADMIN_EMAIL=
ADMIN_PASSWORD_HASH=
SESSION_SECRET=

ANDROID_GATEWAY_TOKEN=
DEVICE_HMAC_MASTER_KEY=

TEMPORAL_ADDRESS=
TEMPORAL_NAMESPACE=pages-to-audio
TEMPORAL_TASK_QUEUE=pages-to-audio-main
TEMPORAL_TLS=false

ANTHROPIC_API_KEY=
ANTHROPIC_MODEL_SOLVER=
ANTHROPIC_MODEL_VERIFIER=
ANTHROPIC_MODEL_ARBITER=

DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_FALLBACK_ENABLED=true

GOOGLE_DOCUMENT_AI_PROJECT_ID=
GOOGLE_DOCUMENT_AI_LOCATION=
GOOGLE_DOCUMENT_AI_PROCESSOR_ID=
GOOGLE_APPLICATION_CREDENTIALS=

AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=
AZURE_DOCUMENT_INTELLIGENCE_KEY=

PADDLE_OCR_ENABLED=false

TTS_PROVIDER=google
GOOGLE_TTS_CREDENTIALS=
AZURE_SPEECH_KEY=
AZURE_SPEECH_REGION=

WEB_SEARCH_ENABLED=true

DEFAULT_EXPECTED_PAGES=30
DEFAULT_EXPECTED_QUESTIONS=70
DEFAULT_MINIMUM_RATIO=0.90

LOCAL_TEMP_ROOT=/tmp/pages-to-audio
LOCAL_TEMP_MAX_GB=2
LOCAL_TEMP_TTL_HOURS=6

MAX_IMAGE_PROCESSING_CONCURRENCY=1
MAX_OCR_CONCURRENCY=3
MAX_LLM_CONCURRENCY=6
MAX_AUDIO_CONCURRENCY=2

SENTRY_DSN=
OTEL_EXPORTER_OTLP_ENDPOINT=
```

Regras:

- nenhum segredo real no repositório;
- produção usa `.env` fora do Git ou secrets do runtime;
- logs nunca imprimem secrets;
- settings falham rapidamente quando configuração crítica estiver ausente.

---

# 8. Modelo de domínio

## 8.1 Device

```text
id UUID PK
device_code TEXT UNIQUE
display_name TEXT
enabled BOOLEAN
created_at TIMESTAMPTZ
last_seen_at TIMESTAMPTZ
firmware_version TEXT
metadata JSONB
```

## 8.2 AndroidGateway

```text
id UUID PK
gateway_code TEXT UNIQUE
enabled BOOLEAN
last_seen_at TIMESTAMPTZ
app_version TEXT
device_model TEXT
metadata JSONB
```

## 8.3 Session

```text
id UUID PK
public_id TEXT UNIQUE
device_id UUID FK
gateway_id UUID FK
status TEXT
expected_pages INTEGER
expected_questions INTEGER
minimum_ratio NUMERIC
capture_started_at TIMESTAMPTZ
capture_locked_at TIMESTAMPTZ
processing_started_at TIMESTAMPTZ
completed_at TIMESTAMPTZ
end_reason TEXT
config_snapshot JSONB
provider_snapshot JSONB
degraded_mode BOOLEAN DEFAULT false
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

## 8.4 Capture

```text
id UUID PK
session_id UUID FK
capture_id TEXT
mode TEXT
command_cursor BIGINT
requested_frames INTEGER
received_frames INTEGER
status TEXT
created_at TIMESTAMPTZ
completed_at TIMESTAMPTZ

UNIQUE(session_id, capture_id)
```

## 8.5 Frame

```text
id UUID PK
session_id UUID FK
capture_id UUID FK
frame_index INTEGER
sha256 CHAR(64)
content_length BIGINT
mime_type TEXT
width INTEGER
height INTEGER
storage_key TEXT
received_android_at TIMESTAMPTZ
received_server_at TIMESTAMPTZ
quality_metrics JSONB
status TEXT
created_at TIMESTAMPTZ

UNIQUE(capture_id, frame_index)
UNIQUE(session_id, sha256, capture_id, frame_index)
```

## 8.6 LogicalPage

```text
id UUID PK
session_id UUID FK
logical_index INTEGER
primary_frame_id UUID FK
status TEXT
quality_score NUMERIC
metadata JSONB
created_at TIMESTAMPTZ

UNIQUE(session_id, logical_index)
```

## 8.7 LogicalPageFrame

```text
logical_page_id UUID FK
frame_id UUID FK
role TEXT  # primary|alternate
rank INTEGER
```

## 8.8 ImageArtifact

```text
id UUID PK
session_id UUID FK
logical_page_id UUID FK NULL
frame_id UUID FK NULL
artifact_type TEXT
storage_key TEXT
sha256 CHAR(64)
metadata JSONB
created_at TIMESTAMPTZ
```

Tipos:

- original;
- deskew;
- perspective;
- contrast;
- denoise;
- crop;
- question_crop;
- media_crop.

## 8.9 OCRRun

```text
id UUID PK
session_id UUID FK
logical_page_id UUID FK
provider TEXT
provider_model TEXT
status TEXT
started_at TIMESTAMPTZ
completed_at TIMESTAMPTZ
raw_storage_key TEXT
normalized JSONB
confidence JSONB
error_code TEXT
attempt INTEGER
```

## 8.10 Question

```text
id UUID PK
session_id UUID FK
question_number INTEGER
status TEXT
text TEXT
alternatives JSONB
page_refs JSONB
media_refs JSONB
ocr_refs JSONB
reconstruction_metadata JSONB
failure_reason TEXT
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ

UNIQUE(session_id, question_number)
```

Status:

- DISCOVERED
- INCOMPLETE
- RESCUING
- READY
- FAILED

## 8.11 KnowledgeDocument

```text
id UUID PK
title TEXT
discipline TEXT
subject TEXT
source_type TEXT
storage_key TEXT
sha256 CHAR(64)
metadata JSONB
active BOOLEAN
created_at TIMESTAMPTZ
```

## 8.12 KnowledgeChunk

```text
id UUID PK
document_id UUID FK
chunk_index INTEGER
text TEXT
fts TSVECTOR
embedding VECTOR(...)
page_number INTEGER NULL
section TEXT NULL
metadata JSONB
```

## 8.13 RetrievalRun

```text
id UUID PK
question_id UUID FK
query TEXT
provider TEXT
results JSONB
created_at TIMESTAMPTZ
```

## 8.14 AnswerAttempt

```text
id UUID PK
question_id UUID FK
role TEXT
provider TEXT
model TEXT
effort TEXT
prompt_version TEXT
status TEXT
answer TEXT NULL
structured_result JSONB
evidence_refs JSONB
latency_ms INTEGER
input_tokens INTEGER NULL
output_tokens INTEGER NULL
cost_estimate NUMERIC NULL
error_code TEXT NULL
attempt INTEGER
created_at TIMESTAMPTZ
```

`role`:

- solver
- verifier
- arbiter

## 8.15 FinalAnswer

```text
id UUID PK
question_id UUID FK UNIQUE
answer TEXT
status TEXT
decision_source TEXT
validated BOOLEAN
degraded_provider BOOLEAN
evidence_refs JSONB
created_at TIMESTAMPTZ
```

## 8.16 AudioArtifact

```text
id UUID PK
session_id UUID FK
artifact_type TEXT
storage_key TEXT
sha256 CHAR(64)
duration_ms INTEGER
status TEXT
metadata JSONB
created_at TIMESTAMPTZ
```

## 8.17 AuditEvent

```text
id BIGSERIAL PK
session_id UUID FK NULL
question_id UUID FK NULL
event_type TEXT
stage TEXT
severity TEXT
reason_code TEXT NULL
payload JSONB
created_at TIMESTAMPTZ
```

---

# 9. Estados da sessão

Usar enum de domínio com transições explícitas.

```text
CREATED
CAPTURING
CAPTURE_END_CANDIDATE
CAPTURE_LOCKING
LOCKED
IMAGE_PROCESSING
OCR_PROCESSING
RECONSTRUCTING
RESCUE_PROCESSING
GATE_1
BLOCKED_GATE_1
RAG_RETRIEVING
SOLVING
VERIFYING
ARBITRATING
GATE_2
BLOCKED_GATE_2
STATUS_AUDIO
TTS_GENERATING
AUDIO_ASSEMBLING
AUDIO_VALIDATING
READY
COMPLETED
FAILED_RECOVERABLE
FAILED_FATAL
CANCELLED
```

Implementar função única:

```python
transition_session(session, target_state, reason, actor)
```

Ela deve:

1. validar transição permitida;
2. atualizar estado;
3. gerar `AuditEvent`;
4. persistir atomicamente.

Nunca alterar `session.status` diretamente fora desta função/repositório.

---

# 10. Invariantes críticas

Estas invariantes devem ter testes próprios.

## Invariante 1

Uma sessão `LOCKED` não aceita silenciosamente novos frames na prova.

Uploads atrasados podem ser armazenados em área de auditoria, mas não alteram páginas lógicas sem operação explícita.

## Invariante 2

`LogicalPage` só é criada após FULL burst válido ou recuperação equivalente.

## Invariante 3

O marcador de FIM nunca vira página lógica.

## Invariante 4

Uma questão `FAILED` nunca recebe `FinalAnswer`.

## Invariante 5

Solver não pode iniciar enquanto Gate 1 não estiver aprovado.

## Invariante 6

TTS de gabarito não pode iniciar enquanto Gate 2 não estiver aprovado.

## Invariante 7

A resposta final precisa ser uma alternativa permitida pela questão.

## Invariante 8

Imagem original nunca é sobrescrita.

## Invariante 9

Operação repetida com a mesma idempotency key deve produzir o mesmo efeito lógico.

## Invariante 10

Falha de provider nunca é convertida em “resposta provável” silenciosamente.

---

# 11. Autenticação

## 11.1 Admin

Como haverá somente um operador:

- login com e-mail + senha;
- senha armazenada com Argon2id;
- cookie HttpOnly;
- Secure;
- SameSite=Strict;
- CSRF token para ações mutáveis;
- sessão expira;
- rate limit de login.

Não é necessário RBAC complexo na V1.

Mesmo assim, modelar `actor_type` nos logs para permitir expansão futura.

## 11.2 Android Gateway

Autenticação independente do admin.

Headers:

```http
Authorization: Bearer <gateway-token>
X-Gateway-Id: ...
```

O gateway token deve poder ser rotacionado.

## 11.3 Device

O ESP32 autentica-se localmente no Android.

Entre Android e VPS, o servidor deve receber:

- `device_id`;
- `gateway_id`;
- assinatura ou atestado do gateway;
- IDs e hashes da captura.

Não confiar diretamente em dados arbitrários enviados como `device_id`.

---

# 12. Storage

## 12.1 Supabase Storage

Buckets privados:

```text
pages-originals
pages-derived
ocr-raw
knowledge
audio
audit-exports
```

Não gerar URLs públicas permanentes.

Usar signed URLs de curta duração quando o painel precisar visualizar arquivos.

## 12.2 Convenção de keys

```text
sessions/{session_public_id}/frames/{capture_id}/{frame_index}.jpg
sessions/{session_public_id}/pages/{logical_index}/original.jpg
sessions/{session_public_id}/derived/{artifact_type}/{id}.jpg
sessions/{session_public_id}/ocr/{provider}/{logical_index}.json
sessions/{session_public_id}/audio/status/{id}.mp3
sessions/{session_public_id}/audio/final/{id}.mp3
```

## 12.3 Upload

Fluxo obrigatório:

```text
recebe upload
→ calcula/verifica SHA-256
→ valida limites
→ envia ao Supabase Storage
→ confirma objeto
→ grava DB
→ retorna sucesso
```

Se DB falhar após storage:

- registrar orphan object;
- retry;
- job de reconciliação.

Se storage falhar:

- não criar frame como persistido.

---

# 13. API REST do servidor

Prefixo:

```text
/api/v1
```

## 13.1 Health

```text
GET /health/live
GET /health/ready
GET /health/dependencies
```

`ready` testa apenas dependências essenciais e com timeout curto.

## 13.2 Admin auth

```text
POST /auth/login
POST /auth/logout
GET  /auth/me
```

## 13.3 Sessions

```text
POST   /sessions
GET    /sessions
GET    /sessions/{session_id}
POST   /sessions/{session_id}/finish-capture
POST   /sessions/{session_id}/cancel
POST   /sessions/{session_id}/pause
POST   /sessions/{session_id}/resume
GET    /sessions/{session_id}/events
GET    /sessions/{session_id}/summary
```

## 13.4 Gateway

```text
POST /gateway/hello
POST /gateway/session/start
POST /gateway/session/{session_id}/heartbeat
POST /gateway/session/{session_id}/capture
POST /gateway/session/{session_id}/frame
POST /gateway/session/{session_id}/capture-complete
POST /gateway/session/{session_id}/probe-analysis
GET  /gateway/session/{session_id}/policy
POST /gateway/session/{session_id}/end-signal
```

Opcional:

```text
WS /gateway/ws
```

WebSocket é acelerador, não dependência obrigatória.

O Android precisa funcionar com HTTP mesmo quando WebSocket cair.

## 13.5 Processing

Admin/debug:

```text
POST /sessions/{session_id}/reprocess/stage/{stage}
POST /questions/{question_id}/retry
POST /questions/{question_id}/reconstruct
GET  /questions/{question_id}
```

Esses endpoints exigem autenticação admin e audit event.

## 13.6 Knowledge

```text
POST   /knowledge/documents
GET    /knowledge/documents
GET    /knowledge/documents/{id}
DELETE /knowledge/documents/{id}
POST   /knowledge/documents/{id}/reindex
POST   /knowledge/search-test
```

## 13.7 Audio

```text
GET /sessions/{session_id}/audio
GET /sessions/{session_id}/audio/status
```

---

# 14. Idempotência

Toda operação de ingestão deve aceitar:

```http
Idempotency-Key: <uuid>
```

No banco:

```text
idempotency_keys
- key
- scope
- request_hash
- response_status
- response_body
- created_at
- expires_at
```

Para frames, identidade adicional:

```text
session_id + capture_id + frame_index + sha256
```

Se o Android reenviar o mesmo JPEG:

- retornar o mesmo resultado;
- não criar duplicata;
- não duplicar storage.

Se o mesmo `capture_id/frame_index` chegar com hash diferente:

- `409 CONFLICT`;
- criar evento crítico;
- não sobrescrever.

---

# 15. Capture Controller

## 15.1 Separação de responsabilidades

Não usar Temporal para cada PROBE.

O Capture Controller deve ser uma camada leve de runtime:

```text
Android ↔ API Capture Coordinator ↔ Supabase
```

Temporal começa o workflow pesado após `LOCK_SESSION`.

Isso evita transformar uma captura a cada ~1 segundo em milhares de Activities.

## 15.2 CapturePolicy

Objeto versionado:

```json
{
  "version": 1,
  "lease_id": "uuid",
  "valid_until": "...",
  "probe_interval_ms": 1200,
  "probe_resolution": "VGA",
  "probe_jpeg_quality": 18,
  "stable_probe_count": 2,
  "full_frames": 3,
  "full_resolution": "UXGA",
  "full_jpeg_quality": 10,
  "full_gap_ms": 220,
  "expected_pages": 30,
  "end": {
    "manual_enabled": true,
    "visual_marker_enabled": true,
    "open_hand_enabled": true,
    "soft_idle_seconds": 60,
    "hard_idle_seconds": 120
  }
}
```

Android mantém uma lease curta.

Se perder 4G:

- continua operando dentro da política permitida;
- armazena localmente;
- não inventa novas regras;
- ao reconectar, sincroniza eventos e frames.

## 15.3 PROBE

Servidor recebe metadata/probe e calcula:

- document presence;
- blur;
- perceptual hash;
- exposição;
- orientação;
- estabilidade;
- provável mudança de página;
- possível END.

Não executar OCR completo em probes.

## 15.4 Novo candidato

Critério configurável:

```text
document_present
AND stability_count >= N
AND perceptual_distance >= threshold
AND NOT end_marker
```

## 15.5 FULL

Quando há candidato:

```text
CAPTURE_FULL
3 frames
UXGA
```

O servidor aguarda burst completo ou timeout recuperável.

## 15.6 Quality score

Criar `FrameQualityScorer`.

Sinais:

- variance of Laplacian;
- glare/clipping;
- histogram;
- document boundary coverage;
- perspective;
- motion proxy;
- usable pixel area.

Score não deve fingir ser probabilidade.

Guardar componentes separadamente.

## 15.7 Página lógica

Se pelo menos um frame passar:

- rankear;
- primary;
- alternates;
- `logical_index += 1`.

Se nenhum passar:

- solicitar novo burst do mesmo candidato;
- não incrementar página.

---

# 16. Encerramento redundante

Ordem:

1. `logical_pages >= expected_pages`;
2. finalização manual;
3. marcador visual;
4. mão aberta validada;
5. inatividade conservadora.

## 16.1 Mão aberta

Não usar uma única detecção.

Exigir:

```text
open_hand_confidence >= threshold
AND no_exam_document
AND confirmations >= 2
AND confirmations_window <= 5s
```

## 16.2 Inatividade

`soft_idle`:

- alerta;
- não encerra.

`hard_idle`:

só encerra se:

- nenhum upload pendente;
- nenhum FULL em andamento;
- nenhuma mudança recente;
- consenso da cena.

## 16.3 LOCK_SESSION

Transação:

1. confirmar end reason;
2. status `CAPTURE_LOCKING`;
3. validar captures;
4. fechar conjunto de frames;
5. criar snapshot;
6. status `LOCKED`;
7. iniciar `ProcessExamWorkflow`.

---

# 17. Temporal

## 17.1 Workflow principal

```text
ProcessExamWorkflow(session_id)
```

Etapas:

```text
1. ValidateLockedSession
2. MaterializeLogicalPages
3. PreprocessPages
4. RunOCR
5. ReconstructExam
6. RescueIncompleteQuestions
7. EvaluateGate1
8. EmitPreCorrectionStatus
9. RetrieveKnowledge
10. SolveQuestions
11. VerifyQuestions
12. ArbitrateDisagreements
13. RescueFailedAnswers
14. EvaluateGate2
15. EmitPostCorrectionStatus
16. GenerateAnswerAudio
17. AssembleFinalAudio
18. ValidateFinalAudio
19. PublishFinalAudio
20. CompleteSession
```

## 17.2 Activity rules

Cada Activity:

- timeout explícito;
- retry policy explícita;
- idempotente;
- grava início/fim;
- retorna IDs, não blobs grandes;
- não passa JPEG binário pelo histórico do Temporal.

Imagens ficam no Storage.

## 17.3 Retry classes

### Retryable

- network timeout;
- HTTP 429;
- HTTP 5xx;
- transient storage;
- provider unavailable.

### Non-retryable

- invalid schema;
- unsupported image;
- missing required session data;
- authentication error;
- bad request determinístico.

## 17.4 Heartbeats

Activities longas, como:

- OCR local;
- FFmpeg;
- ingestion de conhecimento;

devem usar heartbeat.

## 17.5 Workflow versioning

Toda mudança incompatível no workflow precisa usar versionamento seguro.

Não modificar arbitrariamente lógica de workflows que possam estar em execução.

---

# 18. Processamento de imagem

Módulos:

```text
image/quality.py
image/document.py
image/preprocess.py
image/crops.py
image/fingerprint.py
```

## 18.1 ORIGINAL

Nunca modificar.

## 18.2 Derivados

Criar apenas quando necessário:

- corrected_orientation;
- perspective;
- CLAHE;
- denoise;
- sharpen;
- threshold.

## 18.3 CPU budget

Na VPS atual:

```text
MAX_IMAGE_PROCESSING_CONCURRENCY=1
```

OpenCV pesado deve passar por executor separado para não bloquear event loop.

## 18.4 Temp files

Usar diretório por session:

```text
/tmp/pages-to-audio/{session_id}/
```

Apagar:

- após upload dos derivados;
- em finally;
- via janitor periódico.

Limite total inicial:

```text
2 GB
```

Se exceder:

- interromper geração de derivados não essenciais;
- emitir alerta.

---

# 19. OCR provider abstraction

Interface:

```python
class OCRProvider(Protocol):
    async def analyze_page(self, request: OCRRequest) -> OCRResult:
        ...
```

`OCRRequest` contém:

- original storage ref;
- derived refs;
- page index;
- hints;
- requested features.

`OCRResult` normaliza:

- text;
- blocks;
- lines;
- tokens;
- bounding boxes;
- reading order;
- tables;
- formulas when available;
- provider confidence;
- raw result ref.

## 19.1 Providers

Implementar:

```text
GoogleDocumentAIProvider
AzureDocumentIntelligenceProvider
PaddleOCRProvider
```

## 19.2 Política inicial

### Normal

Google Document AI primário.

### Incerteza

Rodar segundo provider.

### Google indisponível

Azure fallback.

### Paddle

Tertiary/independent validator, inicialmente:

```text
PADDLE_OCR_ENABLED=false
```

por causa da VPS de 2 vCPU.

O código precisa estar preparado para um worker Paddle rodando em outro computador/VPS no futuro.

## 19.3 Não serializar vendor format pelo domínio

Guardar raw vendor result separadamente.

A lógica de reconstrução usa apenas `NormalizedOCRResult`.

---

# 20. Visual Understanding

Interface:

```python
class VisionProvider(Protocol):
    async def analyze_region(self, request: VisionRequest) -> VisionResult:
        ...
```

Usos:

- gráfico;
- química;
- circuito;
- geometria;
- tirinha;
- mapa;
- fotografia;
- tabela complexa;
- região OCR conflitante.

Claude Vision pode participar desta etapa, mas isso não equivale ao Solver ainda.

---

# 21. Reconstrução do exame

## 21.1 Input

Todas as páginas lógicas em ordem.

Para cada página:

- primary original;
- alternates;
- OCR normalizado;
- layout;
- crops;
- page number inferred.

## 21.2 Output estruturado

```json
{
  "questions": [
    {
      "question_number": 1,
      "text": "...",
      "alternatives": {
        "A": "...",
        "B": "...",
        "C": "...",
        "D": "..."
      },
      "page_refs": [1, 2],
      "media_refs": [],
      "source_regions": [],
      "completeness": "complete",
      "flags": []
    }
  ]
}
```

Validar com Pydantic.

## 21.3 Prompt

Arquivo:

```text
prompts/reconstruction/v1.md
```

Não colocar prompt hardcoded no Python.

Registrar hash e versão.

## 21.4 Validações determinísticas

Após LLM:

- question numbers únicos;
- ordem plausível;
- alternativas não vazias;
- números esperados;
- lacunas;
- duplicatas;
- continuidade.

---

# 22. Rescue de reconstrução

Para cada questão problemática:

1. alternate frame;
2. novo preprocessamento;
3. OCR secundário;
4. crop dirigido;
5. Vision Provider;
6. páginas anterior/posterior;
7. reconstrução específica;
8. comparação de variantes;
9. tentativa final multimodal.

Cada rescue tem budget máximo.

Não criar loop infinito.

Exemplo:

```text
MAX_RECONSTRUCTION_RESCUE_ROUNDS=3
```

Registrar `reason_code`.

---

# 23. Gate 1

Fórmula:

```python
required = ceil(expected_questions * minimum_ratio)
ready = count(Question.status == READY)
```

Para 70:

```text
required = 63
```

## Resultado

### `ready == expected`

- status success;
- áudio “70 de 70...”.

### `required <= ready < expected`

- prosseguir;
- `session.degraded_mode = true`;
- registrar questões falhas;
- áudio avisa quantidade.

### `ready < required`

- `BLOCKED_GATE_1`;
- não iniciar RAG/Solver;
- gerar status de falha;
- encerrar processamento acadêmico.

---

# 24. Knowledge ingestion

Pipeline independente:

```text
upload
→ extract
→ normalize
→ split
→ metadata
→ embed
→ pgvector
→ FTS
→ validate
→ active
```

## 24.1 Formatos

V1:

- PDF;
- Markdown;
- TXT;
- CSV;
- texto colado.

DOCX pode entrar depois.

## 24.2 Chunking

Não usar tamanho fixo ingênuo como única regra.

Preservar:

- títulos;
- capítulos;
- seções;
- páginas;
- tabelas;
- tópicos.

## 24.3 Embeddings

Criar interface:

```python
class EmbeddingProvider(Protocol):
    async def embed_documents(...)
    async def embed_query(...)
```

A escolha do provider fica configurável.

Antes de produção, benchmarkar pelo menos dois modelos adequados a português e conteúdo acadêmico.

O schema não pode depender da marca do provider.

---

# 25. Hybrid RAG

Executar:

1. query expansion curta;
2. FTS;
3. vector search;
4. Reciprocal Rank Fusion;
5. filtros por disciplina/assunto;
6. reranking;
7. top evidence.

Supabase suporta pgvector + Full Text Search, portanto a implementação inicial deve usar o próprio Postgres.

Não usar Vector Buckets alpha como dependência central da V1.

## 25.1 Retrieval contract

```json
{
  "question_id": "...",
  "query": "...",
  "hits": [
    {
      "chunk_id": "...",
      "document_id": "...",
      "score": 0.0,
      "text": "...",
      "page": 22,
      "source": "..."
    }
  ]
}
```

## 25.2 Teste isolado

Criar endpoint/admin:

```text
POST /knowledge/search-test
```

para medir retrieval sem chamar LLM.

---

# 26. LLM abstraction

Interface:

```python
class ReasoningProvider(Protocol):
    async def solve(self, request: SolveRequest) -> SolveResult:
        ...
    async def verify(self, request: VerifyRequest) -> VerifyResult:
        ...
    async def arbitrate(self, request: ArbitrateRequest) -> ArbitrateResult:
        ...
```

Implementações:

```text
AnthropicProvider
DeepSeekProvider
```

Nunca importar SDK vendor diretamente na camada de domínio.

---

# 27. Política Anthropic → DeepSeek

## 27.1 Primário

Claude Opus 5.

Configuração por environment:

```text
ANTHROPIC_MODEL_SOLVER
ANTHROPIC_MODEL_VERIFIER
ANTHROPIC_MODEL_ARBITER
```

Não hardcode IDs em dezenas de arquivos.

## 27.2 Fallback

DeepSeek V4 Pro.

Model ID:

```text
deepseek-v4-pro
```

Thinking habilitado.

Esforço:

```text
high
```

e `max` para arbitragem/fallback difícil quando suportado.

## 27.3 Quando acionar fallback

Fallback **não** é chamado simplesmente porque o Claude escolheu uma letra inesperada.

Acionar quando:

- timeout após retry budget;
- 429 persistente;
- 5xx persistente;
- provider indisponível;
- resposta sem conformidade de schema após repair retry;
- erro técnico do provider.

Opcionalmente, configuração futura:

```text
DEEPSEEK_CROSSCHECK_ON_HIGH_RISK=false
```

## 27.4 Provider degraded mode

Se DeepSeek for usado:

```text
session.degraded_mode = true
answer_attempt.degraded_provider = true
```

O painel mostra:

```text
Fallback de IA utilizado em N questões
```

## 27.5 Falha dos dois

Se Anthropic e DeepSeek falharem:

- a questão não recebe letra;
- status FAILED;
- rescue/retry;
- Gate 2 decide.

## 27.6 Não vazar reasoning

Não armazenar chain-of-thought bruto.

Guardar:

- resposta estruturada;
- evidências;
- metadados;
- breve rationale permitido/configurado, se necessário para auditoria;
- nunca depender de reasoning privado para funcionamento.

---

# 28. Structured outputs

Schema do Solver:

```json
{
  "question_number": 17,
  "answer": "C",
  "evidence_ids": ["..."],
  "needs_visual_recheck": false,
  "ambiguity_flags": []
}
```

Verifier:

```json
{
  "question_number": 17,
  "answer": "C",
  "evidence_ids": ["..."],
  "verification_status": "supported",
  "ambiguity_flags": []
}
```

Arbiter:

```json
{
  "question_number": 17,
  "answer": "C",
  "decision": "resolved",
  "evidence_ids": ["..."],
  "ambiguity_flags": []
}
```

Pydantic valida.

Se inválido:

1. repair retry;
2. se continuar inválido, provider fallback;
3. se falhar, marcar attempt FAILED.

---

# 29. Solver

Input:

- question text;
- alternatives;
- media crops;
- original region;
- OCR evidence;
- RAG evidence;
- prompt version.

A resposta deve ser somente uma das alternativas permitidas.

Não pedir texto longo.

---

# 30. Verifier

Deve resolver independentemente.

Não enviar:

```text
“O Solver respondeu C. Confirme.”
```

Enviar a mesma questão e evidências necessárias, mas sem a conclusão anterior.

Depois comparar deterministicamente.

---

# 31. Arbiter

Acionar quando:

- solver != verifier;
- algum ambiguity flag crítico;
- OCR conflictante;
- visual dependency crítica;
- evidence conflict.

Input pode conter:

- resultado do Solver;
- resultado do Verifier;
- evidências;
- crops adicionais;
- OCRs divergentes.

O Arbiter decide.

Se continuar ambíguo:

- rescue;
- nova arbitragem dentro do budget;
- FAILED se não resolver.

---

# 32. Paralelismo LLM

VPS não executa o modelo, então o gargalo é rede/API.

Mesmo assim limitar:

```text
MAX_LLM_CONCURRENCY=6
```

Começar com 4 e medir.

Não disparar 70 × Solver + 70 × Verifier ao mesmo tempo sem controle.

Usar semaphore por provider.

Também respeitar 429 e headers de retry.

---

# 33. Gate 2

```python
validated = count(FinalAnswer.validated == True)
required = ceil(expected_questions * minimum_ratio)
```

## 33.1 100%

Prossegue com áudio completo.

## 33.2 90–99%

Prossegue com aviso.

Áudio do gabarito contém somente perguntas validadas.

Não inserir:

```text
“Questão 17, sem resposta”
```

a menos que o produto seja alterado explicitamente.

## 33.3 <90%

`BLOCKED_GATE_2`.

Não gerar áudio de gabarito.

Gerar somente áudio de falha/status.

---

# 34. Status audio

O Android será capaz de usar TTS local para mensagens críticas.

O servidor também poderá gerar status audio opcional.

Mensagens mínimas:

### Gate 1 100%

```text
Captura validada. 70 de 70 questões reconhecidas. Iniciando correção.
```

### Gate 1 degradado

```text
68 de 70 questões reconhecidas. 2 falhas registradas. Iniciando correção.
```

### Gate 1 falhou

```text
Falha de processamento. 61 de 70 questões válidas. 9 falhas. Processo encerrado.
```

### Gate 2 100%

```text
Correção concluída. 70 de 70 respostas validadas.
```

### Gate 2 degradado

```text
Correção concluída. 67 de 70 respostas validadas. 3 falhas registradas.
```

### Gate 2 falhou

```text
Falha de correção. Quantidade mínima de respostas validadas não atingida. Processo encerrado.
```

---

# 35. TTS provider abstraction

Interface:

```python
class TTSProvider(Protocol):
    async def synthesize(self, request: TTSRequest) -> TTSSegment:
        ...
```

Implementações:

```text
GoogleTTSProvider
AzureTTSProvider
```

Config:

```text
TTS_PROVIDER=google
TTS_FALLBACK_PROVIDER=azure
```

Benchmarkar português brasileiro antes de congelar voz.

---

# 36. Construção do áudio final

Não depender apenas de SSML para pausas.

Fluxo:

```text
cada frase → TTS segment
→ normalizar áudio
→ FFmpeg concat
→ inserir silêncio físico
→ validar duração
```

Primeira rodada:

- voz levemente mais lenta;
- 2 segundos entre itens.

Após última resposta:

- 20 segundos.

Segunda rodada:

- velocidade normal;
- 1 segundo.

## 36.1 Texto

Formato:

```text
Questão 1. Letra B.
```

Sem explicações.

## 36.2 Validação

Antes de READY:

- arquivo existe;
- tamanho > mínimo;
- duração plausível;
- FFprobe válido;
- SHA-256;
- número de segmentos esperado;
- 20 s central presentes dentro de tolerância.

---

# 37. Painel administrativo

## Tela principal

Cards:

```text
Dispositivo
Android
VPS
Sessão atual
Páginas lógicas
Questões
Gate 1
Solver
Verifier
Arbitragem
Gate 2
Áudio
```

## Session detail

Mostrar timeline.

Exemplo:

```text
22:31:02 SESSION_CREATED
22:31:08 DEVICE_CONNECTED
22:31:10 CAPTURE_STARTED
22:33:44 LOGICAL_PAGE_25_ACCEPTED
22:33:55 END_MARKER_CONFIRMED
22:33:56 SESSION_LOCKED
...
```

## Questions

Tabela:

```text
Nº | status | páginas | solver | verifier | arbiter | final | provider fallback
```

## Question detail

Mostrar:

- imagens;
- crops;
- OCR;
- RAG hits;
- answer attempts;
- final answer;
- errors;
- retries.

Não mostrar reasoning privado.

## Admin actions

- finalizar captura;
- pausar;
- retomar;
- cancelar;
- reprocessar estágio;
- retry questão;
- baixar logs;
- baixar áudio.

Toda ação gera AuditEvent.

---

# 38. Eventos em tempo real

Usar Server-Sent Events inicialmente:

```text
GET /api/v1/sessions/{id}/stream
```

Mais simples que WebSocket para painel.

Eventos:

```text
session.state_changed
capture.received
logical_page.accepted
question.updated
gate.result
provider.fallback
audio.ready
error
```

Frontend reconecta usando `Last-Event-ID`.

---

# 39. Observabilidade

## 39.1 Logs JSON

Campos:

```text
timestamp
level
service
request_id
trace_id
session_id
question_id
capture_id
frame_id
stage
provider
attempt
duration_ms
reason_code
```

## 39.2 Nunca logar

- API keys;
- passwords;
- gateway token;
- bearer token;
- raw reasoning;
- URLs assinadas completas;
- conteúdo sensível desnecessário.

## 39.3 Sentry

Capturar:

- exceptions;
- release;
- environment;
- trace;
- session public id como tag.

## 39.4 OpenTelemetry

Instrumentar:

- FastAPI;
- httpx;
- SQLAlchemy;
- Temporal;
- provider calls.

## 39.5 Métricas

Inicialmente expor `/metrics` apenas internamente.

Métricas:

```text
sessions_total
sessions_failed_total
frames_received_total
frame_upload_retries_total
logical_pages_total
ocr_requests_total
ocr_failures_total
llm_requests_total
llm_fallback_total
gate1_ratio
gate2_ratio
processing_duration_seconds
provider_latency_seconds
audio_generation_seconds
local_temp_bytes
```

---

# 40. Reason codes

Criar enum central.

Exemplos:

```text
FRAME_HASH_MISMATCH
FRAME_DUPLICATE_CONFLICT
STORAGE_UPLOAD_FAILED
CAPTURE_INCOMPLETE
NO_USABLE_FRAME
OCR_PROVIDER_TIMEOUT
OCR_LOW_CONFIDENCE
QUESTION_NUMBER_MISSING
QUESTION_ALTERNATIVES_INCOMPLETE
QUESTION_VISUAL_AMBIGUITY
GATE_1_BELOW_THRESHOLD
ANTHROPIC_TIMEOUT
ANTHROPIC_RATE_LIMIT
ANTHROPIC_INVALID_SCHEMA
DEEPSEEK_TIMEOUT
DEEPSEEK_INVALID_SCHEMA
SOLVER_VERIFIER_DISAGREEMENT
ARBITRATION_UNRESOLVED
GATE_2_BELOW_THRESHOLD
TTS_PROVIDER_FAILED
AUDIO_VALIDATION_FAILED
```

Não usar mensagens livres como chave de lógica.

---

# 41. Circuit breaker

Para APIs externas:

- timeout;
- retry exponential;
- jitter;
- circuit breaker.

Se Anthropic tiver falhas consecutivas:

- abrir circuit breaker curto;
- direcionar para DeepSeek fallback;
- tentar half-open depois.

Se Google OCR cair:

- Azure fallback.

Não ficar tentando provider indisponível dezenas de vezes para cada questão.

---

# 42. Timeouts iniciais

Valores serão calibrados.

Sugestão inicial:

```text
HTTP generic connect: 10s
HTTP generic read: 60s
Google OCR: 90s
Azure OCR: 90s
Anthropic solver: 180s
Anthropic arbiter: 240s
DeepSeek fallback: 240s
Supabase operation: 30s
FFmpeg: 120s
```

Temporal Activity timeout deve ser um pouco maior que o provider timeout + retry interno.

---

# 43. Retry budget

Não misturar retries infinitos.

Exemplo:

```text
provider internal retries: 2
Temporal activity attempts: 3
rescue rounds: 3
```

A combinação deve ter limite global.

Guardar `attempt`.

---

# 44. Resource budgets na VPS

## API

Começar:

```text
1 container
1 uvicorn worker
async
```

Uma única pessoa usando o sistema não precisa de 4 workers.

## Worker Temporal

```text
1 container
```

Concorrência:

```text
image CPU: 1
OCR external: 3
LLM: 4–6
audio: 1–2
```

## Admin

Build estático.

## Disk

O container não deve criar volume grande permanente.

Alertar em:

```text
free disk < 15 GB
```

Bloquear processamento pesado opcional em:

```text
free disk < 10 GB
```

Nunca consumir os 23 GB livres com fotos.

---

# 45. Docker Compose produção

Serviços da aplicação:

```text
pages-api
pages-worker
pages-admin-static (opcional, ou arquivos no proxy)
```

Não incluir:

- PostgreSQL;
- MinIO;
- Elasticsearch;
- modelos LLM.

Se Temporal Cloud:

nenhum container Temporal.

Se Temporal self-host futuro:

arquivo compose separado.

## Limites

Definir limites de recursos no deploy.

Exemplo de alvo inicial:

```text
api: 1.0 GB RAM
worker: 2.0–2.5 GB RAM
```

CPU shares limitadas.

Não reservar toda RAM da VPS.

---

# 46. GitHub Actions

Pipeline:

```text
checkout
→ setup Python
→ install uv
→ sync
→ ruff
→ typecheck
→ pytest unit
→ pytest integration
→ build Docker
→ frontend lint/test/build
```

Deploy somente após sucesso.

## Produção

Opção:

- GitHub Actions SSH;
- pull image;
- migration;
- rolling/restart;
- health check.

Nunca fazer:

```text
git pull && docker compose down
```

sem health/recovery.

---

# 47. Migrations

Regra:

1. migration forward;
2. deploy código compatível;
3. depois limpeza em release futuro.

Antes de migration destrutiva:

- backup;
- verificar compatibilidade.

Claude Code não pode editar migration aplicada.

---

# 48. Backup

Supabase:

- habilitar backups conforme plano;
- export periódico das tabelas críticas.

Storage:

- imagens não precisam ficar para sempre se política permitir;
- definir retenção.

Sugestão inicial de retenção:

```text
originals: 30 dias
derived: 14 dias
ocr raw: 30 dias
audit metadata: 180 dias
final answer/audio: 30 dias
```

Configurar, não hardcode.

Materiais RAG: persistentes.

---

# 49. Segurança

## Servidor

- TLS no proxy;
- firewall;
- somente portas necessárias;
- containers não-root quando possível;
- read-only filesystem quando possível;
- secrets fora da imagem;
- atualizações de segurança.

## Supabase

- service role apenas backend;
- nunca frontend;
- buckets privados;
- RLS para acesso do painel se usar client direto — preferencialmente painel fala com backend.

## Upload

- MIME allowlist;
- tamanho máximo;
- JPEG/PNG/WebP apenas conforme contrato;
- validar magic bytes;
- não confiar em extensão.

---

# 50. Testes

## 50.1 Unit

Cobrir:

- state machine;
- gate calculation;
- idempotency;
- hash;
- quality scoring;
- provider fallback;
- answer validation;
- audio plan;
- reason codes.

## 50.2 Contract

Mock dos providers.

Testar:

- Anthropic valid;
- Anthropic timeout;
- Anthropic 429;
- DeepSeek fallback;
- invalid schema;
- Google OCR;
- Azure fallback.

## 50.3 Integration

Com banco de teste.

Testar:

```text
create session
→ frames
→ logical pages
→ lock
→ workflow
```

## 50.4 E2E simulado

Criar dataset pequeno:

```text
5 páginas
10 questões
```

Sem APIs reais, providers fake determinísticos.

Depois dataset real:

```text
30 páginas
70 questões
```

## 50.5 Chaos/fault injection

Obrigatório antes de produção:

- matar API;
- matar worker;
- reiniciar worker;
- duplicar frames;
- hash errado;
- storage timeout;
- OCR 500;
- Anthropic timeout;
- Anthropic 429;
- DeepSeek timeout;
- TTS timeout;
- restart no meio da questão 37;
- restart no meio do FFmpeg.

---

# 51. Fixtures e dataset dourado

Criar:

```text
tests/fixtures/golden/
```

Não versionar material confidencial em Git público.

Golden dataset deverá conter:

- imagens;
- expected logical pages;
- expected questions;
- expected answers;
- expected flags.

Métricas:

```text
page detection precision/recall
question reconstruction rate
answer accuracy
Gate 1 ratio
Gate 2 ratio
runtime
provider fallback rate
```

---

# 52. Benchmarks obrigatórios

Antes de congelar produção:

## Captura

- JPEG quality;
- blur thresholds;
- 2 vs 3 frames;
- probe cadence.

## OCR

- Google;
- Azure;
- Paddle em worker disponível.

## RAG

- embedding model A/B;
- chunk size;
- RRF;
- top K;
- reranker.

## LLM

- Opus primary;
- DeepSeek fallback;
- disagreement cases.

## TTS

- Google vs Azure;
- clareza na JBL;
- velocidade.

---

# 53. Fases de implementação para Claude Code

---

## FASE 0 — Bootstrap

### Objetivo

Projeto sobe localmente e passa quality checks.

### Implementar

- monorepo;
- `pyproject.toml`;
- `uv`;
- FastAPI;
- settings;
- logging;
- Docker;
- health endpoints;
- pytest;
- Ruff;
- typecheck;
- `CLAUDE.md`.

### Fora de escopo

- banco real;
- OCR;
- LLM;
- frontend funcional.

### Testes

- app import;
- `/health/live`;
- settings;
- logging redaction.

### DoD

```text
make test
make lint
docker build
```

verdes.

---

## FASE 1 — Banco, domínio e estados

### Implementar

- SQLAlchemy models;
- Alembic;
- session state machine;
- AuditEvent;
- repositories;
- transactions;
- idempotency table.

### Testes

- todas transições válidas;
- transições inválidas;
- unique constraints;
- idempotency.

### DoD

Banco pode representar integralmente uma sessão sem providers.

---

## FASE 2 — Storage e ingestão

### Implementar

- Supabase Storage adapter;
- frame ingest;
- SHA;
- MIME;
- idempotency;
- captures;
- gateway auth;
- Android simulator.

### Testes

- frame válido;
- duplicado;
- conflito;
- hash ruim;
- storage timeout.

### DoD

Simulador envia 100 frames com retries e banco/storage ficam corretos.

---

## FASE 3 — Capture Controller

### Implementar

- CapturePolicy;
- probes;
- quality;
- pHash;
- logical pages;
- full burst lifecycle;
- end conditions;
- lock transaction.

### Testes

- página duplicada;
- página nova;
- burst ruim;
- manual end;
- expected pages;
- open-hand event fake;
- inactivity.

### DoD

Simulador produz N páginas lógicas corretamente.

---

## FASE 4 — Temporal skeleton

### Implementar

- client;
- worker;
- `ProcessExamWorkflow`;
- activities fake;
- retries;
- timeouts;
- workflow tests.

### DoD

Após LOCK, workflow percorre estados com providers fake e retoma após worker restart.

---

## FASE 5 — Image + OCR

### Implementar

- temp manager;
- OpenCV preprocessing;
- OCR abstractions;
- Google;
- Azure;
- normalized OCR;
- Paddle stub/optional worker.

### Testes

- provider fake;
- real provider smoke test opcional;
- fallback.

### DoD

Página real gera OCR normalizado armazenado e auditável.

---

## FASE 6 — Reconstruction + Gate 1

### Implementar

- reconstruction schema;
- prompt v1;
- LLM reconstruction;
- deterministic checks;
- rescue engine;
- Gate 1;
- status message.

### DoD

Golden dataset reconstrói números e alternativas dentro da meta definida.

---

## FASE 7 — Knowledge + RAG

### Implementar

- document ingestion;
- chunking;
- pgvector;
- FTS;
- hybrid;
- RRF;
- search-test;
- retrieval audit.

### DoD

Queries de benchmark recuperam chunks corretos com métricas registradas.

---

## FASE 8 — Solver / Verifier / Arbiter

### Implementar

- AnthropicProvider;
- DeepSeekProvider;
- fallback policy;
- structured outputs;
- solver;
- verifier independente;
- arbiter;
- concurrency;
- circuit breaker;
- cost/latency metadata.

### Testes

- Opus success;
- Opus timeout → DeepSeek;
- Opus 429 → DeepSeek;
- invalid schema;
- disagreement;
- both fail.

### DoD

Nenhuma questão obtém final answer fora da política.

---

## FASE 9 — Gate 2 + TTS

### Implementar

- final validation;
- Gate 2;
- TTS providers;
- FFmpeg;
- two rounds;
- checksum;
- duration validation.

### DoD

Áudio final contém exatamente as respostas validadas com pausas corretas.

---

## FASE 10 — Painel

### Implementar

- login;
- dashboard;
- session list/detail;
- question detail;
- SSE;
- finalization;
- retries admin;
- logs;
- audio download.

### DoD

Operador executa e audita sessão inteira pelo navegador.

---

## FASE 11 — Hardening

### Implementar

- Sentry;
- OTel;
- metrics;
- runbooks;
- cleanup;
- backup;
- security headers;
- rate limits;
- chaos suite;
- resource limits.

### DoD

Fault injection não causa perda silenciosa nem resposta inventada.

---

## FASE 12 — Deploy

### Implementar

- prod compose;
- migrations;
- health;
- proxy integration;
- GitHub Actions;
- rollback;
- operations docs.

### DoD

Deploy repetível sem intervenção manual em código.

---

# 54. Comandos padronizados

`Makefile`:

```text
make install
make dev
make test
make test-unit
make test-integration
make lint
make typecheck
make migrate
make migration name="..."
make api
make worker
make admin
make simulator
make e2e
make benchmark
```

O Claude Code deve manter esses comandos funcionando.

---

# 55. Desenvolvimento local

Ambiente local recomendado:

```text
FastAPI
Temporal dev server
Supabase hosted dev project
React dev server
provider mocks
```

APIs reais ficam opt-in.

Exemplo:

```text
USE_REAL_ANTHROPIC=false
USE_REAL_DEEPSEEK=false
USE_REAL_OCR=false
```

Nunca gastar API durante unit tests.

---

# 56. Staging

Criar ambiente staging separado:

- banco Supabase separado ou schema/projeto separado;
- bucket separado;
- Temporal namespace separado;
- API keys com orçamento;
- domínio staging.

Nunca testar migration perigosa diretamente em produção.

---

# 57. Produção

Produção precisa de:

```text
domain
TLS
Supabase prod
Temporal prod
Anthropic key
DeepSeek key
OCR keys
TTS key
Sentry
backup
```

Antes de ativar:

- `pytest`;
- integration;
- migrations dry run;
- storage test;
- provider smoke tests;
- disk free;
- memory available.

---

# 58. Fluxo E2E definitivo

```text
ESP32 inicia
↓
Android cria/retoma sessão
↓
VPS registra session
↓
Android recebe CapturePolicy
↓
PROBEs
↓
nova página estável
↓
FULL burst
↓
frames → Android → VPS
↓
quality
↓
LogicalPage
↓
repete
↓
END
↓
LOCK_SESSION
↓
Temporal
↓
image preprocessing
↓
OCR ensemble
↓
reconstruction
↓
rescue
↓
Gate 1
├─ <90% → falha + status audio → fim
└─ >=90%
     ↓
     RAG
     ↓
     Opus Solver
     ↓
     Opus Verifier
     ↓
     discordância?
       ├─ não → validate
       └─ sim → Opus Arbiter
                 ↓
        falha Anthropic?
                 ↓
        DeepSeek V4 Pro fallback
                 ↓
          final answers
                 ↓
              Gate 2
       ├─ <90% → falha + status audio → fim
       └─ >=90%
             ↓
            TTS
             ↓
           FFmpeg
             ↓
         validate audio
             ↓
       Supabase Storage
             ↓
          Android
             ↓
            JBL
```

---

# 59. Política de fallback completa

## OCR

```text
Google
→ retry
→ Azure
→ alternate frame
→ preprocessing variant
→ Vision
→ Paddle optional
→ failed
```

## LLM

```text
Claude Opus 5
→ retry
→ schema repair
→ retry
→ DeepSeek V4 Pro
→ retry
→ failed
```

## TTS

```text
Google
→ retry
→ Azure
→ failed
```

## Storage

```text
Supabase
→ retry
→ fail activity
→ Temporal retry
```

Nenhum fallback deve ficar escondido.

---

# 60. Qualidade e segurança acadêmica

O sistema deve preferir:

```text
“não consegui validar esta questão”
```

a:

```text
“provavelmente é B”
```

Regras:

- não preencher lacunas;
- não inferir alternativa ausente sem evidência;
- não mascarar OCR ruim;
- não tratar confiança autodeclarada do LLM como probabilidade;
- consenso entre sinais é mais importante;
- toda resposta final deve ser rastreável.

---

# 61. Critérios de aceite do servidor V1

## Captura

- nenhum frame persistido é perdido;
- duplicatas são idempotentes;
- hash mismatch bloqueia;
- páginas lógicas corretas;
- end redundante;
- lock imutável.

## Processamento

- original preservado;
- OCR normalizado;
- questão multi-página suportada;
- visual assets suportados;
- rescue limitado/auditado.

## Gates

- 63/70 passa;
- 62/70 bloqueia;
- Gate 2 mesma regra;
- nenhum gabarito abaixo de 90%.

## IA

- Opus primary;
- DeepSeek V4 Pro fallback técnico;
- verifier independente;
- arbiter;
- structured outputs;
- nenhum reasoning privado armazenado.

## Áudio

- número + letra;
- primeira rodada 2s;
- pausa 20s;
- segunda 1s;
- checksum.

## Operações

- reinício do worker retoma;
- API restart não corrompe;
- storage retry;
- logs;
- painel;
- backup;
- resource limits.

---

# 62. Critérios de performance iniciais

Qualidade tem prioridade sobre tempo.

Ainda assim medir:

```text
capture finalizada → Gate 1
Gate 1 → answers final
answers → audio READY
total
```

Não definir SLA agressivo antes de benchmark real.

Meta inicial de engenharia:

- evitar trabalho serial desnecessário;
- usar paralelismo externo limitado;
- não sacrificar validação para reduzir segundos.

---

# 63. Runbooks obrigatórios

Criar:

```text
docs/runbooks/anthropic_outage.md
docs/runbooks/deepseek_outage.md
docs/runbooks/ocr_outage.md
docs/runbooks/supabase_outage.md
docs/runbooks/temporal_worker_down.md
docs/runbooks/disk_low.md
docs/runbooks/session_stuck.md
docs/runbooks/reprocess_question.md
docs/runbooks/rollback.md
```

Cada runbook:

- sintomas;
- diagnóstico;
- comandos;
- impacto;
- recuperação;
- como verificar.

---

# 64. Sequência recomendada de trabalho com Claude Code

Para cada fase:

1. abrir repositório;
2. pedir para Claude Code ler:
   - `CLAUDE.md`;
   - `IMPLEMENTATION_PLAN.md`;
   - docs existentes;
3. informar explicitamente a fase;
4. pedir plano de mudanças antes de escrever;
5. implementar;
6. executar testes;
7. corrigir;
8. atualizar docs;
9. commit.

Prompt-base:

```text
Leia integralmente CLAUDE.md e IMPLEMENTATION_PLAN.md.

Implemente somente a FASE X.
Não implemente funcionalidades de fases futuras salvo interfaces/stubs estritamente necessários.

Antes de alterar arquivos:
1. resuma o escopo;
2. liste arquivos que pretende criar/alterar;
3. identifique riscos;
4. confirme invariantes aplicáveis.

Depois:
1. implemente;
2. execute lint, typecheck e testes;
3. corrija todos os erros;
4. mostre os resultados;
5. atualize a documentação da fase;
6. não marque a fase como concluída se algum critério de aceite estiver pendente.
```

---

# 65. Definition of Done global

O servidor V1 só pode ser considerado concluído quando:

- Fases 0–12 finalizadas;
- migrations reproduzíveis;
- E2E golden dataset;
- Gate 1 testado em 100%, 90%, 89%;
- Gate 2 testado em 100%, 90%, 89%;
- Anthropic outage simulado;
- DeepSeek fallback confirmado;
- OCR primary outage simulado;
- restart de worker validado;
- restart de API validado;
- audio validado;
- painel funcional;
- logs auditáveis;
- nenhum segredo no Git;
- recursos da VPS medidos;
- runbooks prontos;
- backup testado;
- rollback testado.

---

# 66. Primeira milestone útil

Não começar tentando responder questões.

A primeira milestone real é:

> “O simulador Android cria uma sessão, envia capturas, o servidor persiste tudo no Supabase, forma páginas lógicas, encerra e bloqueia corretamente o lote, sem duplicação ou perda.”

Somente depois:

> OCR.

Depois:

> reconstrução.

Depois:

> IA.

Essa ordem reduz drasticamente o retrabalho.

---

# 67. Segunda milestone

> “Uma sessão bloqueada com imagens reais produz questões estruturadas e Gate 1 correto, ainda sem responder.”

Aqui validamos a parte mais difícil antes da IA acadêmica:

- OCR;
- layout;
- continuidade;
- visual;
- resgate.

---

# 68. Terceira milestone

> “Um conjunto de questões READY passa por RAG → Opus → Verifier → Arbiter/DeepSeek fallback → Gate 2.”

Ainda sem áudio.

---

# 69. Quarta milestone

> “Uma sessão real completa gera e publica o MP3 final e o painel explica exatamente como cada resposta foi obtida.”

---

# 70. Decisões que ficam configuráveis

Não hardcode:

- 30 páginas;
- 70 questões;
- 90%;
- número de frames;
- JPEG quality;
- thresholds;
- OCR primary;
- OCR fallback;
- LLM models;
- effort;
- concurrency;
- TTS;
- retention;
- timeouts;
- retries.

Toda sessão grava `config_snapshot`.

Assim mudanças futuras não tornam auditorias antigas ambíguas.

---

# 71. Pontos que não devem bloquear o início

Podem ser decididos por benchmark depois:

- embedding provider definitivo;
- voz TTS definitiva;
- threshold de pHash;
- blur score;
- OCR secundário preferido;
- Paddle local/remote;
- concurrency final;
- retenção.

A interface deve existir desde o início.

---

# 72. Pontos que devem ser congelados antes da primeira linha de produção

- schema;
- invariantes;
- estados;
- idempotência;
- locking;
- Gate 1;
- Gate 2;
- provider fallback;
- storage policy;
- audit events;
- retry limits;
- segurança.

---

# 73. Observação sobre DeepSeek V4 Pro

A implementação deverá usar o model id configurável com default:

```text
deepseek-v4-pro
```

O provider deve suportar:

- thinking enabled;
- reasoning effort `high`;
- `max` em arbitragem/fallback de alta complexidade quando configurado;
- JSON/structured parsing validado localmente;
- timeouts;
- 429;
- retries;
- circuit breaker.

O adapter deve permanecer isolado para permitir troca de modelo sem alterar Solver/Verifier/Arbiter.

---

# 74. Observação sobre Supabase RAG

Na V1, usar:

```text
Postgres
+ pgvector
+ tsvector
+ HNSW quando fizer sentido
+ Reciprocal Rank Fusion
```

Não tornar a aplicação dependente de features alpha de Vector Buckets.

---

# 75. Plano operacional da VPS

Como a VPS é compartilhada:

1. medir baseline atual de RAM/CPU/disco;
2. reservar portas;
3. criar Docker network própria;
4. subir somente API;
5. medir;
6. adicionar worker;
7. medir;
8. habilitar processing real;
9. definir limites;
10. criar alerta de disco.

Antes de qualquer sessão real:

```text
free disk >= 15 GB
memory available >= margem definida
Temporal reachable
Supabase reachable
Anthropic or DeepSeek reachable
OCR provider reachable
```

Não exigir todos os providers simultaneamente se fallback válido estiver disponível.

---

# 76. Resultado esperado deste documento

Este arquivo deve ser colocado na raiz do repositório como:

```text
IMPLEMENTATION_PLAN.md
```

e tratado como fonte de verdade arquitetural junto com:

```text
CLAUDE.md
```

O Claude Code deve implementar o projeto **fase por fase**, mantendo compatibilidade com as invariantes e registrando qualquer desvio arquitetural deliberado em `docs/decisions/ADR-xxxx.md`.

---

# 77. ADRs recomendados

Criar Architecture Decision Records para:

```text
ADR-0001 Supabase as application DB/storage
ADR-0002 Temporal as durable workflow engine
ADR-0003 Capture Controller outside per-probe Temporal activities
ADR-0004 Claude primary and DeepSeek fallback
ADR-0005 Gate 1 and Gate 2 fail-closed
ADR-0006 Provider abstractions
ADR-0007 No permanent local image storage
ADR-0008 React static admin
ADR-0009 Single-admin authentication
ADR-0010 Resource-aware shared VPS deployment
```

---

# 78. Checklist para iniciar Fase 0

Antes de chamar Claude Code:

- [ ] criar repositório Git;
- [ ] colocar este `IMPLEMENTATION_PLAN.md`;
- [ ] criar `CLAUDE.md`;
- [ ] definir Python 3.12+;
- [ ] instalar Docker local;
- [ ] criar projeto Supabase de desenvolvimento;
- [ ] decidir endpoint Temporal de desenvolvimento;
- [ ] não adicionar chaves reais ao Git;
- [ ] configurar `.env.example`;
- [ ] criar branch `develop`;
- [ ] iniciar FASE 0.

---

# 79. Checklist antes de usar APIs reais

- [ ] Anthropic key funcionando;
- [ ] DeepSeek key funcionando;
- [ ] Google Document AI configurado;
- [ ] Azure fallback configurado se adotado;
- [ ] Supabase buckets privados;
- [ ] Temporal;
- [ ] rate/cost limits;
- [ ] Sentry;
- [ ] logs sem secrets;
- [ ] dataset de teste não sensível.

---

# 80. Resumo executivo final

A arquitetura do servidor será deliberadamente dividida em duas áreas:

## Tempo real de captura

Leve, rápido e tolerante a 4G:

```text
ESP32 → Android → Capture Controller/API → Supabase
```

O Android recebe uma política temporária do servidor e consegue manter a sessão viva durante pequenas oscilações.

## Processamento pesado após LOCK

Durável e auditável:

```text
Temporal
→ imagem
→ OCR
→ reconstrução
→ Gate 1
→ RAG
→ Claude Opus 5
→ Verifier
→ Arbiter
→ DeepSeek V4 Pro quando houver fallback técnico
→ Gate 2
→ TTS
→ FFmpeg
→ áudio
```

Na VPS atual, a aplicação será mantida pequena:

```text
FastAPI + worker + painel estático
```

e os componentes pesados serão externos ou remotos sempre que isso preservar CPU, RAM e disco.

A ordem de desenvolvimento é:

```text
fundação
→ dados
→ ingestão
→ captura
→ workflow
→ OCR
→ reconstrução
→ Gate 1
→ RAG
→ IA
→ Gate 2
→ áudio
→ painel
→ hardening
→ deploy
```

A regra central permanece:

> qualidade máxima, zero falha silenciosa, nenhuma resposta inventada por falha técnica e nenhuma execução abaixo do piso de 90% chegando ao áudio de gabarito.
