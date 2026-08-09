import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { CompliancePanel, HighlightedText } from "@/components/compliance-panel";
import { StatusTimeline, type TimelineStep } from "@/components/status-timeline";
import { WithTooltip } from "@/components/with-tooltip";
import { ConfirmAction } from "@/components/confirm-action";
import {
  DurationControl,
  MedicalReviewCard,
  QualityChecks,
  QualityIssuesCard,
  StaleEditorResult,
  TitleAlignmentCard,
} from "@/components/script-editor/editor-feedback";
import {
  useDurationAnnouncement,
  useEditorErrorFocus,
} from "@/components/script-editor/editor-feedback-hooks";
import {
  AvatarPicker,
  AvatarSetEditorDialog,
  AvatarSetSelector,
} from "@/components/script-editor/avatar-studio";
import {
  FriendlySwitch,
  HighCreditConsumptionNotice,
  ProductionGateChecklist,
  ProductionReadinessCard,
} from "@/components/script-editor/production-readiness";
import { ScenePlanEditor } from "@/components/script-editor/scene-plan-editor";
import { VisualPlanDirector } from "@/components/script-editor/visual-plan-director";
import { StoryModeEditor } from "@/components/script-editor/story-mode-editor";
import {
  DEFAULT_OUTRO,
  narrationQualityIssues,
  normalizeNarrationOutro,
  removeNarrationOutro,
  videoAgentNarrationQualityIssues,
} from "@/lib/script-quality";
import { editorialToneLabel, prioridadeLabel, riskLabel, scriptStatusLabel } from "@/lib/status";
import { useStore } from "@/lib/store";
import {
  createHeyGenPreview,
  createHeyGenVideo,
  composeFinalVideo,
  deleteAvatarSet,
  fetchAvatarSets,
  fetchHeyGenCatalog,
  fetchMusicTracks,
  fetchProductionProfile,
  fetchScriptEditorState,
  fetchSceneGenerationPlan,
  fetchScenePlan,
  fetchVideoSlideRender,
  fetchVisualPlan,
  generateVisualDirection,
  runScriptEditorAssist,
  saveProductionProfile,
  saveScriptEditorState,
  saveScript,
  renderVideoSlides,
  submitSceneGeneration,
  type AvatarSet,
  type AvatarSetLook,
  type AvatarSetRole,
  type HeyGenCatalog,
  type MusicTrack,
  type GenerationMode,
  type ScenePlan,
  type SceneGenerationResult,
  type VideoSlideRender,
  type VisualPlan,
  type VoiceMood,
} from "@/lib/api/local";
import {
  SCRIPT_EDITOR_CONTRACT_VERSION,
  assessScriptDuration,
  evaluateGenerationGate,
  medicalReviewForRisk,
  normalizeScriptText,
  type EditorAssistResult,
  type EditorOperation,
  type MedicalReviewStatus,
} from "@/lib/script-editor";
import type { Prioridade, Script, ScriptStatus } from "@/lib/mock-data";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import {
  ArrowLeft,
  Captions,
  CheckCircle2,
  Clapperboard,
  Film,
  History,
  Loader2,
  RotateCcw,
  Save,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  Volume2,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/roteiros/$id")({
  head: ({ params }) => ({
    meta: [
      { title: `Roteiro ${params.id} | AI Video Creator` },
      { name: "description", content: "Edicao de roteiro e preparacao para producao de video." },
    ],
  }),
  component: RoteiroDetalhe,
});

const HEYGEN_CATALOG_FALLBACK_VOICES: HeyGenCatalog["voices"] = [
  { id: "33a98f732fe144d9a40f5cf33a7e95ec", name: "drguilhermeia", gender: "male" },
];

const VOICE_MOOD_OPTIONS: Array<{
  value: VoiceMood;
  label: string;
  description: string;
}> = [
  {
    value: "confident",
    label: "Confiante",
    description: "Positivo, seguro e com energia natural.",
  },
  {
    value: "upbeat",
    label: "Animado",
    description: "Mais vivo, otimista e dinâmico.",
  },
  {
    value: "warm",
    label: "Acolhedor",
    description: "Próximo e empático, sem ficar triste.",
  },
  {
    value: "serious",
    label: "Sério",
    description: "Objetivo e informativo, sem dramatizar.",
  },
  {
    value: "neutral",
    label: "Neutro",
    description: "Mantém a voz mais próxima do original.",
  },
];

type StudioDefaults = {
  orientation?: "portrait" | "landscape";
  captions?: boolean;
};

function readStudioDefaults(): StudioDefaults | null {
  try {
    const saved = localStorage.getItem("ai-video-creator-studio-defaults");
    if (!saved) return null;
    return JSON.parse(saved) as StudioDefaults;
  } catch {
    return null;
  }
}

function RoteiroDetalhe() {
  const { id } = Route.useParams();
  const script = useStore((s) => s.scripts.find((x) => x.id === id));
  const allScripts = useStore((s) => s.scripts);
  const siblingCaptureScripts = useMemo(
    () =>
      allScripts
        .filter(
          (candidate) =>
            candidate.ideaId &&
            candidate.ideaId === script?.ideaId &&
            candidate.formatoSugerido.toLowerCase().includes("hook de captura"),
        )
        .sort((a, b) => a.titulo.localeCompare(b.titulo)),
    [allScripts, script?.ideaId],
  );
  const updateScript = useStore((s) => s.updateScript);
  const addVideoJob = useStore((s) => s.addVideoJob);
  const videoJobs = useStore((s) => s.videoJobs);
  const palavras = useStore((s) => s.settings.palavrasProibidas);
  const complianceRules = useStore((s) => s.complianceRules);
  const navigate = useNavigate();
  const initialCaptureDuration = captureHookDuration(script);
  const captureHook = initialCaptureDuration !== null;
  const initialOutro = initialCaptureDuration === 10 ? "" : script?.outroText || DEFAULT_OUTRO;

  const [draft, setDraft] = useState<Script | undefined>(script);
  const [sending, setSending] = useState(false);
  const [mixingMusic, setMixingMusic] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [catalog, setCatalog] = useState<HeyGenCatalog | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [profileLoaded, setProfileLoaded] = useState(false);
  const [avatarId, setAvatarId] = useState("");
  const [voiceId, setVoiceId] = useState("");
  const [avatarMode, setAvatarMode] = useState<"single" | "set">("single");
  const [avatarSetId, setAvatarSetId] = useState<string | null>(null);
  const [primaryAvatarId, setPrimaryAvatarId] = useState("");
  const [avatarSets, setAvatarSets] = useState<AvatarSet[]>([]);
  const [avatarSetsLoading, setAvatarSetsLoading] = useState(true);
  const [avatarSetDialogOpen, setAvatarSetDialogOpen] = useState(false);
  const [editingAvatarSet, setEditingAvatarSet] = useState<AvatarSet | null>(null);
  const [scenePlan, setScenePlan] = useState<ScenePlan | null>(null);
  const [scenePlanLoading, setScenePlanLoading] = useState(true);
  const [sceneGenerationPlan, setSceneGenerationPlan] = useState<SceneGenerationResult | null>(
    null,
  );
  const [sceneGenerationPlanLoading, setSceneGenerationPlanLoading] = useState(false);
  const [visualPlan, setVisualPlan] = useState<VisualPlan | null>(null);
  const [visualPlanLoading, setVisualPlanLoading] = useState(true);
  const [transitionSlideGenerating, setTransitionSlideGenerating] = useState(false);
  const [videoSlideRender, setVideoSlideRender] = useState<VideoSlideRender | null>(null);
  const [videoSlideRenderLoading, setVideoSlideRenderLoading] = useState(true);
  const [orientation, setOrientation] = useState<"portrait" | "landscape">("portrait");
  const [durationSeconds, setDurationSeconds] = useState<10 | 15 | 30 | 45 | 60>(
    initialCaptureDuration ?? 45,
  );
  const [speechMode, setSpeechMode] = useState<"natural" | "fiel" | "direto" | "enfatico">(
    "natural",
  );
  const [voiceMood, setVoiceMood] = useState<VoiceMood>("confident");
  const [generationMode, setGenerationMode] = useState<GenerationMode>("direct");
  const cinematicMode = generationMode === "cinematic";
  const storyMode = generationMode === "story";
  const heygenAgentMode = generationMode === "video_agent" || cinematicMode;
  const [musicTracks, setMusicTracks] = useState<MusicTrack[]>([]);
  const [musicTrackId, setMusicTrackId] = useState<string | null>(null);
  const [musicVolume, setMusicVolume] = useState(0.12);
  const [cinematicPrompt, setCinematicPrompt] = useState("");
  const [ctaMode, setCtaMode] = useState<"auto" | "manual" | "none" | "visual">("auto");
  const [captions, setCaptions] = useState(true);
  const [optimizePronunciation, setOptimizePronunciation] = useState(true);
  const [outroText, setOutroText] = useState(initialOutro);
  const [narrationText, setNarrationText] = useState(() =>
    script ? buildNarrationText(script, initialOutro) : "",
  );
  const [displayText, setDisplayText] = useState(() =>
    script ? buildNarrationText(script, initialOutro) : "",
  );
  const [spokenText, setSpokenText] = useState(() =>
    script ? buildNarrationText(script, initialOutro) : "",
  );
  const [performancePlan, setPerformancePlan] = useState<{
    tone: string;
    pace: string;
    emotion: string;
    recommendedVoiceSpeed: number;
  } | null>(null);
  const [naturalizing, setNaturalizing] = useState(false);
  const [activeEditorOperation, setActiveEditorOperation] = useState<EditorOperation | null>(null);
  const [lastEditorResult, setLastEditorResult] = useState<EditorAssistResult | null>(null);
  const [previousAiScript, setPreviousAiScript] = useState<string | null>(null);
  const [editorTechnicalError, setEditorTechnicalError] = useState<string | null>(null);
  const [editorSchemaValid, setEditorSchemaValid] = useState(true);
  const [humanReviewApproved, setHumanReviewApproved] = useState(false);
  const [titleChoice, setTitleChoice] = useState<"current" | "suggested">("current");
  const [titleBeforeSuggestion, setTitleBeforeSuggestion] = useState(script?.titulo ?? "");
  const [editorStateLoaded, setEditorStateLoaded] = useState(false);
  const [paidScriptVersion, setPaidScriptVersion] = useState({
    scriptRevision: 0,
    finalSpeechHash: "",
    contractVersion: SCRIPT_EDITOR_CONTRACT_VERSION,
  });
  const [staleEditorResult, setStaleEditorResult] = useState<EditorAssistResult | null>(null);
  const lastSavedProfileKey = useRef("");
  const lastSavedEditorStateKey = useRef("");
  const sendPromiseRef = useRef<Promise<void> | null>(null);
  const editorRevisionRef = useRef(0);
  const editorRequestIdRef = useRef(0);
  const editorMountedRef = useRef(true);
  const existingJobs = useMemo(
    () =>
      videoJobs
        .filter((job) => job.scriptId === id && job.status !== "erro" && !job.isPreview)
        .sort(
          (left, right) => new Date(right.criadoEm).getTime() - new Date(left.criadoEm).getTime(),
        ),
    [id, videoJobs],
  );
  const previewJobs = useMemo(
    () =>
      videoJobs
        .filter((job) => job.scriptId === id && job.status !== "erro" && job.isPreview)
        .sort(
          (left, right) => new Date(right.criadoEm).getTime() - new Date(left.criadoEm).getTime(),
        ),
    [id, videoJobs],
  );
  const latestJob = existingJobs[0];
  const latestPreview = previewJobs[0];
  const durationAssessment = useMemo(
    () => assessScriptDuration(displayText, durationSeconds),
    [displayText, durationSeconds],
  );
  const technicalQualityIssues = useMemo(
    () =>
      narrationQualityIssues(displayText, durationSeconds, ctaMode === "manual" ? outroText : ""),
    [ctaMode, displayText, durationSeconds, outroText],
  );
  const qualityIssues = useMemo(() => {
    const editorial = heygenAgentMode
      ? videoAgentNarrationQualityIssues(displayText, durationSeconds)
      : [];
    return [...new Set([...technicalQualityIssues, ...editorial])];
  }, [displayText, durationSeconds, heygenAgentMode, technicalQualityIssues]);
  const blockingQualityIssues = technicalQualityIssues;
  const hasHighCreditConsumption = durationSeconds >= 45;
  const approvalReady = draft?.status === "aprovado_clinicamente";
  const narrationWords = durationAssessment.wordCount;
  const estimatedSpeechSeconds = Math.max(0, Math.round(durationAssessment.estimatedSeconds));
  const baseMedicalReviewStatus = medicalReviewForRisk(
    draft?.risco ?? "medio",
    humanReviewApproved,
  );
  const medicalReviewStatus: MedicalReviewStatus = humanReviewApproved
    ? "approved"
    : lastEditorResult?.medicalSafety.requiresHumanReview
      ? "required"
      : baseMedicalReviewStatus;
  const durationAnnouncement = useDurationAnnouncement(durationAssessment);
  const editorErrorRef = useEditorErrorFocus(editorTechnicalError);

  useEffect(() => {
    editorMountedRef.current = true;
    return () => {
      editorMountedRef.current = false;
      editorRequestIdRef.current += 1;
    };
  }, []);

  useEffect(() => {
    if (script) {
      editorRevisionRef.current += 1;
      setDraft(script);
      setTitleBeforeSuggestion(script.titulo);
      const savedCaptureDuration = captureHookDuration(script);
      const savedOutro = savedCaptureDuration === 10 ? "" : script.outroText || DEFAULT_OUTRO;
      setOutroText(savedOutro);
      const initialText = buildNarrationText(script, savedOutro);
      setNarrationText(initialText);
      setDisplayText(initialText);
      setSpokenText("");
      if (savedCaptureDuration !== null) {
        setDurationSeconds(savedCaptureDuration);
        setSpeechMode("direto");
      }
    }
  }, [script]);

  useEffect(() => {
    let cancelled = false;
    setEditorStateLoaded(false);
    fetchScriptEditorState(id)
      .then((state) => {
        if (cancelled) return;
        if (!(state.legacyFallback && initialCaptureDuration !== null)) {
          setDurationSeconds(state.durationSeconds);
        }
        setHumanReviewApproved(state.humanReviewApproved);
        setTitleChoice(state.titleChoice);
        setLastEditorResult(state.lastResult ?? null);
        setPreviousAiScript(state.previousScript ?? null);
        setEditorSchemaValid(state.schemaValid);
        setEditorTechnicalError(state.technicalError ?? null);
        setPaidScriptVersion({
          scriptRevision: state.scriptRevision,
          finalSpeechHash: state.finalSpeechHash ?? "",
          contractVersion: state.contractVersion,
        });
        lastSavedEditorStateKey.current = JSON.stringify({
          durationSeconds: state.durationSeconds,
          humanReviewApproved: state.humanReviewApproved,
          titleChoice: state.titleChoice,
          suggestedTitle: state.suggestedTitle ?? null,
          schemaValid: state.schemaValid,
          technicalError: state.technicalError ?? null,
          previousScript: state.previousScript ?? null,
          lastResult: state.lastResult ?? null,
        });
      })
      .catch(() => {
        if (!cancelled) setEditorTechnicalError("Não foi possível carregar o estado do editor.");
      })
      .finally(() => {
        if (!cancelled) setEditorStateLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [id, initialCaptureDuration]);

  useEffect(() => {
    let cancelled = false;
    setProfileLoaded(false);
    setAvatarId("");
    setVoiceId("");
    setVoiceMood("confident");
    setAvatarMode("single");
    setAvatarSetId(null);
    setPrimaryAvatarId("");
    setMusicTrackId(null);
    setMusicVolume(0.12);
    setCinematicPrompt("");
    lastSavedProfileKey.current = "";
    fetchProductionProfile(id)
      .then((profile) => {
        if (cancelled) return;
        if (profile) {
          setAvatarId(profile.avatarId);
          setVoiceId(profile.voiceId);
          setAvatarMode(profile.avatarMode === "set" && profile.avatarSetId ? "set" : "single");
          setAvatarSetId(profile.avatarSetId || null);
          setPrimaryAvatarId(profile.primaryAvatarId || profile.avatarId);
          setSpeechMode(profile.speechMode);
          setVoiceMood(profile.voiceMood || "confident");
          setGenerationMode(profile.generationMode);
          setMusicTrackId(profile.musicTrackId || null);
          setMusicVolume(profile.musicVolume || 0.12);
          setCinematicPrompt(profile.cinematicPrompt || "");
          lastSavedProfileKey.current = [
            profile.avatarId,
            profile.voiceId,
            profile.speechMode,
            profile.voiceMood || "confident",
            profile.generationMode,
            profile.avatarMode || "single",
            profile.avatarSetId || "",
            profile.primaryAvatarId || profile.avatarId,
            profile.musicTrackId || "",
            profile.musicVolume || 0.12,
            profile.cinematicPrompt || "",
          ].join("|");
        }
      })
      .catch(() => {
        if (!cancelled) toast.error("Nao consegui carregar o perfil de producao deste roteiro.");
      })
      .finally(() => {
        if (!cancelled) setProfileLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const loadCatalog = (showSuccess = false) => {
    setCatalogLoading(true);
    setCatalogError(null);
    fetchHeyGenCatalog()
      .then((data) => {
        setCatalog(data);
        const preferredAvatar =
          data.avatars.find((avatar) => avatar.id === data.defaultAvatarId) || data.avatars[0];
        setAvatarId((current) => current || preferredAvatar?.id || "");
        setVoiceId(
          (current) => current || preferredAvatar?.defaultVoiceId || data.defaultVoiceId || "",
        );
        if (showSuccess) {
          toast.success(
            data.avatars.length
              ? `${data.avatars.length} avatares carregados.`
              : "HeyGen respondeu, mas nao retornou avatares prontos.",
          );
        }
      })
      .catch((err) => {
        const message = err instanceof Error ? err.message : "Falha ao carregar HeyGen.";
        setCatalogError(message);
        setCatalog({ avatars: [], voices: HEYGEN_CATALOG_FALLBACK_VOICES, defaultAvatarId: null });
        toast.error(message);
      })
      .finally(() => setCatalogLoading(false));
  };

  useEffect(() => {
    loadCatalog();
    setAvatarSetsLoading(true);
    fetchAvatarSets()
      .then((sets) => setAvatarSets(sets))
      .catch(() => toast.error("Nao consegui carregar os Avatar Sets salvos."))
      .finally(() => setAvatarSetsLoading(false));
    fetchMusicTracks()
      .then((tracks) => setMusicTracks(tracks))
      .catch(() => toast.error("Nao consegui carregar a biblioteca de trilhas locais."));
    setScenePlanLoading(true);
    fetchScenePlan(id)
      .then((plan) => setScenePlan(plan))
      .catch(() => toast.error("Nao consegui carregar o Scene Plan deste roteiro."))
      .finally(() => setScenePlanLoading(false));
    setVisualPlanLoading(true);
    fetchVisualPlan(id)
      .then((plan) => setVisualPlan(plan))
      .catch(() => toast.error("Nao consegui carregar a direção visual deste roteiro."))
      .finally(() => setVisualPlanLoading(false));
    setVideoSlideRenderLoading(true);
    fetchVideoSlideRender(id)
      .then((render) => setVideoSlideRender(render))
      .catch(() => toast.error("Nao consegui carregar os previews visuais deste roteiro."))
      .finally(() => setVideoSlideRenderLoading(false));
    const defaults = readStudioDefaults();
    if (defaults?.orientation) setOrientation(defaults.orientation);
    if (typeof defaults?.captions === "boolean") setCaptions(defaults.captions);
  }, [id]);

  useEffect(() => {
    if (!scenePlan) {
      setSceneGenerationPlan(null);
      return;
    }
    let cancelled = false;
    setSceneGenerationPlanLoading(true);
    fetchSceneGenerationPlan(id, { speechMode, voiceMood, orientation })
      .then((plan) => {
        if (!cancelled) setSceneGenerationPlan(plan);
      })
      .catch(() => {
        if (!cancelled) setSceneGenerationPlan(null);
      })
      .finally(() => {
        if (!cancelled) setSceneGenerationPlanLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    avatarMode,
    avatarSetId,
    id,
    orientation,
    primaryAvatarId,
    profileLoaded,
    scenePlan,
    speechMode,
    voiceId,
    voiceMood,
  ]);
  const savedDisplayText = useMemo(
    () =>
      script
        ? buildNarrationText(
            script,
            captureHookDuration(script) === 10 ? "" : script.outroText || DEFAULT_OUTRO,
          )
        : "",
    [script],
  );
  const speechDirty =
    normalizeScriptText(displayText) !== normalizeScriptText(savedDisplayText) ||
    (script?.outroText || DEFAULT_OUTRO) !== outroText;
  const dirty = useMemo(
    () => JSON.stringify(draft) !== JSON.stringify(script) || speechDirty,
    [draft, script, speechDirty],
  );
  const selectedAvatar = useMemo(
    () => catalog?.avatars.find((avatar) => avatar.id === avatarId),
    [avatarId, catalog?.avatars],
  );
  const selectedVoiceName = useMemo(
    () =>
      catalog?.voices.find((voice) => voice.id === voiceId)?.name ||
      (selectedAvatar ? `Voz de ${selectedAvatar.name}` : "Voz do avatar"),
    [catalog?.voices, selectedAvatar, voiceId],
  );
  const selectedMusicTrack = useMemo(
    () => musicTracks.find((track) => track.id === musicTrackId) || null,
    [musicTrackId, musicTracks],
  );
  const selectedAvatarSet = useMemo(
    () => avatarSets.find((avatarSet) => avatarSet.id === avatarSetId) || null,
    [avatarSetId, avatarSets],
  );
  const selectedSetLooks = useMemo(
    () =>
      selectedAvatarSet?.looks
        .map((look) => ({
          look,
          avatar: catalog?.avatars.find((candidate) => candidate.id === look.avatarId),
        }))
        .filter((item): item is { look: AvatarSetLook; avatar: HeyGenCatalog["avatars"][number] } =>
          Boolean(item.avatar),
        ) || [],
    [catalog?.avatars, selectedAvatarSet],
  );
  const avatarSetReady = Boolean(
    selectedAvatarSet && selectedSetLooks.length >= 2 && primaryAvatarId,
  );
  const productionModeReady =
    heygenAgentMode ||
    avatarMode === "single" ||
    Boolean(avatarMode === "set" && sceneGenerationPlan);
  const requiredVisualCount = scenePlan ? Math.max(0, scenePlan.scenes.length - 1) : 0;
  const visualProductionReady =
    heygenAgentMode ||
    avatarMode === "single" ||
    requiredVisualCount === 0 ||
    Boolean(visualPlan && (videoSlideRender?.renderedCount ?? 0) >= requiredVisualCount);
  const selectedAvatarReady =
    heygenAgentMode || avatarMode === "single" ? Boolean(avatarId) : avatarSetReady;
  const sceneRoles = useMemo<AvatarSetRole[]>(
    () => selectedAvatarSet?.looks.map((look) => look.role) || ["primary"],
    [selectedAvatarSet],
  );
  const editorGenerationGate = evaluateGenerationGate({
    speech: displayText,
    durationSeconds,
    aiOperationInFlight: naturalizing,
    schemaValid: editorSchemaValid,
    technicalError: editorTechnicalError,
    medicalReviewStatus,
    humanReviewApproved,
    scriptStatus: draft?.status ?? "aguardando_validacao",
    finalSaved: !dirty,
    // O modal de confirmação cobre esta etapa; o backend recebe o valor explícito.
    finalConfirmed: true,
  });
  const paidVersionReady = Boolean(
    editorStateLoaded &&
    paidScriptVersion.scriptRevision > 0 &&
    paidScriptVersion.finalSpeechHash &&
    paidScriptVersion.contractVersion === SCRIPT_EDITOR_CONTRACT_VERSION,
  );
  const canSendToProduction =
    !storyMode &&
    paidVersionReady &&
    editorGenerationGate.allowed &&
    selectedAvatarReady &&
    productionModeReady &&
    visualProductionReady;

  function chooseAvatar(nextAvatarId: string) {
    setAvatarMode("single");
    setAvatarSetId(null);
    setAvatarId(nextAvatarId);
    setPrimaryAvatarId(nextAvatarId);
    const nextAvatar = catalog?.avatars.find((avatar) => avatar.id === nextAvatarId);
    if (nextAvatar?.defaultVoiceId) setVoiceId(nextAvatar.defaultVoiceId);
  }

  function chooseAvatarSet(nextAvatarSet: AvatarSet) {
    const primaryLook =
      nextAvatarSet.looks.find((look) => look.role === "primary") || nextAvatarSet.looks[0];
    setAvatarMode("set");
    setAvatarSetId(nextAvatarSet.id);
    setPrimaryAvatarId(primaryLook.avatarId);
    setAvatarId(primaryLook.avatarId);
    setVoiceId(nextAvatarSet.voiceId);
  }

  useEffect(() => {
    if (
      selectedAvatar &&
      generationMode === "direct" &&
      selectedAvatar.supportsDirectAvatar === false
    ) {
      setGenerationMode("video_agent");
    }
  }, [generationMode, selectedAvatar]);

  useEffect(() => {
    if (!profileLoaded || !avatarId || !voiceId || (avatarMode === "set" && !avatarSetReady))
      return;
    const key = [
      avatarId,
      voiceId,
      speechMode,
      voiceMood,
      generationMode,
      avatarMode,
      avatarSetId || "",
      primaryAvatarId,
      musicTrackId || "",
      musicVolume,
      cinematicPrompt,
    ].join("|");
    if (key === lastSavedProfileKey.current) return;
    const timeout = window.setTimeout(() => {
      saveProductionProfile(id, {
        avatarId: avatarMode === "set" ? primaryAvatarId : avatarId,
        voiceId,
        speechMode,
        voiceMood,
        generationMode,
        avatarMode,
        avatarSetId: avatarMode === "set" ? avatarSetId : null,
        primaryAvatarId: avatarMode === "set" ? primaryAvatarId : avatarId,
        musicTrackId,
        musicVolume,
        cinematicPrompt,
      })
        .then((profile) => {
          lastSavedProfileKey.current = [
            profile.avatarId,
            profile.voiceId,
            profile.speechMode,
            profile.voiceMood || "confident",
            profile.generationMode,
            profile.avatarMode || "single",
            profile.avatarSetId || "",
            profile.primaryAvatarId || profile.avatarId,
            profile.musicTrackId || "",
            profile.musicVolume || 0.12,
            profile.cinematicPrompt || "",
          ].join("|");
        })
        .catch(() => toast.error("Nao consegui salvar o perfil de producao."));
    }, 500);
    return () => window.clearTimeout(timeout);
  }, [
    avatarId,
    avatarMode,
    avatarSetId,
    avatarSetReady,
    cinematicPrompt,
    generationMode,
    id,
    musicTrackId,
    musicVolume,
    primaryAvatarId,
    profileLoaded,
    speechMode,
    voiceId,
    voiceMood,
  ]);

  useEffect(() => {
    if (!editorStateLoaded) return;
    const state = {
      durationSeconds,
      humanReviewApproved,
      titleChoice,
      suggestedTitle: lastEditorResult?.titleAlignment.suggestedTitle ?? null,
      schemaValid: editorSchemaValid,
      technicalError: editorTechnicalError,
      previousScript: previousAiScript,
      lastResult: lastEditorResult,
    };
    const key = JSON.stringify(state);
    if (key === lastSavedEditorStateKey.current) return;
    const timeout = window.setTimeout(() => {
      saveScriptEditorState(id, state)
        .then((savedState) => {
          lastSavedEditorStateKey.current = key;
          setPaidScriptVersion({
            scriptRevision: savedState.scriptRevision,
            finalSpeechHash: savedState.finalSpeechHash ?? "",
            contractVersion: savedState.contractVersion,
          });
        })
        .catch(() => toast.error("Não consegui salvar o histórico do editor."));
    }, 450);
    return () => window.clearTimeout(timeout);
  }, [
    durationSeconds,
    editorSchemaValid,
    editorStateLoaded,
    editorTechnicalError,
    humanReviewApproved,
    id,
    lastEditorResult,
    previousAiScript,
    titleChoice,
  ]);

  async function handleAvatarSetSaved(saved: AvatarSet) {
    setAvatarSets((current) => {
      const withoutSaved = current.filter((avatarSet) => avatarSet.id !== saved.id);
      return [...withoutSaved, saved].sort((left, right) => left.name.localeCompare(right.name));
    });
    setAvatarSetDialogOpen(false);
    chooseAvatarSet(saved);
    toast.success("Avatar Set salvo com duas posições.");
  }

  async function handleDeleteAvatarSet(avatarSetToDelete: AvatarSet) {
    try {
      await deleteAvatarSet(avatarSetToDelete.id);
      setAvatarSets((current) =>
        current.filter((avatarSet) => avatarSet.id !== avatarSetToDelete.id),
      );
      if (avatarSetId === avatarSetToDelete.id) {
        setAvatarMode("single");
        setAvatarSetId(null);
        setPrimaryAvatarId(avatarId);
      }
      toast.success("Avatar Set excluído.");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Nao foi possivel excluir o Avatar Set.",
      );
    }
  }

  if (!script || !draft) {
    return (
      <AppShell title="Roteiro">
        <p className="text-sm text-muted-foreground">
          Roteiro nao encontrado.{" "}
          <Link to="/roteiros" className="text-status-info underline">
            Voltar
          </Link>
        </p>
      </AppShell>
    );
  }

  function set<K extends keyof Script>(key: K, value: Script[K]) {
    setDraft((d) => (d ? { ...d, [key]: value } : d));
  }

  function setProductionDuration(nextDuration: 10 | 15 | 30 | 45 | 60) {
    editorRevisionRef.current += 1;
    setDurationSeconds(nextDuration);
    setLastEditorResult(null);
    setEditorSchemaValid(true);
    setEditorTechnicalError(null);
    if (nextDuration === 10) {
      setDisplayText((current) => removeNarrationOutro(current, outroText));
      setSpokenText("");
      setNarrationText((current) => removeNarrationOutro(current, outroText));
      setOutroText("");
      setSpeechMode("direto");
    } else if (!outroText.trim()) {
      setOutroText(DEFAULT_OUTRO);
      setDisplayText((current) => normalizeNarrationOutro(current, DEFAULT_OUTRO));
      setSpokenText("");
      setNarrationText((current) => normalizeNarrationOutro(current, DEFAULT_OUTRO));
    }
  }

  const complianceFields = {
    titulo: draft.titulo,
    hook: draft.hook,
    dor: draft.dorConflito,
    explicacao: draft.explicacaoSimples,
    virada: draft.virada,
    cta: draft.cta,
    cuidados: draft.cuidadosMedicos,
  };

  const timeline = buildScriptTimeline(draft.status, {
    criadoEm: draft.criadoEm,
    validadoEm: draft.validadoEm,
  });
  const productionBlockedReason = !editorGenerationGate.allowed
    ? editorGenerationGate.reason
    : !editorStateLoaded
      ? "Carregando o versionamento seguro da fala."
      : !paidVersionReady
        ? "A fala salva ainda não possui revisão e hash de segurança. Atualize a página ou salve o roteiro novamente."
        : storyMode
          ? "No Story Mode, aprove o storyboard e o orçamento antes da geração por shots."
          : catalogLoading
            ? "Carregando avatares e vozes da HeyGen."
            : !profileLoaded
              ? "Carregando perfil de producao do roteiro."
              : cinematicMode && !cinematicPrompt.trim()
                ? "Escreva a direção cinematic antes de enviar este modo."
                : avatarMode === "set" && !selectedAvatarSet
                  ? "Selecione um Avatar Set."
                  : !heygenAgentMode && avatarMode === "set" && !avatarSetReady
                    ? "O Avatar Set precisa ter duas posições disponíveis no catálogo."
                    : !heygenAgentMode && avatarMode === "set" && !productionModeReady
                      ? 'Clique em "Fazer tudo com Claude" para organizar cenas e cortes antes de enviar.'
                      : !heygenAgentMode && avatarMode === "set" && !visualProductionReady
                        ? `Clique em "Fazer tudo com Claude" para gerar e renderizar ${requiredVisualCount} slide(s) de transição.`
                        : !avatarId
                          ? "Selecione um avatar pronto."
                          : !voiceId
                            ? "Selecione uma voz."
                            : saving
                              ? "Salvando roteiro."
                              : null;
  const productionChecklist = [
    {
      label: "Roteiro revisado",
      ready: approvalReady,
      detail: approvalReady
        ? "Status Pronto"
        : 'Mude o status para "Pronto" em Roteiro → Ver contexto.',
    },
    {
      label: "Roteiro salvo",
      ready: !dirty,
      detail: dirty ? "Salve as alterações antes de enviar." : "Sem alterações pendentes.",
    },
    {
      label: "Versão da fala",
      ready: paidVersionReady,
      detail: !editorStateLoaded
        ? "Carregando revisão e hash de segurança."
        : paidVersionReady
          ? `Revisão ${paidScriptVersion.scriptRevision} protegida para geração.`
          : "Atualize a página ou salve novamente para versionar a fala.",
    },
    {
      label: !heygenAgentMode && avatarMode === "set" ? "Avatar Set" : "Avatar",
      ready: selectedAvatarReady,
      detail:
        !heygenAgentMode && avatarMode === "set"
          ? selectedAvatarSet
            ? `${selectedSetLooks.length} look(s) carregado(s).`
            : "Escolha um conjunto de looks."
          : selectedAvatar
            ? selectedAvatar.name
            : "Escolha um avatar.",
    },
    {
      label: "Voz",
      ready: Boolean(voiceId),
      detail: voiceId ? selectedVoiceName : "Selecione uma voz.",
    },
    ...(cinematicMode
      ? [
          {
            label: "Direção cinematic",
            ready: Boolean(cinematicPrompt.trim()),
            detail: cinematicPrompt.trim()
              ? "Briefing exclusivo preenchido."
              : "Escreva câmera, encenação e acontecimentos no ambiente.",
          },
        ]
      : []),
    {
      label: "Cenas",
      ready:
        heygenAgentMode ||
        avatarMode === "single" ||
        Boolean(scenePlan && scenePlan.scenes.length >= 1),
      detail: cinematicMode
        ? "O Cinematic cria a encenação sem usar o Scene Plan antigo."
        : heygenAgentMode
          ? "O HeyGen Video Agent decide a estrutura visual e os cortes."
          : avatarMode === "single"
            ? "Look único não precisa de plano de cenas."
            : scenePlan
              ? `${scenePlan.scenes.length} cena(s) salvas.`
              : 'Clique em "Fazer tudo com Claude".',
    },
    {
      label: "Slide de transição",
      ready:
        heygenAgentMode ||
        avatarMode === "single" ||
        requiredVisualCount === 0 ||
        visualProductionReady,
      detail: cinematicMode
        ? "O Cinematic cria os apoios dentro do próprio vídeo."
        : heygenAgentMode
          ? "O HeyGen cria os visuais dentro do próprio vídeo."
          : avatarMode === "single" || requiredVisualCount === 0
            ? "Não obrigatório para este formato."
            : visualProductionReady
              ? `${requiredVisualCount} apoio(s) renderizado(s).`
              : `Falta gerar/renderizar ${requiredVisualCount} slide(s) com Claude.`,
    },
    {
      label: "Duração",
      ready: durationAssessment.status !== "blocking",
      detail: durationAssessment.message,
    },
    {
      label: "Revisão médica",
      ready: medicalReviewStatus !== "required",
      detail:
        medicalReviewStatus === "approved"
          ? "Revisão médica aprovada."
          : medicalReviewStatus === "required"
            ? "Revisão obrigatória ainda não aprovada."
            : medicalReviewStatus === "recommended"
              ? "Revisão recomendada, sem bloquear a duração."
              : "Revisão médica não obrigatória.",
    },
    {
      label: "Validação técnica",
      ready: editorSchemaValid && !editorTechnicalError && blockingQualityIssues.length === 0,
      detail: editorTechnicalError || blockingQualityIssues[0] || "Schema e texto final válidos.",
    },
  ];

  async function enviarProducaoCore(forceNewVersion = false) {
    if (!draft || !script) return;
    if (storyMode) {
      toast.info("O Story Mode gera por shots somente após aprovação do plano e do orçamento.");
      return;
    }
    if (avatarMode === "set" && generationMode === "direct" && !sceneGenerationPlan) {
      toast.error("Salve o Scene Plan antes de gerar o vídeo por cenas.");
      return;
    }
    if (productionBlockedReason || !canSendToProduction) {
      toast.error(productionBlockedReason || "Conclua o checklist antes de gerar o vídeo.");
      return;
    }
    setSending(true);
    const notice = toast.loading(
      forceNewVersion ? "Enviando a nova versão ao HeyGen..." : "Enviando o vídeo ao HeyGen...",
    );
    try {
      let scriptToSend = script;
      let versionToSend = paidScriptVersion;
      if (dirty) {
        const saved = await saveScript({ ...draft, textoFalado: displayText, outroText });
        updateScript(saved.id, saved);
        setDraft(saved);
        scriptToSend = saved;
        const versionState = await fetchScriptEditorState(saved.id);
        setHumanReviewApproved(versionState.humanReviewApproved);
        versionToSend = {
          scriptRevision: versionState.scriptRevision,
          finalSpeechHash: versionState.finalSpeechHash ?? "",
          contractVersion: versionState.contractVersion,
        };
        setPaidScriptVersion(versionToSend);
      }
      if (avatarMode === "set" && generationMode === "direct") {
        await saveProductionProfile(scriptToSend.id, {
          avatarId: primaryAvatarId,
          primaryAvatarId,
          avatarSetId,
          avatarMode,
          voiceId,
          speechMode,
          voiceMood,
          generationMode,
          musicTrackId,
          musicVolume,
          cinematicPrompt,
        });
        const sceneResult = await submitSceneGeneration(scriptToSend.id, {
          orientation,
          durationSeconds,
          speechMode,
          voiceMood,
          captions,
          optimizePronunciation,
          forceNewVersion,
          expectedScriptRevision: versionToSend.scriptRevision,
          expectedFinalSpeechHash: versionToSend.finalSpeechHash,
          contractVersion: versionToSend.contractVersion,
        });
        sceneResult.jobs.forEach((job) => addVideoJob(job));
        const firstJob = sceneResult.jobs[0];
        if (!firstJob) throw new Error("A HeyGen não retornou jobs por cena.");
        toast.success(`${sceneResult.jobs.length} cena(s) enviada(s) para produção no HeyGen.`, {
          id: notice,
        });
        navigate({ to: "/producao/$id", params: { id: firstJob.id } });
        return;
      }
      const job = await createHeyGenVideo(scriptToSend.id, {
        avatarId,
        voiceId,
        orientation,
        durationSeconds,
        speechMode,
        voiceMood,
        generationMode,
        ctaMode,
        captions,
        optimizePronunciation,
        forceNewVersion,
        narrationText: displayText,
        displayText,
        spokenText: spokenText || undefined,
        cinematicPrompt: cinematicMode ? cinematicPrompt : undefined,
        outroText: ctaMode === "manual" ? outroText : "",
        medicalReviewStatus,
        humanReviewApproved,
        aiOperationInFlight: naturalizing,
        aiSchemaValid: editorSchemaValid,
        editorTechnicalError,
        finalConfirmed: true,
        expectedScriptRevision: versionToSend.scriptRevision,
        expectedFinalSpeechHash: versionToSend.finalSpeechHash,
        contractVersion: versionToSend.contractVersion,
      });
      addVideoJob(job);
      toast.success(
        forceNewVersion
          ? "Nova versão enviada. O status será atualizado automaticamente."
          : dirty
            ? "Roteiro salvo e enviado para producao no HeyGen."
            : "Roteiro enviado para producao no HeyGen.",
        { id: notice },
      );
      navigate({ to: "/producao/$id", params: { id: job.id } });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Nao foi possivel enviar ao HeyGen.", {
        id: notice,
      });
    } finally {
      setSending(false);
    }
  }

  function enviarProducao(forceNewVersion = false): Promise<void> {
    if (sendPromiseRef.current) return sendPromiseRef.current;
    const request = enviarProducaoCore(forceNewVersion).finally(() => {
      sendPromiseRef.current = null;
    });
    sendPromiseRef.current = request;
    return request;
  }

  async function aplicarTrilhaNoVideoFinal() {
    if (!musicTrackId || !avatarId || !voiceId) return;
    setMixingMusic(true);
    try {
      // Garante que um clique logo após escolher a faixa já use essa escolha,
      // sem depender do autosave com debounce da tela.
      await saveProductionProfile(id, {
        avatarId: avatarMode === "set" ? primaryAvatarId : avatarId,
        voiceId,
        speechMode,
        voiceMood,
        generationMode,
        avatarMode,
        avatarSetId: avatarMode === "set" ? avatarSetId : null,
        primaryAvatarId: avatarMode === "set" ? primaryAvatarId : avatarId,
        musicTrackId,
        musicVolume,
        cinematicPrompt,
      });
      const job = await composeFinalVideo(id);
      addVideoJob(job);
      toast.success("Trilha mixada localmente no vídeo final. A fala foi preservada.");
      navigate({ to: "/producao/$id", params: { id: job.id } });
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : "Ainda não foi possível mixar a trilha no vídeo final.",
      );
    } finally {
      setMixingMusic(false);
    }
  }

  async function salvarRoteiro() {
    if (!draft) return;
    setSaving(true);
    try {
      const saved = await saveScript({
        ...draft,
        textoFalado: displayText,
        outroText,
      });
      updateScript(saved.id, saved);
      setDraft(saved);
      setNarrationText(displayText);
      const versionState = await fetchScriptEditorState(saved.id);
      setHumanReviewApproved(versionState.humanReviewApproved);
      setPaidScriptVersion({
        scriptRevision: versionState.scriptRevision,
        finalSpeechHash: versionState.finalSpeechHash ?? "",
        contractVersion: versionState.contractVersion,
      });
      setEditorSchemaValid(true);
      setEditorTechnicalError(null);
      toast.success("Roteiro salvo no Sheets.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Nao foi possivel salvar o roteiro.");
    } finally {
      setSaving(false);
    }
  }

  async function gerarSlidesTransicao(savedPlan: ScenePlan) {
    setTransitionSlideGenerating(true);
    try {
      const result = await generateVisualDirection(id, {
        displayText: displayText || narrationText,
        spokenText,
        durationSeconds,
        tone: performancePlan?.tone,
        pace: performancePlan?.pace,
        emotion: performancePlan?.emotion,
      });
      setVisualPlan(result.visualPlan);
      const rendered = await renderVideoSlides(id);
      setVideoSlideRender(rendered);
      const normalizedPlan = await fetchVisualPlan(id);
      if (normalizedPlan) setVisualPlan(normalizedPlan);
      toast.success(
        savedPlan.scenes.length > 2
          ? "Slides de transição gerados e renderizados."
          : "Slide de transição gerado e renderizado.",
      );
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Nao foi possivel gerar slide de transição.",
      );
      throw error;
    } finally {
      setTransitionSlideGenerating(false);
    }
  }

  async function executarEditorComIa(operation: EditorOperation) {
    if (!draft || !displayText.trim() || naturalizing) return;
    const previousScript = displayText;
    const requestId = ++editorRequestIdRef.current;
    const editorRevision = editorRevisionRef.current;
    setNaturalizing(true);
    setActiveEditorOperation(operation);
    setEditorTechnicalError(null);
    try {
      const result = await runScriptEditorAssist({
        operation,
        scriptId: id,
        text: displayText,
        title: draft.titulo,
        sourceText: "",
        contextText: [
          `Tema: ${draft.tema}`,
          `Hook aprovado: ${draft.hook}`,
          `Dor ou conflito: ${draft.dorConflito}`,
          `Explicação: ${draft.explicacaoSimples}`,
          `Virada: ${draft.virada}`,
          `CTA: ${draft.cta}`,
          draft.link ? `Fonte: ${draft.link}` : "",
        ]
          .filter(Boolean)
          .join("\n"),
        medicalCautions: draft.cuidadosMedicos,
        riskLevel: draft.risco,
        claims: [],
        glossary: [],
        cta: ctaMode === "manual" ? outroText : draft.cta,
        durationSeconds,
        humanReviewApproved,
      });
      if (
        !editorMountedRef.current ||
        requestId !== editorRequestIdRef.current ||
        editorRevision !== editorRevisionRef.current
      ) {
        if (editorMountedRef.current && requestId === editorRequestIdRef.current) {
          setStaleEditorResult(result);
          toast.info("A fala mudou durante a revisão. O resultado antigo não foi aplicado.");
        }
        return;
      }
      setLastEditorResult(result);
      setEditorSchemaValid(result.schemaValid);
      setEditorTechnicalError(
        result.schemaValid ? null : result.technicalError || "Saída de IA inválida.",
      );
      if (!result.schemaValid) {
        toast.error(result.warnings[0] || "A resposta não pôde ser aplicada. O texto foi mantido.");
        return;
      }
      if (result.noOp) {
        toast.info(result.message || `O texto já está adequado para ${durationSeconds}s.`);
        return;
      }
      editorRevisionRef.current += 1;
      setPreviousAiScript(previousScript);
      setDisplayText(result.script);
      setNarrationText(result.script);
      // Vazio faz o backend gerar a versão fonética segura a partir da grafia correta.
      setSpokenText("");
      if (result.medicalSafety.requiresHumanReview) setHumanReviewApproved(false);
      if (result.titleAlignment.status === "possible_mismatch") setTitleChoice("current");
      toast.success(
        operation === "medical_rewrite"
          ? "Revisão editorial concluída. Confira as mudanças antes de salvar."
          : `Fala ajustada para ${durationSeconds}s. Confira antes de salvar.`,
      );
    } catch (error) {
      setEditorSchemaValid(false);
      setEditorTechnicalError(
        error instanceof Error ? error.message : "Não foi possível concluir a edição com IA.",
      );
      toast.error(
        error instanceof Error ? error.message : "Não foi possível concluir a edição com IA.",
      );
    } finally {
      setNaturalizing(false);
      setActiveEditorOperation(null);
    }
  }

  async function gerarPrevia() {
    if (!draft || !script) return;
    if (!approvalReady) {
      toast.error('Conclua a revisão e altere o status do roteiro para "Pronto".');
      return;
    }
    setPreviewing(true);
    try {
      let scriptToSend = script;
      let versionToSend = paidScriptVersion;
      if (dirty) {
        const saved = await saveScript({ ...draft, textoFalado: displayText, outroText });
        updateScript(saved.id, saved);
        setDraft(saved);
        scriptToSend = saved;
        const versionState = await fetchScriptEditorState(saved.id);
        setHumanReviewApproved(versionState.humanReviewApproved);
        versionToSend = {
          scriptRevision: versionState.scriptRevision,
          finalSpeechHash: versionState.finalSpeechHash ?? "",
          contractVersion: versionState.contractVersion,
        };
        setPaidScriptVersion(versionToSend);
      }
      const job = await createHeyGenPreview(scriptToSend.id, {
        avatarId,
        voiceId,
        orientation,
        speechMode,
        voiceMood,
        captions,
        optimizePronunciation,
        displayText,
        spokenText: spokenText || undefined,
        finalConfirmed: true,
        expectedScriptRevision: versionToSend.scriptRevision,
        expectedFinalSpeechHash: versionToSend.finalSpeechHash,
        contractVersion: versionToSend.contractVersion,
      });
      addVideoJob(job);
      toast.success("Prévia técnica Direct Avatar enviada ao HeyGen.");
      navigate({ to: "/producao/$id", params: { id: job.id } });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Nao foi possivel gerar a previa.");
    } finally {
      setPreviewing(false);
    }
  }

  return (
    <AppShell
      title={`Roteiro: ${script.titulo}`}
      actions={
        <>
          <Button variant="ghost" size="sm" asChild>
            <Link to="/roteiros">
              <ArrowLeft className="mr-1 h-4 w-4" /> Voltar
            </Link>
          </Button>
          <WithTooltip label={dirty ? "Salvar alteracoes" : "Nenhuma alteracao pendente"}>
            <Button
              size="sm"
              variant="secondary"
              disabled={!dirty || saving}
              onClick={salvarRoteiro}
            >
              <Save className="mr-1 h-4 w-4" /> Salvar
            </Button>
          </WithTooltip>
          {latestJob ? (
            <>
              <Button size="sm" asChild>
                <Link to="/producao/$id" params={{ id: latestJob.id }}>
                  <Film className="mr-1 h-4 w-4" /> Ver vídeo
                </Link>
              </Button>
              {avatarMode === "set" && musicTrackId ? (
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={mixingMusic}
                  onClick={() => void aplicarTrilhaNoVideoFinal()}
                >
                  <Volume2 className="mr-1 h-4 w-4" />{" "}
                  {mixingMusic ? "Mixando trilha..." : "Aplicar trilha"}
                </Button>
              ) : null}
              <ConfirmAction
                title="Refazer este vídeo?"
                description={
                  <div className="space-y-3">
                    <p>{`Este roteiro já possui ${existingJobs.length} ${
                      existingJobs.length === 1 ? "vídeo" : "vídeos"
                    }. A nova versão consumirá créditos adicionais do HeyGen.`}</p>
                    {hasHighCreditConsumption ? <HighCreditConsumptionNotice compact /> : null}
                  </div>
                }
                confirmLabel="Refazer vídeo"
                onConfirm={() => void enviarProducao(true)}
                trigger={
                  <Button
                    size="sm"
                    variant="secondary"
                    title={
                      productionBlockedReason || !canSendToProduction
                        ? productionBlockedReason || "Revise o texto falado antes de enviar"
                        : "Gerar outra versão deste roteiro"
                    }
                    disabled={
                      saving ||
                      sending ||
                      Boolean(productionBlockedReason) ||
                      !selectedAvatarReady ||
                      !voiceId ||
                      !canSendToProduction
                    }
                  >
                    {sending ? (
                      <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                    ) : (
                      <History className="mr-1 h-4 w-4" />
                    )}
                    {sending ? "Enviando..." : "Refazer vídeo"}
                  </Button>
                }
              />
            </>
          ) : (
            <>
              <ConfirmAction
                title="Gerar prévia técnica de 10 segundos?"
                description={
                  avatarMode === "set"
                    ? "A prévia usa o look principal do Avatar Set para validar voz e enquadramento. O vídeo final usará as cenas e posições salvas. Este clique pode consumir créditos da conta."
                    : "Este clique envia somente o começo naturalizado ao HeyGen e pode consumir créditos da conta."
                }
                confirmLabel="Gerar prévia"
                onConfirm={() => void gerarPrevia()}
                trigger={
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={
                      storyMode ||
                      saving ||
                      previewing ||
                      !selectedAvatarReady ||
                      !voiceId ||
                      !approvalReady ||
                      !editorStateLoaded ||
                      !paidScriptVersion.finalSpeechHash
                    }
                  >
                    <Film className="mr-1 h-4 w-4" /> Gerar prévia
                  </Button>
                }
              />
              <ConfirmAction
                title="Gerar vídeo final?"
                description={
                  <div className="space-y-3">
                    <p>Este clique envia o roteiro ao HeyGen e pode consumir créditos da conta.</p>
                    {hasHighCreditConsumption ? <HighCreditConsumptionNotice compact /> : null}
                  </div>
                }
                confirmLabel="Gerar vídeo final"
                onConfirm={() => void enviarProducao(false)}
                trigger={
                  <Button
                    size="sm"
                    title={
                      productionBlockedReason || !canSendToProduction
                        ? productionBlockedReason || "Revise o texto falado antes de enviar"
                        : "Enviar roteiro ao HeyGen"
                    }
                    disabled={
                      saving ||
                      sending ||
                      Boolean(productionBlockedReason) ||
                      !selectedAvatarReady ||
                      !voiceId ||
                      !canSendToProduction
                    }
                  >
                    {sending ? (
                      <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                    ) : (
                      <Film className="mr-1 h-4 w-4" />
                    )}
                    {sending ? "Enviando..." : "Gerar vídeo final"}
                  </Button>
                }
              />
            </>
          )}
        </>
      }
    >
      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
          {naturalizing
            ? activeEditorOperation === "medical_rewrite"
              ? "Revisão com inteligência artificial em andamento."
              : "Ajuste de duração com inteligência artificial em andamento."
            : durationAnnouncement}
        </div>
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge {...scriptStatusLabel[draft.status]} />
            <StatusBadge {...riskLabel[draft.risco]} />
            <StatusBadge {...prioridadeLabel[draft.prioridade]} />
            {draft.editorialTone ? (
              <StatusBadge {...editorialToneLabel[draft.editorialTone]} />
            ) : null}
            {draft.link ? (
              <a
                href={draft.link}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-xs text-status-info underline-offset-2 hover:underline"
              >
                Fonte / artigo original
              </a>
            ) : null}
          </div>

          <div id="roteiro-editar" className="scroll-mt-20 rounded-xl border bg-card p-4 shadow-sm">
            <SectionHeading
              index={1}
              title="Roteiro"
              description="A fala final aprovada é a fonte do vídeo. O contexto editorial fica recolhido."
            />
            <div className="mt-4 space-y-4">
              <Field label="Título" htmlFor="script-title">
                <Input
                  id="script-title"
                  value={draft.titulo}
                  onChange={(e) => set("titulo", e.target.value)}
                />
              </Field>
              <div>
                <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <Label htmlFor="display-text">Fala final</Label>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      Texto que o avatar deve falar. Use a grafia correta para legenda e revisão.
                    </p>
                  </div>
                  <div className="flex flex-wrap justify-end gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        const restored = buildNarrationText(
                          draft,
                          durationSeconds === 10 ? "" : outroText,
                        );
                        editorRevisionRef.current += 1;
                        setNarrationText(restored);
                        setDisplayText(restored);
                        setSpokenText("");
                        setEditorSchemaValid(true);
                        setEditorTechnicalError(null);
                      }}
                    >
                      <RotateCcw className="mr-1 h-4 w-4" />
                      Restaurar
                    </Button>
                    {previousAiScript ? (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          const current = displayText;
                          editorRevisionRef.current += 1;
                          setDisplayText(previousAiScript);
                          setNarrationText(previousAiScript);
                          setSpokenText("");
                          setPreviousAiScript(current);
                          setEditorSchemaValid(true);
                          setEditorTechnicalError(null);
                        }}
                      >
                        <History className="mr-1 h-4 w-4" />
                        Desfazer IA
                      </Button>
                    ) : null}
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      disabled={naturalizing || displayText.trim().length < 20}
                      onClick={() => void executarEditorComIa("medical_rewrite")}
                    >
                      {naturalizing && activeEditorOperation === "medical_rewrite" ? (
                        <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                      ) : (
                        <Sparkles className="mr-1 h-4 w-4" />
                      )}
                      {naturalizing && activeEditorOperation === "medical_rewrite"
                        ? "Revisando..."
                        : "Revisar com IA"}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      disabled={naturalizing || displayText.trim().length < 20}
                      onClick={() => void executarEditorComIa("fit_duration")}
                    >
                      {naturalizing && activeEditorOperation === "fit_duration" ? (
                        <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                      ) : (
                        <Captions className="mr-1 h-4 w-4" />
                      )}
                      {naturalizing && activeEditorOperation === "fit_duration"
                        ? "Ajustando..."
                        : `Ajustar para ${durationSeconds}s`}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      onClick={salvarRoteiro}
                      disabled={!dirty || saving}
                    >
                      <Save className="mr-1 h-4 w-4" />
                      Salvar
                    </Button>
                  </div>
                </div>
                <Textarea
                  id="display-text"
                  rows={9}
                  value={displayText}
                  onChange={(event) => {
                    editorRevisionRef.current += 1;
                    setDisplayText(event.target.value);
                    setNarrationText(event.target.value);
                    setSpokenText("");
                    setEditorSchemaValid(true);
                    setEditorTechnicalError(null);
                    setLastEditorResult(null);
                  }}
                  aria-describedby={
                    editorTechnicalError
                      ? "script-duration-feedback script-editor-error"
                      : "script-duration-feedback"
                  }
                  className="min-h-56 leading-6"
                />
                <DurationControl
                  assessment={durationAssessment}
                  durationSeconds={durationSeconds}
                  onDurationChange={setProductionDuration}
                />
                {editorTechnicalError ? (
                  <div
                    ref={editorErrorRef}
                    id="script-editor-error"
                    tabIndex={-1}
                    className="mt-2 rounded-lg border border-status-danger/30 bg-status-danger/10 px-3 py-2 text-xs text-status-danger"
                    role="alert"
                  >
                    {editorTechnicalError} O texto anterior foi mantido; revise manualmente ou tente
                    novamente.
                  </div>
                ) : null}
                {staleEditorResult ? (
                  <StaleEditorResult
                    result={staleEditorResult}
                    onDiscard={() => setStaleEditorResult(null)}
                  />
                ) : null}
                <QualityIssuesCard
                  issues={qualityIssues}
                  hasBlockingIssues={blockingQualityIssues.length > 0}
                  onFixOutro={() => {
                    const corrected = normalizeNarrationOutro(displayText, outroText);
                    editorRevisionRef.current += 1;
                    setDisplayText(corrected);
                    setNarrationText(corrected);
                    setSpokenText("");
                    setEditorSchemaValid(true);
                    setEditorTechnicalError(null);
                  }}
                />
                {lastEditorResult ? (
                  <TitleAlignmentCard
                    result={lastEditorResult}
                    selected={titleChoice}
                    onUseSuggested={(suggested) => {
                      if (titleChoice === "current") setTitleBeforeSuggestion(draft.titulo);
                      set("titulo", suggested);
                      setTitleChoice("suggested");
                    }}
                    onKeepCurrent={() => {
                      if (titleChoice === "suggested") set("titulo", titleBeforeSuggestion);
                      setTitleChoice("current");
                    }}
                  />
                ) : null}
                <MedicalReviewCard
                  status={medicalReviewStatus}
                  approved={humanReviewApproved}
                  onToggle={() => setHumanReviewApproved((approved) => !approved)}
                />
                {lastEditorResult ? <QualityChecks result={lastEditorResult} /> : null}
              </div>
              <Accordion type="single" collapsible>
                <AccordionItem value="context">
                  <AccordionTrigger>Ver contexto do roteiro</AccordionTrigger>
                  <AccordionContent>
                    <div className="grid gap-3 pt-2 md:grid-cols-2">
                      <Field label="Tema">
                        <Input value={draft.tema} onChange={(e) => set("tema", e.target.value)} />
                      </Field>
                      <Field label="Hook">
                        <Textarea
                          rows={2}
                          value={draft.hook}
                          onChange={(e) => set("hook", e.target.value)}
                        />
                      </Field>
                      <Field label="Dor / conflito">
                        <Textarea
                          rows={2}
                          value={draft.dorConflito}
                          onChange={(e) => set("dorConflito", e.target.value)}
                        />
                      </Field>
                      <Field label="Explicação simples">
                        <Textarea
                          rows={3}
                          value={draft.explicacaoSimples}
                          onChange={(e) => set("explicacaoSimples", e.target.value)}
                        />
                      </Field>
                      <Field label="Virada / provocação">
                        <Textarea
                          rows={3}
                          value={draft.virada}
                          onChange={(e) => set("virada", e.target.value)}
                        />
                      </Field>
                      <Field label="Encerramento">
                        <Textarea
                          rows={2}
                          value={draft.cta}
                          onChange={(e) => set("cta", e.target.value)}
                        />
                      </Field>
                      <Field label="Cuidados médicos">
                        <Textarea
                          rows={2}
                          value={draft.cuidadosMedicos}
                          onChange={(e) => set("cuidadosMedicos", e.target.value)}
                        />
                      </Field>
                      <Field label="Formato">
                        <Input
                          value={draft.formatoSugerido}
                          onChange={(e) => set("formatoSugerido", e.target.value)}
                        />
                      </Field>
                      <Field label="Prioridade">
                        <Select
                          value={draft.prioridade}
                          onValueChange={(v) => set("prioridade", v as Prioridade)}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="alta">Alta</SelectItem>
                            <SelectItem value="media">Media</SelectItem>
                            <SelectItem value="baixa">Baixa</SelectItem>
                          </SelectContent>
                        </Select>
                      </Field>
                      <Field label="Status">
                        <Select
                          value={draft.status}
                          onValueChange={(v) => set("status", v as ScriptStatus)}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="aguardando_validacao">Rascunho</SelectItem>
                            <SelectItem value="em_revisao">Em edição</SelectItem>
                            <SelectItem value="aprovado_clinicamente">Pronto</SelectItem>
                            <SelectItem value="rejeitado">Arquivado</SelectItem>
                          </SelectContent>
                        </Select>
                      </Field>
                    </div>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            </div>
          </div>

          <div
            id="roteiro-produzir"
            className="scroll-mt-20 rounded-xl border bg-card p-4 shadow-sm"
          >
            <SectionHeading
              index={2}
              title="Produção"
              description="Escolha quem aparece, a duração e mantenha parâmetros técnicos recolhidos."
            />
            <div className="mt-4 space-y-4">
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <Label className="text-xs">Avatar</Label>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      Escolha um look único ou duas posições da mesma identidade.
                    </p>
                  </div>
                  {(catalogError || (!catalogLoading && !catalog?.avatars.length)) && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-7 px-2 text-[11px]"
                      onClick={() => loadCatalog(true)}
                    >
                      <RotateCcw className="mr-1 h-3.5 w-3.5" />
                      Atualizar
                    </Button>
                  )}
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <button
                    type="button"
                    aria-pressed={avatarMode === "single"}
                    onClick={() => {
                      setAvatarMode("single");
                      setAvatarSetId(null);
                      setPrimaryAvatarId(avatarId);
                    }}
                    className={cn(
                      "rounded-lg border px-3 py-2 text-left transition-colors hover:bg-muted/40",
                      avatarMode === "single" &&
                        "border-primary bg-primary/5 ring-1 ring-primary/30",
                    )}
                  >
                    <span className="block text-xs font-semibold">Look único</span>
                    <span className="mt-0.5 block text-[11px] text-muted-foreground">
                      Uma posição contínua para o avatar.
                    </span>
                  </button>
                  <button
                    type="button"
                    aria-pressed={avatarMode === "set"}
                    onClick={() => {
                      if (avatarSets[0]) chooseAvatarSet(selectedAvatarSet || avatarSets[0]);
                      else setAvatarSetDialogOpen(true);
                    }}
                    className={cn(
                      "rounded-lg border px-3 py-2 text-left transition-colors hover:bg-muted/40",
                      avatarMode === "set" && "border-primary bg-primary/5 ring-1 ring-primary/30",
                    )}
                  >
                    <span className="block text-xs font-semibold">Conjunto de looks</span>
                    <span className="mt-0.5 block text-[11px] text-muted-foreground">
                      Duas posições para cortes naturais entre cenas.
                    </span>
                  </button>
                </div>
                {avatarMode === "single" ? (
                  <AvatarPicker
                    value={avatarId}
                    avatars={catalog?.avatars || []}
                    loading={catalogLoading}
                    error={catalogError}
                    onChange={chooseAvatar}
                  />
                ) : (
                  <AvatarSetSelector
                    sets={avatarSets}
                    selectedId={avatarSetId}
                    selected={selectedAvatarSet}
                    avatars={catalog?.avatars || []}
                    selectedLooks={selectedSetLooks}
                    primaryAvatarId={primaryAvatarId}
                    loading={avatarSetsLoading}
                    onSelect={chooseAvatarSet}
                    onSaved={handleAvatarSetSaved}
                    onCreate={() => {
                      setEditingAvatarSet(null);
                      setAvatarSetDialogOpen(true);
                    }}
                    onEdit={(setToEdit) => {
                      setEditingAvatarSet(setToEdit);
                      setAvatarSetDialogOpen(true);
                    }}
                    onDelete={(setToDelete) => void handleDeleteAvatarSet(setToDelete)}
                    onPrimaryChange={(nextAvatarId) => {
                      setPrimaryAvatarId(nextAvatarId);
                      setAvatarId(nextAvatarId);
                    }}
                  />
                )}
                <AvatarSetEditorDialog
                  open={avatarSetDialogOpen}
                  initial={editingAvatarSet}
                  avatars={catalog?.avatars || []}
                  voices={catalog?.voices || HEYGEN_CATALOG_FALLBACK_VOICES}
                  onOpenChange={setAvatarSetDialogOpen}
                  onSaved={handleAvatarSetSaved}
                />
                {catalogError ? (
                  <p className="text-[11px] leading-4 text-status-danger">
                    HeyGen demorou para responder. Tente atualizar; se houver cache, o app usa a
                    ultima lista salva.
                  </p>
                ) : null}
              </div>
              <div className="space-y-2">
                <div>
                  <Label className="text-xs">Humor da voz</Label>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    Escolha a emoção da fala. “Confiante” é o padrão para evitar uma voz triste ou
                    melancólica.
                  </p>
                </div>
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
                  {VOICE_MOOD_OPTIONS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      aria-pressed={voiceMood === option.value}
                      onClick={() => setVoiceMood(option.value)}
                      className={cn(
                        "min-h-20 rounded-lg border px-3 py-2 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        voiceMood === option.value &&
                          "border-primary bg-primary/5 ring-1 ring-primary/30",
                      )}
                    >
                      <span className="flex items-center justify-between gap-2 text-xs font-semibold">
                        {option.label}
                        {voiceMood === option.value ? (
                          <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-primary" />
                        ) : null}
                      </span>
                      <span className="mt-1 block text-[11px] leading-4 text-muted-foreground">
                        {option.description}
                      </span>
                    </button>
                  ))}
                </div>
                <p className="text-[11px] leading-4 text-muted-foreground">
                  No Video Agent e no Cinematic, o humor vira direção de performance. Na produção
                  guiada, o app ajusta ritmo e entonação dentro dos limites da voz clonada.
                </p>
              </div>
              <div className="space-y-2">
                <div>
                  <Label className="text-xs">Quem monta o vídeo?</Label>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    Escolha entre produção guiada, agentes do HeyGen ou planejamento cinematográfico
                    por shots.
                  </p>
                </div>
                <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
                  <button
                    type="button"
                    aria-pressed={generationMode === "direct"}
                    onClick={() => setGenerationMode("direct")}
                    className={cn(
                      "rounded-lg border px-3 py-3 text-left transition-colors hover:bg-muted/40",
                      generationMode === "direct" &&
                        "border-primary bg-primary/5 ring-1 ring-primary/30",
                    )}
                  >
                    <span className="flex items-center gap-2 text-xs font-semibold">
                      <Film className="h-4 w-4 text-primary" /> Produção guiada pelo app
                    </span>
                    <span className="mt-1 block text-[11px] leading-4 text-muted-foreground">
                      Usa cenas, trocas de look e slides de transição definidos aqui.
                    </span>
                  </button>
                  <button
                    type="button"
                    aria-pressed={generationMode === "video_agent"}
                    onClick={() => setGenerationMode("video_agent")}
                    className={cn(
                      "rounded-lg border px-3 py-3 text-left transition-colors hover:bg-muted/40",
                      generationMode === "video_agent" &&
                        "border-primary bg-primary/5 ring-1 ring-primary/30",
                    )}
                  >
                    <span className="flex items-center gap-2 text-xs font-semibold">
                      <Sparkles className="h-4 w-4 text-primary" /> HeyGen Video Agent
                    </span>
                    <span className="mt-1 block text-[11px] leading-4 text-muted-foreground">
                      O HeyGen decide os cortes, interações e visuais do vídeo a partir do roteiro.
                    </span>
                  </button>
                  <button
                    type="button"
                    aria-pressed={generationMode === "cinematic"}
                    onClick={() => setGenerationMode("cinematic")}
                    className={cn(
                      "rounded-lg border px-3 py-3 text-left transition-colors hover:bg-muted/40",
                      generationMode === "cinematic" &&
                        "border-primary bg-primary/5 ring-1 ring-primary/30",
                    )}
                  >
                    <span className="flex items-center gap-2 text-xs font-semibold">
                      <Film className="h-4 w-4 text-primary" /> Cinematic
                    </span>
                    <span className="mt-1 block text-[11px] leading-4 text-muted-foreground">
                      Um fluxo separado para câmera, encenação e acontecimentos no ambiente.
                    </span>
                  </button>
                  <button
                    type="button"
                    aria-pressed={generationMode === "story"}
                    onClick={() => setGenerationMode("story")}
                    className={cn(
                      "cursor-pointer rounded-lg border px-3 py-3 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      generationMode === "story" &&
                        "border-primary bg-primary/5 ring-1 ring-primary/30",
                    )}
                  >
                    <span className="flex items-center gap-2 text-xs font-semibold">
                      <Clapperboard className="h-4 w-4 text-primary" /> História cinematográfica
                    </span>
                    <span className="mt-1 block text-[11px] leading-4 text-muted-foreground">
                      Claude planeja a história e você aprova cada shot e o orçamento antes de
                      gerar.
                    </span>
                  </button>
                </div>
                {generationMode === "video_agent" ? (
                  <div className="rounded-lg border border-status-info/30 bg-status-info/5 px-3 py-2 text-[11px] leading-4 text-muted-foreground">
                    <span className="font-semibold text-foreground">Modo autônomo do HeyGen.</span>{" "}
                    Enviamos fala aprovada, avatar, voz, humor, duração e formato. Nenhuma direção
                    cinematic entra neste fluxo. Não é necessário criar Scene Plan, slides ou render
                    local; a montagem e os elementos visuais são produzidos pelo HeyGen e consomem
                    créditos dele.
                  </div>
                ) : cinematicMode ? (
                  <div className="rounded-lg border border-primary/30 bg-primary/5 px-3 py-2 text-[11px] leading-4 text-muted-foreground">
                    <span className="font-semibold text-foreground">Fluxo Cinematic separado.</span>{" "}
                    Somente este modo recebe o briefing de câmera, encenação e ações de fundo. Ele
                    não usa Scene Plan, slides ou a direção dos fluxos anteriores.
                  </div>
                ) : storyMode ? (
                  <div className="rounded-lg border border-primary/30 bg-primary/5 px-3 py-2 text-[11px] leading-4 text-muted-foreground">
                    <span className="font-semibold text-foreground">
                      Planejamento com controle humano.
                    </span>{" "}
                    A fala permanece imutável. Nenhum shot do HeyGen é reservado antes de Story
                    Bible, storyboard, crítica e orçamento estarem aprovados.
                  </div>
                ) : null}
              </div>
              <div className="space-y-2">
                <Label className="text-xs">Duração</Label>
                <div className="flex flex-wrap gap-2">
                  {([10, 15, 30, 45, 60] as const).map((seconds) => (
                    <button
                      key={seconds}
                      type="button"
                      aria-pressed={durationSeconds === seconds}
                      onClick={() => setProductionDuration(seconds)}
                      className={cn(
                        "h-9 rounded-md border px-3 text-sm font-medium transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        durationSeconds === seconds && "border-primary bg-primary/10 text-primary",
                      )}
                    >
                      {seconds}s
                    </button>
                  ))}
                </div>
                <p className="text-[11px] leading-4 text-muted-foreground">
                  {durationSeconds <= 15
                    ? "A duração final acompanha a fala, sem silêncio para completar o tempo."
                    : storyMode
                      ? "A duração orienta o Story Director e será distribuída entre os shots aprovados."
                      : cinematicMode
                        ? "O Cinematic organiza câmera, encenação e acontecimentos dentro deste tempo aproximado."
                        : heygenAgentMode
                          ? "O HeyGen Video Agent organiza ritmo, cortes e visuais dentro deste tempo aproximado."
                          : "O app distribui a fala e as cenas dentro deste tempo aproximado."}
                </p>
                {hasHighCreditConsumption ? <HighCreditConsumptionNotice /> : null}
              </div>
              <Accordion type="single" collapsible>
                <AccordionItem value="advanced-production">
                  <AccordionTrigger>Configurações avançadas</AccordionTrigger>
                  <AccordionContent>
                    <div className="grid gap-3 pt-2 md:grid-cols-2">
                      <Field label="Orientação">
                        <Select
                          value={orientation}
                          onValueChange={(value) =>
                            setOrientation(value as "portrait" | "landscape")
                          }
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="portrait">Vertical - Reels e TikTok</SelectItem>
                            <SelectItem value="landscape">Horizontal - YouTube</SelectItem>
                          </SelectContent>
                        </Select>
                      </Field>
                      <div className="space-y-1">
                        <Label className="text-xs">Voz</Label>
                        <div className="flex min-h-10 items-center rounded-md border bg-muted/30 px-3 text-sm text-muted-foreground">
                          {selectedVoiceName}
                        </div>
                      </div>
                      <Field label="Modo de geração">
                        <Select
                          value={generationMode}
                          onValueChange={(value) => setGenerationMode(value as GenerationMode)}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem
                              value="direct"
                              disabled={selectedAvatar?.supportsDirectAvatar === false}
                            >
                              Direct Avatar
                            </SelectItem>
                            <SelectItem value="video_agent">Video Agent</SelectItem>
                            <SelectItem value="cinematic">Cinematic separado</SelectItem>
                            <SelectItem value="story">História cinematográfica</SelectItem>
                          </SelectContent>
                        </Select>
                      </Field>
                      <Field label="Ritmo da fala">
                        <Select
                          value={speechMode}
                          onValueChange={(value) =>
                            setSpeechMode(value as "natural" | "fiel" | "direto" | "enfatico")
                          }
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="natural">Natural - conversa fluida</SelectItem>
                            <SelectItem value="fiel">Fiel - segue o roteiro</SelectItem>
                            <SelectItem value="direto">Direto - curto e dinâmico</SelectItem>
                            <SelectItem value="enfatico">Enfático - mais presença</SelectItem>
                          </SelectContent>
                        </Select>
                      </Field>
                      <Field label="Encerramento falado">
                        <Select
                          value={ctaMode}
                          onValueChange={(value) =>
                            setCtaMode(value as "auto" | "manual" | "none" | "visual")
                          }
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="auto">Automático com Claude</SelectItem>
                            <SelectItem value="manual">Manual</SelectItem>
                            <SelectItem value="none">Sem encerramento falado</SelectItem>
                            <SelectItem value="visual">Apenas visual</SelectItem>
                          </SelectContent>
                        </Select>
                      </Field>
                      <Field label="Trilha de fundo">
                        <Select
                          value={musicTrackId || "none"}
                          onValueChange={(value) =>
                            setMusicTrackId(value === "none" ? null : value)
                          }
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Sem trilha" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="none">Sem trilha</SelectItem>
                            {musicTracks.map((track) => (
                              <SelectItem key={track.id} value={track.id}>
                                {track.name} · {track.mood}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </Field>
                    </div>
                    {selectedMusicTrack ? (
                      <div className="mt-3 rounded-md border bg-muted/20 p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2 text-sm">
                            <Volume2 className="h-4 w-4 text-primary" />
                            <span className="font-medium">{selectedMusicTrack.name}</span>
                            <span className="text-muted-foreground">
                              {selectedMusicTrack.artist} · {selectedMusicTrack.mood}
                            </span>
                          </div>
                          <span className="text-xs text-muted-foreground">
                            A trilha entra baixa e não substitui a voz.
                          </span>
                        </div>
                        <div className="mt-2 grid gap-2 md:grid-cols-[1fr_auto] md:items-center">
                          <audio
                            controls
                            preload="none"
                            className="h-9 w-full"
                            src={selectedMusicTrack.url}
                          >
                            Seu navegador não suporta a prévia de áudio.
                          </audio>
                          <label className="flex items-center gap-2 text-xs text-muted-foreground">
                            Volume {Math.round(musicVolume * 100)}%
                            <input
                              type="range"
                              min="3"
                              max="25"
                              value={Math.round(musicVolume * 100)}
                              onChange={(event) => setMusicVolume(Number(event.target.value) / 100)}
                              className="w-24 accent-primary"
                            />
                          </label>
                        </div>
                      </div>
                    ) : null}
                    <p className="mt-2 text-[11px] leading-4 text-muted-foreground">
                      A música só é mixada localmente no MP4 final composto; não cria chamada Claude
                      nem HeyGen.
                    </p>
                    <div className="mt-3 grid gap-3 md:grid-cols-2">
                      <FriendlySwitch
                        icon={<Captions className="h-4 w-4" />}
                        label="Legendas automáticas"
                        description="Texto em português acompanhando a fala"
                        checked={captions}
                        onCheckedChange={setCaptions}
                      />
                      <FriendlySwitch
                        icon={<Sparkles className="h-4 w-4" />}
                        label="Melhorar pronúncia"
                        description="Ajusta siglas, remédios e números para a voz"
                        checked={optimizePronunciation}
                        onCheckedChange={setOptimizePronunciation}
                      />
                    </div>
                    {ctaMode === "manual" && durationSeconds !== 10 ? (
                      <div className="mt-3 rounded-md border border-status-info/30 bg-status-info/5 px-3 py-3">
                        <Label htmlFor="outro-text" className="text-xs font-medium">
                          Frase final do vídeo
                        </Label>
                        <div className="mt-2 flex gap-2">
                          <Input
                            id="outro-text"
                            value={outroText}
                            onChange={(event) => setOutroText(event.target.value)}
                            onBlur={() =>
                              setDisplayText((current) => {
                                editorRevisionRef.current += 1;
                                return normalizeNarrationOutro(current, outroText);
                              })
                            }
                            placeholder="Ex.: Me siga para mais dicas."
                            maxLength={180}
                          />
                          <Button
                            type="button"
                            variant="secondary"
                            onClick={() =>
                              setDisplayText((current) => {
                                editorRevisionRef.current += 1;
                                return normalizeNarrationOutro(current, outroText);
                              })
                            }
                          >
                            Aplicar
                          </Button>
                        </div>
                      </div>
                    ) : null}
                    <div className="mt-3">
                      <Label htmlFor="spoken-text">Texto enviado à voz</Label>
                      <p className="mt-0.5 text-[11px] text-muted-foreground">
                        Ajustes fonéticos ficam somente aqui, nunca na legenda.
                      </p>
                      <Textarea
                        id="spoken-text"
                        rows={5}
                        value={spokenText}
                        onChange={(event) => setSpokenText(event.target.value)}
                        className="mt-2 leading-6"
                      />
                    </div>
                    {performancePlan ? (
                      <div className="mt-3 rounded-md border bg-muted/30 px-3 py-2 text-[11px] leading-4 text-muted-foreground">
                        <span className="font-medium text-foreground">Plano de performance:</span>{" "}
                        {performancePlan.tone} · {performancePlan.pace} · {performancePlan.emotion}{" "}
                        · speed {performancePlan.recommendedVoiceSpeed}.
                      </div>
                    ) : null}
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
              <div className="mt-2 flex items-start gap-2 rounded-md border border-status-success/30 bg-status-success/10 px-3 py-2 text-[11px] leading-4 text-muted-foreground">
                <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-status-success" />A fala
                exata será validada antes do envio ao HeyGen. Dose, promessa ou instrução
                prescritiva bloqueiam a geração paga até a correção.
              </div>
            </div>
          </div>

          <div
            id="roteiro-direcao"
            className="scroll-mt-20 rounded-xl border bg-card p-4 shadow-sm"
          >
            <SectionHeading
              index={3}
              title="Direção"
              description={
                storyMode
                  ? "Planeje a narrativa, revise cada shot e aprove o pior cenário de custo antes de gerar vídeo."
                  : cinematicMode
                    ? "Briefing exclusivo do Cinematic. Ele não altera Scene Plan, slides ou o Video Agent comum."
                    : generationMode === "video_agent"
                      ? "O Video Agent comum cria a edição sem receber nenhuma direção cinematic."
                      : "Depois de escolher duração e avatar, deixe o Claude organizar cenas, cortes de look e slide de transição."
              }
            />
            <div className="mt-4">
              {storyMode ? (
                <StoryModeEditor
                  scriptId={id}
                  title={draft.titulo}
                  durationSeconds={durationSeconds}
                  orientation={orientation}
                  characterId={avatarSetId || avatarId || null}
                  lookId={primaryAvatarId || avatarId || null}
                  characterDescription={
                    selectedAvatar?.name
                      ? `${selectedAvatar.name}, identidade visual aprovada no catálogo.`
                      : ""
                  }
                  wardrobeDirection={selectedAvatarSet?.name || "Manter o look aprovado."}
                />
              ) : cinematicMode ? (
                <div className="space-y-3">
                  <div className="rounded-xl border bg-muted/20 p-4">
                    <Label htmlFor="cinematic-prompt" className="text-sm font-semibold">
                      Direção cinematic
                    </Label>
                    <p className="mt-1 max-w-3xl text-xs leading-5 text-muted-foreground">
                      Escreva clima, câmera, ações de fundo e apoios visuais. O agente interpreta
                      isso como direção visual, nunca como fala.
                    </p>
                    <Textarea
                      id="cinematic-prompt"
                      rows={5}
                      value={cinematicPrompt}
                      onChange={(event) => setCinematicPrompt(event.target.value)}
                      className="mt-3 leading-6"
                      placeholder="Ex.: Gui andando pela cidade, tom editorial sóbrio, câmera acompanhando. Ao fundo, sinais discretos de busca por solução rápida, limitação de mobilidade e dificuldade no transporte. Evitar humor, caricatura e exagero."
                    />
                  </div>
                  <div className="rounded-xl border border-primary/30 bg-primary/5 p-4">
                    <div className="flex items-start gap-2">
                      <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                      <div>
                        <h3 className="text-sm font-semibold">Direção exclusiva do Cinematic</h3>
                        <p className="mt-1 max-w-3xl text-xs leading-5 text-muted-foreground">
                          Ao enviar este modo, o agente recebe a fala aprovada e somente este
                          briefing. Os fluxos de cenas, slides e Video Agent comum permanecem
                          separados.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              ) : generationMode === "video_agent" ? (
                <div className="rounded-xl border border-status-info/30 bg-status-info/5 p-4">
                  <div className="flex items-start gap-2">
                    <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                    <div>
                      <h3 className="text-sm font-semibold">Video Agent sem Cinematic</h3>
                      <p className="mt-1 max-w-3xl text-xs leading-5 text-muted-foreground">
                        Este fluxo recebe somente fala, performance, avatar, duração e formato.
                        Nenhum briefing cinematic, Scene Plan ou slide local é enviado.
                      </p>
                    </div>
                  </div>
                </div>
              ) : (
                <>
                  <ScenePlanEditor
                    scriptId={id}
                    loading={scenePlanLoading}
                    plan={scenePlan}
                    fallbackText={displayText || narrationText}
                    displayText={displayText || narrationText}
                    spokenText={spokenText}
                    durationSeconds={durationSeconds}
                    performancePlan={performancePlan}
                    availableRoles={sceneRoles}
                    transitionSlideGenerating={transitionSlideGenerating}
                    onSaved={setScenePlan}
                    onGenerateTransitionSlides={gerarSlidesTransicao}
                  />
                  <VisualPlanDirector
                    scriptId={id}
                    scenePlan={scenePlan}
                    visualPlan={visualPlan}
                    loading={visualPlanLoading}
                    displayText={displayText || narrationText}
                    spokenText={spokenText}
                    durationSeconds={durationSeconds}
                    performancePlan={performancePlan}
                    onSaved={setVisualPlan}
                    videoSlideRender={videoSlideRender}
                    videoSlideRenderLoading={videoSlideRenderLoading}
                    onRendered={setVideoSlideRender}
                  />
                  <Accordion type="single" collapsible className="mt-3">
                    <AccordionItem value="scene-generation-details">
                      <AccordionTrigger>Detalhes técnicos da geração por cena</AccordionTrigger>
                      <AccordionContent>
                        <SceneGenerationSummary
                          plan={sceneGenerationPlan}
                          loading={sceneGenerationPlanLoading}
                          durationSeconds={durationSeconds}
                          avatarMode={avatarMode}
                        />
                      </AccordionContent>
                    </AccordionItem>
                  </Accordion>
                </>
              )}
            </div>
          </div>

          <div id="roteiro-gerar" className="scroll-mt-20 rounded-xl border bg-card p-4 shadow-sm">
            <SectionHeading
              index={4}
              title="Gerar"
              description="Confirme que fala, avatar, direção e compliance estão prontos antes de gastar créditos."
            />
            <div className="mt-4 space-y-3">
              {storyMode ? (
                <div className="rounded-xl border border-primary/20 bg-primary/5 p-4">
                  <div className="flex items-start gap-2">
                    <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                    <div>
                      <h3 className="text-sm font-semibold">Geração protegida por aprovação</h3>
                      <p className="mt-1 max-w-3xl text-xs leading-5 text-muted-foreground">
                        Use a etapa Direção para aprovar Story Bible, todos os shots, a crítica e o
                        orçamento. A geração por shots será liberada somente com esses vínculos
                        válidos.
                      </p>
                    </div>
                  </div>
                </div>
              ) : (
                <ProductionGateChecklist
                  items={productionChecklist}
                  blockedReason={productionBlockedReason}
                  latestJobId={latestJob?.id}
                  dirty={dirty}
                  narrationWords={narrationWords}
                  estimatedSpeechSeconds={estimatedSpeechSeconds}
                  onOpenLatest={
                    latestJob
                      ? () => navigate({ to: "/producao/$id", params: { id: latestJob.id } })
                      : undefined
                  }
                  onSend={() => void enviarProducao(false)}
                />
              )}
              {latestPreview ? (
                <div className="rounded-lg border border-status-info/30 bg-status-info/5 p-3 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="font-semibold">Prévia técnica de avatar e voz</div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        Valida voz e enquadramento; não representa toda a composição final.
                      </p>
                    </div>
                    <Button size="sm" variant="secondary" asChild>
                      <Link to="/producao/$id" params={{ id: latestPreview.id }}>
                        Abrir prévia
                      </Link>
                    </Button>
                  </div>
                </div>
              ) : null}
              {captureHook && siblingCaptureScripts.length > 1 ? (
                <Accordion type="single" collapsible>
                  <AccordionItem value="capture-variants">
                    <AccordionTrigger>Comparar roteiros de 10s</AccordionTrigger>
                    <AccordionContent>
                      <div className="grid gap-2 pt-2 sm:grid-cols-3">
                        {siblingCaptureScripts.map((candidate, index) => (
                          <Link
                            key={candidate.id}
                            to="/roteiros/$id"
                            params={{ id: candidate.id }}
                            className={`rounded-lg border p-3 text-sm transition-colors ${candidate.id === script.id ? "border-status-info bg-background" : "bg-background/60 hover:border-status-info/50"}`}
                          >
                            <div className="text-[10px] font-semibold uppercase tracking-wider text-status-info">
                              Teste {index + 1}
                            </div>
                            <p className="mt-1 line-clamp-3 text-xs text-muted-foreground">
                              {candidate.textoFalado}
                            </p>
                          </Link>
                        ))}
                      </div>
                    </AccordionContent>
                  </AccordionItem>
                </Accordion>
              ) : null}
              <Accordion type="single" collapsible>
                <AccordionItem value="review-highlight">
                  <AccordionTrigger>Ver revisão com highlight</AccordionTrigger>
                  <AccordionContent>
                    <div className="space-y-2 pt-2 text-sm leading-relaxed">
                      <Preview label="Hook" text={draft.hook} palavras={palavras} />
                      <Preview
                        label="Dor / conflito"
                        text={draft.dorConflito}
                        palavras={palavras}
                      />
                      <Preview
                        label="Explicação"
                        text={draft.explicacaoSimples}
                        palavras={palavras}
                      />
                      <Preview label="Virada" text={draft.virada} palavras={palavras} />
                      <Preview label="Encerramento" text={draft.cta} palavras={palavras} />
                    </div>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            </div>
          </div>
        </div>

        <div id="roteiro-compliance" className="scroll-mt-20 space-y-3">
          <div className="rounded-xl border bg-card p-4 shadow-sm">
            <h3 className="mb-3 font-display text-sm font-semibold">Timeline</h3>
            <StatusTimeline steps={timeline} />
          </div>
          <ProductionReadinessCard
            catalogLoading={catalogLoading}
            catalogError={catalogError}
            avatarReady={selectedAvatarReady}
            voiceReady={Boolean(voiceId)}
            speechReady={blockingQualityIssues.length === 0}
            speechIssue={qualityIssues[0]}
            approvalReady={approvalReady}
            saved={!dirty}
          />
          <CompliancePanel
            fields={complianceFields}
            palavrasProibidas={palavras}
            rules={complianceRules}
          />
        </div>
      </div>
    </AppShell>
  );
}

function SectionHeading({
  index,
  title,
  description,
}: {
  index: number;
  title: string;
  description: string;
}) {
  return (
    <div>
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-status-info">
        {String(index).padStart(2, "0")}
      </div>
      <h3 className="font-display text-sm font-semibold">{title}</h3>
      <p className="mt-1 text-xs text-muted-foreground">{description}</p>
    </div>
  );
}

function SceneGenerationSummary({
  plan,
  loading,
  durationSeconds,
  avatarMode,
}: {
  plan: SceneGenerationResult | null;
  loading: boolean;
  durationSeconds: 10 | 15 | 30 | 45 | 60;
  avatarMode: "single" | "set";
}) {
  return (
    <div className="mt-3 space-y-2 rounded-lg border border-status-warning/30 bg-status-warning/5 p-3">
      <div className="flex items-start gap-2">
        <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-status-warning" />
        <div>
          <h4 className="text-xs font-semibold">Checklist de geração por cena</h4>
          <p className="text-[11px] leading-4 text-muted-foreground">
            Nenhum job foi criado. Antes de qualquer geração paga, confira cenas, looks, voz e
            duração.
          </p>
        </div>
      </div>
      {loading ? <p className="text-xs text-muted-foreground">Montando estimativa...</p> : null}
      {plan ? (
        <>
          <div className="flex flex-wrap gap-2 text-[11px]">
            <span className="rounded-full bg-background px-2 py-1">{plan.sceneCount} cenas</span>
            <span className="rounded-full bg-background px-2 py-1">
              {plan.estimatedCalls} chamadas HeyGen estimadas
            </span>
            <span className="rounded-full bg-background px-2 py-1">
              {durationSeconds}s selecionados
            </span>
            <span className="rounded-full bg-background px-2 py-1">
              {plan.requests[0]?.voiceId || "voz não definida"}
            </span>
          </div>
          <div className="space-y-1">
            {plan.requests.map((request) => (
              <div
                key={request.sceneId}
                className="grid gap-1 rounded-md border bg-background px-2 py-1.5 text-[11px] md:grid-cols-[80px_1fr_1.5fr]"
              >
                <span className="font-semibold">Cena {request.order}</span>
                <span>
                  {avatarMode === "set" ? `Look ${request.avatarId}` : "Avatar principal"}
                </span>
                <span className="truncate text-muted-foreground">{request.spokenText}</span>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-status-warning">{plan.warning}</p>
        </>
      ) : (
        <p className="text-[11px] text-muted-foreground">
          Salve um Scene Plan para visualizar a estimativa por cena.
        </p>
      )}
    </div>
  );
}

function buildScriptTimeline(
  status: ScriptStatus,
  ts: { criadoEm: string; validadoEm?: string },
): TimelineStep[] {
  const fmt = (iso?: string) => (iso ? new Date(iso).toLocaleString("pt-BR") : undefined);
  if (status === "rejeitado") {
    return [
      { key: "criado", label: "Roteiro criado", state: "done", timestamp: fmt(ts.criadoEm) },
      { key: "validado", label: "Arquivado", state: "error", hint: "Fora do fluxo de producao" },
    ];
  }
  const order: ScriptStatus[] = ["aguardando_validacao", "em_revisao", "aprovado_clinicamente"];
  const currentIdx = order.indexOf(status);
  const labels: Record<ScriptStatus, string> = {
    aguardando_validacao: "Rascunho",
    em_revisao: "Em edicao",
    aprovado_clinicamente: "Pronto",
    rejeitado: "Arquivado",
  };
  return [
    { key: "criado", label: "Roteiro criado", state: "done", timestamp: fmt(ts.criadoEm) },
    ...order.map((k, i) => {
      const state: TimelineStep["state"] =
        i < currentIdx ? "done" : i === currentIdx ? "current" : "pending";
      const step: TimelineStep = { key: k, label: labels[k], state };
      if (k === "aprovado_clinicamente" && state === "done") {
        step.timestamp = fmt(ts.validadoEm);
      }
      return step;
    }),
    {
      key: "producao",
      label: "Enviar para producao",
      state: status === "aprovado_clinicamente" ? "current" : "pending",
      hint:
        status === "aprovado_clinicamente"
          ? "Pronto para producao"
          : "Quando o roteiro estiver pronto",
    },
  ];
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <Label htmlFor={htmlFor} className="text-xs">
        {label}
      </Label>
      {children}
    </div>
  );
}

function captureHookDuration(script?: Script): 10 | 15 | null {
  if (!script?.formatoSugerido.toLowerCase().includes("hook de captura")) return null;
  const duration = script.formatoSugerido.match(/(10|15) segundos/i)?.[1];
  return duration === "15" ? 15 : 10;
}

function buildNarrationText(script: Script, outro = DEFAULT_OUTRO): string {
  // Se o roteiro ja veio com o texto falado gerado pela IA (fluxo com tom
  // editorial), usa esse texto pronto em vez de remontar as partes.
  if (script.textoFalado?.trim()) {
    return normalizeNarrationOutro(script.textoFalado.trim(), outro);
  }
  const body = [
    script.hook,
    script.dorConflito,
    script.explicacaoSimples,
    script.virada,
    script.cta,
  ]
    .map((part) => part.trim())
    .filter(Boolean)
    .join("\n\n");
  return normalizeNarrationOutro(body || outro, outro);
}

function Preview({ label, text, palavras }: { label: string; text: string; palavras: string[] }) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="text-sm">
        <HighlightedText text={text} palavrasProibidas={palavras} />
      </div>
    </div>
  );
}
