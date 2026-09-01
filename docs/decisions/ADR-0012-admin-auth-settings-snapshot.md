# ADR-0012 — Auth admin, secrets e snapshot de settings

## Status

Aceito em 01/09/2026 para as fases 1–5 do plano Admin/APK.

## Decisões

- Autenticação usa senha Argon2 e JWT HS256 em cookie host-only `HttpOnly`, com CSRF assinado.
- O browser não armazena token em `localStorage`.
- Chaves de providers são cifradas com Fernet; a chave mestra vive apenas no ambiente.
- `admin_settings` é singleton e usa `version` para optimistic locking.
- Cada nova sessão grava `config_snapshot` e `provider_snapshot`; publisher e summary usam o snapshot.
- Se a linha singleton ainda não existir durante rollout, start usa defaults de ambiente. A migração cria a linha antes do deploy da API.

## Consequências

- Mudanças globais afetam somente novas sessões.
- Rotação da chave de criptografia exige procedimento explícito de recifragem.
- Escritas admin exigem cookie válido e `X-CSRF-Token`.
