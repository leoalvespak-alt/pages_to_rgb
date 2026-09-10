# Plano mestre de implementação e entrada em produção — câmera OCR, RGB físico, backend, Android e firmware

Data de elaboração: 2026-09-09  
Revisão de eficiência: 2026-09-09  
Estado: execução em andamento; oito gates preservados como concluídos e seis gates restantes  
Escopo: servidor/backend, painel administrativo, aplicativo Android Gateway e firmware ESP32-S3-CAM  
Resultado terminal: backend publicado em produção, APK release instalado, firmware Production compilado e instalado na ESP32 física, integração ponta a ponta validada e documentação atualizada

---

## 0. Instrução para o chat executor

Este documento é uma especificação de execução, não um relatório resumido. O chat responsável pela execução deve trabalhar até que todos os gates aplicáveis estejam comprovados por evidências reais.

O executor deve:

1. Ler esta instrução, os requisitos não negociáveis, o gate ativo e os critérios finais. Consultar contratos, inventário e apêndices somente quando forem relevantes à alteração.
2. Ler `AGENTS.md`, `C:\Users\Lenovo\.codex\RTK.md` e as instruções locais dos dois projetos.
3. Usar `rtk` como prefixo de todos os comandos de shell.
4. Preservar modificações preexistentes do usuário.
5. Não usar `git reset --hard`, `git clean`, force push ou checkout destrutivo.
6. Não inventar remote, branch, servidor, credencial, porta COM, keystore, secret ou aprovação de produção.
7. Não considerar uma etapa concluída apenas porque o código foi escrito. Cada gate usa o nível de validação definido na escada de confiança da seção 11.
8. Não gerar nem distribuir uma BIN de diagnóstico. Haverá somente firmware `Production`, com funções de teste protegidas em runtime.
9. Não implementar modo Vídeo, streaming contínuo, clipe ou prévia em movimento nesta entrega.
10. Não encerrar a execução após builds locais. O resultado terminal exige deploy, instalação e validação física.
11. Quando uma dependência externa real impedir avanço — remote do firmware, keystore, telefone, cabo/porta COM, acesso ao VPS ou aprovação de merge — registrar o bloqueio com a evidência exata e pedir somente a informação indispensável ao usuário.
12. Registrar evidências durante cada gate e consolidar a documentação em `G24`, reaproveitando commits, hashes, logs e relatórios já identificados.

### 0.1 Estados permitidos por item

Usar somente estes estados nos registros de execução:

- `PENDENTE`: ainda não iniciado.
- `EM_EXECUCAO`: alteração ou validação em curso.
- `IMPLEMENTADO`: código concluído, mas ainda não validado por todos os testes do gate.
- `VALIDADO_LOCAL`: testes automatizados e builds locais aprovados.
- `VALIDADO_FISICO`: comportamento comprovado na ESP/telefone reais.
- `PUBLICADO`: artefato exato instalado no destino final.
- `VALIDADO_PRODUCAO`: smoke test e observação pós-publicação aprovados.
- `BLOQUEADO`: dependência externa objetiva ausente, com evidência registrada.

Não usar “pronto” ou “concluído” sem informar commit, artefato, destino e evidência.

### 0.2 Regra terminal

Este plano somente termina quando estiverem registrados:

- commit e PR/merge do servidor/Android;
- digest das imagens de API, worker e painel implantadas;
- migration head aplicada no banco de produção;
- `versionName`, `versionCode` e SHA-256 do APK release instalado;
- versão, commit e SHA-256 da BIN Production instalada;
- identidade do telefone e da ESP de produção/piloto;
- teste real do WS2812 físico no GPIO 48;
- captura real OCR em UXGA com upload e OCR concluídos;
- hash do JPEG original preservado de ponta a ponta;
- ausência de `FB-OVF`, `DMA overflow`, corrupção e watchdog/reset na campanha de aceite;
- runbooks, contratos, matriz de compatibilidade, release notes e rollback atualizados.

---

## 1. Projetos, caminhos e estado Git de partida

### 1.1 Caminhos reais confirmados

Firmware:

```text
C:\Users\Lenovo\Downloads\Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1
```

Servidor, painel e Android:

```text
C:\Users\Lenovo\Downloads\pagestoaudio_servidor
```

ESP-IDF:

```text
C:\esp\v6.0.2\esp-idf
```

### 1.2 Servidor/Android

Estado comprovado na elaboração deste plano:

- repositório Git real: `C:\Users\Lenovo\Downloads\pagestoaudio_servidor`;
- remote: `origin https://github.com/leoalvespak-alt/pages_to_rgb.git`;
- branch de produção: `main`;
- branch local de trabalho: `codex/conclusao-pos-reauditoria-2026-09-09`;
- HEAD local observado: `62aeb3c feat: concluir bridge ESP e diagnóstico de câmera`;
- base remota observada: `origin/main` em `be34d8a`;
- alteração local preexistente: `docs/contracts/RGB_RESULT_V1.md`;
- deploy de produção: workflow `.github/workflows/deploy-pages-rgb.yml`, disparado por `main`;
- destino operacional documentado: `/srv/pages-to-rgb/app`;
- projeto Compose: `pages-rgb`;
- arquivo de ambiente: `/srv/pages-to-rgb/config/.env.pages-rgb`;
- domínio: `https://ptr.rotadeataque.com.br`.

O executor deve reconfirmar tudo, pois o estado pode mudar entre planejamento e execução.

### 1.3 Firmware

Estado comprovado na elaboração deste plano:

- a pasta do firmware não possui `.git` próprio;
- `git rev-parse` sobe indevidamente até `C:\Users\Lenovo`;
- esse repositório pai pertence ao projeto `gazetacon` e não pode receber commits do firmware;
- nenhum remote oficial do firmware foi encontrado;
- nenhuma branch oficial do firmware foi encontrada.

Consequência: a etapa F00 deve resolver um repositório próprio antes de qualquer commit ou push de firmware. É proibido usar o repositório pai por conveniência.

### 1.4 Comandos obrigatórios de reconfirmação

No servidor:

```powershell
cd C:\Users\Lenovo\Downloads\pagestoaudio_servidor
rtk git status --short --branch
rtk git rev-parse --show-toplevel
rtk git log -5 --oneline --decorate
rtk git remote -v
rtk git branch -vv
```

No firmware:

```powershell
cd C:\Users\Lenovo\Downloads\Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1
rtk git rev-parse --show-toplevel
rtk git status --short --branch
rtk git remote -v
```

Gate `G00-A`: caminhos, diffs preexistentes, branches, HEADs e remotes registrados sem alterar arquivos.

---

## 2. Requisitos não negociáveis

### 2.1 Firmware único

- Produzir somente a variante `Production`.
- As funções de teste de câmera e RGB devem existir dentro da Production, protegidas por autenticação, seleção de dispositivo, feature flag, timeout e auditoria.
- Remover da documentação e dos scripts o fluxo oficial de BIN `Diagnostic`.
- Remover qualquer auto-start de diagnóstico.
- Não instalar, publicar ou manter uma BIN diagnóstica como artefato da release.

### 2.2 Câmera OCR

- Sensor OV2640.
- XCLK fixo em 10 MHz.
- UXGA 1600×1200.
- JPEG Quality padrão 10.
- Valores permitidos: 8, 9, 10, 11 e 12.
- Framebuffer na PSRAM.
- `fb_count=1`.
- Buffer JPEG alvo de 655.360 bytes, equivalente a 640 KiB.
- 1–3 frames por página.
- Intervalo entre frames de 180–300 ms.
- Intervalo mínimo entre páginas/disparos de 5.000 ms.
- DMA direto para PSRAM desligado inicialmente.
- JPEG original preservado byte a byte.
- Derivados de OCR armazenados separadamente.
- Janela máxima de 10 páginas pendentes.
- Ordem, retry, idempotência, hash e integridade preservados.

### 2.3 Modo Foto

- UXGA.
- JPEG Quality 12.
- `fb_count=1`.
- Brilho 0.
- Contraste 0.
- Saturação 0 inicialmente; +1 somente se teste físico justificar.
- AWB e AEC ligados.
- Lens Correction ligada após validação.
- Flash branco desligado.

### 2.4 Vídeo

- Não implementar.
- Desabilitar criação de novos comandos `VIDEO`, `CLIP`, `PREVIEW` ou streaming.
- Se enums ou dados antigos existirem, preservar compatibilidade de leitura/migração e rejeitar novas operações com erro explícito `MODE_NOT_SUPPORTED`.
- Documentar somente como possível evolução futura.

### 2.5 LEDs

- WS2812 físico integrado: GPIO 48.
- Flash branco da câmera: circuito separado, permanentemente desligado.
- RGB exibido no Android não equivale a aplicação física.
- Teste manual não pode alterar a sequência real imutável de uma sessão.
- Sequência real tem prioridade sobre teste manual.

---

## 3. Arquitetura alvo

### 3.1 Fluxo de câmera

```text
Android UI
  → API backend
  → camera_profile_revision persistida
  → snapshot imutável na sessão
  → CameraCaptureCommandV2
  → Android Gateway/outbox
  → endpoint local da ESP
  → validação do firmware
  → sensor OV2640
  → framebuffer PSRAM
  → JPEG original
  → SHA-256
  → spool emergencial ESP
  → spool durável Android, janela ≤ 10 páginas
  → upload idempotente
  → armazenamento original
  → confirmação de hash
  → derivado de pré-processamento
  → Gemini OCR
```

### 3.2 Fluxo do teste RGB físico

```text
Painel/backend
  → rgb_device_command por device_id
  → Android Gateway/outbox
  → endpoint local da ESP
  → rgb_test_service
  → led_service
  → RMT
  → WS2812 GPIO 48
  → RECEIVED/APPLIED/OFF/FAILED
  → Android outbox
  → backend/auditoria
```

### 3.3 Proprietários de durabilidade

- ESP: frame atual e spool emergencial de uma captura/bundle.
- Android: fila durável local, comandos e até 10 páginas pendentes.
- Backend: identidade global, idempotência, armazenamento confirmado, auditoria e processamento.
- Storage: JPEG original imutável e derivados separados.

### 3.4 Ordem inicial de captura e upload

Usar fluxo sequencial por página na primeira release:

1. Capturar os frames da página.
2. Persistir os originais localmente.
3. Encaminhar para o Android.
4. Confirmar persistência durável no Android.
5. Prosseguir para a próxima página respeitando 5 segundos.
6. Parar ao atingir 10 páginas pendentes.
7. Retomar após confirmações do backend/storage.

Não introduzir paralelismo de captura/upload antes de provar que não afeta PSRAM, ordem, spool, latência e integridade.

---

## 4. Contrato de câmera V2

### 4.1 Novo contrato canônico

Criar `docs/contracts/CAMERA_CONTROL_V2.md` e modelos equivalentes no backend, Android e firmware.

Exemplo de comando:

```json
{
  "schema_version": 2,
  "command_id": "uuid",
  "device_id": "uuid",
  "session_id": "uuid",
  "capture_id": "uuid",
  "page_number": 1,
  "profile_revision": 7,
  "mode": "OCR",
  "requested": {
    "frame_size": "UXGA",
    "width": 1600,
    "height": 1200,
    "esp_jpeg_quality": 10,
    "frame_count": 2,
    "intra_frame_gap_ms": 220,
    "page_interval_ms": 5000,
    "brightness": 0,
    "contrast": 1,
    "saturation": 0,
    "awb": true,
    "awb_gain": true,
    "wb_mode": "AUTO",
    "aec": true,
    "aec2": true,
    "agc": true,
    "bpc": true,
    "wpc": true,
    "raw_gamma": true,
    "lens_correction": true,
    "dcw": true,
    "hmirror": false,
    "vflip": false,
    "special_effect": "NORMAL",
    "colorbar": false
  },
  "technical": {
    "xclk_mhz": 10,
    "jpeg_buffer_bytes": 655360,
    "fb_count": 1,
    "framebuffer_location": "PSRAM",
    "psram_dma": false,
    "white_flash": "LOCKED_OFF"
  }
}
```

### 4.2 Resposta de aplicação

```json
{
  "schema_version": 2,
  "command_id": "uuid",
  "device_id": "uuid",
  "status": "APPLIED",
  "requested": {},
  "effective": {
    "frame_size": "UXGA",
    "width": 1600,
    "height": 1200,
    "esp_jpeg_quality": 10,
    "frame_count": 2,
    "xclk_mhz": 10,
    "jpeg_buffer_bytes": 655360,
    "fb_count": 1,
    "framebuffer_location": "PSRAM",
    "psram_dma": false,
    "white_flash_locked_off": true
  },
  "apply_errors": [],
  "unsupported": []
}
```

### 4.3 Validação obrigatória

- `mode`: `OCR` ou `PHOTO`.
- `esp_jpeg_quality`: inteiro em `[8, 12]`.
- `frame_count`: inteiro em `[1, 3]`.
- `intra_frame_gap_ms`: inteiro em `[180, 300]`.
- `page_interval_ms`: mínimo 5.000.
- OCR e Foto: somente UXGA nesta release.
- XCLK remoto não editável; valor efetivo 10 MHz.
- Buffer remoto não editável; valor efetivo 655.360.
- DMA remoto somente em endpoint técnico protegido e nunca como configuração comum.
- Flash deve ser rejeitado, não ignorado.
- Campo desconhecido deve gerar erro de validação ou aviso explícito, nunca sucesso silencioso.

### 4.4 Separação das escalas de qualidade

Se o Android ainda capturar imagens por CameraX, manter campos distintos:

- `android_jpeg_quality_percent`: 0–100, usado somente pelo codec Android;
- `esp_jpeg_quality`: 8–12, encaminhado sem conversão à OV2640.

Eliminar nomes ambíguos como `quality`, `jpeg_quality` ou `full_quality` quando o domínio não estiver explícito.

### 4.5 Mensagens obrigatórias para incompatibilidades

- `Sharpness — não disponível no driver OV2640 atual.`
- `Denoise — não disponível no driver OV2640 atual.`
- `Autofocus — não suportado; OV2640 depende de foco mecânico fixo.`
- `Foco manual — não existe controle eletrônico de foco neste hardware.`
- `Flash — não é controle de imagem; hardware separado e bloqueado neste projeto.`
- `PLL — não disponível na implementação local da OV2640.`
- `Vídeo — reservado para evolução futura e indisponível nesta versão.`

---

## 5. Persistência alvo

O executor deve confirmar a cabeça atual do Alembic antes de nomear a migração. Se `0012` continuar sendo a cabeça, criar `0013_camera_profiles_rgb_device_commands.py`.

### 5.1 Perfis de câmera

Tabela sugerida `camera_profile_revisions`:

- `id`;
- `public_id` UUID;
- `device_id` opcional para override por dispositivo;
- `mode`;
- `revision`;
- todos os valores solicitáveis;
- `technical_config_json`;
- `capabilities_version`;
- `created_by`;
- `created_at`;
- `superseded_at`;
- `active`.

Nunca atualizar uma revisão usada por sessão. Criar nova revisão.

### 5.2 Snapshot da sessão

Adicionar referência e snapshot imutável do perfil à sessão/captura:

- `camera_profile_revision_id`;
- `camera_profile_snapshot_json`;
- `requested_camera_config_json`;
- `effective_camera_config_json`;
- `firmware_version`;
- `capabilities_version`.

### 5.3 Telemetria de captura/frame

Persistir por captura:

- modo;
- resolução solicitada e efetiva;
- qualidade solicitada e efetiva;
- buffer configurado;
- DMA ativo/inativo;
- firmware;
- página;
- frames esperados/recebidos;
- status;
- retries;
- tempos de captura e upload;
- erros de overflow/watchdog.

Persistir por frame:

- `capture_id`;
- `page_number`;
- `frame_number`;
- `sha256`;
- `jpeg_size_bytes`;
- `jpeg_valid`;
- `psram_free_bytes`;
- `psram_largest_block_bytes`;
- `capture_duration_ms`;
- `upload_duration_ms`;
- `storage_key_original`;
- `storage_etag` ou checksum equivalente;
- `retry_count`;
- `received_at`;
- `confirmed_at`.

Criar constraint/índice de idempotência em identidade lógica mais hash. Um retry com o mesmo identificador e mesmo hash retorna o resultado anterior. O mesmo identificador com hash diferente deve falhar e gerar auditoria.

### 5.4 Comandos RGB por dispositivo

Criar `rgb_device_commands`:

- `id`;
- `command_id` UUID público e único;
- `device_id`;
- `session_id` opcional, apenas para contexto;
- `kind`: `TEST` ou `STOP`;
- RGB solicitado;
- brilho solicitado;
- `on_ms`;
- `off_ms`;
- `repeat_count`;
- `status`;
- timestamps de cada estado;
- `attempt_count`;
- `failure_reason`;
- `expires_at`;
- `created_by`.

Criar `rgb_device_command_events`:

- `command_id`;
- `device_id`;
- `event_type`;
- payload solicitado/efetivo;
- versão do firmware;
- timestamp do dispositivo;
- timestamp de recebimento;
- erro;
- chave idempotente do evento.

### 5.5 Migração e compatibilidade

- Migração somente aditiva.
- Não apagar o modelo antigo `RgbTestCommand` na primeira release.
- Criar adaptador de leitura se o painel ainda consultar comandos antigos.
- Desativar criação pelo caminho antigo após o novo fluxo ser habilitado.
- Não fazer downgrade destrutivo no rollback de aplicação.

Gate `G01`: migração aplica em banco vazio e em cópia representativa; downgrade lógico documentado; testes de integridade e índices aprovados.

---

## 6. Matriz obrigatória OV2640

Criar ou atualizar uma documentação dedicada com colunas:

1. recurso;
2. suporte segundo o datasheet;
3. implementação real em `esp32-camera` 2.1.7/`ov2640.c`;
4. exposição no CameraWebServer;
5. exposição permitida no projeto;
6. teste necessário;
7. mensagem para Android/backend.

Usar exclusivamente estas classificações:

- `Compatível e implementado.`
- `Compatível no sensor, mas não exposto pelo driver.`
- `Compatível no sensor, mas não recomendado para OCR.`
- `Compatível somente para diagnóstico.`
- `Parcialmente compatível.`
- `Não compatível no driver atual.`
- `Não suportado pela OV2640.`
- `Recurso de hardware separado da câmera.`
- `Requer teste físico antes de ser liberado.`

Incluir individualmente:

- todos os framesizes locais: 96×96, QQVGA, 128×128, QCIF, HQVGA, 240×240, QVGA, 320×320, CIF, HVGA, VGA, SVGA, XGA, HD, SXGA e UXGA;
- proporções e recortes;
- JPEG, YUV422, YUV420, RGB565, RGB555, RGB888, RAW e RAW8;
- brilho, contraste, saturação e qualidade JPEG;
- AEC, exposição manual e nível de exposição;
- AGC, ganho manual e limite de ganho;
- AWB, ganho de AWB e modos WB;
- BPC, WPC, Raw Gamma, Lens Correction e DCW;
- Hmirror e Vflip;
- efeitos e colorbar;
- sharpness e denoise;
- autofocus e foco manual;
- zoom, pan e windowing;
- PLL, XCLK e frame rate;
- sincronização;
- flash/strobe;
- leitura e escrita de registradores.

Fontes a registrar na documentação:

- datasheet OV2640 v1.6;
- fontes exatas do componente local travado em 2.1.7;
- `esp_camera.h`, `sensor.h`, `ov2640.c` e camada ESP32-S3;
- CameraWebServer oficial da Espressif/Arduino-ESP32.

Gate `G02`: a matriz cita versão/commit do componente e nenhum controle é declarado compatível apenas por existir em `sensor.h`.

---

## 7. Etapa S01 — backend: capacidades e perfis de câmera

### 7.1 Arquivos-alvo

Localizar e atualizar, conforme a estrutura real:

- modelos de dispositivo, sessão, captura e frame;
- `apps/api/schemas/admin.py`;
- routers de configurações administrativas;
- routers do gateway;
- política de captura;
- geração de comandos;
- migrations Alembic;
- serviços de auditoria;
- testes unitários e de API.

### 7.2 Passos

1. Implementar enums `OCR` e `PHOTO`.
2. Manter enum legado de vídeo apenas se necessário para ler dados antigos.
3. Rejeitar criação de vídeo/clip/preview.
4. Implementar `CameraCapabilitiesV1` com:
   - valores disponíveis;
   - valores protegidos;
   - valores indisponíveis;
   - mensagem explicativa;
   - versão do firmware/driver a que a capability se refere.
5. Implementar perfis padrão OCR e Foto.
6. Implementar criação de nova revisão.
7. Impedir edição retroativa de revisão usada.
8. Criar snapshot ao iniciar sessão.
9. Validar todas as faixas.
10. Registrar usuário/ator e auditoria.
11. Implementar retorno de solicitado versus efetivo.
12. Tratar incompatibilidade firmware antigo versus contrato v2.
13. Manter feature flag desligada até Android e firmware estarem instalados.

### 7.3 Testes

- perfil OCR padrão;
- perfil Foto padrão;
- qualidades 8–12;
- rejeição 7/13;
- rejeição de qualidade Android 90 no campo ESP;
- revisão imutável;
- snapshot por sessão;
- rejeição de vídeo;
- lista de controles indisponíveis;
- auditoria;
- firmware sem capability v2;
- concorrência de atualização de perfil.

Gate `G03`: API documentada, migration aprovada, contrato v2 validado e retrocompatibilidade demonstrada.

Commit sugerido:

```text
feat(camera): add versioned OCR and photo control contract
```

---

## 8. Etapa S02 — backend: upload, original e telemetria

### 8.1 Passos

1. Definir `capture_id`, `page_number` e `frame_number` como identidade explícita.
2. Tornar upload idempotente por identidade e SHA-256.
3. Validar estrutura JPEG, tamanho e hash antes de confirmar.
4. Armazenar original em prefixo/chave imutável.
5. Nunca substituir o original por imagem tratada.
6. Criar derivado de OCR em outra chave com referência ao SHA do original.
7. Registrar solicitado/efetivo, tamanho, PSRAM, DMA, firmware e tempos.
8. Confirmar upload somente depois de commit no storage e banco.
9. Retornar confirmação reutilizável em retries idênticos.
10. Falhar em retry com mesmo ID e conteúdo diferente.
11. Preservar ordem lógica das páginas independentemente da ordem física de chegada.
12. Impedir processamento de sessão com conjunto incompleto/não confirmado.
13. Incluir telemetria na observabilidade e no painel técnico.

### 8.2 Testes

- upload válido;
- JPEG truncado;
- hash divergente;
- retry idêntico;
- retry conflitante;
- dois frames da mesma página;
- páginas chegando fora de ordem;
- storage indisponível;
- banco falhando depois do upload;
- original e derivado com chaves diferentes;
- reprocessamento OCR sem modificar original.

Gate `G04`: o mesmo SHA-256 é comprovado na origem, banco e objeto original; derivado separado; retry idempotente aprovado.

Commit sugerido:

```text
feat(capture): persist immutable originals and camera telemetry
```

---

## 9. Etapa S03 — backend: teste RGB físico e sequência real

### 9.1 Contrato manual

Campos:

- `device_id` obrigatório;
- `session_id` opcional;
- cor por RGB ou hexadecimal;
- brilho 0–100%;
- `on_ms` 100–60000;
- `off_ms` 0–60000;
- `repeat_count` 1–20;
- duração total máxima 120 segundos;
- `command_id` UUID;
- expiração;
- `STOP` idempotente.

### 9.2 Endpoints administrativos sugeridos

Adaptar os caminhos ao estilo real do projeto:

```text
GET  /admin/devices
GET  /admin/devices/{device_id}/camera-capabilities
POST /admin/devices/{device_id}/rgb-tests
GET  /admin/devices/{device_id}/rgb-tests/{command_id}
POST /admin/devices/{device_id}/rgb-tests/{command_id}/stop
```

### 9.3 Endpoints de gateway sugeridos

```text
GET  /gateway/devices/{device_id}/commands?after=<cursor>
POST /gateway/devices/{device_id}/commands/{command_id}/events
```

Se já existir um transporte genérico de comandos, estendê-lo em vez de criar polling paralelo.

### 9.4 Máquina de estados

```text
QUEUED
  → FORWARDED
  → RECEIVED
  → APPLIED
  → OFF
```

Saídas alternativas:

```text
QUEUED/FORWARDED → EXPIRED
qualquer estado ativo → FAILED
qualquer estado ativo → CANCELLED → OFF
```

Não marcar `delivered_at` como prova de aplicação. O estado somente avança com o evento correspondente.

### 9.5 Sequência RGB real

Preservar o contrato atual de sequência por sessão e acrescentar, por snapshot para novas sessões:

- paleta A–E;
- paleta manuscrita, se ainda utilizada;
- RGB por alternativa;
- brilho;
- `on_ms`;
- `off_ms`;
- sinal de início;
- sinal de processamento;
- sinal de conclusão;
- sinal de erro;
- regra de retomada.

Documentar:

```text
período_total_ms = on_ms + off_ms
frequência_aproximada_hz = 1000 / período_total_ms
```

Não criar campo `speed`.

### 9.6 Exclusão mútua

- Uma sequência real ativa cancela ou rejeita teste manual.
- Um teste manual não altera snapshot da sessão.
- O painel deve informar conflito explicitamente.
- O backend deve rejeitar dois testes manuais simultâneos para o mesmo dispositivo.

Gate `G05`: estados, timeout, idempotência, STOP, auditoria e conflito com sequência real cobertos por testes.

Commit sugerido:

```text
feat(rgb): add audited physical device test commands
```

---

## 10. Etapa A01 — Android: armazenamento e bridge confiável

### 10.1 Arquivos-alvo iniciais

- `apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/network/ApiService.kt`;
- `.../domain/SessionRepository.kt`;
- `.../esp/EspHttpServer.kt`;
- `.../service/EspBridgeService.kt` ou equivalente;
- entidades/DAOs Room;
- workers de sincronização;
- testes JVM e instrumentados.

### 10.2 Passos

1. Implementar DTOs do contrato de câmera v2.
2. Separar `androidJpegQualityPercent` de `espJpegQuality`.
3. Persistir comandos recebidos antes de encaminhar à ESP.
4. Persistir eventos da ESP antes de confirmar localmente.
5. Implementar outbox Android → backend.
6. Não avançar cursor de polling antes do efeito durável.
7. Implementar deduplicação por `command_id`.
8. Implementar endpoint local de configuração/captura de câmera.
9. Implementar endpoint local de teste RGB e STOP.
10. Encaminhar `RECEIVED`, `APPLIED`, `OFF`, `FAILED` e telemetria.
11. Manter estado de online/offline por heartbeat real do dispositivo.
12. Implementar timeouts distintos para transporte e aplicação.
13. Recuperar comandos/outbox após encerramento do processo Android.
14. Manter serviço em foreground durante sessão, upload ou comando RGB ativo.
15. Validar autenticação/identidade entre Android e ESP conforme contrato local existente.

### 10.3 Spool Android

1. Persistir cada JPEG original antes de ACK à ESP.
2. Registrar SHA-256 e tamanho.
3. Manter estado:
   - `RECEIVED_LOCAL`;
   - `QUEUED_UPLOAD`;
   - `UPLOADING`;
   - `CONFIRMED_REMOTE`;
   - `FAILED_RETRYABLE`;
   - `FAILED_FINAL`.
4. Limitar a 10 páginas pendentes, contando página e não frame.
5. Permitir 1–3 frames dentro da mesma página.
6. Aplicar backpressure à ESP ao atingir 10.
7. Remover arquivo local somente após confirmação remota persistida.
8. Preservar arquivos após perda de rede, reboot do telefone ou encerramento do app.

### 10.4 Testes

- processo encerrado após receber comando;
- processo encerrado após receber JPEG;
- backend offline;
- ESP offline;
- duplicação de comando;
- duplicação de upload;
- hash divergente;
- janela de 10 páginas;
- 3 frames por página;
- retomada após reinicialização;
- STOP durante RGB ligado e desligado.

Gate `G06`: testes JVM aprovados e instrumentados para persistência/retomada; bridge não depende da tela aberta.

Commit sugerido:

```text
feat(android): bridge camera and physical RGB commands durably
```

---

## 11. Plano remanescente revisado — execução enxuta

Revisão autorizada em 2026-09-09. Os gates concluídos `G00-A`, `G09` e `G01–G06`, seus estados e suas evidências permanecem válidos. Os antigos gates futuros vazios `G08`, `G10–G12`, `G14–G16`, `G18`, `G20–G21` e `G23` foram absorvidos pelos seis gates abaixo; eles não devem ser executados separadamente.

### 11.1 Princípios de eficiência

1. Cada gate de implementação executa apenas checagens rápidas e direcionadas ao código alterado.
2. Dependências são instaladas uma vez por ambiente e caches válidos são reutilizados.
3. Cada suíte completa, build limpo, instalação física e missão longa ocorre no máximo uma vez por candidato imutável.
4. Um resultado aprovado ligado ao mesmo commit, configuração e artefato não é repetido. Repetir somente após mudança que possa invalidá-lo ou por falha ambiental comprovada.
5. Em falha, executar primeiro o teste mínimo que reproduz o defeito; depois da correção, repetir esse teste e apenas a suíte diretamente afetada. A campanha inteira só volta a rodar se o candidato mudou em área transversal.
6. Matriz física usa cobertura ortogonal baseada em risco, não produto cartesiano de todas as combinações.
7. Emulador Android, teste instrumentado e depuração USB não são requisitos por gate. Há uma única validação conectada no telefone piloto em `G22`; usar emulador somente se não houver telefone compatível e nunca testar ambos sem motivo.
8. Debug amplo, busca exploratória por erros, análise consolidada de logs e testes demorados ficam em `G22`.
9. Evidência deve apontar commit, configuração, artefato e relatório. Contagem de testes não substitui cobertura dos riscos críticos.

### 11.2 Paralelismo seguro

Depois de `G07` iniciado, executar em paralelo as frentes independentes:

- frente A: Android UI e painel, no repositório servidor/Android;
- frente B: firmware Production, câmera, spool e RGB, no repositório próprio do firmware;
- frente C: preparação de fixtures, manifesto de evidências e scripts de orquestração, sem alterar contratos já aprovados.

Dois executores não podem escrever no mesmo checkout. Para paralelismo no mesmo repositório, usar worktrees/branches separados e integrar por commits revisados; sem worktree, executar as alterações de código em série. Builds e testes independentes podem rodar em paralelo quando não compartilham diretório de saída, porta, banco ou dispositivo. Cada processo deve ter log próprio e código de saída preservado.

### 11.3 Escada de confiança

| Nível | Momento | O que executar |
|---|---|---|
| Rápido | durante `G07` | lint/compilação/testes focados na unidade alterada |
| Integrado local | `G13` | uma suíte completa por componente e um build limpo do candidato |
| CI/release | `G17` | CI canônica e empacotamento assinado/reproduzível |
| Piloto | `G19` | deploy e instalações reais com smoke curto |
| Final | `G22` | uma campanha física ponta a ponta, falhas, DMA, RGB, Android e rollback |

---

## 12. Gate G07 — onda integrada de implementação

### 12.1 Android e painel

- Concluir UI OCR/Foto e RGB com solicitado versus efetivo, capabilities, estados offline/incompatível/timeout/`APPLIED`/`OFF` e prévia explicitamente não física.
- Manter controles técnicos protegidos e desabilitar campos incompatíveis com mensagem específica.
- Implementar no painel seleção de dispositivo, heartbeat, perfis versionados, capabilities, telemetria, RGB/STOP, permissões e feature flags.
- Não criar Vídeo, clip, streaming ou preview diagnóstico; manter flash branco fora da UI operacional.

### 12.2 Firmware Production

- Manter uma única variante oficial `Production`; remover o fluxo de BIN Diagnostic, preservando funções de teste protegidas e desligadas por padrão.
- Inicializar OV2640 em JPEG/UXGA, qualidade padrão 10 e faixa 8–12, `fb_count=1`, PSRAM, XCLK 10 MHz e buffer 655.360 bytes.
- Aplicar apenas setters compatíveis, verificar retornos e reportar estado efetivo; falha essencial aborta captura.
- Limitar a 1–3 frames, 180–300 ms entre frames e 5 s entre páginas, sem reinicializar a câmera dentro da mesma página.
- Validar JPEG e SHA-256, preservar spool transacional/idempotente e backpressure; o Android continua proprietário da janela durável de 10 páginas.
- Implementar WS2812 no GPIO 48 com estados, deduplicação, timers não bloqueantes, STOP idempotente, deadline/watchdog local e desligamento em erro, reboot, deep sleep ou perda de sessão.
- Configurar o flash branco baixo desde o boot, durante captura e antes do sleep; rejeitar qualquer comando de flash.

### 12.3 Checagens do gate

Executar somente testes focados nos módulos alterados, compilação incremental e `git diff --check`. Não executar `fullclean`, matriz física, emulador, `connectedAndroidTest`, deploy ou busca ampla de regressões neste gate.

Gate `G07`: todas as frentes implementadas, revisadas contra os contratos aprovados e aprovadas nas checagens rápidas. As evidências Android já registradas permanecem; o gate só conclui após painel e firmware também estarem cobertos.

---

## 13. Gate G13 — validação local integrada e candidata

### 13.1 Execução única

Fixar o commit candidato e executar, em paralelo quando os recursos forem independentes:

- backend: ambiente sincronizado uma vez, `ruff`, `mypy` e `pytest`, incluindo PostgreSQL/pgvector quando exigido pelo CI;
- painel: `npm ci` uma vez, typecheck, testes e build pelos scripts reais do `package.json`;
- Android: testes JVM e uma montagem local; não exigir emulador nem telefone neste gate;
- firmware: testes host/Unity/estáticos existentes e exatamente um `fullclean`, `reconfigure` e build `Production` em `build-prod`.

O script de firmware deve propagar falhas e não produzir Diagnostic. Salvar logs separados, versão das ferramentas, configuração efetiva e manifesto dos artefatos. Se uma frente falhar, não reiniciar as demais aprovadas; corrigir, rodar o teste mínimo e repetir apenas a frente impactada.

Gate `G13`: suítes locais aprovadas e candidata imutável identificada por commits, configurações e hashes. O build limpo aprovado não será repetido em `G17` se as entradas forem idênticas.

---

## 14. Gate G17 — release, commits, PRs e CI

### 14.1 Empacotamento sem recompilação inútil

- Reusar saídas de `G13` quando commit, toolchain e configuração forem idênticos; reconstruir somente o que assinatura, versionamento ou mudança de fonte exigir.
- Backend/painel: imagens por SHA e digests, migration head e identidade da fonte.
- Android: `applicationId`, `versionCode/versionName`, APK release com keystore legítimo, assinatura verificada e SHA-256. Sem keystore, bloquear; APK debug não substitui release.
- Firmware: versão nova, BIN Production, ELF/MAP, bootloader/partitions, flash args, sdkconfig efetivo, manifesto e SHA-256; registrar ESP-IDF 6.0.2, esp32-camera 2.1.7, buffer, XCLK, DMA e offsets.

### 14.2 Revisão e CI

Criar commits coerentes por componente, sem secrets/builds/dumps indevidos, fazer push sem `--force`, abrir PRs e executar a CI canônica uma vez no commit candidato. A CI verde serve como regressão ampla; não duplicar localmente a mesma suíte no mesmo commit. Falha de CI aciona diagnóstico focado e novo candidato.

Gate `G17`: artefatos reproduzíveis e assinados quando aplicável, commits/PRs identificados e CI verde.

---

## 15. Gate G19 — deploy e instalações piloto

Reservar uma única janela piloto e capturar o estado anterior necessário para rollback.

1. Implantar backend/painel por SHA, aplicar migration aditiva, confirmar `/ready`, worker, storage e identidade da release.
2. Executar smoke curto: login/admin, dispositivo/capability, um perfil, um upload idempotente de fixture com original/derivado e um comando RGB ainda restrito por flag.
3. Instalar o APK release no telefone piloto sem limpar dados; confirmar assinatura, pacote, versão, foreground service e conectividade com backend/ESP.
4. Gravar a application BIN Production na ESP piloto sem erase, após reconfirmar offset/partições e backup necessário; confirmar boot, versão, OV2640, PSRAM, DMA esperado, buffer, flash branco bloqueado e GPIO 48.
5. Fazer apenas uma captura curta e um RGB curto para provar instalação. A validação extensa pertence a `G22`.

Backend, preparação do telefone e preparação da ESP podem ocorrer em paralelo; os smokes integrados começam somente após readiness. Novos recursos permanecem limitados ao piloto.

Gate `G19`: digests/migration/readiness aprovados, APK e firmware exatos instalados nos dispositivos identificados e smoke mínimo aprovado.

---

## 16. Gate G22 — campanha física e produção integrada

Esta é a única etapa de testes demorados, Android conectado, depuração ampla e busca sistemática por erros. Usar um único pacote de evidências correlacionando UI → request → endpoint → backend/banco/storage → Android → ESP, com relógios sincronizados e IDs de sessão/página/frame/comando.

### 16.1 Matriz compacta de câmera

Não repetir todas as combinações. Executar estes casos ortogonais:

1. nominal: JPEG 10, dois frames, 220 ms, com texto pequeno, página densa e tabela/questão;
2. limite inferior combinado: JPEG 8, um frame, 180 ms, baixa iluminação ou papel amarelado;
3. limite superior combinado: JPEG 12, três frames, 300 ms, sombra ou inclinação;
4. Foto: uma captura representativa para comprovar separação do perfil OCR;
5. durabilidade: uma janela de 10 páginas no perfil nominal, contendo retry de rede controlado e retomada, sem repetir a matriz de cenas.

Medir tamanho/tempo p50-p95 quando a amostra permitir, PSRAM livre/maior bloco, upload/OCR, retries, corrupção, overflows e resets. Comparar JPEG 8/10/12 em uma cena fixa de referência; o conjunto nominal cobre as demais cenas. O padrão continua 10 salvo decisão documentada. Exigir SHA idêntico na ESP, Android, banco e storage, ordem preservada e original separado do derivado.

### 16.2 DMA por exceção

O padrão é `MANTER_DESLIGADO`. Não habilitar DMA nem repetir a matriz se o caso nominal cumprir latência e estabilidade. Executar A/B somente se a telemetria demonstrar gargalo relevante que DMA possa resolver; nesse caso repetir apenas os casos nominal e limite superior, interrompendo ao primeiro sinal de corrupção, overflow, reset, perda, regressão OCR ou pressão de memória. Registrar a decisão e restaurar desligado se não houver benefício claro.

### 16.3 RGB, segurança e Android conectado

- Rodar uma sequência real A–E conhecida para cobrir cores e repetição.
- Rodar um comando hexadecimal intermediário com brilho seguro e confirmar `APPLIED`/`OFF`.
- Executar STOP uma vez durante LED ligado e confirmar desligamento local rápido.
- Executar uma cadeia única de recuperação que cubra perda de conexão, reboot ou deep sleep; terminar e observar LED apagado.
- Confirmar que teste manual não altera paleta/sequência e nunca afeta o flash branco.
- No telefone piloto, executar uma única suíte instrumentada/smoke conectado sobre persistência, retomada e fluxo crítico. Não exigir emulador se o telefone real foi usado; não manter depurador USB conectado durante toda a campanha se logs e instalação puderem ser coletados sem ele.

### 16.4 Missão e rollback no mesmo roteiro

Usar a janela de 10 páginas acima como missão final, confirmando perfil, intervalos, originais, uploads, OCR, resultado na UI e sequência RGB. Depois, ensaiar uma vez o rollback: desabilitar flags, STOP/OFF, preservar evidências e restaurar o componente piloto de maior risco ou a versão anterior conforme o runbook, sem rollback destrutivo de schema. Confirmar readiness/fila/versão e então restaurar a candidata apenas se necessário para o estado final aprovado.

### 16.5 Triage eficiente e aceite

Coletar logs completos uma vez. Procurar automaticamente por `corrupt`, hash mismatch, `FB-OVF`, `DMA overflow`, watchdog, reset, fila perdida, duplicidade, flash e LED não desligado. Investigar somente ocorrências e métricas fora do limite; não fazer busca exploratória ilimitada sem sinal.

Gate `G22` exige:

- zero JPEG corrompido, `FB-OVF`, `DMA overflow` não autorizado ou watchdog/reset;
- zero perda/duplicidade lógica e SHA idêntico ponta a ponta;
- 10 páginas ordenadas, retry/retomada e OCR representativo aprovados;
- flash branco sempre apagado e RGB sempre terminando em `OFF`;
- APK release, firmware Production e backend por SHA funcionando juntos;
- decisão DMA registrada e rollback ensaiado/documentado.

---

## 17. Gate G24 — documentação e fechamento final

Atualizar somente os documentos afetados e reconciliá-los com os artefatos instalados:

- contratos de câmera/RGB/gateway, matriz OV2640 e esquema aditivo;
- build Production único, assinatura/instalação APK, flash sem erase e rollback;
- perfis, telemetria, spool/partições, feature flags e operação física;
- release notes e registro final com commits, PRs, CI, migration, digests, hashes, dispositivos, campanha, DMA, rollback, incidentes e pendências.

Remover instruções obsoletas que recomendem Diagnostic, Vídeo/clip/streaming/preview ou flash branco. Não reexecutar suítes aprovadas para “validar documentação”; conferir links, comandos, versões e comportamento instalado.

Gate `G24`: documentação revisada, commitada e consistente com a release. Executar `plan_control.py final-check`; somente sucesso permite declarar conclusão global.

---

## 18. Critérios finais não negociáveis

- Backend/painel: CI verde, migration aditiva aplicada, digests e readiness comprovados, solicitado/efetivo visível, controles incompatíveis claros e nenhum Vídeo.
- Android: APK release assinado e instalado sem perda de dados, bridge durável, janela de 10 páginas, comandos/eventos retomáveis e STOP real.
- Firmware: somente Production; JPEG/UXGA; qualidade 8–12 padrão 10; XCLK 10 MHz; buffer 655.360; PSRAM; `fb_count=1`; 1–3 frames; 180–300 ms; 5 s; flash branco bloqueado; DMA decidido por evidência; WS2812 GPIO 48 sempre desligado ao final.
- Integridade: zero corrupção/overflow/reset, SHA ponta a ponta, idempotência, ordem, original imutável e derivado separado.
- Produção: backend, APK e firmware identificados, missão integrada e rollback aprovados, documentação final reconciliada.

---

## 19. Dependências externas

Bloquear somente quando o gate realmente precisar do recurso ausente: keystore legítimo; telefone piloto; ESP32/cabo/porta; acesso a GitHub/VPS; aprovação externa de merge/deploy; identidade do piloto ou política de distribuição. Não gastar tempo preparando emulador antes de `G22`, não inventar credenciais e não usar a ausência física para impedir implementação ou validação local possível.

---

## 20. Sequência resumida

1. Concluídos e preservados: `G00-A`, `G09`, `G01–G06`.
2. `G07`: implementação paralelizável com checagens rápidas.
3. `G13`: uma validação local integrada e um build limpo.
4. `G17`: release, commits, PRs e CI uma vez.
5. `G19`: deploy e instalações numa janela piloto.
6. `G22`: uma campanha final física, instrumentada, de falhas e rollback.
7. `G24`: documentação e `final-check`.

O plano passa de 25 para 14 gates totais: oito já concluídos e seis restantes. Os IDs preservados mantêm rastreabilidade com o histórico.

---
## Apêndice A — matriz OV2640 apurada para orientar a implementação

Esta é a baseline técnica já levantada. Durante a execução, o chat deve conferir se a versão travada do componente continua sendo `esp32-camera` 2.1.7 e atualizar a matriz final caso o lockfile tenha mudado. As classificações abaixo são deliberadamente restritivas: suporte no datasheet não autoriza exposição no produto.

| Recurso | OV2640/datasheet | Driver local 2.1.7 | CameraWebServer | Decisão do produto |
|---|---|---|---|---|
| Resolução e tamanhos de frame | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Requer teste físico antes de ser liberado. |
| Proporções e recortes | Compatível e implementado. | Parcialmente compatível. | Compatível somente para diagnóstico. | Compatível somente para diagnóstico. |
| UXGA 1600×1200 | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Requer teste físico antes de ser liberado. |
| SXGA 1280×1024 | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Compatível no sensor, mas não recomendado para OCR. |
| HD 1280×720 | Parcialmente compatível. | Compatível e implementado. | Compatível e implementado. | Compatível no sensor, mas não recomendado para OCR. |
| XGA 1024×768 | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Compatível no sensor, mas não recomendado para OCR. |
| SVGA 800×600 | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Compatível no sensor, mas não recomendado para OCR. |
| VGA 640×480 | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Compatível no sensor, mas não recomendado para OCR. |
| CIF 400×296 | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Compatível no sensor, mas não recomendado para OCR. |
| QVGA 320×240 | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Compatível somente para diagnóstico. |
| 96×96 | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Compatível somente para diagnóstico. |
| QQVGA 160×120 | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Compatível somente para diagnóstico. |
| 128×128 | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Compatível somente para diagnóstico. |
| QCIF 176×144 | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Compatível somente para diagnóstico. |
| HQVGA 240×176 | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Compatível somente para diagnóstico. |
| 240×240 | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Compatível somente para diagnóstico. |
| 320×320 | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Compatível somente para diagnóstico. |
| HVGA 480×320 | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Compatível somente para diagnóstico. |
| JPEG | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Requer teste físico antes de ser liberado. |
| YUV422 | Compatível e implementado. | Compatível e implementado. | Parcialmente compatível. | Compatível no sensor, mas não recomendado para OCR. |
| YUV420 | Compatível e implementado. | Parcialmente compatível. | Não compatível no driver atual. | Compatível no sensor, mas não recomendado para OCR. |
| RGB565 | Compatível e implementado. | Compatível e implementado. | Parcialmente compatível. | Compatível no sensor, mas não recomendado para OCR. |
| RGB555 | Compatível e implementado. | Não compatível no driver atual. | Não compatível no driver atual. | Não compatível no driver atual. |
| RGB888 | Não suportado pela OV2640. | Parcialmente compatível. | Não compatível no driver atual. | Não compatível no driver atual. |
| RAW | Compatível e implementado. | Não compatível no driver atual. | Não compatível no driver atual. | Não compatível no driver atual. |
| RAW8 | Compatível e implementado. | Não compatível no driver atual. | Não compatível no driver atual. | Não compatível no driver atual. |
| Brilho | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Requer teste físico antes de ser liberado. |
| Contraste | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Requer teste físico antes de ser liberado. |
| Saturação | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Requer teste físico antes de ser liberado. |
| Qualidade JPEG | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Requer teste físico antes de ser liberado. |
| Exposição automática | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Requer teste físico antes de ser liberado. |
| Exposição manual | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Compatível somente para diagnóstico. |
| Nível de exposição | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Requer teste físico antes de ser liberado. |
| Ganho automático | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Requer teste físico antes de ser liberado. |
| Ganho manual | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Compatível somente para diagnóstico. |
| Limite de ganho | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Requer teste físico antes de ser liberado. |
| AWB | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Requer teste físico antes de ser liberado. |
| Ganho de AWB | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Requer teste físico antes de ser liberado. |
| Modos de balanço de branco | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Requer teste físico antes de ser liberado. |
| BPC | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Requer teste físico antes de ser liberado. |
| WPC | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Requer teste físico antes de ser liberado. |
| Raw Gamma | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Requer teste físico antes de ser liberado. |
| Lens Correction | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Requer teste físico antes de ser liberado. |
| DCW | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Requer teste físico antes de ser liberado. |
| Hmirror | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Requer teste físico antes de ser liberado. |
| Vflip | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Requer teste físico antes de ser liberado. |
| Efeitos especiais | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Compatível somente para diagnóstico. |
| Colorbar/test pattern | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Compatível somente para diagnóstico. |
| Sharpness | Compatível e implementado. | Não compatível no driver atual. | Não compatível no driver atual. | Não compatível no driver atual. |
| Denoise | Compatível e implementado. | Não compatível no driver atual. | Não compatível no driver atual. | Não compatível no driver atual. |
| Autofocus | Não suportado pela OV2640. | Não compatível no driver atual. | Não compatível no driver atual. | Não suportado pela OV2640. |
| Foco manual eletrônico | Não suportado pela OV2640. | Não compatível no driver atual. | Não compatível no driver atual. | Não suportado pela OV2640. |
| Zoom | Compatível e implementado. | Parcialmente compatível. | Compatível somente para diagnóstico. | Compatível somente para diagnóstico. |
| Pan/windowing | Compatível e implementado. | Parcialmente compatível. | Compatível somente para diagnóstico. | Compatível somente para diagnóstico. |
| Controle de PLL | Compatível e implementado. | Não compatível no driver atual. | Parcialmente compatível. | Não compatível no driver atual. |
| XCLK | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Compatível somente para diagnóstico. |
| Controle de frame rate | Compatível e implementado. | Compatível no sensor, mas não exposto pelo driver. | Parcialmente compatível. | Não compatível no driver atual. |
| Sincronização | Compatível e implementado. | Compatível no sensor, mas não exposto pelo driver. | Não compatível no driver atual. | Compatível somente para diagnóstico. |
| Flash/strobe | Compatível e implementado. | Compatível no sensor, mas não exposto pelo driver. | Recurso de hardware separado da câmera. | Recurso de hardware separado da câmera. |
| Leitura/escrita de registradores | Compatível e implementado. | Compatível e implementado. | Compatível e implementado. | Compatível somente para diagnóstico. |

Notas que o executor deve preservar na documentação final:

1. O driver local aceita `RGB888` em parte da interface do sensor redirecionando configuração RGB, mas o caminho completo da ESP32-S3 não oferece suporte confiável de ponta a ponta; não expor.
2. YUV420 depende de conversor/configuração adicional e não deve ser usado no OCR desta entrega.
3. `set_sharpness`, `set_denoise` e `_set_pll` da implementação OV2640 local não fornecem suporte funcional utilizável.
4. `set_res_raw`/windowing local é parcial e inadequado como controle comum.
5. Acesso direto a registradores é tecnicamente possível, mas fica restrito a engenharia protegida e não integra o perfil comum.
6. O flash branco da placa não é o WS2812 e permanece fora do contrato de imagem.
7. CameraWebServer usa escolhas orientadas a streaming e não deve ser copiado como perfil OCR.

Fontes técnicas a citar na documentação final:

- `https://dl.sipeed.com/MAIX/HDK/Chip_DS/OV2640-DATASHEET.pdf`;
- `https://github.com/espressif/esp32-camera`;
- `https://github.com/espressif/arduino-esp32/blob/master/libraries/ESP32/examples/Camera/CameraWebServer/CameraWebServer.ino`;
- `https://github.com/espressif/arduino-esp32/blob/master/libraries/ESP32/examples/Camera/CameraWebServer/app_httpd.cpp`.

---

## Apêndice B — inventário técnico do estado atual

Este inventário reduz redescoberta, mas deve ser reconfirmado antes de editar porque as fontes podem mudar.

### B.1 Firmware atual

- ESP-IDF travado em 6.0.2.
- `esp32-camera` 2.1.7, commit observado `202df95d...`.
- Perfil de placa com OV2640, XCLK 10 MHz, WS2812 GPIO 48 e flash branco configurado no GPIO 2.
- `camera_service.c` inicializa JPEG, UXGA, `fb_count=1`, framebuffer PSRAM e `CAMERA_GRAB_WHEN_EMPTY`.
- Qualidade full atual observada: 18, ainda incompatível com o padrão 10.
- Faixa atual observada: aproximadamente 5–40, ainda incompatível com 8–12.
- Framesizes expostos pelo produto: QVGA, VGA, SVGA, XGA, SXGA e UXGA; HD e tamanhos intermediários existem no componente, mas não são necessários no perfil do produto.
- Burst atual pode chegar a 30 frames; deve cair para 1–3.
- Gap atual padrão de 5 segundos é aplicado no contexto errado para o novo requisito; deve haver campos separados para frame e página.
- Captura atual copia JPEGs para PSRAM e calcula SHA-256.
- Fluxo atual pode desinicializar/reinicializar entre frames, incompatível com 180–300 ms.
- Kconfig automático calcula aproximadamente 384.000 bytes em UXGA.
- Kconfig do componente oferece tamanho customizado de 655.360 sem patch em terceiro.
- `CONFIG_CAMERA_PSRAM_DMA` está desligado.
- Partição de spool documentada tem aproximadamente 5 MiB.
- Limite UXGA atual do spool está próximo de 350 KiB e precisa ser revisado.
- Spool atual possui versionamento, CRC, hash e commit marker gravado por último.
- Há infraestrutura de perfil Diagnostic e auto-start que deve ser retirada do produto final.
- Release 2.4.0 existente é anterior ao novo escopo e não pode ser reaproveitada como artefato final.

### B.2 Backend atual

- Perfis/políticas existentes ainda misturam qualidades 50/90 ou 75/90 do domínio Android com qualidade da ESP.
- Diagnóstico de câmera existente aceita `PHOTO`, `CLIP` e `PREVIEW`, com qualidade mais ampla; deve ser alinhado ao novo escopo sem Vídeo.
- Backend possui paletas A–E, paleta manuscrita, brilho, `on_ms`, `off_ms`, teste RGB e sequência RGB real.
- Validações atuais de RGB já trabalham com canais 0–255, brilho 0–100, `on_ms` 100–60000 e `off_ms` 0–60000.
- `RgbTestCommand` atual é ligado à sessão e registra criação/entrega, mas não `device_id`, aplicação, desligamento, STOP ou falha física.
- A leitura do comando pelo gateway marca entrega antes de existir confirmação da ESP.
- Não há máquina de estados física completa.
- A branch local possui implementação anterior ampla no commit `62aeb3c`, mas não está comprovadamente publicada em produção.

### B.3 Android atual

- Consulta o teste RGB no backend.
- Exibe a cor na tela e executa temporização visual local.
- Não encaminha esse teste manual ao WS2812 físico.
- Possui servidor HTTP local para sessão, frames, captura completa, heartbeat, fault, sequência/eventos RGB, diagnósticos e comandos genéricos.
- Não possui endpoint específico/confirmado para teste manual físico do RGB.
- A sequência RGB real, diferentemente do teste manual, já é encaminhada ao firmware.
- O build anterior falhou por Android SDK não configurado.
- JDK 17 observado em `C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot`.
- `applicationId` observado: `com.pagestoaudio.gateway`.
- Versão observada: `versionCode 2`, `versionName 1.0.1`.
- Não foi encontrada configuração comprovada de signing release.
- O APK existente é anterior às alterações e não pode ser distribuído como release nova.

### B.4 RGB real atual

O caminho em código da sequência real é:

```text
backend gateway RGB
  → Android /v1/device/rgb-sequence
  → firmware
  → rgb_sequence_service
  → led_service_set_rgb
  → RMT
  → WS2812 GPIO 48
```

Ele precisa de teste físico, mas não deve ser substituído pelo novo teste manual.

### B.5 Produção atual

- Workflow de deploy dispara apenas em `main`.
- Imagens de API e painel são publicadas em GHCR por SHA.
- Deploy usa backup, SSH e scripts versionados.
- O serviço de produção não deve ser considerado atualizado até o merge/deploy e a verificação de identidade da release.
- Não houve push, deploy, APK novo nem flash físico das alterações correspondentes a este plano.

---

## Apêndice C — modelo de evidências finais

Preencher em um arquivo de registro datado durante a execução.

### C.1 Código

| Componente | Repositório | Branch | Commit | PR | CI |
|---|---|---|---|---|---|
| Backend/painel/Android |  |  |  |  |  |
| Firmware |  |  |  |  |  |

### C.2 Artefatos

| Artefato | Versão/tag | SHA-256/digest | Origem | Destino instalado |
|---|---|---|---|---|
| API image |  |  |  |  |
| Worker image |  |  |  |  |
| Admin image |  |  |  |  |
| APK release |  |  |  |  |
| Firmware app BIN |  |  |  |  |
| Firmware ELF |  |  |  |  |

### C.3 Produção

| Item | Valor/evidência |
|---|---|
| Migration head |  |
| Readiness |  |
| Release identity |  |
| Telefone |  |
| ESP/device_id |  |
| Porta/MAC/chip ID |  |
| Feature flags |  |
| Horário do rollout |  |

### C.4 Câmera

| Caso | Cena | Q | Frames/gap | Tamanho | Captura | Upload/OCR | PSRAM mín. | Erros |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Nominal 1 | Texto pequeno/referência | 10 | 2/220 ms |  |  |  |  |  |
| Nominal 2 | Página densa | 10 | 2/220 ms |  |  |  |  |  |
| Nominal 3 | Tabela/questão | 10 | 2/220 ms |  |  |  |  |  |
| Limite inferior | Mesma referência | 8 | 1/180 ms |  |  |  |  |  |
| Limite superior | Mesma referência | 12 | 3/300 ms |  |  |  |  |  |
| Foto | Cena representativa | conforme perfil | 1 |  |  |  |  |  |
| Durabilidade | 10 páginas nominais | 10 | 2/220 ms |  |  |  |  |  |

### C.5 Integridade

| Identidade | SHA ESP | SHA Android | SHA backend | SHA storage | Original preservado |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

### C.6 RGB

| command_id | device_id | solicitado | RECEIVED | APPLIED | OFF | físico observado | erro |
|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |

### C.7 Rollback

| Componente | Versão anterior | Procedimento ensaiado | Resultado |
|---|---|---|---|
| Backend |  |  |  |
| Android |  |  |  |
| Firmware |  |  |  |

---

## Apêndice D — documentos legados a reconciliar

Durante a atualização documental final, revisar estes documentos existentes para evitar instruções conflitantes:

Servidor:

- `docs/PLANO_ADICIONAL_TESTE_CAMERA_2026-09-09.md`;
- `docs/PLANO_CONCLUSAO_POS_REAUDITORIA_2026-09-09.md`;
- `docs/PLANO_IMPLEMENTACAO_SERVIDOR_2026-09-09.md`;
- `docs/runbooks/camera-diag-D06-protocolo.md`;
- `docs/runbooks/camera-diag-D07-deploy.md`;
- `docs/runbooks/camera-diag-D08-rollback.md`;
- `docs/runbooks/missao-fisica-S10.md`;
- `docs/runbooks/rollback-S12.md`.

Firmware:

- `docs/PLANO_ADICIONAL_TESTE_CAMERA_2026-09-09.md`;
- `docs/PLANO_CONCLUSAO_POS_REAUDITORIA_2026-09-09.md`;
- `docs/PLANO_IMPLEMENTACAO_FIRMWARE_2026-09-09.md`;
- `docs/PROCEDIMENTO_BANCADA_F09_2026-09-09.md`;
- `docs/RELEASE_2_4_0_2026-09-09.md`;
- `docs/ROLLBACK_2026-09-09.md`;
- `docs/OPERATION.md`;
- `docs/HARDWARE_PROFILE.md`;
- `docs/ANDROID_GATEWAY_CONTRACT.md`.

Não apagar registros históricos. Marcar planos superados como históricos e apontar para este plano/contratos atuais. Remover apenas instruções operacionais ativas que fariam o executor gerar Diagnostic, Vídeo ou habilitar flash.
