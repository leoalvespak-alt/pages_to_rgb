#!/usr/bin/env bash
# S12 — rollback pages-to-rgb para digests anteriores compatíveis.
# Preserva banco, outbox, objetos e filas. NUNCA downgrade destrutivo de schema.
#
# Uso: PREV_IMAGE_TAG=sha-<anterior> ./scripts/rollback-pages-rgb.sh
set -euo pipefail

LOCKFILE="/tmp/pages-rgb-deploy.lock"
COMPOSE="infra/docker-compose.pages-rgb.prod.yml"
export COMPOSE_PROJECT_NAME="pages-rgb"
ENV_FILE="/srv/pages-to-rgb/config/.env.pages-rgb"
READY_HOST="ptr.rotadeataque.com.br"

exec 9>"$LOCKFILE"
if ! flock -n 9; then echo "Deploy/rollback em andamento ($LOCKFILE)" >&2; exit 1; fi

if [[ -z "${PREV_IMAGE_TAG:-}" ]]; then echo "PREV_IMAGE_TAG é obrigatório" >&2; exit 1; fi
export IMAGE_TAG="$PREV_IMAGE_TAG"

echo "=== rollback para TAG=$IMAGE_TAG (sem perda de dados) ==="
docker compose -f "$COMPOSE" --env-file "$ENV_FILE" config --quiet
docker compose -f "$COMPOSE" --env-file "$ENV_FILE" pull
# Sem downgrade de schema: migrações são aditivas e compatíveis (S11.5/S12.2).
docker compose -f "$COMPOSE" --env-file "$ENV_FILE" up -d pages-rgb-app pages-rgb-worker
docker compose -f "$COMPOSE" --env-file "$ENV_FILE" up -d

for i in $(seq 1 24); do
  if curl -fsS -H "Host: $READY_HOST" http://127.0.0.1:8081/api/v1/health/ready | grep -q '"status"[[:space:]]*:[[:space:]]*"ready"'; then
    echo "ready ok após rollback (~$((i*5))s)"
    break
  fi
  sleep 5
  if [[ $i -eq 24 ]]; then echo "readiness falhou após rollback" >&2; exit 1; fi
done
echo "$IMAGE_TAG" > .last-deployed-pages-rgb-tag
echo "Rollback OK tag=$IMAGE_TAG — retestar retomada e integridade (S12.5)"
