#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="/srv/pages-to-rgb/config/.env.pages-rgb"
PASSWORD_FILE="/srv/pages-to-rgb/config/admin-initial-password.txt"
IMAGE="${1:?API image required}"

if ! grep -q '^ADMIN_PASSWORD_HASH=' "$ENV_FILE"; then
  password="$(openssl rand -base64 24 | tr -d '\n')"
  password_hash="$(docker run --rm -e ADMIN_BOOTSTRAP_PASSWORD="$password" "$IMAGE" python -c 'from argon2 import PasswordHasher; import os; print(PasswordHasher().hash(os.environ["ADMIN_BOOTSTRAP_PASSWORD"]))')"
  encryption_key="$(openssl rand -base64 32 | tr -d '\n')"
  printf '%s\n' "$password" > "$PASSWORD_FILE"
  chmod 600 "$PASSWORD_FILE"
  compose_password_hash="${password_hash//\$/\$\$}"
  printf '\nADMIN_PASSWORD_HASH=%s\nADMIN_SETTINGS_ENCRYPTION_KEY=%s\n' "$compose_password_hash" "$encryption_key" >> "$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi

grep -q '^ADMIN_PASSWORD_HASH=' "$ENV_FILE"
grep -q '^ADMIN_SETTINGS_ENCRYPTION_KEY=' "$ENV_FILE"
echo "Admin secrets ready; initial password stored with mode 600."
