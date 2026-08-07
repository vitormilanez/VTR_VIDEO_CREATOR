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
  schemaVersion?: "institute-carousel-v1" | string;
  designDirection?: "institute_carousel_v1" | string;
  carousel: PackSlide[];
  slides?: PackSlide[];
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
  hashtags?: string[];
  stories: PackSlide[];
  checklist: string[];
  sourceScriptId?: string | null;
  sourceAvatarId?: string | null;
  sourceAvatarSetId?: string | null;
  sourcePrimaryAvatarId?: string | null;
  sourceIdentityKey?: string | null;
  packContextVersion?: string | null;
  avatarAsset?: {
    avatarId: string;
    avatarName: string;
    cachedAssetPath: string;
  } | null;
  designPlan?: Record<string, unknown> | null;
  updatedAt?: string | null;
}

export type PackLayout =
  | "hero_photo"
  | "photo_split"
  | "big_statement"
  | "question"
  | "myth_fact"
  | "number_stat"
  | "three_points"
  | "explainer"
  | "doctor_quote"
  | "photo_overlay"
  | "do_dont"
  | "cta_photo";

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
  description?: string;
  cachedAssetPath: string;
  facePointX?: number;
  facePointY?: number;
  brightness?: number;
  url?: string;
}

export interface PackSlideItem {
  title: string;
  text: string;
}

export interface PackSlideFields {
  eyebrow: string;
  headline: string;
  subheadline: string;
  body: string;
  statistic: string;
  item1: PackSlideItem;
  item2: PackSlideItem;
  item3: PackSlideItem;
  quote: string;
  cta: string;
  footer: string;
  caption: string;
  disclaimer: string;
  photoId: string;
}

export interface PackSlide {
  layoutId?: PackLayout;
  variant?: string;
  fields?: PackSlideFields;
  title?: string;
  body?: string;
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
  avatarMode?: "single" | "set";
  avatarSetId?: string | null;
  primaryAvatarId?: string | null;
  positionCount?: 1 | 2;
  musicTrackId?: string | null;
  musicVolume?: number;
  updatedAt?: string;
}

export interface MusicTrack {
  id: string;
  name: string;
  artist: string;
  mood: string;
  durationSeconds: number;
  url: string;
}

export type AvatarSetRole = "primary" | "front" | "close" | "three_quarter" | "standing" | "wide";

export interface AvatarSetLook {
  avatarId: string;
  role: AvatarSetRole;
  label: string;
}

export interface AvatarSet {
  id: string;
  name: string;
  voiceId: string;
  looks: AvatarSetLook[];
  updatedAt: string;
}

export interface ScenePlanScene {
  id: string;
  order: number;
  text: string;
  lookRole: AvatarSetRole;
  avatarId: string;
  estimatedStart: number;
  estimatedEnd: number;
}

export interface ScenePlan {
  scriptId: string;
  scenes: ScenePlanScene[];
  updatedAt: string;
}

export interface SceneGenerationRequest {
  sceneId: string;
  order: number;
  avatarId: string;
  voiceId: string;
  spokenText: string;
  speechMode: "natural" | "fiel" | "direto" | "enfatico";
  orientation: "portrait" | "landscape";
}

export interface SceneGenerationResult {
  scriptId: string;
  status: "not_submitted";
  provider: "heygen";
  sceneCount: number;
  estimatedCalls: number;
  requiresExplicitConfirmation: boolean;
  warning: string;
  requests: SceneGenerationRequest[];
}

export interface SceneDirectionSuggestion {
  text: string;
  lookRole: AvatarSetRole;
  reason: string;
}

export type VideoVisualType = "none" | "full_slide" | "overlay" | "statistic" | "comparison" | "quote";
export type VideoVisualLayout =
  | "hero_photo"
  | "photo_split"
  | "big_statement"
  | "question"
  | "myth_fact"
  | "number_stat"
  | "three_points"
  | "explainer"
  | "doctor_quote"
  | "photo_overlay"
  | "do_dont"
  | "cta_photo";

export interface VisualPlanScene {
  sceneId: string;
  visual: {
    type: VideoVisualType;
    layout: VideoVisualLayout | "";
    headline: string;
    body: string;
    purpose: string;
    startRatio: number;
    durationSeconds: number;
    motionPreset: "none" | "fade" | "soft_zoom" | "fade_zoom";
  };
}

export interface VisualPlan {
  scriptId: string;
  designSystemVersion: string;
  promptVersion: string;
  scenes: VisualPlanScene[];
  updatedAt: string;
}

export interface VideoSlideAsset {
  sceneId: string;
  index: number;
  type: VideoVisualType;
  layout: VideoVisualLayout | "";
  headline: string;
  body: string;
  startRatio: number;
  durationSeconds: number;
  motionPreset: "none" | "fade" | "soft_zoom" | "fade_zoom";
  assetPath: string | null;
  url?: string;
}

export interface VideoSlideRender {
  scriptId: string;
  width: number;
  height: number;
  scale: number;
  sceneCount: number;
  renderedCount: number;
  assets: VideoSlideAsset[];
  updatedAt: string;
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
  outdatedIdentity?: boolean;
  outdatedPackSchema?: boolean;
  requiredSlideCount?: number;
}> {
  const response = await requestJson<{
    ok: boolean;
    pack: GeneratedPack | null;
    productionProfile: ProductionProfile | null;
    outdatedAvatar: boolean;
    outdatedIdentity?: boolean;
    outdatedPackSchema?: boolean;
    requiredSlideCount?: number;
  }>(`/api/packs/${encodeURIComponent(scriptId)}`, { method: "GET" });
  return {
    pack: response.pack,
    productionProfile: response.productionProfile,
    outdatedAvatar: response.outdatedAvatar,
    outdatedIdentity: response.outdatedIdentity,
    outdatedPackSchema: response.outdatedPackSchema,
    requiredSlideCount: response.requiredSlideCount,
  };
}

export async function refreshPackAvatar(scriptId: string): Promise<{
  pack: GeneratedPack;
  compliance: PackCompliance;
  productionProfile: ProductionProfile | null;
  outdatedAvatar: boolean;
  outdatedIdentity?: boolean;
}> {
  const response = await requestJson<{
    ok: boolean;
    pack: GeneratedPack;
    compliance: PackCompliance;
    productionProfile: ProductionProfile | null;
    outdatedAvatar: boolean;
    outdatedIdentity?: boolean;
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
  schemaVersion?: GeneratedPack["schemaVersion"];
  designDirection?: GeneratedPack["designDirection"];
  carousel: PackSlide[];
  slides?: PackSlide[];
  staticPost: GeneratedPack["staticPost"];
  caption: string;
  hashtags?: string[];
  stories: PackSlide[];
  checklist: string[];
  sourceScriptId?: string | null;
  sourceAvatarId?: string | null;
  sourceAvatarSetId?: string | null;
  sourcePrimaryAvatarId?: string | null;
  sourceIdentityKey?: string | null;
  packContextVersion?: string | null;
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

export async function fetchMusicTracks(): Promise<MusicTrack[]> {
  const response = await requestJson<{ ok: boolean; tracks: MusicTrack[] }>("/api/music-tracks", {
    method: "GET",
  });
  return response.tracks;
}

export async function fetchAvatarSets(): Promise<AvatarSet[]> {
  const response = await requestJson<{ ok: boolean; avatarSets: AvatarSet[] }>(
    "/api/avatar-sets",
    { method: "GET" },
  );
  return response.avatarSets;
}

export async function saveAvatarSet(
  avatarSet: Omit<AvatarSet, "id" | "updatedAt">,
  id?: string,
): Promise<AvatarSet> {
  const response = await requestJson<{ ok: boolean; avatarSet: AvatarSet }>(
    id ? `/api/avatar-sets/${encodeURIComponent(id)}` : "/api/avatar-sets",
    {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(avatarSet),
    },
  );
  return response.avatarSet;
}

export async function deleteAvatarSet(id: string): Promise<void> {
  await requestJson<{ ok: boolean }>(`/api/avatar-sets/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export async function fetchScenePlan(scriptId: string): Promise<ScenePlan | null> {
  const response = await requestJson<{ ok: boolean; scenePlan: ScenePlan | null }>(
    `/api/scripts/${encodeURIComponent(scriptId)}/scene-plan`,
    { method: "GET" },
  );
  return response.scenePlan;
}

export async function saveScenePlan(
  scriptId: string,
  scenes: Array<{
    id?: string;
    text: string;
    lookRole: AvatarSetRole;
    estimatedStart: number;
    estimatedEnd: number;
  }>,
): Promise<ScenePlan> {
  const response = await requestJson<{ ok: boolean; scenePlan: ScenePlan }>(
    `/api/scripts/${encodeURIComponent(scriptId)}/scene-plan`,
    { method: "PUT", body: JSON.stringify({ scenes }) },
  );
  return response.scenePlan;
}

export async function fetchSceneGenerationPlan(
  scriptId: string,
  options?: {
    speechMode?: SceneGenerationRequest["speechMode"];
    orientation?: SceneGenerationRequest["orientation"];
  },
): Promise<SceneGenerationResult> {
  const query = new URLSearchParams({
    speechMode: options?.speechMode || "natural",
    orientation: options?.orientation || "portrait",
  });
  const response = await requestJson<{ ok: boolean; generation: SceneGenerationResult }>(
    `/api/scripts/${encodeURIComponent(scriptId)}/scene-generation/plan?${query.toString()}`,
    { method: "GET" },
  );
  return response.generation;
}

export async function submitSceneGeneration(
  scriptId: string,
  input: {
    orientation: "portrait" | "landscape";
    durationSeconds: 10 | 15 | 30 | 45 | 60;
    speechMode: "natural" | "fiel" | "direto" | "enfatico";
    captions: boolean;
    optimizePronunciation: boolean;
    idempotencyKey?: string;
  },
): Promise<{ generation: SceneGenerationResult; jobs: VideoJob[] }> {
  const response = await requestJson<{
    ok: boolean;
    generation: SceneGenerationResult;
    jobs: VideoJob[];
  }>(`/api/scripts/${encodeURIComponent(scriptId)}/scene-generation/submit`, {
    method: "POST",
    body: JSON.stringify({ confirmed: true, ...input }),
  });
  return { generation: response.generation, jobs: response.jobs };
}

export async function generateSceneDirection(
  scriptId: string,
  input: {
    displayText: string;
    spokenText?: string;
    tone?: string;
    pace?: string;
    emotion?: string;
    emphasisWords?: string[];
    durationSeconds: 10 | 15 | 30 | 45 | 60;
  },
): Promise<{ provider: "claude"; promptVersion: string; scenes: SceneDirectionSuggestion[] }> {
  const response = await requestJson<{
    ok: boolean;
    provider: "claude";
    promptVersion: string;
    scenes: SceneDirectionSuggestion[];
  }>(`/api/scripts/${encodeURIComponent(scriptId)}/scene-plan/direct`, {
    method: "POST",
    body: JSON.stringify(input),
  });
  return response;
}

export async function fetchVisualPlan(scriptId: string): Promise<VisualPlan | null> {
  const response = await requestJson<{ ok: boolean; visualPlan: VisualPlan | null }>(
    `/api/scripts/${encodeURIComponent(scriptId)}/visual-plan`,
    { method: "GET" },
  );
  return response.visualPlan;
}

export async function generateVisualDirection(
  scriptId: string,
  input: {
    displayText: string;
    spokenText?: string;
    tone?: string;
    pace?: string;
    emotion?: string;
    emphasisWords?: string[];
    durationSeconds: 10 | 15 | 30 | 45 | 60;
  },
): Promise<{ provider: "claude"; visualPlan: VisualPlan }> {
  const response = await requestJson<{ ok: boolean; provider: "claude"; visualPlan: VisualPlan }>(
    `/api/scripts/${encodeURIComponent(scriptId)}/visual-plan/direct`,
    { method: "POST", body: JSON.stringify(input) },
  );
  return response;
}

export async function saveVisualPlan(scriptId: string, plan: VisualPlan): Promise<VisualPlan> {
  const response = await requestJson<{ ok: boolean; visualPlan: VisualPlan }>(
    `/api/scripts/${encodeURIComponent(scriptId)}/visual-plan`,
    {
      method: "PUT",
      body: JSON.stringify({ scenes: plan.scenes }),
    },
  );
  return response.visualPlan;
}

export async function fetchVideoSlideRender(scriptId: string): Promise<VideoSlideRender | null> {
  const response = await requestJson<{ ok: boolean; render: VideoSlideRender | null }>(
    `/api/scripts/${encodeURIComponent(scriptId)}/video-slides`,
    { method: "GET" },
  );
  return response.render;
}

export async function renderVideoSlides(scriptId: string): Promise<VideoSlideRender> {
  const response = await requestJson<{ ok: boolean; render: VideoSlideRender }>(
    `/api/scripts/${encodeURIComponent(scriptId)}/video-slides/render`,
    { method: "POST", body: JSON.stringify({}) },
  );
  return response.render;
}

export async function composeFinalVideo(scriptId: string): Promise<VideoJob> {
  const response = await requestJson<{ ok: boolean; job: VideoJob }>(
    `/api/scripts/${encodeURIComponent(scriptId)}/compose-final-video`,
    { method: "POST" },
  );
  return response.job;
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
  generationMode?: "direct" | "video_agent";
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

export type PostProductionStatus =
  | "queued"
  | "transcribing"
  | "planning"
  | "preflight"
  | "rendering_preview"
  | "preview_ready"
  | "failed"
  | "cancelled"
  | "stale"
  | "needs_review";

export interface PostProductionJob {
  id: string;
  kind: "post_production";
  videoJobId: string;
  status: PostProductionStatus;
  progresso: number;
  etapa: string;
  criadoEm: string;
  atualizadoEm: string;
  erro?: string;
  plannerMode?: "cache" | "fallback" | "anthropic";
}

export interface VisualTimelineEvent {
  id: string;
  startWordIndex: number;
  endWordIndex: number;
  startMs: number;
  endMs: number;
  spokenText: string;
  interactionType:
    | "none"
    | "caption_emphasis"
    | "kinetic_text"
    | "progressive_list"
    | "supporting_visual"
    | "cta_card";
  visualText: string;
  enabled: boolean;
  reviewStatus: "pending" | "approved" | "rejected";
  reason: string;
  confidence: number;
}

export interface PostProductionArtifacts {
  transcript: {
    text: string;
    language: string;
    durationMs: number;
    words: Array<{ index: number; startMs: number; endMs: number; text: string }>;
  };
  timeline: {
    version: string;
    stale: boolean;
    events: VisualTimelineEvent[];
  };
}

export interface PreflightReport {
  ok: boolean;
  checkedAt: string;
  findings: Array<{
    code: string;
    classification: "BLOCKER" | "WARNING" | "INFO";
    message: string;
    eventId?: string;
  }>;
}

export async function createPostProduction(videoJobId: string): Promise<PostProductionJob> {
  const response = await postJson<{ job: PostProductionJob }>("/api/post-production", {
    videoJobId,
  });
  return response.job;
}

export async function fetchPostProduction(jobId: string): Promise<PostProductionJob> {
  const response = await requestJson<{ job: PostProductionJob }>(
    `/api/post-production/${encodeURIComponent(jobId)}`,
    {},
  );
  return response.job;
}

export async function fetchPostProductionArtifacts(
  jobId: string,
): Promise<PostProductionArtifacts> {
  return requestJson<PostProductionArtifacts>(
    `/api/post-production/${encodeURIComponent(jobId)}/artifacts`,
    {},
  );
}

export async function updatePostProductionEvents(
  jobId: string,
  events: Array<
    Pick<VisualTimelineEvent, "id"> &
      Partial<Pick<VisualTimelineEvent, "enabled" | "visualText" | "reviewStatus" | "interactionType">>
  >,
): Promise<{ job: PostProductionJob; timeline: PostProductionArtifacts["timeline"] }> {
  return requestJson(
    `/api/post-production/${encodeURIComponent(jobId)}/events`,
    { method: "PATCH", body: JSON.stringify({ events }) },
  );
}

export async function runPostProductionPreflight(
  jobId: string,
): Promise<{ ok: boolean; report: PreflightReport; job: PostProductionJob }> {
  return postJson(`/api/post-production/${encodeURIComponent(jobId)}/preflight`, {});
}

export async function renderPostProductionPreview(jobId: string): Promise<PostProductionJob> {
  const response = await postJson<{ job: PostProductionJob }>(
    `/api/post-production/${encodeURIComponent(jobId)}/render`,
    {},
  );
  return response.job;
}

export async function replanPostProduction(jobId: string): Promise<PostProductionJob> {
  const response = await postJson<{ job: PostProductionJob }>(
    `/api/post-production/${encodeURIComponent(jobId)}/replan`,
    {},
  );
  return response.job;
}

export function postProductionPreviewUrl(jobId: string, download = false): string {
  return `${BASE}/api/post-production/${encodeURIComponent(jobId)}/preview${download ? "?download=true" : ""}`;
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

export async function refreshHeyGenVideo(jobId: string): Promise<{ job: VideoJob; composedJob?: VideoJob | null }> {
  const res = await fetch(`${BASE}/api/videos/${jobId}/refresh`, { method: "POST" });
  if (!res.ok) throw new Error(await errorDetail(res, "Nao foi possivel consultar o HeyGen."));
  return (await res.json()) as { job: VideoJob; composedJob?: VideoJob | null };
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
