const RAW_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

/** Backend base URL, trailing slash stripped. */
export const API_BASE = RAW_BASE.replace(/\/+$/, "");

function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

/** Derive the WebSocket origin from the HTTP base (http->ws, https->wss). */
export function wsUrl(path: string): string {
  const u = new URL(API_BASE);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  return `${u.origin}${path}`;
}

export type QueryValue = string | number | boolean | undefined | null;

export async function getJson<T>(
  path: string,
  params?: Record<string, QueryValue>,
): Promise<T> {
  const url = new URL(apiUrl(path));
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) {
        url.searchParams.set(key, String(value));
      }
    }
  }

  const res = await fetch(url.toString(), {
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}
