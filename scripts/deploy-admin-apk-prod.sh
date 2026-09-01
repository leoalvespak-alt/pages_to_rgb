#!/usr/bin/env bash
set -euo pipefail

env_file="/srv/pages-to-rgb/config/.env.pages-rgb"
compose_file="infra/docker-compose.pages-rgb.prod.yml"
export IMAGE_TAG="${1:?image tag required}"

# Docker Compose interpolates dollar signs in env-file values; escape Argon2's
# separators exactly once so the container receives the original hash.
python3 - "$env_file" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
lines = path.read_text().splitlines()
fixed = []
for line in lines:
    if line.startswith("ADMIN_PASSWORD_HASH="):
        key, value = line.split("=", 1)
        value = value.replace("$$", "$").replace("$", "$$")
        line = f"{key}={value}"
    fixed.append(line)
path.write_text("\n".join(fixed) + "\n")
PY
chmod 600 "$env_file"

docker compose -p pages-to-rgb -f "$compose_file" --env-file "$env_file" config --quiet
docker compose -p pages-to-rgb -f "$compose_file" --env-file "$env_file" up -d pages-rgb-app admin pages-rgb-caddy
docker compose -p pages-to-rgb -f "$compose_file" --env-file "$env_file" ps
