// Cliente da API local (FastAPI em api/server.py). A persistência principal
// pode ser PostgreSQL ou o backend legado, sem alterar os tipos da interface.
import type { HydratePayload } from "../store";
import type { AppSettings, CalendarPost, EditorialTone, Idea, Script, Trend } from "../mock-data";
import type { VideoJob } from "../mock-data";
import type {
  DurationAssessment,
  DurationPreset,
  EditorAssistResult,
  EditorOperation,
  MedicalReviewStatus,
} from "../script-editor";
import type {
  CinematicMediaType,
  CinematicPresenterMode,
  CinematicSupportingImages,
  CinematicVisualStyle,
} from "../cinematic";

const BASE = import.meta.env.VITE_API_URL ?? "";

export interface StatePayload extends HydratePayload {
  updatedAt?: string;
  dataBackend?: "postgres" | "sheets";
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

/** Grava o novo status no repositório de domínio configurado. */
export async function setSheetStatus(
  tab: "radar" | "ideias" | "roteiros" | "calendario",
  itemId: string,
  status: string,
): Promise<{ ok: boolean }> {
  const resources = {
    radar: "trends",
    ideias: "ideas",
    roteiros: "scripts",
    calendario: "calendar-posts",
  } as const;
  const res = await fetch(`${BASE}/api/${resources[tab]}/${itemId}/status`, {
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
      } else if (
        b.detail &&
        typeof b.detail === "object" &&
        "message" in b.detail &&
        typeof (b.detail as { message?: unknown }).message === "string"
      ) {
        detail = String((b.detail as { message: string }).message);
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

/** Persiste uma tendência cadastrada manualmente. */
export async function appendTrend(trend: Trend): Promise<Trend> {
  const response = await postJson<{ ok: boolean; trend: Trend }>("/api/trends", trend);
  return response.trend;
}

/** Persiste uma ideia gerada. */
export async function appendIdea(idea: Idea): Promise<Idea> {
  const response = await postJson<{ ok: boolean; idea: Idea }>("/api/ideas", idea);
  return response.idea;
}

/** Atualiza uma ideia existente, preservando ID e vínculo com a tendência. */
export async function saveIdea(idea: Idea): Promise<Idea> {
  const response = await requestJson<{ ok: boolean; idea: Idea }>(
    `/api/ideas/${encodeURIComponent(idea.id)}`,
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
  durationSeconds?: DurationPreset;
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

export interface CreateScriptFromDraftInput {
  draftText: string;
  title?: string;
  familia: Idea["familia"];
  editorialTone: EditorialTone;
  durationSeconds: DurationPreset;
}

export interface ScriptFromDraftResult {
  provider: "claude";
  model: string;
  promptVersion: string;
  cacheHit: boolean;
  deduplicated: boolean;
  script: Script;
  scenePlan: ScenePlan;
  changes: string[];
}

/** Revisa um texto com Claude, salva o roteiro e cria cenas ainda sem gerar vídeo. */
export async function createScriptFromDraft(
  input: CreateScriptFromDraftInput,
): Promise<ScriptFromDraftResult> {
  const response = await postJson<{ ok: boolean } & ScriptFromDraftResult>(
    "/api/scripts/from-draft",
    input,
  );
  return response;
}

/** Persiste um roteiro gerado. */
export async function appendScript(script: Script): Promise<Script> {
  const response = await postJson<{ ok: boolean; script: Script }>("/api/scripts", script);
  return response.script;
}

/** Atualiza o roteiro na fonte de verdade usada pela produção. */
export async function saveScript(script: Script): Promise<Script> {
  const response = await requestJson<{ ok: boolean; script: Script }>(
    `/api/scripts/${encodeURIComponent(script.id)}`,
    { method: "PUT", body: JSON.stringify(script) },
  );
  return response.script;
}

/** Exclui o roteiro; o backend bloqueia quando existe vídeo ou agendamento vinculado. */
export async function deleteScript(scriptId: string): Promise<{ id: string; title: string }> {
  const response = await requestJson<{ ok: boolean; id: string; title: string }>(
    `/api/scripts/${encodeURIComponent(scriptId)}`,
    { method: "DELETE" },
  );
  return { id: response.id, title: response.title };
}

/** Cria um agendamento persistente. */
export async function appendCalendarPost(post: Omit<CalendarPost, "id">): Promise<CalendarPost> {
  const response = await postJson<{ ok: boolean; post: CalendarPost }>("/api/calendar-posts", post);
  return response.post;
}

/** Persiste reagendamento, publicacao e demais alteracoes do calendario. */
export async function saveCalendarPost(post: CalendarPost): Promise<CalendarPost> {
  const response = await requestJson<{ ok: boolean; post: CalendarPost }>(
    `/api/calendar-posts/${encodeURIComponent(post.id)}`,
    { method: "PUT", body: JSON.stringify(post) },
  );
  return response.post;
}

export type PackFamily = "editorial" | "didatico" | "storytelling" | "manifesto" | "clinico";
export type PackTheme = "modernist-red" | "ocean-deep" | "soft-sage" | "soft-rose";

export interface GeneratedPack {
  schemaVersion?: "institute-carousel-v1" | string;
  designDirection?: "institute_carousel_v1" | string;
  family?: PackFamily;
  themeId?: PackTheme;
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
  educationalFlowVersion?: string | null;
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
  coverNote: string;
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

export type VoiceMood = "confident" | "upbeat" | "warm" | "serious" | "neutral";
export type GenerationMode = "direct" | "video_agent" | "cinematic" | "story";

export interface HeyGenProviderCapabilities {
  provider: "heygen";
  cliVersion: string;
  capabilitiesVersion: string;
  checkedAt: string;
  videoAgent: {
    supported: boolean;
    supportsStyleId: boolean;
    supportsBrandKitId: boolean;
    supportsChatMode: boolean;
    supportsAttachments: boolean;
    supportsIncognitoMode: boolean;
    orientations: string[];
    modes: string[];
  };
  directVideo: {
    supported: boolean;
    supportedTypes: string[];
    supportedEngines: string[];
    supportedResolutions: string[];
    supportedAspectRatios: string[];
  };
}

export interface StoryReferenceAsset {
  id: string;
  kind: "image" | "video" | "document";
  sha256: string;
  description: string;
}

export interface StoryBrief {
  storyType: "historical_explainer" | "medical_explainer" | "narrative_explainer";
  educationalGoal: string;
  period: string;
  location: string;
  realismLevel: "high" | "medium" | "stylized";
  historicalAccuracy: "strict" | "inspired" | "not_applicable";
  tone: "curious_educational" | "documentary" | "warm_explainer" | "dramatic_restrained";
  durationSeconds: number;
  orientation: "portrait" | "landscape" | "square";
  productionTier: "standard" | "cinematic" | "premium";
  maxHeyGenJobs: number;
  maxRegenerationsPerShot: number;
  maxBudgetUsd: number | null;
  characterId: string | null;
  lookId: string | null;
  characterDescription: string;
  wardrobeDirection: string;
  referenceAssets: StoryReferenceAsset[];
}

export interface StoryPlanShot {
  id: string;
  order: number;
  narrativePurpose: string;
  shotType: "avatar_anchor" | "historical_broll" | "modern_broll" | "transition" | "local_asset";
  strategy: "avatar_anchor" | "cinematic_broll" | "local_transition";
  providerStrategy: "video_agent" | "direct_video" | "local_compositor";
  subject: string;
  durationSeconds: number;
  speech: {
    mode: "avatar_speaks" | "voice_continues_from_base_scene";
    startWordIndex: number;
    endWordIndex: number;
  };
  character: { required: boolean; characterId: string | null; lookId: string | null };
  environment: string;
  period: string;
  wardrobe: string;
  action: string;
  camera: { framing: string; movement: string; lens: string };
  lighting: string;
  atmosphere: string;
  continuityKeys: string[];
  referenceAssetIds: string[];
  negativePrompt: string[];
  heygenPrompt: string;
  audioPolicy: "preserve_base_narration" | "mute_generated_audio";
  estimatedCost: { heygenJobs: number; anthropicCalls: 0 };
}

export interface StoryPlan {
  contractVersion: "story-contract-v2";
  storyBible: {
    premise: string;
    educationalGoal: string;
    narrativeArc: { opening: string; development: string; turn: string; ending: string };
    historicalSetting: {
      period: string;
      location: string;
      accuracyMode: "strict" | "inspired" | "not_applicable";
    };
  };
  characterBible: {
    characterId: string | null;
    lookId: string | null;
    identityRule: string;
    voiceRule: string;
    wardrobe: { base: string; accessories: string[]; colors: string[] };
    forbiddenChanges: string[];
  };
  visualBible: {
    palette: string;
    lighting: string;
    cameraStyle: string;
    texture: string;
    forbiddenAnachronisms: string[];
  };
  medicalAssertions: [];
  shots: StoryPlanShot[];
}

export interface StoryShotRecord {
  id: string;
  storyVersionId: string;
  shotId: string;
  order: number;
  provider: StoryPlanShot["providerStrategy"];
  prompt: StoryPlanShot;
  promptHash: string;
  continuityHash: string;
  controls: {
    promptOverride: string;
    lockIdentity: boolean;
    lockWardrobe: boolean;
    lockEnvironment: boolean;
    approved: boolean;
  };
  status: "review" | "approved" | string;
  shotRevision: number;
  currentGenerationId?: string | null;
  thumbnailPath?: string | null;
  currentGeneration?: StoryShotGeneration | null;
}

export interface StoryShotGeneration {
  id: string;
  storyShotId: string;
  storyVersionId: string;
  shotRevision: number;
  strategy: StoryPlanShot["strategy"];
  provider: StoryPlanShot["providerStrategy"];
  prompt: string;
  spokenText: string;
  avatarId: string | null;
  durationSeconds: number;
  continuity: Record<string, unknown>;
  idempotencyKey: string;
  providerJobId: string | null;
  outputPath: string | null;
  outputUrl: string | null;
  status: "ready" | "generating" | "submitted" | "completed" | "failed" | "needs_regeneration";
  retrySafe: boolean;
  estimatedCostUsd: number | null;
  error: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface StoryComposition {
  id: string;
  scriptId: string;
  storyVersionId: string;
  status: "processando" | "pronto" | "erro";
  progresso: number;
  videoUrl: string;
  outputPath: string;
  duracaoSegundos?: number;
  shotCount?: number;
  sourceShotGenerations: string[];
  baseNarrationJobId: string;
  narrationPolicy?: "base_audio_continuous";
  captions?: boolean;
  erro?: string;
}

export interface StoryBudgetIssue {
  code: string;
  severity: "blocking" | "warning" | "info";
  message: string;
  suggestedAction: string;
}

export interface StoryBudget {
  initialHeyGenJobs: number;
  maxRegenerationJobs: number;
  worstCaseHeyGenJobs: number;
  maxHeyGenJobs: number;
  maxRegenerationsPerShot: number;
  providerJobCounts: Record<string, number>;
  providerRatesUsd: Record<string, number | null>;
  estimatedInitialUsd: number | null;
  estimatedWorstCaseUsd: number | null;
  maxBudgetUsd: number | null;
  estimatedAnthropicCalls: number;
  issues: StoryBudgetIssue[];
  approvalEligible: boolean;
  budgetHash: string;
}

export interface StoryCritiqueRecord {
  id: string;
  storyVersionId: string;
  critiqueRevision: number;
  critique: {
    contractVersion: "story-critic-v1";
    decision: "ready" | "changes_required" | "blocked";
    overallRisk: "low" | "medium" | "high";
    summary: string;
    issues: Array<{
      code: string;
      category: string;
      severity: "info" | "warning" | "blocking";
      shotIds: string[];
      message: string;
      suggestedAction: string;
    }>;
    shotAssessments: Array<{
      shotId: string;
      difficulty: "low" | "medium" | "high";
      continuityRisk: "low" | "medium" | "high";
      historicalRisk: "low" | "medium" | "high" | "not_applicable";
      medicalRisk: "low" | "medium" | "high";
      recommendedProvider: StoryPlanShot["providerStrategy"];
      recommendationReason: string;
      redundantWithShotId: string | null;
    }>;
  };
  budget: StoryBudget;
  critiqueHash: string;
  model: string;
  createdAt: string;
}

export interface StoryVersion {
  id: string;
  storyProjectId: string;
  storyRevision: number;
  scriptRevision: number;
  finalSpeechHash: string;
  scriptContractVersion: string;
  storyContractVersion: string;
  providerCapabilitiesVersion: string;
  storyHash: string;
  promptVersion: string;
  model: string;
  activeCritiqueId: string | null;
  activeCritique?: StoryCritiqueRecord | null;
  storyBibleApproved: boolean;
  budgetApproved: boolean;
  budgetApproval: Record<string, unknown> | null;
  approved: boolean;
  approvedAt: string | null;
  createdAt: string;
  plan: StoryPlan;
  shots?: StoryShotRecord[];
  composition?: StoryComposition | null;
}

export interface StoryProject {
  id: string;
  scriptId: string;
  status: string;
  activeStoryVersion: string | null;
  productionTier: StoryBrief["productionTier"];
  brief: StoryBrief;
  budget: {
    maxHeyGenJobs: number;
    maxRegenerationsPerShot: number;
    maxBudgetUsd: number | null;
  };
  activeVersion: StoryVersion | null;
  createdAt: string;
  updatedAt: string;
}

export interface StoryBindings {
  scriptRevision: number;
  finalSpeechHash: string;
  scriptContractVersion: string;
  storyContractVersion: string;
  storyPromptVersion: string;
}

export interface ProductionProfile {
  scriptId: string;
  avatarId: string;
  voiceId: string;
  speechMode: "natural" | "fiel" | "direto" | "enfatico";
  voiceMood: VoiceMood;
  generationMode: GenerationMode;
  avatarMode?: "single" | "set";
  avatarSetId?: string | null;
  primaryAvatarId?: string | null;
  positionCount?: 1 | 2;
  musicTrackId?: string | null;
  musicVolume?: number;
  cinematicPrompt?: string;
  styleId?: string | null;
  brandKitId?: string | null;
  videoAgentMode?: "generate" | "chat";
  videoAgentVisualMode?: "standard" | "seedance";
  videoAgentInstructions?: string;
  videoAgentAttachments?: VideoAgentAttachment[];
  videoAgentIncognitoMode?: boolean;
  updatedAt?: string;
}

export type PodcastSpeakerId = "a" | "b";

export interface PodcastParticipant {
  id: PodcastSpeakerId;
  name: string;
  avatarId: string;
  voiceId: string;
}

export interface PodcastTurn {
  id: string;
  order: number;
  speakerId: PodcastSpeakerId;
  text: string;
}

export interface PodcastPlan {
  scriptId: string;
  title: string;
  orientation: "portrait" | "landscape";
  captions: boolean;
  transitionStyle: "hard_cut";
  musicTrackId?: string | null;
  musicVolume?: number;
  participants: [PodcastParticipant, PodcastParticipant];
  turns: PodcastTurn[];
  updatedAt: string;
}

export interface PodcastDialogueResult {
  provider: "claude";
  model: string;
  promptVersion: string;
  title: string;
  turns: Array<Pick<PodcastTurn, "speakerId" | "text">>;
  turnCount: number;
  wordCount: number;
}

export interface PodcastGenerationRequest {
  turnId: string;
  order: number;
  speakerId: PodcastSpeakerId;
  speakerName: string;
  avatarId: string;
  voiceId: string;
  spokenText: string;
  speechMode: "natural" | "fiel" | "direto" | "enfatico";
  voiceMood: VoiceMood;
  orientation: "portrait" | "landscape";
}

export interface PodcastGenerationResult {
  scriptId: string;
  status: "not_submitted";
  provider: "heygen";
  turnCount: number;
  estimatedCalls: number;
  requiresExplicitConfirmation: boolean;
  warning: string;
  requests: PodcastGenerationRequest[];
}

export interface MusicTrack {
  id: string;
  name: string;
  artist: string;
  mood: string;
  durationSeconds: number;
  url: string;
}

export type AvatarSetRole =
  "primary" | "front" | "close" | "three_quarter" | "standing" | "seated" | "wide";

export type ClaudeSceneModel = "haiku" | "sonnet";

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

export type SceneTransitionStyle = "smooth" | "hard_cut" | "dip_to_black";

export interface ScenePlan {
  scriptId: string;
  scenes: ScenePlanScene[];
  transitionStyle: SceneTransitionStyle;
  updatedAt: string;
}

export interface SceneGenerationRequest {
  sceneId: string;
  order: number;
  lookRole: AvatarSetRole;
  avatarId: string;
  voiceId: string;
  spokenText: string;
  speechMode: "natural" | "fiel" | "direto" | "enfatico";
  voiceMood: VoiceMood;
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

export interface SceneDirectionResult {
  provider: "claude";
  promptVersion: string;
  model: string;
  modelTier: ClaudeSceneModel;
  requestedModel?: string;
  fallbackUsed?: boolean;
  adjustedScript: string;
  scriptChanges: string[];
  scenes: SceneDirectionSuggestion[];
}

export type VideoVisualType =
  "none" | "full_slide" | "overlay" | "statistic" | "comparison" | "quote";
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
  presentation?: { family: PackFamily; themeId: PackTheme },
): Promise<{ pack: GeneratedPack; compliance: PackCompliance }> {
  const res = await fetch(`${BASE}/api/packs/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...script, scriptId: script.id, ...presentation }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, "Nao foi possivel gerar o pack."));
  return (await res.json()) as { pack: GeneratedPack; compliance: PackCompliance };
}

/** Salva composição e tema do Pack localmente. Não chama Claude nem altera a copy. */
export async function updatePackPresentation(
  scriptId: string,
  presentation: { family: PackFamily; themeId: PackTheme },
): Promise<{ pack: GeneratedPack; compliance: PackCompliance }> {
  const response = await requestJson<{
    ok: boolean;
    pack: GeneratedPack;
    compliance: PackCompliance;
  }>(`/api/packs/${encodeURIComponent(scriptId)}/presentation`, {
    method: "PUT",
    body: JSON.stringify(presentation),
  });
  return { pack: response.pack, compliance: response.compliance };
}

export async function fetchPack(scriptId: string): Promise<{
  pack: GeneratedPack | null;
  productionProfile: ProductionProfile | null;
  outdatedAvatar: boolean;
  outdatedIdentity?: boolean;
  outdatedPackSchema?: boolean;
  outdatedEducationalFlow?: boolean;
  requiredSlideCount?: number;
}> {
  const response = await requestJson<{
    ok: boolean;
    pack: GeneratedPack | null;
    productionProfile: ProductionProfile | null;
    outdatedAvatar: boolean;
    outdatedIdentity?: boolean;
    outdatedPackSchema?: boolean;
    outdatedEducationalFlow?: boolean;
    requiredSlideCount?: number;
  }>(`/api/packs/${encodeURIComponent(scriptId)}`, { method: "GET" });
  return {
    pack: response.pack,
    productionProfile: response.productionProfile,
    outdatedAvatar: response.outdatedAvatar,
    outdatedIdentity: response.outdatedIdentity,
    outdatedPackSchema: response.outdatedPackSchema,
    outdatedEducationalFlow: response.outdatedEducationalFlow,
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

/** Salva a mensagem opcional exibida somente na caixa do Slide 1. */
export async function updatePackCoverNote(
  scriptId: string,
  text: string,
): Promise<{ pack: GeneratedPack; compliance: PackCompliance }> {
  const response = await requestJson<{
    ok: boolean;
    pack: GeneratedPack;
    compliance: PackCompliance;
  }>(`/api/packs/${encodeURIComponent(scriptId)}/carousel/cover-note`, {
    method: "PUT",
    body: JSON.stringify({ text }),
  });
  return { pack: response.pack, compliance: response.compliance };
}

export interface PackForExport {
  schemaVersion?: GeneratedPack["schemaVersion"];
  designDirection?: GeneratedPack["designDirection"];
  family?: PackFamily;
  themeId?: PackTheme;
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
): Promise<{
  ok: boolean;
  relative: string;
  folder: string;
  files: number;
  images: number;
  warning?: string;
}> {
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
    images: number;
    warning?: string;
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

export async function fetchPodcastPlan(scriptId: string): Promise<PodcastPlan | null> {
  const response = await requestJson<{ ok: boolean; podcastPlan: PodcastPlan | null }>(
    `/api/scripts/${encodeURIComponent(scriptId)}/podcast-plan`,
    { method: "GET" },
  );
  return response.podcastPlan;
}

export async function savePodcastPlan(
  scriptId: string,
  plan: Omit<PodcastPlan, "scriptId" | "updatedAt">,
): Promise<PodcastPlan> {
  const response = await requestJson<{ ok: boolean; podcastPlan: PodcastPlan }>(
    `/api/scripts/${encodeURIComponent(scriptId)}/podcast-plan`,
    { method: "PUT", body: JSON.stringify(plan) },
  );
  return response.podcastPlan;
}

export async function generatePodcastDialogue(
  scriptId: string,
  input: {
    sourceText: string;
    hostName: string;
    guestName: string;
    direction?: string;
    durationSeconds: 30 | 45 | 60 | 90 | 120 | 180;
  },
): Promise<PodcastDialogueResult> {
  const response = await requestJson<{ ok: boolean } & PodcastDialogueResult>(
    `/api/scripts/${encodeURIComponent(scriptId)}/podcast-dialogue/generate`,
    { method: "POST", body: JSON.stringify(input) },
  );
  return response;
}

export async function fetchPodcastGenerationPlan(
  scriptId: string,
  options?: {
    speechMode?: PodcastGenerationRequest["speechMode"];
    voiceMood?: VoiceMood;
    orientation?: PodcastGenerationRequest["orientation"];
  },
): Promise<PodcastGenerationResult> {
  const query = new URLSearchParams({
    speechMode: options?.speechMode || "natural",
    voiceMood: options?.voiceMood || "confident",
    orientation: options?.orientation || "portrait",
  });
  const response = await requestJson<{ ok: boolean; generation: PodcastGenerationResult }>(
    `/api/scripts/${encodeURIComponent(scriptId)}/podcast-generation/plan?${query.toString()}`,
    { method: "GET" },
  );
  return response.generation;
}

export async function submitPodcastGeneration(
  scriptId: string,
  input: {
    orientation: "portrait" | "landscape";
    durationSeconds: DurationPreset;
    speechMode: PodcastGenerationRequest["speechMode"];
    voiceMood: VoiceMood;
    captions: boolean;
    forceNewVersion?: boolean;
    idempotencyKey?: string;
    expectedScriptRevision?: number;
    expectedFinalSpeechHash?: string;
    contractVersion?: string;
  },
): Promise<{ generation: PodcastGenerationResult; jobs: VideoJob[] }> {
  const response = await requestJson<{
    ok: boolean;
    generation: PodcastGenerationResult;
    jobs: VideoJob[];
  }>(`/api/scripts/${encodeURIComponent(scriptId)}/podcast-generation/submit`, {
    method: "POST",
    body: JSON.stringify({ confirmed: true, ...input }),
  });
  return { generation: response.generation, jobs: response.jobs };
}

export async function fetchHeyGenProviderCapabilities(): Promise<HeyGenProviderCapabilities> {
  const response = await requestJson<{
    ok: boolean;
    capabilities: HeyGenProviderCapabilities;
  }>("/api/providers/heygen/capabilities", { method: "GET" });
  return response.capabilities;
}

export async function fetchStoryProject(scriptId: string): Promise<{
  project: StoryProject | null;
  bindings: StoryBindings;
}> {
  const response = await requestJson<{
    ok: boolean;
    project: StoryProject | null;
    bindings: StoryBindings;
  }>(`/api/scripts/${encodeURIComponent(scriptId)}/story`, { method: "GET" });
  return { project: response.project, bindings: response.bindings };
}

export async function saveStoryBrief(
  scriptId: string,
  brief: StoryBrief,
  bindings: Pick<StoryBindings, "scriptRevision" | "finalSpeechHash" | "scriptContractVersion">,
): Promise<StoryProject> {
  const response = await requestJson<{ ok: boolean; project: StoryProject }>(
    `/api/scripts/${encodeURIComponent(scriptId)}/story/brief`,
    {
      method: "PUT",
      body: JSON.stringify({
        brief,
        expectedScriptRevision: bindings.scriptRevision,
        expectedFinalSpeechHash: bindings.finalSpeechHash,
        scriptContractVersion: bindings.scriptContractVersion,
      }),
    },
  );
  return response.project;
}

export async function planStory(
  scriptId: string,
  brief: StoryBrief,
  bindings: Pick<StoryBindings, "scriptRevision" | "finalSpeechHash" | "scriptContractVersion">,
  providerCapabilitiesVersion: string,
): Promise<{ project: StoryProject; version: StoryVersion; cacheHit: boolean }> {
  return requestJson<{ project: StoryProject; version: StoryVersion; cacheHit: boolean }>(
    `/api/scripts/${encodeURIComponent(scriptId)}/story/plan`,
    {
      method: "POST",
      body: JSON.stringify({
        brief,
        expectedScriptRevision: bindings.scriptRevision,
        expectedFinalSpeechHash: bindings.finalSpeechHash,
        scriptContractVersion: bindings.scriptContractVersion,
        expectedProviderCapabilitiesVersion: providerCapabilitiesVersion,
        confirmed: true,
      }),
    },
  );
}

export async function reviseStoryVersion(
  version: StoryVersion,
  plan: StoryPlan,
  shotReviews: StoryShotRecord["controls"][],
  providerCapabilitiesVersion: string,
  storyBibleApproved: boolean,
): Promise<{ project: StoryProject; version: StoryVersion }> {
  const reviews = plan.shots.map((shot, index) => ({
    shotId: shot.id,
    ...(shotReviews[index] || {
      promptOverride: "",
      lockIdentity: true,
      lockWardrobe: true,
      lockEnvironment: false,
      approved: false,
    }),
  }));
  return requestJson<{ project: StoryProject; version: StoryVersion }>(
    `/api/story-versions/${encodeURIComponent(version.id)}/revise`,
    {
      method: "POST",
      body: JSON.stringify({
        expectedStoryHash: version.storyHash,
        expectedProviderCapabilitiesVersion: providerCapabilitiesVersion,
        plan,
        shotReviews: reviews,
        storyBibleApproved,
        reason: "Edição humana do storyboard.",
        idempotencyKey: newVersionKey(`story-revision:${version.id}`),
      }),
    },
  );
}

export async function critiqueStoryVersion(
  version: StoryVersion,
  providerCapabilitiesVersion: string,
  forceNewVersion = false,
): Promise<{ critique: StoryCritiqueRecord; version: StoryVersion; cacheHit: boolean }> {
  return requestJson<{
    critique: StoryCritiqueRecord;
    version: StoryVersion;
    cacheHit: boolean;
  }>(`/api/story-versions/${encodeURIComponent(version.id)}/critique`, {
    method: "POST",
    body: JSON.stringify({
      expectedStoryHash: version.storyHash,
      expectedProviderCapabilitiesVersion: providerCapabilitiesVersion,
      confirmed: true,
      forceNewVersion,
      idempotencyKey: forceNewVersion ? newVersionKey(`story-critique:${version.id}`) : undefined,
    }),
  });
}

export async function approveStoryVersion(
  version: StoryVersion,
  critique: StoryCritiqueRecord,
): Promise<{ project: StoryProject; version: StoryVersion }> {
  return requestJson<{ project: StoryProject; version: StoryVersion }>(
    `/api/story-versions/${encodeURIComponent(version.id)}/approve`,
    {
      method: "POST",
      body: JSON.stringify({
        critiqueId: critique.id,
        expectedStoryHash: version.storyHash,
        expectedBudgetHash: critique.budget.budgetHash,
        approvalActor: "editor_user",
        confirmed: true,
      }),
    },
  );
}

export async function generateStoryShot(
  version: StoryVersion,
  shot: StoryShotRecord,
  critique: StoryCritiqueRecord,
  regenerate = false,
): Promise<{ generation: StoryShotGeneration; deduplicated: boolean; ok: boolean }> {
  const nextRevision = (shot.currentGeneration?.shotRevision ?? 0) + 1;
  const response = await requestJson<{
    generation: StoryShotGeneration;
    deduplicated: boolean;
    ok: boolean;
  }>(`/api/story-shots/${encodeURIComponent(shot.id)}/generate`, {
    method: "POST",
    body: JSON.stringify({
      expectedStoryHash: version.storyHash,
      expectedPromptHash: shot.promptHash,
      expectedBudgetHash: critique.budget.budgetHash,
      idempotencyKey: `story-shot:${shot.id}:revision:${nextRevision}`,
      regenerate,
      confirmed: true,
    }),
  });
  if (!response.ok) {
    throw new Error(response.generation.error || "O provider não confirmou a geração do shot.");
  }
  return response;
}

export async function refreshStoryShot(generationId: string): Promise<StoryShotGeneration> {
  const response = await requestJson<{ ok: boolean; generation: StoryShotGeneration }>(
    `/api/story-shot-generations/${encodeURIComponent(generationId)}/refresh`,
    { method: "POST" },
  );
  return response.generation;
}

export function storyShotMediaUrl(generation: StoryShotGeneration, thumbnail = false) {
  const path = thumbnail
    ? `/api/story-shot-generations/${encodeURIComponent(generation.id)}/thumbnail`
    : generation.outputUrl ||
      `/api/story-shot-generations/${encodeURIComponent(generation.id)}/file`;
  return /^https?:\/\//.test(path) ? path : `${BASE}${path}`;
}

export async function composeStoryVersion(version: StoryVersion): Promise<StoryComposition> {
  const response = await requestJson<{ ok: boolean; job: StoryComposition }>(
    `/api/story-versions/${encodeURIComponent(version.id)}/compose`,
    {
      method: "POST",
      body: JSON.stringify({
        expectedStoryHash: version.storyHash,
        confirmed: true,
      }),
    },
  );
  return response.job;
}

export function storyCompositionMediaUrl(composition: StoryComposition, download = false) {
  const path = download
    ? `/api/videos/${encodeURIComponent(composition.id)}/download`
    : composition.videoUrl || `/api/videos/${encodeURIComponent(composition.id)}/file`;
  return /^https?:\/\//.test(path) ? path : `${BASE}${path}`;
}

export async function fetchMusicTracks(): Promise<MusicTrack[]> {
  const response = await requestJson<{ ok: boolean; tracks: MusicTrack[] }>("/api/music-tracks", {
    method: "GET",
  });
  return response.tracks.map((track) => ({
    ...track,
    url: /^https?:\/\//.test(track.url) ? track.url : `${BASE}${track.url}`,
  }));
}

export async function fetchAvatarSets(): Promise<AvatarSet[]> {
  const response = await requestJson<{ ok: boolean; avatarSets: AvatarSet[] }>("/api/avatar-sets", {
    method: "GET",
  });
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
  transitionStyle: SceneTransitionStyle = "hard_cut",
): Promise<ScenePlan> {
  const response = await requestJson<{ ok: boolean; scenePlan: ScenePlan }>(
    `/api/scripts/${encodeURIComponent(scriptId)}/scene-plan`,
    { method: "PUT", body: JSON.stringify({ scenes, transitionStyle }) },
  );
  return response.scenePlan;
}

export async function fetchSceneGenerationPlan(
  scriptId: string,
  options?: {
    speechMode?: SceneGenerationRequest["speechMode"];
    voiceMood?: VoiceMood;
    orientation?: SceneGenerationRequest["orientation"];
  },
): Promise<SceneGenerationResult> {
  const query = new URLSearchParams({
    speechMode: options?.speechMode || "natural",
    voiceMood: options?.voiceMood || "confident",
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
    durationSeconds: DurationPreset;
    speechMode: "natural" | "fiel" | "direto" | "enfatico";
    voiceMood: VoiceMood;
    captions: boolean;
    optimizePronunciation: boolean;
    forceNewVersion?: boolean;
    idempotencyKey?: string;
    expectedScriptRevision?: number;
    expectedFinalSpeechHash?: string;
    contractVersion?: string;
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

export async function regenerateSceneVideo(jobId: string): Promise<VideoJob> {
  const response = await postJson<{ ok: boolean; job: VideoJob }>(
    `/api/videos/${encodeURIComponent(jobId)}/regenerate-scene`,
    { confirmed: true },
  );
  return response.job;
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
    durationSeconds: DurationPreset;
    modelTier?: ClaudeSceneModel;
  },
): Promise<SceneDirectionResult> {
  const response = await requestJson<{ ok: boolean } & SceneDirectionResult>(
    `/api/scripts/${encodeURIComponent(scriptId)}/scene-plan/direct`,
    {
      method: "POST",
      body: JSON.stringify(input),
    },
  );
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
    durationSeconds: DurationPreset;
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

export interface CinematicAdjustInput {
  sourceText: string;
  durationSeconds: Exclude<DurationPreset, 10>;
  supportingImages: CinematicSupportingImages;
  presenterMode: CinematicPresenterMode;
  mediaTypes: CinematicMediaType[];
  visualStyle: CinematicVisualStyle;
  requiredElements: string;
  excludedElements: string;
  criticalOnScreenText: string;
  directionNotes: string;
  avatarName?: string;
  avatarType?: string;
  avatarOrientation?: "portrait" | "landscape";
}

export interface CinematicAdjustment {
  speech: string;
  durationSeconds: Exclude<DurationPreset, 10>;
  supportingImages: CinematicSupportingImages;
  presenterMode: CinematicPresenterMode;
  mediaTypes: CinematicMediaType[];
  visualStyle: CinematicVisualStyle;
  requiredElements: string;
  excludedElements: string;
  criticalOnScreenText: string;
  directionNotes: string;
  rationale: string;
}

export interface CinematicAdjustResult {
  provider: "claude";
  model: string;
  adjusted: CinematicAdjustment;
  assessment: DurationAssessment;
  retryCount: number;
  cacheHit: boolean;
}

export async function adjustCinematicWithClaude(
  input: CinematicAdjustInput,
): Promise<CinematicAdjustResult> {
  return requestJson<CinematicAdjustResult>("/api/cinematic/adjust", {
    method: "POST",
    body: JSON.stringify(input),
  });
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
  generationModes?: GenerationMode[];
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
  consentStatus?: string | null;
  setupWarning?: string | null;
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

export interface HeyGenBrandKit {
  brand_kit_id: string;
  name: string;
}

export interface VideoAgentAttachment {
  assetId: string;
  name: string;
  mimeType: string;
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

export async function fetchHeyGenStyles(tag = "all"): Promise<{
  styles: HeyGenStyle[];
  tag: string;
}> {
  return requestJson(`/api/heygen/styles?tag=${encodeURIComponent(tag)}`, { method: "GET" });
}

export async function fetchHeyGenBrandKits(): Promise<HeyGenBrandKit[]> {
  const response = await requestJson<{ brandKits: HeyGenBrandKit[] }>("/api/heygen/brand-kits", {
    method: "GET",
  });
  return response.brandKits;
}

export async function uploadHeyGenAsset(file: File): Promise<VideoAgentAttachment> {
  const dataUrl = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`Não foi possível ler ${file.name}.`));
    reader.onload = () => resolve(String(reader.result || ""));
    reader.readAsDataURL(file);
  });
  const response = await postJson<{ ok: boolean; attachment: VideoAgentAttachment }>(
    "/api/heygen/assets",
    {
      name: file.name,
      mimeType: file.type || "text/plain",
      data: dataUrl.slice(dataUrl.indexOf(",") + 1),
    },
  );
  return response.attachment;
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
    durationSeconds: DurationPreset;
    speechMode: "natural" | "fiel" | "direto" | "enfatico";
    voiceMood: VoiceMood;
    generationMode: GenerationMode;
    ctaMode?: "auto" | "manual" | "none" | "visual";
    captions: boolean;
    optimizePronunciation: boolean;
    styleId?: string;
    brandKitId?: string;
    videoAgentMode?: "generate" | "chat";
    videoAgentVisualMode?: "standard" | "seedance";
    videoAgentInstructions?: string;
    videoAgentAttachments?: VideoAgentAttachment[];
    videoAgentIncognitoMode?: boolean;
    forceNewVersion?: boolean;
    narrationText?: string;
    displayText?: string;
    spokenText?: string;
    cinematicPrompt?: string;
    outroText?: string;
    idempotencyKey?: string;
    medicalReviewStatus?: MedicalReviewStatus;
    humanReviewApproved?: boolean;
    aiOperationInFlight?: boolean;
    aiSchemaValid?: boolean;
    editorTechnicalError?: string | null;
    finalConfirmed?: boolean;
    expectedScriptRevision?: number;
    expectedFinalSpeechHash?: string;
    contractVersion?: string;
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

export interface ScriptEditorAssistInput {
  operation: EditorOperation;
  scriptId?: string;
  text: string;
  title: string;
  sourceText?: string;
  contextText?: string;
  medicalCautions?: string;
  riskLevel?: string;
  claims?: string[];
  glossary?: string[];
  cta?: string;
  durationSeconds: DurationPreset;
  speechProfileId?: string;
  editorialProfileId?: string;
  humanReviewApproved?: boolean;
}

export interface ScriptEditorState {
  scriptId: string;
  durationSeconds: DurationPreset;
  humanReviewApproved: boolean;
  titleChoice: "current" | "suggested";
  suggestedTitle?: string | null;
  schemaValid: boolean;
  technicalError?: string | null;
  previousScript?: string | null;
  lastResult?: EditorAssistResult | null;
  scriptRevision: number;
  finalSpeechHash?: string | null;
  approvedScriptRevision?: number | null;
  approvedFinalSpeechHash?: string | null;
  approvalHistory?: Array<{
    actor: string;
    timestamp: string;
    previousStatus: string;
    nextStatus: string;
    scriptRevision: number;
    finalSpeechHash?: string | null;
    reason?: string | null;
  }>;
  contractVersion: string;
  updatedAt?: string | null;
  legacyFallback?: boolean;
}

const editorAssistInFlight = new Map<string, Promise<EditorAssistResult>>();

export function runScriptEditorAssist(input: ScriptEditorAssistInput): Promise<EditorAssistResult> {
  const key = JSON.stringify(input);
  const existing = editorAssistInFlight.get(key);
  if (existing) return existing;
  const request = postJson<EditorAssistResult>("/api/scripts/editor-assist", input).finally(() => {
    editorAssistInFlight.delete(key);
  });
  editorAssistInFlight.set(key, request);
  return request;
}

export async function fetchScriptEditorState(scriptId: string): Promise<ScriptEditorState> {
  const response = await requestJson<{ ok: boolean; state: ScriptEditorState }>(
    `/api/scripts/${encodeURIComponent(scriptId)}/editor-state`,
    { method: "GET" },
  );
  return response.state;
}

export async function saveScriptEditorState(
  scriptId: string,
  state: Omit<
    ScriptEditorState,
    | "scriptId"
    | "scriptRevision"
    | "finalSpeechHash"
    | "approvedScriptRevision"
    | "approvedFinalSpeechHash"
    | "approvalHistory"
    | "contractVersion"
    | "updatedAt"
    | "legacyFallback"
  >,
): Promise<ScriptEditorState> {
  const response = await requestJson<{ ok: boolean; state: ScriptEditorState }>(
    `/api/scripts/${encodeURIComponent(scriptId)}/editor-state`,
    { method: "PUT", body: JSON.stringify(state) },
  );
  return response.state;
}

export async function naturalizeScript(input: {
  text: string;
  medicalCautions: string;
  durationSeconds: DurationPreset;
  outro: string;
  ctaMode?: "auto" | "manual" | "none" | "visual";
  manualCta?: string;
  recentCtas?: string[];
  generationMode?: GenerationMode;
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
    voiceMood: VoiceMood;
    captions: boolean;
    optimizePronunciation: boolean;
    displayText: string;
    spokenText?: string;
    idempotencyKey?: string;
    finalConfirmed?: boolean;
    expectedScriptRevision?: number;
    expectedFinalSpeechHash?: string;
    contractVersion?: string;
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

export function videoFileUrl(jobId: string): string {
  return `${BASE}/api/videos/${encodeURIComponent(jobId)}/file`;
}

export type PostProductionStatus =
  | "queued"
  | "transcribing"
  | "planning"
  | "preflight"
  | "generating_pack"
  | "rendering_preview"
  | "preview_ready"
  | "failed"
  | "cancelled"
  | "stale"
  | "needs_review";

export interface PostProductionJob {
  id: string;
  kind: "post_production";
  videoJobId?: string | null;
  uploadId?: string | null;
  sourceName?: string;
  status: PostProductionStatus;
  progresso: number;
  etapa: string;
  captionsStatus?: "ready" | "failed";
  captionsPath?: string;
  captionCueCount?: number;
  criadoEm: string;
  atualizadoEm: string;
  erro?: string;
  plannerMode?: "cache" | "fallback" | "anthropic";
  requireClaude?: boolean;
  generatePack?: boolean;
  packStatus?: "ready" | "failed";
  packPath?: string;
  packImageCount?: number;
  packError?: string;
}

export type VisualScreenPosition =
  | "top_left"
  | "top_center"
  | "top_right"
  | "center_left"
  | "center"
  | "center_right"
  | "bottom_left"
  | "bottom_center"
  | "bottom_right";

export interface VisualTimelineEvent {
  id: string;
  startWordIndex: number;
  endWordIndex: number;
  startMs: number;
  endMs: number;
  timingSource?: "transcript" | "manual";
  screenPosition?: VisualScreenPosition;
  backgroundColor?: string;
  backgroundOpacity?: number;
  spokenText: string;
  interactionType:
    | "none"
    | "caption_emphasis"
    | "kinetic_text"
    | "progressive_list"
    | "supporting_visual"
    | "cta_card"
    | "definition_card"
    | "number_card"
    | "comparison_card"
    | "quote_card"
    | "evidence_card";
  visualText: string;
  assetRef?: string | null;
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
  visualPlan?: {
    modelVersion?: string | null;
    contentType?: string | null;
    summary?: string | null;
    strategy?: string | null;
    noVisualReason?: string | null;
  } | null;
}

export interface GeneratedContentPack {
  pack: {
    schemaVersion?: string;
    caption?: string;
    hashtags?: string[];
    family?: string;
    themeId?: string;
    carousel?: Array<{
      layoutId?: string;
      variant?: string;
      fields?: Record<string, unknown>;
    }>;
    slides?: Array<{
      layoutId?: string;
      variant?: string;
      fields?: Record<string, unknown>;
    }>;
  };
  images: string[];
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

export async function createPostProduction(
  videoJobId: string,
  autoRender = false,
  options?: { requireClaude?: boolean; generatePack?: boolean },
): Promise<PostProductionJob> {
  const response = await postJson<{ job: PostProductionJob }>("/api/post-production", {
    videoJobId,
    autoRender,
    requireClaude: options?.requireClaude ?? false,
    generatePack: options?.generatePack ?? false,
  });
  return response.job;
}

export async function createUploadedPostProduction(
  uploadId: string,
  sourceName: string,
): Promise<PostProductionJob> {
  const response = await postJson<{ job: PostProductionJob }>("/api/post-production", {
    uploadId,
    sourceName,
    autoRender: false,
    requireClaude: true,
    generatePack: true,
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

export async function fetchLatestPostProduction(
  videoJobId: string,
): Promise<PostProductionJob | null> {
  const response = await requestJson<{ job: PostProductionJob | null }>(
    `/api/videos/${encodeURIComponent(videoJobId)}/post-production`,
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

export async function fetchPostProductionPack(jobId: string): Promise<GeneratedContentPack> {
  const response = await requestJson<GeneratedContentPack>(
    `/api/post-production/${encodeURIComponent(jobId)}/pack`,
    {},
  );
  return {
    ...response,
    images: response.images.map((path) => (path.startsWith("http") ? path : `${BASE}${path}`)),
  };
}

export async function updatePostProductionEvents(
  jobId: string,
  events: Array<
    Pick<VisualTimelineEvent, "id"> &
      Partial<
        Pick<
          VisualTimelineEvent,
          | "enabled"
          | "startMs"
          | "endMs"
          | "timingSource"
          | "screenPosition"
          | "backgroundColor"
          | "backgroundOpacity"
          | "visualText"
          | "reviewStatus"
          | "interactionType"
        >
      >
  >,
): Promise<{ job: PostProductionJob; timeline: PostProductionArtifacts["timeline"] }> {
  return requestJson(`/api/post-production/${encodeURIComponent(jobId)}/events`, {
    method: "PATCH",
    body: JSON.stringify({ events }),
  });
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

export interface LocalVideoKitInsert {
  id: string;
  uploadId: string;
  sourceName: string;
  sourceDurationSeconds: number;
  timelineStartSeconds: number;
  timelineEndSeconds: number;
  sourceStartSeconds: number;
  sourceEndSeconds: number;
}

export interface LocalVideoKitInsertAsset {
  uploadId: string;
  filename: string;
  size: number;
  durationSeconds: number;
}

export interface LocalVideoKitFiveStack {
  enabled: boolean;
  startSeconds?: number | null;
  durationSeconds?: number | null;
  lines: string[];
}

export type LocalVideoKitClaudeModelId =
  "numberGlass" | "editorialClip" | "mechanismBars" | "evidenceStamp" | "glossarySource";

export interface LocalVideoKitClaudeModel {
  enabled: boolean;
  startSeconds?: number | null;
  durationSeconds?: number | null;
  fields: string[];
}

export type LocalVideoKitClaudeInserts = Record<
  LocalVideoKitClaudeModelId,
  LocalVideoKitClaudeModel
>;

export interface LocalVideoKitConfig {
  name: string;
  role: string;
  title: string;
  subtitle: string;
  sectionNumber: string;
  sectionTitle: string;
  cta: string;
  site: string;
  accent: string;
  sectionStartSeconds?: number | null;
  sectionDurationSeconds?: number | null;
  sectionTransition?: "none" | "fade" | "slide_up" | null;
  musicTrackId?: string | null;
  musicVolume?: number;
  includeCaptions: boolean;
  captionStyle: "dynamic" | "clean" | "editorial";
  captionPosition: "safe_bottom" | "center" | "upper";
  highlightKeywords: boolean;
  duckMusicDuringSpeech: boolean;
  motionPreset: "none" | "subtle" | "social";
  enhanceVoice: boolean;
  outroTailSeconds?: number;
  includeOpening: boolean;
  includeLowerThird: boolean;
  includeSection: boolean;
  includeOutro: boolean;
  manualVisualsEnabled?: boolean;
  inserts: LocalVideoKitInsert[];
  fiveStack?: LocalVideoKitFiveStack;
  claudeInserts?: LocalVideoKitClaudeInserts;
}

export interface LocalVideoKitJob {
  id: string;
  status: "fila" | "processando" | "pronto" | "erro";
  progresso: number;
  etapa: string;
  sourceName: string;
  sourcePath: string;
  sourceVideoJobId?: string | null;
  sourceKitJobId?: string | null;
  analysisJobId?: string | null;
  transcriptReused?: boolean;
  outputPath: string;
  coverPath?: string;
  config: LocalVideoKitConfig;
  externalCreditsUsed: false;
  duracaoSegundos?: number;
  erro?: string;
  criadoEm: string;
  atualizadoEm: string;
}

export async function uploadLocalVideoKitSource(file: File): Promise<{
  uploadId: string;
  filename: string;
  size: number;
}> {
  const response = await fetch(`${BASE}/api/local-video-kit/uploads`, {
    method: "POST",
    headers: {
      "Content-Type": file.type || "video/mp4",
      "X-Filename": encodeURIComponent(file.name),
    },
    body: file,
  });
  if (!response.ok) {
    throw new Error(await errorDetail(response, "Não foi possível enviar o vídeo local."));
  }
  return (await response.json()) as {
    uploadId: string;
    filename: string;
    size: number;
  };
}

export async function uploadLocalVideoKitInsert(file: File): Promise<LocalVideoKitInsertAsset> {
  const response = await fetch(`${BASE}/api/local-video-kit/insert-uploads`, {
    method: "POST",
    headers: {
      "Content-Type": file.type || "video/mp4",
      "X-Filename": encodeURIComponent(file.name),
    },
    body: file,
  });
  if (!response.ok) {
    throw new Error(await errorDetail(response, "Não foi possível enviar o clipe de insert."));
  }
  return (await response.json()) as LocalVideoKitInsertAsset;
}

export async function createLocalVideoKit(input: {
  uploadId?: string;
  videoJobId?: string;
  sourceKitJobId?: string;
  analysisJobId?: string;
  sourceName: string;
  config: LocalVideoKitConfig;
}): Promise<LocalVideoKitJob> {
  const response = await postJson<{ ok: boolean; job: LocalVideoKitJob }>("/api/local-video-kit", {
    uploadId: input.uploadId,
    videoJobId: input.videoJobId,
    sourceKitJobId: input.sourceKitJobId,
    analysisJobId: input.analysisJobId,
    sourceName: input.sourceName,
    ...input.config,
  });
  return response.job;
}

export async function fetchLocalVideoKit(jobId: string): Promise<LocalVideoKitJob> {
  const response = await requestJson<{ job: LocalVideoKitJob }>(
    `/api/local-video-kit/${encodeURIComponent(jobId)}`,
    {},
  );
  return response.job;
}

export async function retryLocalVideoKit(jobId: string): Promise<LocalVideoKitJob> {
  const response = await postJson<{ job: LocalVideoKitJob }>(
    `/api/local-video-kit/${encodeURIComponent(jobId)}/retry`,
    {},
  );
  return response.job;
}

export async function fetchLocalVideoKitJobs(): Promise<LocalVideoKitJob[]> {
  const response = await requestJson<{ jobs: LocalVideoKitJob[] }>("/api/local-video-kit", {});
  return response.jobs;
}

export function localVideoKitSourceUrl(jobId: string): string {
  return `${BASE}/api/local-video-kit/${encodeURIComponent(jobId)}/source`;
}

export function localVideoKitResultUrl(jobId: string, download = false): string {
  return `${BASE}/api/local-video-kit/${encodeURIComponent(jobId)}/result${download ? "?download=true" : ""}`;
}

export function localVideoKitCoverUrl(jobId: string, download = false): string {
  return `${BASE}/api/local-video-kit/${encodeURIComponent(jobId)}/cover${download ? "?download=true" : ""}`;
}

export function localVideoKitInsertUrl(uploadId: string): string {
  return `${BASE}/api/local-video-kit/insert-uploads/${encodeURIComponent(uploadId)}`;
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

export async function refreshHeyGenVideo(
  jobId: string,
): Promise<{ job: VideoJob; composedJob?: VideoJob | null }> {
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
    const body = (await res.json()) as {
      detail?: string | { code?: string; message?: string };
    };
    if (typeof body.detail === "string") return body.detail;
    if (body.detail?.message) return body.detail.message;
    return fallback;
  } catch {
    return fallback;
  }
}
