#!/usr/bin/env bash
# S11.5 — backup recuperável do banco antes do rollout (chamado pelo CI/deploy).
# Requer pg_dump acessível ao banco de produção; falha impede continuação.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/srv/pages-to-rgb/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR"

if [[ -z "${DATABASE_URL:-}" && ! -f /srv/pages-to-rgb/config/.env.pages-rgb ]]; then
  echo "DATABASE_URL ou .env operacional ausente; não é possível backup — abortando" >&2
  exit 1
fi

if [[ -f /srv/pages-to-rgb/config/.env.pages-rgb ]]; then
  # shellcheck disable=SC1091
  set -a; . /srv/pages-to-rgb/config/.env.pages-rgb; set +a
fi

OUT="$BACKUP_DIR/pages-pre-deploy-$STAMP.dump"
echo "pg_dump -> $OUT"
pg_dump --format=custom --file="$OUT" "$DATABASE_URL"
ls -la "$OUT"
echo "CURRENT_TAG=$(cat .last-deployed-pages-rgb-tag 2>/dev/null || echo unknown)" > "$OUT.tag"
echo "Backup OK: $OUT"
