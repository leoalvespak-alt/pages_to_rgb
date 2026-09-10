# Registro de execução G04 — upload, original e telemetria

Data: 2026-09-09  
Gate: G04 — Upload, original e telemetria  
Escopo: somente imagens da missão; Vídeo e BIN Diagnostic não foram usados.

## Evidência implementada

- O upload valida MIME, magic bytes, decodificação real, dimensões e SHA-256
  antes de criar a linha de frame.
- O objeto original usa a chave imutável `pages-originals/...` e recebe o
  mesmo SHA-256 declarado, calculado na origem e persistido na linha `frames`.
- O derivado OCR é gravado separadamente em `pages-derived/...`, nunca
  substitui o original, e `image_artifacts.metadata.original_sha256` e
  `original_storage_key` apontam para a origem.
- Retry com mesmo `capture_id`/`frame_index` e SHA retorna confirmação
  idempotente; conteúdo diferente continua em conflito 409.
- A identidade lógica `page_number`/`frame_number` é aceita por headers
  `X-Page-Number`/`X-Frame-Number`; a listagem administrativa ordena por página
  e frame, independentemente da chegada física.
- Frames registram tamanho/validade JPEG, resolução/qualidade solicitadas e
  efetivas, buffer, DMA, firmware, tempos e `confirmed_at`. O fechamento do
  burst retorna a contagem autoritativa do banco e a contagem declarada.
- Corrigido o retorno de `capture-complete`, que referenciava uma variável de
  upload inexistente.

## Verificações

- `ruff check` no conjunto alterado: aprovado.
- Testes específicos G04: 4 aprovados.
- Regressão de upload/idempotência: 8 aprovados.
- Suíte completa: 454 aprovados, 1 ignorado e 1 warning preexistente de
  `starlette.testclient`/`httpx`; nenhum teste falhou.

## Rollback

O comportamento novo permanece compatível com o fluxo legado; o original
continua separado do derivado. Em rollback de aplicação, remover o uso do
derivado não remove objetos originais nem linhas históricas. Não há alteração
destrutiva de dados neste gate.
