"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

type DiagState = {
  diagnostic_id: string; device_code: string; gateway_code: string | null;
  mode: "PHOTO" | "CLIP" | "PREVIEW"; status: string;
  requested_profile: { resolution: string; jpeg_quality: number } | null;
  effective_profile: { resolution: string; jpeg_quality: number } | null;
  origin: string; expires_at: string | null; reason: string | null;
  counters: { received_frames: number; bytes: number; last_frame_index: number | null };
};
type Latest = {
  diagnostic_id: string; status: string;
  frame: { frame_index: number; sequence: number; sha256: string;
    age_s: number | null; stale: boolean; stale_message: string | null;
    effective_fps: number } | null;
};
type Assets = {
  diagnostic_id: string; mode: string; status: string;
  photos: { frame_index: number; sha256: string; bytes: number;
    width: number | null; height: number | null }[];
  clips: { mp4_key: string; duration_s: number | null; fps: number | null }[];
  page: number; limit: number; total: number;
};

const TERMINAL = new Set(["COMPLETED", "FAILED", "EXPIRED"]);

export default function CameraTestPage() {
  const [device, setDevice] = useState("CAM-001");
  const [diag, setDiag] = useState<DiagState | null>(null);
  const [latest, setLatest] = useState<Latest | null>(null);
  const [assets, setAssets] = useState<Assets | null>(null);
  const [imgSeq, setImgSeq] = useState(0);
  const [fit, setFit] = useState(true);
  const [compare, setCompare] = useState<number[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const lastSeq = useRef(-1);
  const visible = useRef(true);

  useEffect(() => {
    const onVis = () => {
      visible.current = !document.hidden;
      if (document.hidden && diag && !TERMINAL.has(diag.status)) {
        // Aba oculta: para polling/renovação; STOP best-effort (segurança = prazo local).
        void apiFetch(`/api/v1/admin/camera-diagnostics/${diag.diagnostic_id}/stop`, { method: "POST" }).catch(() => {});
      }
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, [diag]);

  const loadState = useCallback(async (id: string, signal?: AbortSignal) => {
    const s = await apiFetch<DiagState>(`/api/v1/admin/camera-diagnostics/${id}`, { signal });
    setDiag(s);
    return s;
  }, []);

  // Prévia: metadados ~500 ms só com tela visível+ativa; imagem só se índice mudou; sem sobreposição.
  useEffect(() => {
    if (!diag || diag.mode !== "PREVIEW" || TERMINAL.has(diag.status)) return;
    const ctrl = new AbortController();
    const t = setInterval(async () => {
      if (!visible.current || pending.current) return;
      pending.current = true;
      try {
        const l = await apiFetch<Latest>(
          `/api/v1/admin/camera-diagnostics/${diag.diagnostic_id}/latest`,
          { signal: ctrl.signal },
        );
        setLatest(l);
        if (l.frame && l.frame.sequence !== lastSeq.current) {
          lastSeq.current = l.frame.sequence;
          setImgSeq((n) => n + 1);
        }
      } catch (e) {
        if (!(e instanceof DOMException)) setError(e instanceof ApiError ? e.message : "Falha na prévia");
      } finally {
        pending.current = false;
      }
    }, 500);
    return () => { ctrl.abort(); clearInterval(t); };
  }, [diag]);

  async function start(mode: "PHOTO" | "CLIP" | "PREVIEW") {
    setBusy(true); setError("");
    try {
      const s = await apiFetch<DiagState>("/api/v1/admin/camera-diagnostics", {
        method: "POST",
        body: JSON.stringify({
          device_code: device,
          mode,
          profile: mode === "PREVIEW" ? { resolution: "VGA", jpeg_quality: 24 } : { resolution: "SVGA", jpeg_quality: 18 },
          duration_s: mode === "CLIP" ? 10 : mode === "PREVIEW" ? 60 : undefined,
        }),
      });
      lastSeq.current = -1;
      setDiag(s); setLatest(null); setAssets(null);
      const full = await loadState(s.diagnostic_id);
      if (mode !== "PREVIEW") {
        // Foto/clipe: consulta estado + galeria (paginada) após estabilizar.
        setTimeout(() => { void loadState(full.diagnostic_id).catch(() => {}); void loadAssets(full.diagnostic_id, 1).catch(() => {}); }, 4000);
      }
    } catch (e) {
      setError(e instanceof ApiError ? `Falha (${e.status}): ${e.message}` : "Falha ao iniciar");
    } finally { setBusy(false); }
  }

  async function stop() {
    if (!diag) return;
    setBusy(true);
    try {
      await apiFetch(`/api/v1/admin/camera-diagnostics/${diag.diagnostic_id}/stop`, { method: "POST" });
      await loadState(diag.diagnostic_id);
      if (diag.mode !== "PREVIEW") await loadAssets(diag.diagnostic_id, 1);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Falha ao parar");
    } finally { setBusy(false); }
  }

  async function loadAssets(id: string, page: number) {
    const a = await apiFetch<Assets>(`/api/v1/admin/camera-diagnostics/${id}/assets?page=${page}&limit=20`);
    setAssets(a);
  }

  const imgUrl = diag && latest?.frame
    ? `/api/v1/admin/camera-diagnostics/${diag.diagnostic_id}/latest.jpg?seq=${imgSeq}`
    : null;
  const stale = latest?.frame?.stale;
  const live = diag?.mode === "PREVIEW" && diag && !TERMINAL.has(diag.status) && !stale;

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-4 md:p-6">
      <header className="card">
        <h1 className="text-lg font-semibold">Teste de câmera (ESP física)</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Origem: câmera física da ESP via gateway Android. Prévia de baixa taxa (alvo 2 fps, VGA);
          vídeo = MP4 montado no servidor a partir de JPEGs reais (sem áudio). Imagem antiga repetida
          nunca é apresentada como ao vivo: após 5 s sem novidade, o indicador sai do verde.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <label className="text-sm text-zinc-400">Dispositivo
            <input value={device} onChange={(e) => setDevice(e.target.value.toUpperCase())}
              className="ml-2 w-32 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 font-mono text-sm" />
          </label>
          <button disabled={busy} onClick={() => start("PHOTO")} className="primary">Tirar foto</button>
          <button disabled={busy} onClick={() => start("CLIP")} className="primary">Gravar 10 segundos</button>
          <button disabled={busy} onClick={() => start("PREVIEW")} className="primary">Ver ao vivo</button>
          <button disabled={busy || !diag} onClick={stop} className="secondary">Parar</button>
        </div>
        {diag && (
          <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-lg bg-[#242424] p-3"><dt className="text-xs text-zinc-500">Estado</dt><dd>{diag.status} • {diag.mode}</dd></div>
            <div className="rounded-lg bg-[#242424] p-3"><dt className="text-xs text-zinc-500">Gateway</dt><dd>{diag.gateway_code ?? "—"} {diag.gateway_code ? "(online)" : "(offline)"}</dd></div>
            <div className="rounded-lg bg-[#242424] p-3"><dt className="text-xs text-zinc-500">Perfil efetivo</dt><dd>{diag.effective_profile ? `${diag.effective_profile.resolution} q${diag.effective_profile.jpeg_quality}` : `${diag.requested_profile?.resolution} q${diag.requested_profile?.jpeg_quality} (solicitado)`}</dd></div>
            <div className="rounded-lg bg-[#242424] p-3"><dt className="text-xs text-zinc-500">Recebidos</dt><dd>{diag.counters.received_frames} frames • {(diag.counters.bytes / 1024).toFixed(0)} KiB</dd></div>
          </dl>
        )}
      </header>

      {error && <div role="alert" className="rounded-lg border border-red-900 bg-red-950/40 p-3 text-red-300">{error}</div>}

      {diag?.mode === "PREVIEW" && (
        <section className="card space-y-3">
          <div className="flex items-center gap-3">
            <span className={`inline-block h-3 w-3 rounded-full ${live ? "bg-green-500" : "bg-zinc-600"}`} aria-label={live ? "ao vivo" : "desatualizado"} />
            <strong>{live ? "Ao vivo" : stale ? "Imagem desatualizada" : diag.status}</strong>
            {latest?.frame && (
              <span className="text-sm text-zinc-400">
                idade {latest.frame.age_s ?? "?"} s • {latest.frame.effective_fps} fps efetivos • frame #{latest.frame.frame_index}
              </span>
            )}
          </div>
          {imgUrl && latest?.frame ? (
            // JPEG como imagem (nunca base64 em JSON); mesma origem, sem segredos na URL.
            // eslint-disable-next-line @next/next/no-img-element
            <img key={imgSeq} src={imgUrl} alt={`Prévia ${diag.device_code} frame ${latest.frame.frame_index}`}
              className={fit ? "max-h-[60vh] w-full object-contain" : "w-full"} />
          ) : (
            <p className="text-zinc-500">Aguardando primeiro frame… (ESP acordada + gateway com rede local)</p>
          )}
          {stale && <p className="text-sm text-amber-300">Sem novidade há mais de 5 s — verifique posição, luz e rede; não é webcam de 30 fps.</p>}
        </section>
      )}

      {diag && diag.mode !== "PREVIEW" && (
        <section className="card space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-semibold">Galeria (paginada)</h2>
            <button onClick={() => loadAssets(diag.diagnostic_id, 1)} className="secondary">Atualizar</button>
            <label className="ml-auto text-sm"><input type="checkbox" checked={fit} onChange={(e) => setFit(e.target.checked)} /> Ajustar à tela</label>
          </div>
          {assets?.photos.length ? (
            <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-4">
              {assets.photos.map((p) => (
                <article key={p.frame_index} className="rounded-lg bg-[#242424] p-3">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={`/api/v1/admin/camera-diagnostics/${diag.diagnostic_id}/frames/${p.frame_index}.jpg?seq=${imgSeq}`}
                    alt={`Foto ${p.frame_index}`} className={fit ? "max-h-48 w-full object-contain" : "w-full"} loading="lazy" />
                  <p className="mt-2 text-xs">#{p.frame_index} • {p.width ?? "?"}x{p.height ?? "?"} • {(p.bytes / 1024).toFixed(0)} KiB</p>
                  <p className="truncate font-mono text-[10px] text-zinc-500">{p.sha256}</p>
                  <div className="mt-2 flex gap-2">
                    <a className="secondary" href={`/api/v1/admin/camera-diagnostics/${diag.diagnostic_id}/frames/${p.frame_index}.jpg`} download={`diag_${diag.diagnostic_id}_${p.frame_index}.jpg`}>Download original</a>
                    <button className="secondary" onClick={() => setCompare((c) => c.includes(p.frame_index) ? c.filter((i) => i !== p.frame_index) : [...c.slice(-1), p.frame_index])}>Comparar</button>
                  </div>
                </article>
              ))}
            </div>
          ) : <p className="text-zinc-500">Sem fotos ainda — aguarde a ESP enviar e clique em Atualizar.</p>}
          {compare.length === 2 && assets && (
            <p className="text-sm text-zinc-300">
              Comparação #{compare[0]} × #{compare[1]}:{" "}
              {assets.photos.filter((p) => compare.includes(p.frame_index)).map((p) => `#${p.frame_index} ${p.width}x${p.height} ${(p.bytes / 1024).toFixed(0)}KiB ${p.sha256.slice(0, 12)}…`).join("  ×  ")}
            </p>
          )}
          {assets?.clips.length ? assets.clips.map((c) => (
            <div key={c.mp4_key} className="space-y-2">
              <p className="text-sm text-zinc-300">Clipe: {c.duration_s?.toFixed(1)} s • {c.fps?.toFixed(2)} fps reais • sem áudio</p>
              <video controls playsInline preload="metadata" className="w-full max-h-[60vh] bg-black">
                <source src={`/api/v1/admin/camera-diagnostics/${diag.diagnostic_id}/clip.mp4`} type="video/mp4" />
              </video>
              <p className="text-xs text-zinc-500">MP4 reencodado serve para sequência temporal; nitidez fina avalia-se nas fotos originais (hash idêntico).</p>
            </div>
          )) : null}
          {assets && <p className="text-xs text-zinc-500">Total {assets.total} • pág. {assets.page}</p>}
        </section>
      )}

      {!diag && (
        <section className="card text-sm text-zinc-400">
          <p>Abra esta página apenas no dispositivo de teste com a flag ligada. Abrir o painel não inicia a câmera.</p>
          <p className="mt-1">Se a ESP estiver em deep sleep: “dispositivo indisponível; ative o modo de teste no gateway e acorde a placa pelo procedimento normal”.</p>
        </section>
      )}
    </div>
  );
}
