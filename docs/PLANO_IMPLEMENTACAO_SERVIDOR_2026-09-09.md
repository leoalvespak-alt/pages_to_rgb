# Plano de implementação e correção — servidor e Android

Data: 09/09/2026. Execução futura por um chat IDE neste projeto.
Raiz: C:/Users/Lenovo/Downloads/pagestoaudio_servidor.
Escopo: API, banco, storage, Temporal/worker, providers, painel, Android, CI, publicação e deploy.
Estado deste documento: planejamento; nenhuma etapa abaixo é declarada executada por sua inclusão.

## 1. Instrução de execução

Ler AGENTS.md, CLAUDE.md, a [auditoria do servidor](AUDITORIA_TECNICA_COMPLETA_2026-09-09.md) e o [contrato consolidado](contracts/INTEGRACAO_CONSOLIDADA_2026-09-09.md). Executar etapas na ordem das dependências; registrar alterações, testes, versões e impedimentos concretos. Não reabrir decisões já fixadas no contrato.

A ponte ESP local pertence ao Android deste repositório. Não implementar servidor cloud diretamente no firmware. Preservar migrações aplicadas, dados existentes, imagens ORIGINAL, segredos e alterações de terceiros. Produção não pode usar atividade fake nem storage em memória. Não considerar testes unitários como aceite de funcionamento real.

O plano correspondente está em C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/docs/PLANO_IMPLEMENTACAO_FIRMWARE_2026-09-09.md. Os marcos H0–H4 no contrato definem a coordenação. Um chat não deve editar código do outro projeto enquanto o outro executor o modifica.

## 2. Critérios de conclusão

- Todas as ocorrências A01–A35 possuem correção ou decisão explícita justificada e evidência; problemas críticos operacionais não podem ser dispensados.
- Android oferece ponte real, autenticada e durável; não há caminho ESP que termine em stub.
- Captura física chega ao storage real, processamento real produz resultado válido e a ESP reproduz a sequência correta.
- Retry, duplicata, queda de rede, reinício e cancelamento preservam identidade, dados e estado.
- API, worker, painel e APK são compilados a partir de versões identificadas; push, publicação e deploy são confirmados.
- Readiness verifica dependências necessárias. HTTP 200 genérico e /live não são prova de deploy.
- Evidências de release incluem commit, imagens/digests, migrações, APK, configuração não secreta, endpoints e execução real.

## 3. Etapas

### S00 — Baseline e ambiente real

1. Registrar git status, branch, HEAD, remote e alterações existentes. Referência auditada: main, commit a6b2deaad3493d6ff4f5821008a2ead93ca20d33, origin https://github.com/leoalvespak-alt/pages_to_rgb.git. Confirmar novamente; não assumir ausência de mudanças.
2. Inspecionar as instruções atuais. Usar prefixo rtk nos comandos, conforme ambiente. Criar branch codex/ apropriada quando necessário, sem descartar trabalho anterior.
3. Identificar Python de produção 3.12, Node 22, JDK 17, SDK Android, Docker, banco, storage e Temporal efetivamente disponíveis. Não usar resultado obtido em Python 3.14 como validação suficiente do container 3.12.
4. Inventariar nomes de variáveis e localização de credenciais sem imprimir valores. Identificar projeto Compose existente, volumes, rede, domínio e instalação Temporal antes de alterar infraestrutura.
5. Separar sessões e objetos de validação dos dados de uso normal. Definir IDs rastreáveis e retenção das evidências; não apagar produção como preparação de teste.
6. Medir baseline: latência de upload, tamanho/quantidade de JPEGs, tamanho de filas, tempo por estágio, memória/CPU de serviços e consumo do telefone. Registrar indisponibilidades com causa observada.
7. Criar registro de execução com tabela etapa/commit/evidência/resultado. Marcar como não executado o que depender de hardware, acesso ou provider ausente.

**Aceite:** ambiente e baseline identificados; nenhuma dependência indisponível é substituída silenciosamente por fake.

### S01 — Contratos, autenticação e schemas compartilhados

Arquivos-alvo: modelos e rotas de apps/api, autenticação em src/pages_to_audio/auth, DTOs/interceptors do Android e docs/contracts.

1. Implementar os campos e traduções da seção 3 do contrato consolidado: start/resume, comando versus status, resultado, eventos, JPEG bruto versus multipart e capture-complete JSON versus query.
2. Preservar compatibilidade aditiva dos endpoints existentes durante rollout. Atualizar OpenAPI e exemplos com limites, erros e semântica de ACK.
3. Enviar Authorization e X-Gateway-Id no cloud. Provisionar identidade/configuração real no aplicativo; remover segredo vazio e identidade fixa como configuração operacional.
4. Vincular gateway, dispositivo e sessão; negar acesso cruzado a upload, comandos e resultados.
5. Validar números positivos, limites de índices, ratios e enums. Validar JPEG real e dimensões; limitar corpo antes de carregar conteúdo integralmente na memória.
6. Aplicar IDs compatíveis com ESP sem truncar nem reduzir globalmente colunas legadas. Cursor deve ser inteiro exato no limite acordado.
7. Implementar retomada exata: hint inválido/encerrado não seleciona outra sessão silenciosamente. Devolver resumed, cursor e resolução de pendências autoritativos.
8. Diferenciar ausência de configuração, null de limpeza e valor explícito. Quantidade de questões omitida herda configuração; default do DTO não a encobre.
9. Cobrir contrato com testes de serialização e requisições reais à API: autorização errada, limite excedido, sessão alheia, retomada encerrada, JPEG inválido e duplicata.

**Aceite H0:** firmware e Android compartilham os mesmos exemplos válidos/erros; nenhum sucesso depende de campos adivinhados.

### S02 — Durabilidade de frames, fechamento, comandos e outbox

Arquivos-alvo: src/pages_to_audio/capture, storage, models, migrations e rotas gateway.

1. Adicionar novas migrações para restrições e estado durável necessários; não editar migração aplicada.
2. Garantir unicidade sessão/capture_id/frame_index. Mesmo hash retorna confirmação idempotente; hash diferente retorna 409 sem substituir ORIGINAL.
3. Implementar conciliação objeto já gravado/linha ainda ausente após falha de commit. Operação repetida precisa concluir vínculo do mesmo objeto.
4. Eliminar fallback de storage em memória em produção. Inicialização e operação falham explicitamente quando o provider configurado estiver indisponível.
5. Aplicar imutabilidade por papel lógico do bucket, inclusive nomes customizados. Não interpretar todo erro de HEAD como inexistência. Usar operação condicional suportada pelo provider ou exclusão/serialização comprovada; evitar corrida check-then-write.
6. Calcular contagem por frames únicos confirmados. capture-complete não sobrescreve contagem com número declarado pelo cliente.
7. Impedir novos frames após fechamento; permitir confirmação idempotente de duplicatas já conhecidas. Definir claramente estados que ainda permitem anexação.
8. Persistir comandos e ACKs. GET não avança cursor nem alterna demonstrações PAUSE/PROBE/PING. Implementar long-poll limitado e seleção de STOP/RESUME sem bloqueio pela pausa.
9. Na transação de fechamento, congelar conjunto de entrada e gravar evento outbox. Dispatcher com ID de workflow determinístico envia após commit e mantém retry observável.
10. Cancelamento deve persistir cerca de cancelamento, solicitar cancelamento do workflow e impedir publicação/avanço tardio. Conclusão RGB histórica não reabre sessão.
11. Validar em banco/storage reais: falha entre gravação e commit, duplicata concorrente, cancelamento durante processamento e reinício do dispatcher. Usar ambiente de validação controlado.

**Aceite:** nenhum ACK falso, nenhuma contagem inflada, nenhum fechamento perdido e nenhuma reativação após cancelamento.

### S03 — Ponte Android real para ESP

Arquivos-alvo: apps/gateway-android; substituir o stub Esp32GatewayCaptureSource e integrar o modo ESP na interface.

1. Implementar serviço local UDP 8786 e HTTPS 8787 com ciclo de vida apropriado ao Android. Anunciar capacidades e identidade, sem tratar discovery como autenticação.
2. Implementar provisionamento de confiança TLS e segredo por dispositivo, usando armazenamento protegido do Android. Validar identidade estável com hotspot de IP variável e política de relógio/rotação compatível com ESP.
3. Implementar handlers locais de HELLO, start, comandos, upload, capture-complete, resultado e eventos exigidos pelo cliente. HELLO repetido não altera estado de domínio nem rebaixa processamento.
4. Traduzir explicitamente chamadas locais para cloud conforme S01. Nenhuma transformação de JPEG antes de encaminhar; preservar bytes/hash.
5. Implementar spool persistente com arquivos e Room: arquivo temporário, escrita concluída, publicação atômica, registro e recuperação de discrepâncias antes do ACK.
6. Validar limites antes de aceitar. Responder ACK durável somente após posse recuperável; duplicatas retornam a mesma identidade/hash.
7. Manter fila cloud persistente, retry com backoff limitado, categorias de erro e reconciliação. Falta de arquivo local não entra em retry infinito sem diagnóstico e resolução.
8. Persistir resultado e outbox de eventos antes de confirmar ao firmware quando houver transferência de responsabilidade.
9. Exibir no app recebido localmente, confirmado cloud, fechamento pendente e erro permanente como situações distintas.
10. Habilitar modo ESP somente após o serviço estar pronto. Tratar permissões, notificações, tela apagada, retomada do app, mudança de rede e encerramento do serviço.
11. Instalar APK candidato em telefone real; comprovar discovery, TLS, upload durável, reinício e encaminhamento cloud. Nenhum mock_gateway participa deste aceite.

**Aceite H1 parcial:** telefone funciona como ponte real, inclusive após reinício, e não perde frames já confirmados localmente.

### S04 — Captura Android, fila e controle de sessão

1. Reutilizar binding CameraX durante sessão, evitando rebind por frame.
2. Retirar espera de foco, EXIF, hash e I/O bloqueantes da thread principal. Usar APIs assíncronas e executor adequado, com cancelamento observável.
3. Ao encerrar: parar produtor de comandos/captura, aguardar operação em voo, persistir intenção, drenar fila e somente então efetivar fechamento cloud.
4. Tratar Result.failure efetivamente, inclusive quando nenhuma exceção é lançada. Timeout de 30 s não autoriza fechar sessão com pendências.
5. Avançar cursor após efeito durável. Em reinício, recuperar comando/ACK e evitar execução duplicada com nova imagem.
6. Atualizar contadores a partir dos ACKs correspondentes; não chamar captura concluída antes das confirmações requeridas.
7. Limpar sessão ativa apenas quando a transição for concluída, preservando histórico e filas pendentes. Aplicar retenção explícita de arquivos já confirmados.
8. Verificar alternância CameraX/ESP, pause/resume, STOP durante upload, reinício e perda de internet com hotspot ainda ativo.

**Aceite:** nenhuma captura nova surge após início de drenagem; UI permanece responsiva e não mascara pendências.

### S05 — Workflow e processamento reais

Arquivos-alvo: worker, workflows, activities, src/pages_to_audio/ai, OCR, áudio e Dockerfile.pages-rgb.

1. Remover ALL_FAKE_ACTIVITIES do registro operacional. Implementar atividades reais de validação, OCR, gates, resolução, áudio e persistência final.
2. Manter fakes somente em testes isolados. Se uma integração não existir/configurar, retornar falha explícita ou estado de revisão; nunca sucesso fabricado.
3. Corrigir starter para configuração pública explícita de namespace/task queue, sem Client._config; tratar WorkflowAlreadyStartedError corretamente.
4. Configurar worker separado da API, com mesmas versões e dependências compatíveis. Verificar Temporal real existente antes de decidir infraestrutura.
5. Não promover start-dev/SQLite local como serviço Temporal de produção. Se não houver instalação adequada, prover serviço com backend persistente e configuração de produção, isolado do restante da VPS.
6. Congelar toda configuração da sessão: providers, modelos configurados, projeto, localização, processor, limites e gates. Alterar painel não pode modificar processamento em andamento.
7. Centralizar carregamento de credenciais JSON/arquivo e refresh assíncrono com reutilização de token. Save-and-verify deve testar a configuração efetivamente proposta.
8. Persistir artefato OCR bruto real sob a sessão correta antes de anunciar sua chave.
9. Garantir Gate 1 antes de Solver. Questão que exige revisão manual não chama resolução automática indevidamente. Integrar verificador/arbitragem somente nos caminhos definidos pela política.
10. Manter Gate 2 de áudio e razão mínima; nenhuma questão fracassada conta como respondida. RGB exige completude própria de 100%.
11. Em pré-processamento, preservar ORIGINAL e devolver artefato realmente transformado quando aplicado; registrar applied/skipped/failed. Usar nomes por sessão/frame e métricas reais.
12. Implementar término e reap de subprocesso FFmpeg/ffprobe em timeout/cancelamento, incluindo encerramento dos recursos associados.
13. Declarar dependências de cada imagem/serviço explicitamente. --all-extras não instala dependency groups. Comprovar imports e executáveis reais no container: bibliotecas de autenticação, PDF/imagem e áudio necessárias.
14. Registrar etapas, duração, retries e falhas sem chaves, conteúdo secreto ou raciocínio privado.

**Aceite:** uma sessão real percorre todas as atividades necessárias, produz artefatos persistidos e falha corretamente quando uma dependência real falha.

### S06 — Conhecimento, consultas e configuração

1. Proteger leitura/escrita das rotas de conhecimento conforme política de acesso. Validar autenticação e escopo; não depender de ocultação no painel.
2. Substituir _DOCS/_CHUNKS por persistência real e jobs de indexação rastreáveis. Se função não estiver pronta, responder indisponibilidade explícita.
3. Corrigir bind de vetor, evitando :embedding::vector ambíguo; usar cast tipado/parâmetro suportado.
4. Usar consulta textual segura para linguagem natural, tratando pontuação sem abortar a transação. Falha de consulta não retorna lista vazia como se não houvesse resultados.
5. Retirar future.result bloqueante de endpoints async; aguardar processamento em executor adequado.
6. Distinguir absent/null para permitir limpar configuração. Verificação não pode reutilizar credencial antiga indevidamente.
7. Testar com Postgres/pgvector reais: persistência após reinício, indexação, consulta híbrida com pontuação, indisponibilidade e autorização.

**Aceite:** reindexação tem resultado verificável, consulta não oculta falhas e configuração salva corresponde à configuração testada.

### S07 — Publicação e entrega RGB

1. Gerar apenas respostas A–E completas e contíguas, na ordem das questões. Remover ou esclarecer controle de mínimo RGB que sugira publicação parcial permitida.
2. Preservar schema 1, packing e hash antigo; adicionar fixture separada do perfil 12%/150/2850.
3. Publicar parâmetros explicitamente em novas sessões. Não alterar revisões antigas nem seus hashes.
4. Inicializar estado virtual com versão 0 e incrementar versões de mudanças reais, sem colisão com primeiro PROCESSING.
5. Persistir resultado imutável antes de anunciá-lo. Cancelamento deve ser consultado antes da publicação e da entrega.
6. Tornar eventos idempotentes. Conservar progresso lógico máximo e aceitar telemetria coerente de retomada sem presumir entrega perfeita de todos os eventos.
7. Expor cancelamento solicitado versus reprodução local já iniciada; não prometer interrupção de placa offline.
8. Validar digest binário, quantidade, ordem, reenvio, evento COMPLETED duplicado e estado cancelado com o firmware candidato.

**Aceite:** resultado exibido no painel, servido ao Android e reproduzido na placa corresponde à mesma revisão e hash.

### S08 — Observabilidade, painel e saúde

1. Separar /live de /ready. Readiness usa timeouts e verifica banco, storage e dependências necessárias à função do serviço; worker precisa demonstrar conexão/polling efetivo.
2. Expor outbox pendente, fila Android, frames locais/cloud, estado Temporal e falhas permanentes sem dados sensíveis.
3. Corrigir painel que carrega sessão uma única vez: atualizar enquanto ativa, cancelar requests antigos e parar polling desnecessário após estado terminal.
4. Paginar frames/eventos e limitar tamanho das respostas. Não carregar histórico inteiro repetidamente.
5. Retestar UI no navegador real, correlacionando ação → request → endpoint → banco. Inspecionar Console/Network e screenshot quando houver alteração visual.
6. Medir melhoria contra S00. Definir limites de regressão com os recursos reais disponíveis; não aumentar concorrência sem medição.

**Aceite:** usuário consegue identificar sessão parada e distinguir falha de ausência de dados; painel permanece utilizável em sessão volumosa.

### S09 — Qualidade e builds reproduzíveis

1. Corrigir CI para executar integração atualmente desabilitada, incluindo checkout, instalação de ferramentas e serviços necessários.
2. Usar Python 3.12 e lockfile congelado. Executar lint/type-check nos módulos alterados e ampliar cobertura necessária às falhas corrigidas; não ocultar erros com exclusões novas.
3. Executar testes unitários e integração com Postgres, storage e Temporal reais no ambiente apropriado. Testes determinísticos de serialização não substituem S10.
4. Construir a imagem de produção efetiva, não somente outro Dockerfile. Verificar imports, ffmpeg/ffprobe, usuário, entrypoint e inicialização API/worker.
5. No painel executar npm ci, typecheck e build; adicionar/rodar verificação funcional dos fluxos alterados. O script test que apenas chama tsc não é teste de UI.
6. No Android executar Gradle assembleDebug e testDebugUnitTest para desenvolvimento; depois gerar APK de release com assinatura operacional existente.
7. Descobrir keystore e mecanismo de assinatura sem expor segredos. Se indisponível, registrar bloqueio somente da release; não inventar chave que impeça atualizar instalação existente.
8. Registrar hashes e logs dos artefatos. Não usar targets Makefile que são stubs como comprovação.

**Aceite:** API, worker, painel e Android compilam de maneira reproduzível; falhas de integração impedem promoção.

### S10 — Validação física integrada

Dependências: H1 dos dois projetos, telefone e ESP reais, credenciais e serviços disponíveis.

1. Registrar commit do servidor, digest de imagens, APK instalado, BIN/ELF da ESP, revisão do contrato, IDs e horário.
2. Executar missão com documento físico de referência conhecido, incluindo múltiplos comandos até completar o total de imagens previsto. Não presumir que um único upload valida uma missão de 30 imagens.
3. Conferir bytes/hashes e contagem única do primeiro ao último frame; acompanhar OCR, gates, resolução e publicação reais.
4. Reproduzir RGB na placa e comparar ordem/quantidade/cores com a referência, incluindo resultado extenso.
5. Repetir com perda de internet do Android, mantendo rede local; depois reiniciar app e restaurar internet. Todos os ACKs locais devem resultar em recuperação e encaminhamento.
6. Testar pausa, retomada e fechamento com frame em voo; reiniciar dispatcher/worker; verificar idempotência e ausência de frames novos após fechamento.
7. Testar credencial/certificado incorretos e sessão alheia. Não deve haver vazamento de token nem aceitação cruzada.
8. Testar cancelamento antes da publicação e após reprodução offline iniciada, verificando a semântica distinta.
9. Registrar latência por estágio, filas, CPU/memória, erros e resultado final. Comparar com baseline; investigar regressão antes de release.
10. Falha real não é substituída por retorno fabricado. Manter etapa pendente com evidência quando hardware/provider estiver ausente.

**Aceite H2:** missão completa e cenários de recuperação aprovados conjuntamente com executor do firmware.

### S11 — Push, imagens e deploy verificável

Arquivos-alvo: .github/workflows/deploy-pages-rgb.yml, infra/docker-compose.pages-rgb.prod.yml, scripts de deploy e runbook de rollback.

1. Corrigir o fluxo atual: ele publica imagens, mas não executa deploy. Acrescentar etapa real de implantação ou documentar e executar comando remoto único e auditável.
2. Consolidar os scripts em um caminho operacional: lock, projeto Compose explícito, --env-file correto, validação de configuração, pull obrigatório e falha imediata. Remover sucesso artificial por ausência de Docker ou pull ignorado.
3. Incluir worker e suas dependências configuradas. Preservar instalação Temporal real quando adequada. Definir TEMPORAL_ADDRESS, namespace e task queue explicitamente.
4. Verificar projeto Compose em uso antes de escolher -p; evitar duplicar serviços/volumes ou colidir com container_name existentes.
5. Registrar backup recuperável do banco e release anterior, incluindo imagens/digests e configuração. Usar migrações aditivas compatíveis; não executar downgrade destrutivo no rollback.
6. Revisar diff e stage somente arquivos próprios. Excluir segredos, dados e artefatos locais. Commitar e fazer push da branch autorizada; seguir proteção de main/PR existente. Não forçar histórico.
7. Acompanhar CI até conclusão. A publicação deve usar SHA imutável; o workflow atual emite sha-<short>. Registrar também digest efetivo, evitando implantação por latest.
8. Atualizar manifesto/Compose para imagens exatas de API, worker e painel. Executar migrações novas uma vez no ambiente alvo, com falha impedindo continuação.
9. Fazer rollout aditivo: backend/worker compatíveis primeiro, Android depois, firmware por último. Não remover contrato legado antes da atualização dos clientes.
10. Executar Compose pull e up no diretório operacional real com os mesmos projeto/env/config. Não regenerar automaticamente hash de senha durante deploy.
11. Verificar saúde pelo roteamento correto: porta local publicada é 127.0.0.1:8081; enviar Host: ptr.rotadeataque.com.br ao consultar /api/v1/health/ready. Caddy sem esse Host pode devolver 200 genérico.
12. Verificar também https://ptr.rotadeataque.com.br/api/v1/health/ready, payload de prontidão, identidade da release e worker consumindo fila. Não tentar portas alternativas até achar qualquer 200.
13. Instalar APK assinado no telefone identificado, preservando dados/identidade quando compatível; não desinstalar como atalho se houver fila pendente.
14. Executar smoke real e H4 com firmware final. Só registrar deploy concluído após comprovar versão ativa e processamento real.

**Aceite H3/H4:** commit enviado, imagens publicadas e serviços implantados correspondem aos artefatos aprovados; aplicativo e placa usam o contrato correspondente.

### S12 — Rollback e entrega

1. Se readiness, processamento ou integração falhar, interromper promoção de clientes e registrar causa.
2. Reverter imagens para digests anteriores compatíveis; preservar banco, outbox, objetos e filas. Não desfazer schema com perda de dados.
3. Se painel falhar isoladamente, seguir runbook para manter API quando seguro. Não rotacionar credenciais automaticamente sem necessidade concreta.
4. Reinstalar APK anterior somente com assinatura e migração de dados compatíveis; filas pendentes devem permanecer recuperáveis.
5. Retestar retomada e integridade após rollback.
6. Atualizar docs operacionais, contratos e registro final com evidências, riscos residuais e mudanças de configuração. Manter auditoria como histórico.

## 4. Matriz de cobertura da auditoria

| Achado | Correção principal | Evidência exigida |
| --- | --- | --- |
| A01 | S05 | Atividades reais e artefatos finais persistidos |
| A02 | S01, S03 | Auth cloud e local reais |
| A03 | S01, S07 | DTOs ponta a ponta |
| A04 | S02 | Outbox recupera falha de despacho |
| A05 | S05, S11 | Worker/Temporal operacionais |
| A06 | S08, S11 | Ready detecta dependência indisponível |
| A07 | S05, S09 | Imports e executáveis na imagem final |
| A08 | S06 | Rotas de conhecimento protegidas |
| A09 | S06 | Dados sobrevivem a reinício |
| A10 | S02 | Novos frames negados após fechamento |
| A11 | S04 | Drenagem completa antes do fechamento |
| A12 | S02, S04 | Contagem única baseada em ACK durável |
| A13 | S02, S04 | Comandos persistentes, long-poll e ACK |
| A14 | S04 | UI responsiva e câmera reutilizada |
| A15 | S02 | Objeto existente conciliado após falha DB |
| A16 | S02 | Falha de R2 não vira memória |
| A17 | S07 | Primeira mudança RGB visível |
| A18 | S02, S07 | Cerca de cancelamento e semântica offline |
| A19 | S01 | Limites e JPEG verificados |
| A20 | S01 | Valor omitido herda configuração |
| A21 | S07 | RGB completo e controle coerente |
| A22 | S05 | Snapshot integral estável |
| A23 | S01, S06 | Null limpa e verificação usa proposta |
| A24 | S06 | Cast vetorial real funciona |
| A25 | S06 | Pontuação não aborta consulta |
| A26 | S06 | Event loop não bloqueado por extração |
| A27 | S05 | Credenciais coerentes e refresh reutilizado |
| A28 | S05 | Chave OCR aponta para objeto real |
| A29 | S05 | Revisão manual e gates controlam execução |
| A30 | S05 | Transformação e estado refletidos no artefato |
| A31 | S05 | Subprocesso encerrado após timeout |
| A32 | S02 | Imutabilidade com bucket customizado |
| A33 | S03, S04 | Fila/sessão recuperáveis e retenção |
| A34 | S08 | Atualização e paginação reais |
| A35 | S09, S10 | CI ativa e missão física completa |

## 5. Simplificações e limites

- Um registro durável de comandos, uma outbox de despacho e uma fila Android com papéis distintos; não multiplicar filas para contornar erros.
- Um adaptador de credenciais/configuração compartilhado pelos caminhos de salvar, verificar e executar.
- Uma política de fechamento baseada em fatos persistidos; evitar contadores paralelos como fontes de verdade.
- Um script de deploy, um manifesto de release e um procedimento de rollback.
- Não reescrever arquitetura inteira, trocar framework ou aumentar concorrência antes de corrigir funcionamento e medir.
- A escolha física de início da ESP permanece pendente. S00–S09 podem avançar nos pontos independentes; não implementar gesto presumido no app ou firmware.

