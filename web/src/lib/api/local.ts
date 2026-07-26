// Cliente da API local (FastAPI em api/server.py) que serve os dados reais
// do Google Sheets. Base configuravel via VITE_API_URL.
import type { HydratePayload } from "../store";
import type { AppSettings, CalendarPost, Idea, Script } from "../mock-data";
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

/** Cria um agendamento real na aba Calendario do Sheets. */
export async function appendCalendarPost(post: Omit<CalendarPost, "id">): Promise<CalendarPost> {
  const response = await postJson<{ ok: boolean; post: CalendarPost }>(
    "/api/sheets/calendario",
    post,
  );
  return response.post;
}

/** Persiste reagendamento, publicacao e demais alteracoes do calendario. */
export async function saveCalendarPost(post: CalendarPost): Promise<CalendarPost> {
  const response = await requestJson<{ ok: boolean; post: CalendarPost }>(
    `/api/sheets/calendario/${encodeURIComponent(post.id)}`,
    { method: "PUT", body: JSON.stringify(post) },
  );
  return response.post;
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

export async function saveSettings(settings: AppSettings): Promise<AppSettings> {
  const response = await requestJson<{ ok: boolean; settings: AppSettings; updatedAt: string }>(
    "/api/settings",
    { method: "PUT", body: JSON.stringify(settings) },
  );
  return response.settings;
}

export async function huntTrends(): Promise<{ ok: boolean; added?: number; queries?: string[] }> {
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
  return (await res.json()) as { ok: boolean; added?: number; queries?: string[] };
}

export interface HeyGenCatalog {
  avatars: Array<{
    id: string;
    name: string;
    orientation: "portrait" | "landscape";
    groupId?: string | null;
    groupName?: string | null;
    previewImageUrl?: string | null;
  }>;
  voices: Array<{ id: string; name: string; gender: string }>;
  defaultAvatarId?: string | null;
  defaultVoiceId?: string | null;
}

export interface HeyGenAvatarGroup {
  id: string;
  name: string;
  gender?: string | null;
  looks_count: number;
  status?: "processing" | "pending_consent" | "failed" | "completed" | null;
  consent_status?: string | null;
  preview_image_url?: string | null;
  preview_video_url?: string | null;
  default_voice_id?: string | null;
  created_at: number;
}

export interface HeyGenAvatarLook {
  id: string;
  group_id: string;
  group_name: string;
  name: string;
  avatar_type?: string | null;
  gender?: string | null;
  status?: "processing" | "pending_consent" | "failed" | "completed" | null;
  preferred_orientation?: "portrait" | "landscape" | null;
  preview_image_url?: string | null;
  default_voice_id?: string | null;
  image_width?: number | null;
  image_height?: number | null;
}

export interface AvatarJob {
  id: string;
  name: string;
  creationType: "photo" | "digital_twin" | "prompt";
  status: string;
  groupId: string;
  avatarId?: string | null;
  voiceId?: string | null;
  voiceStatus?: string | null;
  consentUrl?: string | null;
  previewImageUrl?: string | null;
  previewVideoUrl?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface HeyGenStyle {
  style_id: string;
  name: string;
  aspect_ratio: "9:16" | "16:9" | string;
  tags: string[];
  thumbnail_url?: string | null;
  preview_video_url?: string | null;
}

export interface AvatarMediaPayload {
  name: string;
  mimeType: string;
  data: string;
}

export interface CreateAvatarPayload {
  name: string;
  creationType: "photo" | "digital_twin" | "prompt";
  appearancePrompt: string;
  media: AvatarMediaPayload[];
  cloneVoice: boolean;
  voiceSource?: "upload" | "video";
  voiceMedia?: AvatarMediaPayload;
  consentAccepted: boolean;
}

export async function fetchHeyGenCatalog(): Promise<HeyGenCatalog> {
  const res = await fetch(`${BASE}/api/heygen/catalog`);
  if (!res.ok)
    throw new Error(await errorDetail(res, "Nao foi possivel carregar avatares e vozes."));
  return (await res.json()) as HeyGenCatalog;
}

export async function fetchHeyGenAvatars(): Promise<{
  avatars: HeyGenAvatarGroup[];
  looks: HeyGenAvatarLook[];
  jobs: AvatarJob[];
}> {
  return requestJson("/api/heygen/avatars", { method: "GET" });
}

export async function fetchHeyGenStyles(tag = "cinematic"): Promise<{
  styles: HeyGenStyle[];
  tag: string;
}> {
  return requestJson(`/api/heygen/styles?tag=${encodeURIComponent(tag)}`, { method: "GET" });
}

export async function createHeyGenAvatar(payload: CreateAvatarPayload): Promise<AvatarJob> {
  const response = await postJson<{ ok: boolean; job: AvatarJob }>("/api/heygen/avatars", payload);
  return response.job;
}

export async function refreshHeyGenAvatar(jobId: string): Promise<AvatarJob> {
  const response = await postJson<{ ok: boolean; job: AvatarJob }>(
    `/api/heygen/avatars/${encodeURIComponent(jobId)}/refresh`,
    {},
  );
  return response.job;
}

export async function createHeyGenVideo(
  scriptId: string,
  selection: {
    avatarId?: string;
    voiceId?: string;
    orientation: "portrait" | "landscape";
    durationSeconds: 10 | 15 | 30 | 45 | 60;
    speechMode: "natural" | "fiel" | "direto";
    captions: boolean;
    optimizePronunciation: boolean;
    styleId?: string;
    forceNewVersion?: boolean;
    narrationText?: string;
    idempotencyKey?: string;
  },
): Promise<VideoJob> {
  const idempotencyKey =
    selection.idempotencyKey ??
    globalThis.crypto?.randomUUID?.() ??
    `video-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const res = await fetch(`${BASE}/api/videos`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scriptId, ...selection, idempotencyKey }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, "Nao foi possivel enviar ao HeyGen."));
  return ((await res.json()) as { job: VideoJob }).job;
}

export async function naturalizeScript(input: {
  text: string;
  medicalCautions: string;
  durationSeconds: 10 | 15 | 30 | 45 | 60;
}): Promise<string> {
  const response = await postJson<{ ok: boolean; text: string }>("/api/scripts/naturalize", input);
  return response.text;
}

export function videoDownloadUrl(jobId: string): string {
  return `${BASE}/api/videos/${encodeURIComponent(jobId)}/download`;
}

export interface CutClip {
  id?: string;
  title: string;
  start: number;
  end: number;
  duration?: number;
  score: number;
  hook: string;
  summary: string;
  cta: string;
  caption: string;
  cover: string;
  hashtags: string;
  reason: string;
  filename?: string;
  compliance?: PackCompliance;
}

export interface CutProject {
  id: string;
  status: "fila" | "processando" | "pronto" | "erro";
  progresso: number;
  etapa: string;
  sourceName: string;
  videoJobId?: string | null;
  uploadId?: string | null;
  youtubeUrl?: string | null;
  selectionMode?: "anthropic" | "local";
  settings: {
    clipCount: number;
    minDuration: number;
    maxDuration: number;
    durationMode?: "preset" | "auto";
    captions: boolean;
    layout: "fit" | "fill";
  };
  clips: CutClip[];
  erro?: string;
  criadoEm: string;
  atualizadoEm: string;
}

export async function uploadCutVideo(
  file: File,
): Promise<{ uploadId: string; filename: string; size: number }> {
  const res = await fetch(`${BASE}/api/cuts/uploads`, {
    method: "POST",
    headers: {
      "Content-Type": file.type || "video/mp4",
      "X-Filename": encodeURIComponent(file.name),
    },
    body: file,
  });
  if (!res.ok) throw new Error(await errorDetail(res, "Nao foi possivel enviar o video."));
  return (await res.json()) as { uploadId: string; filename: string; size: number };
}

export async function createCutProject(input: {
  requestId: string;
  videoJobId?: string;
  uploadId?: string;
  youtubeUrl?: string;
  sourceName?: string;
  clipCount: number;
  minDuration: number;
  maxDuration: number;
  durationMode: "preset" | "auto";
  captions: boolean;
  layout: "fit" | "fill";
}): Promise<CutProject> {
  const response = await postJson<{ ok: boolean; project: CutProject }>("/api/cuts", input);
  return response.project;
}

export async function fetchCutProjects(): Promise<CutProject[]> {
  const response = await requestJson<{ projects: CutProject[] }>("/api/cuts", { method: "GET" });
  return response.projects;
}

export async function fetchCutProject(projectId: string): Promise<CutProject> {
  const response = await requestJson<{ project: CutProject }>(
    `/api/cuts/${encodeURIComponent(projectId)}`,
    { method: "GET" },
  );
  return response.project;
}

export async function retryCutProject(projectId: string): Promise<CutProject> {
  const response = await postJson<{ ok: boolean; project: CutProject }>(
    `/api/cuts/${encodeURIComponent(projectId)}/retry`,
    {},
  );
  return response.project;
}

export function cutFileUrl(projectId: string, filename: string, download = false): string {
  return `${BASE}/api/cuts/${encodeURIComponent(projectId)}/files/${encodeURIComponent(filename)}${
    download ? "?download=true" : ""
  }`;
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
