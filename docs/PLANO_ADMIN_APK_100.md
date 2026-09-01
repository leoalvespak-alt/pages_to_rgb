# Plano de execução — Admin + API + Banco + APK 100% no PTR

**Versão:** 2.0 — 01/09/2026  
**Destino:** `https://ptr.rotadeataque.com.br`  
**Repositório:** `leoalvespak-alt/pages_to_rgb`  
**Branch de entrega:** `main`

**Objetivo:** entregar uma solução operacional completa, segura e auditada, composta por admin web, API administrativa, persistência PostgreSQL, configurações realmente aplicadas ao pipeline RGB, APK Android com preview/histórico/offline, testes, imagens Docker, deploy e rollback.

> Este documento é um roteiro de execução. A IDE/IA deve implementar, testar, auditar, corrigir e validar cada fase antes de avançar. Arquivo criado não significa etapa pronta: só marcar uma tarefa como concluída quando o critério de aceite estiver comprovado.

---

## 1. Resultado final obrigatório

1. `https://ptr.rotadeataque.com.br/admin`
   - login por senha operacional e sessão segura de 30 dias;
   - lista/detalhe de processos, fotos R2, RGB, SHA, logs e horários completos;
   - configurações de prova, paletas, tempos, brilho, modelos e chaves;
   - teste de providers sem vazar segredos.
2. `https://ptr.rotadeataque.com.br/api/v1/*`
   - gateway/manuscrito preservados;
   - rotas admin autenticadas;
   - settings persistidas e usadas no início da sessão e publicação RGB;
   - auditoria de todas as escritas administrativas.
3. PostgreSQL
   - migrações reversíveis;
   - settings singleton com constraints e optimistic locking;
   - chaves cifradas, nunca retornadas em texto puro.
4. APK
   - Prova Real e Teste Manuscrito;
   - spool offline, preview final, histórico e settings seguros;
   - APK debug instalável e release assinável.
5. Operação
   - Docker API/admin, Caddy, health checks, CI, push, deploy, smoke e rollback.

---

## 2. Estado inicial confirmado em 01/09/2026

### 2.1 Concluído e commitado — não refazer

- `main` e `origin/main` em `3abdecb`; base no commit `3b04b3d`.
- API Android-only, R2, `HANDWRITTEN_WORD`, spool e 10 cores.
- Migrações `0001`–`0005`.
- Rotas isoladas `/gateway/*` e `/handwritten/*`, ambas com summary.
- `DEFAULT_PALETTE`, `HANDWRITTEN_PALETTE` e seleção pelo `session_type`.
- APK com seletor, spool Room, upload por tipo, pendências, `NetworkCallback` e Retrofit/DTO do summary manuscrito.
- Baseline: `376 passed`.

### 2.2 Rascunho local a aproveitar e corrigir

Há frontend não rastreado em `apps/admin`. É referência visual, não entrega funcional. Antes de aproveitar:

- corrigir dependências Tailwind/PostCSS e gerar lockfile;
- criar layout/nav e redirect `/admin`;
- remover token de `localStorage` e cookie escrito por JavaScript;
- tratar loading, erro, vazio, 401, 409 e retry;
- alinhar contratos ao backend e executar build de produção;
- validar responsividade, acessibilidade, Console e Network.

### 2.3 Lacunas comprovadas

- routers admin, modelo/migração settings e integração no domínio não existem;
- Dockerfile/serviço admin e rota Caddy `/admin*` não existem;
- APK não mostra preview/histórico; URL default ainda é de exemplo;
- Android usa `minSdk 26`, enquanto o plano antigo dizia 24;
- wrapper Gradle contém placeholder e não há APK;
- plano/admin local ainda não estão no Git.

---

## 3. Regras para a IDE/IA

### 3.1 Ordem obrigatória

1. baseline e proteção do working tree;
2. contratos/ADRs;
3. banco;
4. auth;
5. settings API;
6. settings no domínio;
7. processos API;
8. frontend;
9. APK;
10. testes/auditorias;
11. Docker/CI;
12. commit/push;
13. deploy/smoke/rollback.

### 3.2 Regras de qualidade e segurança

- Next.js nunca acessa DB; tudo passa pelo FastAPI.
- Não duplicar domínio em routers.
- Não alterar status via SQL direto; usar máquina de estados/serviços.
- Toda escrita admin gera `AuditEvent` sem segredos.
- Nunca logar senha, cookie, token ou chave.
- Placeholder mascarado/vazio não pode apagar chave existente.
- Toda migração tem `upgrade`, `downgrade` e teste.
- Toda rota nova tem schemas, auth, erros estáveis e testes.
- Correção web exige reteste real UI → request → endpoint → banco.
- Não fazer deploy com arquivos soltos ou CI vermelho.

### 3.3 Definition of Done global

Só declarar 100% quando:

- todos os itens MUST estiverem concluídos;
- backend mantiver os 376 testes e passar os novos;
- frontend passar install, lint, typecheck, testes e `next build`;
- Android passar unit tests e `assembleDebug`;
- migração subir/descer/subir em banco descartável;
- Compose/Caddy validarem e serviços ficarem healthy;
- browser real e APK real completarem o fluxo;
- nenhum segredo estiver em response, log, bundle, APK ou Git;
- `origin/main` e produção executarem o SHA aprovado.

---

## 4. Fase 0 — Baseline e proteção

### Passos

- Registrar `git status`, diffs, log, branch, remote e SHA inicial.
- Inventariar untracked sem apagar alterações do usuário.
- Varrer segredos acidentalmente rastreados.
- Executar Python lint/typecheck/test conforme CI, `pytest -q`, Compose config e `caddy adapt`.
- Verificar Node, Java/Android, Alembic heads/current/history e health local.
- Criar `docs/progress/ADMIN_APK_BASELINE.md` com versões, comandos, SHA e falhas preexistentes.

### Aceite

- Baseline reproduzível documentado; nenhuma regressão introduzida.

---

## 5. Fase 1 — Contratos, segurança e UX

### 5.1 Congelar contratos

Criar `apps/api/schemas/admin.py` com:

- `AdminLoginRequest`, `AdminSessionResponse`, `AdminMeResponse`;
- `AdminSettingsRead/Update`, `ProviderTestRequest/Response`;
- `AdminSessionListItem/Response`, `AdminSessionDetail`;
- `SignedFrameUrlResponse`, `AdminActionResponse`;
- erro padrão `{code, message, details?, request_id?}`.

Definir campos, limites, enums, paginação, nullability, UTC ISO 8601, status técnico/rótulo e máscara de secrets. Não devolver ORM diretamente.

### 5.2 Auth correta

Usar `ADMIN_PASSWORD_HASH` Argon2, `SESSION_SECRET` e `CSRF_SECRET` já existentes:

- cookie `admin_session`, `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, TTL 30d;
- cookie host-only; não usar domínio amplo sem necessidade;
- CSRF em todo método mutável;
- autorização final sempre no FastAPI.

Proibido: senha plain, token em `localStorage`, cookie via `document.cookie` ou middleware Next como única segurança.

### 5.3 Secrets de providers

**MUST:** cifrar no backend com AES-GCM/Fernet e `ADMIN_SETTINGS_ENCRYPTION_KEY` em secret/env. Banco guarda ciphertext/version/nonce, nunca a chave mestra. Documentar rotação. Alternativa somente se usar referências a secret manager externo.

### 5.4 UX

- `/admin/login`, `/admin/processos`, `/admin/processos/[id]`, `/admin/config`;
- header, nav `Processos | Configurações | Sair`;
- dark `#0A0A0A`, cards `#1A1A1A`, bordas `#2A2A2A`, primário `#C62828`.

### Aceite

- Contratos revisados e ADR em `docs/decisions/`; nenhum formato implícito.

---

## 6. Fase 2 — Banco e settings

### 6.1 Modelo singleton

Criar `src/pages_to_audio/db/models/admin_settings.py` e importar no registry:

```text
id UUID PK
singleton_key SMALLINT NOT NULL DEFAULT 1 UNIQUE CHECK(singleton_key = 1)
ocr_provider, solve_model, verify_model, arbiter_model TEXT NOT NULL
*_api_key_encrypted TEXT NULL
secrets_version INTEGER NOT NULL DEFAULT 1
expected_pages INTEGER NOT NULL DEFAULT 70
expected_questions INTEGER NOT NULL DEFAULT 70
handwritten_expected_questions INTEGER NOT NULL DEFAULT 10
minimum_ratio NUMERIC(5,4) NOT NULL DEFAULT 0.9000
brightness_percent INTEGER NOT NULL DEFAULT 12
on_ms INTEGER NOT NULL DEFAULT 3000
off_ms INTEGER NOT NULL DEFAULT 5000
palette, handwritten_palette JSONB NOT NULL
created_at, updated_at TIMESTAMPTZ NOT NULL
version INTEGER NOT NULL DEFAULT 1
```

Confirmar com produto os números EXAM 70/70; não perpetuar 10/10 por engano. Manter manuscrito independente em 10.

### 6.2 Migração `0006_admin_settings.py`

- `down_revision` correto, tabela/constraints/defaults e seed singleton idempotente;
- paletas atuais como defaults;
- sem copiar secrets do env;
- downgrade remove apenas objetos da `0006`.

### 6.3 Serviço

Criar `src/pages_to_audio/admin/settings_service.py`:

- `get_effective_admin_settings`;
- `update_admin_settings(..., expected_version)`;
- encrypt/decrypt/mask;
- validação providers/modelos, RGB 0–255, A–E completas, brilho, tempos e quantidades;
- PUT parcial preserva chave ausente/mascarada;
- limpeza exige flag explícita `clear_*`;
- update incrementa version atomicamente; conflito = 409.

### 6.4 Testes

- singleton/defaults, upgrade/downgrade/upgrade, constraints;
- optimistic locking;
- crypto round-trip e ciphertext adulterado;
- ausência de chave em repr/log/schema.

### Aceite

- Um Alembic head; migração reversível; secrets cifrados e responses mascaradas.

---

## 7. Fase 3 — Auth admin

Criar `apps/api/routers/admin_auth.py`, prefix `/admin`:

- `POST /login`: verifica Argon2, assina `iat/exp/jti/version`, seta cookie e retorna apenas estado/expiração;
- `GET /me`: valida sessão;
- `POST /logout`: apaga/invalida sessão;
- `GET /csrf`: token quando necessário.

Criar `require_admin_session`, `require_admin_csrf` e rate limit de login.

### Proteções MUST

- erro genérico, backoff/rate limit por IP;
- `Cache-Control: no-store`;
- CORS restrito e mesma origem normal;
- produção falha fechada se hashes/secrets obrigatórios faltarem;
- redaction de headers/cookies/keys;
- rotação de session secret documentada.

### Testes

- 401/200, senha errada, cookie expirado/adulterado, logout;
- CSRF ausente/incorreto/correto, rate limit e atributos do cookie;
- nenhuma credencial em body/log.

### Aceite

- Login real funciona sem storage acessível a JS; reload preserva sessão; escritas exigem CSRF.

---

## 8. Fase 4 — Settings API e providers

Criar `apps/api/routers/admin_settings.py` e registrar em `main.py`:

- `GET /api/v1/admin/settings`;
- `PUT /api/v1/admin/settings`;
- `POST /api/v1/admin/settings/test`.

### Regras

- GET retorna settings, máscara e flags `*_configured`;
- PUT exige version, readback e AuditEvent sem valores secrets;
- provider test reutiliza clients existentes, prompt mínimo, timeout 5–10s e rate limit;
- resposta `{ok, provider, model, latency_ms, error_code?, message?}`;
- normalizar 401/403/429/timeout/DNS/5xx sem devolver body bruto.

### Testes

- GET mascarado, PUT/readback, preservar/limpar chave, conflito 409;
- paletas/tempos inválidos;
- mocks provider success/401/429/timeout/500;
- auditoria sem secret.

### Aceite

- Settings sobrevivem ao restart e teste de provider mostra latência/erro sem vazamento.

---

## 9. Fase 5 — Aplicar settings ao sistema real

Tela que apenas salva não atende.

### 9.1 Snapshot por sessão

- No start, ler settings efetivas e gravar snapshot/version usados.
- EXAM usa quantidades/paleta EXAM; manuscrito usa `handwritten_expected_questions`/paleta manuscrita.
- Publisher e summary usam snapshot da sessão, para mudança global não alterar sessão em curso.
- Se necessário, criar `0007_session_settings_snapshot.py`, reversível e testada.

### 9.2 Integrações obrigatórias

Atualizar:

- `/gateway/session/start` e `/handwritten/session/start`;
- policies do gateway;
- seleção OCR/Solve/Verify/Arbiter;
- `rgb/publisher.py` e brightness/on/off;
- summaries EXAM/manuscrito.

### 9.3 Cache/fallback

- cache curto da última config válida, invalidado após PUT;
- não iniciar sessão com config inválida;
- fallback para constantes somente com política explícita e métrica/log;
- logar `settings_version`, jamais secret.

### 9.4 Testes

- config nova afeta só sessão nova;
- sessão antiga conserva snapshot;
- quantidade manuscrita, brilho/on/off e paleta chegam ao payload;
- summary RGB é idêntico ao publicado.

### Aceite

- Admin altera sessões novas sem código/restart; sessões em curso permanecem determinísticas.

---

## 10. Fase 6 — Processos API

Criar `apps/api/routers/admin_sessions.py`.

### 10.1 Lista `GET /admin/sessions`

Parâmetros: page, limit 1–100, type, status real de `SessionState`, q, data inicial/final e sort allowlist. Resposta: items/page/limit/total/pages, public_id, tipo/status/datas, frames count, expected questions, device/gateway, cursor/delivery quando houver.

- evitar N+1;
- count correto e queries parametrizadas;
- índices para filtros;
- validar `EXPLAIN ANALYZE` com volume representativo.

### 10.2 Detalhe `GET /admin/sessions/{public_id}`

Retornar sessão/snapshot, captures, frames, questions/final answers, RGB/revision/SHA, deliveries e AuditEvents ordenados; nunca secrets.

### 10.3 Foto `GET /admin/sessions/{id}/frames/{frame_id}/url`

- confirmar ownership frame→session e bucket/key esperados;
- signed URL TTL 300s e `no-store`;
- nunca aceitar storage key arbitrária do cliente;
- não gravar URL assinada em log/audit.

### 10.4 Cancel `POST /admin/sessions/{id}/cancel`

- motivo obrigatório;
- usar máquina de estados;
- idempotente se já cancelada, 409 em terminal incompatível;
- criar delivery/comando conforme contrato e AuditEvent.

### 10.5 Retry `POST /admin/sessions/{id}/retry`

- `{from_stage?, reason}`;
- somente estados seguros e workflow/service existente;
- idempotency key e proteção de concorrência;
- `202` + operation/workflow id se assíncrono;
- AuditEvent.

### 10.6 Testes e aceite

- auth/CSRF, filtros/paginação/404, query count, IDOR da foto;
- cancel por grupos de estado, retry idempotente/concorrente;
- lista <1s e signed URL <500ms no ambiente-alvo.

---

## 11. Fase 7 — Frontend Admin

### 11.1 Projeto/build

- Corrigir Tailwind/PostCSS ou removê-los; declarar tudo explicitamente.
- Gerar/versionar lockfile; scripts install/lint/typecheck/test/build.
- `output: standalone`, `.env.example`, API server-side parametrizada.
- Evitar rewrite hardcoded que quebre dev.

Estrutura:

```text
app/(auth)/admin/login/page.tsx
app/(admin)/admin/layout.tsx
app/(admin)/admin/page.tsx
app/(admin)/admin/processos/page.tsx
app/(admin)/admin/processos/[id]/page.tsx
app/(admin)/admin/config/page.tsx
components/  lib/api.ts  lib/contracts.ts  lib/date.ts
```

`/admin` redireciona para processos.

### 11.2 Client API/auth

- fetch same-origin com `credentials: include`, CSRF automático e timeout;
- erro padrão e 401 → login com `next` interno seguro;
- nenhum Bearer/localStorage;
- confirmar sessão em `/admin/me`; implementar logout.

### 11.3 Processos

- filtros tipo/status/data, busca, paginação/total e URL refletindo estado;
- loading/empty/error/retry;
- tabela desktop e cards mobile;
- ID copiável, badges, datas `DD/MM/YYYY HH:mm:ss` em São Paulo.

### 11.4 Detalhe

- resumo ID/tipo/status/datas/fotos/RGB/revision/SHA/settings version;
- Cancelar/Reprocessar com confirmação e motivo;
- Fotos: modal acessível, refresh da URL expirada, metadados/SHA;
- RGB: Q/nome/resposta/RGB/brilho/on/off, preview com reduced motion, JSON/SHA;
- Registros: timestamp/stage/reason/actor, JSON expansível/filtro.

### 11.5 Config

- OCR/Solve/Verify/Arbiter e quatro secrets com `Configurada`/remover;
- provider test inline, sem `alert()`;
- páginas/questões EXAM, quantidade manuscrita, ratio, brilho, on/off;
- duas paletas A–E com color picker + RGB numérico;
- preview de 10 itens/on-off;
- aviso “somente novas sessões”; version/409.

### 11.6 Qualidade

- TypeScript sem `any` no domínio;
- a11y, foco, teclado, contraste, modal/escape;
- Playwright: login/logout, filtros, detalhe/foto, settings, 401/409;
- screenshots 375×812, 768×1024 e 1440×900;
- inspecionar Console/Network.

### Aceite

- install/lint/typecheck/test/build verdes; zero erro no fluxo; mobile/teclado funcionais; zero secret/token no browser.

---

## 12. Fase 8 — APK completo

### 12.1 Build/config

- URL default `https://ptr.rotadeataque.com.br/api/v1/`, com override local.
- Decidir `minSdk` 26 ou implementar/testar 24; alinhar código/README.
- Restaurar wrapper Gradle real e verificar checksum.
- Release signing via secrets; nunca versionar token/keystore.

### 12.2 Preview

O Retrofit/DTO manuscrito já existe. Completar:

- repository summary manuscrito e equivalente EXAM;
- `PreviewColor`, `previewColors`, loading/error no UiState;
- após end, poll limitado até RGB pronto, sem travar;
- retry manual;
- usar RGB retornado pela API, nunca paleta hardcoded no APK.

### 12.3 Histórico Room

Criar `SessionHistoryEntity`/DAO com id, type, timestamps, frames, status, preview mínimo, pendências e último sync/error.

- migration Room explícita; remover destructive migration de produção;
- histórico persiste após reinício;
- lista + detalhe e refresh online;
- offline mostra snapshot conhecido.

### 12.4 Offline/settings/UX

- badge online/offline, fila total/por sessão e retry;
- WorkManager com rede/backoff/idempotência; testar morte/reboot;
- tela base URL/token; HTTPS fora de debug;
- token no Android Keystore/EncryptedSharedPreferences;
- testar conexão e confirmar troca durante sessão ativa;
- seletor desabilitado na sessão; rotação não perde estado; TalkBack/contraste/touch targets.

### 12.5 Testes/aceite

- repository/ViewModel summary, Room migrations, history, WorkManager e token storage;
- Compose UI, unit tests e `assembleDebug`;
- `adb install -r`;
- cortar rede no frame 1/3, religá-la e confirmar fila 0 sem duplicação;
- 10 fotos → preview 10 cores; histórico sobrevive ao restart; zero segredo em logcat/APK.

---

## 13. Fase 9 — Docker, Caddy e observabilidade

### 13.1 Admin image

Criar `infra/docker/Dockerfile.admin` multi-stage:

- Node LTS, `npm ci`, standalone;
- runtime mínimo non-root, `NODE_ENV=production`, healthcheck;
- copiar somente standalone/static/public;
- imagem tagueada por SHA, não apenas latest.

### 13.2 Compose

Adicionar `admin` em `docker-compose.pages-rgb.prod.yml`:

- imagem GHCR `${IMAGE_TAG}`;
- `API_URL=http://pages-rgb-app:8000` server-side;
- expose 3000 sem porta pública;
- rede compartilhada, healthcheck e depends_on healthy;
- log rotation/restart; read-only/tmpfs quando possível.

### 13.3 Caddy

Dentro de `@ptr`, rotear em ordem:

```caddy
handle /admin* { reverse_proxy admin:3000 }
handle /api/* { reverse_proxy pages-rgb-app:8000 }
handle /docs* { reverse_proxy pages-rgb-app:8000 }
handle /openapi.json { reverse_proxy pages-rgb-app:8000 }
handle { reverse_proxy pages-rgb-app:8000 }
```

**MUST:** resolver assets Next. Preferir `basePath: "/admin"` e confirmar `/admin/_next/*`; jamais mandar assets do admin para API. Executar `caddy adapt --pretty`.

### 13.4 Segurança/observabilidade

- proxy headers corretos; CSP compatível com Next/R2;
- HSTS no ponto TLS; no-store em páginas sensíveis;
- logs estruturados/request id e redaction;
- métricas login/provider/list/signed-url/retry;
- health admin/API, loop restart, migration failure e SHA em execução.

### Aceite

- Compose healthy; `/admin`, assets, `/api` e `/docs` no serviço correto; API existente preservada; logs limpos.

---

## 14. Fase 10 — Testes, auditorias e debug

### 14.1 Novos testes mínimos

```text
tests/unit/admin/test_auth.py
tests/unit/admin/test_settings.py
tests/unit/admin/test_settings_crypto.py
tests/unit/admin/test_sessions.py
tests/integration/db/test_admin_settings_migration.py
tests/integration/api/test_admin_flow.py
tests/integration/rgb/test_settings_snapshot.py
```

Criar `scripts/simulate_admin.py`: login/cookies/CSRF, me, settings readback, provider seguro, list/detail/url, cancel/retry descartável e logout. Estender `simulate_handwritten.py` para verificar settings/RGB.

### 14.2 E2E browser

1. `/admin` sem sessão → login;
2. senha inválida e correta;
3. filtros/detalhe/foto;
4. HH:mm:ss, RGB e SHA;
5. editar paleta;
6. nova sessão manuscrita usa nova paleta;
7. logout protege rotas.

Ao falhar, correlacionar UI → Network → endpoint → SQL/log e retestar após correção.

### 14.3 Auditorias

**Segurança:** secrets no Git/bundle/APK, cookie/CSRF, IDOR frame/session, injection, XSS em logs, brute force, signed URL TTL, deps/images, CORS/CSP/cache e non-root.

**Desempenho:** lista/detalhe com volume, signed URL, bundle, N+1/query count, memória e polling APK.

**Visual/a11y:** desktop/tablet/mobile, WCAG AA, foco/teclado, labels/erros, modal focus trap/Escape, reduced motion.

### Aceite

- Criar `docs/progress/ADMIN_APK_FINAL_AUDIT.md` com comandos/evidências/screenshots. Findings MUST devem ser corrigidos e retestados, não apenas anotados.

---

## 15. Fase 11 — CI, builds e artefatos

Atualizar CI com jobs:

- backend lint/typecheck/tests;
- Alembic em PostgreSQL de serviço;
- admin `npm ci`/lint/typecheck/test/build;
- Android unit tests/assembleDebug;
- Docker build API/admin;
- scans secrets/deps/images;
- upload de APK autorizado.

Publicar imagens por SHA/digest, gerar SBOM quando possível e registrar digest. Gerar debug APK, release signing via CI secret e SHA-256 do APK.

### Aceite

- CI verde; API/admin/APK correspondem ao mesmo SHA; checksums registrados.

---

## 16. Fase 12 — Git, push, deploy e rollback

### 16.1 Antes do commit

- revisar status/untracked, diff e `git diff --check`;
- não adicionar env, secret, keystore, node_modules, `.next`, APK ou log;
- suíte completa, migrações, lockfiles e docs revisados.

Commits sugeridos:

1. `feat(admin-db): persist secure global settings`
2. `feat(admin-api): add auth settings and session management`
3. `feat(admin-web): complete responsive admin interface`
4. `feat(android): add color preview history and secure settings`
5. `build(deploy): add admin image routing and release checks`

Push após validação; aguardar CI remoto e registrar SHA aprovado.

### 16.2 Pré-deploy

- backup/snapshot DB;
- registrar digests atuais;
- validar espaço, secrets, R2/Postgres/GHCR;
- `docker compose config` sem expor secrets;
- responsável/janela de rollback definidos.

### 16.3 Deploy ordenado

1. pull por SHA/digest;
2. migração one-shot (nunca concorrente);
3. verificar head;
4. atualizar API e health;
5. subir admin e health;
6. validar/recarregar Caddy sem downtime;
7. smoke interno com Host header;
8. smoke público HTTPS.

### 16.4 Smoke público MUST

- live/ready 200;
- docs/openapi preservados;
- `/admin` entrega login, não health;
- assets Next 200;
- login → processos;
- settings GET/PUT/readback;
- list/detail/photo;
- manuscrito 10 fotos → summary/RGB;
- outro domínio/app não sofre regressão.

### 16.5 Rollback

Criar `docs/runbooks/admin_apk_rollback.md`:

- voltar Caddy/Compose/digests;
- compatibilidade schema/API;
- quando evitar downgrade;
- restaurar backup;
- revogar sessões/rotacionar secret;
- desabilitar admin sem derrubar gateway;
- smoke pós-rollback.

Preferir migração backward-compatible para rollback da app sem downgrade imediato.

### Aceite

- Produção no SHA aprovado, smoke verde, observação estável e rollback praticável.

---

## 17. Matriz de rastreabilidade

| Requisito | Backend | Banco | Web | APK | Teste |
|---|---|---|---|---|---|
| Login 30d | auth/cookie | — | login/logout | — | auth + Playwright |
| Settings | service/router | singleton | config | policy | snapshot integration |
| Secrets | crypto | ciphertext | máscara/clear | keystore | leak/crypto |
| Processos | sessions router | queries/indexes | lista/detalhe | history | API/E2E |
| Fotos | signed URL | ownership | modal | opcional | IDOR/TTL |
| RGB | publisher/summary | sequence/snapshot | preview | preview | igualdade canônica |
| Cancel/retry | state/workflow | audit/delivery | confirmação | — | idempotência |
| Offline | idempotência API | — | — | Room/WorkManager | corte de rede |
| Deploy | health | migrations | image | APK | smoke público |

---

## 18. Checklist final

### Backend/banco

- [ ] `0006` e eventual `0007` testadas.
- [ ] Singleton/version/crypto.
- [ ] Auth cookie + CSRF + rate limit.
- [ ] Settings GET/PUT/test e aplicação no domínio.
- [ ] List/detail/url/cancel/retry.
- [ ] AuditEvent em escritas.

### Frontend

- [ ] Dependências/lockfile/build.
- [ ] Login/layout/nav/logout.
- [ ] Lista responsiva/paginação.
- [ ] Detalhe fotos/RGB/logs.
- [ ] Config completa/preview/409.
- [ ] Estados de UI/browser/mobile/a11y auditados.

### APK

- [ ] URL PTR/settings seguros.
- [ ] Summaries ligados ao ViewModel.
- [ ] Preview 10 cores e histórico Room.
- [ ] Offline/fila comprovados.
- [ ] Wrapper/test/build/install.

### Operação

- [ ] Dockerfile/Compose/Caddy/health.
- [ ] CI completo verde.
- [ ] Auditoria sem findings MUST.
- [ ] Commit/push/deploy confirmados.
- [ ] Smoke público e rollback.

---

## 19. Evidências finais obrigatórias

A IDE/IA deve entregar, e não apenas responder “feito”:

1. SHA e CI;
2. principais arquivos alterados;
3. resultados backend/frontend/Android;
4. upgrade/downgrade Alembic;
5. digests e checksum APK;
6. health/smoke resumidos;
7. screenshots desktop/mobile;
8. evidência APK preview/history/fila offline zerada;
9. auditoria de segurança sem secrets;
10. SHA em produção e runbook de rollback.

Se qualquer MUST falhar, informar bloqueio, evidência, impacto e próximo passo; não classificar como 100%.
