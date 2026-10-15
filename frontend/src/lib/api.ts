export class ApiError extends Error {
  code: string;
  status: number;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

/** Address of the API server. Empty (the default) means "same address as this page", which is how the
 * single-container build and the dev proxy work. Set VITE_BACKEND_URL at build time (for example
 * https://resqnet-ai.onrender.com) when the website is hosted separately from the server. */
export const BACKEND_URL: string = ((import.meta.env.VITE_BACKEND_URL as string | undefined) ?? "").replace(/\/+$/, "");
export const apiUrl = (path: string) => BACKEND_URL + path;
export const wsUrl = (path: string) => (BACKEND_URL ? BACKEND_URL.replace(/^http/, "ws") : `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}`) + path;

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(apiUrl(path), {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "NETWORK", BACKEND_URL ? `Backend unreachable at ${BACKEND_URL}. A free Render server sleeps when idle; wait a minute and retry.` : "Backend unreachable — is the API server running on :8000?");
  }
  if (!res.ok) {
    let code = "HTTP_" + res.status;
    let message = res.statusText;
    try {
      const j = await res.json();
      code = j?.error?.code ?? (Array.isArray(j?.detail) ? "VALIDATION" : code);
      message = j?.error?.message ?? (Array.isArray(j?.detail) ? j.detail.map((d: any) => d.msg).join("; ") : message);
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, code, message);
  }
  return (await res.json()) as T;
}

export const api = {
  get: <T,>(p: string) => request<T>("GET", p),
  post: <T,>(p: string, b: unknown = {}) => request<T>("POST", p, b),
};
