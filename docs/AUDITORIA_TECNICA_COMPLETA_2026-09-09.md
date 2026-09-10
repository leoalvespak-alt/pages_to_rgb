# Auditoria técnica — servidor, painel e gateway Android

**Projeto:** Pages to Audio / Pages RGB  
**Data da auditoria e consolidação:** 9 de setembro de 2026  
**Diretório analisado:** `C:/Users/Lenovo/Downloads/pagestoaudio_servidor`  
**Revisão Git de referência:** `a6b2deaad3493d6ff4f5821008a2ead93ca20d33`  
**Natureza do trabalho:** análise, investigação, diagnóstico e recomendações; sem implementação de correções.

> Este relatório consolida a auditoria realizada na conversa. Os testes e as observações de ambiente descritos foram realizados durante aquela análise; a geração deste documento não representa uma nova execução de todos os testes nem garante que serviços externos permaneçam no mesmo estado.

## 1. Escopo e preservação do projeto

Foram examinados o backend Python, as rotas da API, o painel administrativo Next.js, o aplicativo gateway Android, os componentes de captura, armazenamento, OCR, IA, RAG, áudio, entrega RGB, workflows, infraestrutura e testes.

O pedido inicial utilizou a palavra “firmware”. Após a informação de que o firmware estava sendo analisado em outra tarefa, o escopo desta auditoria foi definido como o projeto do servidor e seus clientes. **O código do firmware ESP32-S3 não foi auditado aqui.**

Pasta do firmware informada pelo usuário, apenas para delimitação do escopo:

`C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1`

Não foram alterados código-fonte, configurações, migrações ou dados de produção durante a auditoria. Não houve implantação, commit, reindexação real, exclusão de documentos ou teste destrutivo. A árvore Git estava limpa ao concluir a análise e imediatamente antes de criar este relatório. A criação deste arquivo Markdown foi autorizada posteriormente pelo usuário.

Foi aplicada a skill de diagnóstico: [fullstack-diagnosis](C:/Users/Lenovo/.codex/skills/fullstack-diagnosis/SKILL.md), incluindo inspeção direta do navegador quando aplicável. A auditoria também utilizou leitura estática, rastreamento de chamadas, inspeção de dependências e reproduções isoladas. Não havia diretório `.codegraph/` na raiz inspecionada, portanto CodeGraph não foi utilizado.

## 2. Diagnóstico principal

O problema mais importante é a distância entre os componentes existentes e o fluxo realmente conectado.

O worker principal executa atividades simuladas para etapas essenciais, enquanto o Android e a API apresentam divergências de autenticação e formato de mensagens. Há também janelas de falha entre fechamento da sessão, persistência, despacho ao Temporal e entrega do resultado.

Isso permite situações em que:

- A aplicação aparenta estar disponível, mas não consegue iniciar o processamento.
- A captura é encerrada sem que todas as imagens tenham sido confirmadas.
- O fluxo avança com resultados simulados.
- Uma sessão fica bloqueada sem recuperação automática.
- Uma falha de armazenamento aparenta sucesso usando memória temporária.
- Os testes passam sem comprovar uma prova real processada de ponta a ponta.

A prioridade recomendada é restaurar um caminho mínimo, real e verificável de captura até entrega. Otimizações de desempenho vêm junto de algumas dessas correções, especialmente no polling, na câmera e em operações bloqueantes, mas não substituem a integração funcional.

## 3. Como interpretar as evidências

### 3.1 Níveis de prioridade

| Prioridade | Significado neste relatório |
|---|---|
| Crítico | Impede o funcionamento do caminho principal na configuração/código analisado ou substitui processamento essencial por simulação. |
| Alto | Pode causar perda de trabalho, travamento de sessão, exposição de operações, ausência de persistência ou falha importante de integração. |
| Médio | Causa inconsistência, diagnóstico enganoso, custo desnecessário, bloqueio ou falha em componente específico. |

As prioridades representam impacto técnico sobre o objetivo do projeto. Não são uma pontuação formal de vulnerabilidades.

### 3.2 Tipos de evidência

| Classificação | O que significa |
|---|---|
| Reprodução isolada | O comportamento foi exercitado com entradas controladas, mocks ou armazenamento temporário. Não significa reprodução sobre dados reais. |
| Código | O comportamento decorre dos caminhos lidos e rastreados. A condição específica pode não ter sido reproduzida em dispositivo ou produção. |
| Ambiente observado | O serviço ou contêiner em execução apresentou o comportamento na consulta realizada. É uma observação pontual. |
| Latente | O defeito está em um componente ainda não conectado ao caminho principal ou depende de uma configuração/condição específica. |

As referências de linha correspondem ao código observado. Podem mudar após edições posteriores. Os links usam caminhos absolutos locais para facilitar abertura no ambiente do usuário.

## 4. Verificações executadas e resultados

| Verificação | Resultado | Alcance e limite |
|---|---|---|
| Testes unitários Python | **399 passaram**, aproximadamente 33,43 segundos; um aviso de depreciação do Starlette | Execução isolada; não comprova hardware, serviços pagos ou transações reais entre componentes. |
| TypeScript do painel | **Passou** | Verificação de tipos, sem execução completa das telas autenticadas. |
| Mypy ampliado em `src` e `apps/api` | **Falhou** | Saída com vários erros, incluindo opções de atividades Temporal, uso de configuração privada e incompatibilidades de retorno. Não foi consolidado um total porque a saída foi truncada. |
| Ruff em `src apps/api tests` | **30 ocorrências**, todas nos testes | São achados de análise estática/manutenção; não equivalem a 30 bugs funcionais. |
| Verificação de formatação | 19 arquivos seriam reformatados; 202 já formatados no escopo verificado | Nenhuma formatação foi aplicada. |
| Navegador: login administrativo | Tela carregou; acesso a `/admin` redirecionou para login | Screenshot examinado; não foi observado defeito visual evidente na tela consultada. |
| Console da tela consultada | Sem erros/avisos na amostra consultada | Não abrange todas as telas ou todos os fluxos. |
| Endpoint de prontidão | Respondeu `ready` com `checks: {}` | Não refletiu as falhas de dependências reportadas no diagnóstico separado. |
| Diagnóstico de dependências | Falha de consulta ao banco, Temporal indisponível, Supabase não configurado | Estado pontual; Supabase não configurado não é necessariamente defeito se outro storage for o escolhido. |
| Autenticação Android padrão | Requisição isolada recebeu **422** | Faltaram os cabeçalhos exigidos pelo servidor. |
| Conhecimento sem autenticação | Listagem respondeu **200** em consulta real e isolada | Nenhuma operação destrutiva foi executada. |
| Upload após `LOCKED` | Aceito em reprodução isolada | Banco/storage simulados; confirmou ausência da restrição no caminho exercitado. |
| Cursor RGB | Mudança inicial de estado ficou invisível com cursor repetido | Reprodução isolada do cálculo de snapshot. |
| Fallback R2 em memória | Objeto visível em uma instância e ausente em outra | Reprodução isolada; evidencia ausência de durabilidade do fallback. |
| SQL de busca vetorial | Parâmetro `:embedding::vector` permaneceu sem vínculo na compilação | Verificação com SQLAlchemy e dialeto asyncpg; não depende de uma busca real em produção. |
| Preservação do código | Git sem alterações ao fim da auditoria | Este Markdown foi criado depois, por solicitação explícita. |

### 4.1 Ambiente de execução dos testes

Os testes Python usaram um ambiente WSL preexistente, em:

`/home/deploy/pages_to_audio_server_venv/bin/python`

Esse ambiente utilizava Python 3.14. Não era uma reconstrução exata da imagem de produção com Python 3.12 e seu lockfile. Essa diferença limita a equivalência entre teste local e implantação.

A execução foi iniciada a partir de `/tmp`, com o projeto no `PYTHONPATH`, evitando carregar a configuração real da raiz como configuração de execução dos testes. As reproduções funcionais utilizaram banco e armazenamento simulados quando necessário.

### 4.2 Observações pontuais do ambiente em execução

Foram encontrados serviços da API, painel e proxy. Não foi identificado worker ativo nem servidor Temporal escutando na porta esperada no ambiente inspecionado.

A consulta ao diagnóstico de dependências, registrada em **2026-09-09T06:21:56Z**, apresentou:

- Banco: indisponível no teste, com `TimeoutError`, aproximadamente 3484,9 ms.
- Temporal: indisponível, com `RuntimeError`, aproximadamente 52,74 ms.
- Supabase: não configurado.

Uma verificação TCP posterior ao endereço configurado do banco retornou sucesso. Portanto, **a causa exata da falha da consulta ao banco não foi estabelecida**. Não há base para concluir simplesmente que o banco estava desligado ou que havia bloqueio de rede.

Os arquivos locais `health.py`, `gateway.py`, `worker.py`, `fakes.py` e `frame_upload.py` foram comparados por hash com os correspondentes do contêiner, e coincidiram. Essa comparação abrange esses arquivos, não todo o ambiente ou o APK instalado.

## 5. Achados prioritários detalhados

### A01 — Atividades simuladas no processamento principal

**Prioridade:** crítico.  
**Evidência:** código e coincidência dos arquivos centrais comparados com o contêiner.

**Problema:** o worker registra `ALL_FAKE_ACTIVITIES` diretamente. Não há, nesse registro, uma condição que limite essas atividades ao ambiente de testes.

As atividades simuladas não são apenas implementações reais com nomes antigos. Entre os comportamentos lidos estão:

- Validação que retorna sucesso sem validar a sessão efetivamente.
- OCR que retorna uma quantidade fixa de execuções.
- Gate que retorna aprovação fixa.
- Resolução que informa dez questões resolvidas.
- Publicação de áudio que devolve uma chave de arquivo sem produzir o áudio.
- Conclusão que devolve `completed: true` sem concluir a sessão no banco.

O workflow combina essas atividades com a publicação RGB real. Esta depende de questões e respostas persistidas que as etapas simuladas não produzem.

**Impacto:** o workflow pode avançar sem processar uma prova real. O resultado de conclusão do workflow não prova a conclusão persistida da sessão nem a existência de um arquivo de áudio. A publicação RGB pode encontrar lacunas e não disponibilizar o resultado esperado.

**Causa estrutural:** implementações demonstrativas ocupam o mesmo caminho de execução usado pelo worker normal, enquanto componentes reais de IA/OCR estão separados.

**Simplificação proposta:** conectar uma sequência mínima real, com saída persistida em cada fronteira necessária. Simulações devem ser selecionadas explicitamente em testes. Não ampliar estados, recuperações e provedores antes de comprovar uma execução completa.

**Teste recomendado:** enviar uma prova conhecida e verificar imagens persistidas, OCR efetivamente executado, respostas gravadas, transição final da sessão e resultado entregue. Asserções não devem depender apenas do retorno `completed`.

**Referências:** [src/pages_to_audio/workflows/worker.py:37](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/workflows/worker.py:37), [src/pages_to_audio/workflows/activities/fakes.py:36](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/workflows/activities/fakes.py:36), [src/pages_to_audio/workflows/activities/fakes.py:185](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/workflows/activities/fakes.py:185), [src/pages_to_audio/workflows/process_exam.py](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/workflows/process_exam.py).

### A02 — Autenticação incompatível entre Android padrão e API

**Prioridade:** crítico.  
**Evidência:** código e reprodução isolada com HTTP 422.

**Problema:** o Android usa segredo vazio na configuração padrão. Seu interceptor envia identificação de dispositivo e outros metadados, mas não envia `X-Gateway-Id`. A API exige `Authorization` e `X-Gateway-Id`.

A configuração padrão também utiliza identificador fixo e não apresenta um fluxo efetivo de provisionamento persistido nesse caminho.

**Reprodução:** uma requisição com os cabeçalhos produzidos pela configuração padrão foi rejeitada por ausência dos campos obrigatórios. Esse teste não depende de câmera, firmware ou OCR.

**Impacto:** o aplicativo construído com essa configuração não consegue iniciar o fluxo autenticado esperado. Se várias instalações utilizarem o mesmo identificador, suas identidades também podem colidir.

**Simplificação proposta:** uma única configuração persistida do gateway, contendo endereço, identificador único e credencial. Validar a conexão antes de permitir captura. Usar os mesmos nomes e obrigatoriedades de cabeçalhos no cliente e no servidor.

**Teste recomendado:** executar o login/hello com o interceptor real do Android, inclusive em instalação limpa, e verificar a associação correta entre gateway e dispositivo.

**Limite:** o APK efetivamente instalado não foi comparado ao código-fonte; a conclusão se refere ao aplicativo e à configuração analisados.

**Referências:** [apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/domain/GatewayConfig.kt:9](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/domain/GatewayConfig.kt:9), [apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/network/GatewayAuthInterceptor.kt:24](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/network/GatewayAuthInterceptor.kt:24), [src/pages_to_audio/auth/gateway.py:27](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/auth/gateway.py:27).

### A03 — Divergência no contrato de resultado e eventos RGB

**Prioridade:** alto.  
**Evidência:** comparação dos modelos e rastreamento de chamadas.

**Problemas encontrados:**

- O modelo Android espera `status`, enquanto a resposta correspondente do servidor usa `command`.
- O Android representa respostas como `List<String>`; o protocolo do servidor utiliza uma string como `"ABCDE"`.
- O evento modelado no Android não contém todos os campos exigidos pelo servidor, incluindo `session_id`, `next_index` e `item_count`.
- Os métodos de consulta e entrega de resultado não aparecem conectados ao fluxo normal de encerramento da sessão. Existem declarações e caminhos separados de teste.

**Impacto:** mesmo com autenticação corrigida, há risco de erro de desserialização, requisição rejeitada e ausência de entrega do resultado no aplicativo.

**Simplificação proposta:** definir o protocolo uma única vez e gerar os modelos compatíveis a partir do OpenAPI, quando viável. Conectar um fluxo normal de consulta, obtenção da sequência e confirmação de entrega.

**Teste recomendado:** usar exemplos reais de resposta da API nos testes Android e enviar eventos produzidos pelos DTOs Kotlin para a validação real do backend.

**Referências:** [apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/network/ApiService.kt:256](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/network/ApiService.kt:256), [apps/api/routers/gateway_rgb.py:29](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/gateway_rgb.py:29), [src/pages_to_audio/rgb/schemas.py](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/rgb/schemas.py), [apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/domain/SessionRepository.kt:206](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/domain/SessionRepository.kt:206).

### A04 — Sessão pode ficar LOCKED sem workflow e sem recuperação automática

**Prioridade:** alto.  
**Evidência:** código.

**Problema:** o fechamento altera o estado para `LOCKED` e tenta iniciar o Temporal dentro da requisição. Se houver falha, o erro é registrado, mas o endpoint ainda retorna a sessão como bloqueada com sucesso.

Uma repetição do fechamento encontra `LOCKED`, atualiza a indicação de processamento quando possível e retorna sem repetir o início do workflow. O caminho administrativo de repetição aceita outro estado de falha, não resolvendo normalmente essa sessão bloqueada.

Há uma segunda janela: o início do workflow ocorre antes do commit feito pela dependência da requisição. Um worker rápido pode tentar observar um estado ainda não confirmado no banco.

**Impacto:** a captura termina aparentemente bem, mas o trabalho não é executado ou começa com uma visão inconsistente do estado.

**Simplificação proposta:** registrar, na mesma transação do fechamento, uma pendência durável de processamento. Um despachante deve iniciar o workflow de forma idempotente e repetir falhas transitórias. Centralizar fechamento e despacho, evitando implementações paralelas.

**Teste recomendado:** simular Temporal indisponível no fechamento; restaurar o serviço; comprovar início automático único do processamento sem intervenção manual e sem reabrir a captura.

**Referências:** [apps/api/routers/gateway.py:491](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/gateway.py:491), [apps/api/routers/gateway.py:564](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/gateway.py:564), [apps/api/dependencies.py:15](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/dependencies.py:15), [apps/api/routers/admin_sessions.py:355](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/admin_sessions.py:355), [src/pages_to_audio/capture/lock.py](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/capture/lock.py).

### A05 — Infraestrutura e configuração Temporal não garantem consumidor ativo

**Prioridade:** alto.  
**Evidência:** código, inspeção de serviços e verificação de exceção.

**Problemas encontrados:**

- O Compose de produção não define serviço para o worker.
- Não foi identificado worker ativo nem Temporal escutando na porta configurada no ambiente consultado.
- O starter procura uma configuração de fila em `Client._config` e recorre a um valor fixo. O worker utiliza `TEMPORAL_TASK_QUEUE`; uma configuração diferente pode separar produtor e consumidor.
- O tratamento de workflow já iniciado captura `RPCError` e procura texto. Foi verificado que `WorkflowAlreadyStartedError` não é subclasse de `RPCError` no ambiente usado.

**Impacto:** workflows podem não ser iniciados, permanecer sem consumidor ou apresentar erros em repetições que deveriam ser idempotentes.

**Simplificação proposta:** passar explicitamente a mesma fila para starter e worker, tratar a exceção específica e declarar o processo consumidor na implantação. Isso não exige substituir Temporal; exige uma configuração única e um despacho recuperável.

**Teste recomendado:** alterar a fila por configuração e comprovar consumo; repetir o mesmo identificador de workflow; reiniciar o worker com trabalho pendente.

**Referências:** [src/pages_to_audio/workflows/starter.py:48](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/workflows/starter.py:48), [src/pages_to_audio/workflows/worker.py:39](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/workflows/worker.py:39), [infra/docker-compose.pages-rgb.prod.yml](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/infra/docker-compose.pages-rgb.prod.yml).

### A06 — Prontidão reporta sucesso sem verificar dependências

**Prioridade:** alto.  
**Evidência:** código e ambiente observado.

**Problema:** `/health/ready` devolve prontidão com verificações vazias. O diagnóstico separado reportou falha na consulta ao banco e indisponibilidade do Temporal. Os healthchecks da implantação usam liveness, que prova apenas que o processo responde.

**Impacto:** monitoramento e implantação podem classificar a aplicação como pronta quando o caminho essencial não funciona.

**Simplificação proposta:** separar claramente processo vivo de capacidade de atender a operação. A prontidão deve refletir as dependências realmente obrigatórias para aquele serviço, com verificação limitada por timeout. Dependências opcionais devem aparecer como opcionais.

**Teste recomendado:** interromper, em ambiente de teste, cada dependência obrigatória e verificar a prontidão e a mensagem operacional resultantes.

**Limite:** a causa raiz da falha de consulta ao banco não foi determinada. A conexão TCP posterior funcionou.

**Referências:** [apps/api/routers/health.py:23](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/health.py:23), [infra/docker-compose.pages-rgb.prod.yml](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/infra/docker-compose.pages-rgb.prod.yml).

### A07 — Imagem de produção não contém dependências de caminhos reais

**Prioridade:** alto.  
**Evidência:** configuração de build e inspeção do contêiner.

**Problema:** o Dockerfile usa `uv sync --frozen --no-dev --all-extras`, mas parte das dependências está em grupos, que não são instalados por essa seleção de extras.

No contêiner foram identificadas ausências de `google.auth`, `pypdf`, `numpy`, `cv2`, `ffmpeg` e `ffprobe`, usados por componentes do projeto. Algumas dessas dependências também não estão declaradas no conjunto esperado.

**Impacto:** quando os componentes reais forem conectados, OCR autenticado, PDF, processamento de imagem ou áudio poderão falhar imediatamente.

**Distinção importante:** a ausência do SDK completo do Document AI, sozinha, não demonstra falha, pois o adaptador usa REST. A ausência de `google.auth` é relevante porque o código o utiliza.

**Simplificação proposta:** definir dependências explícitas por serviço implantado e executar verificações de importação e presença dos executáveis durante o build.

**Teste recomendado:** construir a imagem a partir do lockfile e executar operações mínimas de cada capacidade anunciada, sem depender de bibliotecas instaladas apenas no host.

**Referências:** [infra/docker/Dockerfile.pages-rgb:13](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/infra/docker/Dockerfile.pages-rgb:13), [pyproject.toml](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/pyproject.toml).

### A08 — Rotas de conhecimento sem autenticação

**Prioridade:** alto.  
**Evidência:** código, HTTP 200 real e reprodução isolada.

**Problema:** o router de conhecimento não aplica autenticação aos endpoints analisados. A listagem foi acessível sem credenciais. O código também expõe criação, remoção e reindexação sem a dependência de autenticação correspondente.

**Impacto:** terceiros que alcancem as rotas podem acessar funcionalidades administrativas. Se o processamento externo estiver habilitado, operações de ingestão também podem gerar consumo e custo.

**Simplificação proposta:** aplicar autenticação e autorização no router e definir limites de tamanho e operação. Manter uma fronteira única de proteção evita esquecer a verificação em novos endpoints.

**Teste recomendado:** requisições sem credencial devem ser rejeitadas; usuários sem papel adequado não devem executar mutações.

**Limite:** não foram feitas exclusões, criações ou reindexações no ambiente real durante a auditoria.

**Referência:** [apps/api/routers/knowledge.py:34](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/knowledge.py:34).

### A09 — Conhecimento usa memória volátil e operações incompletas

**Prioridade:** alto.  
**Evidência:** código.

**Problema:** `_DOCS` e `_CHUNKS` armazenam os dados em memória do processo. A chave de armazenamento do documento é produzida sem upload correspondente. A reindexação retorna aceitação sem reindexar. O retriever construído não alimenta efetivamente o caminho de busca mostrado pelo router.

**Impacto:** reinícios apagam conteúdo; processos distintos divergem; a interface pode anunciar uma operação que não ocorreu. Modelos de persistência existentes no projeto não tornam esse endpoint persistente automaticamente.

**Simplificação proposta:** uma única implementação persistente de documentos, fragmentos e busca. Até ela existir, apresentar a função como indisponível/incompleta em vez de devolver sucesso artificial.

**Teste recomendado:** inserir documento em ambiente de teste, reiniciar o processo, consultar de outro processo e comprovar persistência e reindexação real.

**Referências:** [apps/api/routers/knowledge.py:80](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/knowledge.py:80), [apps/api/routers/knowledge.py:182](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/knowledge.py:182), [apps/api/routers/knowledge.py:290](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/knowledge.py:290).

### A10 — Upload aceita imagens novas depois do fechamento da sessão

**Prioridade:** alto.  
**Evidência:** código e reprodução isolada.

**Problema:** o upload rejeita estados terminais, mas `LOCKED` e estados de processamento não são terminais. O indicador de upload tardio também não resolve a aceitação nesse caminho.

**Reprodução:** uma nova imagem foi aceita em sessão `LOCKED` usando UOW e storage simulados.

**Impacto:** o conjunto de imagens de uma prova pode mudar depois de ser considerado congelado. Isso dificulta reprodutibilidade, contagem e interpretação do resultado.

**Simplificação proposta:** definir os estados que aceitam imagens novas em uma única regra de domínio. Repetições de objetos já conhecidos podem retornar a confirmação anterior; não devem reabrir a captura silenciosamente.

**Teste recomendado:** enviar imagem nova e repetida em cada estado relevante, distinguindo idempotência de inclusão tardia.

**Referências:** [src/pages_to_audio/capture/frame_upload.py:123](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/capture/frame_upload.py:123), [src/pages_to_audio/domain/enums/session_state.py](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/domain/enums/session_state.py).

### A11 — Encerramento Android compete com captura e upload

**Prioridade:** alto.  
**Evidência:** código.

**Problema:** o Android aguarda a fila esvaziar antes de parar o polling. Durante essa espera, podem ser produzidas novas capturas. Ao atingir 30 segundos, a espera termina e o encerramento prossegue mesmo com pendências.

Há também confirmação de captura antes de receber ACK dos uploads. Alguns métodos retornam `Result.failure`, mas os chamadores apenas usam `try/catch` ou ignoram o resultado; esse padrão não trata falhas encapsuladas em `Result`.

**Impacto:** sessão incompleta, contagem otimista e término com imagens ainda não confirmadas.

**Simplificação proposta:** parar novas capturas, aguardar tarefas em andamento, confirmar a persistência dos uploads e só então fechar. Se houver pendência, manter estado explícito e recuperável.

**Teste recomendado:** rede lenta, desconexão no último frame, falha ao salvar no spool e timeout de envio. O sistema deve conservar as pendências e não anunciar fechamento completo.

**Referências:** [apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/ui/SessionViewModel.kt:215](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/ui/SessionViewModel.kt:215), [apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/ui/SessionViewModel.kt:349](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/ui/SessionViewModel.kt:349), [apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/ui/SessionViewModel.kt:447](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/ui/SessionViewModel.kt:447).

### A12 — Quantidade recebida tem duas fontes concorrentes

**Prioridade:** alto.  
**Evidência:** código.

**Problema:** o upload incrementa `received_frames`, enquanto `captureComplete` atribui esse campo a partir do número informado pelo cliente. O Android pode informar conclusão antes dos uploads restantes. A captura também pode ainda não existir no instante da chamada, resultando em falha que o cliente não trata adequadamente.

**Impacto:** uploads posteriores podem incrementar uma contagem já preenchida. Quantidade declarada, quantidade persistida e estado de conclusão deixam de representar a mesma coisa.

**Simplificação proposta:** o servidor calcula a quantidade recebida a partir dos frames persistidos. O cliente informa expectativa e intenção de encerramento; o servidor confirma a conclusão.

**Teste recomendado:** variar a ordem entre conclusão e uploads, inclusive com repetições e concorrência. O total deve permanecer igual ao número de frames únicos persistidos.

**Referências:** [apps/api/routers/gateway.py:975](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/gateway.py:975), [src/pages_to_audio/capture/frame_upload.py:252](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/capture/frame_upload.py:252).

### A13 — Polling sem espera efetiva e comandos baseados em contador

**Prioridade:** alto.  
**Evidência:** código.

**Problema:** `wait_ms` não produz espera real no endpoint. Os comandos seguem um contador com sequência de pausa, retomada, sondagens e pings. O cursor fica em memória e avança a cada consulta.

No Android, respostas bem-sucedidas não recebem uma pausa equivalente a um long polling. O cursor pode ser avançado antes da captura ser concluída com sucesso.

**Impacto:** excesso de requisições, capturas contínuas em certas condições, consumo de bateria e perda de comando se a ação falhar após o avanço do cursor. Reinícios e múltiplos processos também dificultam consistência de cursores em memória.

**Simplificação proposta:** comandos associados à necessidade real da sessão, espera limitada, backoff em falhas e confirmação após a ação correspondente. Persistir apenas o estado que precisa sobreviver a reinícios.

**Teste recomendado:** deixar uma sessão ociosa, indisponibilizar a câmera e falhar uma captura. Medir requisições por minuto e confirmar que ações pendentes não desaparecem.

**Referências:** [apps/api/routers/gateway.py:351](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/gateway.py:351), [apps/api/routers/gateway.py:425](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/gateway.py:425), [apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/ui/SessionViewModel.kt:299](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/ui/SessionViewModel.kt:299).

### A14 — Câmera reinicializada por frame e trabalho bloqueante na interface

**Prioridade:** alto.  
**Evidência:** código; não foi medida a latência em aparelho físico.

**Problema:** o caminho de captura vincula novamente a câmera a cada frame, executando desvinculação e nova vinculação. Há espera por foco com `get(1200 ms)` dentro do contexto da thread principal. O callback padrão também conduz processamento de arquivo, EXIF e hash nesse contexto.

**Impacto:** congelamento perceptível da interface, atraso entre frames e trabalho repetido de hardware.

**Simplificação proposta:** manter a câmera vinculada enquanto o perfil permanecer válido. Aguardar foco por mecanismo suspensivo/callback. Executar leitura de arquivo e hash em contexto apropriado para I/O.

**Teste recomendado:** captura repetida em aparelho físico com medição do tempo de interface, intervalo entre frames e estabilidade ao alternar de tela/perfil.

**Referência:** [apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/camera/PhoneCameraCaptureSource.kt:145](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/camera/PhoneCameraCaptureSource.kt:145).

### A15 — Falha entre storage e banco pode bloquear uma repetição legítima

**Prioridade:** alto.  
**Evidência:** código; cenário de falha não foi injetado em produção.

**Problema:** o objeto é gravado antes da confirmação da transação do banco. Se a gravação funcionar e a persistência do registro falhar, a repetição pode não encontrar o frame no banco, mas encontrar o objeto imutável no storage e rejeitar o envio.

O script de reconciliação existente contém trabalho não implementado e não resolve automaticamente essa situação.

**Impacto:** imagem órfã e upload que não se recupera por simples repetição, embora o conteúdo seja o mesmo.

**Simplificação proposta:** reconhecer identidade e hash em repetições, recuperar o vínculo quando o objeto existente coincide e implementar reconciliação real. Banco e storage exigem uma política explícita para falha parcial.

**Teste recomendado:** injetar falha após a gravação do objeto e antes do commit; repetir o upload e verificar exatamente um frame vinculado.

**Referências:** [src/pages_to_audio/capture/frame_upload.py:213](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/capture/frame_upload.py:213), [scripts/reconcile_storage.py](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/scripts/reconcile_storage.py).

### A16 — Fallback R2 em memória pode aparentar persistência

**Prioridade:** alto.  
**Evidência:** código e reprodução isolada.

**Problema:** falha na inicialização do cliente R2 pode levar a armazenamento em memória. Novas instâncias do adaptador são criadas no fluxo normal, portanto o conteúdo desse fallback não é compartilhado de forma durável.

**Reprodução:** a instância A gravou e encontrou o objeto; a instância B não o encontrou.

**Impacto:** a API pode confirmar uma gravação que não estará disponível para a próxima operação.

**Simplificação proposta:** selecionar armazenamento real ou simulado explicitamente. Em produção, não converter falha de configuração em sucesso temporário. Reutilizar o cliente real quando adequado.

**Teste recomendado:** forçar falha de inicialização e verificar erro claro sem confirmação de persistência; validar leitura entre requisições e reinícios.

**Referências:** [src/pages_to_audio/storage/r2_storage.py:25](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/storage/r2_storage.py:25), [src/pages_to_audio/storage/__init__.py:13](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/storage/__init__.py:13).

### A17 — Cursor RGB repete o valor na primeira mudança de estado

**Prioridade:** médio.  
**Evidência:** reprodução isolada.

**Problema:** o resultado virtual `NOT_STARTED`, sem registro persistido, usa cursor `1`. O primeiro registro `PROCESSING` também começa em `1`.

**Reprodução:** após consultar `NOT_STARTED` no cursor `1`, uma consulta com esse cursor não recebeu atualização quando o estado passou para `PROCESSING`.

**Impacto:** uma mudança de estado observável fica invisível para o cliente.

**Simplificação proposta:** usar cursor virtual inicial `0` ou persistir o estado inicial. Toda mudança observável precisa de uma versão diferente.

**Teste recomendado:** percorrer ausência de registro, processamento, resultado e confirmação usando sempre o último cursor recebido.

**Referência:** [src/pages_to_audio/rgb/delivery.py:282](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/rgb/delivery.py:282).

### A18 — Cancelamento administrativo não interrompe todo o fluxo

**Prioridade:** alto.  
**Evidência:** código e risco de concorrência identificado.

**Problema:** o cancelamento altera a sessão no banco, mas não cancela o workflow correspondente. Caminhos posteriores não verificam o cancelamento uniformemente. A indicação de processamento pode restaurar estado de entrega que já estava cancelado, e a consulta de sequência não se baseia sempre no estado atual da sessão.

**Impacto:** trabalho e publicação podem continuar depois de o usuário cancelar. O painel e o consumidor do resultado podem observar estados diferentes.

**Simplificação proposta:** uma operação central de cancelamento, com sinalização ao workflow e barreira obrigatória antes de publicar ou disponibilizar resultados.

**Teste recomendado:** cancelar antes do processamento, durante OCR e imediatamente antes da publicação; nenhuma dessas situações deve produzir entrega normal posterior ao cancelamento.

**Referências:** [apps/api/routers/admin_sessions.py:299](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/admin_sessions.py:299), [src/pages_to_audio/rgb/delivery.py:247](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/rgb/delivery.py:247), [src/pages_to_audio/rgb/publisher.py](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/rgb/publisher.py).

## 6. Inconsistências adicionais e defeitos latentes

### A19 — Validação insuficiente de parâmetros e conteúdo de imagem

**Prioridade:** médio.  
**Evidência:** código e reproduções isoladas.

**Problema:** o modelo de início de sessão aceita valores como quantidade negativa de páginas, zero questões e proporção mínima maior que `1`. Foram aceitos, no caminho isolado de upload, índice negativo e conteúdo que começa com assinatura JPEG, mas não é uma imagem válida completa.

A checagem inicial de MIME/assinatura não equivale à decodificação da imagem. O arquivo também é lido integralmente antes da aplicação do limite de tamanho naquele caminho, e dimensões informadas pelo cliente não devem ser tomadas como validação do conteúdo.

**Impacto:** estados sem sentido, falhas posteriores difíceis de relacionar à entrada e consumo de memória desnecessário em entradas excessivas.

**Simplificação proposta:** limites explícitos nos modelos, validação de conteúdo efetivo e um limite de corpo aplicado antes da leitura integral quando possível. Derivar dimensões da imagem decodificada.

**Teste recomendado:** limites mínimos e máximos, arquivo truncado, assinatura falsa, índice negativo e corpo acima do limite.

**Referências:** [apps/api/routers/gateway.py:111](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/gateway.py:111), [src/pages_to_audio/capture/frame_upload.py](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/capture/frame_upload.py).

### A20 — Quantidade manuscrita padrão pode ignorar a configuração administrativa

**Prioridade:** médio.  
**Evidência:** código e validação do modelo.

**Problema:** `HandwrittenSessionStartRequest()` assume dez palavras. Quando o cliente omite o campo, esse padrão pode prevalecer sobre a quantidade configurada no administrador. No Android, o campo nulo pode ser omitido na serialização.

**Impacto:** o usuário configura uma quantidade, mas a sessão é criada com outra sem escolha explícita.

**Simplificação proposta:** ausência do campo significa herdar a configuração administrativa; um número enviado explicitamente significa sobrescrever, se isso for permitido.

**Teste recomendado:** configurar quantidade diferente de dez e iniciar a sessão com campo ausente e com valor explícito.

**Referência:** [apps/api/routers/handwritten.py:41](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/handwritten.py:41).

### A21 — Configuração de mínimo RGB não representa a política aplicada

**Prioridade:** médio.  
**Evidência:** comparação entre painel e política.

**Problema:** o painel oferece uma proporção mínima para RGB, mas a política exige todas as posições esperadas com respostas válidas.

**Impacto:** o usuário pode esperar uma entrega parcial permitida pela configuração, enquanto o servidor exige completude.

**Simplificação proposta:** tornar a regra real explícita e eliminar controle sem efeito. Se a entrega parcial for um requisito futuro, definir antes como representar lacunas sem deslocar a associação entre questão e resposta.

**Teste recomendado:** configurar proporção menor que `1` e uma questão ausente; a interface e o comportamento devem expressar a mesma regra.

**Referências:** [apps/admin/app/(admin)/admin/config/page.tsx:124](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/admin/app/(admin)/admin/config/page.tsx:124), [src/pages_to_audio/rgb/policy.py:45](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/rgb/policy.py:45).

### A22 — Snapshot de configuração da sessão é aplicado parcialmente

**Prioridade:** médio.  
**Evidência:** código; defeito latente no caminho de provedores.

**Problema:** a fábrica usa o snapshot para parte das escolhas, mas consulta a configuração atual para parâmetros como projeto, localização e processador, apesar de esses dados integrarem o snapshot.

**Impacto:** alterar a configuração administrativa depois de iniciar uma sessão pode mudar o processamento daquela sessão quando esse caminho estiver conectado. A reprodução de um resultado fica menos confiável.

**Simplificação proposta:** após criar a sessão, usar um único objeto de configuração congelada para todo o processamento. A configuração atual deve servir à criação de novas sessões, salvo alteração explicitamente solicitada.

**Teste recomendado:** criar sessão, alterar o administrador e comprovar que a sessão existente mantém os parâmetros originais.

**Referência:** [src/pages_to_audio/ai/factory.py:29](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/ai/factory.py:29).

### A23 — Limpeza de campos e teste de provedor podem usar configuração inesperada

**Prioridade:** médio.  
**Evidência:** código.

**Problemas encontrados:**

- Determinadas atualizações ignoram `None`, impedindo limpar um campo opcional anteriormente preenchido, como versão de processador.
- O caminho de “salvar e verificar” no painel condiciona o salvamento à presença de determinada chave. Alterar apenas projeto ou outros parâmetros pode testar valores ainda salvos no banco.

**Impacto:** o usuário pode acreditar que removeu um valor ou testou uma configuração nova, quando a operação usou a anterior.

**Simplificação proposta:** distinguir campo ausente de campo explicitamente nulo. Definir claramente se o teste utiliza o formulário atual ou a configuração persistida e implementar essa escolha de forma uniforme.

**Teste recomendado:** remover um valor opcional; modificar apenas o projeto; verificar o payload salvo e os parâmetros usados no teste.

**Referências:** [src/pages_to_audio/admin/settings_service.py:239](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/admin/settings_service.py:239), [apps/admin/app/(admin)/admin/config/page.tsx:100](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/admin/app/(admin)/admin/config/page.tsx:100).

### A24 — Consulta vetorial contém parâmetro SQL sem vínculo

**Prioridade:** médio.  
**Evidência:** compilação isolada; defeito latente no retriever.

**Problema:** a expressão SQL utiliza `:embedding::vector`. Na compilação com SQLAlchemy e asyncpg, esse trecho permaneceu literal e a lista de parâmetros vinculados ficou vazia.

O erro da consulta é capturado e convertido em lista vazia.

**Impacto:** falha de infraestrutura/SQL pode aparecer como ausência de conteúdo relevante, prejudicando o diagnóstico e a qualidade das respostas.

**Simplificação proposta:** usar cast explícito compatível com o vínculo de parâmetros. Distinguir “nenhum resultado” de “busca falhou”.

**Teste recomendado:** executar a consulta em PostgreSQL com a extensão usada pelo projeto e um vetor conhecido, verificando que há parâmetro vinculado e ordenação correta.

**Referência:** [src/pages_to_audio/rag/retrieval.py:283](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/rag/retrieval.py:283).

### A25 — Busca textual pode falhar com sintaxe de consulta e afetar a transação

**Prioridade:** médio.  
**Evidência:** código; dependente da entrada e do caminho de execução.

**Problema:** o texto é encaminhado a `to_tsquery`, cuja entrada tem sintaxe própria. Conteúdo comum com pontuação pode causar erro se não for preparado. Capturar a exceção e retornar vazio não necessariamente recupera a transação; a busca vetorial seguinte pode encontrar a mesma transação abortada.

**Impacto:** uma entrada problemática pode inutilizar as duas partes da recuperação e ser interpretada como nenhum documento encontrado.

**Simplificação proposta:** escolher a função PostgreSQL adequada a texto livre ou construir consulta validada. Tratar falha de transação explicitamente, sem ocultar o diagnóstico.

**Teste recomendado:** frases naturais com pontuação, operadores, aspas e caracteres especiais, seguidas de uma consulta vetorial na mesma operação.

**Referência:** [src/pages_to_audio/rag/retrieval.py:229](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/rag/retrieval.py:229).

### A26 — Endpoint assíncrono bloqueia esperando embedding

**Prioridade:** médio.  
**Evidência:** código.

**Problema:** o caminho usa `ThreadPoolExecutor`, mas espera `future.result()` dentro da função assíncrona. Isso bloqueia a thread que deveria continuar atendendo o event loop. Há também trabalho síncrono de extração e fragmentação no processamento do documento.

**Impacto:** uma chamada lenta ao serviço de embedding pode atrasar outras requisições do mesmo processo.

**Simplificação proposta:** aguardar a operação de forma assíncrona e deslocar trabalho bloqueante para executor apropriado. A criação de uma thread seguida de espera bloqueante não elimina o bloqueio do chamador.

**Teste recomendado:** retardar artificialmente o embedding enquanto outra requisição leve é atendida; medir sua latência.

**Referência:** [apps/api/routers/knowledge.py:404](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/knowledge.py:404).

### A27 — Autenticação OCR e formato de credencial são inconsistentes

**Prioridade:** médio.  
**Evidência:** código; componente real ainda não conectado ao workflow principal.

**Problemas encontrados:**

- A obtenção do token Google executa atualização síncrona de credencial dentro de uma função assíncrona.
- O teste administrativo aceita credencial em formato JSON ou como caminho de arquivo.
- O adaptador OCR tenta interpretar a credencial recebida como JSON, o que não cobre o mesmo caminho de arquivo aceito pelo teste administrativo.

**Impacto:** o teste de configuração pode aceitar uma credencial que falha no processamento real. Renovação síncrona de credencial também adiciona bloqueio e latência.

**Simplificação proposta:** uma rotina compartilhada de carregamento de credenciais e reutilização/renovação controlada do token. O teste de provedor deve utilizar o mesmo mecanismo do processamento real.

**Teste recomendado:** JSON válido, caminho válido, credencial inválida e token expirado usando o adaptador efetivo.

**Referências:** [src/pages_to_audio/ocr/providers/google_document_ai.py:49](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/ocr/providers/google_document_ai.py:49), [apps/api/routers/admin_settings.py:112](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/admin_settings.py:112).

### A28 — Referência de OCR bruto não corresponde à persistência efetuada

**Prioridade:** médio.  
**Evidência:** código; defeito latente.

**Problema:** o adaptador retorna uma chave no formato `sessions/unknown/ocr/google/{page_index}.json`, sem gravação correspondente nesse caminho. O identificador de sessão também não é efetivo.

**Impacto:** auditoria posterior pode apontar para um artefato inexistente. Se a mesma convenção for usada para persistir, sessões diferentes podem disputar o mesmo caminho.

**Simplificação proposta:** só retornar referência de artefato após a gravação confirmada, usando a identidade real da sessão e da execução.

**Teste recomendado:** após OCR, recuperar o artefato pela chave retornada e comparar o conteúdo bruto; repetir com duas sessões.

**Referência:** [src/pages_to_audio/ocr/providers/google_document_ai.py:211](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/ocr/providers/google_document_ai.py:211).

### A29 — Confiança e revisão manual não governam uniformemente o pipeline

**Prioridade:** médio.  
**Evidência:** código e reprodução isolada; componente ainda separado do workflow principal.

**Problema:** na reprodução, `finalize_review(0.1, "texto")` retornou modo de recomposição sem sinalizar revisão manual. O pipeline utiliza parte dos dados de confiança, mas não integra de forma uniforme sinais de tokens, revisão e decisão de continuar. Mesmo caminhos classificados como manuais podem chegar à chamada do resolvedor.

Também não há integração completa do verificador/árbitro nesse caminho apenas porque esses módulos existem no repositório.

**Impacto:** uma classificação de confiança pode não ter o efeito operacional esperado, produzindo resposta apesar de uma condição que deveria interromper ou encaminhar a revisão.

**Simplificação proposta:** uma decisão explícita por questão: continuar, repetir uma etapa específica ou encaminhar para revisão. Essa decisão deve controlar a execução, não apenas compor metadados.

**Teste recomendado:** OCR de baixa confiança, texto ambíguo e revisão manual; verificar quais provedores são realmente chamados em cada caso.

**Referências:** [src/pages_to_audio/ai/confidence.py:63](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/ai/confidence.py:63), [src/pages_to_audio/ai/question_pipeline.py:33](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/ai/question_pipeline.py:33).

### A30 — Pré-processamento e qualidade podem ocultar ausência de processamento

**Prioridade:** médio.  
**Evidência:** código; defeitos latentes/condicionais.

**Problemas encontrados:**

- O caminho de correção de perspectiva calcula informações, mas devolve a imagem original.
- Exceções amplas podem resultar em imagem original sem distinguir “não precisou corrigir” de “a correção falhou”.
- A saída pode ser marcada como sucesso mesmo sem a transformação anunciada.
- Nomes fixos de artefatos podem colidir quando várias entradas usam o mesmo diretório.
- O cálculo de qualidade pode substituir falhas por valores neutros sem sinalizar degradação.

**Impacto:** métricas e artefatos podem transmitir confiança indevida, e uma falha pode permanecer escondida até o OCR. Colisões dependem do uso compartilhado do diretório.

**Simplificação proposta:** executar somente transformações necessárias, registrar se houve aplicação, ausência de necessidade ou erro, e identificar saídas por entrada/execução.

**Teste recomendado:** documento inclinado conhecido, falha de biblioteca, duas imagens no mesmo diretório e imagem que não precisa de correção.

**Referências:** [src/pages_to_audio/image/preprocess.py:100](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/image/preprocess.py:100), [src/pages_to_audio/image/preprocess.py:192](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/image/preprocess.py:192), [src/pages_to_audio/image/quality.py](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/image/quality.py).

### A31 — Timeout de áudio não garante encerramento do subprocesso

**Prioridade:** médio.  
**Evidência:** código; depende de timeout.

**Problema:** ao exceder o tempo de espera de subprocessos de áudio, o código não garante encerramento explícito e espera pelo término do processo filho em todos os caminhos analisados.

**Impacto:** `ffmpeg` ou `ffprobe` podem continuar consumindo recursos depois que a operação já foi considerada falha.

**Simplificação proposta:** padronizar execução de subprocessos com timeout, encerramento e coleta do processo em um único utilitário.

**Teste recomendado:** subprocesso propositalmente lento; após o timeout, verificar que não restou processo filho e que os arquivos temporários podem ser removidos.

**Referências:** [src/pages_to_audio/audio/assemble.py:72](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/audio/assemble.py:72), [src/pages_to_audio/audio/validate.py:33](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/audio/validate.py:33).

### A32 — Regras de imutabilidade do storage dependem de nomes e verificações frágeis

**Prioridade:** médio.  
**Evidência:** código; risco condicionado à configuração e concorrência.

**Problemas encontrados:**

- A lista de buckets imutáveis utiliza nomes padrão, enquanto a resolução pode produzir um nome personalizado. A proteção pode deixar de se aplicar ao bucket configurado.
- Erros de consulta de existência são tratados genericamente como objeto ausente.
- Verificar existência antes de gravar não torna a gravação atômica sob concorrência.
- O alias de exportações de auditoria é direcionado ao armazenamento de áudio no mapeamento lido.

**Impacto:** comportamento diferente entre configuração padrão e personalizada, risco de sobrescrita concorrente e artefatos em localização inesperada.

**Simplificação proposta:** definir imutabilidade pela finalidade lógica do objeto, distinguir erro de consulta de inexistência e usar garantias condicionais do storage quando disponíveis. Manter mapeamento de buckets central e verificável.

**Teste recomendado:** bucket com nome personalizado, dois uploads concorrentes da mesma chave, erro de permissão no HEAD e exportação de auditoria.

**Referência:** [src/pages_to_audio/storage/r2_storage.py](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/storage/r2_storage.py).

### A33 — Estado da interface Android e spool exigem recuperação mais explícita

**Prioridade:** médio.  
**Evidência:** código; sem reprodução em aparelho físico.

**Problemas encontrados:**

- O identificador da sessão não é limpo no encerramento no caminho lido, enquanto seletores de modo dependem de ele estar ausente. Isso pode manter a troca de modo bloqueada.
- Contadores visuais avançam em caminhos anteriores à confirmação efetiva de persistência.
- Itens com arquivo ausente ou falha permanente podem continuar pendentes e ser reenfileirados.
- Não foi encontrada uma chamada efetiva de limpeza periódica para o método de expurgo de itens confirmados no fluxo rastreado.

**Impacto:** interface com estado antigo, diferença entre páginas e frames, pendências sem saída clara e crescimento de dados locais.

**Simplificação proposta:** separar sessão ativa de histórico, e distinguir estados de fila como pendente, enviando, confirmado e falha que requer ação. Definir uma política única de limpeza e recuperação.

**Teste recomendado:** finalizar e trocar de modo, reiniciar com upload pendente, remover o arquivo local de um item de teste e simular falha permanente do servidor.

**Referências:** [apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/ui/SessionViewModel.kt](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/ui/SessionViewModel.kt), [apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/ui/SessionScreen.kt](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/ui/SessionScreen.kt), [apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/sync/UploadWorker.kt](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/sync/UploadWorker.kt), [apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/spool/SpoolRepository.kt](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/gateway-android/app/src/main/java/com/pagestoaudio/gateway/spool/SpoolRepository.kt).

### A34 — Painel pode apresentar estado desatualizado e detalhes volumosos

**Prioridade:** médio, com efeito de desempenho dependente do volume.  
**Evidência:** código; sem benchmark de carga.

**Problema:** telas carregam dados inicialmente sem atualização automática uniforme. O detalhe de sessão reúne capturas, frames e até centenas de eventos, sem paginação individual desses conjuntos.

**Impacto:** progresso pode parecer parado até recarregar. Sessões grandes podem aumentar resposta, renderização e consumo de memória. Isso é uma hipótese de escala sustentada pelo formato da consulta, não uma latência medida.

**Simplificação proposta:** atualização limitada enquanto houver trabalho ativo e paginação dos conjuntos grandes. Carregar detalhes extensos apenas quando necessários.

**Teste recomendado:** sessão com grande quantidade de frames/eventos e transições em andamento, medindo tamanho da resposta e tempo de renderização.

**Referências:** [apps/api/routers/admin_sessions.py:153](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/api/routers/admin_sessions.py:153), [apps/admin/app/(admin)/admin/processos/[id]/page.tsx](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/admin/app/(admin)/admin/processos/[id]/page.tsx).

### A35 — Testes e CI não representam o caminho completo do produto

**Prioridade:** alto para confiabilidade de entrega.  
**Evidência:** execução das verificações e leitura da CI/testes.

**Problemas encontrados:**

- O job de integração está desativado com `if: false`.
- A estrutura de testes de integração contém essencialmente arquivos de inicialização, sem cobertura real do fluxo.
- Testes denominados ponta a ponta usam banco, provedores e spool simulados.
- O spool simulado em Python não testa a implementação Kotlin efetivamente instalada no Android.
- Comandos do painel se concentram na checagem TypeScript; isso não exercita interação real.
- A verificação mypy da CI cobre um conjunto limitado com opções permissivas; a execução ampliada falhou.

**Impacto:** regressões entre componentes podem coexistir com testes verdes. O número de testes, isoladamente, não indica cobertura das fronteiras que estão falhando.

**Simplificação proposta:** preservar testes unitários úteis e acrescentar poucos testes de integração que atravessem as fronteiras reais: cliente/API, banco/storage, fechamento/worker e resultado/consumidor.

**Teste recomendado:** executar em ambiente descartável o caminho completo mínimo, mais falhas de rede, repetição e reinício. O objetivo é verificar propriedades do produto, não reproduzir a implementação nos testes.

**Referências:** [.github/workflows/ci.yml:36](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/.github/workflows/ci.yml:36), [.github/workflows/ci.yml:45](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/.github/workflows/ci.yml:45), [tests/unit/api/test_android_only_e2e.py](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/tests/unit/api/test_android_only_e2e.py), [tests/unit/api/test_handwritten_e2e.py](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/tests/unit/api/test_handwritten_e2e.py), [apps/admin/package.json](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/apps/admin/package.json).

## 7. Complexidade que pode ser removida ou consolidada

As propostas desta seção são recomendações. Nenhuma foi implementada durante a auditoria.

### 7.1 Um único fluxo real antes de múltiplas estratégias

O projeto possui vários componentes especializados, aproximadamente vinte etapas no workflow principal e numerosas estratégias de recuperação. Parte das estratégias de recuperação ainda é composta por implementações vazias, e partes reais de IA não possuem chamadas no fluxo produtivo rastreado.

**Recomendação:** manter um fluxo mínimo executável e verificável. Acrescentar uma estratégia de recuperação apenas quando houver uma falha concreta que ela resolva e um teste que demonstre essa recuperação.

Referências: [src/pages_to_audio/reconstruction/rescue.py](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/reconstruction/rescue.py), [src/pages_to_audio/ai/question_pipeline.py](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/ai/question_pipeline.py), [src/pages_to_audio/workflows/process_exam.py](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/workflows/process_exam.py).

### 7.2 Uma política central para o ciclo de vida da sessão

As decisões de aceitar imagem, encerrar, bloquear, repetir, cancelar e publicar estão espalhadas. Há também caminhos distintos para fechamento e despacho.

**Recomendação:** uma camada pequena de operações de domínio compartilhadas, com transições e invariantes explícitas. Não é necessário substituir imediatamente toda a máquina de estados; primeiro eliminar decisões contraditórias.

Invariantes propostas:

1. Imagem nova só entra em estado que aceita captura.
2. Fechamento congela o conjunto de entrada.
3. Fechamento confirmado deixa trabalho durável para processamento.
4. Cancelamento impede publicação posterior normal.
5. Conclusão só ocorre com resultado persistido.
6. Repetição não duplica efeitos.

### 7.3 Uma fonte de verdade para quantidades e confirmações

**Recomendação:** o banco do servidor determina frames recebidos e resultado disponível. O spool Android determina o que ainda precisa ser enviado. A interface deriva seus indicadores desses estados, evitando contadores independentes atualizados antes de ACK.

Isso reduz a quantidade de correções manuais necessárias quando há repetição ou perda de conexão.

### 7.4 Um contrato compartilhado de comunicação

**Recomendação:** centralizar autenticação, DTOs, formatos de respostas e eventos. Gerar modelos ou validar exemplos reais nos dois lados.

Manter uma versão explícita do protocolo quando houver mudança incompatível. As mudanças no servidor devem ser coordenadas com a auditoria separada do firmware; este relatório não prescreve alterações internas no ESP32.

### 7.5 Um mecanismo de captura com políticas por modo

Captura comum e manuscrita compartilham polling, spool, upload, encerramento e recuperação. Implementações duplicadas ampliam a chance de corrigir um modo e deixar o outro inconsistente.

**Recomendação:** compartilhar o mecanismo e variar apenas os parâmetros necessários, como frames por unidade, quantidade esperada e regra de conclusão. O caminho manual que assume múltiplos frames deve respeitar o modo manuscrito quando sua expectativa for diferente.

### 7.6 Falhas explícitas em vez de sucesso artificial

**Recomendação:** substituir conversões silenciosas de erro por estados claros:

| Situação | Comportamento recomendado |
|---|---|
| Storage real não inicializa | Operação falha sem ACK de persistência. |
| Reindexação não implementada | Funcionalidade explicitamente indisponível. |
| Busca falha | Erro de busca distinguível de nenhum resultado. |
| Transformação de imagem falha | Resultado marcado como degradado/falho, sem anunciar transformação concluída. |
| Temporal indisponível | Pendência durável com repetição. |
| Revisão manual necessária | Pipeline para ou encaminha; não continua normalmente. |

### 7.7 Reutilização de recursos e operações realmente assíncronas

**Recomendação:** reutilizar clientes de rede e storage quando adequado, manter câmera vinculada, aplicar espera no polling e deslocar processamento bloqueante para o contexto correto.

O ganho deve ser medido depois. Não foi calculada porcentagem de redução de latência ou consumo.

### 7.8 Remoção de redundâncias após confirmar invariantes

Há verificações repetidas e restrições de unicidade aparentemente sobrepostas no caminho de frames, além de módulos demonstrativos e caminhos pouco conectados.

**Recomendação:** eliminar duplicação somente após identificar qual verificação protege cada propriedade. Não remover índices ou constraints apenas por aparência; confirmar plano de consulta, concorrência e compatibilidade das migrações.

Referências: [src/pages_to_audio/db/models/frame.py](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/db/models/frame.py), [src/pages_to_audio/capture/frame_upload.py](C:/Users/Lenovo/Downloads/pagestoaudio_servidor/src/pages_to_audio/capture/frame_upload.py).

## 8. Ordem recomendada de tratamento

| Ordem | Objetivo | Achados principais | Critério de conclusão |
|---|---|---|---|
| 1 | Estabelecer comunicação real Android/API | A02, A03 | Instalação configurada autentica, inicia sessão e interpreta respostas reais. |
| 2 | Garantir processamento real e consumidor ativo | A01, A05, A07 | Uma prova conhecida produz dados reais persistidos usando a imagem implantada. |
| 3 | Tornar fechamento e cancelamento recuperáveis | A04, A10, A11, A12, A18 | Falhas e reinícios não perdem o trabalho nem alteram entradas já fechadas. |
| 4 | Garantir persistência e repetição segura | A15, A16, A32 | Repetir upload após falha parcial recupera o mesmo objeto/frame. |
| 5 | Proteger conhecimento e remover sucesso fictício | A08, A09 | Rotas protegidas; dados duráveis ou função explicitamente indisponível. |
| 6 | Alinhar prontidão e observabilidade | A06, A17 | Estado anunciado corresponde à capacidade real e às mudanças de resultado. |
| 7 | Reduzir travamentos e trabalho repetido | A13, A14, A26, A31, A33, A34 | Captura e interface permanecem responsivas; frequência e recursos são medidos. |
| 8 | Corrigir configuração e componentes latentes | A19–A25, A27–A30 | Entradas, snapshots, busca e OCR têm comportamento coerente antes de integração. |
| 9 | Consolidar arquitetura e cobertura de integração | A35 e seção 7 | CI verifica fronteiras reais e o caminho mínimo completo. |

Algumas ações podem ser executadas em paralelo por uma equipe, mas a sequência acima representa dependências funcionais. Por exemplo, otimizar o resolvedor não corrige a ausência de um worker nem os cabeçalhos do cliente.

## 9. Plano de validação recomendado após futuras correções

Esta seção descreve testes ainda necessários. **Não afirma que tenham sido executados nesta auditoria.**

| Cenário | O que deve ser demonstrado |
|---|---|
| Instalação Android limpa | Provisionamento de identidade/credencial e autenticação efetiva. |
| Captura normal completa | Todos os frames confirmados antes do fechamento. |
| Captura manuscrita | Quantidade e frames por unidade coerentes com a configuração. |
| Último upload lento | A sessão não anuncia conclusão prematura. |
| Rede cai durante upload | Spool preserva trabalho e repetição não duplica efeitos. |
| Banco falha após escrita no storage | Reenvio recupera vínculo sem rejeição indevida. |
| Temporal indisponível no fechamento | Pendência permanece e inicia após recuperação. |
| Worker reinicia | Trabalho pendente continua sem duplicar publicação. |
| Upload novo após LOCKED | Rejeição ou política explícita; conjunto fechado não muda silenciosamente. |
| Upload repetido após LOCKED | Retorna confirmação anterior quando legítimo e idempotente. |
| Cancelamento concorrente | Nenhuma publicação normal posterior ao cancelamento. |
| Primeiro polling RGB | Cliente observa a transição de NOT_STARTED para PROCESSING. |
| Resultado RGB real | DTOs Android interpretam resposta; eventos são aceitos pelo servidor. |
| Storage inválido | Erro claro, sem fallback silencioso que confirme persistência. |
| Conhecimento sem login | Rejeição de leitura/mutação conforme autorização definida. |
| Reinício do serviço de conhecimento | Documentos persistem ou a função está explicitamente desabilitada. |
| Alteração de configuração durante sessão | Snapshot mantém os parâmetros esperados. |
| OCR de baixa confiança | Decisão de revisão controla a execução. |
| Busca vetorial com dado conhecido | Consulta executa e retorna resultado esperado. |
| Busca textual com pontuação | Não aborta silenciosamente a recuperação. |
| Timeout de áudio | Nenhum subprocesso órfão. |
| Dependência obrigatória indisponível | Readiness e diagnóstico refletem a falha. |
| Sessão volumosa no painel | Resposta e renderização permanecem dentro de metas medidas. |
| Execução de ponta a ponta | Entrada conhecida produz resultado real, validado e entregue ao consumidor. |

## 10. Limites, incertezas e pendências da auditoria

1. **Firmware fora do escopo:** nenhuma conclusão aqui substitui a análise do código ESP32-S3 na outra tarefa.
2. **Sem hardware real:** não houve validação de câmera, foco, consumo de bateria, conexão física ou LEDs em dispositivo.
3. **Sem prova completa real:** não foi executada uma prova com Android físico, OCR pago, IA e entrega final ao firmware.
4. **Sem alteração de produção:** nenhuma mutação destrutiva foi utilizada para confirmar vulnerabilidades ou falhas.
5. **Telas autenticadas:** foram analisadas pelo código; o navegador confirmou login e redirecionamento, sem sessão administrativa autenticada.
6. **Ambiente pontual:** observações de serviços e dependências correspondem ao momento consultado.
7. **Banco:** timeout observado, mas causa raiz não estabelecida. TCP funcionando posteriormente impede afirmar que era apenas indisponibilidade de rede.
8. **Python de testes diferente da imagem:** os testes usaram ambiente preexistente Python 3.14, não uma reconstrução exata de produção.
9. **Sem teste Android completo:** a checagem TypeScript não valida Kotlin; não foi reportado build ou execução integral de testes Android nesta auditoria.
10. **Sem benchmark:** não há número medido de ganho potencial de desempenho. Os mecanismos de bloqueio e repetição foram identificados no código.
11. **Defeitos latentes:** componentes não conectados não são atribuídos como causa comprovada de incidentes atuais.
12. **Sem certificação de ausência de bugs:** a cobertura é ampla, mas não prova que todos os caminhos, condições de concorrência e dependências estejam livres de falhas.
13. **Correções pendentes:** todas as propostas deste documento permanecem recomendações. Apenas este relatório foi criado por solicitação do usuário.

## 11. Registro de comandos e reproduções relevantes

Os comandos abaixo documentam como parte das verificações foi executada. Não são um script único a ser rodado automaticamente. Caminhos de runtime dependem do ambiente local.

### 11.1 Testes unitários Python

Execução no WSL, iniciada fora da raiz para isolamento da configuração:

```sh
cd /tmp
PYTHONPATH=/mnt/c/Users/Lenovo/Downloads/pagestoaudio_servidor APP_ENV=test /home/deploy/pages_to_audio_server_venv/bin/python -B -m pytest -q -p no:cacheprovider -c /mnt/c/Users/Lenovo/Downloads/pagestoaudio_servidor/pyproject.toml /mnt/c/Users/Lenovo/Downloads/pagestoaudio_servidor/tests/unit --tb=short
```

Resultado observado: **399 passed**, em aproximadamente **33,43 s**.

As chamadas de shell da sessão foram encaminhadas por `rtk`, conforme instrução local.

### 11.2 TypeScript sem emissão de arquivos

```powershell
rtk proxy node apps/admin/node_modules/typescript/bin/tsc --project apps/admin/tsconfig.json --noEmit --incremental false
```

Resultado observado: código de saída zero.

### 11.3 Análise estática Python

Escopo de Ruff: `src apps/api tests`, sem cache. Resultado: 30 ocorrências, todas em testes.

Escopo ampliado de mypy: `src apps/api`, com cache direcionado para `/tmp/pages-audit-mypy` e sem execução incremental. Resultado: falha. Não foi registrado total definitivo de erros.

### 11.4 Reproduções isoladas resumidas

| Entrada/condição | Resultado observado |
|---|---|
| Hello com cabeçalhos equivalentes ao Android padrão | HTTP 422 por falta de Authorization e X-Gateway-Id. |
| GET de documentos sem autenticação | HTTP 200. |
| SessionStartRequest com páginas negativas, zero questões e proporção 2 | Modelo aceitou. |
| HandwrittenSessionStartRequest sem parâmetros | expected_words igual a 10. |
| Upload em sessão LOCKED, índice negativo e JPEG inválido com assinatura inicial | Caminho isolado aceitou. |
| NOT_STARTED cursor 1 seguido de PROCESSING cursor 1 | Consulta com cursor anterior não recebeu mudança. |
| R2 fallback: gravar em instância A, consultar em B | A encontrou; B não encontrou. |
| Compilar SQL com :embedding::vector no dialeto asyncpg | Trecho permaneceu literal; nenhum parâmetro vinculado naquele fragmento. |
| finalize_review com confiança 0,1 e texto | Recomposição sem revisão manual. |
| Verificar herança de WorkflowAlreadyStartedError em relação a RPCError | Falso. |
| Starter com configuração do cliente sem task_queue | Seleção da fila padrão fixa. |

Essas reproduções não persistiram registros de teste no banco real nem gravaram imagens de teste no armazenamento de produção.

## 12. Conclusão técnica

O sistema possui componentes e testes úteis, mas a cadeia operacional ainda apresenta interrupções importantes entre captura, autenticação, persistência, processamento e entrega.

A redução de complexidade com maior retorno é:

- Um contrato único entre cliente e servidor.
- Um fluxo real de processamento.
- Uma regra central de ciclo de vida da sessão.
- Uma fonte persistida para confirmações e quantidades.
- Recuperação explícita de falhas parciais.
- Eliminação de sucessos simulados no caminho normal.
- Testes de integração focados nas fronteiras que hoje divergem.

Com essas bases, a otimização de câmera, polling e execução assíncrona passa a melhorar um fluxo confiável e mensurável.

## 13. Consolidação com a auditoria do firmware — 09/09/2026

Esta seção foi acrescentada após a comparação das duas auditorias e a conferência dos pontos de integração. Não altera a natureza dos testes históricos acima: reproduções isoladas continuam isoladas, e nenhuma missão física completa é declarada realizada por esta consolidação.

Documentos normativos para implementação:

- [Contrato consolidado de integração, revisão 1](contracts/INTEGRACAO_CONSOLIDADA_2026-09-09.md).
- [Plano completo de servidor, Android e deploy](PLANO_IMPLEMENTACAO_SERVIDOR_2026-09-09.md).
- [Auditoria do firmware](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/docs/AUDITORIA_COMPLETA_FIRMWARE_2026-09-09.md).
- [Plano de firmware e instalação](C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1/docs/PLANO_IMPLEMENTACAO_FIRMWARE_2026-09-09.md).

### 13.1 Divergências resolvidas e recomendações substituídas

Em caso de divergência com uma recomendação anterior deste relatório, prevalece a decisão desta tabela e o contrato vinculado. Os achados não são considerados corrigidos pela atualização documental.

| Assunto | Consolidação obrigatória |
| --- | --- |
| Caminho ESP para servidor | Implementar ponte Android real; não ligar ESP diretamente ao cloud nem tratar stub como integração pronta. |
| ACK de upload | Distinguir posse durável Android de confirmação durável cloud. Contadores e fechamento usam o nível correto. |
| Identidade e retry | Sessão/capture_id/índice identificam frame. Mesmo hash confirma; hash diferente conflita. Firmware preserva bytes antes da primeira aceitação. |
| Fechamento | Parar produtor, aguardar operação, drenar, conciliar frames cloud e fechar com outbox transacional. Timeout não autoriza perda de pendências. |
| Cursores | GET não consome comando; ACK vem após efeito durável. Versão RGB inicial virtual é zero. |
| RGB parcial | Exigir 100% e ordem contígua A–E. Não compactar respostas nem aplicar mínimo de áudio ao RGB. |
| RGB defaults | Publicar 12%/150/2850 explicitamente para novas sessões low-power após validação; preservar versões antigas 3000/5000 e respectivos hashes. |
| IDs | Aplicar limites embarcados a sessões/dispositivos ESP, sem truncar nem reduzir globalmente IDs antigos do banco. |
| Cancelamento | Cerca server/workflow e bloqueio de entrega; não prometer parar instantaneamente reprodução já iniciada offline. |
| Segurança local | TLS com confiança provisionada; UDP só localiza. Credencial ESP local distinta da credencial gateway cloud. |
| Estado do dispositivo | HELLO/reconnect não reinicia domínio nem altera pausa. READY de hardware não equivale a sessão em captura. |
| Auto-start/RST | Escolha física ainda pendente; não usar ESP_RST_EXT como solução presumida no ESP32-S3 examinado. |
| Deploy | Push/publicação de imagem não equivalem a deploy. Verificar SHA/digest, readiness real, worker e missão. |
| Aceite | Preservar testes existentes como evidência parcial; exigir placa, Android e serviços reais para conclusão operacional. |

### 13.2 Lacunas adicionais identificadas no cruzamento

**Ponte local ausente.** Esp32GatewayCaptureSource no Android é stub, e o caminho ESP não está operacional. Implementar UDP/local HTTPS, handlers, spool durável, tradução cloud e lifecycle Android. Ajustar apenas autenticação/DTOs não fecha a cadeia.

**Protocolos não são proxies transparentes.** Firmware envia JPEG bruto; API cloud recebe multipart. capture-complete local usa JSON, enquanto o endpoint cloud examinado utiliza parâmetros de query. Start/resume também tem campos e semânticas diferentes. A tradução pertence ao gateway, ou deve ser acompanhada de evolução aditiva explícita da API.

**Retomada exata.** Um last_session_id não pode resultar em seleção silenciosa de outra sessão ativa. Isso conflita com spool e identidade persistidos na ESP. Exigir resolução autoritativa para sessão encerrada ou incompatível.

**Deploy incompleto e saúde enganosa.** .github/workflows/deploy-pages-rgb.yml publica imagens, mas não tem implantação operacional. O Compose de produção examinado não inclui worker/Temporal. Scripts consultam portas que não correspondem ao caminho publicado e podem ignorar falhas. Caddy publica em 127.0.0.1:8081 e pode responder 200 genérico quando Host não corresponde a ptr.rotadeataque.com.br. O aceite deve verificar /api/v1/health/ready pelo Host correto, dependências e consumo real da fila.

**Limite físico da confirmação.** Uma sequência RGB já iniciada offline pode terminar após cancelamento no servidor. Uma queda de energia pode repetir o último item emitido antes da gravação de progresso. Tratar observação física e progresso lógico separadamente; não prometer exatamente uma emissão física sob corte de energia.

### 13.3 Ordem coordenada

1. Fixar schemas e contrato compartilhado — H0.
2. Corrigir persistência, despacho real e ponte Android; corrigir estado, spool, rede e RGB do firmware — H1.
3. Instalar candidatos e executar missão física e recuperação — H2.
4. Publicar e implantar backend compatível, atualizar Android e instalar firmware final — H3.
5. Comprovar versão ativa, missão real, recuperação e standby — H4.

A implementação está detalhada nos dois planos. Esta atualização altera somente documentação; build final, flash, push e deploy são etapas dos executores posteriores.

