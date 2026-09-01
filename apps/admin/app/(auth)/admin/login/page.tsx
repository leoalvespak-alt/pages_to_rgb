"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    const res = await fetch("/api/v1/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok && data.token) {
      router.push("/admin/processos");
    } else if (res.ok && data.authenticated) {
      const next = new URL(window.location.href).searchParams.get("next");
      router.push(next && next.startsWith("/admin/") ? next : "/admin/processos");
    } else {
      setError("Dados inválidos");
    }
    setLoading(false);
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0A0A0A] p-4">
      <div className="w-[360px] bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl p-6">
        <div className="text-red-500 text-2xl mb-2">🔒</div>
        <h1 className="text-lg font-semibold">Acesso ao Admin</h1>
        <p className="text-sm text-zinc-400 mb-6">Use a senha operacional configurada na API.</p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-xs text-zinc-400">Senha</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full mt-1 bg-[#2A2A2A] border border-zinc-700 rounded-lg px-3 py-2 text-sm"
              placeholder="••••••••"
              autoComplete="current-password"
              required
            />
          </div>
          {error && <p className="text-xs text-red-500">{error}</p>}
          <button type="submit" disabled={loading} className="w-full bg-[#C62828] hover:bg-[#B71C1C] rounded-lg py-2 text-sm font-medium disabled:opacity-50">
            {loading ? "..." : "Entrar"}
          </button>
        </form>
      </div>
    </div>
  );
}
