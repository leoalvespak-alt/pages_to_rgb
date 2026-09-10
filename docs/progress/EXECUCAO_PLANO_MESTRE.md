# Execução do plano mestre

> Gerado por scripts/plan_control.py. Não editar manualmente.

- Atualizado em: 2026-09-10T03:05:54+00:00
- Progresso: **10/14 gates**
- Próximo gate: **G17**

## Gates

| Ordem | Gate | Estado | Alvo | Descrição | Evidências |
|---:|---|---|---|---|---:|
| 1 | G00-A | VALIDADO_LOCAL | VALIDADO_LOCAL | Baseline, caminhos, Git e diffs preservados | 2 |
| 2 | G09 | VALIDADO_LOCAL | VALIDADO_LOCAL | Repositório e branch legítimos do firmware | 15 |
| 3 | G01 | VALIDADO_LOCAL | VALIDADO_LOCAL | Migração aditiva e persistência | 23 |
| 4 | G02 | VALIDADO_LOCAL | VALIDADO_LOCAL | Matriz OV2640 confirmada | 3 |
| 5 | G03 | VALIDADO_LOCAL | VALIDADO_LOCAL | Backend de capacidades e perfis | 16 |
| 6 | G04 | VALIDADO_LOCAL | VALIDADO_LOCAL | Upload, original e telemetria | 14 |
| 7 | G05 | VALIDADO_LOCAL | VALIDADO_LOCAL | Backend RGB físico | 19 |
| 8 | G06 | VALIDADO_LOCAL | VALIDADO_LOCAL | Android bridge e spool duráveis | 60 |
| 9 | G07 | VALIDADO_LOCAL | VALIDADO_LOCAL | Onda integrada de implementação | 25 |
| 10 | G13 | VALIDADO_LOCAL | VALIDADO_LOCAL | Validação local integrada e candidata | 13 |
| 11 | G17 | EM_EXECUCAO | VALIDADO_LOCAL | Release, commits, PRs e CI | 3 |
| 12 | G19 | PENDENTE | VALIDADO_PRODUCAO | Deploy e instalações piloto | 0 |
| 13 | G22 | PENDENTE | VALIDADO_PRODUCAO | Campanha física e produção integrada | 0 |
| 14 | G24 | PENDENTE | VALIDADO_PRODUCAO | Documentação e fechamento final | 0 |

## Bloqueios ativos

- Nenhum.

## Resumos concluídos

- **G00-A**: Caminhos reais, diffs preexistentes, branches, HEADs e remotes reconfirmados e registrados; nenhum arquivo alterado pelo gate.
- **G09**: Repositório independente legítimo criado e publicado; topo Git exato, branch main padrão/sincronizada, baseline e decisão documentados, árvore limpa, sem builds/secrets/NVS/BIN Diagnostic.
- **G01**: Migração 0013 aditiva implementada; modelos/telemetria/perfis/comandos RGB auditáveis; Alembic 0003->0013 aplicado na instância documentada; banco vazio e cadeia representativa validados; downgrade 0013->0012 e re-upgrade ensaiados preservando legado; integridade/índices aprovados; 442 testes passaram; rollback lógico documentado.
- **G02**: Matriz OV2640 dedicada criada com 59 recursos individuais e 7 colunas; datasheet v1.6, esp32-camera 2.1.7 com commit/tag e component_hash, sensor.h/ov2640.c, ESP32-S3 e CameraWebServer citados; decisões de produto conservadoras, mensagens obrigatórias e exclusão de Vídeo registradas.
- **G03**: API CameraCapabilitiesV1 e perfis imutáveis OCR/PHOTO implementados; migração 0013 validada pelo G01; feature flag v2 desligada; snapshot/auditoria/solicitado-vs-efetivo e incompatibilidade de firmware cobertos; 450 testes passaram.
- **G04**: Upload validado com SHA origem/banco/storage original, derivado OCR separado e imutável, retry idempotente/conflitante, telemetria completa, identidade page/frame, ordem lógica e capture-complete autoritativo; 454 testes passaram.
- **G05**: Backend RGB físico implementado e validado localmente: comandos por dispositivo, validação RGB/hex e duração, máquina de estados com eventos duráveis, timeout auditado, idempotência, STOP sem falsificar OFF, exclusão mútua com sequência real, rotas admin/gateway autenticadas, adaptador legado e documentação; 466 testes passaram, 1 foi ignorado.
- **G06**: JVM aprovado e bridge/spool implementados; SDK Android e AVD adb validados. Teste instrumentado foi preparado/iniciado e fica pendente para a etapa final com depuração USB, conforme ordem explícita do usuário; pendência não é declarada como aprovação.
- **G07**: Frentes Android/painel/firmware Production implementadas e cobertas por checagens rápidas; painel typecheck e contratos 6/6; Android testDebugUnitTest BUILD SUCCESSFUL (29 tasks); backend ruff limpo; firmware Production ESP-IDF 6.0.2 + esp32-camera 2.1.7 BUILD SUCCESSFUL e artefatos build-prod gerados; git diff --check limpo.
- **G13**: Validação integrada concluída: backend pytest 470 passed/1 skipped, Ruff e Mypy canônicos da CI aprovados; integração canônica executada sem casos coletados; painel npm ci/typecheck/test 6/6/build aprovados; Android testDebugUnitTest + assembleDebug aprovados; firmware Production único fullclean/reconfigure/build com ESP-IDF 6.0.2 e esp32-camera 2.1.7, artefatos/hashes/configuração registrados.

## Retomada

    rtk python scripts/plan_control.py verify
    rtk python scripts/plan_control.py status
    rtk python scripts/plan_control.py next
