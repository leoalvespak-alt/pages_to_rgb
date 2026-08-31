#!/usr/bin/env bash
set -euo pipefail

TEMPORAL_BIN="/home/deploy/.local/bin/temporal"
TEMPORAL_DB="/home/deploy/temporal-pages-to-audio.db"

if [[ ! -x "$TEMPORAL_BIN" ]]; then
    echo "Temporal CLI não encontrado em $TEMPORAL_BIN" >&2
    echo "Instale o CLI oficial antes de executar este script." >&2
    exit 1
fi

exec "$TEMPORAL_BIN" server start-dev \
    --ip 0.0.0.0 \
    --port 7233 \
    --ui-port 8233 \
    --db-filename "$TEMPORAL_DB" \
    --namespace pages-to-audio
