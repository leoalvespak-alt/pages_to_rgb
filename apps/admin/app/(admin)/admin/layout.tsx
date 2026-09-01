"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch, getMe } from "@/lib/api";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false); const path = usePathname(); const router = useRouter();
  useEffect(() => { getMe().then(() => setReady(true)).catch(() => router.replace(`/admin/login?next=${encodeURIComponent(path)}`)); }, [path, router]);
  async function logout() { await apiFetch<void>("/api/v1/admin/logout", { method: "POST" }); router.replace("/admin/login"); }
  if (!ready) return <div className="min-h-screen grid place-items-center text-zinc-400">Verificando sessão…</div>;
  return <div className="min-h-screen">
    <a href="#conteudo" className="sr-only focus:not-sr-only">Ir para conteúdo</a>
    <header className="sticky top-0 z-20 border-b border-[#2A2A2A] bg-[#0A0A0A]/95 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center gap-5 px-4 py-3">
        <strong className="mr-auto text-sm">Pages to RGB — Admin</strong>
        {[['/admin/processos','Processos'],['/admin/config','Configurações']].map(([href,label]) => <Link key={href} href={href} className={`text-sm ${path.startsWith(href) ? 'text-white' : 'text-zinc-400 hover:text-white'}`}>{label}</Link>)}
        <button onClick={logout} className="rounded-lg border border-zinc-700 px-3 py-2 text-xs hover:bg-zinc-800">Sair</button>
      </div>
    </header><main id="conteudo">{children}</main>
  </div>;
}
