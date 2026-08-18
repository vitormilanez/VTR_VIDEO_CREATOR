import { useEffect, useMemo, useRef, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  Clock3,
  Film,
  ImageIcon,
  ImageOff,
  LoaderCircle,
  MessageSquareText,
  ShieldCheck,
  Sparkles,
  UserRound,
  WandSparkles,
} from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/app-shell";
import { AvatarPicker } from "@/components/script-editor/avatar-studio";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { scanCompliance } from "@/lib/compliance";
import {
  adjustCinematicWithClaude,
  appendScript,
  createHeyGenVideo,
  fetchHeyGenCatalog,
  fetchScriptEditorState,
  type HeyGenCatalog,
} from "@/lib/api/local";
import {
  buildCinematicDirection,
  buildCinematicScript,
  CINEMATIC_DIRECTION_MAX_LENGTH,
  type CinematicMediaType,
  type CinematicPresenterMode,
  type CinematicSupportingImages,
  type CinematicVisualStyle,
} from "@/lib/cinematic";
import { assessScriptDuration, type DurationPreset } from "@/lib/script-editor";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/cinematic 2")({
  head: () => ({
    meta: [
      { title: "Cinematic | AI Video Creator" },
      {
        name: "description",
        content: "Crie um vídeo Cinematic a partir da fala final do Gui.",
      },
    ],
  }),
  component: CinematicPage,
});

const DURATION_OPTIONS = [15, 30, 45, 60] as const;
const CINEMATIC_DRAFT_STORAGE_KEY = "ai-video-creator:cinematic-draft:v1";

interface CinematicDraft {
  speech: string;
  durationSeconds: (typeof DURATION_OPTIONS)[number];
  supportingImages: CinematicSupportingImages;
  presenterMode: CinematicPresenterMode;
  mediaTypes: CinematicMediaType[];
  visualStyle: CinematicVisualStyle;
  requiredElements: string;
  excludedElements: string;
  criticalOnScreenText: string;
  directionNotes: string;
  avatarId: string;
  voiceId: string;
  adjustmentSummary: string | null;
  draftProjectId: string | null;
  completedJobId: string | null;
  completedJobError: string | null;
  productionWarnings: string[];
  savedAt: string;
}
const VISUAL_STYLES: Array<{
  value: CinematicVisualStyle;
  label: string;
  description: string;
}> = [
  { value: "editorial", label: "Editorial", description: "Premium e contemporâneo" },
  { value: "documentary", label: "Documental", description: "Humano e realista" },
  { value: "clean", label: "Clean", description: "Minimalista e direto" },
];
const PRESENTER_MODES: Array<{
  value: CinematicPresenterMode;
  label: string;
  description: string;
}> = [
  {
    value: "anchor",
    label: "Âncora entre apoios",
    description: "O Gui volta à cena com frequência.",
  },
  {
    value: "always",
    label: "Sempre em cena",
    description: "Apoios aparecem ao lado ou sobre o vídeo.",
  },
  {
    value: "intro_outro",
    label: "Abertura e final",
    description: "O Gui abre e fecha; os apoios ficam no meio.",
  },
];
const MEDIA_TYPES: Array<{
  value: CinematicMediaType;
  label: string;
  description: string;
}> = [
  {
    value: "motion_graphics",
    label: "Motion graphics",
    description: "Dados, palavras-chave e explicações visuais.",
  },
  {
    value: "stock_media",
    label: "Banco de imagens",
    description: "Pessoas, lugares e situações reais.",
  },
  {
    value: "ai_generated",
    label: "Gerado por IA",
    description: "Conceitos abstratos ou cenas muito específicas.",
  },
];

function CinematicPage() {
  const addScript = useStore((state) => state.addScript);
  const addVideoJob = useStore((state) => state.addVideoJob);
  const forbiddenWords = useStore((state) => state.settings.palavrasProibidas);
  const complianceRules = useStore((state) => state.complianceRules);
  const [speech, setSpeech] = useState("");
  const [durationSeconds, setDurationSeconds] = useState<DurationPreset>(45);
  const [supportingImages, setSupportingImages] = useState<CinematicSupportingImages>("auto");
  const [presenterMode, setPresenterMode] = useState<CinematicPresenterMode>("anchor");
  const [mediaTypes, setMediaTypes] = useState<CinematicMediaType[]>([
    "motion_graphics",
    "stock_media",
  ]);
  const [visualStyle, setVisualStyle] = useState<CinematicVisualStyle>("editorial");
  const [requiredElements, setRequiredElements] = useState("");
  const [excludedElements, setExcludedElements] = useState("");
  const [criticalOnScreenText, setCriticalOnScreenText] = useState("");
  const [directionNotes, setDirectionNotes] = useState("");
  const [catalog, setCatalog] = useState<HeyGenCatalog | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [avatarId, setAvatarId] = useState("");
  const [voiceId, setVoiceId] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [adjustingWithClaude, setAdjustingWithClaude] = useState(false);
  const [adjustError, setAdjustError] = useState<string | null>(null);
  const [adjustmentSummary, setAdjustmentSummary] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [completedJobId, setCompletedJobId] = useState<string | null>(null);
  const [completedJobError, setCompletedJobError] = useState<string | null>(null);
  const [productionWarnings, setProductionWarnings] = useState<string[]>([]);
  const [draftProjectId, setDraftProjectId] = useState<string | null>(null);
  const [draftReady, setDraftReady] = useState(false);
  const [draftSavedAt, setDraftSavedAt] = useState<string | null>(null);
  const restoredAvatarIdRef = useRef("");
  const restoredVoiceIdRef = useRef("");

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(CINEMATIC_DRAFT_STORAGE_KEY);
      if (!raw) return;
      const draft = JSON.parse(raw) as Partial<CinematicDraft>;
      if (typeof draft.speech === "string") setSpeech(draft.speech);
      if (DURATION_OPTIONS.includes(draft.durationSeconds as (typeof DURATION_OPTIONS)[number])) {
        setDurationSeconds(draft.durationSeconds as (typeof DURATION_OPTIONS)[number]);
      }
      if (draft.supportingImages === "auto" || draft.supportingImages === "avatar_only") {
        setSupportingImages(draft.supportingImages);
      }
      if (["anchor", "always", "intro_outro"].includes(draft.presenterMode || "")) {
        setPresenterMode(draft.presenterMode as CinematicPresenterMode);
      }
      if (Array.isArray(draft.mediaTypes)) {
        setMediaTypes(
          draft.mediaTypes.filter((item): item is CinematicMediaType =>
            ["motion_graphics", "stock_media", "ai_generated"].includes(item),
          ),
        );
      }
      if (["editorial", "documentary", "clean"].includes(draft.visualStyle || "")) {
        setVisualStyle(draft.visualStyle as CinematicVisualStyle);
      }
      if (typeof draft.requiredElements === "string") setRequiredElements(draft.requiredElements);
      if (typeof draft.excludedElements === "string") setExcludedElements(draft.excludedElements);
      if (typeof draft.criticalOnScreenText === "string") {
        setCriticalOnScreenText(draft.criticalOnScreenText);
      }
      if (typeof draft.directionNotes === "string") setDirectionNotes(draft.directionNotes);
      if (typeof draft.adjustmentSummary === "string") {
        setAdjustmentSummary(draft.adjustmentSummary);
      }
      if (typeof draft.draftProjectId === "string") setDraftProjectId(draft.draftProjectId);
      if (typeof draft.completedJobId === "string") setCompletedJobId(draft.completedJobId);
      if (typeof draft.completedJobError === "string") {
        setCompletedJobError(draft.completedJobError);
      }
      if (Array.isArray(draft.productionWarnings)) {
        setProductionWarnings(draft.productionWarnings.filter((item) => typeof item === "string"));
      }
      if (typeof draft.savedAt === "string") setDraftSavedAt(draft.savedAt);
      if (typeof draft.avatarId === "string") restoredAvatarIdRef.current = draft.avatarId;
      if (typeof draft.voiceId === "string") restoredVoiceIdRef.current = draft.voiceId;
    } catch {
      window.localStorage.removeItem(CINEMATIC_DRAFT_STORAGE_KEY);
    } finally {
      setDraftReady(true);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    setCatalogLoading(true);
    fetchHeyGenCatalog()
      .then((nextCatalog) => {
        if (cancelled) return;
        setCatalog(nextCatalog);
        const preferred =
          nextCatalog.avatars.find((avatar) => avatar.id === restoredAvatarIdRef.current) ||
          nextCatalog.avatars.find((avatar) => avatar.id === nextCatalog.defaultAvatarId) ||
          nextCatalog.avatars[0];
        const restoredVoice = nextCatalog.voices.find(
          (voice) => voice.id === restoredVoiceIdRef.current,
        );
        setAvatarId(preferred?.id || "");
        setVoiceId(
          restoredVoice?.id || preferred?.defaultVoiceId || nextCatalog.defaultVoiceId || "",
        );
      })
      .catch((error) => {
        if (cancelled) return;
        setCatalogError(
          error instanceof Error ? error.message : "Não foi possível carregar os avatares.",
        );
      })
      .finally(() => {
        if (!cancelled) setCatalogLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!draftReady) return;
    const timer = window.setTimeout(() => {
      const hasDraft = Boolean(
        speech.trim() ||
        requiredElements.trim() ||
        excludedElements.trim() ||
        criticalOnScreenText.trim() ||
        directionNotes.trim() ||
        draftProjectId ||
        completedJobId,
      );
      if (!hasDraft) {
        window.localStorage.removeItem(CINEMATIC_DRAFT_STORAGE_KEY);
        setDraftSavedAt(null);
        return;
      }
      const savedAt = new Date().toISOString();
      const draft: CinematicDraft = {
        speech,
        durationSeconds: durationSeconds as (typeof DURATION_OPTIONS)[number],
        supportingImages,
        presenterMode,
        mediaTypes,
        visualStyle,
        requiredElements,
        excludedElements,
        criticalOnScreenText,
        directionNotes,
        avatarId,
        voiceId,
        adjustmentSummary,
        draftProjectId,
        completedJobId,
        completedJobError,
        productionWarnings,
        savedAt,
      };
      window.localStorage.setItem(CINEMATIC_DRAFT_STORAGE_KEY, JSON.stringify(draft));
      setDraftSavedAt(savedAt);
    }, 200);
    return () => window.clearTimeout(timer);
  }, [
    adjustmentSummary,
    avatarId,
    completedJobError,
    completedJobId,
    criticalOnScreenText,
    directionNotes,
    draftProjectId,
    draftReady,
    durationSeconds,
    excludedElements,
    mediaTypes,
    presenterMode,
    productionWarnings,
    requiredElements,
    speech,
    supportingImages,
    visualStyle,
    voiceId,
  ]);

  const assessment = useMemo(
    () => assessScriptDuration(speech, durationSeconds),
    [durationSeconds, speech],
  );
  const compliancePreview = useMemo(
    () => scanCompliance({ speech }, forbiddenWords, complianceRules),
    [complianceRules, forbiddenWords, speech],
  );
  const compliancePreviewMessages = useMemo(
    () => [
      ...compliancePreview.hits.map((hit) => `Termo sensível: ${hit.palavra}`),
      ...compliancePreview.alertas.map((alert) => alert.titulo),
    ],
    [compliancePreview.alertas, compliancePreview.hits],
  );
  const selectedAvatar = useMemo(
    () => catalog?.avatars.find((avatar) => avatar.id === avatarId) || null,
    [avatarId, catalog?.avatars],
  );
  const selectedVoice = useMemo(
    () => catalog?.voices.find((voice) => voice.id === voiceId) || null,
    [catalog?.voices, voiceId],
  );
  const cinematicDirection = useMemo(
    () =>
      buildCinematicDirection({
        durationSeconds,
        supportingImages,
        presenterMode,
        mediaTypes,
        visualStyle,
        requiredElements,
        excludedElements,
        criticalOnScreenText,
        notes: directionNotes,
      }),
    [
      criticalOnScreenText,
      directionNotes,
      durationSeconds,
      excludedElements,
      mediaTypes,
      presenterMode,
      requiredElements,
      supportingImages,
      visualStyle,
    ],
  );
  const directionWithinLimit = cinematicDirection.length <= CINEMATIC_DIRECTION_MAX_LENGTH;
  const canAdjustWithClaude = Boolean(
    speech.trim().length >= 8 && !adjustingWithClaude && !submitting && !completedJobId,
  );
  const canGenerate = Boolean(
    speech.trim().length >= 10 &&
    assessment.status !== "blocking" &&
    avatarId &&
    voiceId &&
    directionWithinLimit &&
    confirmed &&
    !catalogLoading &&
    !submitting &&
    !completedJobId,
  );

  function invalidatePreparedDraft() {
    if (!submitting) setDraftProjectId(null);
    setConfirmed(false);
    setSubmitError(null);
    setAdjustError(null);
    setAdjustmentSummary(null);
  }

  function chooseAvatar(nextAvatarId: string) {
    const nextAvatar = catalog?.avatars.find((avatar) => avatar.id === nextAvatarId);
    setAvatarId(nextAvatarId);
    setVoiceId(nextAvatar?.defaultVoiceId || catalog?.defaultVoiceId || "");
    invalidatePreparedDraft();
  }

  function toggleMediaType(mediaType: CinematicMediaType) {
    setMediaTypes((current) =>
      current.includes(mediaType)
        ? current.filter((item) => item !== mediaType)
        : [...current, mediaType],
    );
    invalidatePreparedDraft();
  }

  async function handleClaudeAdjust() {
    if (!canAdjustWithClaude) return;
    setAdjustingWithClaude(true);
    setAdjustError(null);
    setAdjustmentSummary(null);
    setConfirmed(false);
    setSubmitError(null);
    setDraftProjectId(null);
    try {
      const result = await adjustCinematicWithClaude({
        sourceText: speech.trim(),
        durationSeconds: durationSeconds as Exclude<DurationPreset, 10>,
        supportingImages,
        presenterMode,
        mediaTypes,
        visualStyle,
        requiredElements,
        excludedElements,
        criticalOnScreenText,
        directionNotes,
        avatarName: selectedAvatar?.name || "",
        avatarType: selectedAvatar?.type || "",
        avatarOrientation: selectedAvatar?.orientation,
      });
      const adjusted = result.adjusted;
      setSpeech(adjusted.speech);
      setDurationSeconds(adjusted.durationSeconds);
      setSupportingImages(adjusted.supportingImages);
      setPresenterMode(adjusted.presenterMode);
      setMediaTypes(adjusted.mediaTypes);
      setVisualStyle(adjusted.visualStyle);
      setRequiredElements(adjusted.requiredElements);
      setExcludedElements(adjusted.excludedElements);
      setCriticalOnScreenText(adjusted.criticalOnScreenText);
      setDirectionNotes(adjusted.directionNotes);
      setAdjustmentSummary(adjusted.rationale || "Pacote ajustado aos padrões do HeyGen.");
      toast.success("Conteúdo e direção ajustados pelo Claude Sonnet. Revise antes de gerar.");
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Não foi possível ajustar o conteúdo com Claude Sonnet.";
      setAdjustError(message);
      toast.error(message);
    } finally {
      setAdjustingWithClaude(false);
    }
  }

  async function handleGenerate() {
    if (!canGenerate) return;
    setSubmitting(true);
    setSubmitError(null);
    const reviewedSpeech = speech.trim();
    const projectId = draftProjectId || newCinematicProjectId();
    setDraftProjectId(projectId);
    try {
      const project = buildCinematicScript({
        id: projectId,
        speech: reviewedSpeech,
        createdAt: new Date().toISOString(),
      });
      const saved = await appendScript(project);
      addScript(saved);

      const editorState = await fetchScriptEditorState(saved.id);
      if (
        !editorState.humanReviewApproved ||
        !editorState.finalSpeechHash ||
        editorState.scriptRevision < 1
      ) {
        throw new Error(
          "O roteiro foi salvo, mas a confirmação da fala ainda não foi versionada. Abra o roteiro e confirme a revisão antes de tentar novamente.",
        );
      }

      const job = await createHeyGenVideo(saved.id, {
        avatarId,
        voiceId,
        orientation: "portrait",
        durationSeconds,
        speechMode: "natural",
        voiceMood: "confident",
        generationMode: "cinematic",
        ctaMode: "none",
        captions: true,
        optimizePronunciation: true,
        narrationText: reviewedSpeech,
        displayText: reviewedSpeech,
        cinematicPrompt: cinematicDirection,
        outroText: "",
        medicalReviewStatus: "approved",
        humanReviewApproved: true,
        finalConfirmed: true,
        expectedScriptRevision: editorState.scriptRevision,
        expectedFinalSpeechHash: editorState.finalSpeechHash,
        contractVersion: editorState.contractVersion,
      });
      addVideoJob(job);
      setCompletedJobId(job.id);
      setCompletedJobError(job.status === "erro" ? job.erro || "Falha no envio ao HeyGen." : null);
      setProductionWarnings(job.warnings || []);
      setSubmitError(null);
      if (job.status === "erro") {
        toast.warning(`Job ${job.id} salvo. O envio ao HeyGen precisa ser retomado.`);
      } else if (job.warnings?.length) {
        toast.warning(`Job ${job.id} enviado com aviso de compliance.`);
      } else {
        toast.success(`Vídeo Cinematic enviado. Job ${job.id}.`);
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Não foi possível iniciar o vídeo Cinematic.";
      setSubmitError(message);
      toast.error(message);
    } finally {
      setSubmitting(false);
    }
  }

  function startAnother() {
    setSpeech("");
    setRequiredElements("");
    setExcludedElements("");
    setCriticalOnScreenText("");
    setDirectionNotes("");
    setAdjustError(null);
    setAdjustmentSummary(null);
    setConfirmed(false);
    setSubmitError(null);
    setCompletedJobId(null);
    setCompletedJobError(null);
    setProductionWarnings([]);
    setDraftProjectId(null);
    setDraftSavedAt(null);
    window.localStorage.removeItem(CINEMATIC_DRAFT_STORAGE_KEY);
  }

  return (
    <AppShell title="Cinematic">
      <div className="mx-auto max-w-7xl space-y-5">
        <section className="relative overflow-hidden rounded-2xl border bg-card px-5 py-6 shadow-sm sm:px-7 sm:py-7">
          <div className="pointer-events-none absolute inset-y-0 right-0 hidden w-1/2 bg-[radial-gradient(circle_at_70%_30%,color-mix(in_oklch,var(--color-status-success)_18%,transparent),transparent_55%)] lg:block" />
          <div className="relative max-w-3xl">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-status-success/25 bg-status-success/10 px-3 py-1 text-xs font-semibold text-foreground">
              <Sparkles className="h-3.5 w-3.5 text-status-success" />
              Roteiro aberto · HeyGen Video Agent
            </div>
            <h2 className="font-display text-2xl font-semibold tracking-tight sm:text-3xl">
              Cole uma ideia ou uma fala. O Sonnet prepara para o HeyGen.
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground sm:text-base">
              O Claude interpreta o assunto e todas as escolhas da tela, refaz a fala no tempo certo
              e transforma o contexto em direção visual compatível com o Video Agent.
            </p>
            <div className="mt-5 flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1.5">
                <MessageSquareText className="h-3.5 w-3.5 text-primary" /> Fala final como fonte
                canônica
              </span>
              <span className="inline-flex items-center gap-1.5">
                <ShieldCheck className="h-3.5 w-3.5 text-status-success" /> Confirmação antes do uso
                de créditos
              </span>
              <span className="inline-flex items-center gap-1.5">
                <Film className="h-3.5 w-3.5 text-status-info" /> Saída vertical 9:16
              </span>
            </div>
          </div>
        </section>

        {completedJobId ? (
          <Alert
            className={cn(
              completedJobError
                ? "border-status-warn/40 bg-status-warn/10"
                : "border-status-success/35 bg-status-success/8",
            )}
          >
            {completedJobError ? (
              <ShieldCheck className="h-4 w-4 text-status-warn" />
            ) : (
              <CheckCircle2 className="h-4 w-4 text-status-success" />
            )}
            <AlertTitle>
              {completedJobError ? "Job salvo; envio não concluído" : "Vídeo enviado para produção"}
            </AlertTitle>
            <AlertDescription className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <span>
                <strong className="font-semibold text-foreground">ID: {completedJobId}</strong>
                <span className="mt-1 block">
                  {completedJobError
                    ? completedJobError
                    : productionWarnings.length
                      ? `Enviado com aviso: ${productionWarnings.join("; ")}.`
                      : "A fala foi salva em Roteiros e o HeyGen recebeu a direção Cinematic."}
                </span>
              </span>
              <div className="flex flex-wrap gap-2">
                <Button asChild size="sm">
                  <Link to="/producao/$id" params={{ id: completedJobId }}>
                    Acompanhar produção <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                </Button>
                <Button type="button" size="sm" variant="outline" onClick={startAnother}>
                  Criar outro
                </Button>
              </div>
            </AlertDescription>
          </Alert>
        ) : null}

        {draftSavedAt && !completedJobId ? (
          <p className="px-1 text-right text-[11px] text-muted-foreground" aria-live="polite">
            Rascunho salvo automaticamente neste navegador.
          </p>
        ) : null}

        <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
          <fieldset
            disabled={submitting || adjustingWithClaude || Boolean(completedJobId)}
            className="min-w-0 space-y-5"
          >
            <Card className="shadow-sm">
              <CardHeader className="gap-3 border-b p-5 sm:flex-row sm:items-start">
                <StepNumber value="1" />
                <div>
                  <CardTitle className="text-base">Ideia ou fala do Gui</CardTitle>
                  <CardDescription className="mt-1">
                    Pode ser uma ideia curta, anotações ou um roteiro completo. O texto original não
                    é enviado ao HeyGen antes da sua revisão.
                  </CardDescription>
                </div>
              </CardHeader>
              <CardContent className="space-y-4 p-5">
                <div className="space-y-2">
                  <Label htmlFor="cinematic-speech">Ideia ou fala do Gui</Label>
                  <Textarea
                    id="cinematic-speech"
                    value={speech}
                    maxLength={6000}
                    onChange={(event) => {
                      setSpeech(event.target.value);
                      invalidatePreparedDraft();
                    }}
                    placeholder="Ex.: uma ideia provocativa sobre como o excesso de conforto afeta energia, hábitos e saúde masculina..."
                    className="min-h-52 resize-y bg-background text-[15px] leading-6"
                  />
                </div>

                <div className="grid gap-4 lg:grid-cols-[1fr_auto] lg:items-end">
                  <div className="space-y-2">
                    <Label>Duração desejada</Label>
                    <div
                      className="grid grid-cols-4 gap-2"
                      role="group"
                      aria-label="Duração desejada"
                    >
                      {DURATION_OPTIONS.map((duration) => (
                        <button
                          key={duration}
                          type="button"
                          aria-pressed={durationSeconds === duration}
                          onClick={() => {
                            setDurationSeconds(duration);
                            invalidatePreparedDraft();
                          }}
                          className={cn(
                            "min-h-11 cursor-pointer rounded-lg border px-3 text-sm font-semibold transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-ring",
                            durationSeconds === duration
                              ? "border-primary bg-primary text-primary-foreground"
                              : "bg-background hover:border-primary/40 hover:bg-muted/40",
                          )}
                        >
                          {duration}s
                        </button>
                      ))}
                    </div>
                  </div>
                  <DurationStatus
                    status={assessment.status}
                    words={assessment.wordCount}
                    estimated={assessment.estimatedSecondsDisplay}
                    target={assessment.targetWords}
                    maximum={assessment.hardLimitWords}
                  />
                </div>
                {assessment.status === "blocking" ? (
                  <p className="rounded-lg border border-status-danger/25 bg-status-danger/5 px-3 py-2 text-xs leading-5 text-status-danger">
                    {assessment.message}
                  </p>
                ) : null}

                {compliancePreviewMessages.length ? (
                  <Alert className="border-status-warn/40 bg-status-warn/10">
                    <ShieldCheck className="h-4 w-4 text-status-warn" />
                    <AlertTitle>Aviso de compliance — não bloqueia a geração</AlertTitle>
                    <AlertDescription className="text-xs leading-5">
                      {compliancePreviewMessages.join("; ")}. Revise se quiser; ao confirmar, o
                      vídeo poderá ser enviado mesmo com este aviso.
                    </AlertDescription>
                  </Alert>
                ) : null}

                <div className="rounded-xl border border-primary/20 bg-primary/[0.04] p-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="max-w-2xl">
                      <div className="flex items-center gap-2 text-sm font-semibold">
                        <Sparkles className="h-4 w-4 text-primary" /> Ajuste inteligente do pacote
                      </div>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">
                        O Sonnet ajusta fala, duração, presença do Gui, apoios, estilo, textos
                        literais e direção técnica usando tudo o que está preenchido na tela.
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      className="min-h-10 shrink-0 border-primary/30 bg-background"
                      disabled={!canAdjustWithClaude}
                      onClick={handleClaudeAdjust}
                    >
                      {adjustingWithClaude ? (
                        <>
                          <LoaderCircle className="h-4 w-4 animate-spin" /> Ajustando...
                        </>
                      ) : (
                        <>
                          <WandSparkles className="h-4 w-4" /> Ajustar tudo com Claude Sonnet
                        </>
                      )}
                    </Button>
                  </div>
                  <p className="mt-2 text-[10px] leading-4 text-muted-foreground">
                    Usa tokens do Claude, mas não consome créditos do HeyGen. A confirmação final é
                    removida após cada ajuste.
                  </p>
                </div>

                {adjustmentSummary ? (
                  <Alert className="border-status-success/30 bg-status-success/8">
                    <CheckCircle2 className="h-4 w-4 text-status-success" />
                    <AlertTitle>Pacote ajustado — revise antes de confirmar</AlertTitle>
                    <AlertDescription className="text-xs leading-5">
                      {adjustmentSummary}
                    </AlertDescription>
                  </Alert>
                ) : null}

                {adjustError ? (
                  <Alert variant="destructive">
                    <AlertTitle>Não foi possível ajustar com o Sonnet</AlertTitle>
                    <AlertDescription className="text-xs leading-5">{adjustError}</AlertDescription>
                  </Alert>
                ) : null}
              </CardContent>
            </Card>

            <Card className="shadow-sm">
              <CardHeader className="gap-3 border-b p-5 sm:flex-row sm:items-start">
                <StepNumber value="2" />
                <div>
                  <CardTitle className="text-base">Avatar</CardTitle>
                  <CardDescription className="mt-1">
                    Selecione qual versão do Gui apresenta o vídeo. A voz vinculada entra
                    automaticamente.
                  </CardDescription>
                </div>
              </CardHeader>
              <CardContent className="space-y-3 p-5">
                <AvatarPicker
                  value={avatarId}
                  avatars={catalog?.avatars || []}
                  loading={catalogLoading}
                  error={catalogError}
                  onChange={chooseAvatar}
                />
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-muted/35 px-3 py-2 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1.5">
                    <UserRound className="h-3.5 w-3.5" />
                    {selectedAvatar?.name || "Avatar ainda não selecionado"}
                  </span>
                  <span>{selectedVoice?.name || "Voz padrão do avatar"}</span>
                </div>
              </CardContent>
            </Card>

            <Card className="shadow-sm">
              <CardHeader className="gap-3 border-b p-5 sm:flex-row sm:items-start">
                <StepNumber value="3" />
                <div>
                  <CardTitle className="text-base">Elementos do vídeo</CardTitle>
                  <CardDescription className="mt-1">
                    Diga ao HeyGen o que mostrar, o que evitar e quando o Gui aparece.
                  </CardDescription>
                </div>
              </CardHeader>
              <CardContent className="space-y-5 p-5">
                <div className="space-y-2">
                  <Label>Como ilustrar a fala</Label>
                  <p className="text-xs leading-5 text-muted-foreground">
                    O agente pode selecionar apoios relacionados ou manter somente o apresentador.
                  </p>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <VisualChoice
                    active={supportingImages === "auto"}
                    icon={ImageIcon}
                    title="Gui + apoios relacionados"
                    badge="Recomendado"
                    description="O agente escolhe recursos coerentes com cada trecho, seguindo os limites abaixo."
                    onClick={() => {
                      setSupportingImages("auto");
                      invalidatePreparedDraft();
                    }}
                  />
                  <VisualChoice
                    active={supportingImages === "avatar_only"}
                    icon={ImageOff}
                    title="Somente o Gui"
                    description="O avatar permanece em cena; o agente só varia enquadramento, ritmo e composição."
                    onClick={() => {
                      setSupportingImages("avatar_only");
                      setPresenterMode("always");
                      invalidatePreparedDraft();
                    }}
                  />
                </div>

                {supportingImages === "auto" ? (
                  <>
                    <div className="space-y-2">
                      <Label>Presença do Gui</Label>
                      <div
                        className="grid gap-2 md:grid-cols-3"
                        role="group"
                        aria-label="Presença do Gui"
                      >
                        {PRESENTER_MODES.map((mode) => (
                          <button
                            key={mode.value}
                            type="button"
                            aria-pressed={presenterMode === mode.value}
                            onClick={() => {
                              setPresenterMode(mode.value);
                              invalidatePreparedDraft();
                            }}
                            className={cn(
                              "min-h-24 cursor-pointer rounded-lg border p-3 text-left transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-ring",
                              presenterMode === mode.value
                                ? "border-primary bg-primary/5 ring-1 ring-primary/20"
                                : "bg-background hover:border-primary/40 hover:bg-muted/30",
                            )}
                          >
                            <span className="flex items-start justify-between gap-2 text-sm font-semibold">
                              {mode.label}
                              {presenterMode === mode.value ? (
                                <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                              ) : null}
                            </span>
                            <span className="mt-1 block text-[11px] leading-4 text-muted-foreground">
                              {mode.description}
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="space-y-2">
                      <Label>Tipos de apoio visual</Label>
                      <div
                        className="grid gap-2 md:grid-cols-3"
                        role="group"
                        aria-label="Tipos de apoio visual"
                      >
                        {MEDIA_TYPES.map((mediaType) => {
                          const active = mediaTypes.includes(mediaType.value);
                          return (
                            <button
                              key={mediaType.value}
                              type="button"
                              aria-pressed={active}
                              onClick={() => toggleMediaType(mediaType.value)}
                              className={cn(
                                "min-h-24 cursor-pointer rounded-lg border p-3 text-left transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-ring",
                                active
                                  ? "border-status-info/60 bg-status-info/8 ring-1 ring-status-info/15"
                                  : "bg-background hover:border-primary/40 hover:bg-muted/30",
                              )}
                            >
                              <span className="flex items-start justify-between gap-2 text-sm font-semibold">
                                {mediaType.label}
                                {active ? (
                                  <Check className="mt-0.5 h-4 w-4 shrink-0 text-status-info" />
                                ) : null}
                              </span>
                              <span className="mt-1 block text-[11px] leading-4 text-muted-foreground">
                                {mediaType.description}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                      <p className="text-[11px] leading-4 text-muted-foreground">
                        “Gerado por IA” fica desligado por padrão para evitar cenas sintéticas não
                        solicitadas.
                      </p>
                    </div>
                  </>
                ) : null}

                <div className="space-y-2">
                  <Label>Estilo visual</Label>
                  <div
                    className="grid gap-2 sm:grid-cols-3"
                    role="group"
                    aria-label="Estilo visual"
                  >
                    {VISUAL_STYLES.map((style) => (
                      <button
                        key={style.value}
                        type="button"
                        aria-pressed={visualStyle === style.value}
                        onClick={() => {
                          setVisualStyle(style.value);
                          invalidatePreparedDraft();
                        }}
                        className={cn(
                          "cursor-pointer rounded-lg border p-3 text-left transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-ring",
                          visualStyle === style.value
                            ? "border-primary bg-primary/5 ring-1 ring-primary/20"
                            : "bg-background hover:border-primary/40 hover:bg-muted/30",
                        )}
                      >
                        <span className="flex items-center justify-between gap-2 text-sm font-semibold">
                          {style.label}
                          {visualStyle === style.value ? (
                            <Check className="h-4 w-4 text-primary" />
                          ) : null}
                        </span>
                        <span className="mt-1 block text-[11px] text-muted-foreground">
                          {style.description}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="cinematic-required-elements">O que precisa aparecer</Label>
                    <Textarea
                      id="cinematic-required-elements"
                      value={requiredElements}
                      maxLength={500}
                      onChange={(event) => {
                        setRequiredElements(event.target.value);
                        invalidatePreparedDraft();
                      }}
                      placeholder="Ex.: consulta com nutricionista, refeição brasileira e caminhada ao ar livre"
                      className="min-h-28 resize-y bg-background"
                    />
                    <p className="text-[11px] leading-4 text-muted-foreground">
                      Objetos, ambientes, ações e situações essenciais.
                    </p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="cinematic-excluded-elements">O que deve ser evitado</Label>
                    <Textarea
                      id="cinematic-excluded-elements"
                      value={excludedElements}
                      maxLength={400}
                      onChange={(event) => {
                        setExcludedElements(event.target.value);
                        invalidatePreparedDraft();
                      }}
                      placeholder="Ex.: hospitais, agulhas, marcas, antes e depois ou corpos sem contexto"
                      className="min-h-28 resize-y bg-background"
                    />
                    <p className="text-[11px] leading-4 text-muted-foreground">
                      Restrições visuais específicas deste conteúdo.
                    </p>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="cinematic-literal-text">Texto exato na tela</Label>
                  <Textarea
                    id="cinematic-literal-text"
                    value={criticalOnScreenText}
                    maxLength={400}
                    onChange={(event) => {
                      setCriticalOnScreenText(event.target.value);
                      invalidatePreparedDraft();
                    }}
                    placeholder={
                      "Ex.: Acompanhamento profissional\nResultados variam para cada pessoa"
                    }
                    className="min-h-24 resize-y bg-background"
                  />
                  <p className="text-[11px] leading-4 text-muted-foreground">
                    Uma frase por linha. O HeyGen recebe um bloco literal para não resumir nem
                    traduzir números, nomes ou CTAs.
                  </p>
                </div>

                <details className="group rounded-xl border bg-muted/20 p-4">
                  <summary className="cursor-pointer list-none text-sm font-semibold focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring">
                    Direção avançada opcional
                    <span className="ml-2 text-xs font-normal text-muted-foreground">
                      câmera, luz, ritmo e transições
                    </span>
                  </summary>
                  <div className="mt-4 space-y-2">
                    <Label htmlFor="cinematic-direction">Instruções adicionais</Label>
                    <Textarea
                      id="cinematic-direction"
                      value={directionNotes}
                      maxLength={600}
                      onChange={(event) => {
                        setDirectionNotes(event.target.value);
                        invalidatePreparedDraft();
                      }}
                      placeholder="Ex.: use luz natural quente, câmera estável e transições discretas"
                      className="min-h-24 resize-y bg-background"
                    />
                    <p className="text-[11px] leading-4 text-muted-foreground">
                      Direção técnica apenas. Este texto nunca entra na fala.
                    </p>
                  </div>
                </details>

                {!directionWithinLimit ? (
                  <Alert variant="destructive">
                    <AlertTitle>Direção visual muito longa</AlertTitle>
                    <AlertDescription>
                      Reduza as instruções para até {CINEMATIC_DIRECTION_MAX_LENGTH} caracteres
                      antes de gerar.
                    </AlertDescription>
                  </Alert>
                ) : null}
              </CardContent>
            </Card>
          </fieldset>

          <aside className="space-y-4 xl:sticky xl:top-20">
            <Card className="overflow-hidden border-primary/15 shadow-sm">
              <div className="border-b bg-linear-to-br from-primary/[0.06] via-card to-status-success/[0.08] p-5">
                <div className="flex items-center gap-2 text-sm font-semibold">
                  <WandSparkles className="h-4 w-4 text-status-success" /> Resumo da produção
                </div>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  O agente recebe a fala revisada como fonte canônica e estas escolhas.
                </p>
              </div>
              <CardContent className="space-y-4 p-5">
                <div className="relative mx-auto aspect-[9/16] w-full max-w-48 overflow-hidden rounded-2xl border bg-muted shadow-inner">
                  {selectedAvatar?.previewImageUrl ? (
                    <img
                      src={selectedAvatar.previewImageUrl}
                      alt={`Prévia de ${selectedAvatar.name}`}
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <div className="flex h-full flex-col items-center justify-center gap-3 bg-linear-to-b from-muted to-secondary p-5 text-center">
                      <div className="flex h-16 w-16 items-center justify-center rounded-full border bg-card shadow-sm">
                        <UserRound className="h-8 w-8 text-muted-foreground" />
                      </div>
                      <span className="text-xs font-semibold">
                        {selectedAvatar?.name || "Avatar do Gui"}
                      </span>
                    </div>
                  )}
                  <div className="absolute inset-x-3 bottom-3 rounded-lg bg-foreground/80 px-3 py-2 text-center text-[10px] font-medium text-background backdrop-blur-sm">
                    Legendas automáticas
                  </div>
                  <div className="absolute left-3 top-3 rounded-full bg-card/90 px-2 py-1 text-[10px] font-semibold shadow-sm backdrop-blur-sm">
                    9:16 · {durationSeconds}s
                  </div>
                </div>

                <dl className="space-y-2.5 text-xs">
                  <SummaryRow label="Fala" value={`${assessment.wordCount} palavras`} />
                  <SummaryRow
                    label="Tempo estimado"
                    value={assessment.wordCount ? assessment.estimatedSecondsDisplay : "—"}
                  />
                  <SummaryRow label="Avatar" value={selectedAvatar?.name || "Pendente"} />
                  <SummaryRow
                    label="Modo visual"
                    value={supportingImages === "auto" ? "Gui + apoios" : "Somente o Gui"}
                  />
                  <SummaryRow
                    label="Presença"
                    value={
                      supportingImages === "avatar_only"
                        ? "Sempre em cena"
                        : PRESENTER_MODES.find((mode) => mode.value === presenterMode)?.label || "—"
                    }
                  />
                  <SummaryRow
                    label="Apoios"
                    value={
                      supportingImages === "avatar_only"
                        ? "Desativados"
                        : mediaTypes.length
                          ? `${mediaTypes.length} tipos permitidos`
                          : "Nenhum tipo"
                    }
                  />
                  <SummaryRow
                    label="Estilo"
                    value={VISUAL_STYLES.find((style) => style.value === visualStyle)?.label || "—"}
                  />
                </dl>

                <details className="rounded-lg border bg-background">
                  <summary className="cursor-pointer list-none px-3 py-2.5 text-xs font-semibold focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring">
                    Instruções técnicas enviadas ao HeyGen
                  </summary>
                  <div className="border-t p-3">
                    <pre className="max-h-64 overflow-y-auto whitespace-pre-wrap break-words font-mono text-[10px] leading-4 text-muted-foreground">
                      {cinematicDirection}
                    </pre>
                    <p
                      className={cn(
                        "mt-2 text-right text-[10px]",
                        directionWithinLimit ? "text-muted-foreground" : "text-status-danger",
                      )}
                    >
                      {cinematicDirection.length}/{CINEMATIC_DIRECTION_MAX_LENGTH} caracteres
                    </p>
                  </div>
                </details>

                <div className="rounded-lg border bg-muted/25 p-3">
                  <label className="flex cursor-pointer items-start gap-2.5 text-xs leading-5">
                    <Checkbox
                      checked={confirmed}
                      onCheckedChange={(value) => setConfirmed(value === true)}
                      aria-label="Revisei e confirmo a fala final e os elementos do vídeo"
                      className="mt-0.5"
                    />
                    <span>
                      <strong className="block text-foreground">
                        Revisei a fala e os elementos
                      </strong>
                      <span className="text-muted-foreground">
                        A fala define tese, fatos, tom e CTA. O Video Agent pode adaptar a fluidez
                        sem mudar esses limites; as demais escolhas orientam o visual.
                      </span>
                    </span>
                  </label>
                </div>

                {submitError ? (
                  <Alert variant="destructive" className="px-3 py-2">
                    <AlertTitle>Não foi possível gerar</AlertTitle>
                    <AlertDescription className="text-xs leading-5">{submitError}</AlertDescription>
                  </Alert>
                ) : null}

                <Button
                  type="button"
                  className="min-h-11 w-full"
                  disabled={!canGenerate}
                  onClick={handleGenerate}
                >
                  {submitting ? (
                    <>
                      <LoaderCircle className="h-4 w-4 animate-spin" /> Preparando produção...
                    </>
                  ) : (
                    <>
                      <Film className="h-4 w-4" /> Gerar vídeo no HeyGen
                    </>
                  )}
                </Button>
                <p className="text-center text-[10px] leading-4 text-muted-foreground">
                  O clique cria 1 roteiro e inicia 1 geração paga. Cliques duplicados são
                  deduplicados.
                </p>
              </CardContent>
            </Card>

            <div className="rounded-xl border border-dashed bg-card/50 p-4 text-xs leading-5 text-muted-foreground">
              <div className="mb-1.5 flex items-center gap-2 font-semibold text-foreground">
                <ShieldCheck className="h-4 w-4 text-status-success" /> O que fica protegido
              </div>
              A fala é versionada antes da geração. Se algo falhar, o roteiro permanece salvo para
              uma nova tentativa sem perder o texto.
            </div>
          </aside>
        </div>
      </div>
    </AppShell>
  );
}

function StepNumber({ value }: { value: string }) {
  return (
    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
      {value}
    </span>
  );
}

function DurationStatus({
  status,
  words,
  estimated,
  target,
  maximum,
}: {
  status: "ideal" | "warning" | "blocking";
  words: number;
  estimated: string;
  target: number;
  maximum: number;
}) {
  return (
    <div
      className={cn(
        "min-w-56 rounded-lg border px-3 py-2",
        status === "blocking"
          ? "border-status-danger/30 bg-status-danger/5"
          : status === "warning"
            ? "border-status-warn/40 bg-status-warn/10"
            : "border-status-success/30 bg-status-success/8",
      )}
      aria-live="polite"
    >
      <div className="flex items-center justify-between gap-3 text-xs font-semibold">
        <span className="inline-flex items-center gap-1.5">
          <Clock3 className="h-3.5 w-3.5" /> {words} palavras
        </span>
        <span>{words ? estimated : "~0s"}</span>
      </div>
      <p className="mt-1 text-[10px] leading-4 text-muted-foreground">
        Meta {target} · máximo seguro {maximum}
      </p>
    </div>
  );
}

function VisualChoice({
  active,
  icon: Icon,
  title,
  badge,
  description,
  onClick,
}: {
  active: boolean;
  icon: typeof ImageIcon;
  title: string;
  badge?: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "cursor-pointer rounded-xl border p-4 text-left transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-ring",
        active
          ? "border-primary bg-primary/5 ring-1 ring-primary/20"
          : "bg-background hover:border-primary/40 hover:bg-muted/30",
      )}
    >
      <span className="flex items-start justify-between gap-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-muted">
          <Icon className="h-4 w-4 text-primary" />
        </span>
        {badge ? (
          <span className="rounded-full bg-status-success/12 px-2 py-1 text-[9px] font-bold uppercase tracking-wide text-foreground">
            {badge}
          </span>
        ) : null}
      </span>
      <span className="mt-3 flex items-center gap-2 text-sm font-semibold">
        {title} {active ? <CheckCircle2 className="h-4 w-4 text-primary" /> : null}
      </span>
      <span className="mt-1 block text-xs leading-5 text-muted-foreground">{description}</span>
    </button>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b pb-2.5 last:border-0 last:pb-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="max-w-44 truncate text-right font-semibold text-foreground">{value}</dd>
    </div>
  );
}

function newCinematicProjectId() {
  const unique =
    globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `s-cinematic-${unique}`;
}
