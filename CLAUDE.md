# CLAUDE.md — Regras invioláveis do projeto pages-to-audio

## Regras obrigatórias (§6)

1. Nunca apagar migrations antigas.
2. Nunca alterar schema sem migration.
3. Nunca colocar segredo real no código.
4. Nunca criar fallback silencioso.
5. Nunca marcar questão FAILED como respondida.
6. Nunca iniciar Solver antes do Gate 1.
7. Nunca gerar áudio se Gate 2 < minimum_ratio.
8. Nunca sobrescrever imagem ORIGINAL.
9. Toda chamada externa deve ter timeout explícito.
10. Toda chamada externa deve possuir retry policy explícita.
11. Toda operação mutável deve ser idempotente.
12. Toda nova feature precisa de testes.
13. Não usar sleeps arbitrários para sincronização.
14. Não usar regex para extrair resposta final de LLM.
15. LLM deve usar schema estruturado validado por Pydantic.
16. Não registrar API keys, tokens ou conteúdo de reasoning privado.
17. Não armazenar imagens permanentemente no disco local.
18. Não aumentar concurrency sem teste de recursos.
19. O servidor deve continuar funcionando se PaddleOCR estiver desabilitado.
20. Claude Opus 5 é primary; DeepSeek V4 Pro é fallback.

## Operacional

- Fonte de verdade arquitetural: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)
- Plano de execução operacional: [CODEX_EXECUTION_PLAN.md](CODEX_EXECUTION_PLAN.md)

### Comandos do Makefile (§54)

```bash
make install        # Instala dependências com uv
make dev            # Inicia API em modo dev
make test           # Roda todos os testes
make test-unit      # Apenas testes unitários
make test-integration # Testes de integração (requer banco)
make lint           # ruff check + ruff format
make typecheck      # mypy --strict
make migrate        # Aplica migrations pendentes
make migration name="..." # Cria nova migration Alembic
make api            # Sobe o servidor FastAPI
make worker         # Sobe o worker Temporal
make admin          # Build do painel React
make simulator      # Executa o simulador Android
make e2e            # Testes end-to-end
make benchmark      # Benchmark de providers
```

### Regra de migrations (§47)

> Toda alteração de schema exige migration Alembic nova; migration aplicada é imutável.
> Correções sempre em migration nova — nunca editar migration existente.
