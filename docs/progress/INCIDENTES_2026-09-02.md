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
| INC-01 | Fallback DNS seguro no APK, sem desabilitar TLS | `FallbackDnsTest`; `testDebugUnitTest`, `lintDebug`, `assembleDebug` verdes | Aguardando aparelho |
| INC-02 | Colunas de contexto do `AuditEvent` | Migração 0008 encadeada a 0009/0010; suíte Python 396 testes | Aguardando produção |
| INC-03 | Catálogo restrito e credenciais separadas | catálogo API + campos Document AI | Implementado localmente |
| INC-04 | ID oficial do Gemini | `gemini-3.1-pro-preview` em schema/adapter | Implementado localmente |
| INC-05 | GLM/DeepSeek/Claude fora do fluxo | migração 0010 + UI sem opções | Implementado localmente |
| INC-06 | Document AI com project/location/processor e bytes reais | provider sem placeholder `b""`; normalização de estrutura/confiança/qualidade | Aguardando credencial e produção |
| INC-07 | Factory DB-backed para OCR/Gemini | `src/pages_to_audio/ai/factory.py` | Implementado localmente |

Nenhuma chave real é criada ou registrada por este documento. Se uma credencial
não existir no ambiente, permanece explicitamente como `Não configurada`.

## Gates restantes

- suíte Python: 396 testes verdes; mypy dos arquivos alterados e ruff `src/`/`apps/` verdes;
- Android: unit tests, lint e assemble verdes; instalar/testar no aparelho conectado;
- Admin: `npm ci`, typecheck, lint e build verdes (aviso não fatal de lockfile externo);
- aplicar migrações 0008–0010 com backup nomeado, fazer commit/push, aguardar CI;
- publicar por SHA, executar smoke autenticado, testar no navegador e no Android;
- registrar checksum do APK, SHA de produção e rollback.
