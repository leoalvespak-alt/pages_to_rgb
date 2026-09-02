# Incidentes e execução — 02/09/2026

## Política aprovada

O único fluxo de IA ativo é Google Document AI Enterprise OCR → Gemini 3.1 Pro
Preview (`gemini-3.1-pro-preview`) para conferência multimodal → Gemini para
correção/resolução. DeepSeek, Claude e GLM não são selecionáveis.

A conferência aplica faixas por trecho: texto comum `0,90/0,75` e trecho crítico
`0,95/0,85`; recomposição só ocorre com indício de degradação, seguindo evidência
visual > OCR Google > contexto local. Ambiguidade com impacto na resposta é a
única exceção que encaminha uma leitura acima do limite para revisão manual.

## Estado da execução

| ID | Correção | Evidência | Estado |
|---|---|---|---|
| INC-01 | Fallback DNS seguro no APK, sem desabilitar TLS | `FallbackDnsTest`; `testDebugUnitTest`, `lintDebug`, `assembleDebug` verdes | Verificado; falta aparelho físico |
| INC-02 | Colunas de contexto do `AuditEvent` | Migração 0008 aplicada em produção, encadeada a 0009/0010 | Concluído |
| INC-03 | Catálogo restrito e credenciais separadas | catálogo API retorna somente Gemini + Document AI; smoke 200 | Concluído |
| INC-04 | ID oficial do Gemini | `gemini-3.1-pro-preview` em schema/adapter e produção | Concluído |
| INC-05 | GLM/DeepSeek/Claude fora do fluxo | migração 0010 + UI sem opções; produção em `sha-7869349` | Concluído |
| INC-06 | Document AI com project/location/processor e bytes reais | provider sem placeholder `b""`; normalização de estrutura/confiança/qualidade | Código concluído; falta cadastrar credencial real |
| INC-07 | Factory DB-backed para OCR/Gemini | `src/pages_to_audio/ai/factory.py`; modelos validados no smoke | Concluído |

Nenhuma chave real é criada ou registrada por este documento. Se uma credencial
não existir no ambiente, permanece explicitamente como `Não configurada`.

## Evidência final de deploy

- suíte Python: 399 testes verdes; mypy direcionado aos arquivos alterados, Ruff e
  `compileall` verdes;
- CI `33636029217` e deploy `33636029123` verdes para o commit `7869349`;
- backup PostgreSQL: `/srv/pages-to-rgb/backups/pre-0010-9f5bea3.dump`;
- Alembic em produção: `0010 (head)`; imagens API/Admin: `sha-7869349`;
- smoke autenticado: login 200, catálogo 200, `PUT` 200, readback 200,
  sessões 200 e logout 204; health público 200;
- APK debug gerado em `apps/gateway-android/app/build/outputs/apk/debug/app-debug.apk`;
  SHA-256 `c1cb692b339441f4b887d917c9afd1e66b63b6f0e88d8794f7a4ca4bb17cc136`.

## Pendências operacionais

- cadastrar a chave real do Gemini e as credenciais JSON do Google Document AI
  (project/location/processor) no Admin; o ambiente permanece deliberadamente
  sem segredos (`gemini_configured=false` e Document AI `false`);
- instalar o APK e exercitar DNS/sessão/RGB em um Android conectado; `adb devices`
  não encontrou aparelho durante esta execução;
- a checagem mypy global ainda possui avisos legados fora dos arquivos alterados;
  o gate de CI permanece direcionado e verde.
