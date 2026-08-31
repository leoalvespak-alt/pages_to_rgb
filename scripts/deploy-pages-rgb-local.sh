#!/usr/bin/env bash
set -euo pipefail

# Deploy pages-to-rgb isolado — não toca Rota (lockfile/compose/porta diferentes).
# Uso: ./scripts/deploy-pages-rgb-local.sh <IMAGE_TAG>

LOCKFILE="/tmp/pages-rgb-deploy.lock"
COMPOSE="infra/docker-compose.pages-rgb.prod.yml"
CADDYFILE="infra/Caddyfile.pages-rgb"
ENV_FILE="/srv/pages-to-rgb/config/.env.pages-rgb"
SRC_ENV=".env.pages-rgb"

exec 9>"$LOCKFILE"
if ! flock -n 9; then
  echo "Another pages-rgb deploy is running ($LOCKFILE)" >&2
  exit 1
fi

IMAGE_TAG="${1:-latest}"
export IMAGE_TAG

if [[ ! -f "$ENV_FILE" && -f "$SRC_ENV" ]]; then
  echo "WARN: $ENV_FILE not found, using $SRC_ENV — copy to $ENV_FILE for production" >&2
  ENV_FILE="$SRC_ENV"
fi

if [[ ! -f "$COMPOSE" ]]; then
  echo "Missing $COMPOSE" >&2
  exit 1
fi

echo "=== pages-to-rgb deploy TAG=$IMAGE_TAG ==="

# Pull e up
if command -v docker >/dev/null 2>&1; then
  docker compose -f "$COMPOSE" pull pages-rgb-app || true
  docker compose -f "$COMPOSE" up -d
else
  echo "docker not found, skipping compose up (CI mode)" >&2
fi

# Healthcheck até 90s
echo "Waiting healthcheck..."
for i in $(seq 1 18); do
  if curl -fsS http://127.0.0.1:8080/api/v1/health/live >/dev/null 2>&1 || curl -fsS http://127.0.0.1:8001/api/v1/health/live >/dev/null 2>&1 || curl -fsS http://localhost:8000/api/v1/health/live >/dev/null 2>&1; then
    echo "health ok after $((i*5))s"
    break
  fi
  echo "  attempt $i/18..."
  sleep 5
  if [[ $i -eq 18 ]]; then
    echo "health check failed" >&2
    docker compose -f "$COMPOSE" ps || true
    docker compose -f "$COMPOSE" logs --tail=100 || true
    exit 1
  fi
done

echo "$IMAGE_TAG" > .last-deployed-pages-rgb-tag
echo "Deploy OK tag=$IMAGE_TAG"
