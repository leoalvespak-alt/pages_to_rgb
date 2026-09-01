"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/date";

type Row = { public_id:string; session_type:string; status:string; created_at:string; frames_count:number };
type Result = { items:Row[]; page:number; pages:number; total:number };

const statusColor: Record<string,string> = {
  CAPTURING:"bg-amber-500/15 text-amber-300", LOCKED:"bg-blue-500/15 text-blue-300",
  COMPLETED:"bg-emerald-500/15 text-emerald-300", CANCELLED:"bg-zinc-700 text-zinc-300",
  FAILED_FATAL:"bg-red-500/15 text-red-300", FAILED_RECOVERABLE:"bg-orange-500/15 text-orange-300",
};

export default function ProcessosPage() {
  const [data,setData]=useState<Result>({items:[],page:1,pages:0,total:0});
  const [type,setType]=useState("all"), [status,setStatus]=useState("all"), [q,setQ]=useState("");
  const [page,setPage]=useState(1), [loading,setLoading]=useState(true), [error,setError]=useState("");
  async function load(target=page) { setLoading(true); setError(""); try {
    const p=new URLSearchParams({page:String(target),limit:"20",type,status}); if(q.trim())p.set("q",q.trim());
    setData(await apiFetch<Result>(`/api/v1/admin/sessions?${p}`)); setPage(target);
  } catch(e){setError(e instanceof ApiError?e.message:"Falha ao carregar");} finally{setLoading(false);} }
  useEffect(()=>{load(1);},[type,status]); // eslint-disable-line react-hooks/exhaustive-deps
  return <div className="mx-auto max-w-7xl p-4 md:p-6">
    <div className="mb-6 flex items-end justify-between"><div><h1 className="text-2xl font-semibold">Processos</h1><p className="text-sm text-zinc-400">{data.total} sessões encontradas</p></div></div>
    <form onSubmit={e=>{e.preventDefault();load(1);}} className="mb-4 grid gap-2 rounded-xl border border-zinc-800 bg-[#1A1A1A] p-3 md:grid-cols-[180px_200px_1fr_auto]">
      <select aria-label="Tipo" value={type} onChange={e=>setType(e.target.value)} className="control"><option value="all">Todos os tipos</option><option value="EXAM">Prova Real</option><option value="HANDWRITTEN_WORD">Teste Manuscrito</option></select>
      <select aria-label="Status" value={status} onChange={e=>setStatus(e.target.value)} className="control"><option value="all">Todos os status</option>{["CAPTURING","LOCKED","IMAGE_PROCESSING","SOLVING","COMPLETED","FAILED_RECOVERABLE","FAILED_FATAL","CANCELLED"].map(s=><option key={s}>{s}</option>)}</select>
      <input aria-label="Buscar" value={q} onChange={e=>setQ(e.target.value)} placeholder="Buscar S-, dispositivo ou gateway" className="control" />
      <button className="primary">Buscar</button>
    </form>
    {error&&<div role="alert" className="mb-4 rounded-lg border border-red-900 bg-red-950/40 p-3 text-sm text-red-300">{error} <button onClick={()=>load()} className="underline">Tentar novamente</button></div>}
    <div className="overflow-x-auto rounded-xl border border-zinc-800 bg-[#1A1A1A]">
      <table className="w-full min-w-[760px] text-sm"><thead className="bg-[#252525] text-zinc-400"><tr>{["ID","Tipo","Status","Criado em","Fotos","Ações"].map(h=><th key={h} className="p-3 text-left font-medium">{h}</th>)}</tr></thead>
      <tbody>{!loading&&data.items.map(r=><tr key={r.public_id} className="border-t border-zinc-800 hover:bg-zinc-800/40"><td className="p-3 font-mono text-xs"><button title="Copiar ID" onClick={()=>navigator.clipboard.writeText(r.public_id)}>{r.public_id}</button></td><td className="p-3">{r.session_type==="HANDWRITTEN_WORD"?"Teste":"Prova"}</td><td className="p-3"><span className={`rounded-full px-2 py-1 text-xs ${statusColor[r.status]||"bg-violet-500/15 text-violet-300"}`}>{r.status}</span></td><td className="p-3 text-xs">{formatDate(r.created_at)}</td><td className="p-3">{r.frames_count}</td><td className="p-3"><Link className="text-red-400 hover:text-red-300" href={`/admin/processos/${r.public_id}`}>Ver</Link></td></tr>)}</tbody></table>
      {loading&&<p className="p-8 text-center text-zinc-400">Carregando…</p>}{!loading&&!data.items.length&&<p className="p-8 text-center text-zinc-500">Nenhum processo encontrado.</p>}
    </div>
    <div className="mt-4 flex items-center justify-end gap-3 text-sm"><button disabled={page<=1||loading} onClick={()=>load(page-1)} className="secondary disabled:opacity-40">Anterior</button><span>{page} de {Math.max(data.pages,1)}</span><button disabled={page>=data.pages||loading} onClick={()=>load(page+1)} className="secondary disabled:opacity-40">Próxima</button></div>
  </div>;
}
