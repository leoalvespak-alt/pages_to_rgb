# Registro de execução G06 — 2026-09-09

## Escopo

Bridge Android durável para comandos RGB físicos Production, eventos da ESP,
cursor cloud, outbox, retomada por WorkManager/Room e execução independente da
tela. Vídeo e BIN Diagnostic não fazem parte deste gate.

## Implementação registrada

- DTOs Retrofit para página de comandos por dispositivo e eventos idempotentes.
- Entidades Room `pending_rgb_commands`, `rgb_event_outbox` e
  `rgb_command_cursors`, com migração 3→4.
- Cursor avançado somente após inserção transacional da página.
- Deduplicação por `command_id` sem sobrescrever estado local.
- Eventos locais persistidos antes do ACK ao ESP e reenviados até aceite cloud.
- Validação de identidade do dispositivo, tipos/estados/expiração e transições
  locais monotônicas.
- `RgbCommandSyncWorker` com restrição de rede, backoff exponencial e fábrica
  do WorkManager; o `EspBridgeService` agenda a sincronização sem Activity.
- Rotas locais `GET /v1/device/rgb-test` e
  `POST /v1/device/rgb-test/event`, autenticadas por dispositivo.
- Spool de JPEG existente preservado: SHA/tamanho, ACK durável, deduplicação e
  retomada continuam em `PendingFrame`/`SpoolRepository`.

## Testes previstos pelo gate

- `RgbCommandDaoTest`: persistência antes do cursor, replay idempotente e
  outbox pendente até ACK.
- `RgbCommandPersistenceInstrumentedTest`: persistência Room em dispositivo.
- A execução Gradle depende de Android SDK configurado; nenhum caminho,
  credencial, keystore ou dispositivo foi inventado.

## Limitação aberta deste registro

No host executor não há Android SDK instalado nos caminhos documentados pelo
projeto, portanto os testes Android ainda não podem ser declarados aprovados.
O gate permanece em execução até que a execução JVM e a instrumentada sejam
realmente realizadas.

