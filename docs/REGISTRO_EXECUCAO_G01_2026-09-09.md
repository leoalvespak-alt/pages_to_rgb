# G01 — persistência de câmera RGB e comandos físicos

Data: 2026-09-09

## Resultado

- A cabeça encontrada na instância PostgreSQL documentada era `0003`.
- As migrações intermediárias `0004`–`0012` e a nova `0013` foram aplicadas
  com sucesso; a cabeça final ficou em `0013`.
- A migração `0013` é aditiva e mantém o modelo legado `RgbTestCommand`.
- O banco vazio foi exercitado antes da inserção de uma cadeia representativa
  de dispositivo, gateway, sessão, captura e frame.
- O downgrade `0013 -> 0012` preservou essa cadeia legada; o re-upgrade para
  `0013` restaurou as colunas, tabelas, índices e constraints novas.
- A verificação live confirmou todos os índices de idempotência e constraints
  de integridade previstos.

## Downgrade lógico e rollback de aplicação

O rollback normal da aplicação deve manter o banco em `0013`; ele consiste em
retornar o código para a versão anterior compatível sem executar downgrade de
schema. O downgrade de banco é uma operação controlada de exceção:

```text
alembic downgrade 0012
```

Esse comando remove somente os objetos introduzidos por `0013` — perfis,
comandos/eventos RGB e os campos/índices S03 — e não remove tabelas ou dados
legados. Antes de usá-lo, exportar os dados S03 e confirmar que a versão de
aplicação anterior não depende deles. A reversão do schema é:

```text
alembic upgrade 0013
```

O downgrade foi ensaiado no banco de validação e o re-upgrade foi concluído
com os dados legados preservados.

## Limites da release

Esta etapa não habilita Vídeo e não produz BIN Diagnostic. O firmware e seus
artefatos permanecem fora deste gate.
