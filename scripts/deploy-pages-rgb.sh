#!/usr/bin/env bash
# S11 — caminho operacional ÚNICO de deploy pages-to-rgb (lock, projeto explícito,
# pull obrigatório, migrate uma vez, health pelo roteamento correto, sem latest).
#
# Uso (no diretório operacional real da VPS, em geral /srv/pages-to-rgb/app):
#   IMAGE_TAG=sha-<short> ./scripts/deploy-pages-rgb.sh
#
# Exige: docker + compose plugin, .env operacional em /srv/pages-to-rgb/config/.env.pages-rgb
# (NUNCA regenera hash de senha aqui), backup prévio feito pelo chamador/CI.
set -euo pipefail

LOCKFILE="/tmp/pages-rgb-deploy.lock"
COMPOSE="infra/docker-compose.pages-rgb.prod.yml"
PROJECT="pages-rgb"
ENV_FILE="/srv/pages-to-rgb/config/.env.pages-rgb"
READY_HOST="ptr.rotadeataque.com.br"

exec 9>"$LOCKFILE"
if ! flock -n 9; then
  echo "Another pages-rgb deploy is running ($LOCKFILE)" >&2
  exit 1
fi

# S11.4: verifica o projeto Compose em uso antes de escolher -p (evita duplicar).
if [[ "${COMPOSE_PROJECT_NAME:-}" != "" && "${COMPOSE_PROJECT_NAME}" != "$PROJECT" ]]; then
  echo "COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME} difere de $PROJECT; abortando para não duplicar serviços/volumes" >&2
  exit 1
fi
export COMPOSE_PROJECT_NAME="$PROJECT"

if [[ -z "${IMAGE_TAG:-}" ]]; then
  echo "IMAGE_TAG é obrigatório (SHA imutável, ex: sha-abc1234). latest é proibido em produção." >&2
  exit 1
fi
if [[ "$IMAGE_TAG" == "latest" ]]; then
  echo "Recusado: deploy por latest é proibido (S11.7). Use o SHA publicado pelo CI." >&2
  exit 1
fi
export IMAGE_TAG

if [[ ! -f "$COMPOSE" ]]; then echo "Missing $COMPOSE (rode no diretório operacional real)" >&2; exit 1; fi
if [[ ! -f "$ENV_FILE" ]]; then echo "Missing $ENV_FILE" >&2; exit 1; fi
if ! command -v docker >/dev/null 2>&1; then echo "docker não encontrado" >&2; exit 1; fi

echo "=== pages-to-rgb deploy TAG=$IMAGE_TAG projeto=$PROJECT ==="

# S11.2: validação de configuração (falha imediata, sem sucesso artificial).
docker compose -f "$COMPOSE" --env-file "$ENV_FILE" config --quiet

# S11.2: pull OBRIGATÓRIO (falha impede continuação; nunca `|| true`).
docker compose -f "$COMPOSE" --env-file "$ENV_FILE" pull

# S11.8: migrações novas uma vez no alvo, com falha impedindo continuação.
echo "--- migrations ---"
docker compose -f "$COMPOSE" --env-file "$ENV_FILE" run --rm --no-deps pages-rgb-app \
  python -m alembic upgrade head

# S11.9: rollout aditivo — backend/worker compatíveis primeiro.
echo "--- rollout app+worker ---"
docker compose -f "$COMPOSE" --env-file "$ENV_FILE" up -d pages-rgb-app pages-rgb-worker
docker compose -f "$COMPOSE" --env-file "$ENV_FILE" up -d

# S11.11: saúde pelo roteamento correto — porta local 127.0.0.1:8081 com Host real,
# endpoint /ready (NÃO qualquer 200 genérico, NÃO /live como prova).
echo "--- readiness (Host: $READY_HOST) ---"
READY_OK=0
for i in $(seq 1 24); do
  if curl -fsS -H "Host: $READY_HOST" http://127.0.0.1:8081/api/v1/health/ready | grep -q '"status"[[:space:]]*:[[:space:]]*"ready"'; then
    echo "ready ok após ~$((i*5))s"
    READY_OK=1
    break
  fi
  echo "  tentativa $i/24..."
  sleep 5
done
if [[ "$READY_OK" != "1" ]]; then
  echo "readiness FALHOU (ver S12 rollback)" >&2
  docker compose -f "$COMPOSE" --env-file "$ENV_FILE" ps || true
  docker compose -f "$COMPOSE" --env-file "$ENV_FILE" logs --tail=150 pages-rgb-app pages-rgb-worker || true
  exit 1
fi

# S11.12: confirmação externa + identidade da release + worker na fila.
curl -fsS "https://$READY_HOST/api/v1/health/ready" | head -c 600; echo
curl -fsS -H "Host: $READY_HOST" http://127.0.0.1:8081/api/v1/health/worker | head -c 400; echo

echo "$IMAGE_TAG" > .last-deployed-pages-rgb-tag
echo "Deploy OK tag=$IMAGE_TAG (Android depois, firmware por último — S11.9)"
