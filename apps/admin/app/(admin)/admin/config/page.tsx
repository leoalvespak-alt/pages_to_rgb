"use client";

import { useEffect, useMemo, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";

type Color = { rgb: number[] };
type Palette = Record<string, Color>;
type Settings = {
  version: number;
  ocr_provider: string;
  solve_model: string;
  verify_model: string;
  arbiter_model: string;
  gemini_configured: boolean;
  expected_pages: number;
  expected_questions: number;
  handwritten_expected_questions: number;
  minimum_ratio: number;
  brightness_percent: number;
  on_ms: number;
  off_ms: number;
  palette: Palette;
  handwritten_palette: Palette;
  handwritten_words: Record<string, string>;
  google_document_ai_project_id: string;
  google_document_ai_location: string;
  google_document_ai_processor_id: string;
  google_document_ai_processor_version: string | null;
  google_document_ai_credentials: string;
  google_document_ai_configured: boolean;
  google_document_ai_credentials_configured: boolean;
};

type Provider = { name: string; label: string; kind: "llm" | "ocr"; models: string[]; notes?: string };
type ProviderKey = "gemini" | "google_document_ai";

const letters = "ABCDE".split("");
const keyRows = [["gemini", "Gemini 3.1 Pro"]] as const;

function hex(rgb: number[]): string { return `#${rgb.map((x) => x.toString(16).padStart(2, "0")).join("")}`; }
function fromHex(value: string): number[] { return [1, 3, 5].map((index) => parseInt(value.slice(index, index + 2), 16)); }
function isConfigured(settings: Settings, provider: ProviderKey): boolean {
  return provider === "gemini"
    ? settings.gemini_configured
    : settings.google_document_ai_credentials_configured;
}

export default function ConfigPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [catalog, setCatalog] = useState<Provider[]>([]);
  const [keys, setKeys] = useState<Partial<Record<ProviderKey, string>>>({});
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [testSession, setTestSession] = useState("");
  const [testColor, setTestColor] = useState([0, 0, 255]);
  const [testBrightness, setTestBrightness] = useState(25);
  const [testOn, setTestOn] = useState(2000);
  const [testOff, setTestOff] = useState(1000);

  async function load(): Promise<void> {
    try {
      const [read, available] = await Promise.all([apiFetch<Settings>("/api/v1/admin/settings"), apiFetch<{ providers: Provider[] }>("/api/v1/admin/settings/catalog")]);
      setSettings(read); setCatalog(available.providers);
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Falha ao carregar configurações"); }
  }
  useEffect(() => { void load(); }, []);
  const llmProviders = useMemo(() => catalog.filter((item) => item.kind === "llm"), [catalog]);
  const ocrProviders = useMemo(() => catalog.filter((item) => item.kind === "ocr"), [catalog]);

  function updateField(field: keyof Settings, value: unknown): void { setSettings((current) => current ? { ...current, [field]: value } : current); }
  function updatePalette(which: "palette" | "handwritten_palette", letter: string, rgb: number[]): void { setSettings((current) => current ? { ...current, [which]: { ...current[which], [letter]: { rgb } } } : current); }
  function updateWord(letter: string, value: string): void { setSettings((current) => current ? { ...current, handwritten_words: { ...current.handwritten_words, [letter]: value } } : current); }
  function buildPayload(): Record<string, unknown> | null {
    if (!settings) return null;
    return {
      version: settings.version, ocr_provider: settings.ocr_provider, solve_model: settings.solve_model,
      verify_model: settings.verify_model, arbiter_model: settings.arbiter_model,
      expected_pages: settings.expected_pages, expected_questions: settings.expected_questions,
      handwritten_expected_questions: settings.handwritten_expected_questions, minimum_ratio: settings.minimum_ratio,
      brightness_percent: settings.brightness_percent, on_ms: settings.on_ms, off_ms: settings.off_ms,
      palette: settings.palette, handwritten_palette: settings.handwritten_palette, handwritten_words: settings.handwritten_words,
      google_document_ai_project_id: settings.google_document_ai_project_id,
      google_document_ai_location: settings.google_document_ai_location,
      google_document_ai_processor_id: settings.google_document_ai_processor_id,
      google_document_ai_processor_version: settings.google_document_ai_processor_version,
      ...Object.entries(keys).reduce<Record<string, string>>((acc, [name, value]) => {
        if (name === "gemini" && value?.trim()) acc.gemini_api_key = value;
        return acc;
      }, {}),
      ...(keys.google_document_ai ? { google_document_ai_credentials: keys.google_document_ai } : {}),
    };
  }
  async function save(): Promise<void> {
    const payload = buildPayload(); if (!payload) return; setBusy(true); setError("");
    try { setSettings(await apiFetch<Settings>("/api/v1/admin/settings", { method: "PUT", body: JSON.stringify(payload) })); setKeys({}); setMessage("Configurações salvas. Novas sessões usarão esta versão."); }
    catch (cause) { setError(cause instanceof ApiError && cause.status === 409 ? "Outra aba alterou os dados. Recarregue e tente novamente." : cause instanceof ApiError ? cause.message : "Falha ao salvar"); }
    finally { setBusy(false); }
  }
  async function testProvider(name: string): Promise<void> {
    if (!settings) return; const provider = name as ProviderKey; const definition = catalog.find((item) => item.name === provider); const model = definition?.models[0];
    if (!model) { setError("Modelo não disponível no catálogo oficial"); return; } setError("");
    try { if (keys[provider]) { const payload = buildPayload(); if (payload) setSettings(await apiFetch<Settings>("/api/v1/admin/settings", { method: "PUT", body: JSON.stringify(payload) })); setKeys({}); }
      const result = await apiFetch<{ ok: boolean; latency_ms: number; message?: string }>("/api/v1/admin/settings/test", { method: "POST", body: JSON.stringify({ provider, model }) });
      setMessage(result.ok ? `${name}: conectado em ${result.latency_ms} ms` : `${name}: ${result.message || "falha"}`);
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Falha no teste"); }
  }
  async function sendRgbTest(): Promise<void> {
    setError("");
    try { const result = await apiFetch<{ command_id: number }>("/api/v1/admin/settings/rgb-test", { method: "POST", body: JSON.stringify({ session_id: testSession.trim(), rgb: testColor, brightness_percent: testBrightness, on_ms: testOn, off_ms: testOff }) }); setMessage(`Teste RGB #${result.command_id} enviado ao Android.`); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "Falha ao enviar teste RGB"); }
  }
  if (!settings) return <div className="p-8 text-zinc-400">{error || "Carregando…"}</div>;
  const modelOptions = (field: string): string[] => llmProviders.flatMap((item) => item.models).filter((model, index, all) => all.indexOf(model) === index || model === settings[field as keyof Settings]);

  return <div className="mx-auto max-w-5xl space-y-6 p-4 md:p-6">
    <div><h1 className="text-2xl font-semibold">Configurações</h1><p className="text-sm text-zinc-400">Versão {settings.version}. Mudanças afetam somente novas sessões.</p></div>
    {error && <p role="alert" className="rounded-lg border border-red-900 p-3 text-red-300">{error}</p>}{message && <p role="status" className="rounded-lg border border-emerald-900 p-3 text-emerald-300">{message}</p>}
    <section className="card space-y-4"><h2 className="font-medium">Modelos de raciocínio</h2>
      {[["solve_model", "Modelo que resolve"], ["verify_model", "Modelo que confere"], ["arbiter_model", "Modelo que decide"]].map(([field, label]) => <label key={field} className="grid gap-2 text-sm md:grid-cols-[250px_1fr]"><span>{label}</span><select className="control" value={String(settings[field as keyof Settings])} onChange={(event) => updateField(field as keyof Settings, event.target.value)}>{modelOptions(field).map((model) => <option key={model}>{model}</option>)}</select></label>)}
      {keyRows.map(([name, label]) => <div key={name} className="grid items-center gap-2 md:grid-cols-[250px_1fr_auto]"><label className="text-sm" htmlFor={`key-${name}`}>{label} — {isConfigured(settings, name) ? "Configurada" : "Não configurada"}</label><input id={`key-${name}`} type="password" autoComplete="new-password" className="control" value={keys[name] || ""} onChange={(event) => setKeys({ ...keys, [name]: event.target.value })} placeholder="Deixe vazio para preservar"/><button onClick={() => void testProvider(name)} className="secondary">Salvar e verificar</button></div>)}
    </section>
    <section className="card space-y-4"><h2 className="font-medium">Google Document AI (OCR)</h2><p className="text-sm text-zinc-400">Credencial do Document AI é independente da chave Gemini. {ocrProviders[0]?.notes || "Use uma service account com acesso restrito ao processor."}</p><div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">Projeto<input className="control mt-1" value={settings.google_document_ai_project_id} onChange={(event) => updateField("google_document_ai_project_id", event.target.value)} /></label><label className="text-sm">Região<input className="control mt-1" value={settings.google_document_ai_location} onChange={(event) => updateField("google_document_ai_location", event.target.value)} /></label><label className="text-sm">Processor ID<input className="control mt-1" value={settings.google_document_ai_processor_id} onChange={(event) => updateField("google_document_ai_processor_id", event.target.value)} /></label><label className="text-sm">Versão do processor<input className="control mt-1" value={settings.google_document_ai_processor_version || ""} onChange={(event) => updateField("google_document_ai_processor_version", event.target.value || null)} /></label></div><div className="grid items-center gap-2 md:grid-cols-[250px_1fr_auto]"><label className="text-sm" htmlFor="key-google_document_ai">Credencial ADC/JSON — {settings.google_document_ai_credentials_configured ? "Configurada" : "Não configurada"}</label><input id="key-google_document_ai" type="password" autoComplete="new-password" className="control" value={keys.google_document_ai || ""} onChange={(event) => setKeys({ ...keys, google_document_ai: event.target.value })} placeholder="JSON da service account ou referência ao secret" /><button onClick={() => void testProvider("google_document_ai")} className="secondary">Salvar e verificar</button><span className="text-xs text-zinc-400">{settings.google_document_ai_configured ? "Processor definido" : "Configuração incompleta"}</span></div></section>
    <section className="card space-y-5"><h2 className="font-medium">Prova, palavras e cores</h2><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{([["expected_pages", "Páginas EXAM"], ["expected_questions", "Questões EXAM"], ["handwritten_expected_questions", "Fotos manuscrito"], ["minimum_ratio", "Mínimo RGB (0–1)"], ["brightness_percent", "Brilho %"], ["on_ms", "Ligado ms"], ["off_ms", "Desligado ms"]] as [keyof Settings, string][]).map(([field, label]) => <label key={field} className="text-sm">{label}<input className="control mt-1" type="number" step={field === "minimum_ratio" ? "0.01" : "1"} value={Number(settings[field])} onChange={(event) => updateField(field, Number(event.target.value))} /></label>)}</div><div><h3 className="mb-2 text-sm text-zinc-300">Palavras e cores do teste manuscrito</h3><div className="grid gap-3 sm:grid-cols-5">{letters.map((letter) => <div key={letter} className="rounded-lg bg-[#242424] p-3"><label className="text-sm">Código {letter}<input className="control mt-1" value={settings.handwritten_words[letter]} maxLength={80} onChange={(event) => updateWord(letter, event.target.value)} /></label><label className="mt-2 block text-xs text-zinc-400">RGB {settings.handwritten_palette[letter].rgb.join(",")}<input className="mt-1 h-10 w-full" type="color" value={hex(settings.handwritten_palette[letter].rgb)} onChange={(event) => updatePalette("handwritten_palette", letter, fromHex(event.target.value))} /></label></div>)}</div></div><div><h3 className="mb-2 text-sm text-zinc-300">Paleta da prova</h3><div className="grid gap-2 sm:grid-cols-5">{letters.map((letter) => <label key={letter} className="rounded-lg bg-[#242424] p-3 text-sm"><span className="mb-2 block">{letter} • {settings.palette[letter].rgb.join(",")}</span><input className="h-10 w-full" type="color" value={hex(settings.palette[letter].rgb)} onChange={(event) => updatePalette("palette", letter, fromHex(event.target.value))} /></label>)}</div></div></section>
    <section className="card space-y-4"><div><h2 className="font-medium">Teste RGB no Android</h2><p className="text-sm text-zinc-400">Inicie uma sessão no celular, copie o ID exibido e envie cor, brilho e tempos para validar o RGB antes do ESP32.</p></div><label className="text-sm">ID da sessão ativa<input className="control mt-1" value={testSession} onChange={(event) => setTestSession(event.target.value)} placeholder="UUID mostrado no Android" /></label><div className="grid gap-4 sm:grid-cols-4"><label className="text-sm">Cor<input className="mt-1 h-10 w-full" type="color" value={hex(testColor)} onChange={(event) => setTestColor(fromHex(event.target.value))} /></label><label className="text-sm">Brilho %<input className="control mt-1" type="number" min="0" max="100" value={testBrightness} onChange={(event) => setTestBrightness(Number(event.target.value))} /></label><label className="text-sm">Ligado ms<input className="control mt-1" type="number" min="100" max="60000" value={testOn} onChange={(event) => setTestOn(Number(event.target.value))} /></label><label className="text-sm">Desligado ms<input className="control mt-1" type="number" min="0" max="60000" value={testOff} onChange={(event) => setTestOff(Number(event.target.value))} /></label></div><button onClick={() => void sendRgbTest()} disabled={!testSession.trim()} className="secondary w-full">Acionar cor no Android</button></section>
    <button disabled={busy} onClick={() => void save()} className="primary w-full py-3">{busy ? "Salvando…" : "Salvar configurações"}</button>
  </div>;
}
