# Plano adicional — teste de câmera: fotos, vídeo e prévia online

Data: 09/09/2026. Revisão 1.
Execução: somente depois do aceite dos planos principais de servidor e firmware.
Estado: proposta para implementação posterior; nenhuma câmera foi ligada ou testada por este documento.
Este mesmo plano fica nos dois projetos; manter as cópias idênticas.

## 1. Objetivo e entregas

Permitir avaliar enquadramento, foco óptico, iluminação, nitidez, compressão e estabilidade da câmera real da ESP pelo navegador do PC ou celular.

| Modo | Entrega | Uso |
| --- | --- | --- |
| Foto | JPEG original salvo, galeria e download | Examinar detalhes e comparar qualidade depois |
| Vídeo curto | MP4 sem áudio produzido no servidor a partir de JPEGs reais temporizados | Examinar mudanças de enquadramento, exposição e movimento |
| Ao vivo | Última imagem real atualizada na página online, com idade e taxa efetiva | Ajustar posição e iluminação durante o teste |

A prévia inicial é de baixa taxa de quadros. Vídeo não significa 25/30 FPS nem codificação na ESP. A taxa disponível será medida na placa, telefone e rede usados. Não apresentar repetição de imagem antiga como câmera ao vivo.

O driver oficial suporta JPEG e exemplos de captura/transmissão. A documentação alerta para custo de memória/CPU e diferenças entre um ou vários framebuffers, especialmente com Wi-Fi. A implementação deve aproveitar JPEG já suportado, sem atualizar o driver ou ativar buffers extras apenas para este teste. [Espressif — esp32-camera](https://github.com/espressif/esp32-camera)

## 2. Pré-requisitos e limites do escopo

1. Concluir e aceitar os dois planos de 09/09/2026, incluindo missão física, recuperação, TLS, APK e deploy.
2. Ler a revisão atual de docs/contracts/INTEGRACAO_CONSOLIDADA_2026-09-09.md e o registro real das implementações. O código já pode ter evoluído; não aplicar patches contra o retrato original da auditoria.
3. Reutilizar câmera, transporte autenticado, gateway, autenticação administrativa, banco, storage e execução de tarefas existentes.
4. Criar um módulo opcional de diagnóstico, desligado por padrão, com apenas os pontos mínimos de integração no código principal.
5. Não alterar contratos de captura, IDs de missão, spool principal, contagem de frames, OCR, solver, RGB ou áudio para acomodar diagnóstico.
6. Não trocar firmware por exemplo CameraWebServer, mudar pinagem, redefinir partições ou apagar NVS.
7. Não adicionar WebRTC, RTSP, HLS, broker, Redis ou servidor de streaming à primeira versão. JPEG por HTTPS e MP4 posterior atendem ao objetivo inicial.
8. Diagnóstico não roda ao mesmo tempo que missão, recuperação de spool, espera/reprodução RGB ou outra operação pendente que dependa da placa. Sessão pausada continua ocupada.
9. Não alterar parâmetros persistentes de qualidade da missão. Mudanças feitas na tela de teste são temporárias.
10. Usar câmera física da ESP como origem e identificá-la na tela. CameraX do telefone não pode ser substituto silencioso.
11. PC/celular remoto acessa o painel HTTPS; não precisa estar no hotspot. A ESP continua próxima do Android gateway, que precisa ter rede local e acesso ao servidor.
12. ESP em deep sleep não pode receber comando remoto. A tela deve informar “dispositivo indisponível; ative o modo de teste no gateway e acorde a placa pelo procedimento normal”. Não mudar a política de wake principal.

## 3. Arquitetura mínima

Fluxo de controle: navegador autenticado → API existente → Android conectado → cliente de diagnóstico da ESP.

Fluxo de imagem: câmera ESP → JPEG → gateway Android → API/storage existentes → navegador.

Fluxo de vídeo: JPEGs do clipe + tempos reais → tarefa limitada no worker existente → MP4 no storage → player/download.

O navegador nunca recebe segredo da ESP, token cloud do gateway ou acesso direto à rede local. Não abrir portas públicas na placa nem criar túnel adicional.

### 3.1 Uma cadeia de aquisição para três modos

- Foto: adquirir um frame e salvar.
- Ao vivo: repetir aquisição com prazo e taxa limitados; servir a imagem mais recente disponível.
- Vídeo: adquirir uma sequência finita de frames com timestamps e depois montar o clipe.
- Somente um modo de aquisição por vez. Para foto em resolução maior, parar a prévia, liberar recursos e iniciar foto; não trocar resolução no meio de um clipe.
- Assistir a um MP4 já pronto ou consultar galeria não ocupa a câmera.

### 3.2 Estado de diagnóstico separado

Estados mínimos: REQUESTED, ACTIVE, STOPPING, COMPLETED, FAILED e EXPIRED.

Registrar diagnostic_id, device_id, gateway_id, modo, perfil solicitado/efetivo, limite de duração, limite de bytes, origem, horário, motivo final e contadores. IDs novos seguem os limites embarcados já acordados.

Cada tentativa tem diagnostic_id próprio. Frames usam diagnostic_id + frame_index e SHA-256. Duplicata idêntica é idempotente; outra imagem no mesmo índice é conflito. Não utilizar capture_id/session_id de missão como namespace do teste.

Uma exclusão atômica por dispositivo impede dois inícios simultâneos, inclusive entre início de missão e diagnóstico. O controlador principal adquire/libera a câmera; o módulo de teste não decide ignorar o estado de missão.

Se uma missão for solicitada durante teste, cancelar o diagnóstico e aguardar liberação confirmada antes de iniciar, ou devolver “câmera em teste” de forma explícita. Escolher uma política consistente com o controlador existente; nunca executar ambos em paralelo.

### 3.3 Ativação e encerramento

1. Administrador habilita teste para dispositivo específico, com prazo.
2. Gateway confirma que está disponível; ESP confirma capacidade e ausência de pendências.
3. Somente a confirmação da ESP coloca diagnóstico em ACTIVE. HTTP de criação do pedido não equivale a câmera funcionando.
4. Na primeira versão, ativação local no Android mantém uma janela curta para a placa acordada receber o pedido, conforme a política já implantada.
5. Cada rodada tem duração máxima local. Desconexão do servidor/navegador não deixa câmera ligada indefinidamente.
6. Heartbeat de controle a cada 10 s enquanto a tela estiver visível; expirar autorização de captura após 30 s sem renovação, além do limite total do modo.
7. Parar no botão, expiração, perda prolongada da conexão, erro de recurso ou solicitação de atividade principal.
8. Após reboot, diagnóstico não retoma automaticamente. Recuperar só arquivos já aceitos e marcar a aquisição interrompida.
9. Encerrar tarefas/requisições, devolver buffers, restaurar perfil de câmera e política de energia anteriores e liberar exclusão.
10. ACK de STOP confirma liberação efetiva; até lá a tela mostra “encerrando” ou “dispositivo sem resposta”.

## 4. Perfis iniciais e orçamento

São limites iniciais propostos, não desempenho medido nem garantia do sensor.

| Parâmetro | Valor inicial |
| --- | --- |
| Foto | Uma imagem; SVGA como opção inicial; resoluções maiores somente entre as já validadas pelo plano principal |
| Prévia | VGA, alvo de até 2 quadros/s |
| Alternativa em rede lenta | QVGA ou taxa menor, sempre informando perfil efetivo |
| Duração da prévia | 60 s por rodada; nova rodada exige ação explícita |
| Clipe | 10 s, alvo de até 2 quadros/s, sem áudio |
| Limite de clipe | 30 s e 60 frames na primeira versão |
| Upload simultâneo na ESP | Um frame por vez |
| Prévia no gateway | Uma imagem em trânsito e no máximo uma mais recente aguardando; descartar intermediárias |
| Teto inicial de foto | Menor entre capacidade validada do firmware e 2 MiB |
| Teto por rodada de prévia | 20 MiB |
| Teto por clipe | 20 MiB de JPEGs de entrada, além de saída temporária limitada |
| Conversão de vídeo | Uma por vez no worker designado, timeout inicial de 60 s e limite de memória configurado |
| Histórico de teste | 7 dias e no máximo 100 MiB por dispositivo, com limpeza restrita a diagnóstico |
| Prévia transitória no storage | Manter apenas janela curta; limpar objetos antigos em até 10 min |

O teto de servidor não autoriza a ESP a alocar 2 MiB: prevalece seu limite validado, considerando PSRAM, heap contíguo e memória do transporte TLS.

Para dimensionamento, usar bytes reais por JPEG × taxa efetiva × duração. Exemplo aritmético: 100 KiB × 2 quadros/s ≈ 1,64 Mbit/s de payload em cada trecho de upload, sem overhead; 60 s ≈ 11,7 MiB. Esse cálculo não é benchmark.

Se a implementação principal desliga Wi-Fi para fotografar, medir primeiro o ciclo existente. Não prometer 2 FPS nesse caso. Reutilização de conexão e câmera/rádio ativos só pode ser habilitada dentro do diagnóstico após ensaio de memória/corrente e estabilidade. Se não ficar estável, manter taxa menor e reportá-la; não reestruturar a missão para acelerar o teste.

No primeiro lançamento, oferecer apenas resolução e presets de qualidade já validados. Não incluir autofocus fictício, controles sem suporte, sliders para todos os registradores ou ajuste automático de produção.

## 5. Transporte, persistência e visualização

### 5.1 API e contratos adicionais

Adicionar namespace próprio à API, aproveitando convenções atuais. Nomes propostos, a confirmar sem conflitar com rotas existentes:

- POST /api/v1/admin/camera-diagnostics: solicitar foto, clipe ou prévia.
- GET /api/v1/admin/camera-diagnostics/{id}: estado, limites e metadados.
- POST /api/v1/admin/camera-diagnostics/{id}/stop: parar idempotentemente.
- GET /api/v1/admin/camera-diagnostics/{id}/latest: metadados da última imagem, sequence/frame_index, idade e acesso autorizado.
- GET /api/v1/admin/camera-diagnostics/{id}/assets: fotos/clipes salvos.
- Namespace gateway equivalente para consulta/ACK de controle, upload JPEG e eventos.
- Namespace local equivalente sob /v1/device/diagnostics, usando o cliente e TLS já implantados.

Congelar schema, erros e exemplos antes de dividir implementação. Reutilizar envelope/entrega de controle existentes por extensão explícita, sem colocar comandos de teste no parser antigo como se fossem comandos de captura. Cliente sem capacidade camera_diagnostics_v1 devolve indisponibilidade controlada.

Uploads recebem JPEG bruto ou adaptação já disponível, sempre com identidade, índice, hash, dimensões e tempo monotônico de captura. Android acrescenta tempo de recebimento; servidor acrescenta tempo de chegada. Não calcular latência ponta a ponta subtraindo relógios não sincronizados.

### 5.2 Fotos e clipes são persistentes

1. Preservar JPEG original sem reencode, filtros ou orientação destrutiva.
2. Reutilizar mecanismo de fila durável do Android com tipo diagnóstico e quota própria, sem criar uma segunda implementação de spool.
3. Confirmar foto/frame de clipe somente após a durabilidade correspondente ao ACK local/cloud já definido.
4. Persistir em prefixo/bucket lógico de diagnóstico, por exemplo diagnostics/{device_id}/{diagnostic_id}/.
5. Arquivos de missão e ORIGINAL existentes não são tocados. Aplicar imutabilidade aos JPEGs salvos dentro da retenção de diagnóstico.
6. Android libera arquivo após confirmação cloud. Um clipe parcialmente recebido deve ser marcado incompleto; não completar com frames inventados.
7. Se necessário, permitir baixar os frames recebidos de clipe incompleto, com indicação explícita; não publicar MP4 como captura completa.

### 5.3 Prévia é transitória, sem fila de histórico

1. Frame de prévia não usa spool de missão nem escreve flash da ESP a cada atualização.
2. Definir ACK de prévia como aceitação transitória, em endpoint separado. Ele não carrega a garantia de foto salva e não serve para incrementar contagem de missão.
3. Em lentidão, descartar frames intermediários e manter o mais recente. Limitar pedidos em voo; não acumular minutos de vídeo atrasado.
4. Usar storage compartilhado existente com objetos temporários de índice único e um ponteiro de “último frame” em estado compartilhado no banco. Publicar o ponteiro somente após objeto existir.
5. Não usar variável global de um processo como fonte única: API com múltiplos workers ou restart precisa apresentar estado coerente.
6. O ponteiro só avança; chegada atrasada não substitui frame mais novo. Limpeza não remove o frame apontado enquanto válido.
7. Se storage indisponível, informar falha; não cair silenciosamente em memória como se o serviço continuasse durável.
8. O custo de PUT/GET desta opção é aceito apenas pelo limite curto de diagnóstico. Medir número de operações antes de ampliar duração/FPS; não adicionar infraestrutura de streaming preventivamente.

### 5.4 Navegador online

1. Criar página administrativa “Teste de câmera”, responsiva para PC e celular.
2. Exibir dispositivo, gateway online/offline, ocupado/livre e modo atual.
3. Oferecer “Tirar foto”, “Gravar 10 segundos”, “Ver ao vivo” e “Parar”, com duração e perfil efetivo visíveis.
4. Para a prévia, buscar metadados aproximadamente a cada 500 ms enquanto visível e ativa. Buscar imagem apenas quando o índice mudar; não iniciar nova consulta enquanto a anterior estiver pendente.
5. Servir imagem por rota autenticada ou URL assinada curta após autorização, sem tornar bucket público. Usar mesma origem quando possível e evitar segredos na URL.
6. Não retornar arquivo binário dentro de JSON/base64. Carregar JPEG como imagem e liberar URLs de objeto quando aplicável.
7. Exibir idade do último frame, taxa efetiva de captura/recepção e estado de conexão. Após 5 s sem novidade, mostrar “imagem desatualizada”; não manter indicador verde de ao vivo.
8. Em aba oculta/desmontada, parar polling e renovação de autorização; enviar STOP em melhor esforço. A segurança do encerramento depende do prazo local, não de unload do navegador.
9. Foto: miniatura, ampliação a 100%, ajuste à tela e download do original. Oferecer comparação simples de duas fotos com resolução, qualidade e tamanho.
10. Vídeo: player nativo com controles, playsinline e download, sem áudio. Mostrar duração e taxa reais; sem autoplay obrigatório.
11. MP4 reencodado serve para avaliar sequência temporal; qualidade fina de JPEG é avaliada nas fotos originais, não no MP4.
12. Não carregar lista inteira nem todos os originais ao abrir a galeria. Paginar e usar miniaturas derivadas com originais preservados.

## 6. Etapas de execução

### D00 — Conferir baseline e congelar extensão

Responsável: ambos os projetos; alterações iniciais apenas de documentação/schema.

1. Confirmar H4 dos dois planos principais e registrar versões/artefatos realmente implantados.
2. Ler instruções atuais e mudanças posteriores. Não reverter correções existentes.
3. Registrar teste normal antes da extensão: missão completa, recuperação, RGB e standby.
4. Localizar o proprietário atual da câmera, canal de controle gateway, fila Android, storage e worker. Reutilizar esses pontos.
5. Definir exclusão de câmera, capacidade camera_diagnostics_v1, endpoints, quotas e ACKs distintos.
6. Documentar prefixos de dados e limpeza. Definir feature flag desligada em servidor/Android/firmware.
7. Confirmar que a ESP pode ficar acordada durante a janela de diagnóstico sem mudar wake normal.

Aceite: contrato adicional fechado; nenhum identificador/comando de missão ganha significado diferente.

### D01 — Servidor: controle, upload e galeria de fotos

Responsável: projeto pagestoaudio_servidor.

1. Criar migração nova mínima para diagnóstico/estado/artefatos, reutilizando estruturas seguras quando apropriado.
2. Implementar início/consulta/STOP autenticados com vínculo usuário-dispositivo-gateway, expiração e exclusão concorrente.
3. Implementar ingestão de JPEG com limite antes de leitura integral, validação, hash e idempotência.
4. Usar armazenamento real no namespace diagnóstico e galeria paginada.
5. Tratar cliente sem capacidade, dispositivo offline e ocupado sem sucesso fictício.
6. Implementar quotas/retention com limpeza limitada a chaves de diagnóstico verificadas.
7. Disponibilizar página inicial somente a administradores e atrás da flag.

Aceite: upload real e autorizado fica disponível após reinício, sem alterar nenhum registro de missão.

### D02 — Android: encaminhamento de diagnóstico

Responsável: projeto pagestoaudio_servidor, aplicativo gateway.

1. Reutilizar serviço local TLS e cliente cloud; implementar somente novos handlers/adaptações.
2. Associar diagnóstico a dispositivo real; não acionar CameraX por fallback.
3. Reservar janela de disponibilidade e encaminhar controle conforme capacidade.
4. Para foto/clipe, usar fila durável existente com tipo/quota de diagnóstico.
5. Para prévia, usar buffer limitado e descarte de frames antigos, sem retry indefinido.
6. Encerrar por prazo, STOP e perda de autorização. Recuperar pendências duráveis sem reiniciar câmera após reboot.
7. Mostrar estado de teste no app e disponibilizar botão local de parada.

Aceite: transporte preserva hash/identidade e nenhuma falha gera crescimento ilimitado de fila.

### D03 — Firmware: foto isolada e restauração

Responsável: projeto Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1.

1. Criar módulo de diagnóstico pequeno, reutilizando camera_service, autenticação e cliente existentes.
2. Adicionar capacidade e entrada no controlador; garantir exclusão em relação a sessão ativa, pausada, spool e RGB.
3. Manter configurações do teste em memória, separadas do perfil principal.
4. Capturar um frame por chamada usando limites corrigidos de buffer/resolução.
5. Transmitir foto com identidade própria; liberar recursos somente conforme posse/durabilidade definida.
6. Restaurar perfil e energia ao sair, inclusive por timeout, erro e reset.
7. Não gravar configuração temporária em NVS, não usar IDs de missão e não alterar partições.

Aceite conjunto D01–D03: foto real da ESP aparece no navegador, original baixado tem hash idêntico e missão normal seguinte funciona.

### D04 — Prévia online de baixa taxa

Responsável: firmware + Android + servidor/painel.

1. Repetir a aquisição de um frame, envio e liberação, com no máximo uma operação por vez.
2. Medir tempo com política câmera/rádio atual. Ajustar taxa solicitada ao que for comprovado, sem mexer no funcionamento principal.
3. Implementar ponteiro compartilhado do último JPEG temporário e limpeza limitada.
4. Exibir imagem por polling controlado, estado stale e taxa efetiva.
5. Implementar heartbeat, prazo local e STOP em todos os trechos.
6. Testar VGA com alvo 2 FPS; se não alcançar, manter taxa real informada e avaliar QVGA. A aprovação exige utilidade real para enquadramento, não etiqueta “2 FPS”.
7. Buscar latência de exibição de até 3 s em rede saudável como objetivo inicial, não garantia. Se não atingir, documentar medidas por trecho e resolver dentro da solução simples antes de ampliar infraestrutura.

Aceite: imagem muda com cena real, não acumula atraso e termina automaticamente sem controle disponível.

### D05 — Vídeo curto sem codificador embarcado

Responsável principal: servidor/worker; aquisição usa D03/D04.

1. Criar modo finito de 10 s, com limite de 30 s/60 frames e quota de entrada.
2. Preservar timestamps monotônicos e índices; manter ordenação e detectar faltas.
3. Encaminhar frames pela fila durável de diagnóstico e aguardar conciliação cloud antes de finalizar clipe completo.
4. Agendar uma tarefa no mecanismo/worker existente, fora do request HTTP e sem chamar OCR/solver/áudio.
5. Montar MP4 H.264 com formato de pixels compatível com navegadores, dimensões válidas e faststart, usando FFmpeg disponível na imagem de produção.
6. Verificar que o encoder escolhido realmente existe na imagem. Não presumir libx264 só porque ffmpeg está instalado.
7. Preservar intervalos de captura via manifest de concatenação/durações ou timestamps equivalentes. Não reproduzir 20 frames coletados em 10 s como se fossem 30 FPS de captura.
8. Usar diretório temporário privado com tamanho limitado; validar nomes de arquivos e invocar processo com argumentos estruturados, sem comandos montados a partir de entrada do usuário.
9. Aplicar timeout e término/reap do processo; remover temporários em sucesso/falha e limpar sobras do próprio diagnóstico após restart.
10. Salvar MP4 no storage existente e expor player/download. Nenhum arquivo de câmera fica permanentemente no disco da VPS.
11. Preservar fotos do clipe até conversão confirmada, conforme quota/retention; conversão repetida deve ser idempotente.

O demuxer concat do FFmpeg aceita lista de arquivos e durações por arquivo; validar a duração resultante com ffprobe e reprodução real. [FFmpeg — formatos e concat](https://ffmpeg.org/ffmpeg-formats.html#concat-1)

Aceite: clipe de cena real toca no PC/celular com duração coerente, sem imagens fabricadas e sem processo órfão.

### D06 — Interface, qualidade e testes reais

Responsável: servidor/painel; validação conjunta com placa e telefone.

1. Testar fotos de página impressa com letras pequenas, objeto com textura e cena com iluminação desigual.
2. Comparar presets mantendo distância, enquadramento e luz; salvar metadados de resolução, qualidade, tamanho e versão.
3. Avaliar foco físico, reflexos, borrão, exposição e compressão visualmente. Não alterar lente ou atribuir foco automático ao sensor sem suporte confirmado.
4. Testar prévia movendo objeto real; comparar captura/recepção e observar atraso em vez de confiar só no contador.
5. Testar clipe com movimento e intervalo conhecidos; conferir timestamps, duração e reprodução.
6. Usar navegador real em PC e celular, incluindo tela estreita, zoom da foto e player. Inspecionar Console/Network; examinar screenshots da interface.
7. Testar modo ocupado, duas abas, dois pedidos concorrentes, perda de internet, fechamento de aba, tela apagada do Android, reboot da ESP e certificado inválido.
8. Confirmar que o último frame antigo é sinalizado como desatualizado, e que arquivo salvo não desaparece por falha transitória.
9. Medir heap/PSRAM, fila Android, CPU/memória do servidor, bytes, operações de storage, latência e corrente.
10. Executar missão principal completa imediatamente após cada modo e após um encerramento por falha.

Aceite: foto, vídeo e prévia funcionam em hardware real e todos os fluxos principais permanecem aprovados.

### D07 — Build, deploy, instalação e habilitação limitada

Responsável: cada executor na própria parte.

1. Revisar diff para manter mudanças concentradas em diagnóstico e hooks mínimos.
2. Executar testes afetados, builds reais de API/worker/painel/APK e firmware, conforme os planos principais.
3. Registrar commits, hashes de APK/BIN, digests de imagens e revisão deste plano/contrato adicional.
4. Fazer push e deploy pelo procedimento corrigido do projeto, com flag desativada; aplicar somente migração nova compatível.
5. Instalar APK e firmware na identidade física correta, preservando NVS, spool e dados.
6. Verificar readiness e versões efetivas. Habilitar diagnóstico somente no dispositivo de teste.
7. Executar os três modos remotamente pelo domínio HTTPS real, em PC e celular.
8. Reexecutar missão normal e standby; registrar comparação com D00.
9. Manter desligado por padrão para demais dispositivos. Abrir o painel não inicia câmera.

Aceite: recurso utilizável no ambiente real, com release identificada e sem regressão.

### D08 — Desativação e rollback

1. Desabilitar novas ativações pela flag; solicitar STOP e aguardar prazo local das ativações existentes.
2. Confirmar câmera liberada e retorno à política de energia principal.
3. Se necessário, restaurar imagens/APK/BIN anteriores pelo procedimento principal, sem apagar dados.
4. Não desfazer migração com perda de registros nem alterar objetos de missão.
5. Expurgar apenas dados temporários de diagnóstico conforme política; fotos/clipes salvos seguem retenção e indicação na interface.
6. Registrar causa, evidência e teste normal posterior.

## 7. Matriz final de aceite

| Cenário | Evidência obrigatória |
| --- | --- |
| Foto original | JPEG da ESP, hash idêntico, abertura e download após reinício |
| Vídeo | MP4 real, duração coerente, player no PC e celular |
| Ao vivo | Atualização da cena física e idade/FPS efetivos visíveis |
| Rede lenta | Frames intermediários descartados; fila permanece limitada |
| Aba fechada | Captura encerra por STOP ou prazo local |
| ESP dormindo | Interface indica indisponibilidade; nenhum wake remoto fictício |
| Missão ativa/pausada ou RGB pendente | Diagnóstico negado sem alterar sessão |
| Pedido de missão durante teste | Serialização/liberação confirmada, sem duas capturas concorrentes |
| Reset durante teste | Não reinicia aquisição; pendências salvas são conciliadas |
| Quota ou storage indisponível | Erro explícito e parada segura |
| Usuário/gateway indevido | Sem imagem, controle ou segredo exposto |
| Cancelamento de conversão | FFmpeg encerrado e temporários tratados |
| Após os três modos | Missão completa, retomada e standby normais aprovados |
| Flag desligada | Nenhuma aquisição, polling permanente ou consumo adicional de câmera |

## 8. Entrega ao concluir a implementação

Entregar instrução curta de uso da página, versões instaladas, fotos originais de referência, um clipe, evidência da prévia real, taxas/latências medidas, consumo/quota e resultado da regressão principal.

Registrar limites observados. Se a taxa disponível for baixa, informar o valor; não simular fluidez, duplicar frames sem transparência ou prometer webcam convencional.

## 9. Localização e coordenação

Projeto servidor/Android: C:/Users/Lenovo/Downloads/pagestoaudio_servidor.
Projeto firmware: C:/Users/Lenovo/Downloads/Pages_to_Audio_ESP32S3_CAM_N16R8_FW_V2_1.

Executar D00 em acordo documental; servidor faz D01/D02, firmware faz D03; ambos integram D04; servidor implementa D05; D06–D08 são aceites conjuntos. Não iniciar este plano apenas porque os planos anteriores foram escritos: sua implementação e validação precisam estar concluídas.

O contrato principal continua normativo para a missão. As exceções de volatilidade e descarte deste documento existem somente no namespace de prévia diagnóstica e nunca se aplicam a fotos de missão ou fotos/clipes declarados salvos.

