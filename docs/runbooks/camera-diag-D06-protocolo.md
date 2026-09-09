# D06 — protocolo de qualidade e testes reais (foto, prévia, clipe)

Referência: PLANO_ADICIONAL_TESTE_CAMERA_2026-09-09 §D06 + matriz de aceite §7.
Pré-requisito: D07 executado no dispositivo de teste com flag ligada só nele.

## 1. Fotos — página impressa, textura, luz desigual

1. Fixar distância/enquadramento/luz; fotografar página impressa com letras
   pequenas, objeto com textura e cena com iluminação desigual.
2. Comparar presets (VGA/SVGA/XGA…) mantendo cena; salvar metadados
   (resolução, qualidade, tamanho, versão de firmware/API/APK).
3. Avaliar foco físico, reflexos, borrão, exposição e compressão no JPEG
   original (hash idêntico ao baixado). MP4 não serve para nitidez fina.
4. Não alterar lente nem atribuir autofocus sem suporte confirmado.

## 2. Prévia — movimento real, atraso observado

1. Mover objeto real diante da lente; comparar captura × recepção.
2. Observar atraso real em vez de confiar só no contador; registrar taxa
   efetiva de captura/recepção e idade do último frame.
3. Forçar rede lenta: confirmar descarte de intermediárias e fila limitada
   (gateway: 1 em voo + 1 aguardando). Não acumular minutos atrasados.
4. Fechar a aba: captura encerra por STOP ou prazo local. Reabrir mostra
   "imagem desatualizada" após 5 s, nunca verde falso.

## 3. Clipe — movimento e intervalo conhecidos

1. Gravar 10 s com movimento e intervalo conhecidos; conferir timestamps
   monotônicos, duração e reprodução no PC e no celular.
2. Clipe parcial: marcado incompleto; frames recebidos baixáveis com
   indicação; nenhum MP4 publicado como captura completa.
3. Cancelar conversão: FFmpeg encerrado, temporários tratados, sem órfãos.

## 4. Matriz de aceite (evidência obrigatória)

| Cenário | Evidência |
| --- | --- |
| Foto original | JPEG da ESP, hash idêntico, abre e baixa após reinício |
| Vídeo | MP4 real, duração coerente, player no PC e celular |
| Ao vivo | Cena física muda; idade/FPS efetivos visíveis |
| Rede lenta | Intermediárias descartadas; fila limitada |
| Aba fechada | Captura encerra por STOP ou prazo local |
| ESP dormindo | "dispositivo indisponível…", sem wake remoto fictício |
| Missão ativa/pausada ou RGB pendente | Diagnóstico negado sem alterar sessão |
| Missão pedida durante teste | Serialização/liberação confirmada, sem concorrência |
| Reset durante teste | Sem retomada automática; salvos conciliados |
| Quota/storage indisponível | Erro explícito e parada segura |
| Usuário/gateway indevido | Sem imagem, controle ou segredo exposto |
| Cancelamento de conversão | FFmpeg encerrado e temporários tratados |
| Após os três modos | Missão completa, retomada e standby normais |
| Flag desligada | Sem aquisição, polling ou consumo de câmera |

## 5. Medições (registrar valores reais, sem prometer)

Heap/PSRAM (livre + maior bloco por lote), fila Android, CPU/memória do
servidor, bytes e operações de storage por rodada, latência por trecho
(captura → gateway → servidor → navegador), corrente por fase. Se a taxa for
baixa, informar o valor; sem simular fluidez, duplicar frames sem
transparência ou prometer webcam convencional.

## 6. Regressão principal após cada modo e após cada falha

Missão completa + recuperação + RGB + standby imediatamente após foto,
prévia, clipe e após cada encerramento por falha. Comparar com o baseline
D00. Qualquer regressão bloqueia a promoção.
