# Registro de execução G05 — 2026-09-09

## Escopo

Implementação do teste RGB físico por dispositivo no backend, sem alterar a
sequência RGB real da sessão e sem implementar Vídeo, clipe, prévia ou BIN
Diagnostic.

## Entregas

- DTO manual com RGB/hex, brilho, tempos, repetição e limite de 120 s.
- Serviço transacional para `rgb_device_commands` e
  `rgb_device_command_events`.
- Estados `QUEUED`, `FORWARDED`, `RECEIVED`, `APPLIED`, `OFF`, `EXPIRED`,
  `FAILED` e `CANCELLED` com timestamps e auditoria.
- STOP idempotente: a solicitação grava `CANCELLED`; `OFF` depende de evento
  físico do gateway.
- Exclusão mútua por lock da linha do dispositivo contra teste concorrente e
  sequência real ativa.
- Endpoints administrativos, polling/eventos autenticados do gateway e
  adaptador do endpoint legado para a tabela nova.
- Contrato operacional em `docs/contracts/RGB_DEVICE_COMMANDS_V1.md`.

## Validação

- Ruff focado: aprovado.
- Suíte RGB + contrato G05: 33 testes aprovados.
- Suíte completa do backend: 466 testes aprovados, 1 ignorado e 2 avisos.

## Evidência de limites

Este gate valida o contrato e o backend local. A chegada ao WS2812 físico,
aplicação de cor/brilho e desligamento seguro permanecem comprovações físicas
dos gates de Android/firmware e da missão final; código, build, publicação e
instalação não são tratados como equivalentes.
