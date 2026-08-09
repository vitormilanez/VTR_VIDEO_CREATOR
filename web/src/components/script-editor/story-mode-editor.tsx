import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import {
  BookOpen,
  Check,
  CircleDollarSign,
  Clapperboard,
  FileUp,
  History,
  Loader2,
  LockKeyhole,
  RefreshCw,
  RotateCcw,
  Save,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from "lucide-react";

import { ConfirmAction } from "@/components/confirm-action";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  approveStoryVersion,
  critiqueStoryVersion,
  fetchHeyGenProviderCapabilities,
  fetchStoryProject,
  generateStoryShot,
  planStory,
  refreshStoryShot,
  reviseStoryVersion,
  saveStoryBrief,
  type HeyGenProviderCapabilities,
  type StoryBindings,
  type StoryBrief,
  type StoryPlan,
  type StoryPlanShot,
  type StoryProject,
  type StoryShotRecord,
  type StoryVersion,
  storyShotMediaUrl,
} from "@/lib/api/local";
import { cn } from "@/lib/utils";

type RequestName =
  "save" | "plan" | "revise" | "critique" | "approve" | "generate" | "refresh" | null;
type ShotControls = StoryShotRecord["controls"];

interface StorySnapshot {
  plan: StoryPlan;
  reviews: ShotControls[];
  storyBibleApproved: boolean;
}

export interface StoryEditorState {
  phase: "loading" | "ready" | "error";
  error: string | null;
  pending: RequestName;
  project: StoryProject | null;
  bindings: StoryBindings | null;
  capabilities: HeyGenProviderCapabilities | null;
  brief: StoryBrief;
  version: StoryVersion | null;
  plan: StoryPlan | null;
  reviews: ShotControls[];
  storyBibleApproved: boolean;
  dirty: boolean;
  history: StorySnapshot[];
  announcement: string;
}

type StoryEditorAction =
  | { type: "load-start" }
  | {
      type: "load-success";
      project: StoryProject | null;
      bindings: StoryBindings;
      capabilities: HeyGenProviderCapabilities;
    }
  | { type: "load-error"; message: string }
  | { type: "brief-change"; brief: StoryBrief }
  | { type: "request-start"; request: Exclude<RequestName, null> }
  | { type: "request-error"; message: string }
  | { type: "project-saved"; project: StoryProject; message: string }
  | { type: "version-loaded"; project: StoryProject; version: StoryVersion; message: string }
  | { type: "shot-change"; index: number; shot: StoryPlanShot }
  | { type: "review-change"; index: number; controls: ShotControls }
  | { type: "bible-approval"; approved: boolean }
  | { type: "undo" }
  | { type: "critique-loaded"; version: StoryVersion; message: string }
  | { type: "approved"; project: StoryProject; version: StoryVersion };

function defaultControls(): ShotControls {
  return {
    promptOverride: "",
    lockIdentity: true,
    lockWardrobe: true,
    lockEnvironment: false,
    approved: false,
  };
}

function cloneSnapshot(state: StoryEditorState): StorySnapshot | null {
  if (!state.plan) return null;
  return {
    plan: structuredClone(state.plan),
    reviews: structuredClone(state.reviews),
    storyBibleApproved: state.storyBibleApproved,
  };
}

function versionState(version: StoryVersion) {
  const reviews = version.plan.shots.map((_, index) =>
    structuredClone(version.shots?.[index]?.controls ?? defaultControls()),
  );
  return {
    version,
    plan: structuredClone(version.plan),
    reviews,
    storyBibleApproved: version.storyBibleApproved,
  };
}

export function makeStoryEditorState(brief: StoryBrief): StoryEditorState {
  return {
    phase: "loading",
    error: null,
    pending: null,
    project: null,
    bindings: null,
    capabilities: null,
    brief,
    version: null,
    plan: null,
    reviews: [],
    storyBibleApproved: false,
    dirty: false,
    history: [],
    announcement: "Carregando Story Mode.",
  };
}

export function storyModeReducer(
  state: StoryEditorState,
  action: StoryEditorAction,
): StoryEditorState {
  if (action.type === "load-start") {
    return { ...state, phase: "loading", error: null, announcement: "Carregando Story Mode." };
  }
  if (action.type === "load-error" || action.type === "request-error") {
    return {
      ...state,
      phase: action.type === "load-error" ? "error" : "ready",
      pending: null,
      error: action.message,
      announcement: action.message,
    };
  }
  if (action.type === "load-success") {
    const version = action.project?.activeVersion ?? null;
    const active = version ? versionState(version) : null;
    return {
      ...state,
      phase: "ready",
      error: null,
      pending: null,
      project: action.project,
      bindings: action.bindings,
      capabilities: action.capabilities,
      brief: action.project?.brief ?? state.brief,
      version,
      plan: active?.plan ?? null,
      reviews: active?.reviews ?? [],
      storyBibleApproved: active?.storyBibleApproved ?? false,
      dirty: false,
      history: [],
      announcement: version
        ? `Storyboard revisão ${version.storyRevision} carregado.`
        : "Briefing pronto para começar.",
    };
  }
  if (action.type === "brief-change") {
    return { ...state, brief: action.brief, error: null };
  }
  if (action.type === "request-start") {
    return {
      ...state,
      pending: action.request,
      error: null,
      announcement: "Processando solicitação.",
    };
  }
  if (action.type === "project-saved") {
    return {
      ...state,
      project: action.project,
      brief: action.project.brief,
      pending: null,
      error: null,
      announcement: action.message,
    };
  }
  if (action.type === "version-loaded") {
    const active = versionState(action.version);
    return {
      ...state,
      ...active,
      project: action.project,
      pending: null,
      error: null,
      dirty: false,
      history: [],
      announcement: action.message,
    };
  }
  if (action.type === "shot-change" || action.type === "review-change") {
    const snapshot = cloneSnapshot(state);
    if (!snapshot || !state.plan) return state;
    if (action.type === "shot-change") {
      const shots = state.plan.shots.map((shot, index) =>
        index === action.index ? action.shot : shot,
      );
      return {
        ...state,
        plan: { ...state.plan, shots },
        dirty: true,
        history: [...state.history, snapshot],
        error: null,
      };
    }
    const reviews = state.reviews.map((review, index) =>
      index === action.index ? action.controls : review,
    );
    return {
      ...state,
      reviews,
      dirty: true,
      history: [...state.history, snapshot],
      error: null,
    };
  }
  if (action.type === "bible-approval") {
    const snapshot = cloneSnapshot(state);
    if (!snapshot) return state;
    return {
      ...state,
      storyBibleApproved: action.approved,
      dirty: true,
      history: [...state.history, snapshot],
      error: null,
    };
  }
  if (action.type === "undo") {
    const snapshot = state.history.at(-1);
    if (!snapshot) return state;
    return {
      ...state,
      plan: snapshot.plan,
      reviews: snapshot.reviews,
      storyBibleApproved: snapshot.storyBibleApproved,
      dirty: true,
      history: state.history.slice(0, -1),
      announcement: "Última edição desfeita.",
    };
  }
  if (action.type === "critique-loaded") {
    return {
      ...state,
      version: action.version,
      pending: null,
      error: null,
      announcement: action.message,
    };
  }
  if (action.type === "approved") {
    return {
      ...state,
      project: action.project,
      version: action.version,
      pending: null,
      error: null,
      announcement: "Story Plan e orçamento aprovados.",
    };
  }
  return state;
}

export function canCritiqueStory(state: StoryEditorState) {
  return Boolean(
    state.version &&
    state.plan &&
    !state.dirty &&
    state.storyBibleApproved &&
    state.reviews.length === state.plan.shots.length &&
    state.reviews.every((review) => review.approved),
  );
}

export function canApproveStory(state: StoryEditorState) {
  const critique = state.version?.activeCritique;
  return Boolean(
    canCritiqueStory(state) &&
    critique?.critique.decision === "ready" &&
    critique.budget.approvalEligible &&
    !state.version?.approved,
  );
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Não foi possível concluir a ação.";
}

function money(value: number | null) {
  return value === null
    ? "Taxa não configurada"
    : new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD" }).format(value);
}

function storyBriefDefaults({
  title,
  durationSeconds,
  orientation,
  characterId,
  lookId,
  characterDescription,
  wardrobeDirection,
}: Omit<StoryModeEditorProps, "scriptId">): StoryBrief {
  return {
    storyType: "narrative_explainer",
    educationalGoal: `Explicar ${title} com clareza, continuidade visual e rigor editorial.`,
    period: "",
    location: "",
    realismLevel: "high",
    historicalAccuracy: "not_applicable",
    tone: "curious_educational",
    durationSeconds,
    orientation,
    productionTier: "cinematic",
    maxHeyGenJobs: 6,
    maxRegenerationsPerShot: 1,
    maxBudgetUsd: null,
    characterId,
    lookId,
    characterDescription,
    wardrobeDirection,
    referenceAssets: [],
  };
}

function LoadingState() {
  return (
    <div className="space-y-3" aria-label="Carregando Story Mode">
      <Skeleton className="h-14 w-full" />
      <div className="grid gap-3 md:grid-cols-2">
        <Skeleton className="h-44" />
        <Skeleton className="h-44" />
      </div>
    </div>
  );
}

function StepRail({ active }: { active: number }) {
  const steps = ["Briefing", "Story Bible", "Storyboard", "Orçamento"];
  return (
    <ol className="grid gap-2 sm:grid-cols-4" aria-label="Etapas da história cinematográfica">
      {steps.map((label, index) => {
        const number = index + 1;
        const complete = number < active;
        return (
          <li
            key={label}
            aria-current={number === active ? "step" : undefined}
            className={cn(
              "flex min-h-11 items-center gap-2 rounded-lg border px-3 text-xs font-medium",
              number === active && "border-primary bg-primary/5 text-foreground",
              complete && "border-status-success/30 bg-status-success/5",
            )}
          >
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border bg-background text-[11px]">
              {complete ? <Check className="h-3.5 w-3.5 text-status-success" /> : number}
            </span>
            {label}
          </li>
        );
      })}
    </ol>
  );
}

function BriefField({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  );
}

function StoryBriefForm({
  brief,
  pending,
  onChange,
  onReference,
  onSave,
  onPlan,
}: {
  brief: StoryBrief;
  pending: RequestName;
  onChange: (brief: StoryBrief) => void;
  onReference: (file: File) => void;
  onSave: () => void;
  onPlan: () => void;
}) {
  const planningReady = brief.educationalGoal.trim().length >= 10 && brief.maxBudgetUsd !== null;
  return (
    <Card>
      <CardHeader className="p-4">
        <CardTitle className="flex items-center gap-2 text-sm">
          <BookOpen className="h-4 w-4 text-primary" /> Story Brief
        </CardTitle>
        <CardDescription className="text-xs leading-5">
          Defina intenção, limites e orçamento antes de pedir qualquer planejamento ao Claude.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 p-4 pt-0">
        <div className="grid gap-3 md:grid-cols-2">
          <BriefField label="Tipo de história" htmlFor="story-type">
            <Select
              value={brief.storyType}
              onValueChange={(value) =>
                onChange({ ...brief, storyType: value as StoryBrief["storyType"] })
              }
            >
              <SelectTrigger id="story-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="historical_explainer">Explicação histórica</SelectItem>
                <SelectItem value="medical_explainer">Explicação médica</SelectItem>
                <SelectItem value="narrative_explainer">Explicação narrativa</SelectItem>
              </SelectContent>
            </Select>
          </BriefField>
          <BriefField label="Tom" htmlFor="story-tone">
            <Select
              value={brief.tone}
              onValueChange={(value) => onChange({ ...brief, tone: value as StoryBrief["tone"] })}
            >
              <SelectTrigger id="story-tone">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="curious_educational">Curioso e educativo</SelectItem>
                <SelectItem value="documentary">Documental</SelectItem>
                <SelectItem value="warm_explainer">Acolhedor</SelectItem>
                <SelectItem value="dramatic_restrained">Dramático contido</SelectItem>
              </SelectContent>
            </Select>
          </BriefField>
        </div>
        <BriefField label="Objetivo educacional" htmlFor="story-goal">
          <Textarea
            id="story-goal"
            rows={3}
            value={brief.educationalGoal}
            onChange={(event) => onChange({ ...brief, educationalGoal: event.target.value })}
          />
        </BriefField>
        <div className="grid gap-3 md:grid-cols-2">
          <BriefField label="Período" htmlFor="story-period">
            <Input
              id="story-period"
              value={brief.period}
              onChange={(event) => onChange({ ...brief, period: event.target.value })}
              placeholder="Ex.: década de 1920"
            />
          </BriefField>
          <BriefField label="Local" htmlFor="story-location">
            <Input
              id="story-location"
              value={brief.location}
              onChange={(event) => onChange({ ...brief, location: event.target.value })}
              placeholder="Ex.: São Paulo"
            />
          </BriefField>
          <BriefField label="Realismo" htmlFor="story-realism">
            <Select
              value={brief.realismLevel}
              onValueChange={(value) =>
                onChange({ ...brief, realismLevel: value as StoryBrief["realismLevel"] })
              }
            >
              <SelectTrigger id="story-realism">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="high">Alto</SelectItem>
                <SelectItem value="medium">Médio</SelectItem>
                <SelectItem value="stylized">Estilizado</SelectItem>
              </SelectContent>
            </Select>
          </BriefField>
          <BriefField label="Precisão histórica" htmlFor="story-accuracy">
            <Select
              value={brief.historicalAccuracy}
              onValueChange={(value) =>
                onChange({
                  ...brief,
                  historicalAccuracy: value as StoryBrief["historicalAccuracy"],
                })
              }
            >
              <SelectTrigger id="story-accuracy">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="strict">Estrita</SelectItem>
                <SelectItem value="inspired">Inspirada</SelectItem>
                <SelectItem value="not_applicable">Não se aplica</SelectItem>
              </SelectContent>
            </Select>
          </BriefField>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <BriefField label="Duração (segundos)" htmlFor="story-duration">
            <Input
              id="story-duration"
              type="number"
              min={10}
              max={180}
              value={brief.durationSeconds}
              onChange={(event) =>
                onChange({ ...brief, durationSeconds: Number(event.target.value) })
              }
            />
          </BriefField>
          <BriefField label="Máximo de jobs HeyGen" htmlFor="story-jobs">
            <Input
              id="story-jobs"
              type="number"
              min={0}
              max={12}
              value={brief.maxHeyGenJobs}
              onChange={(event) =>
                onChange({ ...brief, maxHeyGenJobs: Number(event.target.value) })
              }
            />
          </BriefField>
          <BriefField label="Regenerações por shot" htmlFor="story-regens">
            <Input
              id="story-regens"
              type="number"
              min={0}
              max={2}
              value={brief.maxRegenerationsPerShot}
              onChange={(event) =>
                onChange({ ...brief, maxRegenerationsPerShot: Number(event.target.value) })
              }
            />
          </BriefField>
          <BriefField label="Teto de orçamento (USD)" htmlFor="story-budget">
            <Input
              id="story-budget"
              type="number"
              min={0}
              step="0.01"
              value={brief.maxBudgetUsd ?? ""}
              onChange={(event) =>
                onChange({
                  ...brief,
                  maxBudgetUsd: event.target.value === "" ? null : Number(event.target.value),
                })
              }
              placeholder="Obrigatório"
            />
          </BriefField>
        </div>
        <BriefField label="Descrição do personagem" htmlFor="story-character">
          <Textarea
            id="story-character"
            rows={2}
            value={brief.characterDescription}
            onChange={(event) => onChange({ ...brief, characterDescription: event.target.value })}
          />
        </BriefField>
        <BriefField label="Direção de figurino" htmlFor="story-wardrobe">
          <Input
            id="story-wardrobe"
            value={brief.wardrobeDirection}
            onChange={(event) => onChange({ ...brief, wardrobeDirection: event.target.value })}
          />
        </BriefField>
        <div className="rounded-lg border border-dashed p-3">
          <Label
            htmlFor="story-reference"
            className="flex min-h-11 cursor-pointer items-center gap-2 text-sm"
          >
            <FileUp className="h-4 w-4 text-primary" /> Adicionar referência local
          </Label>
          <Input
            id="story-reference"
            type="file"
            accept="image/*,video/*,.pdf"
            className="sr-only"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) onReference(file);
              event.currentTarget.value = "";
            }}
          />
          <p className="text-xs text-muted-foreground">
            Nesta fase, guardamos hash e descrição; o arquivo não é enviado a nenhum provedor.
          </p>
          {brief.referenceAssets.length ? (
            <ul className="mt-2 space-y-1 text-xs">
              {brief.referenceAssets.map((asset) => (
                <li key={asset.id} className="truncate">
                  {asset.description} · {asset.sha256.slice(0, 10)}…
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="outline" onClick={onSave} disabled={pending !== null}>
            {pending === "save" ? <Loader2 className="animate-spin" /> : <Save />} Salvar brief
          </Button>
          <ConfirmAction
            title="Planejar a história com Claude?"
            description="Esta ação faz 1 chamada ao Anthropic. Nenhum job HeyGen será criado."
            confirmLabel="Planejar história"
            confirmDisabled={!planningReady || pending !== null}
            onConfirm={onPlan}
            trigger={
              <Button type="button" disabled={!planningReady || pending !== null}>
                {pending === "plan" ? <Loader2 className="animate-spin" /> : <Sparkles />} Planejar
                com Claude
              </Button>
            }
          />
        </div>
        {!planningReady ? (
          <p className="text-right text-xs text-status-warn-foreground">
            Preencha o objetivo e defina um teto de orçamento.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function BibleCard({
  plan,
  approved,
  disabled,
  onApproved,
}: {
  plan: StoryPlan;
  approved: boolean;
  disabled: boolean;
  onApproved: (approved: boolean) => void;
}) {
  return (
    <Card>
      <CardHeader className="p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-sm">
              <BookOpen className="h-4 w-4 text-primary" /> Story Bible
            </CardTitle>
            <CardDescription className="mt-1 text-xs">
              A base narrativa, visual e de continuidade que todos os shots devem respeitar.
            </CardDescription>
          </div>
          <div className="flex min-h-11 items-center gap-2 rounded-lg border px-3">
            <Label htmlFor="story-bible-approved" className="text-xs">
              Bible revisada
            </Label>
            <Switch
              id="story-bible-approved"
              checked={approved}
              disabled={disabled}
              onCheckedChange={onApproved}
            />
          </div>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3 p-4 pt-0 md:grid-cols-2">
        <div className="rounded-lg border bg-muted/20 p-3 md:col-span-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Premissa
          </p>
          <p className="mt-1 text-sm leading-6">{plan.storyBible.premise}</p>
        </div>
        <div className="rounded-lg border p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Arco narrativo
          </p>
          <ol className="mt-2 space-y-1.5 text-xs leading-5">
            <li>
              <strong>Abertura:</strong> {plan.storyBible.narrativeArc.opening}
            </li>
            <li>
              <strong>Desenvolvimento:</strong> {plan.storyBible.narrativeArc.development}
            </li>
            <li>
              <strong>Virada:</strong> {plan.storyBible.narrativeArc.turn}
            </li>
            <li>
              <strong>Final:</strong> {plan.storyBible.narrativeArc.ending}
            </li>
          </ol>
        </div>
        <div className="rounded-lg border p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Continuidade
          </p>
          <dl className="mt-2 space-y-1.5 text-xs leading-5">
            <div>
              <dt className="inline font-semibold">Identidade: </dt>
              <dd className="inline">{plan.characterBible.identityRule}</dd>
            </div>
            <div>
              <dt className="inline font-semibold">Figurino: </dt>
              <dd className="inline">{plan.characterBible.wardrobe.base}</dd>
            </div>
            <div>
              <dt className="inline font-semibold">Câmera: </dt>
              <dd className="inline">{plan.visualBible.cameraStyle}</dd>
            </div>
            <div>
              <dt className="inline font-semibold">Luz: </dt>
              <dd className="inline">{plan.visualBible.lighting}</dd>
            </div>
          </dl>
        </div>
      </CardContent>
    </Card>
  );
}

function ShotCard({
  shot,
  controls,
  record,
  characterId,
  lookId,
  disabled,
  generationDisabled,
  onShotChange,
  onControlsChange,
  onGenerate,
  onRefresh,
}: {
  shot: StoryPlanShot;
  controls: ShotControls;
  record?: StoryShotRecord;
  characterId: string | null;
  lookId: string | null;
  disabled: boolean;
  generationDisabled: boolean;
  onShotChange: (shot: StoryPlanShot) => void;
  onControlsChange: (controls: ShotControls) => void;
  onGenerate: (regenerate: boolean) => void;
  onRefresh: () => void;
}) {
  const lockItems = [
    ["lockIdentity", "Travar identidade"],
    ["lockWardrobe", "Travar figurino"],
    ["lockEnvironment", "Travar ambiente"],
  ] as const;
  const generation = record?.currentGeneration;
  const canGenerate = !generationDisabled && controls.approved && Boolean(record);
  function changeStrategy(strategy: StoryPlanShot["strategy"]) {
    const avatar = strategy === "avatar_anchor";
    const local = strategy === "local_transition";
    onShotChange({
      ...shot,
      strategy,
      shotType: avatar ? "avatar_anchor" : local ? "transition" : "historical_broll",
      providerStrategy: avatar ? "direct_video" : local ? "local_compositor" : "video_agent",
      speech: {
        ...shot.speech,
        mode: avatar ? "avatar_speaks" : "voice_continues_from_base_scene",
      },
      character: avatar
        ? { required: true, characterId, lookId }
        : { required: false, characterId: null, lookId: null },
      audioPolicy: avatar ? "preserve_base_narration" : "mute_generated_audio",
      estimatedCost: { heygenJobs: local ? 0 : 1, anthropicCalls: 0 },
    });
  }
  return (
    <Card className={cn("shadow-sm", controls.approved && "border-status-success/40")}>
      <CardHeader className="p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Clapperboard className="h-4 w-4 text-primary" /> Shot{" "}
              {String(shot.order).padStart(2, "0")}
            </CardTitle>
            <CardDescription className="mt-1 text-xs">
              Palavras {shot.speech.startWordIndex + 1}–{shot.speech.endWordIndex + 1} ·{" "}
              {shot.strategy.replaceAll("_", " ")}
            </CardDescription>
          </div>
          <Badge variant={controls.approved ? "default" : "outline"}>
            {controls.approved ? "Aprovado" : "Em revisão"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 p-4 pt-0">
        {generation?.status === "completed" ? (
          <video
            controls
            preload="metadata"
            className="aspect-[9/16] max-h-[420px] w-full rounded-lg bg-black object-contain"
            src={storyShotMediaUrl(generation)}
          />
        ) : null}
        <div className="grid gap-3 sm:grid-cols-2">
          <BriefField label="Estratégia" htmlFor={`${shot.id}-strategy`}>
            <Select
              value={shot.strategy}
              disabled={disabled}
              onValueChange={(value) => changeStrategy(value as StoryPlanShot["strategy"])}
            >
              <SelectTrigger id={`${shot.id}-strategy`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="avatar_anchor" disabled={!characterId || !lookId}>
                  Avatar falando · HeyGen Direct
                </SelectItem>
                <SelectItem value="cinematic_broll">
                  B-roll cinematográfico · Video Agent
                </SelectItem>
                <SelectItem value="local_transition">Transição · render local</SelectItem>
              </SelectContent>
            </Select>
          </BriefField>
          <BriefField label="Duração do shot" htmlFor={`${shot.id}-duration`}>
            <Input
              id={`${shot.id}-duration`}
              type="number"
              min={1}
              max={30}
              step="0.5"
              value={shot.durationSeconds}
              disabled={disabled}
              onChange={(event) =>
                onShotChange({ ...shot, durationSeconds: Number(event.target.value) })
              }
            />
          </BriefField>
        </div>
        <div className="rounded-lg border bg-muted/20 p-3 text-xs leading-5">
          <p className="font-semibold">{shot.subject}</p>
          <p className="text-muted-foreground">
            {shot.period || "Período contemporâneo"} · {shot.wardrobe || "Sem figurino em quadro"}
          </p>
          <p className="mt-1 text-muted-foreground">{shot.atmosphere}</p>
        </div>
        <BriefField label="Ambiente" htmlFor={`${shot.id}-environment`}>
          <Textarea
            id={`${shot.id}-environment`}
            rows={2}
            value={shot.environment}
            disabled={disabled}
            onChange={(event) => onShotChange({ ...shot, environment: event.target.value })}
          />
        </BriefField>
        <BriefField label="Ação" htmlFor={`${shot.id}-action`}>
          <Textarea
            id={`${shot.id}-action`}
            rows={2}
            value={shot.action}
            disabled={disabled}
            onChange={(event) => onShotChange({ ...shot, action: event.target.value })}
          />
        </BriefField>
        <BriefField label="Prompt final do HeyGen" htmlFor={`${shot.id}-prompt`}>
          <Textarea
            id={`${shot.id}-prompt`}
            rows={3}
            value={controls.promptOverride || shot.heygenPrompt}
            disabled={disabled}
            onChange={(event) =>
              onControlsChange({ ...controls, promptOverride: event.target.value })
            }
            placeholder="Prompt visual estruturado pelo Claude, sem fala nova."
          />
          <p className="text-[11px] text-muted-foreground">
            Criado pelo Claude no Story Plan. Editar e salvar gera uma nova revisão do storyboard.
          </p>
        </BriefField>
        <div className="grid gap-2 sm:grid-cols-3">
          {lockItems.map(([key, label]) => (
            <div
              key={key}
              className="flex min-h-11 items-center justify-between gap-2 rounded-lg border px-3"
            >
              <Label htmlFor={`${shot.id}-${key}`} className="flex items-center gap-1.5 text-xs">
                <LockKeyhole className="h-3.5 w-3.5" /> {label}
              </Label>
              <Switch
                id={`${shot.id}-${key}`}
                checked={controls[key]}
                disabled={disabled}
                onCheckedChange={(checked) => onControlsChange({ ...controls, [key]: checked })}
              />
            </div>
          ))}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3">
          <p className="text-xs text-muted-foreground">
            {shot.estimatedCost.heygenJobs
              ? `HeyGen: ${shot.estimatedCost.heygenJobs} job · ${generation?.estimatedCostUsd == null ? "custo conforme taxa configurada" : money(generation.estimatedCostUsd)}`
              : "Render local · zero crédito HeyGen"}
            {generation ? ` · status: ${generation.status.replaceAll("_", " ")}` : " · pronto"}
          </p>
          <div className="flex gap-2">
            {generation?.status === "generating" || generation?.status === "submitted" ? (
              <Button
                type="button"
                variant="outline"
                disabled={generationDisabled}
                onClick={onRefresh}
              >
                <RefreshCw /> Atualizar status
              </Button>
            ) : generation?.status === "completed" ||
              generation?.status === "failed" ||
              generation?.status === "needs_regeneration" ? (
              <ConfirmAction
                title={`Refazer ${shot.id}?`}
                description="Somente este shot será gerado novamente. Os demais arquivos e aprovações serão preservados. Esta ação pode consumir 1 job HeyGen."
                confirmLabel="Refazer shot"
                onConfirm={() => onGenerate(true)}
                trigger={
                  <Button type="button" variant="outline" disabled={!canGenerate}>
                    <RotateCcw /> Refazer shot
                  </Button>
                }
              />
            ) : (
              <ConfirmAction
                title={`Gerar somente ${shot.id}?`}
                description={
                  shot.estimatedCost.heygenJobs
                    ? `Estratégia ${shot.strategy.replaceAll("_", " ")}. Esta ação cria 1 job HeyGen e usa o orçamento aprovado.`
                    : "Esta transição será renderizada localmente e não usa créditos HeyGen."
                }
                confirmLabel="Gerar shot"
                onConfirm={() => onGenerate(false)}
                trigger={
                  <Button type="button" variant="outline" disabled={!canGenerate}>
                    Gerar shot
                  </Button>
                }
              />
            )}
            <Button
              type="button"
              variant={controls.approved ? "secondary" : "default"}
              disabled={disabled}
              onClick={() => onControlsChange({ ...controls, approved: !controls.approved })}
            >
              {controls.approved ? <RotateCcw /> : <Check />}{" "}
              {controls.approved ? "Reabrir" : "Aprovar shot"}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function BudgetCard({
  state,
  onCritique,
  onApprove,
}: {
  state: StoryEditorState;
  onCritique: (force?: boolean) => void;
  onApprove: () => void;
}) {
  const critique = state.version?.activeCritique;
  const budget = critique?.budget;
  return (
    <Card className="border-primary/20">
      <CardHeader className="p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-sm">
              <CircleDollarSign className="h-4 w-4 text-primary" /> Revisão e orçamento
            </CardTitle>
            <CardDescription className="mt-1 text-xs">
              O orçamento permanece visível antes de qualquer produção. Nenhum job HeyGen nasce
              nesta tela.
            </CardDescription>
          </div>
          {state.version?.approved ? <Badge>Plano aprovado</Badge> : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-4 p-4 pt-0">
        {budget ? (
          <>
            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-lg border p-3">
                <p className="text-[11px] text-muted-foreground">Jobs iniciais</p>
                <p className="mt-1 text-lg font-semibold">{budget.initialHeyGenJobs}</p>
              </div>
              <div className="rounded-lg border p-3">
                <p className="text-[11px] text-muted-foreground">Pior cenário</p>
                <p className="mt-1 text-lg font-semibold">{budget.worstCaseHeyGenJobs} jobs</p>
              </div>
              <div className="rounded-lg border p-3">
                <p className="text-[11px] text-muted-foreground">Estimativa inicial</p>
                <p className="mt-1 text-lg font-semibold">{money(budget.estimatedInitialUsd)}</p>
              </div>
              <div className="rounded-lg border p-3">
                <p className="text-[11px] text-muted-foreground">Teto aprovado</p>
                <p className="mt-1 text-lg font-semibold">{money(budget.maxBudgetUsd)}</p>
              </div>
            </div>
            <Alert variant={budget.approvalEligible ? "default" : "destructive"}>
              {budget.approvalEligible ? (
                <ShieldCheck className="h-4 w-4" />
              ) : (
                <TriangleAlert className="h-4 w-4" />
              )}
              <AlertTitle>
                {critique.critique.decision === "ready" && budget.approvalEligible
                  ? "Plano pronto para aprovação"
                  : "Ajustes necessários"}
              </AlertTitle>
              <AlertDescription>{critique.critique.summary}</AlertDescription>
            </Alert>
            {critique.critique.issues.length || budget.issues.length ? (
              <ul className="space-y-2" aria-label="Problemas da revisão">
                {[...critique.critique.issues, ...budget.issues].map((issue, index) => (
                  <li
                    key={`${issue.code}-${index}`}
                    className="rounded-lg border px-3 py-2 text-xs leading-5"
                  >
                    <strong>{issue.code}:</strong> {issue.message}
                    <span className="block text-muted-foreground">{issue.suggestedAction}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </>
        ) : (
          <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
            A crítica calcula dificuldade, redundância, continuidade e pior cenário de custo.
          </div>
        )}
        <div className="flex flex-wrap justify-end gap-2">
          {critique ? (
            <ConfirmAction
              title="Refazer a crítica?"
              description="Faz uma nova chamada ao Anthropic e cria outra revisão da crítica. Nenhum job HeyGen será criado."
              confirmLabel="Refazer crítica"
              onConfirm={() => onCritique(true)}
              trigger={
                <Button
                  type="button"
                  variant="outline"
                  disabled={!canCritiqueStory(state) || state.pending !== null}
                >
                  <RefreshCw /> Refazer crítica
                </Button>
              }
            />
          ) : null}
          <ConfirmAction
            title="Revisar Story Plan com Claude?"
            description="Esta ação faz 1 chamada ao Anthropic para auditar narrativa, continuidade e orçamento. Nenhum job HeyGen será criado."
            confirmLabel="Rodar crítica"
            onConfirm={() => onCritique(false)}
            trigger={
              <Button
                type="button"
                variant="outline"
                disabled={!canCritiqueStory(state) || state.pending !== null}
              >
                {state.pending === "critique" ? (
                  <Loader2 className="animate-spin" />
                ) : (
                  <ShieldCheck />
                )}{" "}
                {critique ? "Atualizar crítica" : "Rodar crítica"}
              </Button>
            }
          />
          <ConfirmAction
            title="Aprovar plano e orçamento?"
            description={`Esta aprovação fica vinculada aos hashes do plano, da crítica e do orçamento. Ainda não gera vídeo. Limite: ${money(budget?.maxBudgetUsd ?? state.brief.maxBudgetUsd)}.`}
            confirmLabel="Aprovar plano"
            onConfirm={onApprove}
            trigger={
              <Button type="button" disabled={!canApproveStory(state) || state.pending !== null}>
                {state.pending === "approve" ? <Loader2 className="animate-spin" /> : <Check />}{" "}
                Aprovar plano e orçamento
              </Button>
            }
          />
        </div>
      </CardContent>
    </Card>
  );
}

export interface StoryModeEditorProps {
  scriptId: string;
  title: string;
  durationSeconds: number;
  orientation: "portrait" | "landscape";
  characterId: string | null;
  lookId: string | null;
  characterDescription: string;
  wardrobeDirection: string;
}

export function StoryModeEditor(props: StoryModeEditorProps) {
  const [state, dispatch] = useReducer(
    storyModeReducer,
    storyBriefDefaults(props),
    makeStoryEditorState,
  );
  const requestSequence = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++requestSequence.current;
    dispatch({ type: "load-start" });
    try {
      const [{ project, bindings }, capabilities] = await Promise.all([
        fetchStoryProject(props.scriptId),
        fetchHeyGenProviderCapabilities(),
      ]);
      if (requestId !== requestSequence.current) return;
      dispatch({ type: "load-success", project, bindings, capabilities });
    } catch (error) {
      if (requestId !== requestSequence.current) return;
      dispatch({ type: "load-error", message: errorMessage(error) });
    }
  }, [props.scriptId]);

  useEffect(() => {
    void load();
    return () => {
      requestSequence.current += 1;
    };
  }, [load]);

  const run = useCallback(
    async <T,>(
      request: Exclude<RequestName, null>,
      task: () => Promise<T>,
      onSuccess: (result: T) => void,
    ) => {
      const requestId = ++requestSequence.current;
      dispatch({ type: "request-start", request });
      try {
        const result = await task();
        if (requestId !== requestSequence.current) return;
        onSuccess(result);
      } catch (error) {
        if (requestId !== requestSequence.current) return;
        dispatch({ type: "request-error", message: errorMessage(error) });
      }
    },
    [],
  );

  const activeStep = state.version ? (state.version.activeCritique ? 4 : 3) : 1;
  const approvedShots = state.reviews.filter((review) => review.approved).length;
  const pendingDisabled = state.pending !== null;

  async function addReference(file: File) {
    try {
      const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
      const sha256 = Array.from(new Uint8Array(digest), (byte) =>
        byte.toString(16).padStart(2, "0"),
      ).join("");
      const kind: "image" | "video" | "document" = file.type.startsWith("image/")
        ? "image"
        : file.type.startsWith("video/")
          ? "video"
          : "document";
      dispatch({
        type: "brief-change",
        brief: {
          ...state.brief,
          referenceAssets: [
            ...state.brief.referenceAssets,
            { id: `ref-${crypto.randomUUID()}`, kind, sha256, description: file.name },
          ],
        },
      });
    } catch (error) {
      dispatch({ type: "request-error", message: errorMessage(error) });
    }
  }

  function saveBriefOnly() {
    if (!state.bindings) return;
    void run(
      "save",
      () => saveStoryBrief(props.scriptId, state.brief, state.bindings!),
      (project) =>
        dispatch({ type: "project-saved", project, message: "Story Brief salvo localmente." }),
    );
  }

  function createPlan() {
    if (!state.bindings || !state.capabilities) return;
    void run(
      "plan",
      () =>
        planStory(
          props.scriptId,
          state.brief,
          state.bindings!,
          state.capabilities!.capabilitiesVersion,
        ),
      (result) =>
        dispatch({
          type: "version-loaded",
          project: result.project,
          version: result.version,
          message: result.cacheHit
            ? "Storyboard recuperado do cache seguro."
            : "Nova história planejada; nenhum job HeyGen foi criado.",
        }),
    );
  }

  function saveRevision() {
    if (!state.version || !state.plan || !state.capabilities) return;
    void run(
      "revise",
      () =>
        reviseStoryVersion(
          state.version!,
          state.plan!,
          state.reviews,
          state.capabilities!.capabilitiesVersion,
          state.storyBibleApproved,
        ),
      (result) =>
        dispatch({
          type: "version-loaded",
          project: result.project,
          version: result.version,
          message: `Revisão ${result.version.storyRevision} salva. A versão anterior foi preservada.`,
        }),
    );
  }

  function critique(force = false) {
    if (!state.version || !state.capabilities) return;
    void run(
      "critique",
      () => critiqueStoryVersion(state.version!, state.capabilities!.capabilitiesVersion, force),
      (result) =>
        dispatch({
          type: "critique-loaded",
          version: {
            ...result.version,
            shots: state.version?.shots,
            activeCritique: result.critique,
          },
          message: result.cacheHit
            ? "Crítica recuperada do cache seguro."
            : "Crítica concluída; nenhum job HeyGen foi criado.",
        }),
    );
  }

  function approve() {
    const critiqueRecord = state.version?.activeCritique;
    if (!state.version || !critiqueRecord) return;
    void run(
      "approve",
      () => approveStoryVersion(state.version!, critiqueRecord),
      (result) =>
        dispatch({
          type: "approved",
          project: result.project,
          version: {
            ...result.version,
            shots: state.version?.shots,
            activeCritique: critiqueRecord,
          },
        }),
    );
  }

  function generateShot(index: number, regenerate: boolean) {
    const version = state.version;
    const record = version?.shots?.[index];
    const critiqueRecord = version?.activeCritique;
    if (!version || !record || !critiqueRecord || !version.approved) return;
    void run(
      "generate",
      () => generateStoryShot(version, record, critiqueRecord, regenerate),
      () => void load(),
    );
  }

  function refreshShot(index: number) {
    const generation = state.version?.shots?.[index]?.currentGeneration;
    if (!generation) return;
    void run(
      "refresh",
      () => refreshStoryShot(generation.id),
      () => void load(),
    );
  }

  if (state.phase === "loading") return <LoadingState />;
  if (state.phase === "error") {
    return (
      <Alert variant="destructive">
        <TriangleAlert className="h-4 w-4" />
        <AlertTitle>Não foi possível abrir o Story Mode</AlertTitle>
        <AlertDescription className="space-y-3">
          <p>{state.error}</p>
          <Button type="button" variant="outline" onClick={() => void load()}>
            <RefreshCw /> Tentar novamente
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-4">
      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {state.announcement}
      </div>
      <div className="flex flex-col gap-3 rounded-xl border border-primary/20 bg-primary/5 p-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h2 className="flex items-center gap-2 font-display text-base font-semibold">
            <Clapperboard className="h-5 w-5 text-primary" /> História cinematográfica
          </h2>
          <p className="mt-1 max-w-3xl text-xs leading-5 text-muted-foreground">
            Planeje com Claude, revise cada shot e aprove o pior cenário de custo antes de liberar
            qualquer chamada paga de vídeo.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <Badge variant="outline">
            Capabilities {state.capabilities?.capabilitiesVersion.slice(0, 12)}
          </Badge>
          {state.version ? (
            <Badge variant="outline">
              <History className="mr-1 h-3 w-3" /> Revisão {state.version.storyRevision}
            </Badge>
          ) : null}
          <Badge variant="outline">0 jobs HeyGen nesta fase</Badge>
        </div>
      </div>

      <StepRail active={activeStep} />
      {state.error ? (
        <Alert variant="destructive">
          <TriangleAlert className="h-4 w-4" />
          <AlertTitle>Ação não concluída</AlertTitle>
          <AlertDescription>{state.error}</AlertDescription>
        </Alert>
      ) : null}

      <StoryBriefForm
        brief={state.brief}
        pending={state.pending}
        onChange={(brief) => dispatch({ type: "brief-change", brief })}
        onReference={(file) => void addReference(file)}
        onSave={saveBriefOnly}
        onPlan={createPlan}
      />

      {state.plan && state.version ? (
        <>
          <BibleCard
            plan={state.plan}
            approved={state.storyBibleApproved}
            disabled={pendingDisabled}
            onApproved={(approved) => dispatch({ type: "bible-approval", approved })}
          />
          <div className="flex flex-col gap-3 rounded-xl border bg-card p-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="text-sm font-semibold">Storyboard editável</h3>
              <p className="mt-1 text-xs text-muted-foreground">
                {approvedShots}/{state.plan.shots.length} shots aprovados. Edite, desfaça ou salve
                uma nova revisão.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={!state.history.length || pendingDisabled}
                onClick={() => dispatch({ type: "undo" })}
              >
                <RotateCcw /> Desfazer
              </Button>
              <Button
                type="button"
                disabled={!state.dirty || pendingDisabled}
                onClick={saveRevision}
              >
                {state.pending === "revise" ? <Loader2 className="animate-spin" /> : <Save />}{" "}
                Salvar nova revisão
              </Button>
            </div>
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            {state.plan.shots.map((shot, index) => (
              <ShotCard
                key={shot.id}
                shot={shot}
                controls={state.reviews[index] ?? defaultControls()}
                record={state.version?.shots?.[index]}
                characterId={state.plan?.characterBible.characterId ?? null}
                lookId={state.plan?.characterBible.lookId ?? null}
                disabled={pendingDisabled || Boolean(state.version?.approved)}
                generationDisabled={pendingDisabled || !Boolean(state.version?.approved)}
                onShotChange={(nextShot) =>
                  dispatch({ type: "shot-change", index, shot: nextShot })
                }
                onControlsChange={(controls) =>
                  dispatch({ type: "review-change", index, controls })
                }
                onGenerate={(regenerate) => generateShot(index, regenerate)}
                onRefresh={() => refreshShot(index)}
              />
            ))}
          </div>
          {state.dirty ? (
            <Alert>
              <History className="h-4 w-4" />
              <AlertTitle>Alterações ainda locais</AlertTitle>
              <AlertDescription>
                Salve uma nova revisão antes de rodar a crítica. A revisão{" "}
                {state.version.storyRevision} permanece intacta até o backend aceitar todo o
                contrato.
              </AlertDescription>
            </Alert>
          ) : null}
          <BudgetCard state={state} onCritique={critique} onApprove={approve} />
        </>
      ) : null}
    </div>
  );
}
