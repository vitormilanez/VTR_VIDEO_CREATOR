// Cliente da API local (FastAPI em api/server.py) que serve os dados reais
// do Google Sheets. Base configuravel via VITE_API_URL.
import type { HydratePayload } from "../store";
import type { AppSettings, CalendarPost, EditorialTone, Idea, Script, Trend } from "../mock-data";
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
      const b = (await res.json()) as { detail?: unknown };
      if (typeof b.detail === "string") {
        detail = b.detail;
      } else if (Array.isArray(b.detail)) {
        detail = b.detail
          .map((item) => {
            if (typeof item === "string") return item;
            if (item && typeof item === "object" && "msg" in item) {
              return String((item as { msg: unknown }).msg);
            }
            return JSON.stringify(item);
          })
          .filter(Boolean)
          .join(" ");
      } else if (b.detail) {
        detail = JSON.stringify(b.detail);
      }
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

/** Persiste uma tendencia cadastrada manualmente na aba Radar Tendencias do Sheets. */
export async function appendTrend(trend: Trend): Promise<Trend> {
  const response = await postJson<{ ok: boolean; trend: Trend }>("/api/sheets/radar", trend);
  return response.trend;
}

/** Persiste uma ideia gerada na aba Ideias do Sheets. */
export async function appendIdea(idea: Idea): Promise<Idea> {
  const response = await postJson<{ ok: boolean; idea: Idea }>("/api/sheets/ideias", idea);
  return response.idea;
}

/** Atualiza uma ideia existente no Sheets, preservando ID e vinculo com a tendencia. */
export async function saveIdea(idea: Idea): Promise<Idea> {
  const response = await requestJson<{ ok: boolean; idea: Idea }>(
    `/api/sheets/ideias/${encodeURIComponent(idea.id)}`,
    { method: "PUT", body: JSON.stringify(idea) },
  );
  return response.idea;
}

export interface ExpandIdeasInput {
  seed: string;
  quantity?: number;
  familia?: Idea["familia"];
  prioridade?: Idea["prioridade"];
  sourceUrl?: string | null;
}

/** Expande uma ideia livre em opcoes editoriais prontas para roteiro. */
export async function expandIdeas(input: ExpandIdeasInput): Promise<Idea[]> {
  const response = await postJson<{ ok: boolean; provider: "claude" | "fallback"; ideas: Idea[] }>(
    "/api/ideas/expand",
    input,
  );
  return response.ideas;
}

export interface CaptureHooksInput {
  durationSeconds: 10 | 15;
  trendId: string;
  titulo: string;
  subtema?: string | null;
  sinal?: string | null;
  dorPublico?: string | null;
  notas?: string | null;
  familia: Trend["familia"];
  prioridade: Trend["prioridade"];
  sourceUrl?: string | null;
  editorialTone: EditorialTone;
  outro: string;
  requireClaude?: boolean;
}

export interface CaptureHookVariant {
  variant: number;
  strategy: string;
  title: string;
  hook: string;
  turn: string;
  spokenText: string;
  wordCount: number;
  rationale: string;
  stopScore: number;
  profileScore: number;
  complianceNotes: string;
}

export interface CaptureHooksResult {
  provider: "claude" | "fallback";
  analysis: {
    capturePotential: number;
    audienceReflex: string;
    recommendedAngle: string;
    riskNotes: string[];
  };
  variants: CaptureHookVariant[];
}

/** Uma chamada ao Claude avalia a tendencia e devolve tres testes de captura de 10s ou 15s. */
export async function generateCaptureHooks(input: CaptureHooksInput): Promise<CaptureHooksResult> {
  const response = await postJson<{ ok: boolean } & CaptureHooksResult>(
    "/api/trends/capture-hooks",
    input,
  );
  return {
    provider: response.provider,
    analysis: response.analysis,
    variants: response.variants,
  };
}

export interface TrendSourceSummary {
  summary: string;
  keyPoints: string[];
  provider: "claude" | "fallback";
}

/** Le e resume a fonte somente quando o usuario abre o preview; o backend mantém cache por URL. */
export async function summarizeTrendSource(
  title: string,
  sourceUrl: string,
): Promise<TrendSourceSummary> {
  return postJson<TrendSourceSummary>("/api/trends/summarize", { title, sourceUrl });
}

export interface ArticleIdeasInput {
  article: string;
  sourceUrl?: string | null;
  quantity?: number;
  familia?: Idea["familia"];
  prioridade?: Idea["prioridade"];
}

export interface ArticleAnalysis {
  tituloArtigo: string;
  achadoPrincipal: string;
  tipoEstudo: string;
  populacao: string;
  amostra: string;
  seguimento: string;
  numerosChave: string[];
  limitacoes: string[];
  podeFalar: string[];
  naoPodeFalar: string[];
}

export interface ArticleIdeasResult {
  provider: "claude" | "fallback";
  analysis: ArticleAnalysis;
  ideas: Idea[];
}

/** Analisa artigo cientifico e gera ideias editoriais com limites de compliance. */
export async function analyzeArticle(input: ArticleIdeasInput): Promise<ArticleIdeasResult> {
  const response = await postJson<{ ok: boolean } & ArticleIdeasResult>(
    "/api/articles/analyze",
    input,
  );
  return {
    provider: response.provider,
    analysis: response.analysis,
    ideas: response.ideas,
  };
}

export interface GenerateScriptInput {
  idea: {
    titulo: string;
    hook?: string;
    angulo?: string;
    tipo?: string | null;
    publicoDor?: string | null;
    cta?: string;
    familia?: Idea["familia"];
    observacaoCompliance?: string;
    prioridade?: Idea["prioridade"];
    linkOrigem?: string | null;
  };
  articleAnalysis?: ArticleAnalysis | null;
  editorialTone: EditorialTone;
  durationSeconds?: 10 | 15 | 30 | 45 | 60;
  outro?: string;
  requireClaude?: boolean;
}

export interface GeneratedScriptText {
  titulo: string;
  hook: string;
  dorConflito: string;
  explicacaoSimples: string;
  virada: string;
  cta: string;
  cuidadosMedicos: string;
  textoFalado: string;
}

/**
 * Chamada paga UNICA ao Claude: gera roteiro estruturado + texto falado completo
 * a partir de uma ideia ja escolhida e do tom editorial ja definido pelo usuario.
 * Nunca chame esta funcao tres vezes (uma por tom) para a mesma ideia.
 */
export async function generateScript(
  input: GenerateScriptInput,
): Promise<{ provider: "claude" | "fallback"; script: GeneratedScriptText }> {
  const response = await postJson<{
    ok: boolean;
    provider: "claude" | "fallback";
    script: GeneratedScriptText;
  }>("/api/scripts/generate", input);
  return { provider: response.provider, script: response.script };
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
  designDirection?: "editorial_premium" | "medical_modern" | "dark_provocative" | "human_lifestyle";
  carousel: PackSlide[];
  staticPost: {
    headline: string;
    subline: string;
    layout?: PackLayout;
    visualIntent?: PackVisualIntent;
    background?: PackBackground;
    avatar?: PackAvatarPlan;
    photoAsset?: Omit<PackPhotoAsset, "url"> | null;
  };
  caption: string;
  stories: PackSlide[];
  checklist: string[];
  sourceScriptId?: string | null;
  sourceAvatarId?: string | null;
  avatarAsset?: {
    avatarId: string;
    avatarName: string;
    cachedAssetPath: string;
  } | null;
  designPlan?: Record<string, unknown> | null;
  updatedAt?: string | null;
}

export type PackLayout =
  | "hero_avatar"
  | "avatar_split"
  | "big_statement"
  | "myth_fact"
  | "number_stat"
  | "three_points"
  | "quote_card"
  | "editorial_photo"
  | "minimal_explainer"
  | "cta_avatar";

export type PackVisualIntent =
  "provocative" | "educational" | "reassuring" | "contrast" | "authority" | "action";

export type PackBackground =
  | "dark_gradient"
  | "clinical_light"
  | "teal_soft"
  | "editorial_ink"
  | "warm_neutral"
  | "data_panel";

export interface PackAvatarPlan {
  show: boolean;
  position: "left" | "right" | "center" | "none";
  crop: "head" | "waist" | "full";
  scale: number;
}

export interface PackPhotoAsset {
  id: string;
  name: string;
  cachedAssetPath: string;
  url?: string;
}

export interface PackSlide {
  title: string;
  body: string;
  layout?: PackLayout;
  visualIntent?: PackVisualIntent;
  highlight?: string;
  avatar?: PackAvatarPlan;
  background?: PackBackground;
  photoAsset?: Omit<PackPhotoAsset, "url"> | null;
}

export interface ProductionProfile {
  scriptId: string;
  avatarId: string;
  voiceId: string;
  speechMode: "natural" | "fiel" | "direto" | "enfatico";
  generationMode: "direct" | "video_agent";
  updatedAt?: string;
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
    body: JSON.stringify({ ...script, scriptId: script.id }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, "Nao foi possivel gerar o pack."));
  return (await res.json()) as { pack: GeneratedPack; compliance: PackCompliance };
}

export async function fetchPack(scriptId: string): Promise<{
  pack: GeneratedPack | null;
  productionProfile: ProductionProfile | null;
  outdatedAvatar: boolean;
}> {
  const response = await requestJson<{
    ok: boolean;
    pack: GeneratedPack | null;
    productionProfile: ProductionProfile | null;
    outdatedAvatar: boolean;
  }>(`/api/packs/${encodeURIComponent(scriptId)}`, { method: "GET" });
  return {
    pack: response.pack,
    productionProfile: response.productionProfile,
    outdatedAvatar: response.outdatedAvatar,
  };
}

export async function refreshPackAvatar(scriptId: string): Promise<{
  pack: GeneratedPack;
  compliance: PackCompliance;
  productionProfile: ProductionProfile | null;
  outdatedAvatar: boolean;
}> {
  const response = await requestJson<{
    ok: boolean;
    pack: GeneratedPack;
    compliance: PackCompliance;
    productionProfile: ProductionProfile | null;
    outdatedAvatar: boolean;
  }>(`/api/packs/${encodeURIComponent(scriptId)}/refresh-avatar`, { method: "POST" });
  return response;
}

/** Salva o modelo visual escolhido manualmente para um slide do carrossel. */
export async function updatePackCarouselLayout(
  scriptId: string,
  slideIndex: number,
  layout: PackLayout,
): Promise<{ pack: GeneratedPack; compliance: PackCompliance }> {
  const response = await requestJson<{
    ok: boolean;
    pack: GeneratedPack;
    compliance: PackCompliance;
  }>(`/api/packs/${encodeURIComponent(scriptId)}/carousel/${slideIndex}/layout`, {
    method: "PUT",
    body: JSON.stringify({ layout }),
  });
  return { pack: response.pack, compliance: response.compliance };
}

export async function fetchPackPhotoAssets(): Promise<PackPhotoAsset[]> {
  const response = await requestJson<{ ok: boolean; assets: PackPhotoAsset[] }>(
    "/api/packs/photo-assets",
    { method: "GET" },
  );
  return response.assets;
}

export async function updatePackCarouselPhoto(
  scriptId: string,
  slideIndex: number,
  photoAssetId: string | null,
): Promise<{ pack: GeneratedPack; compliance: PackCompliance }> {
  const response = await requestJson<{
    ok: boolean;
    pack: GeneratedPack;
    compliance: PackCompliance;
  }>(`/api/packs/${encodeURIComponent(scriptId)}/carousel/${slideIndex}/photo`, {
    method: "PUT",
    body: JSON.stringify({ photoAssetId }),
  });
  return { pack: response.pack, compliance: response.compliance };
}

export interface PackForExport {
  designDirection?: GeneratedPack["designDirection"];
  carousel: PackSlide[];
  staticPost: GeneratedPack["staticPost"];
  caption: string;
  stories: PackSlide[];
  checklist: string[];
  sourceScriptId?: string | null;
  sourceAvatarId?: string | null;
  avatarAsset?: GeneratedPack["avatarAsset"];
  designPlan?: GeneratedPack["designPlan"];
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
      scriptId: script.id,
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

export async function fetchProductionProfile(scriptId: string): Promise<ProductionProfile | null> {
  const response = await requestJson<{ ok: boolean; profile: ProductionProfile | null }>(
    `/api/scripts/${encodeURIComponent(scriptId)}/production-profile`,
    { method: "GET" },
  );
  return response.profile;
}

export async function saveProductionProfile(
  scriptId: string,
  profile: Omit<ProductionProfile, "scriptId" | "updatedAt">,
): Promise<ProductionProfile> {
  const response = await requestJson<{ ok: boolean; profile: ProductionProfile }>(
    `/api/scripts/${encodeURIComponent(scriptId)}/production-profile`,
    { method: "PUT", body: JSON.stringify(profile) },
  );
  return response.profile;
}

export async function saveSettings(settings: AppSettings): Promise<AppSettings> {
  const response = await requestJson<{ ok: boolean; settings: AppSettings; updatedAt: string }>(
    "/api/settings",
    { method: "PUT", body: JSON.stringify(settings) },
  );
  return response.settings;
}

export interface HuntTrendsResult {
  ok: boolean;
  partial?: boolean;
  added?: number;
  queries?: string[];
  failedStep?: string;
  detail?: string;
}

export async function huntTrends(): Promise<HuntTrendsResult> {
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
  return (await res.json()) as HuntTrendsResult;
}

export interface HeyGenCatalog {
  avatars: Array<{
    id: string;
    name: string;
    type?: string | null;
    orientation: "portrait" | "landscape";
    status?: string | null;
    groupId?: string | null;
    groupName?: string | null;
    previewImageUrl?: string | null;
    previewVideoUrl?: string | null;
    defaultVoiceId?: string | null;
    supportsDirectAvatar?: boolean;
    supportsVideoAgent?: boolean;
  }>;
  voices: Array<{ id: string; name: string; gender: string }>;
  defaultAvatarId?: string | null;
  defaultVoiceId?: string | null;
  speechPresets?: Record<string, { speed: number; pitch: number; volume: number; locale: string }>;
  generationModes?: Array<"direct" | "video_agent">;
  directDurations?: Array<10 | 15 | 30 | 45 | 60>;
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
  /** true quando a HeyGen estava indisponivel e a lista veio do cache local. */
  fromCache?: boolean;
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

function stableProductionKey(
  prefix: "video" | "preview",
  configuration: Record<string, unknown>,
): string {
  const source = JSON.stringify(
    Object.keys(configuration)
      .sort()
      .reduce<Record<string, unknown>>((result, key) => {
        result[key] = configuration[key] ?? null;
        return result;
      }, {}),
  );
  let hash = 0x811c9dc5;
  for (let index = 0; index < source.length; index += 1) {
    hash ^= source.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return `${prefix}:${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

function newVersionKey(baseKey: string): string {
  const nonce =
    globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${baseKey}:version:${nonce}`;
}

export async function createHeyGenVideo(
  scriptId: string,
  selection: {
    avatarId?: string;
    voiceId?: string;
    orientation: "portrait" | "landscape";
    durationSeconds: 10 | 15 | 30 | 45 | 60;
    speechMode: "natural" | "fiel" | "direto" | "enfatico";
    generationMode: "direct" | "video_agent";
    ctaMode?: "auto" | "manual" | "none" | "visual";
    captions: boolean;
    optimizePronunciation: boolean;
    styleId?: string;
    forceNewVersion?: boolean;
    narrationText?: string;
    displayText?: string;
    spokenText?: string;
    outroText?: string;
    idempotencyKey?: string;
  },
): Promise<VideoJob> {
  const baseKey = stableProductionKey("video", {
    scriptId,
    ...selection,
    idempotencyKey: undefined,
  });
  const idempotencyKey =
    selection.idempotencyKey ?? (selection.forceNewVersion ? newVersionKey(baseKey) : baseKey);
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
  outro: string;
  ctaMode?: "auto" | "manual" | "none" | "visual";
  manualCta?: string;
  recentCtas?: string[];
}): Promise<{
  text: string;
  displayText: string;
  spokenText: string;
  tone: string;
  pace: string;
  emotion: string;
  emphasisWords: string[];
  pauseAfterSentencesMs: number[];
  recommendedVoiceSpeed: number;
  recommendedSpeechMode: "natural" | "direto" | "enfatico" | "fiel";
  cta: string;
}> {
  const response = await postJson<{
    ok: boolean;
    text: string;
    displayText: string;
    spokenText: string;
    tone: string;
    pace: string;
    emotion: string;
    emphasisWords: string[];
    pauseAfterSentencesMs: number[];
    recommendedVoiceSpeed: number;
    recommendedSpeechMode: "natural" | "direto" | "enfatico" | "fiel";
    cta: string;
  }>("/api/scripts/naturalize", input);
  return response;
}

export async function createHeyGenPreview(
  scriptId: string,
  selection: {
    avatarId: string;
    voiceId: string;
    orientation: "portrait" | "landscape";
    speechMode: "natural" | "fiel" | "direto" | "enfatico";
    captions: boolean;
    optimizePronunciation: boolean;
    displayText: string;
    spokenText?: string;
    idempotencyKey?: string;
  },
): Promise<VideoJob> {
  const idempotencyKey =
    selection.idempotencyKey ??
    stableProductionKey("preview", {
      scriptId,
      ...selection,
      generationMode: "direct",
      idempotencyKey: undefined,
    });
  const res = await fetch(`${BASE}/api/videos/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scriptId, ...selection, generationMode: "direct", idempotencyKey }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, "Nao foi possivel gerar a previa."));
  return ((await res.json()) as { job: VideoJob }).job;
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
  status: "fila" | "processando" | "pronto" | "erro" | "cancelado";
  progresso: number;
  etapa: string;
  sourceName: string;
  videoJobId?: string | null;
  uploadId?: string | null;
  youtubeUrl?: string | null;
  selectionMode?: "anthropic" | "local";
  settings: {
    clipCount: number | null;
    minDuration: number;
    maxDuration: number;
    durationMode?: "preset" | "auto";
    analysisStartSeconds?: number;
    analysisEndSeconds?: number | null;
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
  clipCount: number | null;
  minDuration: number;
  maxDuration: number;
  durationMode: "preset" | "auto";
  analysisStartSeconds: number;
  analysisEndSeconds: number | null;
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

export async function cancelCutProject(projectId: string): Promise<CutProject> {
  const response = await postJson<{ ok: boolean; project: CutProject }>(
    `/api/cuts/${encodeURIComponent(projectId)}/cancel`,
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
  calls?: number;
  inputTokens?: number;
  outputTokens?: number;
  cacheReadTokens?: number;
  cacheWriteTokens?: number;
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

export interface InstagramStatus {
  configured: boolean;
  connected: boolean;
  account: {
    id: string;
    username?: string;
    name?: string;
    profilePictureUrl?: string;
    followersCount?: number;
    mediaCount?: number;
  } | null;
  detail: string;
}

export interface InstagramPublication {
  containerId: string;
  mediaId: string;
  mediaType: "REELS" | "STORIES";
  publishedAt: string;
}

export async function fetchInstagramStatus(): Promise<InstagramStatus> {
  return requestJson<InstagramStatus>("/api/instagram/status", { method: "GET" });
}

export async function publishVideoToInstagram(input: {
  videoJobId: string;
  mediaType: "REELS" | "STORIES";
  caption?: string;
  shareToFeed?: boolean;
}): Promise<InstagramPublication> {
  const response = await postJson<{ ok: boolean; publication: InstagramPublication }>(
    "/api/instagram/publish",
    input,
  );
  return response.publication;
}

async function errorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string };
    return body.detail || fallback;
  } catch {
    return fallback;
  }
}
