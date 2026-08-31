# Runbook: stack local real

Este projeto pode ser executado de duas formas:

1. Docker Compose, com PostgreSQL + pgvector, Temporal, API e worker.
2. Desenvolvimento no Windows usando PostgreSQL instalado no WSL.

Os valores abaixo são somente para desenvolvimento local. Não reutilize as credenciais do `.env` em qualquer ambiente compartilhado.

## Opção recomendada: Docker Compose

Pré-requisitos: Docker Desktop com Compose habilitado, `uv` e um `.env` criado a partir de `.env.example`.

```powershell
Copy-Item .env.example .env
uv sync --all-extras
docker compose -f infra/docker-compose.dev.yml up -d --build
```

O Compose inicia, em ordem:

- PostgreSQL com a extensão `vector`;
- Temporal e seu banco de metadados;
- a migração Alembic até `head`;
- API em `http://127.0.0.1:18180`;
- worker Temporal para a fila `pages-to-audio-main`.

Verificação:

```powershell
Invoke-RestMethod http://127.0.0.1:18180/api/v1/health/live
Invoke-RestMethod http://127.0.0.1:18180/api/v1/health/dependencies
```

Para acompanhar os serviços e parar a stack:

```powershell
docker compose -f infra/docker-compose.dev.yml logs -f pages-api pages-worker temporal
docker compose -f infra/docker-compose.dev.yml down
```

## Opção sem Docker: PostgreSQL no WSL

O script abaixo atualiza o IP do WSL no `.env`. O IP pode mudar quando a distribuição reinicia.

```powershell
Copy-Item .env.example .env
uv sync --all-extras
.\scripts\configure_local_wsl.ps1
uv run alembic upgrade head
```

Em um terminal WSL, inicie o Temporal de desenvolvimento persistente:

```bash
bash /mnt/c/Users/Lenovo/Downloads/pagestoaudio_servidor/scripts/start_temporal_wsl.sh
```

Em um terminal Windows, inicie a API:

```powershell
uv run uvicorn apps.api.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

Em outro terminal, inicie o worker:

```powershell
uv run python -m src.pages_to_audio.workflows.worker
```

O Temporal UI ficará disponível em `http://127.0.0.1:8233` e `/api/v1/health/dependencies` deverá retornar `database.status = ok` e `temporal.status = ok`. Se o Temporal não estiver rodando, a API continuará iniciando e reportará `temporal.status = unavailable`; isso é uma falha real de dependência, não um fallback silencioso.

## Banco e migrações

A revisão atual esperada é `0003`. Para confirmar:

```powershell
uv run alembic current
uv run alembic upgrade head
```

As migrações criam as tabelas de sequências RGB, eventos RGB e entregas idempotentes por sessão.

## Desligamento

```powershell
docker compose -f infra/docker-compose.dev.yml down
```

Para preservar os dados locais, não use `down -v`. O volume `pages-to-audio-postgres` contém o banco de desenvolvimento.
