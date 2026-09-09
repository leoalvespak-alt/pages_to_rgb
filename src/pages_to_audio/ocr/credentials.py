"""S05.7/A27 — carregamento único de credenciais Google + token com reuso.

Usado pelo adaptador OCR real e pelo save-and-verify administrativo: o teste
usa exatamente o mesmo mecanismo do processamento real (JSON ou caminho).
Refresh executado em executor (nunca bloqueia o event loop).
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass

_CACHED_TOKEN: str | None = None
_CACHED_EXPIRY: float = 0.0


@dataclass(frozen=True)
class GoogleCredentials:
    info: dict | None  # service_account info quando JSON
    file_path: str | None  # caminho quando arquivo


def load_google_credentials(
    raw: str | None, *, file_fallback: str | None = None
) -> GoogleCredentials:
    """Aceita JSON ou caminho de arquivo — mesmo caminho p/ verify e execução."""
    candidate = (raw or "").strip() or (file_fallback or "").strip()
    if not candidate:
        raise RuntimeError("Google credentials are not configured")
    if candidate.lstrip().startswith("{"):
        try:
            info = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Google credentials JSON is invalid") from exc
        if info.get("type") != "service_account":
            raise RuntimeError("Google credentials JSON is not a service_account key")
        return GoogleCredentials(info=info, file_path=None)
    from pathlib import Path

    path = Path(candidate)
    if not path.is_file():
        raise RuntimeError("Google credentials file was not found")
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Google credentials file is invalid") from exc
    return GoogleCredentials(info=info, file_path=str(path))


async def get_google_access_token(creds: GoogleCredentials) -> str:
    """Token com reuso até ~50min; refresh síncrono isolado em thread."""
    global _CACHED_TOKEN, _CACHED_EXPIRY
    now = time.monotonic()
    if _CACHED_TOKEN and now < _CACHED_EXPIRY:
        return _CACHED_TOKEN

    def _refresh() -> str:
        import google.auth
        import google.auth.transport.requests

        scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        if creds.info is not None:
            from google.oauth2 import service_account

            credentials = service_account.Credentials.from_service_account_info(
                creds.info, scopes=scopes
            )
        else:
            assert creds.file_path is not None
            credentials, _ = google.auth.load_credentials_from_file(creds.file_path, scopes=scopes)
        credentials.refresh(google.auth.transport.requests.Request())
        return str(credentials.token)

    token = await asyncio.to_thread(_refresh)
    _CACHED_TOKEN = token
    _CACHED_EXPIRY = now + 50 * 60
    return token


def reset_google_token_cache() -> None:
    global _CACHED_TOKEN, _CACHED_EXPIRY
    _CACHED_TOKEN = None
    _CACHED_EXPIRY = 0.0
