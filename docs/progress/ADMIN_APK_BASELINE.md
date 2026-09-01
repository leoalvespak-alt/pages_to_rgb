# Baseline das fases 0–5 — Admin/APK

Data: 01/09/2026  
SHA inicial: `3abdecb`  
Branch: `main`, alinhada a `origin/main`

## Estado inicial

- Rascunho `apps/admin` e plano estavam não rastreados; foram preservados.
- Suíte Python: `376 passed`, 1 warning de depreciação Starlette/httpx.
- Python local: 3.14.0; projeto declara Python >=3.12.
- Migrações existentes: `0001`–`0005`.

## Dívida preexistente observada

- O mypy estrito do repositório já falhava em módulos de imagem, RAG, Temporal, tipos SQLAlchemy e dependências sem stubs.
- O Ruff global já apontava violações em migrações/testes preexistentes.
- A validação desta entrega deve separar regressões novas da dívida registrada acima.
