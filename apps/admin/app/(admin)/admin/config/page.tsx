"use client";
import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

type Color = { rgb: number[] };
type Palette = Record<string, Color>;
type Settings = {
  version:number; ocr_provider:string; solve_model:string; verify_model:string; arbiter_model:string;
  deepseek_configured:boolean; gemini_configured:boolean; anthropic_configured:boolean; glm_configured:boolean;
  expected_pages:number; expected_questions:number; handwritten_expected_questions:number; minimum_ratio:number;
  brightness_percent:number; on_ms:number; off_ms:number; palette:Palette; handwritten_palette:Palette;
  handwritten_words:Record<string,string>;
};

const models=["deepseek-v4-pro","gemini-3.1-pro","claude-opus-5","glm-5.3"];
const keyRows=[["deepseek","DeepSeek"],["gemini","Gemini"],["anthropic","Claude"],["glm","GLM"]] as const;
const letters="ABCDE".split("");
function hex(rgb:number[]){return `#${rgb.map(x=>x.toString(16).padStart(2,"0")).join("")}`;}
function fromHex(v:string){return [1,3,5].map(i=>parseInt(v.slice(i,i+2),16));}

export default function ConfigPage(){
  const [s,setS]=useState<Settings|null>(null),[keys,setKeys]=useState<Record<string,string>>({});
  const [msg,setMsg]=useState(""),[error,setError]=useState(""),[busy,setBusy]=useState(false);
  const [testSession,setTestSession]=useState(""),[testColor,setTestColor]=useState([0,0,255]);
  const [testBrightness,setTestBrightness]=useState(25),[testOn,setTestOn]=useState(2000),[testOff,setTestOff]=useState(1000);

  async function load(){try{setS(await apiFetch<Settings>("/api/v1/admin/settings"));}catch(e){setError(e instanceof ApiError?e.message:"Falha ao carregar");}}
  useEffect(()=>{load();},[]);
  async function save(){if(!s)return;setBusy(true);setError("");try{const payload={version:s.version,ocr_provider:s.ocr_provider,solve_model:s.solve_model,verify_model:s.verify_model,arbiter_model:s.arbiter_model,expected_pages:s.expected_pages,expected_questions:s.expected_questions,handwritten_expected_questions:s.handwritten_expected_questions,minimum_ratio:s.minimum_ratio,brightness_percent:s.brightness_percent,on_ms:s.on_ms,off_ms:s.off_ms,palette:s.palette,handwritten_palette:s.handwritten_palette,handwritten_words:s.handwritten_words,...Object.fromEntries(Object.entries(keys).filter(([,v])=>v).map(([k,v])=>[`${k}_api_key`,v]))};setS(await apiFetch<Settings>("/api/v1/admin/settings",{method:"PUT",body:JSON.stringify(payload)}));setKeys({});setMsg("Configurações salvas. Novas sessões usarão esta versão.");}catch(e){setError(e instanceof ApiError?(e.status===409?"Outra aba alterou os dados. Recarregue e tente novamente.":e.message):"Falha ao salvar");}finally{setBusy(false);}}
  async function testProvider(name:string){const map:Record<string,string>={deepseek:"deepseek-v4-pro",gemini:"gemini-3.1-pro",anthropic:"claude-opus-5",glm:"glm-5.3"};const provider=name==="anthropic"?"claude":name;try{const r=await apiFetch<{ok:boolean;latency_ms:number;message?:string}>("/api/v1/admin/settings/test",{method:"POST",body:JSON.stringify({provider,model:map[name]})});setMsg(r.ok?`${name}: conectado em ${r.latency_ms} ms`:`${name}: ${r.message}`);}catch(e){setError(e instanceof ApiError?e.message:"Falha no teste");}}
  async function sendRgbTest(){setError("");try{const r=await apiFetch<{command_id:number}>("/api/v1/admin/settings/rgb-test",{method:"POST",body:JSON.stringify({session_id:testSession.trim(),rgb:testColor,brightness_percent:testBrightness,on_ms:testOn,off_ms:testOff})});setMsg(`Teste RGB #${r.command_id} enviado ao Android.`);}catch(e){setError(e instanceof ApiError?e.message:"Falha ao enviar teste RGB");}}
  function field(key:keyof Settings,value:unknown){if(s)setS({...s,[key]:value});}
  function palette(which:"palette"|"handwritten_palette",letter:string,rgb:number[]){if(s)setS({...s,[which]:{...s[which],[letter]:{rgb}}});}
  function word(letter:string,value:string){if(s)setS({...s,handwritten_words:{...s.handwritten_words,[letter]:value}});}

  if(!s)return <div className="p-8 text-zinc-400">{error||"Carregando…"}</div>;
  return <div className="mx-auto max-w-5xl space-y-6 p-4 md:p-6">
    <div><h1 className="text-2xl font-semibold">Configurações</h1><p className="text-sm text-zinc-400">Versão {s.version}. Mudanças afetam somente novas sessões.</p></div>
    {error&&<p role="alert" className="rounded-lg border border-red-900 p-3 text-red-300">{error}</p>}{msg&&<p role="status" className="rounded-lg border border-emerald-900 p-3 text-emerald-300">{msg}</p>}
    <section className="card space-y-4"><h2 className="font-medium">Modelos e chaves</h2>
      {([["ocr_provider","Modelo que lê a foto (OCR)",["google_document_ai","azure","paddle"]],["solve_model","Modelo que resolve",models],["verify_model","Modelo que confere",models],["arbiter_model","Modelo que decide",models]] as [keyof Settings,string,string[]][]).map(([k,l,opts])=><label key={k} className="grid gap-2 text-sm md:grid-cols-[250px_1fr]"><span>{l}</span><select className="control" value={String(s[k])} onChange={e=>field(k,e.target.value)}>{opts.map(o=><option key={o}>{o}</option>)}</select></label>)}
      {keyRows.map(([k,l])=><div key={k} className="grid items-center gap-2 md:grid-cols-[250px_1fr_auto]"><label className="text-sm" htmlFor={`key-${k}`}>{l} — {(s as unknown as Record<string,boolean>)[`${k}_configured`]?"Configurada":"Não configurada"}</label><input id={`key-${k}`} type="password" autoComplete="off" className="control" value={keys[k]||""} onChange={e=>setKeys({...keys,[k]:e.target.value})} placeholder="Deixe vazio para preservar"/><button onClick={()=>testProvider(k)} className="secondary">Verificar</button></div>)}
    </section>
    <section className="card space-y-5"><h2 className="font-medium">Prova e teste manuscrito</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{([["expected_pages","Páginas EXAM"],["expected_questions","Questões EXAM"],["handwritten_expected_questions","Fotos manuscrito"],["minimum_ratio","Mínimo RGB (0–1)"],["brightness_percent","Brilho %"],["on_ms","Ligado ms"],["off_ms","Desligado ms"]] as [keyof Settings,string][]).map(([k,l])=><label key={k} className="text-sm">{l}<input className="control mt-1" type="number" step={k==="minimum_ratio"?"0.01":"1"} value={Number(s[k])} onChange={e=>field(k,Number(e.target.value))}/></label>)}</div>
      <div><h3 className="mb-2 text-sm text-zinc-300">Palavras e cores do teste manuscrito</h3><div className="grid gap-3 sm:grid-cols-5">{letters.map(letter=><div key={letter} className="rounded-lg bg-[#242424] p-3"><label className="text-sm">Código {letter}<input className="control mt-1" value={s.handwritten_words[letter]} maxLength={80} onChange={e=>word(letter,e.target.value)}/></label><label className="mt-2 block text-xs text-zinc-400">RGB {s.handwritten_palette[letter].rgb.join(",")}<input className="mt-1 h-10 w-full" type="color" value={hex(s.handwritten_palette[letter].rgb)} onChange={e=>palette("handwritten_palette",letter,fromHex(e.target.value))}/></label></div>)}</div></div>
      <div><h3 className="mb-2 text-sm text-zinc-300">Paleta da prova</h3><div className="grid gap-2 sm:grid-cols-5">{letters.map(letter=><label key={letter} className="rounded-lg bg-[#242424] p-3 text-sm"><span className="mb-2 block">{letter} • {s.palette[letter].rgb.join(",")}</span><input className="h-10 w-full" type="color" value={hex(s.palette[letter].rgb)} onChange={e=>palette("palette",letter,fromHex(e.target.value))}/></label>)}</div></div>
      <div><h3 className="mb-2 text-sm">Preview das 10 fotos</h3><div className="flex flex-wrap gap-2">{Array.from({length:10},(_,i)=>letters[i%5]).map((l,i)=><span key={i} title={`Foto ${i+1}: ${s.handwritten_words[l]} (${l})`} className="grid h-16 w-20 place-items-center rounded-lg border border-white/10 text-xs text-black" style={{background:`rgb(${s.handwritten_palette[l].rgb.join(",")})`,opacity:Math.max(.15,s.brightness_percent/100)}}>{s.handwritten_words[l]}</span>)}</div></div>
    </section>
    <section className="card space-y-4"><div><h2 className="font-medium">Teste RGB no Android</h2><p className="text-sm text-zinc-400">Inicie uma sessão no celular, copie o ID exibido e envie uma cor. O APK mostrará cor, brilho e duração.</p></div><label className="text-sm">ID da sessão ativa<input className="control mt-1" value={testSession} onChange={e=>setTestSession(e.target.value)} placeholder="UUID mostrado no Android"/></label><div className="grid gap-4 sm:grid-cols-4"><label className="text-sm">Cor<input className="mt-1 h-10 w-full" type="color" value={hex(testColor)} onChange={e=>setTestColor(fromHex(e.target.value))}/></label><label className="text-sm">Brilho %<input className="control mt-1" type="number" min="0" max="100" value={testBrightness} onChange={e=>setTestBrightness(Number(e.target.value))}/></label><label className="text-sm">Ligado ms<input className="control mt-1" type="number" min="100" max="60000" value={testOn} onChange={e=>setTestOn(Number(e.target.value))}/></label><label className="text-sm">Desligado ms<input className="control mt-1" type="number" min="0" max="60000" value={testOff} onChange={e=>setTestOff(Number(e.target.value))}/></label></div><button onClick={sendRgbTest} disabled={!testSession.trim()} className="secondary w-full">Acionar cor no Android</button></section>
    <button disabled={busy} onClick={save} className="primary w-full py-3">{busy?"Salvando…":"Salvar configurações"}</button>
  </div>;
}
