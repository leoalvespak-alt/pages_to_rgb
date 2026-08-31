# Plano — Teste manuscrito alternativo (10 palavras → 10 cores) + R2 + Tunnel HTTPS + GitHub

**Versão:** 1.0 — 31/08/2026  
**Base:** `docs/PLANO_ANDROID_ONLY.md` (etapas 0–7 já auditadas) + `DEPLOY_VPS.md`/`INFRA-WSL2-ESTABILIDADE.md` do Rota-Migracao  
**Objetivo:** adicionar modo **separado e selecionável** de teste com folha manuscrita (`João/Maria/Pedro/Paula/Fernanda` → `Azul/Vermelho/Verde/Roxo/Amarelo`) sem quebrar o fluxo `EXAM` já consolidado, migrando storage para **R2**, com **push sempre para `main` em `https://github.com/leoalvespak-alt/pages_to_rgb.git`** e **deploy via GitHub Actions para WSL2 local com Cloudflare Tunnel HTTPS fixo** (mesma conta Cloudflare do Rota, mas **tunnel/domínio/compose separados**, sem interferir no Rota).

> **Alternância:** `EXAM` (prova real, 70 questões `A-E` paleta branca/amarelo/ciano/azul/vermelho) continua intocado. `HANDWRITTEN_WORD` (10 fotos, 1 palavra por foto, `A-E` + paleta palavra→cor) é **alternativo**, escolhido na UI antes de `Iniciar sessão`.

---

## 0. Decisões de alinhamento (respostas do usuário)

| Tema | Decisão |
|---|---|
| Storage | **Migrar para R2 já** (sai Supabase Storage) |
| Tunnel | **HTTPS fixo** `ptr.rotadeataque.com.br` (mesma zone `rotadeataque.com.br`, novo tunnel `pages-to-rgb-wsl2` ID diferente do Rota `17a16fd2...`). Sem custo, sem domínio novo. |
| Repo | **Novo** `pages_to_rgb.git` → push do estado atual de `C:\Users\Lenovo\Downloads\pagestoaudio_servidor` para `main` (sem branches alternativos) |
| Seletor | **Seletor + endpoint separado** (`/gateway/handwritten/*`), sem tocar `/gateway/session/start` do EXAM |
| IA | **Reusar pipeline** (GATE_1/2, Solve/Verify/Arbiter, mesmo `ProcessExamWorkflow`) — palavra = questão |
| Escopo RGB | **10 fotos → 10 itens** (10 "perguntas", cada uma `A-E` = 5 nomes). Próximo de prova real para testar fim-a-fim. |
| Paleta | **Mesma estrutura** `DEFAULT_PALETTE` + `defaults 12%/3000/5000` (`rgb/schemas.py:108`, `canonical.py:68` `<BBBBBII`) |
| Deploy | **Reusar padrão Rota**: `.github/workflows/deploy-local-producao.yml` → GHCR → `scripts/deploy-producao-local.sh` no WSL2, mas **compose/Caddy/tunnel/credenciais isolados** do Rota. |

---

## 1. Infra WSL2 isolada (não interferir no Rota)

**Por que isolar:** Rota já roda em WSL2 Ubuntu 26.04 com Postgres 18 nativo + PgBouncer 6432 + `rota-app` (GHCR) + `rota-caddy` (Caddy :80) + `cloudflared-rota.service` tunnel `rota-ataque-wsl2-producao` → `app.rotadeataque.com.br`. O pages-to-rgb **não pode** compartilhar `docker-compose.prod.yml`, `IMAGE_NAME`, `LOCKFILE` ou porta do Rota.

**Passos (a IA executora cria e preenche `DATABASE_URL` e `APP_PORT` no `.env.pages-rgb`):**

1.1 Criar DB separado (a IA lê `CREDENCIAIS_ROTA.txt` só para referência, mas cria DB local):

```bash
# no WSL2, como postgres
sudo -u postgres psql -c "CREATE DATABASE pages_to_rgb;"
sudo -u postgres psql -c "CREATE USER pages_to_rgb WITH PASSWORD '$(openssl rand -hex 16)';"
sudo -u postgres psql -c "GRANT ALL ON DATABASE pages_to_rgb TO pages_to_rgb;"
# URL resultante: postgresql+asyncpg://pages_to_rgb:<senha>@172.29.52.81:5432/pages_to_rgb
# a IA grava em C:\Users\Lenovo\Desktop\pages-to-rgb-env.txt e .env.pages-rgb
```

Ou via `host.docker.internal:6432` (PgBouncer) — ambas valem; registrar `search_path` se usar PgBouncer.

1.2 Criar diretório separado no WSL2 (ex: `/srv/pages-to-rgb`):

```bash
sudo mkdir -p /srv/pages-to-rgb/config /srv/pages-to-rgb/caddy_data /srv/pages-to-rgb/caddy_config
sudo chown $USER:$USER /srv/pages-to-rgb
```

1.3 Duplicar e renomear compose/Caddyfile/Dockerfile:

- `docker-compose.pages-rgb.prod.yml` (serviços `pages-rgb-app` + `pages-rgb-caddy`, `extra_hosts: host.docker.internal:host-gateway`, volumes `pages_rgb_*`, rede `pages_rgb_net`, `APP_PORT=8080` para FastAPI)
- `Caddyfile.pages-rgb` (site `https://ptr.rotadeataque.com.br` → `pages-rgb-app:8000`, `request_body max_size 20MB`, `flush_interval -1`)
- `Dockerfile.production` pode ser o mesmo, só troca `IMAGE_NAME` para `ghcr.io/leoalvespak-alt/pages_to_rgb`

1.4 Porta Caddy isolada: `pages-rgb-caddy` em `8080:80` e tunnel ingress `→ http://localhost:8080`. Systemd + KeepAlive já ok (`INFRA-WSL2-ESTABILIDADE.md:96` âncora `sleep infinity` + `vmIdleTimeout=86400000`) — mesma âncora já segura a distro.

## 2. Cloudflare Tunnel HTTPS fixo — `ptr.rotadeataque.com.br` (mesma conta Rota)

**Atual Rota:** `cloudflared` `rota-ataque-wsl2-producao` `17a16fd2-ab67-4189-9c53-68d26cf43024` → `app.rotadeataque.com.br` CNAME `cfargotunnel.com`.

**Para ptr (pages-to-rgb): a IA executora cria novo tunnel e DNS usando credenciais de `CREDENCIAIS_ROTA.txt` (conta `3dd8e77a...`, Token DNS `cfat_Rdre...`, R2 `7e3232...`), mas sem tocar no tunnel do Rota:**

2.1 Mesmo `CLOUDFLARE_API_TOKEN` e `Account ID` de `CREDENCIAIS_ROTA.txt:32`, **novo tunnel** (não reusar ID do Rota):

```bash
# a IA faz (usa token da conta Rota, mas CNAME separado):
cloudflared tunnel create pages-to-rgb-wsl2
# gera ID e cred file /etc/cloudflared/pages-rgb-*.json → grava TUNNEL_ID/TUNNEL_TOKEN no .env.pages-rgb
cloudflared tunnel route dns pages-to-rgb-wsl2 ptr.rotadeataque.com.br
# cria CNAME ptr.rotadeataque.com.br → <ID>.cfargotunnel.com proxied:true
```

2.2 Domínio é `ptr.rotadeataque.com.br` (subdomínio do Rota, sem custo, isolado por `CNAME` diferente de `app.` e `admin.`). Não criar `trycloudflare` nem `us.kg`.

2.3 Serviço separado:

```bash
sudo tee /etc/systemd/system/cloudflared-pages-rgb.service
# ExecStart=/usr/bin/cloudflared tunnel --config /etc/cloudflared/pages-rgb.yml run
sudo systemctl enable --now cloudflared-pages-rgb
```

Ingress `pages-rgb.yml`:

```yaml
tunnel: <TUNNEL_ID pages-to-rgb-wsl2>
credentials-file: /etc/cloudflared/<ID>.json
ingress:
  - hostname: ptr.rotadeataque.com.br
    service: http://localhost:8080
  - service: http_status:404
```

2.4 Testar: `curl -I https://ptr.rotadeataque.com.br/api/v1/health/live` → 200 (via tunnel → pages-rgb-caddy:8080 → pages-rgb-app:8001).

## 3. Storage — R2 (mesma conta Rota, buckets `pages-to-rgb-*`, auto-limpeza 90 dias)

**Hoje:** `SupabaseStorageAdapter` (`src/pages_to_audio/storage/supabase_storage.py:19`, buckets `pages-originals/...`, `StoredObject`).  
**Executora usa credenciais de `CREDENCIAIS_ROTA.txt:32` (Account/Access/Secret/Token DNS) — sem pedir novo token.**

3.1 A IA cria 4 buckets (se não existirem) na mesma conta `rota-arquivos`:

- `pages-to-rgb-originals`, `pages-to-rgb-derived`, `pages-to-rgb-ocr`, `pages-to-rgb-audio` — seguir §12.2 keys `sessions/{id}/frames/...` sem mudar convenção.
- Usa mesma `Account ID` e endpoint do Rota (de `CREDENCIAIS_ROTA.txt`).
- Após criar, grava `R2_*` no `.env.pages-rgb` e replica no `.env.pages-rgb` do WSL2 `/srv/pages-to-rgb/config/.env`.

3.2 Lifecycle 90 dias (mesma conta, bucket separado, sem afetar `rota-arquivos`): cada bucket → `Settings → Lifecycle → Delete after 90 days` (ou API `PutBucketLifecycle`):

```json
{"Rules":[{"ID":"ptr-90d","Status":"Enabled","Filter":{},"Expiration":{"Days":90}}]}
```

Fotos/provas processadas/respostas do PTR são deletadas automaticamente — EXAM do Rota não é tocado (outro bucket).

3.3 Novo adapter `src/pages_to_audio/storage/r2_storage.py` (copia interface `StoragePort` `StoredObject`, usa `boto3` S3 compatível):

```python
class R2StorageAdapter:
    async def put_object(bucket, key, data, content_type, *, sha256, overwrite=False) ...
    async def object_exists ...
    async def get_object ...
    async def create_signed_url ...  # SigV4 ttl 300s
    async def delete_object ...
```

Config via `src/pages_to_audio/config/settings.py` (a IA adiciona e preenche com `CREDENCIAIS_ROTA.txt`):

```env
STORAGE_PROVIDER=r2            # supabase | r2 (ptr usa r2)
R2_ACCOUNT_ID=__AUTO__  # de CREDENCIAIS_ROTA.txt:32
R2_ACCESS_KEY_ID=__AUTO__
R2_SECRET_ACCESS_KEY=__AUTO__
R2_ENDPOINT=https://__R2_ACCOUNT_ID__.r2.cloudflarestorage.com
R2_BUCKET_ORIGINALS=pages-to-rgb-originals
R2_BUCKET_DERIVED=pages-to-rgb-derived
R2_BUCKET_OCR_RAW=pages-to-rgb-ocr
R2_BUCKET_AUDIO=pages-to-rgb-audio
```

Factory `storage/__init__.py: get_storage_adapter()` lê `STORAGE_PROVIDER`. `supabase_storage.py` fica deprecado, não removido (`CLAUDE.md:4`).

3.4 Reuso de APIs do Rota: `DEEPSEEK_TOKEN`, `PADDLE_OCR`, `RESEND` etc podem ser copiados para `.env.pages-rgb` sem criar novas chaves — a IA copia de `CREDENCIAIS_ROTA.txt` e do `.env` do Rota.

## 4. GitHub — push para `pages_to_rgb` + Actions deploy isolado

**Repo alvo:** `https://github.com/leoalvespak-alt/pages_to_rgb.git` (privado, `main` único, sem branches alternativos).

4.1 Inicializar repo local (a partir de `C:\Users\Lenovo\Downloads\pagestoaudio_servidor`):

```powershell
cd C:\Users\Lenovo\Downloads\pagestoaudio_servidor
git remote remove origin 2>$null
git remote add origin https://github.com/leoalvespak-alt/pages_to_rgb.git
git branch -M main
git add .
git commit -m "pages-to-rgb: base Android-Only (etapas 0-7) + R2 baseline"
git push -u origin main
```

4.2 Adaptar workflow do Rota sem copiar identidade:

Criar `.github/workflows/deploy-pages-rgb-local.yml` (copiar estrutura de `Rota de Ataque/.../.github/workflows/deploy-local-producao.yml:1` mas com):

```yaml
env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}  # → ghcr.io/leoalvespak-alt/pages_to_rgb
# job build-and-push:
#   Dockerfile.production, platforms linux/amd64, push true, tags :sha7 + :latest
#   cache-from/to: type=gha,mode=min
#   NODE_OPTIONS=--max-old-space-size=6144 (se for Next, senão PYTHON)
```

Para Python/FastAPI a imagem é **pequena** (não precisa swap 8GB nem `.next/cache`); simplificar: `setup-python 3.12`, `uv sync`, `docker/build-push-action` com `Dockerfile.pages-rgb` (multi-stage `python:3.12-slim`).

4.3 Script de deploy isolado no WSL2:

`scripts/deploy-pages-rgb-local.sh` (cópia de `scripts/deploy-producao-local.sh:1` do Rota, renomear):

```bash
LOCKFILE="/tmp/pages-rgb-deploy.lock"
IMAGE_TAG="$SHA"
docker compose -f docker-compose.pages-rgb.prod.yml pull pages-rgb-app
docker compose -f docker-compose.pages-rgb.prod.yml up -d
# healthcheck /api/v1/health/live até 90s
echo "$SHA" > .last-deployed-pages-rgb-tag
```

**Importante:** `IMAGE_TAG` e `LOCKFILE` diferentes do Rota → deploys não concorrem (`/tmp/pages-rgb-deploy.lock` vs `/tmp/rota-deploy...`).

4.4 Secrets GitHub (`Settings → Secrets and variables → Actions`):

- `CLOUDFLARE_TUNNEL_TOKEN_PAGES_RGB` (se usar `cloudflared` com token)
- `R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY`
- `DATABASE_URL` (se usar Supabase remoto) ou `PGPASSWORD` (se Postgres local WSL2)
- `ANDROID_GATEWAY_TOKEN` (Bearer)

Actions **só** no repo `pages_to_rgb`; **nunca** no repo do Rota → não dispara deploy do Rota.

## 5. Servidor — modo HANDWRITTEN_WORD isolado

**Objetivo:** `HANDWRITTEN_WORD` não toca `EXAM` (que fica como `EXAM` padrão). Reusa pipeline (GATE_1/2, Solve/Verify/Arbiter), mas classificação é palavra→cor.

5.1 Nova coluna `session_type`:

```sql
-- migration 0005_handwritten_session_type.py
ALTER TABLE sessions ADD COLUMN session_type TEXT NOT NULL DEFAULT 'EXAM'
  CHECK (session_type IN ('EXAM','HANDWRITTEN_WORD'));
ALTER TABLE captures ADD COLUMN session_type TEXT NOT NULL DEFAULT 'EXAM';
CREATE INDEX ix_sessions_session_type ON sessions(session_type);
```

Modelos `session.py:60` / `capture.py:44` + `expected_questions`/`expected_pages` já existem; para `HANDWRITTEN_WORD` fixar `expected_pages=10`, `expected_questions=10`.

5.2 Novo namespace **separado** (não alterar `/gateway/session/start` do EXAM):

```
POST /api/v1/handwritten/session/start   {gateway_code, device_code, expected_words:10}
POST /api/v1/handwritten/session/{id}/frame   (mesma semântica frame_upload, mas session_type=HANDWRITTEN_WORD)
POST /api/v1/handwritten/session/{id}/capture-complete
POST /api/v1/handwritten/session/{id}/end-signal
GET  /api/v1/handwritten/session/{id}/summary
GET  /api/v1/handwritten/session/{id}/policy
GET  /api/v1/handwritten/session/{id}/command
POST /api/v1/handwritten/session/{id}/debug/publish-rgb
```

Implementar `apps/api/routers/handwritten.py` (cópia de `gateway.py` mas com `session_type` hard `HANDWRITTEN_WORD` e `capture_source=ANDROID_CAMERA`). Validar `X-Gateway-Id` + `Authorization` igual ao Rota.

5.3 Mapping palavra→cor (5 nomes, 10 fotos):

| Palavra (OCR) | Cor RGB | `answer` | RGB paleta |
|---|---|---|---|
| João | Azul | `A`? ou `C`? | `0,0,255` (mesma paleta EXAM `D`) |
| Maria | Vermelha | `B`? | `255,0,0` (`E`) |
| Pedro | Verde | `C`? | `0,255,0` (novo) |
| Paula | Roxo | `D`? | `128,0,128` (novo) |
| Fernanda | Amarela | `E`? | `255,255,0` (`B`) |

**Escolha:** manter `A-E` como envelopes, mapear:

```
João -> A -> Azul   (0,0,255)
Maria -> B -> Vermelho (255,0,0)
Pedro -> C -> Verde (0,255,0)
Paula -> D -> Roxo (128,0,128)
Fernanda -> E -> Amarelo (255,255,0)
```

Paleta fica em `src/pages_to_audio/rgb/policy.py:15` como `HANDWRITTEN_PALETTE` (separada de `DEFAULT_PALETTE`), mas com **mesma estrutura** `RgbColor` + `defaults 12%/3000/5000` (exigência de mesma estrutura).

5.4 Pipeline reusado:

- `src/pages_to_audio/ocr/` → `GoogleDocumentAI`/`Azure`/`Paddle` já existe (sem mudar, só garante `PADDLE_OCR_ENABLED` opcional)
- `src/pages_to_audio/reconstruction/` → prompt `prompts/reconstruction/handwritten_word_v1.md` (instrui LLM: "extraia exatamente uma palavra entre [João,Maria,Pedro,Paula,Fernanda], normalize acentos/case").
- `src/pages_to_audio/rgb/publisher.py:91` → publica `HANDWRITTEN_PALETTE` quando `session_type=HANDWRITTEN_WORD`, senão `DEFAULT_PALETTE`. Mesma validação `item_count 1..1000`, `sha256` canonical `canonical.py:68`.
- Gate 1/2: `expected_questions=10`, `minimum_ratio=0.90` → `required=9`. Com 10 fotos, 10 palavras validadas → `READY`.

**Isolamento:** `EXAM` continua usando `DEFAULT_PALETTE` e `reconstruction/v1.md`; `HANDWRITTEN_WORD` usa `HANDWRITTEN_PALETTE` + prompt novo. Nenhum `if` espalha em código de EXAM — check só em `publisher.py` e `handwritten.py`.

## 6. Android — seletor + 10 fotos

**Atual:** `apps/gateway-android` seletor `Android/ESP32`, `SessionScreen.kt:61` `PreviewView` + `[Iniciar][Capturar][Encerrar]`, `SpoolRepository.kt:39` + `UploadWorker.kt:26` (10 fotos já suportado via `SpoolDao` unique index).

**Adição:**

6.1 `ui/SessionScreen.kt` novo toggle **antes** de `Iniciar sessão` (topo, abaixo de `TopBar`):

```
[Prova EXAM █]  [Teste Manuscrito █]   // session_type
```

Seleciona `session_type`; desabilita `ESP32` quando `HANDWRITTEN_WORD` (só câmera).

6.2 `domain/SessionRepository.kt` + `network/ApiService.kt` novo método `startHandwrittenSession` → `POST /handwritten/session/start` com `expected_words:10`. `SessionViewModel.kt:47` armazena `sessionType`.

6.3 Captura: `PhoneCameraCaptureSource.kt:42` idêntico (mesma ordem `capturar→salvar→Room→SHA→WorkManager→2xx→apagar`). Para `HANDWRITTEN_WORD`, gap 180ms mantido, mas `CapturePolicy` pode ser `full_jpeg_quality 92 / UXGA` (foto de palavra é menor que prova, não precisa altíssima).

6.4 Resumo: `GET /handwritten/session/{id}/summary` exibe lista `Q1: João → Azul`, `Q2: Fernanda → Amarelo` etc (mesma `SessionScreen` Linha 1 `Páginas: 10 | Fila: 2`).

6.5 Endpoint separation garante: se usuário escolher `EXAM`, chama `/gateway/*`; se `HANDWRITTEN_WORD`, chama `/handwritten/*` — **nenhum código de EXAM é tocado**.

## 7. Testes alternativos (sem imprimir simulado)

**10 fotos, 1 palavra cada, 5 nomes ×2 repetições** (ex: João, Maria, Pedro, Paula, Fernanda, João, Maria, Pedro, Paula, Fernanda).

**Pipeline:** mesma bateria `ETAPA_7_TESTES_11_GATES.md:11` mas com `session_type=HANDWRITTEN_WORD`:

| Gate | EXAM | HANDWRITTEN |
|---|---|---|
| 1 | `POST /gateway/session/start` | `POST /handwritten/session/start` |
| 3 | JPEG prova | JPEG folha A4 com palavra à mão (caneta preta, luz natural, sem sombra) |
| 11 | `RGB_SEQUENCE_READY` com `A-E` + paleta prova | `RGB_SEQUENCE_READY` com `A-E` + paleta palavra→cor, SHA `canonical` idêntico |

**Scripts:**

- `scripts/simulate_handwritten.py` (cópia de `simulate_android.py:1` mas gera JPEG com texto renderizado PIL `João` etc + `_headers` + `X-Resolution`)
- `tests/unit/handwritten/test_word_mapping.py` (mapeamento case-insensitive, acento, 5 nomes, fallback `FAILED` se não reconhecido)

**Fotos reais:** usar câmera do celular via APK (folha branca, palavra centralizada, 1 palavra por foto, sem outras marcas) → `POST /handwritten/session/{id}/frame` idêntico ao EXAM (mesmo `storage_key` mas bucket R2 separado).

## 8. Deploy GitHub Actions (pages_to_rgb isolado)

**Workflow minimal (sem Next, sem swap 8GB):**

`.github/workflows/deploy-pages-rgb.yml`:

```yaml
name: pages-to-rgb build & deploy
on: { push: { branches: [main] } }
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: uv sync && uv run ruff check src/ apps/ && uv run pytest tests/unit -q
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with: { registry: ghcr.io, username: ${{ github.actor }}, password: ${{ secrets.GITHUB_TOKEN }} }
      - uses: docker/build-push-action@v6
        with:
          context: .
          file: ./infra/docker/Dockerfile.pages-rgb
          push: true
          tags: ghcr.io/leoalvespak-alt/pages_to_rgb:${{ github.sha }}
```

Deploy no WSL2 (manual após build, como Rota):

```bash
# no WSL2 /srv/pages-to-rgb
./scripts/deploy-pages-rgb-local.sh <sha>
# que faz: docker compose -f docker-compose.pages-rgb.prod.yml pull && up -d && healthcheck
```

**Isolamento:** `IMAGE_NAME` ≠ Rota, `LOCKFILE` ≠ Rota, `Caddy` porta ≠ Rota (8080 vs 80), `Tunnel` ID ≠ Rota, `Secrets` prefix `PAGES_RGB_*`. Impossível disparar deploy do Rota ao fazer push no `pages_to_rgb`.

---

## Ordem de execução (recomendada — 2 semanas)

**Semana 1 — Infra + Storage + Repo**

1. Registrar domínio gratuito + criar bucket R2 `pages-to-rgb` + gerar token R2.
2. Criar tunnel `pages-to-rgb-wsl2` + serviço `cloudflared-pages-rgb` + DNS CNAME.
3. Push `pagestoaudio_servidor` → `pages_to_rgb.git` `main` + workflow `deploy-pages-rgb.yml`.
4. Criar `docker-compose.pages-rgb.prod.yml` + `Caddyfile.pages-rgb` + teste `https://<novo-dominio>/health/live`.

**Semana 2 — App + Pipeline**

5. Migration `0005_session_type` + `handwritten.py` + `HANDWRITTEN_PALETTE` + `R2StorageAdapter`.
6. Android seletor `EXAM/HANDWRITTEN_WORD` + 10 fotos + endpoints `/handwritten/*`.
7. `simulate_handwritten.py` + testes `test_word_mapping.py` + bateria 11 gates adaptada.
8. Validação fim-a-fim: 10 folhas manuscritas → `summary` 10 cores → `RGB_SEQUENCE_READY` `duplicate:true` + painel.

**Critérios de aceite:**

- `EXAM` continua passando `361` testes, sem tocar `DEFAULT_PALETTE` nem `/gateway/*`.
- `HANDWRITTEN_WORD` com 10 fotos gera 10 itens RGB com cores exatas (João Azul etc), SHA `<BBBBBII` <256 KiB, `COMPLETED duplicate:true`.
- `git push origin main` em `pages_to_rgb` **não** dispara deploy do Rota, e vice-versa.
- `https://<novo-dominio>` responde via tunnel + Caddy, imagens em R2 com signed URL 300s, sem porta aberta no roteador.

---

## Referências para execução

- `Rota-Migracao-2026/INFRA-WSL2-ESTABILIDADE.md` (KeepAlive, .wslconfig)
- `Rota de Ataque/.../Docs/DEPLOY_VPS.md` (GHCR, `deploy-producao-local.sh`, tunnel `17a16fd2...`)
- `src/pages_to_audio/storage/supabase_storage.py:19` → modelo para `r2_storage.py`
- `src/pages_to_audio/rgb/policy.py:15` → adicionar `HANDWRITTEN_PALETTE`
- `src/pages_to_audio/rgb/canonical.py:68` → SHA fixo
- `apps/gateway-android/app/src/main/java/.../ui/SessionScreen.kt:61` → adicionar toggle
