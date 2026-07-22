// Cliente da API local (FastAPI em api/server.py) que serve os dados reais
// do Google Sheets. Base configuravel via VITE_API_URL.
import type { HydratePayload } from "../store";
import type { Idea, Script } from "../mock-data";

const BASE = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

export interface StatePayload extends HydratePayload {
  updatedAt?: string;
}

export async function fetchState(): Promise<StatePayload> {
  const res = await fetch(`${BASE}/api/state`);
  if (!res.ok) throw new Error(`API /api/state -> ${res.status}`);
  return (await res.json()) as StatePayload;
}

export async function refreshSnapshot(): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/api/refresh`, { method: "POST" });
  if (!res.ok) throw new Error(`API /api/refresh -> ${res.status}`);
  return (await res.json()) as { ok: boolean };
}

/** Grava o novo status de um item de volta no Google Sheets. */
export async function setSheetStatus(
  tab: "radar" | "ideias" | "roteiros",
  itemId: string,
  status: string,
): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/api/sheets/${tab}/${itemId}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) {
    let detail = `API set status -> ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* corpo nao-JSON */
    }
    throw new Error(detail);
  }
  return (await res.json()) as { ok: boolean };
}

async function postJson(path: string, body: unknown): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `API ${path} -> ${res.status}`;
    try {
      const b = (await res.json()) as { detail?: string };
      if (b.detail) detail = b.detail;
    } catch {
      /* corpo nao-JSON */
    }
    throw new Error(detail);
  }
  return (await res.json()) as { ok: boolean };
}

/** Persiste uma ideia gerada na aba Ideias do Sheets. */
export function appendIdea(idea: Idea): Promise<{ ok: boolean }> {
  return postJson("/api/sheets/ideias", idea);
}

/** Persiste um roteiro gerado na aba Roteiros do Sheets. */
export function appendScript(script: Script): Promise<{ ok: boolean }> {
  return postJson("/api/sheets/roteiros", script);
}

export async function huntTrends(): Promise<{ ok: boolean; added?: number }> {
  const res = await fetch(`${BASE}/api/trends/hunt`, { method: "POST" });
  if (!res.ok) {
    let detail = `API /api/trends/hunt -> ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* corpo nao-JSON */
    }
    throw new Error(detail);
  }
  return (await res.json()) as { ok: boolean; added?: number };
}
