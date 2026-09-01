#!/usr/bin/env bash
set -euo pipefail

base_url="${1:-https://ptr.rotadeataque.com.br}"
password_file="${2:-/srv/pages-to-rgb/config/admin-initial-password.txt}"
cookie_jar="$(mktemp)"
trap 'rm -f "$cookie_jar"' EXIT

payload="$(python3 -c 'import json,sys; print(json.dumps({"password": open(sys.argv[1]).read().strip()}))' "$password_file")"
login_code="$(curl -sS -o /tmp/admin-login.json -w '%{http_code}' -c "$cookie_jar" -H 'Content-Type: application/json' --data "$payload" "$base_url/api/v1/admin/login")"
test "$login_code" = 200

me_code="$(curl -sS -o /tmp/admin-me.json -w '%{http_code}' -b "$cookie_jar" "$base_url/api/v1/admin/me")"
test "$me_code" = 200
csrf="$(python3 -c 'import json; print(json.load(open("/tmp/admin-me.json"))["csrf_token"])')"

for endpoint in settings 'sessions?page=1&page_size=5'; do
  code="$(curl -sS -o /dev/null -w '%{http_code}' -b "$cookie_jar" "$base_url/api/v1/admin/$endpoint")"
  test "$code" = 200
  echo "$endpoint=$code"
done

logout_code="$(curl -sS -o /dev/null -w '%{http_code}' -X POST -b "$cookie_jar" -H "X-CSRF-Token: $csrf" "$base_url/api/v1/admin/logout")"
test "$logout_code" = 204
echo "login=200 logout=204 admin-smoke=ok"
