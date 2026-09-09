# Registro de execução D00–D08 — diagnóstico de câmera — 09/09/2026

Plano: `docs/PLANO_ADICIONAL_TESTE_CAMERA_2026-09-09.md` (revisão 1).
Contrato adicional: `docs/contracts/CAMERA_DIAGNOSTICS_2026-09-09.md`
(P2A-CAMERA-DIAG-2026-09-09 rev.1) — cópia idêntica nos dois projetos (hash
conferido na execução).
Executor: chat IDE (servidor/Android + coordenação firmware).

## Pré-requisitos (plano §2) — estado honesto

1. Planos principais de 09/09/2026: código concluído nos dois projetos
   (servidor S00–S12, firmware F00–F11 v2.4.0), porém o **aceite físico H4
   segue pendente** (S10 bloqueado sem telefone/ESP/serviços; F09 com
   procedimento pronto e execução pendente). Conforme o plano ("somente
   depois do aceite"), nenhuma câmera foi ligada ou testada por este
   registro; a implementação abaixo segue como **código atrás de flag
   desligada**, sem declarar aceite físico nem substituir H4 por mock.
2. Contrato principal e registros reais lidos antes de codar; nenhum patch
   contra retrato antigo: IDs/cursores/ACKs/durabilidade seguem o código
   atual (S01–S05 + S06–S12).
3. Sem CameraX silencioso, sem WebRTC/RTSP/HLS/broker/Redis/streaming,
   sem exemplo CameraWebServer, sem pinagem/partição/NVS tocadas.

## O que foi implementado

| Etapa | Entrega | Evidência |
| --- | --- | --- |
| D00 | Extensão congelada + flags off | `docs/contracts/CAMERA_DIAGNOSTICS_2026-09-09.md` (2 cópias idênticas); `CAMERA_DIAGNOSTICS_ENABLED=false`, `DiagConfig.diagnosticsEnabled=false`, `CONFIG_CAPTURE_DIAG_ENABLE=n` |
| D01 | Servidor: controle/upload/galeria | `db/models/camera_diagnostic.py`, migration `0012`, `camera_diagnostics/service.py` + `video.py`, routers `admin_camera_diagnostics.py` + `gateway_diagnostics.py`, `main.py`, `storage/keys.py`, teste novo |
| D02 | Android: forwarder diagnóstico | `diag/DiagConfig.kt`, `CameraDiagnosticsForwarder.kt`, `DiagCloudApi.kt`, `DiagViewModel.kt`; hook mínimo no `EspHttpServer.kt` (capability + 4 rotas diag) |
| D03 | Firmware: foto isolada | `main/diag_camera.{h,c}`, `gateway_client_diag_{poll,frame,ack}`, Kconfig `CAPTURE_DIAG_ENABLE=n`, CMakeLists, hook no `app_main.c` (janela pré-missão com exclusão) |
| D04 | Prévia baixa taxa | Endpoint transitório `/preview` + objeto único + ponteiro que só avança + `latest` com idade/FPS/stale; forwarder com 1 em voo + 1 aguardando + descarte; firmware 1 frame por vez com taxa medida; página com polling 500 ms sem sobreposição |
| D05 | Vídeo curto | `camera_diagnostics/video.py`: 1 por vez, timeout 60 s, concat + durações reais, H.264/yuv420p/faststart, encoder verificado (libx264 ou mpeg4), argv estruturado, tmp privado, ffprobe, idempotente; ffmpeg/ffprobe já na imagem (`infra/docker/Dockerfile.pages-rgb`) |
| D06 | Interface + protocolo real | `apps/admin/app/(admin)/admin/camera-test/page.tsx` (foto 100%/fit/download, comparação de 2, player playsinline, galeria paginada, stale, aba oculta); `__tests__/flows.test.mjs` +1 fluxo; `docs/runbooks/camera-diag-D06-protocolo.md` |
| D07 | Build/deploy/habilitação | `docs/runbooks/camera-diag-D07-deploy.md`; `.env.example` com flags; procedimento por SHA com flag desligada |
| D08 | Desativação/rollback | `docs/runbooks/camera-diag-D08-rollback.md` (sem perda, sem downgrade destrutivo) |

## Verificação executada aqui

- `pytest tests/unit`: **433 passed, 1 skipped** (425 anteriores + 8 novos).
- `ruff check`: verde no escopo do diagnóstico.
- `npm test` (admin): tsc + 6 fluxos verdes (5 anteriores + 1 câmera).
- Migration `0012` importa e encadeia `0011 → 0012`.
- Firmware: `tools/validate_project.py` OK; revisão de headers/tipos feita.
  **Build completo com link NÃO executado aqui** (ESP-IDF sem `python_env`
  neste ambiente); pendente em máquina com IDF íntegro.
- APK/Gradle: código Kotlin adicionado; **build NÃO executado aqui**
  (sem JDK/SDK neste ambiente); pendente de runner.
- Nenhum teste físico (placa/telefone/serviços reais) executado aqui;
  D06-físico, D07-deploy e matriz §7 seguem pendentes de bancada (H2/H4).

## Limites observados (não benchmark)

Taxas/latências reais serão medidas na placa, telefone e rede usados
(VGA alvo 2 fps, latência-alvo 3 s). Nada foi apresentado como ao vivo;
stale >5 s é explícito e o MP4 preserva durações reais de captura.
