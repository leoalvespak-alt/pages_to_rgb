# Plano de alinhamento do servidor com o firmware V2.2 e resultados por LED RGB

Data: 2026-08-18  
Servidor alvo: `C:\Users\Lenovo\Downloads\pagestoaudio_servidor`  
Firmware de referência: `C:\Users\Lenovo\Downloads\Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1`  
Versão do firmware: `2.2.0-n16r8-rgb-results`

## 1. Objetivo

Executar todas as alterações necessárias no backend para que o resultado final da prova possa ser entregue ao ESP32-S3, por intermédio do Android Gateway, como uma sequência persistente e versionada de respostas `A` a `E` exibida pelo WS2812.

Ao concluir este plano, o servidor deverá:

- informar ao Android se o resultado ainda não começou, está em processamento, está pronto ou foi cancelado;
- gerar uma sequência RGB somente a partir de `FinalAnswer.validated=true`;
- publicar payload compatível com `schema_version: 1` do firmware;
- calcular exatamente o mesmo SHA-256 binário calculado pelo ESP32;
- manter revisão, cursor e payload imutáveis depois da publicação;
- aceitar eventos `RECEIVED`, `STARTED`, `RESUMED`, `COMPLETED` e `INVALID`;
- tratar reenvios e especialmente `COMPLETED` de maneira idempotente;
- sobreviver a reinícios, concorrência, retries do Android e retries do firmware;
- preservar o fluxo de áudio existente: entrega RGB é um canal adicional e não substitui o MP3.

## 2. Fontes de verdade obrigatórias

Antes de editar código, ler integralmente:

1. `CLAUDE.md` do servidor, em especial as regras de migration, idempotência, testes e proibição de fallbacks silenciosos.
2. `IMPLEMENTATION_PLAN.md` e `Pages_to_Audio_Resposta_IMPLEMENTATION_PLAN.md`.
3. No firmware:
   - `docs/ANDROID_GATEWAY_CONTRACT.md`;
   - `main/gateway_client.c` e `main/gateway_client.h`;
   - `main/rgb_sequence_service.c` e `main/rgb_sequence_store.h`;
   - `main/led_service.c` e `main/led_service.h`;
   - `firmware_manifest.json`.

Em caso de divergência, o contrato V2.2 e o código compilado do firmware têm precedência para a comunicação com o dispositivo. Mudanças incompatíveis exigem uma nova versão de schema; não alterar silenciosamente o schema 1.

## 3. Limite arquitetural

Manter o desenho existente:

```text
ESP32-S3  <── HTTP local /v1/device/* ──>  Android Gateway
Android   <── HTTPS /api/v1/gateway/* ──>  Servidor/VPS
```

O servidor não deve fazer o ESP32 acessar diretamente a VPS. O Android continua responsável por:

- autenticar o dispositivo na rede local;
- implementar os endpoints locais `/v1/device/*` consumidos pelo firmware;
- consultar o servidor autenticado por `Authorization: Bearer ...` e `X-Gateway-Id`;
- encaminhar ao firmware o status, o payload RGB e os ACKs recebidos do servidor;
- manter fila local durável quando a internet móvel estiver indisponível.

O servidor deve expor respostas fáceis de encaminhar sem transformação ambígua.

## 4. Lacunas atuais verificadas

O código atual possui o router `apps/api/routers/gateway.py`, autenticação de gateway, modelos de `Device`, `Session`, `Question` e `FinalAnswer`, mas ainda não possui:

- modelos persistentes para publicação e entrega de sequência RGB;
- endpoints do servidor para status de resultado, download da sequência e eventos RGB;
- serialização canônica compartilhada com o firmware;
- vínculo entre conclusão do Gate 2 e publicação da sequência;
- testes de contrato para o fluxo V2.2;
- simulação do polling/ACK RGB no `scripts/simulate_android.py`.

O router atual ainda contém respostas provisórias e uso de `FakeStorageAdapter`; não expandir esses atalhos para a implementação RGB. A nova funcionalidade deve usar banco e Unit of Work reais.

## 5. Decisões normativas

### 5.1 Semântica das respostas

Gerar a sequência pela ordem crescente de `Question.question_number`.

Uma sequência só pode ficar pronta quando houver exatamente uma resposta validada para cada questão esperada, com numeração contígua de `1` até `Session.expected_questions`, e cada resposta for uma letra maiúscula entre `A` e `E`.

Motivo: o schema do firmware transmite somente a string de letras e não possui marcador para questão ausente. Enviar uma lista parcial deslocaria todas as respostas seguintes e produziria um resultado visual ambíguo.

Se Gate 2 terminar com conjunto parcial, lacunas, duplicatas, questão `FAILED`, resposta fora de `A` a `E` ou quantidade acima de 1000:

- não publicar sequência;
- marcar a entrega RGB como cancelada;
- retornar `RESULT_CANCELLED` ao Android;
- registrar `AuditEvent` com motivo explícito, sem afetar silenciosamente a política de áudio já existente.

### 5.2 Mapeamento de estado para comando

O serviço de resultado deve produzir exatamente um destes comandos:

| Situação persistida | Comando para o firmware |
|---|---|
| sessão encerrada para captura, mas processamento ainda não iniciado | `RESULT_NOT_STARTED` |
| OCR/reconstrução/RAG/solver/verificação/arbitragem/Gate 2 em andamento | `RESULT_PROCESSING` |
| sequência publicada e válida | `RGB_SEQUENCE_READY` |
| sessão cancelada/falha fatal/Gate bloqueado/conjunto RGB incompleto ou inválido | `RESULT_CANCELLED` |

Não criar estados RGB dentro de `SessionState`. O estado de processamento da prova e o estado de entrega ao dispositivo são responsabilidades diferentes.

### 5.3 Cursor

- Manter cursor monotônico por sessão em registro persistente de entrega.
- Incrementar o cursor somente quando o comando visível ao dispositivo mudar ou uma nova revisão for publicada.
- Se o cursor enviado pelo Android estiver atualizado, o servidor pode retornar `204 No Content`.
- Nunca diminuir ou reutilizar cursor para conteúdo diferente.

### 5.4 Revisão e imutabilidade

- A primeira publicação usa `revision=1`.
- Payload publicado é imutável.
- Mesmos dados lógicos devem reutilizar a mesma sequência, revisão e hash.
- Alteração real cria nova revisão e novo `sequence_id`, marcando a anterior como `SUPERSEDED`.
- `sequence_id` deve ser URL-safe, não vazio e ter no máximo 64 caracteres. Preferência: `rgb-` seguido de UUID sem hífens.
- Uma sequência inválida relatada pelo dispositivo não deve ser corrigida no mesmo registro.

### 5.5 LED

O servidor não envia comandos diretos para ligar/desligar o LED de status. Ele controla o comportamento apenas por:

- comandos de resultado (`RESULT_*`);
- sequência de respostas;
- paleta, brilho e tempos da sequência.

Os sinais visuais de início, retomada, conclusão, processamento e cancelamento são implementados pelo firmware.

## 6. Contrato servidor ↔ Android

Adicionar endpoints autenticados no namespace existente `/api/v1/gateway`.

### 6.1 Consultar resultado

```http
GET /api/v1/gateway/session/{session_id}/result?device_id=CAM-001&cursor=12
Authorization: Bearer <gateway-token>
X-Gateway-Id: <gateway-id>
```

Retornar `204` se não houver atualização. Caso contrário, usar o mesmo shape que o Android encaminhará ao endpoint local `/v1/device/command?...&phase=RESULT_WAIT`.

Exemplos:

```json
{
  "command": "RESULT_PROCESSING",
  "cursor": 13,
  "session_id": "S-..."
}
```

```json
{
  "command": "RGB_SEQUENCE_READY",
  "cursor": 14,
  "session_id": "S-...",
  "sequence_id": "rgb-0123456789abcdef0123456789abcdef",
  "revision": 1,
  "item_count": 70,
  "sha256": "<64 caracteres hexadecimais minúsculos>"
}
```

Validar que `device_id`, gateway autenticado e sessão estão vinculados. Não confiar apenas nos identificadores fornecidos pela URL/query.

### 6.2 Baixar sequência

```http
GET /api/v1/gateway/session/{session_id}/rgb-sequence?device_id=CAM-001&sequence_id=rgb-...
```

Resposta schema 1:

```json
{
  "schema_version": 1,
  "session_id": "S-...",
  "sequence_id": "rgb-...",
  "revision": 1,
  "item_count": 5,
  "sha256": "6f2f655b4ea2ee02ee009a938cc95515f6ff38309b3b2ddcb0594057a5151f17",
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

Restrições obrigatórias:

- JSON máximo: 262144 bytes;
- `item_count`: 1 a 1000 e igual a `len(answers)`;
- respostas: somente `A` a `E`;
- RGB: 0 a 255;
- brilho: 0 a 100;
- `on_ms`: 100 a 60000;
- `off_ms`: 0 a 60000;
- índice de override: base zero, dentro da sequência e sem duplicatas;
- SHA dentro do payload deve ser idêntico ao anunciado no resultado.

### 6.3 Eventos

```http
POST /api/v1/gateway/session/{session_id}/rgb-sequence/event
Idempotency-Key: <uuid>
Content-Type: application/json
```

Body compatível com o firmware:

```json
{
  "device_id": "CAM-001",
  "session_id": "S-...",
  "sequence_id": "rgb-...",
  "revision": 1,
  "event": "COMPLETED",
  "next_index": 70,
  "item_count": 70
}
```

Eventos aceitos: `RECEIVED`, `STARTED`, `RESUMED`, `COMPLETED`, `INVALID`.

Regras:

- validar associação gateway/dispositivo/sessão/sequência/revisão;
- validar `0 <= next_index <= item_count`;
- rejeitar `item_count` diferente da sequência;
- impedir regressão de `next_index`;
- exigir `next_index == item_count` para `COMPLETED`;
- `COMPLETED` repetido deve retornar sucesso e a mesma representação lógica;
- idempotência mínima de `COMPLETED`: `device_id + session_id + sequence_id + revision + event`;
- processar evento e `AuditEvent` na mesma transação;
- usar lock de linha para impedir corridas entre dois reenvios;
- `INVALID` deve gerar alerta/auditoria e impedir nova entrega da revisão inválida.

## 7. Hash canônico obrigatório

O SHA-256 não é calculado sobre o JSON. Resolver defaults, paleta e overrides e concatenar cada item em 13 bytes:

```text
answer:              uint8 ASCII
r:                   uint8
g:                   uint8
b:                   uint8
brightness_percent:  uint8
on_ms:               uint32 little-endian
off_ms:              uint32 little-endian
```

Em Python, a operação equivalente é:

```python
struct.pack("<BBBBBII", ord(answer), r, g, b, brightness, on_ms, off_ms)
```

Vetores dourados que os testes devem preservar:

```text
A, RGB 255/255/255, brilho 12, on 3000, off 5000
bytes = 41ffffff0cb80b000088130000
sha256 = 8a2b2c9188f7e8be635244c53d5b4aad52c595407ef35f7e96b2471a310ad893

ABCDE com a paleta padrão e os mesmos defaults
payload_size = 65 bytes
sha256 = 6f2f655b4ea2ee02ee009a938cc95515f6ff38309b3b2ddcb0594057a5151f17
```

Não depender da serialização JSON, ordenação de chaves ou arquitetura nativa da CPU para gerar o hash.

## 8. Persistência e migration

Criar uma migration Alembic nova, posterior a `0002_rag_vector_fts.py`. Nunca editar migrations existentes.

### 8.1 `session_result_deliveries`

Registro um-para-um por sessão:

- `id UUID PK`;
- `session_id UUID FK UNIQUE NOT NULL`;
- `device_id UUID FK NOT NULL`;
- `gateway_id UUID FK NOT NULL`;
- `command TEXT NOT NULL`;
- `cursor BIGINT NOT NULL DEFAULT 0`;
- `active_sequence_id UUID FK NULL`;
- `reason_code TEXT NULL`;
- `created_at`, `updated_at`.

Adicionar constraints para os comandos permitidos e cursor não negativo.

### 8.2 `rgb_sequences`

- `id UUID PK`;
- `sequence_id TEXT UNIQUE NOT NULL`;
- `session_id UUID FK NOT NULL`;
- `revision INTEGER NOT NULL`;
- `schema_version INTEGER NOT NULL DEFAULT 1`;
- `status TEXT NOT NULL` (`READY`, `RECEIVED`, `PLAYING`, `COMPLETED`, `INVALID`, `SUPERSEDED`);
- `answers TEXT NOT NULL`;
- `item_count INTEGER NOT NULL`;
- `defaults JSONB NOT NULL`;
- `palette JSONB NOT NULL`;
- `overrides JSONB NOT NULL DEFAULT []`;
- `payload_sha256 CHAR(64) NOT NULL`;
- `payload_size INTEGER NOT NULL`;
- `last_next_index INTEGER NOT NULL DEFAULT 0`;
- `created_at`, `ready_at`, `completed_at`, `updated_at`.

Constraints e índices:

- `UNIQUE(session_id, revision)`;
- item count entre 1 e 1000;
- payload size igual a `item_count * 13`;
- índices por `(session_id, status)` e `sequence_id`;
- no máximo uma sequência ativa por sessão, por índice parcial ou regra transacional equivalente.

### 8.3 `rgb_sequence_events`

- `id BIGSERIAL PK`;
- `rgb_sequence_id UUID FK NOT NULL`;
- `device_id UUID FK NOT NULL`;
- `gateway_id UUID FK NOT NULL`;
- `event TEXT NOT NULL`;
- `next_index INTEGER NOT NULL`;
- `item_count INTEGER NOT NULL`;
- `idempotency_key TEXT NULL`;
- `event_identity TEXT NOT NULL UNIQUE`;
- `payload JSONB NOT NULL`;
- `received_at TIMESTAMPTZ NOT NULL`.

`event_identity` deve ser calculada de forma determinística. Para `COMPLETED`, não incluir campos voláteis.

Criar os modelos em `src/pages_to_audio/db/models/` e registrá-los em `src/pages_to_audio/db/models/__init__.py`.

## 9. Serviços de domínio

Criar pacote `src/pages_to_audio/rgb/` com responsabilidades separadas:

- `schemas.py`: enums e modelos Pydantic estritos do schema 1;
- `canonical.py`: resolução dos itens, packing little-endian e SHA-256;
- `policy.py`: defaults, paleta e validação de conjunto completo de respostas;
- `publisher.py`: coleta ordenada de respostas, criação/reutilização de revisão e publicação atômica;
- `delivery.py`: mapeamento de estado, cursor, download e processamento de eventos.

Requisitos:

- funções públicas completamente tipadas;
- nenhuma chamada externa sem timeout/retry explícitos;
- nenhuma gravação fora de Unit of Work;
- logging estruturado sem respostas completas quando isso aumentar exposição desnecessária;
- nenhuma exceção de validação transformada em fallback silencioso;
- respostas e payloads retornados devem ser construídos a partir da linha persistida, não recalculados de forma divergente em cada request.

## 10. Integração com o workflow

Integrar a publicação depois que Gate 2 tiver resultado definitivo e as `FinalAnswer` validadas estiverem persistidas.

Ordem transacional/lógica:

1. carregar sessão e respostas finais ordenadas;
2. avaliar se o conjunto RGB é completo e representável;
3. se válido, gerar/reutilizar sequência e atualizar entrega para `RGB_SEQUENCE_READY`;
4. se inválido ou incompleto, atualizar entrega para `RESULT_CANCELLED` com reason code;
5. registrar auditoria;
6. permitir que o fluxo de áudio continue conforme as regras existentes.

Não manter o workflow Temporal aberto esperando `COMPLETED` do dispositivo. O ACK RGB é assíncrono e pode chegar muito depois da conclusão do processamento.

Enquanto o workflow estiver ativo, atualizar a entrega para `RESULT_PROCESSING`. Quando a captura tiver terminado mas o workflow ainda não tiver começado, usar `RESULT_NOT_STARTED`.

Se o projeto ainda estiver usando activities fake para essa parte, implementar primeiro a activity real de publicação RGB e seus testes; não fazer a feature depender de retorno fake.

## 11. API e dependências

### 11.1 Arquivos esperados

- ajustar `apps/api/dependencies.py` para fornecer Unit of Work/sessão assíncrona com rollback/close corretos;
- criar `apps/api/schemas/rgb.py` ou manter os schemas no pacote de domínio com importação limpa;
- preferencialmente criar `apps/api/routers/gateway_rgb.py` e registrá-lo em `apps/api/main.py`;
- manter `apps/api/routers/gateway.py` para os endpoints já existentes, evitando um arquivo monolítico;
- reutilizar `verify_gateway_token` e validar os vínculos no banco.

### 11.2 Códigos HTTP

- `200`: leitura/evento aceito ou duplicata idempotente;
- `204`: cursor sem atualização;
- `400/422`: payload incompatível com schema/limites;
- `401`: gateway não autenticado;
- `403`: gateway/dispositivo não vinculado à sessão;
- `404`: sessão ou sequência inexistente para aquele vínculo;
- `409`: revisão, item count, sequência, cursor ou idempotency key conflitante;
- `410`: revisão superseded/invalid quando requisitada diretamente.

Não vazar a existência de sessões de outro gateway em mensagens de erro.

## 12. Configuração

Adicionar a `AppSettings` e `.env.example`, com validação de faixa:

```text
RGB_RESULTS_ENABLED=true
RGB_SEQUENCE_SCHEMA_VERSION=1
RGB_SEQUENCE_MAX_ITEMS=1000
RGB_SEQUENCE_MAX_JSON_BYTES=262144
RGB_DEFAULT_BRIGHTNESS_PERCENT=12
RGB_DEFAULT_ON_MS=3000
RGB_DEFAULT_OFF_MS=5000
```

Manter a paleta padrão versionada em código, exatamente igual à do firmware. Se futuramente a paleta for configurável, a configuração deve ser validada e persistida no snapshot da sequência.

## 13. Simulador Android

Estender `scripts/simulate_android.py` com um modo de resultado RGB:

- consultar status usando cursor;
- tratar `204`;
- baixar o JSON quando receber `RGB_SEQUENCE_READY`;
- validar metadados, limites e SHA canônico;
- enviar `RECEIVED`, `STARTED` e `COMPLETED`;
- reenviar `COMPLETED` para comprovar idempotência;
- simular retomada com `RESUMED` e `next_index > 0`;
- simular evento inválido, hash divergente, item count divergente e gateway não vinculado;
- permitir falha de rede simulada sem usar sleeps arbitrários como sincronização.

O simulador representa Android ↔ servidor. Um teste de contrato separado deve representar Android local ↔ firmware.

## 14. Testes obrigatórios

### 14.1 Unitários

Criar `tests/unit/rgb/` com, no mínimo:

- packing e os dois vetores dourados deste plano;
- respostas `A` a `E`, limites RGB/brilho/tempos e tamanho máximo;
- aplicação de defaults, paleta e overrides;
- rejeição de override duplicado ou fora de faixa;
- ordenação por `question_number`;
- rejeição de lacunas, duplicatas, respostas não validadas e letras inválidas;
- geração idempotente da mesma revisão;
- nova revisão quando o payload muda;
- mapeamento de todos os estados da sessão para `RESULT_*`;
- cursor monotônico;
- transições e monotonicidade de `next_index`;
- `COMPLETED` repetido sem efeito duplicado;
- `INVALID` bloqueando a revisão.

### 14.2 API

Criar testes em `tests/unit/api/` ou `tests/integration/api/` para:

- autenticação e vínculo gateway/dispositivo/sessão;
- `204` com cursor atual;
- quatro comandos de resultado;
- payload pronto com campos exatos;
- download com JSON abaixo de 256 KiB;
- todos os eventos e conflitos;
- reenvio idempotente de `COMPLETED`;
- isolamento entre gateways.

### 14.3 Banco e concorrência

- migration `upgrade` e `downgrade` em banco limpo;
- upgrade a partir de `0002` com dados existentes;
- constraints de revisão/item count/hash;
- duas requisições concorrentes de publicação não criam duas revisões iguais;
- dois `COMPLETED` concorrentes geram um único efeito lógico.

### 14.4 Contrato de firmware

Manter fixtures JSON exatamente compatíveis com `rgb_sequence_service_store_json()` e `parse_command_response()` do firmware.

Se houver toolchain ESP-IDF disponível durante a execução, adicionar uma verificação cruzada que produza o mesmo hash do firmware. Não exigir hardware físico para os testes unitários.

## 15. Observabilidade e auditoria

Adicionar eventos estruturados, sem segredos:

- `rgb_result_status_changed`;
- `rgb_sequence_published`;
- `rgb_sequence_downloaded`;
- `rgb_sequence_event_received`;
- `rgb_sequence_completed`;
- `rgb_sequence_invalid`;
- `rgb_sequence_cancelled`.

Métricas recomendadas:

- tempo de Gate 2 até publicação;
- tempo de publicação até `RECEIVED`;
- tempo de `STARTED` até `COMPLETED`;
- retries por evento;
- sequências inválidas/canceladas;
- sessões prontas sem ACK após janela operacional configurável.

Não registrar token, HMAC, reasoning privado ou conteúdo integral da prova.

## 16. Documentação a atualizar

- `README.md`: novo canal RGB e fluxo Android;
- `Pages_to_Audio_Resposta_IMPLEMENTATION_PLAN.md`: adicionar extensão V2.2 sem apagar decisões existentes;
- `CODEX_EXECUTION_PLAN.md`: registrar passos operacionais implementados;
- `docs/progress/PHASE_STATUS.md`: status real, sem marcar concluído antes dos testes;
- criar `docs/contracts/RGB_RESULT_V1.md` com os contratos deste plano;
- criar ADR sobre sequência RGB completa, imutabilidade de revisão e hash canônico.

Se `IMPLEMENTATION_PLAN.md` continuar sendo apenas ponte para o documento principal, não duplicar conteúdo divergente nele.

## 17. Ordem de execução para o Codex

1. Executar `git status` restrito ao projeto e preservar alterações do usuário.
2. Rodar baseline de testes, lint e typecheck; registrar falhas preexistentes separadamente.
3. Implementar schemas, policy e canonicalização com testes unitários primeiro.
4. Criar modelos e migration nova.
5. Implementar publisher e delivery com Unit of Work.
6. Integrar ao workflow/Gate 2.
7. Implementar endpoints autenticados.
8. Estender simulador Android.
9. Adicionar testes de API, integração, concorrência e contrato.
10. Atualizar documentação.
11. Rodar migration, suíte completa, lint e typecheck.
12. Revisar diff, garantir que migrations antigas não mudaram e entregar relatório final.

## 18. Comandos finais de validação

Usar os comandos do projeto e o ambiente virtual existente:

```bash
make lint
make typecheck
make test-unit
make test
make migrate
```

Quando `make` não estiver disponível no Windows, executar os equivalentes:

```powershell
uv run ruff check src/ apps/ tests/ scripts/
uv run ruff format --check src/ apps/ tests/ scripts/
uv run mypy src/pages_to_audio
uv run pytest tests/unit/
uv run pytest tests/ --cov=src/pages_to_audio --cov-report=term-missing
uv run alembic upgrade head
```

Validar também o simulador no fluxo feliz, retry de `COMPLETED`, retomada e payload inválido.

## 19. Critérios de aceite

O plano estará concluído somente quando:

- o servidor persistir e publicar sequência completa `A` a `E` compatível com schema 1;
- os vetores dourados produzirem os hashes exatos documentados;
- o Android puder obter e encaminhar os quatro comandos esperados pelo firmware;
- payload e metadados coincidirem em sessão, sequência, revisão, quantidade e SHA;
- `COMPLETED` repetido ou concorrente não duplicar efeitos;
- reboot/retry do dispositivo não causar nova revisão nem repetição lógica no servidor;
- sequência parcial ou ambígua nunca for apresentada como pronta;
- fluxo de áudio continuar funcional e desacoplado do ACK RGB;
- migrations antigas permanecerem intactas;
- migration nova, testes, lint e typecheck passarem;
- documentação refletir o contrato implementado;
- nenhuma credencial ou dado sensível entrar no repositório.

## 20. Fora de escopo deste repositório

- alterar o firmware já compilado V2.2;
- implementar a interface local do Android Gateway;
- controlar o WS2812 diretamente pela VPS;
- aguardar ACK do LED para concluir o workflow principal;
- suportar respostas fora de `A` a `E` no schema 1;
- suportar sequência esparsa sem criar antes um schema de protocolo novo.
