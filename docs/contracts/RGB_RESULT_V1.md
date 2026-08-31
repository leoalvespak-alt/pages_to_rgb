# Contrato de resultado RGB V1

Este contrato é o formato entregue pelo servidor ao Android Gateway para ser encaminhado ao firmware ESP32-S3 V2.2.

O servidor usa `/api/v1/gateway/session/{session_id}/result`, `/rgb-sequence` e `/rgb-sequence/event`. O Android converte esses recursos para os endpoints locais `/v1/device/command`, `/v1/device/rgb-sequence` e `/v1/device/rgb-sequence/event`.

## Comandos

- `RESULT_NOT_STARTED`
- `RESULT_PROCESSING`
- `RGB_SEQUENCE_READY`
- `RESULT_CANCELLED`

Uma resposta pronta contém `cursor`, `session_id`, `sequence_id`, `revision`, `item_count` e `sha256`.

## Payload

```json
{
  "schema_version": 1,
  "session_id": "S-...",
  "sequence_id": "rgb-...",
  "revision": 1,
  "item_count": 5,
  "sha256": "<64 hex lowercase>",
  "answers": "ABCDE",
  "defaults": {
    "brightness_percent": 12,
    "on_ms": 3000,
    "off_ms": 5000
  },
  "palette": {
    "A": {"rgb": [255, 255, 255]},
    "B": {"rgb": [255, 255, 0]},
    "C": {"rgb": [0, 255, 255]},
    "D": {"rgb": [0, 0, 255]},
    "E": {"rgb": [255, 0, 0]}
  },
  "overrides": []
}
```

O servidor só publica uma sequência quando existe uma resposta validada para cada questão esperada, em ordem contígua, e cada letra está entre `A` e `E`. O firmware não tem marcador para uma questão ausente.

## Simulador Android

Com o servidor configurado, o fluxo normal pode ser exercitado com:

```bash
uv run python scripts/simulate_android.py --rgb-session-id S-... --rgb-device-id CAM-001
```

Os cenários `--rgb-mode` disponíveis são `normal`, `invalid-event`, `invalid-hash`, `invalid-item-count`, `unlinked-gateway` e `network-failure`. O último usa timeout explícito e não depende de `sleep` para sincronização.

## Hash

O hash é calculado sobre os itens resolvidos, não sobre o JSON. Cada item tem 13 bytes:

```python
struct.pack("<BBBBBII", ord(answer), r, g, b, brightness_percent, on_ms, off_ms)
```

`on_ms` e `off_ms` são little-endian. O hash de `ABCDE` com a paleta/defaults acima é:

```text
6f2f655b4ea2ee02ee009a938cc95515f6ff38309b3b2ddcb0594057a5151f17
```

## Eventos

Eventos aceitos: `RECEIVED`, `STARTED`, `RESUMED`, `COMPLETED` e `INVALID`.

`COMPLETED` exige `next_index == item_count` e é idempotente por dispositivo, sessão, sequência, revisão e evento. O servidor rejeita regressão de progresso e registra auditoria de cada evento aceito.
