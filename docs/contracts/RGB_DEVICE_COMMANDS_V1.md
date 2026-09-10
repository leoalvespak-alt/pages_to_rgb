# RGB Device Commands V1

Contrato do teste físico do WS2812 por dispositivo. Este contrato é exclusivo
para o firmware Production e não cria BIN Diagnostic, vídeo, clipe ou prévia.

## Comando manual

`POST /api/v1/admin/devices/{device_code}/rgb-tests` exige sessão administrativa
com CSRF e recebe:

```json
{
  "session_id": "opcional",
  "rgb": [255, 0, 0],
  "brightness_percent": 12,
  "on_ms": 3000,
  "off_ms": 5000,
  "repeat_count": 1
}
```

`rgb` ou `hex_color` (`#RRGGBB`) deve ser informado, mas não ambos. Os canais
RGB ficam em 0–255, brilho em 0–100%, `on_ms` em 100–60000, `off_ms` em
0–60000 e `repeat_count` em 1–20. A duração `(on_ms + off_ms) * repeat_count`
não pode exceder 120000 ms. Cada comando recebe um `command_id` UUID, expira
após sua duração mais uma margem de segurança e registra ator, dispositivo,
payload solicitado e payload efetivo.

## Estados e prova física

```text
QUEUED → FORWARDED → RECEIVED → APPLIED → OFF
QUEUED/FORWARDED → EXPIRED
qualquer estado ativo → FAILED
qualquer estado ativo → CANCELLED → OFF
```

O GET de polling não avança estado. `FORWARDED`, `RECEIVED`, `APPLIED` e
`OFF` somente são persistidos quando o gateway envia o evento correspondente.
O endpoint administrativo de STOP persiste `CANCELLED`; a resposta só vira
`OFF` depois do evento `OFF` confirmado pela execução local. Repetir STOP em
estado terminal ou já cancelado é idempotente.

## Gateway

O gateway autenticado consulta:

```text
GET  /api/v1/gateway/devices/{device_code}/commands?after=<cursor>
POST /api/v1/gateway/devices/{device_code}/commands/{command_id}/events
```

`after` e `cursor` são milissegundos UTC derivados de `queued_at`; o servidor
retorna comandos ainda em voo posteriores ao cursor e não marca entrega no
GET. O POST de evento exige `Authorization`, `X-Gateway-Id` e
`Idempotency-Key`. Repetição da mesma chave com o mesmo payload retorna a
mesma aceitação; reutilização com payload diferente é rejeitada.

## Exclusão mútua e sequência real

O backend bloqueia a linha do dispositivo antes de avaliar concorrência. Uma
sequência RGB real em `READY`, `RECEIVED` ou `PLAYING` rejeita o teste manual,
e outro teste manual em `QUEUED`, `FORWARDED`, `RECEIVED`, `APPLIED` ou
`CANCELLED` também é rejeitado. O teste manual nunca altera o snapshot da
sessão nem a sequência real.

Para a sequência real, os tempos permanecem explícitos:

```text
periodo_total_ms = on_ms + off_ms
frequencia_aproximada_hz = 1000 / periodo_total_ms
```

Não existe campo `speed` neste contrato.
