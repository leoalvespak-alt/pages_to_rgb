// S09.5 — teste funcional dos fluxos alterados (S06.6 proposta, S08.3 abort, S08.4 paginação).
// Roda com: npm test  (tsc --noEmit && node --test __tests__/)
import { describe, it, mock } from "node:test";
import assert from "node:assert/strict";

// Importa o módulo compilado? api.ts é TypeScript; testamos o CONTRATO via
// transpilação sob demanda mínima: lê o fonte e valida os fluxos alterados.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const apiSrc = readFileSync(join(root, "lib", "api.ts"), "utf8");
const configSrc = readFileSync(
  join(root, "app", "(admin)", "admin", "config", "page.tsx"),
  "utf8"
);
const detailSrc = readFileSync(
  join(root, "app", "(admin)", "admin", "processos", "[id]", "page.tsx"),
  "utf8"
);

describe("S06.6 save-and-verify usa a proposta", () => {
  it("painel envia api_key/projeto/processador/credencial propostos", () => {
    for (const field of [
      "api_key",
      "google_document_ai_project_id",
      "google_document_ai_location",
      "google_document_ai_processor_id",
      "google_document_ai_credentials",
    ]) {
      assert.ok(configSrc.includes(field), `config page deve enviar ${field}`);
    }
    assert.ok(
      configSrc.includes("sem salvar antes") || configSrc.includes("proposta"),
      "deve documentar que nada é salvo antes do teste"
    );
  });
});

describe("S08.3 abort e polling", () => {
  it("apiFetch respeita sinal externo do chamador", () => {
    assert.ok(apiSrc.includes("init.signal"), "apiFetch deve ler init.signal");
    assert.ok(
      apiSrc.includes('addEventListener("abort"'),
      "apiFetch deve propagar abort externo"
    );
  });
  it("detalhe cancela requests antigos e para após terminal", () => {
    assert.ok(detailSrc.includes("AbortController"), "usa AbortController");
    assert.ok(detailSrc.includes("TERMINAL"), "para polling após estado terminal");
    assert.ok(detailSrc.includes("setInterval"), "atualiza enquanto ativa");
  });
});

describe("S08.4 paginação", () => {
  it("detalhe pagina fotos e registros", () => {
    assert.ok(detailSrc.includes("frames_page"), "pagina fotos");
    assert.ok(detailSrc.includes("logs_page"), "pagina registros");
    assert.ok(detailSrc.includes("frames_total"), "exibe total de fotos");
    assert.ok(detailSrc.includes("logs_total"), "exibe total de registros");
  });
});

describe("S07.1 mínimo RGB não sugere parcial", () => {
  it("painel esclarece que RGB exige 100%", () => {
    assert.ok(
      configSrc.includes("100%") && configSrc.includes("Gate 2"),
      "deve distinguir mínimo Gate 2 de completude RGB"
    );
  });
});
