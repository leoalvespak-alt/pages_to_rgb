# Contrato consolidado de integração — 09/09/2026

Identificador: P2A-INTEGRACAO-2026-09-09, revisão 1.
Estado: decisões para implementação; não descreve funcionalidades já entregues.
Escopo: ESP32-S3 → Android gateway → API/worker/storage → Android → ESP32-S3.
Cópias: este arquivo deve ser idêntico nos dois projetos. Mudanças posteriores exigem atualizar as duas cópias e registrar a revisão.

## 1. Precedência e responsabilidade

Este contrato substitui recomendações divergentes das auditorias exclusivamente nos assuntos abaixo. Os achados históricos continuam válidos até correção e comprovação. RGB_RESULT_V1 conserva seu formato binário e seus vetores antigos. Documentos anteriores não autorizam alterar silenciosamente um payload publicado.

O projeto do servidor contém API, worker, painel, infraestrutura e aplicativo Android. A implementação da ponte local pertence a esse projeto. O firmware implementa somente o cliente embarcado. Não mover OCR, RAG ou resolução para a ESP. Não substituir Temporal ou criar outro broker para contornar os defeitos de despacho.

## 2. Decisões consolidadas

| Tema | Decisão | Motivo e consequência |
| --- | --- | --- |
| Topologia | ESP conecta ao Android local; Android conecta à API por HTTPS. | O stub Esp32GatewayCaptureSource não constitui ponte funcional. Implementar serviço real. |
| Transporte local | Perfil de produção autenticado com TLS e confiança provisionada; discovery UDP é apenas localização. | Nonce UDP não autentica servidor. Não enviar Bearer antes de validar identidade TLS. HTTP legado somente em bancada explicitamente isolada, sem aceite de produção. |
| Autenticação | Credencial por dispositivo no trecho local; credencial de gateway e X-Gateway-Id no trecho cloud. | Nunca colocar token cloud no firmware. Vincular dispositivo, gateway e sessão no servidor. |
| Identidade | Para ESP, session_id, capture_id e device_id: 1–63 caracteres ASCII alfanuméricos, underscore ou hífen; sequence_id: 1–64. | Rejeitar excesso; nunca truncar. Não reduzir globalmente colunas existentes de 128 caracteres nem reutilizar IDs legados incompatíveis. |
| Frame | Chave lógica: sessão + capture_id + frame_index. Hash descreve conteúdo, não participa da identidade lógica. | Reenvio com mesmo hash é idempotente; outro hash na mesma chave é conflito 409. ORIGINAL é imutável. |
| Durabilidade | ACK local significa posse durável pelo Android; ACK cloud significa objeto durável e vínculo no banco confirmado. | Separar recebido localmente, enviado ao servidor e processado. |
| Captura | Persistir bytes antes da primeira aceitação remota que obrigue retomada. | Não recapturar outra imagem sob uma identidade já aceita. Falta de espaço deve impedir início do comando, sem truncar quantidade. |
| Cursores | Cursor de comando e versão RGB são domínios independentes. | GET não consome comandos. Versão RGB virtual inicial = 0; primeira transição real > 0. |
| RGB | Resultado completo, contíguo, A–E, na ordem original. | Não compactar respostas parciais; manter 100% para RGB. Gate de áudio continua independente. |
| Tempos RGB | Novas sessões no perfil low-power recebem explicitamente brilho 12%, ligado 150 ms e intervalo 2850 ms. | Payloads antigos 3000/5000 ms permanecem imutáveis. Aceitação visual e elétrica real antes da promoção do novo perfil. |
| Resultado | Espera inicial 750 s e nova consulta após 90 s, como configuração única do perfil, respeitando os campos negociados. | Não duplicar defaults contraditórios entre firmware, Android e servidor. |
| Cancelamento | Cercar publicação, entrega e workflow; sequência já em execução offline pode terminar. | O painel informa a limitação. Não ligar permanentemente Wi-Fi para prometer interrupção instantânea. |
| Estado | Controle da sessão separado de fase transitória de rede/câmera. | Reconnect e HELLO não despausam nem reabrem sessão, e não rebaixam processamento. |
| Início físico | Decisão pendente entre início pelo Android, automático na alimentação ou botão dedicado. | ESP_RST_EXT não resolve a distinção POWERON/RST na versão examinada do ESP32-S3. Nenhuma opção está autorizada implicitamente. |
| Aceite | Missão com ESP, Android, API, banco, storage e providers reais. | Testes unitários e fixtures complementam; mock não comprova integração operacional. |

## 3. Transporte e adaptação de mensagens

1. Preservar discovery na porta UDP 8786 e serviço local na porta 8787 como referências existentes, expondo esquema e capacidades no protocolo. Negociar versão de integração separada de schema_version do RGB.
2. Provisionar confiança local fora do discovery: CA/certificado e identidade estável do gateway, com segredo por dispositivo protegido no Android. Escolher mecanismo suportado pelo ESP-IDF instalado que valide cadeia e identidade mesmo com IP variável do hotspot. Verificação de hostname/certificado não pode ser desativada. Documentar rotação e inicialização de relógio compatível com a validação de certificados. Sem fallback inseguro automático.
3. Android deve executar serviço local durante uso real, inclusive com tela apagada, conforme permissões e restrições do Android. Implementar limites de corpo, timeouts e encerramento limpo.
4. Local POST /v1/device/frame recebe JPEG bruto. Gateway transforma para multipart no endpoint cloud /api/v1/gateway/session/{session_id}/frame, sem alterar bytes.
5. Enviar X-Frame-Index, X-Capture-Id e X-SHA256; preencher metadados opcionais de recebimento, resolução e orientação quando conhecidos, sem inventá-los.
6. Local capture-complete recebe JSON com device_id, session_id, capture_id e frames. O endpoint cloud existente usa parâmetros de query. Implementar adaptação explícita ou evolução aditiva documentada do endpoint cloud; não repassar JSON esperando compatibilidade automática.
7. Local start utiliza resume_hint booleano e last_session_id; cloud utiliza hint de sessão e identidade/capture_source. Gateway deve traduzir campos e devolver resumed e cursor de resultado autoritativo, persistidos ou retornados pela API.
8. Hint com sessão exata não pode cair silenciosamente em outra sessão ativa. Sessão encerrada deve retornar resolução explícita, permitindo preservar/conciliar pendências sem loop infinito.
9. DTOs devem distinguir comando, status da sessão e resultado. Definir campos obrigatórios, enums, arrays/string de respostas e eventos em schema verificável. Um campo desconhecido opcional pode ser ignorado; comando desconhecido ou campo obrigatório inválido não pode consumir cursor.
10. Limitar cursores JSON a inteiros entre 0 e 2^53−1 para representação exata no parser atual. IDs inseridos em URL/JSON devem ser validados e serializados corretamente.

## 4. Propriedade dos dados e ACK

1. Firmware cria uma identidade de comando, captura dentro do orçamento de RAM/flash e grava lote recuperável antes do primeiro upload.
2. Android valida tamanho, JPEG, identidade e hash; grava arquivo temporário, conclui escrita durável suportada, publica arquivo atomicamente e confirma registro persistente da fila. Na recuperação, reconciliar arquivo/Room antes de responder como aceito.
3. Respostas locais 200/201/208 somente contam como ACK durável quando o corpo confirma identidade e hash. 202 ou um 2xx arbitrário não significa transferência concluída. Duplicata idêntica retorna o mesmo resultado lógico.
4. Android mantém JPEG até ACK cloud confirmado. Não remover por reinício do app, erro transitório ou passagem para outra tela.
5. API só confirma após armazenamento real e transação do vínculo do frame. Se objeto existir e commit anterior tiver falhado, conciliar o mesmo hash em vez de sobrescrever ou bloquear a recuperação.
6. Falha de storage configurado em produção é indisponibilidade explícita; nunca trocar por armazenamento em memória.
7. Contagem de recebidos vem de frames únicos confirmados no banco. Declaração do dispositivo/gateway não substitui essa contagem.
8. Firmware pode liberar sua cópia após todos os ACKs locais duráveis e captura local concluída de forma persistente. Android assume a responsabilidade de drenagem cloud. A política de retenção deve registrar essa transferência.
9. Erros permanentes, conflitos, autenticação, payload inválido, falta de recursos e indisponibilidade são categorias distintas. Nenhuma delas justifica apagar automaticamente fotos válidas.

## 5. Fechamento, comandos e despacho

1. Cessar emissão de novos comandos de captura; aguardar comando em andamento em ponto seguro.
2. Persistir intenção de fechamento no Android; drenar a fila local para cloud e confirmar todas as identidades esperadas.
3. Efetivar capture-complete cloud somente com recebidos duráveis conciliados. Timeout com pendências mantém fechamento pendente.
4. Fechar a sessão e registrar intenção de processamento na mesma transação, usando outbox.
5. Dispatcher envia workflow com ID determinístico; retry de envio e AlreadyStarted são idempotentes. Falha de Temporal deixa evento pendente e observável.
6. Entregar STOP/estado fechado à ESP por canal durável; registrar espera RGB local de modo recuperável.
7. Comandos persistem até ACK de efeito durável. Repetir GET não altera estado. Usar long-poll limitado: cliente 20 s, teto servidor 25 s e timeout HTTP superior ao tempo efetivo de espera.
8. PAUSE impede novas capturas; RESUME/STOP não podem ficar presos atrás de um comando de captura impedido pela pausa. Definir seleção de controle e ACK sem descartar silenciosamente comandos.
9. Quantidade menor por comando depende de capacidade anunciada e de novos comandos; nunca reduzir silenciosamente um comando já emitido. O total da missão permanece o solicitado.
10. Cancelamento marca cerca durável consultada por atividades/publicação e solicita cancelamento Temporal. Evento atrasado não ressuscita sessão cancelada.

## 6. Resultado RGB e recuperação

1. Preservar schema_version 1 e item binário little-endian <BBBBBII, 13 bytes, com a ordem de campos do contrato RGB_RESULT_V1.
2. Preservar vetor antigo ABCDE e hash 6f2f655b4ea2ee02ee009a938cc95515f6ff38309b3b2ddcb0594057a5151f17; criar novo vetor separado para novos tempos, sem editar o anterior.
3. Antes de READY, validar identidade, versão, contagem, limites, soma de tamanhos, ordenação, símbolos e hash de todo payload. Downloads parciais nunca são reproduzíveis.
4. Atualizar cursor do firmware somente depois da transição durável correspondente. Repetição do mesmo resultado é inócua.
5. Na inicialização, validar sequência persistida antes de reproduzir. Diário de progresso danificado deve ser recuperado até último registro válido e reparado antes de novas gravações.
6. Manter next_index lógico monotônico no servidor. Telemetria de retomada pode observar repetição do último item físico após corte de energia; registrar a observação sem retroceder o progresso lógico.
7. COMPLETED local deve ser durável antes de enviar evento; perda do ACK repete somente o evento. API/gateway aceitam retransmissão idempotente e não exigem entrega perfeita de todos os eventos anteriores para conciliar uma conclusão válida.
8. Cancelamento antes da entrega impede nova publicação; após início offline não há garantia de interrupção imediata. Não substituir revisão ativa durante reprodução.
9. Resultado original e parâmetros publicados são imutáveis. Correção exige revisão explícita, apenas quando compatível com o estado da sessão e do dispositivo.

## 7. Marcos entre executores

| Marco | Servidor/Android entrega | Firmware entrega | Condição para avançar |
| --- | --- | --- | --- |
| H0 | Schemas e exemplos reais/aditivos, auth e IDs definidos | Parser e capacidades planejados; decisão física registrada quando disponível | Duas cópias deste contrato na mesma revisão |
| H1 | API, storage, worker e ponte Android funcionais em ambiente identificado | BIN candidato compilado e recovery implementado | Cada lado registra versão e endpoints; unidade isolada não substitui missão |
| H2 | APK instalado no telefone e serviços reais disponíveis | Placa candidata instalada em bancada | Captura → upload → workflow → RGB completo com correlação dos IDs |
| H3 | Imagens publicadas por SHA/digest e deploy verificado | Artefato final idêntico ao validado, instalado na placa correta | Compatibilidade aditiva: servidor primeiro, Android depois, firmware por último |
| H4 | Evidências de processamento, durabilidade e rollback | Evidências de retomada, reprodução e corrente | Aceite físico e operacional sem pendências críticas |

Trabalhos internos independentes podem prosseguir antes de H1/H2. Um executor que aguarda o outro registra exatamente o marco e o artefato necessário, sem substituir o outro lado por mock para declarar conclusão.

