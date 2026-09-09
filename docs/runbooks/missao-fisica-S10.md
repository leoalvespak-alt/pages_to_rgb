# Runbook S10 — missão física integrada (H2)

Status: PROTOCOLO PRONTO, execução BLOQUEADA até H1 dos dois projetos
(telefone + ESP reais, credenciais e serviços disponíveis).

## 1. Registro pré-missão (obrigatório)

| Item | Valor |
|---|---|
| Commit servidor | `git rev-parse HEAD` |
| Digest imagens API/worker/painel | `api.digest`, `admin.digest` (artefatos CI) |
| APK instalado | `versionName` + `sha256(apk)` |
| BIN/ELF ESP | versão + hash do executor firmware |
| Revisão contrato | P2A-INTEGRACAO-2026-09-09 r1 |
| IDs missão | session_id, device_id, gateway_id, horário UTC |

## 2. Missão base (documento físico de referência conhecido)

1. Provisionar gateway (X-Gateway-Id + segredo) e dispositivo ESP (segredo local).
2. Discovery UDP 8786 → confirma `gateway_id`; TLS/HTTPS 8787.
3. Start com `resume_hint=false`; anotar `session_id`/`cursor` autoritativos.
4. Executar missão com MÚLTIPLOS comandos até o total previsto (nunca 1 upload
   como prova de missão de 30 imagens).
5. Conferir bytes/hashes e contagem ÚNICA do primeiro ao último frame
   (`capture-complete` usa contagem do banco; `declared_frames` só auditoria).
6. Acompanhar OCR → Gate 1 → resolução → Gate 2 → publicação reais no painel
   (polling 5 s enquanto ativa; paginação de fotos/registros).
7. Reproduzir RGB na placa; comparar ordem/quantidade/cores com a referência,
   incluindo resultado extenso (string contígua A–E, perfil low-power 12%/150/2850).

## 3. Cenários de recuperação (todos obrigatórios)

- [ ] Perda de internet do Android com rede local ativa → ACKs locais duráveis,
      reenvio idempotente (200/208), sem 409 indevido, sem recaptura sob identidade aceita.
- [ ] Reinício do app + restauração da internet → `reconcileLocalSpool`, cursor
      persistido, comandos não duplicados (ACK de efeito).
- [ ] Pausa/resume e STOP durante upload; frame em voo no fechamento
      (fechamento fica PENDENTE, nunca fecha com pendências).
- [ ] Reinício dispatcher/worker mid-processing → outbox PENDING despacha 1 vez
      (ID determinístico; AlreadyStarted idempotente).
- [ ] Credencial/certificado incorretos e sessão alheia → 401/403/404, sem vazamento
      de token nem aceitação cruzada.
- [ ] Cancelamento antes da publicação (nada publicado depois) e após reprodução
      offline iniciada (sem promessa de interrupção instantânea).

## 4. Métricas (comparar com baseline S00; investigar regressão antes da release)

Latência por estágio, filas (spool/outbox), CPU/memória serviços + telefone,
erros por categoria, resultado final. Falha real nunca vira retorno fabricado:
etapa sem hardware/provider fica PENDENTE com evidência, não "passou".
