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
  # The operational file is maintained on Windows and may contain a UTF-8 BOM.
  # Strip only that marker while sourcing; never rewrite or print the secrets file.
  # shellcheck disable=SC1091
  set -a; . <(sed '1s/^\xEF\xBB\xBF//' /srv/pages-to-rgb/config/.env.pages-rgb); set +a
fi

OUT="$BACKUP_DIR/pages-pre-deploy-$STAMP.dump"
echo "pg_dump -> $OUT"
# SQLAlchemy uses an async driver suffix that libpq/pg_dump does not understand.
# Keep the operational URL untouched and normalize only the scheme passed to pg_dump.
DB_URL_FOR_DUMP="$DATABASE_URL"
DB_URL_FOR_DUMP="${DB_URL_FOR_DUMP//postgresql+asyncpg:\/\//postgresql:\/\/}"
DB_URL_FOR_DUMP="${DB_URL_FOR_DUMP//postgresql+psycopg:\/\//postgresql:\/\/}"
DB_URL_FOR_DUMP="${DB_URL_FOR_DUMP//host.docker.internal/127.0.0.1}"
pg_dump --format=custom --file="$OUT" "$DB_URL_FOR_DUMP"
ls -la "$OUT"
echo "CURRENT_TAG=$(cat .last-deployed-pages-rgb-tag 2>/dev/null || echo unknown)" > "$OUT.tag"
echo "Backup OK: $OUT"
