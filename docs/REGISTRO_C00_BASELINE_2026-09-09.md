# C00 — baseline isolado e versionamento (09/09/2026)

## Branch e HEAD

- Repositório servidor: `C:/Users/Lenovo/Downloads/pagestoaudio_servidor`
- Branch: `codex/conclusao-pos-reauditoria-2026-09-09`, criada de `be34d8a`
  (`be34d8a65d3517e372b496decd84e64e48965e54`), sem rebase, sem stage global.
- HEAD anterior na cadeia: `c282758` → `be34d8a`. Diagnóstico D00–D08 segue
  fora desses commits (não rastreado) até commits pequenos por etapa.

## Classificação do diff (git status na criação da branch)

Modificados (diagnóstico, meus — commitar por etapa, sem opacidade):
`M .env.example`, `M apps/admin/__tests__/flows.test.mjs`, `M apps/api/main.py`,
`M apps/gateway-android/.../esp/EspHttpServer.kt`,
`M src/pages_to_audio/common/errors.py`, `M src/pages_to_audio/config/settings.py`,
`M src/pages_to_audio/db/models/__init__.py`, `M src/pages_to_audio/storage/keys.py`.

Modificado preexistente (NÃO meu — preservar sem stage até revisar diff):
`M docs/contracts/RGB_RESULT_V1.md` (nota de consolidação, 2 linhas).

Não rastreados meus (diagnóstico): `apps/admin/app/(admin)/admin/camera-test/`,
`apps/api/routers/admin_camera_diagnostics.py`,
`apps/api/routers/gateway_diagnostics.py`,
`apps/gateway-android/.../diag/`, `docs/REGISTRO_EXECUCAO_D00_D08_DIAG_2026-09-09.md`,
`docs/contracts/CAMERA_DIAGNOSTICS_2026-09-09.md`,
`docs/runbooks/camera-diag-D0[678]-*.md`,
`migrations/versions/0012_camera_diagnostics.py`,
`src/pages_to_audio/camera_diagnostics/`,
`src/pages_to_audio/db/models/camera_diagnostic.py`,
`tests/unit/api/test_camera_diagnostics_contract.py`.

Não rastreados alheios (auditoria/planos — não commitar neste fluxo):
`docs/AUDITORIA_TECNICA_COMPLETA_2026-09-09.md`,
`docs/PLANO_ADICIONAL_TESTE_CAMERA_2026-09-09.md`,
`docs/PLANO_CONCLUSAO_POS_REAUDITORIA_2026-09-09.md`,
`docs/PLANO_IMPLEMENTACAO_SERVIDOR_2026-09-09.md`,
`docs/REAUDITORIA_CRUZADA_IMPLEMENTACOES_2026-09-09.md`,
`docs/contracts/INTEGRACAO_CONSOLIDADA_2026-09-09.md`.

## Firmware: sem git add/commit

- A pasta pertence ao repositório ancestral `C:/Users/Lenovo` (HEAD `2f0869d`),
  com dezenas de arquivos alheios modificados (ex.: `Desktop/Rota de Ataque/...`).
  NENHUM `git add/commit` será executado a partir dele.
- Destino Git independente do firmware: PENDENTE de decisão do proprietário.
  Até lá, alterações do firmware ficam só em disco + hashes neste registro.
- BIN 2.4.0 (`build/` e `release/fw_2_4_0/`): SHA-256
  `3CF029A5B337D4F25E5D7C6C780D9D68F3CA396D0DC7CB8C7712C7CB46E2D312`
  (idênticos). É ANTERIOR às fontes diagnósticas — NÃO reutilizar.

## Toolchains e ambiente (sondagem, sem alteração de dados)

- Python (venv temporária): 3.14.0. Node: v24.16.0. Java/JDK: ausente.
  Docker: ausente. ESP-IDF python_env: ausente (`~/.espressif` inexistente).
- Portas: COM3 listada (não aberta — sem reset de placa); TCP 5432 em escuta
  (`::` e `0.0.0.0`); TCP 127.0.0.1:8081 em escuta.
- `CAMERA_DIAGNOSTICS_ENABLED=false` em `.env.example` (produção desligada).

## Gate C00

 Classificados: sim (tabela acima). Branch correta: sim. Nada staged nesta
etapa além deste registro. Baseline reproduzível: sim (HEAD + hashes + tools).
Próximo gate: C01 (protocolo único Android–ESP, RA01–RA03).
