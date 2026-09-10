#!/usr/bin/env bash
set -euo pipefail

# Production deploy for the isolated pages-to-rgb stack hosted by local WSL2.
# The Rota stack keeps its own compose project, lock and ports.

LOCKFILE="/tmp/pages-rgb-deploy.lock"
COMPOSE="infra/docker-compose.pages-rgb.prod.yml"
ENV_FILE="/srv/pages-to-rgb/config/.env.pages-rgb"
READY_HOST="ptr.rotadeataque.com.br"
LOCAL_BASE="http://127.0.0.1:8081"
PROJECT="pages-to-rgb"

IMAGE_TAG="${1:?Usage: $0 sha-<immutable-tag>}"
if [[ "$IMAGE_TAG" == "latest" ]]; then
  echo "latest is forbidden for Production deploys" >&2
  exit 1
fi
export IMAGE_TAG

exec 9>"$LOCKFILE"
if ! flock -n 9; then
  echo "Another pages-rgb deploy is running ($LOCKFILE)" >&2
  exit 1
fi

if [[ ! -f "$COMPOSE" ]]; then
  echo "Missing $COMPOSE" >&2
  exit 1
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing operational environment file $ENV_FILE" >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found" >&2
  exit 1
fi

COMPOSE_ARGS=("-p" "$PROJECT" "-f" "$COMPOSE" "--env-file" "$ENV_FILE")

echo "=== pages-to-rgb WSL2 Production deploy TAG=$IMAGE_TAG ==="

echo "--- recoverable database backup ---"
./scripts/backup-db.sh

echo "--- compose validation ---"
docker compose "${COMPOSE_ARGS[@]}" config --quiet

echo "--- pull immutable images ---"
docker compose "${COMPOSE_ARGS[@]}" pull

echo "--- additive migrations ---"
docker compose "${COMPOSE_ARGS[@]}" run --rm --no-deps pages-rgb-app \
  python -m alembic upgrade head

echo "--- app, worker, admin and Caddy rollout ---"
docker compose "${COMPOSE_ARGS[@]}" up -d pages-rgb-app pages-rgb-worker admin pages-rgb-caddy

echo "--- local readiness ---"
READY_OK=0
for i in $(seq 1 24); do
  if curl -fsS -H "Host: $READY_HOST" \
      "$LOCAL_BASE/api/v1/health/ready" \
      | grep -Eq '"status"[[:space:]]*:[[:space:]]*"ready"'; then
    echo "ready ok after ~$((i * 5))s"
    READY_OK=1
    break
  fi
  echo "  attempt $i/24..."
  sleep 5
done
if [[ "$READY_OK" != "1" ]]; then
  echo "local readiness failed" >&2
  docker compose "${COMPOSE_ARGS[@]}" ps
  docker compose "${COMPOSE_ARGS[@]}" logs --tail=150 pages-rgb-app pages-rgb-worker admin pages-rgb-caddy >&2 || true
  exit 1
fi

curl -fsS -H "Host: $READY_HOST" "$LOCAL_BASE/api/v1/health/worker"
echo
docker compose "${COMPOSE_ARGS[@]}" ps

echo "--- public tunnel smoke ---"
curl -fsS "https://$READY_HOST/api/v1/health/ready"
echo
curl -fsS "https://$READY_HOST/api/v1/health/worker"
echo

printf '%s\n' "$IMAGE_TAG" > /srv/pages-to-rgb/.last-deployed-pages-rgb-tag
echo "Deploy OK tag=$IMAGE_TAG project=$PROJECT host=$READY_HOST"
