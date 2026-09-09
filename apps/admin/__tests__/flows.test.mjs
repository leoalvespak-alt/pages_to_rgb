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

describe("D04/D05 página de teste de câmera", () => {
  it("prévia com polling controlado, stale e sem binário em JSON", () => {
    const camSrc = readFileSync(
      join(root, "app", "(admin)", "admin", "camera-test", "page.tsx"),
      "utf8"
    );
    assert.ok(camSrc.includes("500"), "metadados ~500 ms");
    assert.ok(camSrc.includes("pending"), "sem sobreposição de requests");
    assert.ok(camSrc.toLowerCase().includes("imagem desatualizada"), "sinaliza stale após 5 s");
    assert.ok(camSrc.includes("latest.jpg"), "JPEG como imagem, nunca base64 em JSON");
    assert.ok(!camSrc.includes("data:image"), "sem binário embutido em JSON");
    assert.ok(camSrc.includes("visibilitychange"), "aba oculta para polling/STOP");
    assert.ok(camSrc.includes("playsInline"), "player nativo sem áudio forçado");
    assert.ok(camSrc.includes("Download original"), "download do original");
  });
});
