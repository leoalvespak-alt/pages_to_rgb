"use client";

import { useEffect, useMemo, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";

type Device = {
  device_code: string;
  display_name: string;
  enabled: boolean;
  firmware_version: string | null;
  camera_capabilities_version: string | null;
  capture_source: string;
  last_seen_at: string | null;
  telemetry: Record<string, unknown>;
};

type Capabilities = {
  firmware_version: string;
  driver_version: string;
  available: Record<string, unknown>;
  protected: Record<string, unknown>;
  unavailable: Record<string, string>;
  feature_enabled: boolean;
  compatible: boolean;
  reason_code: string | null;
  message: string;
};

type Profile = {
  public_id: string;
  mode: "OCR" | "PHOTO";
  revision: number;
  capabilities_version: string;
  requested: Record<string, unknown>;
  effective: Record<string, unknown>;
  created_at: string;
  active: boolean;
};

type Command = {
  command_id: string;
  device_code: string;
  kind: "TEST" | "STOP";
  status: string;
  requested: Record<string, unknown>;
  effective: Record<string, unknown>;
  failure_reason: string | null;
};

type ProfileForm = {
  mode: "OCR" | "PHOTO";
  frame_count: number;
  esp_jpeg_quality: number;
  intra_frame_gap_ms: number;
  page_interval_ms: number;
};

const initialForm: ProfileForm = {
  mode: "OCR",
  frame_count: 2,
  esp_jpeg_quality: 10,
  intra_frame_gap_ms: 220,
  page_interval_ms: 5000,
};

function seenLabel(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "nunca";
}

export default function DevicesPage() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [deviceCode, setDeviceCode] = useState("");
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [form, setForm] = useState<ProfileForm>(initialForm);
  const [color, setColor] = useState("#00aaff");
  const [brightness, setBrightness] = useState(12);
  const [command, setCommand] = useState<Command | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function loadDevices(): Promise<void> {
    try {
      const result = await apiFetch<{ items: Device[] }>("/api/v1/admin/devices");
      setDevices(result.items);
      setDeviceCode((current) => current || result.items[0]?.device_code || "");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Falha ao carregar dispositivos");
    }
  }

  async function loadDetails(code: string): Promise<void> {
    if (!code) return;
    setError("");
    try {
      const [cap, revisionList] = await Promise.all([
        apiFetch<Capabilities>("/api/v1/admin/devices/" + encodeURIComponent(code) + "/camera-capabilities"),
        apiFetch<{ items: Profile[] }>("/api/v1/admin/camera-profiles?device_code=" + encodeURIComponent(code)),
      ]);
      setCapabilities(cap);
      setProfiles(revisionList.items);
    } catch (reason) {
      setCapabilities(null);
      setProfiles([]);
      setError(reason instanceof ApiError ? reason.message : "Falha ao carregar capabilities");
    }
  }

  useEffect(() => {
    void loadDevices();
    const timer = window.setInterval(() => void loadDevices(), 15000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    void loadDetails(deviceCode);
  }, [deviceCode]);

  const selected = useMemo(
    () => devices.find((item) => item.device_code === deviceCode) || null,
    [devices, deviceCode],
  );

  async function saveProfile(): Promise<void> {
    if (!deviceCode || !capabilities?.feature_enabled) return;
    setBusy(true);
    setError("");
    try {
      await apiFetch<Profile>("/api/v1/admin/camera-profiles", {
        method: "POST",
        body: JSON.stringify({ device_code: deviceCode, ...form }),
      });
      await loadDetails(deviceCode);
      setMessage("Nova revisão de perfil criada; revisões anteriores permanecem imutáveis.");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Falha ao criar perfil");
    } finally {
      setBusy(false);
    }
  }

  async function sendRgb(): Promise<void> {
    if (!deviceCode || !selected?.enabled) return;
    setBusy(true);
    setError("");
    try {
      const next = await apiFetch<Command>(
        "/api/v1/admin/devices/" + encodeURIComponent(deviceCode) + "/rgb-tests",
        {
          method: "POST",
          body: JSON.stringify({
            hex_color: color,
            brightness_percent: brightness,
            on_ms: 3000,
            off_ms: 5000,
            repeat_count: 1,
          }),
        },
      );
      setCommand(next);
      setMessage("Comando " + next.command_id + " criado; APPLIED só será mostrado após confirmação física.");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Falha ao enviar RGB");
    } finally {
      setBusy(false);
    }
  }

  async function refreshCommand(): Promise<void> {
    if (!deviceCode || !command) return;
    try {
      setCommand(
        await apiFetch<Command>(
          "/api/v1/admin/devices/" + encodeURIComponent(deviceCode) + "/rgb-tests/" + command.command_id,
        ),
      );
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Falha ao atualizar comando");
    }
  }

  async function stopRgb(): Promise<void> {
    if (!deviceCode || !command) return;
    setBusy(true);
    try {
      setCommand(
        await apiFetch<Command>(
          "/api/v1/admin/devices/" + encodeURIComponent(deviceCode) + "/rgb-tests/" + command.command_id + "/stop",
          { method: "POST" },
        ),
      );
      setMessage("STOP idempotente enviado; aguarde o evento OFF físico.");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Falha ao enviar STOP");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-4 md:p-6">
      <div>
        <p className="text-xs uppercase tracking-[0.2em] text-cyan-400">Operação física</p>
        <h1 className="mt-1 text-2xl font-semibold">Dispositivos, câmera e RGB</h1>
        <p className="mt-2 text-sm text-zinc-400">A tela mostra solicitado versus efetivo e nunca trata prévia como prova física.</p>
      </div>

      {error && <div className="rounded-lg border border-red-900 bg-red-950/40 p-3 text-sm text-red-200">{error}</div>}
      {message && <div className="rounded-lg border border-emerald-900 bg-emerald-950/40 p-3 text-sm text-emerald-200">{message}</div>}

      <section className="card space-y-3">
        <h2 className="font-medium">Seleção e heartbeat</h2>
        <select className="control w-full" value={deviceCode} onChange={(event) => setDeviceCode(event.target.value)}>
          <option value="">Selecione um dispositivo</option>
          {devices.map((item) => <option key={item.device_code} value={item.device_code}>{item.display_name} · {item.device_code}</option>)}
        </select>
        {selected && (
          <div className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div><span className="block text-xs text-zinc-500">Fonte</span>{selected.capture_source}</div>
            <div><span className="block text-xs text-zinc-500">Firmware</span>{selected.firmware_version || "desconhecida"}</div>
            <div><span className="block text-xs text-zinc-500">Último heartbeat</span>{seenLabel(selected.last_seen_at)}</div>
            <div><span className="block text-xs text-zinc-500">Estado</span>{selected.enabled ? "habilitado" : "desabilitado"}</div>
          </div>
        )}
        {selected && <pre className="overflow-auto rounded-lg bg-[#171717] p-3 text-xs text-zinc-400">telemetria: {JSON.stringify(selected.telemetry || {}, null, 2)}</pre>}
      </section>

      {deviceCode && capabilities && (
        <>
          <section className="card space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-medium">Capabilities e feature flags</h2>
              <span className={"rounded-full px-2 py-1 text-xs " + (capabilities.feature_enabled ? "bg-emerald-500/15 text-emerald-300" : "bg-amber-500/15 text-amber-300")}>{capabilities.feature_enabled ? "v2 habilitado" : "fail-closed"}</span>
            </div>
            <p className="text-sm text-zinc-300">{capabilities.message}</p>
            {capabilities.reason_code && <p className="text-xs text-amber-300">Motivo: {capabilities.reason_code}</p>}
            <div className="grid gap-3 text-sm sm:grid-cols-2">
              <pre className="overflow-auto rounded-lg bg-[#171717] p-3 text-xs">protegido: {JSON.stringify(capabilities.protected, null, 2)}</pre>
              <pre className="overflow-auto rounded-lg bg-[#171717] p-3 text-xs">disponível: {JSON.stringify(capabilities.available, null, 2)}</pre>
            </div>
            <details><summary className="cursor-pointer text-sm text-zinc-400">Controles indisponíveis</summary><pre className="mt-2 overflow-auto rounded-lg bg-[#171717] p-3 text-xs">{JSON.stringify(capabilities.unavailable, null, 2)}</pre></details>
          </section>

          <section className="card space-y-4">
            <h2 className="font-medium">Perfil versionado OCR/Foto</h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <label className="text-sm">Modo<select className="control mt-1 w-full" value={form.mode} onChange={(event) => setForm({ ...form, mode: event.target.value as ProfileForm["mode"] })}><option value="OCR">OCR</option><option value="PHOTO">Foto</option></select></label>
              <label className="text-sm">Frames<input className="control mt-1 w-full" type="number" min="1" max="3" value={form.frame_count} onChange={(event) => setForm({ ...form, frame_count: Number(event.target.value) })} /></label>
              <label className="text-sm">JPEG ESP<input className="control mt-1 w-full" type="number" min="8" max="12" value={form.esp_jpeg_quality} onChange={(event) => setForm({ ...form, esp_jpeg_quality: Number(event.target.value) })} /></label>
              <label className="text-sm">Gap entre frames<input className="control mt-1 w-full" type="number" min="180" max="300" value={form.intra_frame_gap_ms} onChange={(event) => setForm({ ...form, intra_frame_gap_ms: Number(event.target.value) })} /></label>
              <label className="text-sm">Intervalo página<input className="control mt-1 w-full" type="number" min="5000" value={form.page_interval_ms} onChange={(event) => setForm({ ...form, page_interval_ms: Number(event.target.value) })} /></label>
            </div>
            <button className="primary" disabled={busy || !capabilities.feature_enabled} onClick={() => void saveProfile()}>Criar revisão imutável</button>
            <div className="space-y-2">{profiles.map((item) => <div className="rounded-lg bg-[#242424] p-3 text-sm" key={item.public_id}><div className="flex flex-wrap justify-between gap-2"><span>{item.mode} · revisão {item.revision} · {item.capabilities_version}</span><span className="text-zinc-500">{item.active ? "ativa" : "histórica"}</span></div><pre className="mt-2 overflow-auto text-xs text-zinc-400">solicitado: {JSON.stringify(item.requested)}{"\n"}efetivo: {JSON.stringify(item.effective)}</pre></div>)}</div>
          </section>

          <section className="card space-y-4">
            <h2 className="font-medium">RGB físico e STOP</h2>
            <div className="flex flex-wrap items-end gap-3">
              <label className="text-sm">Cor<input className="mt-1 block h-10 w-20" type="color" value={color} onChange={(event) => setColor(event.target.value)} /></label>
              <label className="text-sm">Brilho %<input className="control mt-1 w-24" type="number" min="0" max="100" value={brightness} onChange={(event) => setBrightness(Number(event.target.value))} /></label>
              <button className="primary" disabled={busy || !selected?.enabled} onClick={() => void sendRgb()}>Enviar teste</button>
              <button className="secondary" disabled={busy || !command} onClick={() => void refreshCommand()}>Atualizar estado</button>
              <button className="secondary" disabled={busy || !command} onClick={() => void stopRgb()}>STOP / OFF</button>
            </div>
            {command && <pre className="overflow-auto rounded-lg bg-[#171717] p-3 text-xs">comando {command.command_id} · {command.kind} · {command.status}{"\n"}efetivo: {JSON.stringify(command.effective)}{command.failure_reason ? "\nfalha: " + command.failure_reason : ""}</pre>}
          </section>
        </>
      )}
    </div>
  );
}
