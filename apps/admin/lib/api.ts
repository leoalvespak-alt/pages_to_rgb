let csrfToken = "";

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function getMe(): Promise<{ authenticated: boolean; csrf_token: string }> {
  const res = await fetch("/api/v1/admin/me", { credentials: "include", cache: "no-store" });
  if (!res.ok) throw new ApiError(res.status, "Sessão inválida");
  const data = await res.json();
  csrfToken = data.csrf_token;
  return data;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method || "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && !csrfToken) await getMe();
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) headers.set("X-CSRF-Token", csrfToken);
  // S08.3: respeita sinal do chamador (polling cancelável); timeout interno só sem sinal externo.
  const external = init.signal;
  const controller = new AbortController();
  const timeout = external ? 0 : setTimeout(() => controller.abort(), 15000);
  if (external) external.addEventListener("abort", () => controller.abort(), { once: true });
  try {
    const res = await fetch(path, { ...init, headers, credentials: "include", cache: "no-store", signal: controller.signal });
    if (res.status === 401 && typeof window !== "undefined") {
      window.location.assign(`/admin/login?next=${encodeURIComponent(window.location.pathname)}`);
      throw new ApiError(401, "Sessão expirada");
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new ApiError(res.status, body.detail || body.message || `Erro HTTP ${res.status}`);
    }
    if (res.status === 204) return undefined as T;
    return await res.json() as T;
  } finally { if (timeout) clearTimeout(timeout); }
}
