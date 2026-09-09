# Contrato adicional — diagnóstico de câmera (foto, prévia, clipe)

Identificador: P2A-CAMERA-DIAG-2026-09-09, revisão 1.
Pai normativo: P2A-INTEGRACAO-2026-09-09 rev.1 (missão continua normativa).
Estado: extensão congelada para implementação (D00). Cópias idênticas nos dois projetos.
Feature flag: desligada por padrão nas três pontas (servidor/Android/firmware).

## 1. Capacidade e ativação

- Capability: `camera_diagnostics_v1`. Cliente sem ela responde indisponibilidade
  controlada; nunca interpreta comando de teste como comando de captura.
- Admin habilita por dispositivo com prazo. Gateway confirma disponibilidade;
  ESP confirma capacidade + ausência de pendências. Só a confirmação da ESP
  coloca o diagnóstico em ACTIVE. HTTP de criação do pedido ≠ câmera funcionando.
- Ativação local no Android mantém janela curta para a placa acordada receber
  o pedido (política de wake principal inalterada). ESP em deep sleep:
  interface informa "dispositivo indisponível; ative o modo de teste no gateway
  e acorde a placa pelo procedimento normal". Sem wake remoto.
- Diagnóstico nunca roda junto com missão, recuperação de spool,
  espera/reprodução RGB ou operação pendente da placa. Sessão pausada continua
  ocupada. Exclusão atômica por dispositivo (uma aquisição por vez). Se missão
  for pedida durante teste: cancela diagnóstico, aguarda liberação confirmada,
  depois inicia — ou devolve "câmera em teste". Nunca em paralelo.
- Duração máxima local por rodada. Heartbeat de controle a cada 10 s com tela
  visível; expira autorização após 30 s sem renovação + limite total do modo.
  Parada: botão, expiração, perda prolongada, erro de recurso, atividade
  principal. Após reboot, diagnóstico não retoma; só arquivos já aceitos são
  recuperados. ACK de STOP confirma liberação; até lá "encerrando".

## 2. Modos e limites iniciais (propostos, não benchmark)

- Foto: 1 frame; SVGA inicial; maiores só entre resoluções já validadas.
  Teto: menor entre capacidade validada do firmware e 2 MiB.
- Prévia: VGA alvo até 2 fps; alternativa QVGA/taxa menor em rede lenta,
  sempre com perfil efetivo. 60 s por rodada. Teto 20 MiB/rodada.
  ESP: 1 frame por vez. Gateway: 1 em trânsito + 1 aguardando; descarta
  intermediárias. Prévia é transitória (sem spool de missão, sem flash da ESP
  a cada update); limpeza em até 10 min; ponteiro "último frame" só avança.
- Clipe: 10 s alvo até 2 fps, sem áudio; limite 30 s / 60 frames.
  Teto 20 MiB de JPEGs + saída temporária limitada.
  Conversão: 1 por vez no worker, timeout 60 s, memória configurada.
- Histórico: 7 dias e 100 MiB/dispositivo, limpeza restrita a diagnóstico.
- Para dimensionar: bytes_reais × taxa_efetiva × duração
  (ex.: 100 KiB × 2 fps ≈ 1,64 Mbit/s payload por trecho; 60 s ≈ 11,7 MiB).
- Se missão desliga Wi-Fi para fotografar, medir o ciclo antes de prometer
  2 fps. Sem reestruturar missão para acelerar teste. Só presets validados;
  sem autofocus fictício nem sliders de registradores.

## 3. Identidade e estado

- Estados: REQUESTED, ACTIVE, STOPPING, COMPLETED, FAILED, EXPIRED.
- Campos: diagnostic_id, device_id, gateway_id, modo (PHOTO/CLIP/PREVIEW),
  perfil solicitado/efetivo, limites, origem (ESP física), horários, motivo
  final, contadores. IDs 1–63 chars `[A-Za-z0-9_-]` (nunca truncar).
- Cada tentativa tem diagnostic_id próprio. Frames: diagnostic_id +
  frame_index + SHA-256. Duplicata idêntica = idempotente (208/duplicate);
  outra imagem no mesmo índice = conflito 409. Nunca usar
  capture_id/session_id de missão como namespace do teste.
- Uploads: JPEG bruto ou adaptação existente, com identidade, índice, hash,
  dimensões e tempo monotônico de captura. Android adiciona recebimento;
  servidor adiciona chegada. Sem subtrair relógios não sincronizados.

## 4. API administrativa (prefixo /api/v1/admin/camera-diagnostics)

| Método | Rota | Corpo/resposta |
| --- | --- | --- |
| POST | /api/v1/admin/camera-diagnostics | `{device_code, mode: PHOTO\|CLIP\|PREVIEW, profile:{resolution, jpeg_quality}, duration_s?, note?}` → `201 {diagnostic_id, status: REQUESTED, expires_at, limits}` |
| GET | /api/v1/admin/camera-diagnostics/{id} | `{diagnostic_id, device_code, gateway_code, mode, status, requested_profile, effective_profile, origin, created_at, expires_at, completed_at, reason, counters{received_frames, bytes, last_frame_at}}` |
| POST | /api/v1/admin/camera-diagnostics/{id}/stop | idempotente → `{diagnostic_id, status: STOPPING\|COMPLETED, ack}` |
| GET | /api/v1/admin/camera-diagnostics/{id}/latest | `{frame_index, sequence, sha256, width, height, captured_at_mono_ms, received_at, age_s, effective_fps, storage_key}` + imagem via rota autenticada ou URL assinada curta |
| GET | /api/v1/admin/camera-diagnostics/{id}/assets | `{photos:[{frame_index, sha256, bytes, url}], clips:[{mp4_key, url, duration_s, fps, frames}]}` paginado |

Erros: 400 validação, 401/403 auth/papel, 404 inexistente, 409 ocupado/
conflito de hash/concorrência, 410 expirado, 413 quota/tamanho, 501 sem
capacidade, 503 storage/worker indisponível. `Cache-Control: no-store`.

Exemplo criação:

```json
{"device_code": "CAM-001", "mode": "PHOTO", "profile": {"resolution": "SVGA", "jpeg_quality": 18}}
```

Exemplo estado:

```json
{"diagnostic_id": "dg_01AbC", "mode": "PREVIEW", "status": "ACTIVE",
 "effective_profile": {"resolution": "VGA", "jpeg_quality": 24},
 "counters": {"received_frames": 12, "bytes": 1234567}}
```

## 5. Gateway cloud (prefixo /api/v1/gateway) — extensão aditiva

- `POST /api/v1/gateway/diagnostics/{id}/claim` — gateway assume entrega.
- `POST /api/v1/gateway/diagnostics/{id}/event` — `{event: ACTIVE|FRAME|STOPPED|FAILED, frame_index?, sha256?, bytes?}`.
- `POST /api/v1/gateway/diagnostics/{id}/frame` (multipart JPEG) — headers
  `X-Diagnostic-Id, X-Frame-Index, X-SHA256, X-Captured-Mono-Ms,
  X-Width, X-Height`; resposta `200/201` (novo) ou `208 duplicate:true`;
  `409` conflito de hash.
- `POST /api/v1/gateway/diagnostics/{id}/preview` — aceitação transitória
  (endpoint separado; não conta como foto salva nem missão).
- `POST /api/v1/gateway/diagnostics/{id}/ack` — confirma liberação (STOP).
- Auth: token cloud + X-Gateway-Id; vínculo usuário-dispositivo-gateway.

## 6. Trecho local ESP↔Android (porta 8787, TLS provisionado em produção)

- `POST /v1/device/diagnostics` — `{diagnostic_id, mode, resolution,
  jpeg_quality, duration_s, max_frames}` → `200 {accepted, reason?}` ou
  `409 busy {reason: mission_active|spool_pending|rgb_pending}`.
- `POST /v1/device/diagnostics/frame` — JPEG bruto + mesmos headers do §5.
- `POST /v1/device/diagnostics/stop` — `{diagnostic_id}` → `200 {released}`.
- `GET /v1/device/diagnostics` — `{active: bool, diagnostic_id?, mode?}`.
- Segredo por dispositivo no header Authorization; nunca em log. Capability
  anunciada no HELLO: `camera_diagnostics_v1`.

## 7. Persistência

- Fotos/clipes: JPEG original sem reencode; fila durável Android com
  tipo/quota de diagnóstico (sem segunda implementação de spool);
  confirmação só após durabilidade do ACK local/cloud; prefixo
  `diagnostics/{device_id}/{diagnostic_id}/`; imutável na retenção;
  Android libera após ACK cloud; clipe parcial = incompleto (sem frames
  inventados; download parcial permitido com indicação; sem MP4 completo).
- Missão e ORIGINAL intocados. Nenhum arquivo de câmera permanente no disco
  da VPS; MP4 no storage existente.
- Prévia: storage compartilhado com objeto temporário de índice único +
  ponteiro "último frame" no banco publicado só após objeto existir; sem
  variável global de processo como fonte única; chegada atrasada não
  retrocede ponteiro; limpeza não remove o apontado válido; se storage cai,
  falha explícita (sem cair em memória como se fosse durável).

## 8. Vídeo (worker existente)

- Entrada: JPEGs do clipe + tempos reais. Tarefa fora do request HTTP, sem
  OCR/solver/áudio. FFmpeg com lista concat + durações (manifest) ou
  timestamps equivalentes; H.264, yuv420p, dimensões pares, faststart.
- Verificar encoder real na imagem (não presumir libx264). Validar duração
  com ffprobe + reprodução real. Timeout 60 s, kill/wait/reap, temporários
  em diretório privado limitado, nomes validados, argv estruturado (sem
  shell com entrada do usuário). Idempotente; sobras limpas após restart.
  Cancelamento encerra FFmpeg e trata temporários.

## 9. Navegador

Página admin "Teste de câmera" (PC + celular): dispositivo, gateway
online/offline, ocupado/livre, modo; botões foto/10 s/ao vivo/parar com
perfil efetivo; polling de metadados ~500 ms só com tela visível e sem
sobreposição (só busca imagem se índice mudou); JPEG como imagem (nunca
base64 em JSON); URLs assinadas curtas mesma origem; idade/FPS/conexão;
>5 s sem novidade = "imagem desatualizada"; aba oculta para polling/STOP
best-effort (segurança depende do prazo local); foto com 100%/fit/download
+ comparação de 2 fotos; player nativo playsinline sem áudio com duração/
taxa reais; galeria paginada com miniaturas (sem carregar tudo).

## 10. Flags, quotas e limpeza

- Flags (todas default off): `CAMERA_DIAGNOSTICS_ENABLED` (servidor),
  `diagnosticsEnabled` (Android), `CONFIG_CAPTURE_DIAG_ENABLE=n` (firmware).
- Quotas: foto 2 MiB; prévia 20 MiB/rodada; clipe 20 MiB entrada; histórico
  7 d / 100 MiB por dispositivo; prévia transitória 10 min; conversão 1 por
  vez / 60 s.
- Limpeza restrita a chaves `diagnostics/...` verificadas; nunca toca missão.
- Teste não altera qualidade persistente da missão; perfil de teste é
  temporário em memória; sem NVS, sem partição, sem pinagem, sem exemplo
  CameraWebServer, sem WebRTC/RTSP/HLS/broker/Redis/streaming na v1.
- Origem sempre identificada como câmera física da ESP; CameraX nunca é
  substituto silencioso.
