#!/usr/bin/env bash
set -euo pipefail

base_url="${1:-https://ptr.rotadeataque.com.br}"
password_file="${2:-/srv/pages-to-rgb/config/admin-initial-password.txt}"
temp_dir="$(mktemp -d)"
cookie_jar="$temp_dir/cookies.txt"
trap 'rm -rf -- "$temp_dir"' EXIT

payload="$(python3 -c 'import json,sys; print(json.dumps({"password": open(sys.argv[1]).read().strip()}))' "$password_file")"
login_code="$(curl -sS -o "$temp_dir/admin-login.json" -w '%{http_code}' -c "$cookie_jar" -H 'Content-Type: application/json' --data "$payload" "$base_url/api/v1/admin/login")"
test "$login_code" = 200

me_code="$(curl -sS -o "$temp_dir/admin-me.json" -w '%{http_code}' -b "$cookie_jar" "$base_url/api/v1/admin/me")"
test "$me_code" = 200
csrf="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["csrf_token"])' "$temp_dir/admin-me.json")"

settings_code="$(curl -sS -o "$temp_dir/settings.json" -w '%{http_code}' -b "$cookie_jar" "$base_url/api/v1/admin/settings")"
test "$settings_code" = 200
catalog_code="$(curl -sS -o "$temp_dir/catalog.json" -w '%{http_code}' -b "$cookie_jar" "$base_url/api/v1/admin/settings/catalog")"
test "$catalog_code" = 200
python3 - "$temp_dir/catalog.json" <<'PY'
import json
import sys

providers = {item["name"] for item in json.load(open(sys.argv[1], encoding="utf-8"))["providers"]}
assert providers == {"gemini", "google_document_ai"}, providers
PY
python3 - "$temp_dir/settings.json" "$temp_dir/settings-put.json" <<'PY'
import json
import sys

source, target = sys.argv[1:]
settings = json.load(open(source, encoding="utf-8"))
allowed = {
    "version", "ocr_provider", "solve_model", "verify_model", "arbiter_model",
    "expected_pages", "expected_questions", "handwritten_expected_questions",
    "minimum_ratio", "brightness_percent", "on_ms", "off_ms", "palette",
    "handwritten_palette", "handwritten_words",
    "google_document_ai_project_id", "google_document_ai_location",
    "google_document_ai_processor_id", "google_document_ai_processor_version",
}
json.dump({key: value for key, value in settings.items() if key in allowed}, open(target, "w", encoding="utf-8"))
PY
settings_put_code="$(curl -sS -o "$temp_dir/settings-updated.json" -w '%{http_code}' -X PUT -b "$cookie_jar" -H "X-CSRF-Token: $csrf" -H 'Content-Type: application/json' --data-binary "@$temp_dir/settings-put.json" "$base_url/api/v1/admin/settings")"
test "$settings_put_code" = 200

settings_readback_code="$(curl -sS -o /dev/null -w '%{http_code}' -b "$cookie_jar" "$base_url/api/v1/admin/settings")"
test "$settings_readback_code" = 200
sessions_code="$(curl -sS -o /dev/null -w '%{http_code}' -b "$cookie_jar" "$base_url/api/v1/admin/sessions?page=1&page_size=5")"
test "$sessions_code" = 200
echo "settings=get:$settings_code catalog=$catalog_code put:$settings_put_code readback:$settings_readback_code sessions=$sessions_code"

logout_code="$(curl -sS -o /dev/null -w '%{http_code}' -X POST -b "$cookie_jar" -H "X-CSRF-Token: $csrf" "$base_url/api/v1/admin/logout")"
test "$logout_code" = 204
echo "login=200 logout=204 admin-smoke=ok"
