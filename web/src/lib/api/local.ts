// Cliente da API local (FastAPI em api/server.py) que serve os dados reais
// do Google Sheets. Base configuravel via VITE_API_URL.
import type { HydratePayload } from "../store";
import type { Idea, Script } from "../mock-data";
import type { VideoJob } from "../mock-data";

const BASE = import.meta.env.VITE_API_URL ?? "";

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
  tab: "radar" | "ideias" | "roteiros" | "calendario",
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

async function requestJson<T>(path: string, init: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
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
  return (await res.json()) as T;
}

async function postJson<T = { ok: boolean }>(path: string, body: unknown): Promise<T> {
  return requestJson<T>(path, { method: "POST", body: JSON.stringify(body) });
}

/** Persiste uma ideia gerada na aba Ideias do Sheets. */
export async function appendIdea(idea: Idea): Promise<Idea> {
  const response = await postJson<{ ok: boolean; idea: Idea }>("/api/sheets/ideias", idea);
  return response.idea;
}

/** Persiste um roteiro gerado na aba Roteiros do Sheets. */
export async function appendScript(script: Script): Promise<Script> {
  const response = await postJson<{ ok: boolean; script: Script }>("/api/sheets/roteiros", script);
  return response.script;
}

/** Atualiza o roteiro no Sheets e no snapshot usado para gerar o video. */
export async function saveScript(script: Script): Promise<Script> {
  const response = await requestJson<{ ok: boolean; script: Script }>(
    `/api/sheets/roteiros/${encodeURIComponent(script.id)}`,
    { method: "PUT", body: JSON.stringify(script) },
  );
  return response.script;
}

export interface GeneratedPack {
  carousel: Array<{ title: string; body: string }>;
  staticPost: { headline: string; subline: string };
  caption: string;
  stories: Array<{ title: string; body: string }>;
  checklist: string[];
}

export interface PackCompliance {
  ok: boolean;
  blocked: boolean;
  issues: string[];
}

/** Gera o pack de conteudo real via Claude (server-side) a partir de um roteiro. */
export async function generatePack(
  script: Script,
): Promise<{ pack: GeneratedPack; compliance: PackCompliance }> {
  const res = await fetch(`${BASE}/api/packs/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(script),
  });
  if (!res.ok) throw new Error(await errorDetail(res, "Nao foi possivel gerar o pack."));
  return (await res.json()) as { pack: GeneratedPack; compliance: PackCompliance };
}

export interface PackForExport {
  carousel: Array<{ title: string; body: string }>;
  staticPost: { headline: string; subline: string };
  caption: string;
  stories: Array<{ title: string; body: string }>;
  checklist: string[];
}

/** Salva o pack completo numa pasta local (content/packs/...). */
export async function exportPack(
  script: Script,
  pack: PackForExport,
): Promise<{ ok: boolean; relative: string; folder: string; files: number }> {
  const res = await fetch(`${BASE}/api/packs/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      titulo: script.titulo,
      tema: script.tema,
      categoria: script.categoria,
      risco: script.risco,
      formatoSugerido: script.formatoSugerido,
      pack,
    }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, "Nao foi possivel salvar o pack."));
  return (await res.json()) as {
    ok: boolean;
    relative: string;
    folder: string;
    files: number;
  };
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

export interface HeyGenCatalog {
  avatars: Array<{ id: string; name: string; orientation: "portrait" | "landscape" }>;
  voices: Array<{ id: string; name: string; gender: string }>;
  defaultAvatarId?: string | null;
  defaultVoiceId?: string | null;
}

export async function fetchHeyGenCatalog(): Promise<HeyGenCatalog> {
  const res = await fetch(`${BASE}/api/heygen/catalog`);
  if (!res.ok)
    throw new Error(await errorDetail(res, "Nao foi possivel carregar avatares e vozes."));
  return (await res.json()) as HeyGenCatalog;
}

export async function createHeyGenVideo(
  scriptId: string,
  selection: { avatarId?: string; voiceId?: string },
): Promise<VideoJob> {
  const res = await fetch(`${BASE}/api/videos`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scriptId, ...selection }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, "Nao foi possivel enviar ao HeyGen."));
  return ((await res.json()) as { job: VideoJob }).job;
}

export async function refreshHeyGenVideo(jobId: string): Promise<VideoJob> {
  const res = await fetch(`${BASE}/api/videos/${jobId}/refresh`, { method: "POST" });
  if (!res.ok) throw new Error(await errorDetail(res, "Nao foi possivel consultar o HeyGen."));
  return ((await res.json()) as { job: VideoJob }).job;
}

export interface AiCostProvider {
  id: string;
  name: string;
  description: string;
  status: "conectado" | "nao_conectado" | "indisponivel";
  currency: string | null;
  remainingBalance: number | null;
  trackedSpend: number | null;
  note: string;
}

export interface AiCosts {
  updatedAt: string;
  providers: AiCostProvider[];
}

export async function fetchAiCosts(): Promise<AiCosts> {
  const res = await fetch(`${BASE}/api/ai-costs`);
  if (!res.ok)
    throw new Error(await errorDetail(res, "Nao foi possivel consultar os custos de IA."));
  return (await res.json()) as AiCosts;
}

async function errorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string };
    return body.detail || fallback;
  } catch {
    return fallback;
  }
}
