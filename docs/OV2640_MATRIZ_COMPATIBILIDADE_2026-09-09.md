# Matriz de compatibilidade OV2640 — release Pages to Audio

Data da verificação: 2026-09-09  
Hardware alvo: ESP32-S3-CAM N16R8 + OV2640 2 MP  
Escopo: imagem para OCR/foto e diagnóstico técnico protegido. Vídeo continua
fora desta release.

## Identidade das fontes

| Código | Fonte e revisão usada |
|---|---|
| D1 | [OV2640 datasheet v1.6](https://dl.sipeed.com/MAIX/HDK/Chip_DS/OV2640-DATASHEET.pdf), versão 1.6 de 2006-02-28; especialmente descrição, formatos, controles de imagem, zoom/windowing, sincronização e strobe. |
| L1 | Firmware local `managed_components/espressif__esp32-camera/dependencies.lock`: `espressif/esp32-camera` **2.1.7**, `component_hash` `bc9c8a6b51df777a014fa295825b3de5069bc0300c317acff20c97cf4a10ac7d`; tag oficial `v2.1.7` no commit `202df95d7b1dc72e9303ad78f47b8dc9f339e6a1`. |
| L2 | `driver/include/sensor.h:81-123, 191-257`: enums de pixel/frame size, status e ponte de funções; `driver/sensor.c:25`: tabela de resoluções. |
| L3 | `sensors/ov2640.c:110-246, 248-550`: formatos, windowing, resolução, controles, registradores, XCLK e ponte `esp32_camera_ov2640_init`. |
| L4 | `target/esp32s3/ll_cam.c` e `driver/esp_camera.c`: camada de captura ESP32-S3 e frame buffer. |
| P1 | `main/camera_service.c:34-48, 56-84, 125-147, 168-205, 283-405`: exposição real do produto; perfis comuns QVGA/VGA/SVGA/XGA/SXGA/UXGA, JPEG, uma framebuffer PSRAM, `CAMERA_GRAB_WHEN_EMPTY`, defaults e captura. |
| W1 | [CameraWebServer `app_httpd.cpp` no commit `6048a624f084ea7f645384fd91c57f43e633875d`](https://github.com/espressif/arduino-esp32/blob/6048a624f084ea7f645384fd91c57f43e633875d/libraries/ESP32/examples/Camera/CameraWebServer/app_httpd.cpp): handler `set`, `set_reg` e `greg`; [entrypoint `.ino`](https://github.com/espressif/arduino-esp32/blob/6048a624f084ea7f645384fd91c57f43e633875d/libraries/ESP32/examples/Camera/CameraWebServer/CameraWebServer.ino). |

As classificações abaixo são deliberadamente conservadoras. `sensor.h`
sozinho não prova implementação: a decisão usa o corpo de `ov2640.c`, a
ponte de funções e a camada real do produto.

## Matriz

| Recurso | Suporte segundo o datasheet | Implementação real em `esp32-camera` 2.1.7/`ov2640.c` | Exposição no CameraWebServer | Exposição permitida no projeto | Teste necessário | Mensagem para Android/backend |
|---|---|---|---|---|---|---|
| 96×96 | Compatível e implementado. [D1] | Compatível e implementado. [L2,L3] | Compatível e implementado. [W1] | Compatível somente para diagnóstico. | Capturar e confirmar dimensões efetivas e rejeitar uso OCR. | `Resolução reduzida reservada para diagnóstico.` |
| QQVGA 160×120 | Compatível e implementado. [D1] | Compatível e implementado. [L2,L3] | Compatível e implementado. [W1] | Compatível somente para diagnóstico. | Capturar, medir legibilidade e confirmar dimensões. | `QQVGA não é perfil OCR desta release.` |
| 128×128 | Compatível e implementado. [D1] | Compatível e implementado. [L2,L3] | Compatível e implementado. [W1] | Compatível somente para diagnóstico. | Capturar e confirmar recorte quadrado. | `Perfil quadrado reservado para diagnóstico.` |
| QCIF 176×144 | Compatível e implementado. [D1] | Compatível e implementado. [L2,L3] | Compatível e implementado. [W1] | Compatível somente para diagnóstico. | Capturar e medir texto pequeno. | `QCIF não é perfil OCR desta release.` |
| HQVGA 240×176 | Compatível e implementado. [D1] | Compatível e implementado. [L2,L3] | Compatível e implementado. [W1] | Compatível somente para diagnóstico. | Capturar e confirmar dimensões efetivas. | `HQVGA reservado para diagnóstico.` |
| 240×240 | Compatível e implementado. [D1] | Compatível e implementado. [L2,L3] | Compatível e implementado. [W1] | Compatível somente para diagnóstico. | Capturar e confirmar recorte quadrado. | `240×240 reservado para diagnóstico.` |
| QVGA 320×240 | Compatível e implementado. [D1] | Compatível e implementado. [L2,L3] | Compatível e implementado. [W1] | Compatível somente para diagnóstico. | Capturar, medir legibilidade e confirmar dimensões. | `QVGA não é perfil OCR desta release.` |
| 320×320 | Compatível e implementado. [D1] | Compatível e implementado. [L2,L3] | Compatível e implementado. [W1] | Compatível somente para diagnóstico. | Capturar e confirmar recorte quadrado. | `320×320 reservado para diagnóstico.` |
| CIF 400×296 | Compatível e implementado. [D1] | Compatível e implementado. [L2,L3] | Compatível e implementado. [W1] | Compatível somente para diagnóstico. | Capturar e confirmar dimensões efetivas. | `CIF não é perfil OCR desta release.` |
| HVGA 480×320 | Compatível e implementado. [D1] | Compatível e implementado. [L2,L3] | Compatível e implementado. [W1] | Compatível somente para diagnóstico. | Capturar e medir legibilidade. | `HVGA reservado para diagnóstico.` |
| VGA 640×480 | Compatível e implementado. [D1] | Compatível e implementado. [L2,L3] | Compatível e implementado. [W1] | Compatível somente para diagnóstico. | Capturar e confirmar bytes/dimensões no dispositivo. | `VGA é permitido apenas no perfil técnico.` |
| SVGA 800×600 | Compatível e implementado. [D1] | Compatível e implementado. [L2,L3] | Compatível e implementado. [W1] | Compatível no sensor, mas não recomendado para OCR. | Capturar página real e medir OCR/bytes. | `SVGA não é recomendado para OCR.` |
| XGA 1024×768 | Compatível e implementado. [D1] | Compatível e implementado. [L2,L3] | Compatível e implementado. [W1] | Compatível no sensor, mas não recomendado para OCR. | Capturar página real e medir OCR/bytes. | `XGA não é recomendado para OCR.` |
| HD 1280×720 | Compatível e implementado. [D1] | Compatível e implementado. [L2,L3] | Compatível e implementado. [W1] | Compatível no sensor, mas não recomendado para OCR. | Capturar e confirmar recorte 16:9; não liberar por padrão. | `HD não é perfil OCR desta release.` |
| SXGA 1280×1024 | Compatível e implementado. [D1] | Compatível e implementado. [L2,L3] | Compatível e implementado. [W1] | Compatível no sensor, mas não recomendado para OCR. | Capturar página real e medir OCR/bytes. | `SXGA não é recomendado para OCR.` |
| UXGA 1600×1200 | Compatível e implementado. [D1] | Compatível e implementado. [L2,L3] | Compatível e implementado. [W1] | Requer teste físico antes de ser liberado. | Medir dimensões, JPEG, PSRAM, tempo e estabilidade na placa. | `UXGA só pode ser habilitado após validação física.` |
| Proporções e recortes | Compatível e implementado. [D1] | Parcialmente compatível. [L3] | Compatível somente para diagnóstico. [W1] | Compatível somente para diagnóstico. | Exercitar cada proporção e comparar janela efetiva com o pedido. | `Recorte/windowing não é controle comum do perfil OCR.` |
| JPEG | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Requer teste físico antes de ser liberado. | Validar marcador JPEG, decodificação, tamanho, hash e estabilidade. | `JPEG efetivo e tamanho devem ser reportados.` |
| YUV422 | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Parcialmente compatível. [W1] | Compatível no sensor, mas não recomendado para OCR. | Capturar e validar conversão/uso de memória antes de qualquer experimento. | `YUV422 não é perfil OCR desta release.` |
| YUV420 | Compatível e implementado. [D1] | Não compatível no driver atual. [L3] | Não compatível no driver atual. [W1] | Compatível no sensor, mas não recomendado para OCR. | Confirmar rejeição explícita no driver e manter fora do contrato. | `YUV420 depende de configuração adicional e não é permitido no OCR.` |
| RGB565 | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Parcialmente compatível. [W1] | Compatível no sensor, mas não recomendado para OCR. | Capturar e medir custo/qualidade; manter JPEG no produto. | `RGB565 não é o formato de captura OCR.` |
| RGB555 | Compatível e implementado. [D1] | Não compatível no driver atual. [L3] | Não compatível no driver atual. [W1] | Não compatível no driver atual. | Enviar pedido negativo e confirmar erro sem fallback silencioso. | `RGB555 não é compatível no driver atual.` |
| RGB888 | Não suportado pela OV2640. [D1] | Parcialmente compatível. [L3] | Não compatível no driver atual. [W1] | Não compatível no driver atual. | Confirmar que não há liberação do caminho parcial para produção. | `RGB888 não oferece caminho confiável de ponta a ponta nesta release.` |
| RAW | Compatível e implementado. [D1] | Não compatível no driver atual. [L3] | Não compatível no driver atual. [W1] | Não compatível no driver atual. | Confirmar rejeição do formato bruto. | `RAW não é compatível no driver atual.` |
| RAW8 | Compatível e implementado. [D1] | Não compatível no driver atual. [L3] | Não compatível no driver atual. [W1] | Não compatível no driver atual. | Confirmar rejeição do formato bruto. | `RAW8 não é compatível no driver atual.` |
| Brilho | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Requer teste físico antes de ser liberado. | Medir efeito em página clara/escura e persistir solicitado/efetivo. | `Brilho efetivo deve ser confirmado no dispositivo.` |
| Contraste | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Requer teste físico antes de ser liberado. | Medir efeito e impacto no OCR; não confundir com qualidade JPEG. | `Contraste efetivo deve ser confirmado no dispositivo.` |
| Saturação | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Requer teste físico antes de ser liberado. | Medir efeito sem alterar legibilidade das marcações. | `Saturação efetiva deve ser confirmada no dispositivo.` |
| Qualidade JPEG | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Requer teste físico antes de ser liberado. | Medir qualidade OV2640 8–12, bytes, decodificação e OCR. | `esp_jpeg_quality (8–12) não é a escala Android 0–100.` |
| Exposição automática (AEC) | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Requer teste físico antes de ser liberado. | Medir página uniforme, sombra e brilho; registrar estado efetivo. | `AEC efetivo deve ser reportado.` |
| Exposição manual | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Compatível somente para diagnóstico. | Exercitar somente endpoint protegido e confirmar retorno ao automático. | `Exposição manual não é controle comum do OCR.` |
| Nível de exposição | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Requer teste físico antes de ser liberado. | Medir níveis extremos e legibilidade. | `Nível de exposição efetivo deve ser confirmado.` |
| Ganho automático (AGC) | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Requer teste físico antes de ser liberado. | Medir iluminação baixa e ruído. | `AGC efetivo deve ser reportado.` |
| Ganho manual | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Compatível somente para diagnóstico. | Exercitar endpoint protegido, ruído e recuperação para automático. | `Ganho manual não é controle comum do OCR.` |
| Limite de ganho | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Requer teste físico antes de ser liberado. | Medir limite em baixa luz e confirmar estabilidade. | `Limite de ganho efetivo deve ser confirmado.` |
| AWB | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Requer teste físico antes de ser liberado. | Medir luz neutra e colorida; persistir solicitado/efetivo. | `AWB efetivo deve ser reportado.` |
| Ganho de AWB | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Requer teste físico antes de ser liberado. | Medir com AWB ligado/desligado em bancada. | `Ganho de AWB efetivo deve ser confirmado.` |
| Modos de balanço de branco | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Requer teste físico antes de ser liberado. | Exercitar cada modo disponível e validar cor/legibilidade. | `Modo WB efetivo deve ser reportado.` |
| BPC | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Requer teste físico antes de ser liberado. | Comparar ligado/desligado com padrão controlado. | `BPC efetivo deve ser confirmado.` |
| WPC | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Requer teste físico antes de ser liberado. | Comparar ligado/desligado com pontos claros controlados. | `WPC efetivo deve ser confirmado.` |
| Raw Gamma | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Requer teste físico antes de ser liberado. | Medir escala tonal e impacto no OCR. | `Raw Gamma efetivo deve ser confirmado.` |
| Lens Correction | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Requer teste físico antes de ser liberado. | Medir bordas e geometria da página. | `Lens Correction efetivo deve ser confirmado.` |
| DCW | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Requer teste físico antes de ser liberado. | Medir redução e impacto em cada resolução. | `DCW efetivo deve ser confirmado.` |
| Hmirror | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Requer teste físico antes de ser liberado. | Capturar marcador assimétrico e confirmar orientação. | `Hmirror deve permanecer desligado no perfil OCR.` |
| Vflip | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Requer teste físico antes de ser liberado. | Capturar marcador assimétrico e confirmar orientação. | `Vflip deve permanecer desligado no perfil OCR.` |
| Efeitos especiais | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Compatível somente para diagnóstico. | Exercitar efeitos sem contaminar missão OCR. | `Efeitos especiais não são permitidos no OCR.` |
| Colorbar/test pattern | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Compatível somente para diagnóstico. | Confirmar padrão e impedir envio como frame de missão. | `Colorbar é somente diagnóstico e não é evidência de página.` |
| Sharpness | Compatível e implementado. [D1] | Não compatível no driver atual. [L3] | Não compatível no driver atual. [W1] | Não compatível no driver atual. | Enviar pedido negativo e confirmar erro explícito. | `Sharpness — não disponível no driver OV2640 atual.` |
| Denoise | Compatível e implementado. [D1] | Não compatível no driver atual. [L3] | Não compatível no driver atual. [W1] | Não compatível no driver atual. | Enviar pedido negativo e confirmar erro explícito. | `Denoise — não disponível no driver OV2640 atual.` |
| Autofocus | Não suportado pela OV2640. [D1] | Não compatível no driver atual. [L3] | Não compatível no driver atual. [W1] | Não suportado pela OV2640. | Confirmar ponte AF nula e rejeição no contrato. | `Autofocus — não suportado; OV2640 depende de foco mecânico fixo.` |
| Foco manual eletrônico | Não suportado pela OV2640. [D1] | Não compatível no driver atual. [L3] | Não compatível no driver atual. [W1] | Não suportado pela OV2640. | Confirmar ausência de atuador e de setter funcional. | `Foco manual — não existe controle eletrônico de foco neste hardware.` |
| Zoom | Compatível e implementado. [D1] | Parcialmente compatível. [L3] | Compatível somente para diagnóstico. [W1] | Compatível somente para diagnóstico. | Exercitar janela e confirmar que não substitui enquadramento físico. | `Zoom não é controle comum do perfil OCR.` |
| Pan/windowing | Compatível e implementado. [D1] | Parcialmente compatível. [L3] | Compatível somente para diagnóstico. [W1] | Compatível somente para diagnóstico. | Comparar janela solicitada/efetiva e rejeitar valores fora do sensor. | `Pan/windowing não é controle comum do perfil OCR.` |
| Controle de PLL | Compatível e implementado. [D1] | Não compatível no driver atual. [L3] | Parcialmente compatível. [W1] | Não compatível no driver atual. | Confirmar que `set_pll` retorna erro e que timing interno não é remoto. | `PLL — não disponível na implementação local da OV2640.` |
| XCLK | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Compatível somente para diagnóstico. | Medir frequência real e manter valor efetivo fixo em 10 MHz. | `XCLK remoto não é editável; valor efetivo 10 MHz.` |
| Controle de frame rate | Compatível e implementado. [D1] | Compatível no sensor, mas não exposto pelo driver. [L2,L3] | Parcialmente compatível. [W1] | Não compatível no driver atual. | Medir taxa efetiva em placa/rede; não prometer FPS por configuração. | `Frame rate será medido; não é controle liberado nesta release.` |
| Sincronização | Compatível e implementado. [D1] | Compatível no sensor, mas não exposto pelo driver. [L2,L3] | Não compatível no driver atual. [W1] | Compatível somente para diagnóstico. | Medir VSYNC/PCLK e sincronismo com captura, sem expor ajuste comum. | `Sincronização é somente diagnóstico nesta release.` |
| Flash/strobe | Compatível e implementado. [D1] | Compatível no sensor, mas não exposto pelo driver. [L3] | Recurso de hardware separado da câmera. [W1] | Recurso de hardware separado da câmera. | Testar GPIO/flash da placa separadamente, sem atribuir efeito ao sensor. | `Flash — não é controle de imagem; hardware separado e bloqueado neste projeto.` |
| Leitura/escrita de registradores | Compatível e implementado. [D1] | Compatível e implementado. [L3] | Compatível e implementado. [W1] | Compatível somente para diagnóstico. | Usar somente endpoint protegido, registrar endereço/máscara/valor e restaurar estado. | `Registradores são restritos à engenharia protegida.` |

## Decisões de produto e mensagens obrigatórias

- Perfis OCR e Foto desta release usam somente UXGA após aprovação física,
  JPEG, `esp_jpeg_quality` entre 8 e 12, XCLK efetivo de 10 MHz e os controles
  conservadores definidos no perfil versionado.
- `android_jpeg_quality_percent` (0–100) e `esp_jpeg_quality` (8–12) são
  escalas distintas; nunca converter silenciosamente uma na outra.
- Nenhum campo não suportado pode virar sucesso silencioso. O backend deve
  devolver erro ou aviso explícito e persistir a configuração solicitada e a
  efetiva.
- `Vídeo — reservado para evolução futura e indisponível nesta versão.` O
  CameraWebServer usado como fonte de comparação não autoriza implementar
  Vídeo no produto.
- O flash branco da placa não é o WS2812 e não participa do contrato de imagem.

## Resultado do gate G02

A matriz cobre individualmente todos os recursos exigidos pelo plano, cita a
versão/commit exatos do componente local e separa datasheet, driver,
CameraWebServer e decisão de produto. Nenhuma capacidade foi classificada
como compatível apenas pela existência de um ponteiro em `sensor.h`; os casos
de `set_sharpness`, `set_denoise`, `set_pll`, windowing e autofocus foram
conferidos no corpo/ponte de `ov2640.c`.
