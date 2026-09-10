# Reauditoria cruzada das três implementações — 09/09/2026

## Veredito

**Não está tudo certo nem pronto para uso real.** Há implementações úteis, mas os resumos superestimam a conclusão em código de partes essenciais. A ausência de hardware não explica os defeitos estáticos e os caminhos desconectados documentados abaixo.

Esta revisão compara os três planos, contratos, registros, fontes atuais e pontos de integração. Não é implementação de correções. As únicas alterações autorizadas nesta etapa são os documentos de auditoria e plano de conclusão.

Servidor: C:/Users/Lenovo/Downloads/pagestoaudio_servidor. Firmware: C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1.
Servidor HEAD local observado: be34d8a, precedido de c282758. As alterações do diagnóstico ainda aparecem fora desses commits.
Plano de conclusão: [PLANO_CONCLUSAO_POS_REAUDITORIA_2026-09-09.md](PLANO_CONCLUSAO_POS_REAUDITORIA_2026-09-09.md).

## Método e evidência

Foi aplicada a skill fullstack-diagnosis: rastreamento UI → API → serviço → banco/storage e Android → protocolo → firmware. Sem CodeGraph nos dois projetos. Consultas locais e navegador foram usados sem alterar dados de aplicação.

| Verificação executada nesta revisão | Resultado e limite |
| --- | --- |
| Leitura dos contratos principais e de diagnóstico nos dois projetos | Cópias correspondentes idênticas; igualdade documental não significa implementação compatível |
| Leitura de rotas, bridge, fila, firmware, workflow, storage, CI/deploy e painel | Achados RA01–RA36 abaixo; referências apontam ao snapshot examinado |
| GCC Xtensa real, flags do compile_commands, -fsyntax-only e CONFIG_CAPTURE_DIAG_ENABLE=1 | app_main.c, diag_camera.c e gateway_client.c: código de saída 0; não houve link, BIN novo ou teste de hardware |
| TypeScript real, --noEmit --incremental false | Código de saída 0; isso não valida comportamento do player/galeria |
| Python WSL instalado, introspecção de funções reais | Confirmado argumento session_id duplicado em materialize; SQLAlchemy ORM sem with_for_update; transição LOCKED→COMPLETED não permitida |
| pytest tests/integration -m integration --collect-only | Nenhum teste coletado; a pasta não contém test_*.py |
| HTTP local 127.0.0.1:8081 /api/v1/health/ready, Host ptr.rotadeataque.com.br | HTTP 200 com checks vazio; versão ativa não verificada por digest |
| Navegador real no domínio /admin/camera-test | Redirecionou para /admin/login. Screenshot examinado; sem sessão autenticada para validar diagnóstico. Console mostrou favicon 404, sem evidência de falha funcional do login |
| HTTP Python ao domínio público | 403 / Cloudflare 1010; não foi confundido com indisponibilidade do backend |
| Portas/serial | 5432 e 8081 em escuta; COM3 listada. Porta serial não foi aberta, para não resetar a placa durante auditoria |
| Git/artefatos | Diagnóstico do servidor não consolidado em commit; BIN 2.4.0 anterior às fontes diagnósticas |

As contagens 425/433 e os testes dos resumos pertencem às execuções anteriores e não foram reapresentados como nova prova de funcionamento. Testes isolados existentes não substituem integração real. Os testes de painel examinados verificam presença de strings nos arquivos, apesar da denominação funcional.

## Melhorias aproveitáveis

- Separação de estado de controle da sessão e fase transitória no firmware.
- Correção de dimensionamento inicial de câmera e comparação C do PID do sensor.
- Novo formato de spool com commit/integridade e melhor classificação de erros, embora ainda haja caminhos que ignoram a persistência.
- Registro RGB versionado, validação antes de READY e recuperação de progresso melhorada, com limitações remanescentes.
- Tabelas de outbox/comandos, rejeição de JPEG indecodificável e contagem de frames baseada no banco.
- Remoção do fallback de escrita R2 em produção nos caminhos protegidos.
- Implementação de persistência RAG, mudanças de configuração e estrutura de painel que podem ser mantidas.
- Namespace e flags de diagnóstico, schema aditivo e componentes de aquisição/conversão como base.

Essas melhorias não equivalem a aceite global. Recomenda-se corrigir os pontos listados sem reescrever a arquitetura.

## Achados

Legenda de referências: S = projeto do servidor; F = projeto do firmware. Números indicam linhas no snapshot desta revisão. Para artefatos binários, a referência é o arquivo, sem interpretação de linha.

### RA01 — Ponte Android incompatível com o protocolo da ESP

**Prioridade:** Crítica. **Plano relacionado:** S03/H1.

**Problema e causa:** Android responde discovery em JSON, enquanto ESP espera P2A_GATEWAY_V1 com nonce. Android expõe GET /v1/hello, enquanto ESP envia POST /v1/device/hello. Faltam rotas RGB, heartbeat e fault esperadas. cloudCommand descarta payload com {} e cloudResult retém apenas command/cursor. Captura e resultado não chegam com os campos exigidos.

**Correção necessária:** Concluir adaptador explícito e versionado, com tabela método/rota/schema dos dois lados, discovery compatível e encaminhamento integral dos campos. Comprovar HELLO, captura e RGB pelo mesmo APK/BIN.

**Evidência:** [S:apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspHttpServer.kt:99](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspHttpServer.kt:99) · [S:apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspDiscoveryResponder.kt:44](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspDiscoveryResponder.kt:44) · [S:apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspBridgeService.kt:84](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspBridgeService.kt:84) · [F:main/gateway_discovery.c:64](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/main/gateway_discovery.c:64) · [F:main/gateway_client.c:422](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/main/gateway_client.c:422)

### RA02 — Autenticação e provisionamento local incompletos

**Prioridade:** Alta. **Plano relacionado:** S01/S03/F04.

**Problema e causa:** Start cria segredo aleatório no telefone, sem mecanismo de instalação do mesmo segredo na ESP. Só alguns handlers validam Authorization; start, comandos, resultado, capture-complete e controles diagnósticos não têm proteção equivalente. O comentário de bancada não restringe automaticamente execução a bancada.

**Correção necessária:** Provisionar segredo/identidade em ambos, aplicar autenticação e vínculo de sessão/dispositivo a todas as rotas protegidas e remover criação implícita de credencial por pedido não autenticado.

**Evidência:** [S:apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspHttpServer.kt:222](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspHttpServer.kt:222) · [S:apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspProvisioning.kt:36](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspProvisioning.kt:36)

### RA03 — Origem e identidade da sessão ESP são substituídas pelas do telefone

**Prioridade:** Alta. **Plano relacionado:** S01/S03.

**Problema e causa:** startForDevice recebe deviceId, mas não o passa ao repository. startSession fixa captureSource=ANDROID_CAMERA, deviceCode=deviceId do repository e gatewayCode=deviceId. Ignora allow_new_session do corpo ESP e reduz erros distintos a 503. Isso quebra vínculo, retomada e separação entre fontes.

**Correção necessária:** Passar identidade ESP e gateway explicitamente, preservar capture_source, allow_new_session e resolução de retomada exata; traduzir 409/401/503 sem perder sua semântica.

**Evidência:** [S:apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspBridgeService.kt:59](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspBridgeService.kt:59) · [S:apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/domain/SessionRepository.kt:42](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/domain/SessionRepository.kt:42)

### RA04 — ACK Android pode confirmar arquivo sem registro recuperável

**Prioridade:** Crítica. **Plano relacionado:** S02/S03/S04.

**Problema e causa:** Se arquivo existe com mesmo hash, deviceFrame retorna 208 sem conciliar Room. Uma falha após rename e antes de save deixa órfão aceito no retry, sem garantia de upload. reconcileLocalSpool só percorre linhas existentes e registra arquivos ausentes; não reconstrói órfãos. Servidor inicia antes da reconciliação. Eventos esp_outbox são writeText sem confirmação durável e não há consumidor identificado no caminho da ponte.

**Correção necessária:** Reconciliar arquivo e registro antes de qualquer ACK, serializar por identidade, tratar fsync/rename corretamente, bloquear readiness até recuperar estado e implementar envio/retry idempotente dos eventos.

**Evidência:** [S:apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspHttpServer.kt:273](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspHttpServer.kt:273) · [S:apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/spool/SpoolRepository.kt:105](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/spool/SpoolRepository.kt:105) · [S:apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspBridgeService.kt:99](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspBridgeService.kt:99)

### RA05 — Comandos persistidos ainda não obedecem controle/ACK/capacidades

**Prioridade:** Alta. **Plano relacionado:** S01/S02/M01.

**Problema e causa:** GET cria próximo comando a partir do cursor informado, independentemente de ACK. Um comando existente no cursor+1 é devolvido mesmo se STOP passou a ser necessário. Valores fixos 1280x720/75 e UXGA/92 misturam convenções CameraX e ESP (qualidade aceita pelo sensor é outra). Novas capturas são produzidas enquanto CAPTURING sem política de término por quantidade/capacidade consolidada.

**Correção necessária:** Persistir intenção de comando, prioridade de controle e efeito/ACK separados; selecionar perfil conforme origem/capacidade, limitar missão e negociar lotes menores. Não avançar apenas por cursor fornecido.

**Evidência:** [S:src/pages_to_audio/capture/commands.py:28](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/capture/commands.py:28) · [S:src/pages_to_audio/capture/commands.py:83](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/capture/commands.py:83)

### RA06 — Cursores/ACKs de comandos não garantem retomada idempotente

**Prioridade:** Crítica. **Plano relacionado:** F01/F02/S04.

**Problema e causa:** Firmware avança cursor só em RAM e limpa spool/intent antes de tornar o efeito recuperável; não há chamada de ACK cloud/local correspondente no cliente de missão. Start devolve cursor RGB, que não é cursor de captura. Android ignora Result de ackCommand e avança mesmo em falha; retry pode refazer exposição sem reconciliar frames existentes.

**Correção necessária:** Persistir comando/efeito/ACK e pausa em journal mínimo, separar cursor de captura e versão RGB, reenviar bytes existentes e somente repetir ACK quando efeito já ocorreu. Não consumir comando por sucesso aparente.

**Evidência:** [F:main/app_main.c:1134](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/main/app_main.c:1134) · [F:main/app_main.c:698](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/main/app_main.c:698) · [S:apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/ui/SessionViewModel.kt:393](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/ui/SessionViewModel.kt:393) · [S:apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/sync/CommandPollWorker.kt:111](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/sync/CommandPollWorker.kt:111) · [S:apps/api/routers/gateway.py:35](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/gateway.py:35)

### RA07 — Atividades denominadas reais ainda não executam o processamento

**Prioridade:** Crítica. **Plano relacionado:** S05/A01.

**Problema e causa:** Materialização e pré-processamento contam frames. run_ocr cria providers e retorna ocr_runs=0, sem chamar OCR. Recuperação, RAG, solver, verificação, arbitragem e áudio retornam contadores zero ou flags falsas; emit_post_correction_status devolve emitted=True sem emissão. Não há despacho para o runner mencionado no comentário dentro dessa cadeia.

**Correção necessária:** Ligar atividades aos serviços de processamento existentes e persistir artefatos reais. Remover sucesso nominal, criar estados explícitos para revisão/falha e comprovar uma sessão nova do JPEG ao resultado.

**Evidência:** [S:src/pages_to_audio/workflows/activities/real.py:90](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/workflows/activities/real.py:90) · [S:src/pages_to_audio/workflows/activities/real.py:150](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/workflows/activities/real.py:150) · [S:src/pages_to_audio/workflows/activities/real.py:266](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/workflows/activities/real.py:266) · [S:src/pages_to_audio/workflows/activities/real.py:395](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/workflows/activities/real.py:395)

### RA08 — Materialização falha por argumento duplicado no logger

**Prioridade:** Crítica. **Plano relacionado:** S05.

**Problema e causa:** result contém session_id e é expandido em _step_log que já recebe session_id posicional. A chamada gera TypeError: multiple values for argument 'session_id'. O binding foi confirmado com inspect.signature do código real, sem executar providers ou banco.

**Correção necessária:** Corrigir contrato do helper/log e executar o caminho completo da atividade com dados reais; teste apenas do nome/registro da atividade não detecta isso.

**Evidência:** [S:src/pages_to_audio/workflows/activities/real.py:33](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/workflows/activities/real.py:33) · [S:src/pages_to_audio/workflows/activities/real.py:115](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/workflows/activities/real.py:115)

### RA09 — Máquina de estados tem chamada de SQLAlchemy inválida e workflow não avança fases

**Prioridade:** Crítica. **Plano relacionado:** S02/S05.

**Problema e causa:** sqlalchemy.orm.with_for_update não existe na instalação inspecionada. Além disso, as atividades intermediárias não transitam a sessão; complete_session tenta COMPLETED a partir de estado que pode continuar LOCKED. A tabela local não permite LOCKED→COMPLETED. Validação de estado também ocorre antes de adquirir o lock efetivo.

**Correção necessária:** Usar select(...).with_for_update() ou API suportada, reler/validar sob lock e persistir transições reais durante processamento. Não relaxar toda a máquina para esconder saltos.

**Evidência:** [S:src/pages_to_audio/domain/state_machine.py:224](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/domain/state_machine.py:224) · [S:src/pages_to_audio/workflows/activities/real.py:458](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/workflows/activities/real.py:458) · [S:src/pages_to_audio/workflows/process_exam.py:166](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/workflows/process_exam.py:166)

### RA10 — Gate 2 conta respostas de todas as sessões

**Prioridade:** Crítica. **Plano relacionado:** S05/Gate 2.

**Problema e causa:** A consulta conta todo FinalAnswer.validated=True sem join com Question nem filtro da sessão. Respostas anteriores podem aprovar indevidamente a sessão atual.

**Correção necessária:** Filtrar pelo conjunto de questões da sessão e critérios de validade; comprovar isolamento usando duas sessões reais com respostas distintas.

**Evidência:** [S:src/pages_to_audio/workflows/activities/real.py:351](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/workflows/activities/real.py:351) · [S:src/pages_to_audio/db/models/final_answer.py:20](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/db/models/final_answer.py:20)

### RA11 — Outbox ainda é despachada antes do commit do fechamento

**Prioridade:** Alta. **Plano relacionado:** S02/A04.

**Problema e causa:** end-signal faz flush e chama dispatch_pending na mesma transação; commit ocorre no encerramento da dependência. Temporal pode iniciar antes de o worker enxergar LOCKED ou o intent confirmado. O loop posterior de outbox é melhoria, mas não elimina essa corrida.

**Correção necessária:** Despachar somente intents commitados, por dispatcher dedicado já existente; manter ID determinístico, reconciliação e cancelamento. Verificar também rota handwritten.

**Evidência:** [S:apps/api/routers/gateway.py:603](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/gateway.py:603) · [S:apps/api/dependencies.py:14](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/dependencies.py:14) · [S:src/pages_to_audio/capture/dispatcher.py:40](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/capture/dispatcher.py:40)

### RA12 — Storage R2 usa bucket incorreto e mantém corrida de imutabilidade

**Prioridade:** Alta. **Plano relacionado:** S02/A15/A32.

**Problema e causa:** put_object calcula resolved, mas o boto3 PUT usa Bucket=bucket original; HEAD/GET usam resolved. Alias lógico pode gravar no bucket errado/falhar. Imutabilidade ainda depende de HEAD seguido de PUT sem condição atômica.

**Correção necessária:** Resolver bucket uma vez para todas as operações; usar escrita condicional/coordenação comprovada por identidade. Verificar alias, nome customizado e concorrência no R2 real.

**Evidência:** [S:src/pages_to_audio/storage/r2_storage.py:107](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/storage/r2_storage.py:107) · [S:src/pages_to_audio/storage/r2_storage.py:130](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/storage/r2_storage.py:130)

### RA13 — Firmware ainda envia sem spool e pode substituir/apagar fotos pendentes

**Prioridade:** Crítica. **Plano relacionado:** F03/F09/F17.

**Problema e causa:** Falha de spool_store_bundle ativa ram_only e continua upload. Se rede/reset falha, JPEGs são liberados sem cópia durável. Lote diferente ou falha de leitura pode cair em nova gravação que substitui o spool anterior. STOP limpa spool/intent quando FINISHED foi gravado, sem conciliar necessariamente todas as fotos.

**Correção necessária:** Recusar upload sem persistência, bloquear substituição de lote não conciliado e concluir STOP somente preservando/transferindo pendências. Falha de memória/leitura não autoriza apagamento.

**Evidência:** [F:main/app_main.c:539](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/main/app_main.c:539) · [F:main/app_main.c:620](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/main/app_main.c:620) · [F:main/app_main.c:749](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/main/app_main.c:749)

### RA14 — NVS ainda tem apagamento automático e fechamento parcialmente persistido

**Prioridade:** Alta. **Plano relacionado:** F02/F08/F11.

**Problema e causa:** Boot ainda executa nvs_flash_erase em NO_FREE_PAGES/NEW_VERSION_FOUND. Sessão ativa/finished/sid continuam setters separados. FINISHED precede registro RGB pendente, deixando janela de perda na queda de energia. Registro RGB inconsistente pode cair em fallback legado como se estivesse ausente.

**Correção necessária:** Eliminar apagamento automático de dados operacionais; persistir transição coerente e preservar estado inválido para recuperação explícita. Migrar formatos sem confundir ausência com corrupção.

**Evidência:** [F:main/app_main.c:1143](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/main/app_main.c:1143) · [F:main/app_main.c:724](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/main/app_main.c:724) · [F:main/session_store.c:180](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/main/session_store.c:180) · [F:main/session_store.c:87](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/main/session_store.c:87)

### RA15 — TLS existe como helper, mas caminho operacional continua HTTP

**Prioridade:** Crítica para produção. **Plano relacionado:** S03/F04/F24.

**Problema e causa:** Seleção normal utiliza gateway_client_set_gateway e desliga s_use_tls. Não foram encontrados consumidores operacionais dos setters TLS/CA fora das definições. Android usa ServerSocket HTTP. Log 'bancada' não impede perfil Production de enviar segredo por HTTP.

**Correção necessária:** Concluir TLS ponta a ponta, provisionar CA/identidade/relógio e travar build/runtime de produção contra HTTP. Não declarar fail-closed global só porque um helper isolado rejeita CA ausente.

**Evidência:** [F:main/gateway_client.c:210](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/main/gateway_client.c:210) · [F:main/gateway_client.c:218](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/main/gateway_client.c:218) · [S:apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspHttpServer.kt:65](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspHttpServer.kt:65)

### RA16 — Progresso RGB continua com busca quadrática por slot

**Prioridade:** Média. **Plano relacionado:** F06/M04.

**Problema e causa:** Cache guarda next_index, mas cada append procura slot apagado desde zero. O custo de leitura de marcadores continua O(n²). Recuperação de cauda melhorou, porém não corresponde à alegação de append O(1).

**Correção necessária:** Cachear também o próximo offset de escrita, reconstruído uma vez no boot; validar slots totalmente livres/rasgados e medir sessão longa.

**Evidência:** [F:main/rgb_sequence_store.c:369](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/main/rgb_sequence_store.c:369)

### RA17 — Eventos RGB ainda rejeitam telemetria válida de retomada

**Prioridade:** Alta. **Plano relacionado:** S07/contrato RGB.

**Problema e causa:** RECEIVED só é permitido em READY e progresso inferior ao máximo é rejeitado antes de conciliar observação física. Contrato consolidado admite repetição do último item após corte e exige progresso lógico monotônico sem descartar toda telemetria de retomada.

**Correção necessária:** Separar evento observado do high-water mark lógico, preservando validação de identidade e conclusão. Testar ACK perdido e reset durante reprodução na placa.

**Evidência:** [S:src/pages_to_audio/rgb/delivery.py:502](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/rgb/delivery.py:502) · [S:src/pages_to_audio/rgb/delivery.py:508](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/rgb/delivery.py:508)

### RA18 — Diagnóstico não tem caminho completo do painel à ESP

**Prioridade:** Crítica. **Plano relacionado:** D00–D04.

**Problema e causa:** diagForwarder fica null e não há instanciação/ligação identificada no app. DiagViewModel não está integrado à UI/ciclo operacional. Não há consulta cloud de pedidos pendentes por dispositivo. GET local retorna apenas active; firmware exige diagnostic_id e perfil. Não basta ligar flags.

**Correção necessária:** Implementar descoberta/entrega de pedido, ligação do forwarder/UI local e resposta local completa, com confirmação da ESP. Verificar caminho efetivo sem chamadas manuais fabricando sucesso.

**Evidência:** [S:apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspHttpServer.kt:131](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspHttpServer.kt:131) · [S:apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspBridgeService.kt:99](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspBridgeService.kt:99) · [S:apps/api/routers/gateway_diagnostics.py:62](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/gateway_diagnostics.py:62) · [F:main/gateway_client.c:1094](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/main/gateway_client.c:1094)

### RA19 — Parada e duração locais do diagnóstico não seguem o contrato

**Prioridade:** Alta. **Plano relacionado:** D03/D04.

**Problema e causa:** active=false não interrompe imediatamente aquisição ativa; código conserva operação até prazo. Se poll interno desativa por deadline, loop while(s_active || true) pode continuar ocioso indefinidamente. gateway_client_diag_ack não é chamado pelo módulo. Janela pré-missão é uma consulta única; não há janela local controlada completa. Perfil/câmera anterior não é restaurado se já estava inicializado.

**Correção necessária:** Implementar ciclo finito com estados, lease local, STOP com liberação e ACK reais, prazo independente da rede e restauração de recursos. Não deixar o teste impedir retorno à missão.

**Evidência:** [F:main/diag_camera.c:180](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/main/diag_camera.c:180) · [F:main/diag_camera.c:232](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/main/diag_camera.c:232) · [F:main/diag_camera.c:132](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/main/diag_camera.c:132) · [F:main/app_main.c:1223](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/main/app_main.c:1223)

### RA20 — Frames diagnósticos podem reutilizar identidade com bytes diferentes

**Prioridade:** Alta. **Plano relacionado:** D03/D04/ACK.

**Problema e causa:** JPEG é liberado após tentativa. Na prévia, erro mantém frame_index e próxima captura gera outros bytes com o mesmo índice. Android usa 202 para prévia enfileirada, mas cliente trata como falha conforme classificação. Corpo do ACK/hash não é validado para foto/clipe.

**Correção necessária:** Consumir índice na aquisição de cada frame transitório, definir ACK transitório separado e preservar bytes de fotos/clipes até confirmação ou falha terminal explícita conciliada.

**Evidência:** [F:main/diag_camera.c:164](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/main/diag_camera.c:164) · [F:main/diag_camera.c:263](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/main/diag_camera.c:263) · [F:main/gateway_client.c:1163](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/main/gateway_client.c:1163) · [S:apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspHttpServer.kt:200](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspHttpServer.kt:200)

### RA21 — Fila DIAG é enviada pelo worker de missão e perde recuperação correta

**Prioridade:** Crítica. **Plano relacionado:** D02/persistência.

**Problema e causa:** save enfileira UploadWorker automaticamente. Esse worker só distingue handwritten e exame; DIAG cai em uploadFrame de missão com sessionId/captureId 'diag:...'. O forwarder simultaneamente abre outro loop de upload. recoverDurable reenfileira no mesmo worker incorreto; upload dedicado depende de isActive, encerrando retries ao terminar teste.

**Correção necessária:** Uma fila com roteamento explícito por tipo, sem duplicação de produtores; persistir metadados completos e recuperar fotos/clipes mesmo após fim de aquisição/reboot. Não misturar namespace diagnóstico com missão.

**Evidência:** [S:apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/diag/CameraDiagnosticsForwarder.kt:184](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/diag/CameraDiagnosticsForwarder.kt:184) · [S:apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/spool/SpoolRepository.kt:85](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/spool/SpoolRepository.kt:85) · [S:apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/sync/UploadWorker.kt:99](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/sync/UploadWorker.kt:99)

### RA22 — Último frame pode retroceder ou ser trocado durante envio

**Prioridade:** Alta. **Plano relacionado:** D04.

**Problema e causa:** Servidor usa preview_latest.jpg compartilhado, e sequence é ordem de chegada, não índice capturado. Frame atrasado recebe sequence maior e substitui o mais novo. Android sobrescreve preview_latest.jpg enquanto outra coroutine pode estar lendo/enviando o mesmo arquivo. Hash e imagem podem divergir.

**Correção necessária:** Objetos/bytes imutáveis por índice em trânsito, ponteiro atualizado condicionalmente por índice/timestamp de origem e buffer de tamanho fixo; nunca sobrescrever arquivo aberto para envio.

**Evidência:** [S:src/pages_to_audio/camera_diagnostics/__init__.py:69](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/camera_diagnostics/__init__.py:69) · [S:src/pages_to_audio/camera_diagnostics/service.py:286](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/camera_diagnostics/service.py:286) · [S:src/pages_to_audio/camera_diagnostics/service.py:312](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/camera_diagnostics/service.py:312) · [S:apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/diag/CameraDiagnosticsForwarder.kt:223](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/diag/CameraDiagnosticsForwarder.kt:223)

### RA23 — Servidor confirma parada/conclusão antes da ESP e pode ressuscitar diagnóstico

**Prioridade:** Crítica. **Plano relacionado:** D01/D04.

**Problema e causa:** stop_diagnostic passa imediatamente a COMPLETED; admin devolve ack=True sem liberação da ESP. Claim já marca ACTIVE sem confirmação física. Evento FAILED é tratado como parada concluída. mark_active pode tornar ACTIVE um estado terminal; expiração não é validada em toda ingestão e heartbeat cloud está ausente.

**Correção necessária:** Separar claim, ACTIVE físico, STOPPING, ACK e falha; estados terminais não retrocedem. Autorizações expiram no servidor e na placa. Drenagem de dados tem estado próprio.

**Evidência:** [S:src/pages_to_audio/camera_diagnostics/service.py:177](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/camera_diagnostics/service.py:177) · [S:src/pages_to_audio/camera_diagnostics/service.py:194](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/camera_diagnostics/service.py:194) · [S:apps/api/routers/gateway_diagnostics.py:100](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/gateway_diagnostics.py:100)

### RA24 — Exclusão de diagnóstico não é atômica nem simétrica com missão

**Prioridade:** Alta. **Plano relacionado:** D00/D01.

**Problema e causa:** FOR UPDATE sobre diagnóstico ativo não bloqueia a ausência de linha. Duas criações podem passar; índice device/status não é unique parcial. Início de missão não participa da mesma trava. Consulta exclui LOCKED embora resultado/pendência possa continuar ocupando o dispositivo.

**Correção necessária:** Adquirir lock em recurso persistente comum por dispositivo e validar ocupação sob esse lock nos dois fluxos; constraint defensiva para diagnóstico ativo e confirmação local da ESP.

**Evidência:** [S:src/pages_to_audio/camera_diagnostics/service.py:68](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/camera_diagnostics/service.py:68) · [S:migrations/versions/0012_camera_diagnostics.py:62](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/migrations/versions/0012_camera_diagnostics.py:62)

### RA25 — Vínculo e flag não são verificados em todas as rotas diagnósticas

**Prioridade:** Alta. **Plano relacionado:** D01/D02.

**Problema e causa:** Rotas cloud recebem gateway_id mas carregam diagnóstico só por ID, sem validar proprietário/vínculo. Flag é checada em create/claim, não como cerca consistente de upload/eventos. Controles locais têm proteção desigual. Relay admin aceita JPEG arbitrário enquanto origem permanece ESP32_CAMERA.

**Correção necessária:** Centralizar autorização/vínculo/flag/lease, desabilitar relay fora de bancada ou identificar origem distinta. Não permitir que outro gateway reivindique ou finalize diagnóstico alheio.

**Evidência:** [S:apps/api/routers/gateway_diagnostics.py:46](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/gateway_diagnostics.py:46) · [S:apps/api/routers/gateway_diagnostics.py:138](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/gateway_diagnostics.py:138) · [S:apps/api/routers/admin_camera_diagnostics.py:290](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/admin_camera_diagnostics.py:290) · [S:apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspHttpServer.kt:143](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/esp/EspHttpServer.kt:143)

### RA26 — Quotas e idempotência diagnósticas são inconsistentes

**Prioridade:** Alta. **Plano relacionado:** D01/persistência.

**Problema e causa:** Estado/quota são verificados antes da duplicata: retry de foto já recebida pode falhar por quota ou fechamento. Unique inclui hash, permitindo duas linhas do mesmo índice com hashes distintos em corrida. Contadores sem lock podem perder incrementos. /frame não restringe modo adequadamente; metadados declarados de dimensão substituem os decodificados.

**Correção necessária:** Checar duplicata conhecida antes dos gates de nova ingestão, unique por diagnóstico/índice, lock de contadores/limites e validação do modo e dimensão real.

**Evidência:** [S:src/pages_to_audio/camera_diagnostics/service.py:228](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/camera_diagnostics/service.py:228) · [S:migrations/versions/0012_camera_diagnostics.py:87](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/migrations/versions/0012_camera_diagnostics.py:87)

### RA27 — Conversão de vídeo roda no request e aceita incompletude/codec alternativo

**Prioridade:** Alta. **Plano relacionado:** D05.

**Problema e causa:** Funções são awaited na ingestão/STOP; não há atividade/dispatcher de vídeo registrado no worker. Lock asyncio só vale por processo e não há FOR UPDATE alegado. Dois frames em estado EXPIRED/STOPPING podem virar clipe sem validar conjunto completo. Fallback mpeg4 contraria H.264 definido. Cancelamento e timeout dos probes não garantem kill/reap; saída não tem teto efetivo.

**Correção necessária:** Agendar tarefa durável no worker existente, validar entrada/tempo real/completude, limitar recurso/saída, exigir encoder aprovado e encerrar todos os subprocessos em cancelamento.

**Evidência:** [S:src/pages_to_audio/camera_diagnostics/video.py:52](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/camera_diagnostics/video.py:52) · [S:apps/api/routers/admin_camera_diagnostics.py:175](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/admin_camera_diagnostics.py:175) · [S:src/pages_to_audio/camera_diagnostics/service.py:333](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/camera_diagnostics/service.py:333)

### RA28 — Galeria e player não entregam os arquivos anunciados

**Prioridade:** Alta. **Plano relacionado:** D06.

**Problema e causa:** Todas as fotos e downloads usam latest.jpg em vez do frame da linha. Comparar mostra só metadados. Player usa /assets#clip, que é endpoint JSON; fragmento não seleciona binário no servidor. Faltam rota/URL de MP4 e arquivo original por índice, histórico navegável e controles completos de paginação.

**Correção necessária:** Servir arquivo exato por identidade com autorização, player apontando MP4 real, download correto, comparação visual e consulta paginada de diagnósticos anteriores.

**Evidência:** [S:apps/admin/app/(admin)/admin/camera-test/page.tsx:200](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/admin/app/(admin)/admin/camera-test/page.tsx:200) · [S:apps/admin/app/(admin)/admin/camera-test/page.tsx:222](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/admin/app/(admin)/admin/camera-test/page.tsx:222) · [S:apps/api/routers/admin_camera_diagnostics.py:241](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/admin_camera_diagnostics.py:241)

### RA29 — Indicadores de ao vivo e atualização podem mostrar estado falso

**Prioridade:** Média/alta. **Plano relacionado:** D04/D06.

**Problema e causa:** live pode ser true sem primeiro frame, porque stale é undefined. Falha de rede conserva age/stale antigo. Poll da prévia não atualiza diag.status; gateway_code existente vira 'online' sem heartbeat recente. Foto/clipe têm apenas atualização por timeout de 4 s, anterior ao fim do clipe de 10 s.

**Correção necessária:** Derivar estado de amostra recente, heartbeat e status atualizado; envelhecer imagem localmente, parar polling em terminal/aba oculta e atualizar foto/clipe até estado final sem timeout usado como sincronização.

**Evidência:** [S:apps/admin/app/(admin)/admin/camera-test/page.tsx:63](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/admin/app/(admin)/admin/camera-test/page.tsx:63) · [S:apps/admin/app/(admin)/admin/camera-test/page.tsx:132](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/admin/app/(admin)/admin/camera-test/page.tsx:132) · [S:apps/admin/app/(admin)/admin/camera-test/page.tsx:156](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/admin/app/(admin)/admin/camera-test/page.tsx:156)

### RA30 — Retenção pode entrar em loop e não limpa todo o histórico

**Prioridade:** Alta. **Plano relacionado:** D01/D08.

**Problema e causa:** Loop de quota seleciona sempre o diagnóstico mais antigo e zera received_bytes. Se total continuar acima do limite, seleciona a mesma linha agora zero e não progride. Limpeza não remove clip_key e preserva latest mesmo quando expirado. Não há agendamento operacional identificado para manutenção. Contador histórico é alterado para representar exclusão de objetos.

**Correção necessária:** Limpeza finita e idempotente por lote, seleção de objetos retidos e bytes armazenados separados de bytes recebidos; remover MP4/prévia expirada sem tocar missão; agendar manutenção no mecanismo existente.

**Evidência:** [S:src/pages_to_audio/camera_diagnostics/service.py:342](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/camera_diagnostics/service.py:342) · [S:src/pages_to_audio/camera_diagnostics/service.py:439](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/camera_diagnostics/service.py:439)

### RA31 — Perfis de build não ativam diagnóstico nem garantem isolamento

**Prioridade:** Alta. **Plano relacionado:** F08/D07.

**Problema e causa:** Script procura build/config/sdkconfig, ausente no build real; pode voltar a set-target/fullclean. Defaults Diagnostic só ligam CAPTURE_DIAGNOSTIC_AUTO_START, não CAPTURE_DIAG_ENABLE. Defaults não substituem necessariamente sdkconfig já existente; Production/Diagnostic compartilham diretório. Comandos nativos não têm checagem explícita de LASTEXITCODE.

**Correção necessária:** Usar diretórios e sdkconfigs separados, flags corretas, verificação pós-configuração e falha imediata por exit code. Não alegar build diagnóstico porque arquivo C está listado.

**Evidência:** [F:tools/build_windows.ps1:16](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/tools/build_windows.ps1:16) · [F:tools/sdkconfig.diagnostic.defaults:1](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/tools/sdkconfig.diagnostic.defaults:1) · [F:main/Kconfig.projbuild:138](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/main/Kconfig.projbuild:138)

### RA32 — CI 'integração ativa' não tem testes e não bloqueia deploy completo

**Prioridade:** Alta. **Plano relacionado:** S09/A35.

**Problema e causa:** tests/integration contém só __init__.py; collect-only não coletou testes. Deploy depende apenas do build do próprio workflow, não de Android, integração e demais jobs da CI. Testes chamados 'funcionais' do painel procuram strings nos fontes, sem executar UI; podem passar com player JSON e fotos erradas.

**Correção necessária:** Adicionar integração real e testes funcionais dos fluxos; exigir gates do mesmo SHA antes de promover; tratar zero testes como erro explícito.

**Evidência:** [S:.github/workflows/ci.yml:74](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/.github/workflows/ci.yml:74) · [S:.github/workflows/deploy-pages-rgb.yml:118](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/.github/workflows/deploy-pages-rgb.yml:118) · [S:apps/admin/__tests__/flows.test.mjs:12](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/admin/__tests__/flows.test.mjs:12)

### RA33 — Publicação e deploy usam tags incompatíveis e smoke insuficiente

**Prioridade:** Alta. **Plano relacionado:** S11/S12.

**Problema e causa:** Imagem é publicada sha-curto, deploy usa sha completo. Digests registrados não são consumidos na implantação. Script só compara variável de projeto, não projeto Compose já instalado. Backup usa DATABASE_URL diretamente; URLs SQLAlchemy +asyncpg precisam conversão antes de pg_dump. Worker não herda extra_hosts do app quando endereço depende de host.docker.internal. Smoke não compara versão e aceita payload worker não saudável em 200.

**Correção necessária:** Implantar por digest ou tag exata produzida, verificar projeto real, backup restaurável com URL libpq, conectividade do worker e estados/versões no smoke. Não promover por qualquer 200.

**Evidência:** [S:.github/workflows/deploy-pages-rgb.yml:59](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/.github/workflows/deploy-pages-rgb.yml:59) · [S:.github/workflows/deploy-pages-rgb.yml:147](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/.github/workflows/deploy-pages-rgb.yml:147) · [S:scripts/deploy-pages-rgb.sh:24](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/scripts/deploy-pages-rgb.sh:24) · [S:scripts/backup-db.sh:22](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/scripts/backup-db.sh:22)

### RA34 — Readiness não comprova storage/worker e ambiente responde código anterior

**Prioridade:** Alta. **Plano relacionado:** S08/S11.

**Problema e causa:** _storage_check apenas instancia adapter/verifica configuração, sem I/O remoto. worker_health usa chamada de describe_task_queue a revisar contra a API do SDK e devolve 200 para no_pollers/not_configured. Endpoint local real 8081 com Host correto devolveu {status:ready, checks:{}}: não corresponde à nova implementação lida. Pedido Python ao domínio público recebeu 403 Cloudflare 1010; navegador abriu login.

**Correção necessária:** Verificar dependências com I/O limitado, request SDK correto, falha de prontidão sem pollers e identidade ativa de release. Distinguir bloqueio de acesso de falha da aplicação.

**Evidência:** [S:apps/api/routers/health.py:133](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/health.py:133) · [S:apps/api/routers/health.py:173](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/health.py:173)

### RA35 — Artefatos e registros não correspondem ao código diagnóstico atual

**Prioridade:** Alta. **Plano relacionado:** F08/F10/D07.

**Problema e causa:** BIN em build e release tem SHA 3cf029a5b337d4f25e5d7c6c780d9d68f3ca396d0dc7cb8c7712c7cb46e2d312, anterior às fontes diagnósticas. Esse binário não comprova D03/D04. Código diagnóstico do servidor permanece modificado/não rastreado além dos commits be34d8a/c282758. Firmware é abrangido por Git ancestral do perfil do usuário, não repo isolado confiável para stage global.

**Correção necessária:** Congelar nova release somente após correções, com manifesto de fontes/configuração/binários e commit/digest correspondente. Restringir stage ao projeto; não publicar arquivos do perfil pessoal.

**Evidência:** [F:build/pages_to_audio_capture_v2.bin:1](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/build/pages_to_audio_capture_v2.bin) · [F:release/fw_2_4_0/pages_to_audio_capture_v2.bin:1](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/release/fw_2_4_0/pages_to_audio_capture_v2.bin) · [S:docs/REGISTRO_EXECUCAO_D00_D08_DIAG_2026-09-09.md:1](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/docs/REGISTRO_EXECUCAO_D00_D08_DIAG_2026-09-09.md:1)

### RA36 — Execução física, TLS, builds finais e deploy continuam sem comprovação

**Prioridade:** Bloqueio de aceite. **Plano relacionado:** S10/H2/H4/F09/D06–D08.

**Problema e causa:** Nenhuma evidência apresentada comprova a missão completa, diagnóstico físico ou novo deploy. Nesta revisão a COM3 está listada e há serviços nas portas 5432/8081; logo indisponibilidades antigas precisam ser sondadas novamente. COM3 não prova modelo, firmware ou sensor. Não foi aberto serial, enviado comando de câmera ou executado flash.

**Correção necessária:** Reinventariar ambiente real sem repetir bloqueios desatualizados; após corrigir código, identificar placa/telefone, instalar artefatos e executar matrizes reais antes de declarar pronto.

**Evidência:** [S:docs/REGISTRO_EXECUCAO_S00_S05.md:1](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/docs/REGISTRO_EXECUCAO_S00_S05.md:1) · [F:docs/REGISTRO_EXECUCAO_F06-F11_2026-09-09.md:1](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/docs/REGISTRO_EXECUCAO_F06-F11_2026-09-09.md:1)

## Alinhamento dos resumos

| Resumo apresentado | Conclusão da conferência |
| --- | --- |
| S00–S12 executados em código | Parcial. Ponte e workflow têm bloqueios próprios de código, além dos bloqueios externos já informados |
| 20 atividades reais | Não confirmado: várias atividades são cascas sem processamento, e materialização tem TypeError |
| Outbox/ACK duráveis concluídos | Parcial: dispatcher existe, mas há despacho pré-commit e ACK local sem conciliação |
| Firmware F00–F11 com build OK | Há BIN anterior e correções compiladas; não valida fontes diagnósticas posteriores nem remove caminhos ram_only/clear |
| Perfil diagnóstico e produção separados | Não confirmado operacionalmente: script e defaults não isolam/ativam o diagnóstico como documentado |
| Diagnóstico completo em código com flag off | Não confirmado: falta ligação/entrega de controle, há stop prematuro, fila incorreta e mídia servida por rotas erradas |
| CI com integração ativa | YAML ativado, mas sem casos de integração e sem dependência completa do deploy |
| Build/deploy/físico pendentes por ambiente | Pendências reais, porém inventário precisa atualização; COM3 e serviços locais agora existem |

A política automática de início foi registrada pelo executor de firmware como decisão técnica autorizada naquela execução. Esta revisão não a troca nem exige reconfirmação sem necessidade; pede apenas unificar os documentos normativos, que ainda contêm a escolha como pendente, e validar o comportamento físico.

O diagnóstico foi implementado antes de H4 dos planos principais, contrariando a ordem pedida. Mantê-lo desativado é necessário, mas não substitui corrigir seus hooks e demonstrar ausência de regressão. Primeiro concluir a missão base; depois habilitar diagnóstico no dispositivo de teste.

## Limites da revisão e correção aplicada

Nenhuma correção funcional, migração, upload de imagem, provider pago, flash, push ou deploy foi executado nesta revisão. Houve somente análise, verificações de leitura/compilação sem emissão e produção de documentação.

Os achados de código são suficientes para impedir aprovação global. Eles não são uma promessa de ausência de outros defeitos: após as correções, executar os gates reais do plano, inclusive banco/storage/Temporal, APK, placa e navegador autenticado.

## Resultado e pendências

Executar o plano de conclusão vinculado, preservando os três planos anteriores como referência e reclassificando DONE quando existir apenas código parcial/protocolo. A entrega final deve identificar separadamente: implementado, compilado, testado em integração real, instalado e aprovado em uso físico.

## Revalidação complementar desta entrega

- A suíte oficial foi repetida em ambiente temporário congelado, com o mesmo `PYTHONPATH=.` da CI: **433 passaram, 1 skip**. `ruff check src/ apps/` também passou.
- `pytest tests/integration -m integration --collect-only` coletou **zero testes** e terminou com código 5.
- O painel executou 6 testes verdes; a leitura do arquivo confirmou que são inspeções de strings (`readFileSync`/`includes`), não testes de navegador.
- O build Android continua bloqueado: `JAVA_HOME`/JDK não estão disponíveis.
- O validador estrutural do firmware passou, mas o ESP-IDF não está disponível no PATH. Não houve novo link.
- O perfil `Diagnostic` não ativa `CONFIG_CAPTURE_DIAG_ENABLE`; ele ativa apenas `CONFIG_CAPTURE_DIAGNOSTIC_AUTO_START`.
- O BIN `3cf029a5...46e2d312` foi gerado às 05:34 e as fontes `diag_camera.c`/`app_main.c` foram alteradas depois das 08:09; portanto o BIN não contém essas fontes atuais.
- No momento desta revalidação, não foi enumerada porta COM. PostgreSQL 5432 e HTTP 8081 estavam em escuta.
- `GET /api/v1/health/ready` local retornou HTTP 200 com `{"status":"ready","checks":{}}`, incompatível com a readiness nova lida no workspace.
- No navegador real, `/admin/camera-test` publicado redirecionou para `/admin/login`; a tela de login estava visualmente íntegra e sem erro de Console observado. Nenhuma credencial foi usada, logo galeria/player não foram validados.
