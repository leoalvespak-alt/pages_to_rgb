# D08 — desativação e rollback do diagnóstico

Referência: PLANO_ADICIONAL_TESTE_CAMERA_2026-09-09 §D08.

## 1. Desativação (sem perda de dados)

1. Desabilitar novas ativações: `CAMERA_DIAGNOSTICS_ENABLED=false`
   (servidor), `diagnosticsEnabled=false` (Android). Firmware Production
   (CONFIG_CAPTURE_DIAG_ENABLE=n) na próxima janela — sem flash emergencial.
2. `POST /admin/camera-diagnostics/{id}/stop` nas ativas; aguardar prazo
   local (até 60 s + 30 s de autorização). Confirmar câmera liberada e
   retorno à política de energia principal (gateway ACK + ESP deinit).
3. Expurgar só temporários de diagnóstico (`diagnostics/…` verificadas,
   transitórios >10 min, sobras de conversão); fotos/clipes salvos seguem
   retenção de 7 d / 100 MiB com indicação na interface.
4. Registrar causa, evidência e teste normal posterior (missão + standby).

## 2. Rollback (se necessário, sem apagar dados)

1. Servidor: restaurar imagem/APK/BIN anteriores pelo procedimento principal
   (por SHA/digest). Migration 0012 NÃO é desfeita com perda: tabelas
   `camera_diagnostics*` permanecem (vazias ou com histórico); nenhum objeto
   de missão é alterado.
2. Android: APK anterior com a mesma assinatura.
3. Firmware: slot OTA anterior, sem apagar NVS/spool/dados; leitor v4/v3
   e NVS/RGB convivem (ver ROLLBACK_2026-09-09).
4. Reteste pós-rollback: missão completa + standby. Flag continua desligada.
