# D07 — build, deploy, instalação e habilitação limitada

Referência: PLANO_ADICIONAL_TESTE_CAMERA_2026-09-09 §D07.

## 1. Revisão e testes (antes de qualquer deploy)

1. `git status/diff`: mudanças concentradas em diagnóstico + hooks mínimos
   (servidor: `camera_diagnostics/`, 2 routers, migration 0012, settings,
   keys, página `camera-test`; Android: `diag/` + hook no `EspHttpServer`;
   firmware: `diag_camera.*`, 3 funções `gateway_client_diag_*`, Kconfig,
   CMakeLists, hook no `app_main`).
2. Servidor: `pytest tests/unit` (433 passed + novos de diagnóstico), `ruff`,
   `npm test` no admin (tsc + 6 fluxos), migration 0012 revisada (só cria).
3. Android: build Gradle/APK em runner com JDK 17/SDK (indisponível neste
   ambiente — pendente de runner).
4. Firmware: `tools/build_windows.ps1 -Profile Production` (padrão, diag OFF)
   e `-Profile Diagnostic` (teste). Build completo com link OK nesta máquina:
   PENDENTE — ambiente ESP-IDF sem python_env (ver registro D00–D08);
   validação estrutural OK + revisão de tipos/headers feita.
5. Registrar commits, hashes de APK/BIN, digests de imagens e revisão do
   contrato P2A-CAMERA-DIAG-2026-09-09 rev.1.

## 2. Deploy (procedimento corrigido do projeto, flag DESLIGADA)

1. Push + deploy pelo workflow corrigido (por SHA, sem `latest`), backup de
   banco antes, `migrate` uma vez (0012 aditiva, compatível), smoke
   `/ready` + versão.
2. Nenhuma migração antiga editada; nenhum objeto de missão tocado.
3. Instalar APK e firmware na identidade física correta (CAM-001/teste),
   preservando NVS, spool e dados. Verificar readiness e versões efetivas.
4. Habilitar diagnóstico SOMENTE no dispositivo de teste:
   `CAMERA_DIAGNOSTICS_ENABLED=true` (servidor), `diagnosticsEnabled`
   (Android), firmware Diagnostic (CONFIG_CAPTURE_DIAG_ENABLE=y).
   Demais dispositivos: tudo desligado; abrir o painel não inicia câmera.

## 3. Execução remota + regressão

1. Executar foto, clipe 10 s e prévia 60 s pelo domínio HTTPS real, em PC e
   celular (página `/admin/camera-test`).
2. Reexecutar missão normal + standby; registrar comparação com D00.
3. Entrega (plano §8): instrução curta de uso, versões instaladas, fotos
   originais de referência, um clipe, evidência da prévia real,
   taxas/latências medidas, consumo/quota e resultado da regressão.
