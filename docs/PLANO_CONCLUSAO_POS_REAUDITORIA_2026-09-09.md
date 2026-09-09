# Plano de conclusão pós-reauditoria — servidor, Android e firmware

Data: 09/09/2026  
Escopo: `pagestoaudio_servidor` + `Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1`  
Base: os três planos de 09/09/2026 e `REAUDITORIA_CRUZADA_IMPLEMENTACOES_2026-09-09.md`.

## 1. Veredito e regra de execução

O sistema **não está pronto para novo deploy, APK de produção ou flash da placa**. Os testes unitários existentes passam, mas há defeitos estáticos críticos na ponte Android–ESP, durabilidade, workflow, diagnóstico, CI e empacotamento. Build, instalação, missão física e deploy atuais também não foram comprovados.

Executar as etapas abaixo na ordem. Não promover uma etapa enquanto seu gate estiver vermelho. Em todos os registros, usar separadamente os estados:

- `IMPLEMENTADO`: fonte concluída e revisada;
- `COMPILADO`: build limpo do artefato correspondente;
- `TESTADO_UNITARIO`: testes isolados passaram;
- `TESTADO_INTEGRACAO`: fluxo com banco/storage/Temporal ou protocolo real passou;
- `INSTALADO`: digest/APK/BIN identificado está no destino;
- `APROVADO_FISICO`: evidência de telefone, ESP, câmera, rede e energia reais.

Mocks, inspeção de strings, `-fsyntax-only`, arquivo de procedimento e resposta HTTP 200 não podem ser promovidos para uma categoria superior.

## 2. Estado de partida confirmado

| Área | Estado atual | Bloqueio principal |
| --- | --- | --- |
| Servidor base S00–S12 | Parcial | Workflow nominal, Gate 2 incorreto, lock inválido, despacho pré-commit e R2 incorreto |
| Ponte/Android | Parcial | Discovery/rotas/schemas incompatíveis, identidade e ACK não duráveis |
| Firmware F00–F11 | Parcial | Caminhos sem spool, NVS apagável, HTTP operacional e cursor/ACK incompletos |
| Diagnóstico D00–D08 | Estrutura parcial, flag efetivamente desligada | Controle painel→cloud→Android→ESP desconectado, fila e mídia incorretas |
| Testes | 433 passam, 1 skip; painel 6 passa | Zero testes de integração; painel testa strings |
| Artefatos | BIN 2.4.0 existente | BIN é anterior às fontes diagnósticas; APK final ausente |
| Ambiente observado | PostgreSQL 5432 e HTTP 8081 ativos | readiness em 8081 responde `checks:{}`; sem JDK/SDK Android, IDF no PATH ou COM nesta verificação |
| Git | Servidor `main` em `be34d8a`, diagnóstico não commitado | Firmware cai no repositório ancestral `C:/Users/Lenovo`; risco de stage alheio |

## 3. Etapas obrigatórias

### C00 — Isolar fontes, baseline e versionamento

1. Criar branch exclusiva no servidor a partir de `be34d8a`, sem rebase destrutivo e sem stage global.
2. Inventariar cada arquivo modificado/não rastreado e separar: implementação base, diagnóstico, documentação e alteração preexistente `docs/contracts/RGB_RESULT_V1.md`.
3. Não incluir a alteração preexistente em commit sem revisão explícita de seu diff.
4. Tornar o firmware um repositório independente ou movê-lo para um monorepo escolhido pelo proprietário. Nunca executar `git add`/commit a partir do repositório ancestral do perfil do usuário.
5. Registrar HEAD, diff, toolchains, portas, placa/USB e hashes dos artefatos antes de alterar código.
6. Manter `CAMERA_DIAGNOSTICS` desligado em produção até C08.

**Gate C00:** diffs classificados; branch/repositório corretos; nenhum arquivo alheio staged; baseline reproduzível.

### C01 — Congelar um protocolo único Android–ESP

Corrige RA01–RA03 e prepara RA15.

1. Criar tabela normativa única com discovery, método, rota, headers, corpo, resposta e códigos para HELLO, START, FRAME, CAPTURE_COMPLETE, COMMAND, COMMAND_ACK, RESULT, RGB_EVENT, HEARTBEAT, FAULT e DIAG.
2. Fazer discovery responder exatamente `P2A_GATEWAY_V1 nonce=<eco> port=<porta>` ou alterar ambos os lados para um novo formato versionado; testar nonce e rejeição de replay.
3. Unificar HELLO (`POST /v1/device/hello`) e todas as demais rotas. Não manter aliases silenciosos sem teste de compatibilidade.
4. Encaminhar payloads integrais; remover `{}` fixo em comando e a redução do resultado a `command/cursor`.
5. Separar `esp_device_id`, `android_gateway_id` e origem `ESP32_CAMERA`; preservar `allow_new_session`, `resume_hint` e erros 401/409/422/503.
6. Criar provisionamento explícito e comum de identidade/segredo. Nenhuma rota protegida pode criar credencial por pedido não autenticado.
7. Aplicar autenticação, vínculo de dispositivo/sessão e limite de corpo a todas as rotas protegidas.

**Gate C01:** testes contratuais bidirecionais usam os parsers reais Kotlin/C e comprovam discovery, HELLO, START, captura, ACK, STOP e RGB com os mesmos vetores.

### C02 — Durabilidade, comandos, cursores e recuperação

Corrige RA04–RA06, RA11, RA13–RA14 e RA16–RA17.

1. Android: serializar ingestão por identidade e tornar arquivo + registro Room reconciliáveis antes do ACK. Em retry com arquivo idêntico, recriar/confirmar a linha antes de 208.
2. Executar reconciliação completa antes de abrir discovery/HTTP/readiness. Descobrir arquivos órfãos, linhas sem arquivo e outbox local.
3. Implementar consumidor idempotente da outbox Android; `writeText` isolado não é entrega durável.
4. Firmware: remover o caminho `ram_only`; falha em persistir lote impede upload e preserva fotos/intent anteriores.
5. Proibir substituição/limpeza de lote não conciliado. STOP só finaliza após transferência ou preservação recuperável comprovada.
6. Persistir journal de comando, efeito e ACK. Separar cursor de captura, cursor de resultado RGB e revisão da sequência.
7. Android e firmware só avançam cursor depois de efeito durável **e** ACK confirmado; retry reutiliza bytes/identidade.
8. Servidor persiste intenção de controle e capacidade por origem. STOP/PAUSE têm prioridade sobre captura; não gerar comandos ilimitados por cursor informado.
9. Remover `nvs_flash_erase()` automático em erro de versão/espaço. Implementar recuperação/migração que preserve corrupção para diagnóstico.
10. Tornar FINISHED + RGB pendente uma transição recuperável; não confundir registro corrupto com ausente.
11. Cachear o próximo offset RGB para append O(1) real e separar telemetria observada do high-water mark lógico.
12. Remover despacho Temporal do request antes do commit. Apenas dispatcher separado pode consumir intents commitados.

**Gate C02:** testes de queda em cada fronteira (write/rename/Room/ACK/NVS/spool/commit), reinício e retry provam zero perda, zero recaptura sob a mesma identidade e zero despacho pré-commit.

### C03 — Tornar o workflow realmente operacional

Corrige RA07–RA12.

1. Corrigir `_step_log` para não receber `session_id` duas vezes e adicionar teste que execute cada atividade, não apenas confira o registro.
2. Substituir `sqlalchemy.orm.with_for_update` por `select(...).with_for_update()`, reler e validar o estado sob o lock.
3. Definir e persistir transições intermediárias; `complete_session` não pode saltar de `LOCKED` para `COMPLETED`.
4. Ligar materialização, preprocessamento, OCR, reconstrução, resgate, RAG, solver, verifier, arbiter, TTS, montagem, validação e publicação aos serviços reais existentes.
5. Remover retornos nominais (`0`, `False`, `emitted=True`) quando nenhum efeito ocorreu. Persistir artefatos, tentativas, erros e estados de revisão.
6. Filtrar Gate 2 pelas respostas das questões da sessão atual; testar duas sessões concorrentes.
7. Evitar abrir `UnitOfWork` aninhada chamando uma activity diretamente de outra; extrair serviço interno compartilhado.
8. Resolver bucket R2 uma vez e usar o nome resolvido no PUT/HEAD/GET. Implementar criação imutável atômica ou coordenação equivalente.
9. Tornar status/eventos reais: emitir somente depois do efeito persistido e cercar tudo por cancelamento.

**Gate C03:** uma sessão nova percorre JPEG decodificável → página → OCR → questão → RAG → resposta → Gate 2 → áudio → RGB, com IDs e linhas/objetos verificáveis no banco/storage.

### C04 — Completar o diagnóstico no servidor

Corrige RA22–RA27 e RA30.

1. Criar máquina de estados `REQUESTED → CLAIMED → ACTIVE → STOPPING → DRAINING → COMPLETED|FAILED|EXPIRED|CANCELLED`; estados terminais não retrocedem.
2. Confirmar ACTIVE e COMPLETED somente por ACK físico da ESP. `stop` do admin solicita parada; não fabrica `ack=true`.
3. Usar lock persistente comum por dispositivo para missão e diagnóstico, com constraint defensiva de exclusividade.
4. Centralizar flag, autenticação, gateway/device binding, lease e expiração em create/claim/frame/event/stop.
5. Idempotência por `(diagnostic_id, frame_index)`; mesmo hash retorna a mesma resposta, hash diferente retorna conflito. Validar dimensões decodificadas e modo.
6. Atualizar quota/contadores sob lock; retry conhecido deve ser reconhecido antes da quota de nova ingestão.
7. Armazenar objetos imutáveis por frame. Atualizar `latest` condicionalmente por índice/timestamp de captura, nunca por ordem de chegada.
8. Tirar FFmpeg do request. Criar job durável, idempotente e limitado; exigir H.264 aprovado, conjunto completo, timeout, cancelamento e reap de subprocesso.
9. Tornar retenção finita/idempotente, incluir MP4/prévia e separar bytes recebidos de bytes ainda armazenados; agendar o job.

**Gate C04:** concorrência, retry, expiração, STOP, quota, frames fora de ordem e conversão reiniciada passam contra PostgreSQL e storage reais de teste.

### C05 — Completar Android e firmware diagnósticos

Corrige RA18–RA21.

1. Instanciar e ligar `CameraDiagnosticsForwarder` no `EspBridgeService`; integrar ciclo cloud de pedidos pendentes e resposta local completa.
2. Integrar `DiagViewModel` à UI/ciclo operacional ou removê-lo se o controle for exclusivamente cloud; não deixar código morto.
3. Criar uma única fila com roteamento explícito `EXAM|HANDWRITTEN|DIAG`. O worker de missão nunca recebe `diag:*`.
4. Persistir metadados DIAG suficientes para recuperar foto/clipe depois de reboot e depois do fim da aquisição.
5. Prévia usa buffer imutável de tamanho fixo; frame transitório consome identidade ao capturar, mesmo quando o envio falha.
6. Foto/clipe preservam os mesmos bytes até ACK de identidade/hash ou falha terminal conciliada.
7. Firmware implementa lease, prazo local finito, STOP imediato, ACK real via `gateway_client_diag_ack` e restauração integral de câmera/energia.
8. Remover loops logicamente infinitos e a janela de poll única pré-missão; diagnóstico não pode bloquear a missão indefinidamente.

**Gate C05:** pedido criado no painel chega sem intervenção manual à ESP, retorna frames, respeita STOP/timeout/reboot e libera o dispositivo para missão.

### C06 — Corrigir galeria, player e estado ao vivo

Corrige RA28–RA29.

1. Criar rota/URL autorizada para o JPEG exato de cada frame e MP4 exato do clipe; não usar `latest.jpg` para todas as linhas nem fragmento em endpoint JSON.
2. Implementar comparação visual, download correto, histórico e paginação completa.
3. Calcular `live` somente após primeiro frame recente + heartbeat recente + estado ACTIVE.
4. Em erro de rede, envelhecer/inativar o estado; polling atualiza metadados e status, para em terminal/aba oculta e é cancelável.
5. Foto e clipe fazem polling até terminal com deadline explícito; timeout de UI não é sincronização.

**Gate C06:** Playwright executa login de ambiente de teste, foto, preview, STOP, clipe, player, download, comparação, paginação, stale e erro de rede; Console sem erro e requests/status/payloads conferidos.

### C07 — TLS e segurança de produção

Corrige RA02, RA15 e parte de RA25.

1. Implementar TLS ponta a ponta no servidor local Android e cliente ESP, com CA/pin/identidade e relógio provisionados.
2. Criar provisionamento reproduzível do mesmo segredo na ESP e Android, com rotação e revogação; nunca logar segredo.
3. Build `Production` deve falhar se HTTP, CA ausente, diagnóstico ou credencial de bancada estiverem ativos.
4. Build `Diagnostic` só pode instalar no dispositivo de teste identificado e continua autenticado.
5. Testar gateway falso, certificado/host/relógio inválidos, segredo errado, replay e rota cruzada.

**Gate C07:** captura e diagnóstico funcionam por TLS válido; cada caso inválido falha fechado sem apagar dados.

### C08 — Builds reproduzíveis e artefatos coerentes

Corrige RA31 e RA35.

1. Instalar/pinar JDK, Android SDK/Build Tools e ESP-IDF/toolchain suportados; registrar versões.
2. Firmware: usar diretórios/sdconfigs separados (`build-prod`, `build-diag`).
3. `Diagnostic` deve ligar `CONFIG_CAPTURE_DIAG_ENABLE=y`; `Production` deve confirmar `# ... is not set`. Ambos verificam configuração pós-CMake e `$LASTEXITCODE` de cada comando.
4. Não reutilizar o BIN 2.4.0. Incrementar versão após as correções e gerar manifestos com commit, config, toolchain, tamanho e SHA-256.
5. Executar build limpo e rebuild idêntico de produção e diagnóstico; validar que os binários diferem nas flags esperadas.
6. Android: `testDebugUnitTest`, lint, `assembleDebug`, `bundle/assembleRelease`, assinatura configurada fora do Git e hashes do APK/AAB.
7. Servidor/admin/worker: gerar imagens pelo SHA completo, registrar digests e SBOM/scan conforme CI existente.

**Gate C08:** fontes, commits, configurações, imagens, APK e BIN formam uma cadeia de identidade verificável e reproduzível.

### C09 — Integração real e CI bloqueante

Corrige RA32 e prepara RA33–RA34.

1. Criar testes reais em `tests/integration/test_*.py`; coleta zero deve falhar a CI.
2. Subir PostgreSQL, Temporal e storage de teste; aplicar migrações `0001…0012` em banco vazio e upgrade de cópia restaurável.
3. Exercitar concorrência, locks, outbox pós-commit, worker, R2, workflow completo, cancelamento e diagnóstico.
4. Substituir testes de strings do painel por testes funcionais; manter inspeções de contrato apenas como complemento.
5. Adicionar testes Kotlin do bridge e protocolo com vetores gerados pelos parsers C; executar instrumentação quando necessária.
6. CI do mesmo SHA deve exigir: Python, lint/typecheck, integração, admin E2E, Android, build firmware prod/diag e scans. Deploy depende de todos.

**Gate C09:** todos os jobs obrigatórios do mesmo SHA estão verdes, com casos reais coletados e artefatos publicados por digest.

### C10 — Bancada física e falhas induzidas

Corrige RA36 e conclui S10/F09/D06.

1. Reinventariar no dia do teste: telefone, Android/SDK, ESP32-S3 N16R8, sensor OV2640, porta COM, fonte, hotspot e servidor/digests. Não reutilizar o bloqueio antigo sem nova sondagem.
2. Identificar chip/MAC/flash sem apagar; fazer `read_flash` integral e testar restauração do backup.
3. Instalar primeiro APK + BIN diagnóstico no dispositivo de teste; conferir hashes/versões nos logs.
4. Executar matriz do plano firmware: duas capturas, pausa/retomada/STOP, rede lenta/queda, reset e corte de energia em cada fronteira, lotes cheios, RGB, brownout e rollback.
5. Executar matriz DIAG: foto/hash, preview/stale/FPS, clipe/duração, aba fechada, ocupado, concorrência, quota/auth/cancelamento e retorno à missão.
6. Medir JPEG máximo, heap/PSRAM/bloco livre, latência, fila, CPU/memória do telefone, bytes/ops e corrente por fase; calibrar limites sem truncamento silencioso.
7. Repetir a missão base com diagnóstico compilado mas desligado para provar ausência de regressão.

**Gate C10:** evidências contêm IDs, hashes não secretos, versões, logs, medidas e resultado de cada caso. Só então marcar `APROVADO_FISICO`.

### C11 — Commit, push, staging e deploy por digest

Corrige RA33–RA34 e conclui S11–S12/D07–D08.

1. Fazer commits pequenos por etapa, com testes no corpo. Revisar diff e staged files antes de cada commit.
2. Push da branch; nunca push direto de worktree sujo para `main`. Abrir/revisar PR e proteger merge pelos gates C09/C10 aplicáveis.
3. Corrigir tag curta versus SHA completo: preferir digest imutável em Compose/deploy. O digest implantado deve ser o publicado pela CI.
4. Corrigir detecção do projeto Compose instalado, `extra_hosts`/conectividade do worker e conversão de `DATABASE_URL` SQLAlchemy para formato aceito por `pg_dump`.
5. Fazer backup e ensaio de restore antes da migration. Implantar primeiro em staging, aplicar migration e executar smoke profundo.
6. Readiness deve fazer I/O limitado com DB/storage e exigir poller do worker; `not_configured`/`no_pollers` não pode ser ready em produção.
7. Smoke confere release/commit/digest, migração, worker, upload/download, workflow, painel e um fluxo DIAG controlado. Qualquer 200 genérico é insuficiente.
8. Promover o mesmo digest para produção, repetir smoke e observar filas/erros. Executar rollback automático no primeiro gate vermelho.
9. Somente depois instalar BIN Production aprovado na placa-alvo. Preservar backup, NVS e spool.

**Gate C11:** produção informa exatamente o digest aprovado; smoke completo e missão curta passam; rollback foi ensaiado e permanece disponível.

### C12 — Fechamento e instruções de uso

1. Atualizar README/runbooks com URL, provisionamento, inicialização automática, estados, operação do painel, modo diagnóstico, retenção, backup/restore e rollback.
2. Unificar a decisão de início automático com retomada prioritária nos documentos normativos; remover marcações contraditórias de “pendente”, sem apagar o histórico.
3. Publicar matriz final dos três planos com evidência por item e as seis categorias da seção 1.
4. Listar pendências residuais reais, responsável e risco. Não usar “tudo concluído” se algum gate estiver bloqueado.

**Gate C12:** outra pessoa consegue reproduzir build, instalar, operar, diagnosticar e reverter usando apenas os runbooks e artefatos identificados.

## 4. Testes mínimos que precisam ser adicionados

- Unitários: `_step_log`, transições, Gate 2 por sessão, bucket R2 resolvido, idempotência/frame DIAG, retenção finita e perfil de build.
- Contrato: vetores comuns C/Kotlin/Python para todas as rotas, limites, códigos e hashes.
- Integração: banco real, migration, outbox pós-commit, Temporal/poller, storage e workflow completo.
- Android: reconciliação arquivo↔Room, roteamento de fila, cursor/ACK e bridge reiniciada.
- Firmware: testes host quando possível e matriz de bancada para NVS/spool/comandos/RGB/TLS/DIAG.
- Navegador: E2E real da galeria/player/live/stale/paginação e correlação de Console/Network com API/banco.
- Deploy: restore de backup, digest ativo, readiness profunda, rollback e missão curta.

## 5. Critério final de aceitação

O trabalho termina somente quando:

1. RA01–RA36 estiverem fechados com link para diff e teste;
2. os três planos originais tiverem matriz atualizada, sem DONE nominal;
3. C00–C12 estiverem verdes;
4. commits/digests/APK/BIN corresponderem exatamente ao instalado;
5. missão base, diagnóstico limitado, falhas induzidas e rollback tiverem evidência real;
6. nenhum dado/segredo do usuário ou arquivo alheio tiver sido incluído no Git ou nos artefatos.

## 6. Execução complementar após falha de cota do Open Code (09/09/2026)

Implementações aplicadas nesta retomada local:

- máquina de estados: `SELECT ... FOR UPDATE` antes da validação e auditoria de transições inválidas na mesma transação;
- workflow: atividade idempotente `advance_session_state` entre etapas, Gate 1/Gate 2 respeitados e áudio não publicado quando validação/publicação falhar;
- Gate 2: contagem de `FinalAnswer` limitada às perguntas da sessão;
- R2: PUT usa o bucket físico resolvido;
- diagnóstico: lock por dispositivo/diagnóstico, claim cloud antes de anunciar `ACTIVE`, `STOPPING` só vira `COMPLETED` após ACK, evento `FAILED` terminal, duplicata verificada antes da quota, dimensões JPEG decodificadas e retenção sem loop infinito;
- painel: cada foto usa seu próprio frame original e o clipe usa endpoint MP4 real;
- Android/ESP: assinaturas do bridge alinhadas, payloads completos, heartbeat/RGB/fault, polling de pedidos, forwarder ligado ao serviço e DIAG roteado pelo WorkManager;
- firmware: defaults de diagnóstico habilitam `CONFIG_CAPTURE_DIAG_ENABLE` apenas no perfil de bancada, com diretórios `build-prod`/`build-diag` separados e checagem de exit code.

Validação executada: `ruff check src/pages_to_audio apps/api` OK; `pytest -q` com `PYTHONPATH=.`: **433 passed, 1 skipped** (permanece um `RuntimeWarning` externo de `Connection._cancel`); `npm test` do painel: **6 passed**; `tools/validate_project.py`: **Validação estrutural OK**. Não foi possível executar o build Android (JDK ausente), build/link do ESP32 (IDF ausente), teste físico, deploy ou flash.

## 7. Prompt para executar no Open Code

```text
Leia integralmente:
1) C:/Users/Lenovo/Downloads/pagestoaudio_servidor/docs/REAUDITORIA_CRUZADA_IMPLEMENTACOES_2026-09-09.md
2) C:/Users/Lenovo/Downloads/pagestoaudio_servidor/docs/PLANO_CONCLUSAO_POS_REAUDITORIA_2026-09-09.md
3) os três planos originais citados nesses documentos.

Execute C00–C12 na ordem, sem pular gates e sem declarar integração/físico/deploy com mocks, inspeção de strings ou procedimento escrito. Corrija primeiro RA01–RA36. Não faça push, deploy ou flash antes dos gates correspondentes.

No servidor, crie branch própria a partir de be34d8a, faça stage seletivo e preserve a alteração preexistente docs/contracts/RGB_RESULT_V1.md até revisar seu diff. O diagnóstico atual está fora dos commits be34d8a/c282758: não o misture em um commit opaco. Faça commits pequenos por etapa, com testes e arquivos staged registrados.

No firmware, pare antes de qualquer git add/commit: a pasta atualmente pertence ao repositório ancestral C:/Users/Lenovo. Crie/use um repositório independente ou o destino que o proprietário indicar; nunca commite arquivos do perfil do usuário. Não reutilize o BIN 2.4.0, pois ele é anterior às fontes diagnósticas.

Use build-prod e build-diag separados; confirme CAPTURE_DIAG_ENABLE=n/y respectivamente. Refaça testes unitários, integração real, E2E de navegador, build Android, builds/link do firmware e bancada. Depois publique por digest imutável, faça staging, backup/restore, smoke profundo, produção e rollback conforme C11.

Ao final de cada etapa, entregue: status nas seis categorias, diff, comandos, saídas, hashes, bloqueios atuais e próximo gate. Se faltar credencial, hardware ou decisão de destino Git, pare apenas no gate afetado e continue todo trabalho seguro independente.
```
