# Android Gateway Bridge V1

Contrato do caminho durável entre a API, o Android Gateway e a ESP32
Production. Este contrato não habilita Vídeo, BIN Diagnostic ou qualquer
fallback de captura por tela.

## Topologia e identidade

- A ESP32 fala somente com o Android local.
- O Android fala com a API por HTTPS usando a identidade provisionada do
  gateway; nenhum token cloud é gravado no firmware.
- O trecho local de produção exige TLS e confiança provisionada. O servidor
  HTTP legado em `8787` permanece apenas para bancada/compatibilidade e não é
  aceito como evidência de publicação de produção.
- Toda requisição local carrega `X-Device-Id` e `Authorization: Bearer
  <device-secret>`. O Android valida o par dispositivo/segredo; não cria
  segredo em nome do operador.

## Comandos RGB físicos

O Android consulta a API por:

```text
GET /api/v1/gateway/devices/{device_id}/commands?after=<cursor>
```

O cursor só é avançado na mesma transação Room que insere os comandos. A
chave primária é `command_id`; replay não sobrescreve estado físico já
observado.

O ESP consulta o Android em `GET /v1/device/rgb-test?device_id=...`. A leitura
não consome o comando. O Android confirma um evento somente depois de
persisti-lo no `rgb_event_outbox`:

```text
POST /v1/device/rgb-test/event
```

Eventos aceitos são `FORWARDED`, `RECEIVED`, `APPLIED`, `OFF`, `FAILED`,
`CANCELLED` e `EXPIRED`. A transição local é monotônica; `OFF` só encerra
depois do evento físico. O outbox é reenviado com `Idempotency-Key` e só é
marcado como enviado após aceite HTTP do backend.

## Retomada

Room e WorkManager recuperam cursor, comandos e outbox depois de processo
encerrado, perda de rede ou reinicialização. O bridge é iniciado pelo
`EspBridgeService` em foreground e não depende de Activity visível.

## Imagens

JPEG é gravado no spool antes do ACK local à ESP. O registro mantém SHA-256,
tamanho, sessão, captura e índice; o arquivo só é removido depois do ACK
remoto persistido. A qualidade Android e a qualidade JPEG da ESP são campos
independentes.

