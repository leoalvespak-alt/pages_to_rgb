# Camera Control v2

Status: implementado no backend, feature flag `CAMERA_CONTRACT_V2_ENABLED=false`.

Este contrato cobre somente imagens estáticas para `OCR` e `PHOTO`. Os modos
legados `VIDEO`, `CLIP` e `PREVIEW` não podem criar uma revisão nem uma sessão
v2; o namespace de diagnóstico legado continua separado e desligado por sua
própria flag.

## Capabilities

`GET /api/v1/admin/camera-profiles/capabilities?device_code=CAM-001` exige
sessão administrativa. O gateway usa
`GET /api/v1/gateway/camera/capabilities?device_code=CAM-001` com seu token.
O retorno `CameraCapabilitiesV1` informa `available`, `protected` e
`unavailable`, além de `firmware_version`, `driver_version`, compatibilidade,
flag e `reason_code`.

O backend reconhece capability v2 quando o dispositivo já registrado contém
`metadata.camera_capabilities_version=v2` ou quando o gateway envia
`X-Camera-Capabilities-Version: v2`. Sem isso, uma sessão v2 é recusada com
`FIRMWARE_CAPABILITY_V2_REQUIRED`.

## Revisions and snapshots

`POST /api/v1/admin/camera-profiles` cria uma nova revisão. Não existe PUT/PATCH:
uma revisão usada permanece imutável e uma mudança gera uma nova revisão,
desativando a anterior. A alocação é serializada por escopo/mode, e cada
criação gera `CAMERA_PROFILE_CREATED` com o ator.

O início de uma sessão com a flag v2 ligada cria ou reutiliza o perfil padrão
do modo, grava a revisão e o snapshot em `sessions`, e retorna separadamente
`requested_camera_config` e `effective_camera_config`. Também gera
`CAMERA_PROFILE_SNAPSHOT_CREATED`.

Os limites do contrato são: `UXGA`, qualidade JPEG ESP 8–12, 1–3 frames,
intervalo entre frames 180–300 ms e intervalo de página de pelo menos 5 s.
Qualidade Android 90 não é aceita no campo `esp_jpeg_quality`.

## Rollback

A migração 0013 é aditiva. O rollback de aplicação desliga
`CAMERA_CONTRACT_V2_ENABLED`; dados históricos e a tabela legada
`rgb_test_commands` continuam preservados. Nenhuma rotina deste contrato
habilita Vídeo ou BIN Diagnostic.
