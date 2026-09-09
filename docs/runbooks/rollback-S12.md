# Runbook S12 — rollback e entrega

## 1. Quando reverter (S12.1)

Interromper promoção de clientes (Android depois, firmware por último — ordem
inversa do rollout) e registrar a causa quando: readiness 503, processamento
com falha, integração H2 reprovada, ou regressão vs baseline S00.

## 2. Rollback backend (S12.2)

```bash
PREV_IMAGE_TAG=sha-<anterior-compatível> ./scripts/rollback-pages-rgb.sh
```

- Reverte imagens para digests anteriores COMPATÍVEIS (aditivas).
- Preserva banco, outbox (`workflow_outbox` PENDING continua despachável),
  objetos (ORIGINAL imutável), filas e spool Android.
- NUNCA downgrade destrutivo de schema (migrations 0001–0011 são aditivas).

## 3. Painel isolado (S12.3)

Se só o painel falhar e a API estiver `ready`, manter API+worker no ar e reverter
só `pages_to_rgb-admin` para o digest anterior. Não rotacionar credenciais sem
causa concreta.

## 4. APK anterior (S12.4)

- Reinstalar APK anterior SOMENTE com mesma assinatura (keystore operacional —
  ver S09.7: sem keystore existente, release é BLOQUEADA, não improvisada).
- Filas pendentes (Room `pending_frames` não-ACK) permanecem recuperáveis:
  `reconcileLocalSpool` + `reenqueueAllPending` após reinstalação compatível.
- Nunca desinstalar como atalho com fila pendente.

## 5. Pós-rollback (S12.5–S12.6)

1. Retestar retomada exata (hint inválido → 409, sem fallback) e integridade
   (contagem do banco, hashes, RGB mesma revisão/hash).
2. Atualizar `docs/REGISTRO_EXECUCAO_S00_S05.md` (ou sucessor S06–S12),
   contratos e este runbook com evidências, riscos residuais e mudanças de config.
3. Auditoria permanece como histórico (imutável).
