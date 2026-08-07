import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { CompliancePanel, HighlightedText } from "@/components/compliance-panel";
import { StatusTimeline, type TimelineStep } from "@/components/status-timeline";
import { WithTooltip } from "@/components/with-tooltip";
import { ConfirmAction } from "@/components/confirm-action";
import {
  DEFAULT_OUTRO,
  maximumWordsForDuration,
  narrationQualityIssues,
  normalizeNarrationOutro,
  removeNarrationOutro,
} from "@/lib/script-quality";
import { editorialToneLabel, prioridadeLabel, riskLabel, scriptStatusLabel } from "@/lib/status";
import { useStore } from "@/lib/store";
import {
  createHeyGenPreview,
  createHeyGenVideo,
  deleteAvatarSet,
  fetchAvatarSets,
  fetchHeyGenCatalog,
  fetchHeyGenStyles,
  fetchProductionProfile,
  fetchSceneGenerationPlan,
  fetchScenePlan,
  fetchVideoSlideRender,
  fetchVisualPlan,
  generateSceneDirection,
  generateVisualDirection,
  naturalizeScript,
  saveAvatarSet,
  saveProductionProfile,
  saveScript,
  saveScenePlan,
  renderVideoSlides,
  submitSceneGeneration,
  saveVisualPlan,
  type AvatarSet,
  type AvatarSetLook,
  type AvatarSetRole,
  type HeyGenCatalog,
  type HeyGenStyle,
  type ScenePlan,
  type SceneGenerationResult,
  type VideoVisualLayout,
  type VideoVisualType,
  type VideoSlideRender,
  type VisualPlan,
} from "@/lib/api/local";
import type { Prioridade, Script, ScriptStatus } from "@/lib/mock-data";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
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
  ArrowRight,
  ArrowLeft,
  Captions,
  CheckCircle2,
  Circle,
  Film,
  History,
  Pencil,
  Plus,
  RotateCcw,
  Save,
  ShieldCheck,
  Sparkles,
  Trash2,
  TriangleAlert,
  UserRound,
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
  const [previewing, setPreviewing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [catalog, setCatalog] = useState<HeyGenCatalog | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [styles, setStyles] = useState<HeyGenStyle[]>([]);
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
  const [sceneGenerationPlan, setSceneGenerationPlan] = useState<SceneGenerationResult | null>(null);
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
  const [generationMode, setGenerationMode] = useState<"direct" | "video_agent">("direct");
  const [ctaMode, setCtaMode] = useState<"auto" | "manual" | "none" | "visual">("auto");
  const [captions, setCaptions] = useState(true);
  const [optimizePronunciation, setOptimizePronunciation] = useState(true);
  const [styleId, setStyleId] = useState("");
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
  const lastSavedProfileKey = useRef("");
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
  const qualityIssues = useMemo(
    () =>
      narrationQualityIssues(displayText, durationSeconds, ctaMode === "manual" ? outroText : ""),
    [ctaMode, displayText, durationSeconds, outroText],
  );
  const blockingQualityIssues = useMemo(
    () => qualityIssues.filter((issue) => !issue.startsWith("Texto muito curto")),
    [qualityIssues],
  );
  const hasHighCreditConsumption = durationSeconds >= 45;
  const approvalReady = draft?.status === "aprovado_clinicamente";
  const narrationWords = displayText.trim().split(/\s+/).filter(Boolean).length;
  const estimatedSpeechSeconds = Math.max(1, Math.round(narrationWords / 2.4));

  useEffect(() => {
    if (script) {
      setDraft(script);
      const savedCaptureDuration = captureHookDuration(script);
      const savedOutro = savedCaptureDuration === 10 ? "" : script.outroText || DEFAULT_OUTRO;
      setOutroText(savedOutro);
      const initialText = buildNarrationText(script, savedOutro);
      setNarrationText(initialText);
      setDisplayText(initialText);
      setSpokenText(initialText);
      if (savedCaptureDuration !== null) {
        setDurationSeconds(savedCaptureDuration);
        setSpeechMode("direto");
      }
    }
  }, [script]);

  useEffect(() => {
    let cancelled = false;
    setProfileLoaded(false);
    setAvatarId("");
    setVoiceId("");
    setAvatarMode("single");
    setAvatarSetId(null);
    setPrimaryAvatarId("");
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
          setGenerationMode(profile.generationMode);
          lastSavedProfileKey.current = [
            profile.avatarId,
            profile.voiceId,
            profile.speechMode,
            profile.generationMode,
            profile.avatarMode || "single",
            profile.avatarSetId || "",
            profile.primaryAvatarId || profile.avatarId,
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
    fetchHeyGenStyles("cinematic")
      .then((data) => setStyles(data.styles))
      .catch(() => setStyles([]));

    try {
      const saved = localStorage.getItem("ai-video-creator-studio-defaults");
      if (saved) {
        const defaults = JSON.parse(saved) as {
          orientation?: "portrait" | "landscape";
          styleId?: string | null;
          captions?: boolean;
        };
        if (defaults.orientation) setOrientation(defaults.orientation);
        if (defaults.styleId) setStyleId(defaults.styleId);
        if (typeof defaults.captions === "boolean") setCaptions(defaults.captions);
      }
    } catch {
      /* configuracao local antiga ou invalida */
    }
  }, []);

  useEffect(() => {
    if (!scenePlan) {
      setSceneGenerationPlan(null);
      return;
    }
    let cancelled = false;
    setSceneGenerationPlanLoading(true);
    fetchSceneGenerationPlan(id, { speechMode, orientation })
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
  }, [avatarMode, avatarSetId, id, orientation, primaryAvatarId, profileLoaded, scenePlan?.updatedAt, speechMode, voiceId]);
  const dirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(script), [draft, script]);
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
        .filter(
          (item): item is { look: AvatarSetLook; avatar: HeyGenCatalog["avatars"][number] } =>
            Boolean(item.avatar),
        ) || [],
    [catalog?.avatars, selectedAvatarSet],
  );
  const avatarSetReady = Boolean(selectedAvatarSet && selectedSetLooks.length >= 2 && primaryAvatarId);
  const productionModeReady = avatarMode === "single" || Boolean(avatarMode === "set" && sceneGenerationPlan);
  const requiredVisualCount = scenePlan ? Math.max(0, scenePlan.scenes.length - 1) : 0;
  const visualProductionReady =
    avatarMode === "single" ||
    requiredVisualCount === 0 ||
    Boolean(visualPlan && (videoSlideRender?.renderedCount ?? 0) >= requiredVisualCount);
  const selectedAvatarReady = avatarMode === "single" ? Boolean(avatarId) : avatarSetReady;
  const sceneRoles = useMemo<AvatarSetRole[]>(
    () =>
      selectedAvatarSet?.looks.map((look) => look.role) || ["primary"],
    [selectedAvatarSet],
  );
  const canSendToProduction =
    blockingQualityIssues.length === 0 && approvalReady && selectedAvatarReady && productionModeReady && visualProductionReady;

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
    if (!profileLoaded || !avatarId || !voiceId || (avatarMode === "set" && !avatarSetReady)) return;
    const key = [
      avatarId,
      voiceId,
      speechMode,
      generationMode,
      avatarMode,
      avatarSetId || "",
      primaryAvatarId,
    ].join("|");
    if (key === lastSavedProfileKey.current) return;
    const timeout = window.setTimeout(() => {
      saveProductionProfile(id, {
        avatarId: avatarMode === "set" ? primaryAvatarId : avatarId,
        voiceId,
        speechMode,
        generationMode,
        avatarMode,
        avatarSetId: avatarMode === "set" ? avatarSetId : null,
        primaryAvatarId: avatarMode === "set" ? primaryAvatarId : avatarId,
      })
        .then((profile) => {
          lastSavedProfileKey.current = [
            profile.avatarId,
            profile.voiceId,
            profile.speechMode,
            profile.generationMode,
            profile.avatarMode || "single",
            profile.avatarSetId || "",
            profile.primaryAvatarId || profile.avatarId,
          ].join("|");
        })
        .catch(() => toast.error("Nao consegui salvar o perfil de producao."));
    }, 500);
    return () => window.clearTimeout(timeout);
  }, [avatarId, avatarMode, avatarSetId, avatarSetReady, generationMode, id, primaryAvatarId, profileLoaded, speechMode, voiceId]);

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
      setAvatarSets((current) => current.filter((avatarSet) => avatarSet.id !== avatarSetToDelete.id));
      if (avatarSetId === avatarSetToDelete.id) {
        setAvatarMode("single");
        setAvatarSetId(null);
        setPrimaryAvatarId(avatarId);
      }
      toast.success("Avatar Set excluído.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Nao foi possivel excluir o Avatar Set.");
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
    setDurationSeconds(nextDuration);
    if (nextDuration === 10) {
      setDisplayText((current) => removeNarrationOutro(current, outroText));
      setSpokenText((current) => removeNarrationOutro(current, outroText));
      setNarrationText((current) => removeNarrationOutro(current, outroText));
      setOutroText("");
      setSpeechMode("direto");
    } else if (!outroText.trim()) {
      setOutroText(DEFAULT_OUTRO);
      setDisplayText((current) => normalizeNarrationOutro(current, DEFAULT_OUTRO));
      setSpokenText((current) => normalizeNarrationOutro(current, DEFAULT_OUTRO));
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
  const productionBlockedReason = blockingQualityIssues[0]
    ? `Revise a fala final: ${blockingQualityIssues[0]}`
    : dirty
      ? "Salve o roteiro antes de enviar."
      : !approvalReady
        ? 'Conclua a revisão e altere o status do roteiro para "Pronto".'
        : catalogLoading
          ? "Carregando avatares e vozes da HeyGen."
          : !profileLoaded
            ? "Carregando perfil de producao do roteiro."
            : avatarMode === "set" && !selectedAvatarSet
              ? "Selecione um Avatar Set."
              : avatarMode === "set" && !avatarSetReady
                ? "O Avatar Set precisa ter duas posições disponíveis no catálogo."
                : avatarMode === "set" && !productionModeReady
                  ? "Salve o Scene Plan antes de gerar o vídeo com duas posições."
                  : avatarMode === "set" && !visualProductionReady
                    ? `Gere e renderize ${requiredVisualCount} apoio(s) visual(is) antes de enviar.`
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
      detail: approvalReady ? "Status Pronto" : 'Mude o status para "Pronto" em Roteiro → Ver contexto.',
    },
    {
      label: "Roteiro salvo",
      ready: !dirty,
      detail: dirty ? "Salve as alterações antes de enviar." : "Sem alterações pendentes.",
    },
    {
      label: avatarMode === "set" ? "Avatar Set" : "Avatar",
      ready: selectedAvatarReady,
      detail:
        avatarMode === "set"
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
    {
      label: "Cenas",
      ready: avatarMode === "single" || Boolean(scenePlan && scenePlan.scenes.length >= 1),
      detail:
        avatarMode === "single"
          ? "Look único não precisa de plano de cenas."
          : scenePlan
            ? `${scenePlan.scenes.length} cena(s) salvas.`
            : "Salve o plano de cenas.",
    },
    {
      label: "Slide de transição",
      ready: avatarMode === "single" || requiredVisualCount === 0 || visualProductionReady,
      detail:
        avatarMode === "single" || requiredVisualCount === 0
          ? "Não obrigatório para este formato."
          : visualProductionReady
            ? `${requiredVisualCount} apoio(s) renderizado(s).`
            : `Gere e renderize ${requiredVisualCount} apoio(s).`,
    },
    {
      label: "Compliance da fala",
      ready: blockingQualityIssues.length === 0,
      detail: blockingQualityIssues[0] || "Sem bloqueios.",
    },
  ];

  async function enviarProducao(forceNewVersion = false) {
    if (!draft || !script) return;
    if (avatarMode === "set" && !sceneGenerationPlan) {
      toast.error("Salve o Scene Plan antes de gerar o vídeo por cenas.");
      return;
    }
    if (productionBlockedReason || !canSendToProduction) {
      toast.error(
        blockingQualityIssues[0]
          ? `Revise o texto falado antes de enviar: ${blockingQualityIssues[0]}`
          : productionBlockedReason || 'Conclua a revisão e altere o status do roteiro para "Pronto".',
      );
      return;
    }
    setSending(true);
    try {
      let scriptToSend = script;
      if (dirty) {
        const saved = await saveScript(draft);
        updateScript(saved.id, saved);
        setDraft(saved);
        scriptToSend = saved;
      }
      if (avatarMode === "set") {
        const sceneResult = await submitSceneGeneration(scriptToSend.id, {
          orientation,
          durationSeconds,
          speechMode,
          captions,
          optimizePronunciation,
        });
        sceneResult.jobs.forEach((job) => addVideoJob(job));
        const firstJob = sceneResult.jobs[0];
        if (!firstJob) throw new Error("A HeyGen não retornou jobs por cena.");
        toast.success(`${sceneResult.jobs.length} cena(s) enviada(s) para produção no HeyGen.`);
        navigate({ to: "/producao/$id", params: { id: firstJob.id } });
        return;
      }
      const job = await createHeyGenVideo(scriptToSend.id, {
        avatarId,
        voiceId,
        orientation,
        durationSeconds,
        speechMode,
        generationMode,
        ctaMode,
        captions,
        optimizePronunciation,
        styleId: styleId || undefined,
        forceNewVersion,
        narrationText: displayText,
        displayText,
        spokenText,
        outroText: ctaMode === "manual" ? outroText : "",
      });
      addVideoJob(job);
      toast.success(
        dirty
          ? "Roteiro salvo e enviado para producao no HeyGen."
          : "Roteiro enviado para producao no HeyGen.",
      );
      navigate({ to: "/producao/$id", params: { id: job.id } });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Nao foi possivel enviar ao HeyGen.");
    } finally {
      setSending(false);
    }
  }

  async function salvarRoteiro() {
    if (!draft) return;
    setSaving(true);
    try {
      const saved = await saveScript(draft);
      updateScript(saved.id, saved);
      setDraft(saved);
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
      toast.success(
        savedPlan.scenes.length > 2
          ? "Slides de transição gerados pelo Claude."
          : "Slide de transição gerado pelo Claude.",
      );
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Nao foi possivel gerar slide de transição.");
      throw error;
    } finally {
      setTransitionSlideGenerating(false);
    }
  }

  async function naturalizarFala() {
    if (!draft || !narrationText.trim()) return;
    setNaturalizing(true);
    try {
      const naturalized = await naturalizeScript({
        text: displayText || narrationText,
        medicalCautions: draft.cuidadosMedicos,
        durationSeconds,
        outro: ctaMode === "manual" ? outroText : "",
        ctaMode,
        manualCta: outroText,
        recentCtas: videoJobs
          .map((job) => String(job.productionSettings?.outroText || ""))
          .filter(Boolean)
          .slice(0, 5),
      });
      setDisplayText(naturalized.displayText);
      setNarrationText(naturalized.displayText);
      setSpokenText(naturalized.spokenText);
      if (naturalized.cta && ctaMode === "auto") setOutroText(naturalized.cta);
      if (naturalized.recommendedSpeechMode) setSpeechMode(naturalized.recommendedSpeechMode);
      setPerformancePlan({
        tone: naturalized.tone,
        pace: naturalized.pace,
        emotion: naturalized.emotion,
        recommendedVoiceSpeed: naturalized.recommendedVoiceSpeed,
      });
      toast.success("Texto naturalizado. Revise a fala antes de enviar.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível naturalizar o texto.");
    } finally {
      setNaturalizing(false);
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
      if (dirty) {
        const saved = await saveScript(draft);
        updateScript(saved.id, saved);
        setDraft(saved);
        scriptToSend = saved;
      }
      const job = await createHeyGenPreview(scriptToSend.id, {
        avatarId,
        voiceId,
        orientation,
        speechMode,
        captions,
        optimizePronunciation,
        displayText,
        spokenText,
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
                      saving || sending || Boolean(productionBlockedReason) || !selectedAvatarReady || !voiceId || !canSendToProduction
                    }
                  >
                    <History className="mr-1 h-4 w-4" /> Refazer vídeo
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
                      saving ||
                      previewing ||
                      !selectedAvatarReady ||
                      !voiceId ||
                      !approvalReady
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
                      saving || sending || Boolean(productionBlockedReason) || !selectedAvatarReady || !voiceId || !canSendToProduction
                    }
                  >
                    <Film className="mr-1 h-4 w-4" />{" "}
                    Gerar vídeo final
                  </Button>
                }
              />
            </>
          )}
        </>
      }
    >
      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
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
              <Field label="Título">
                <Input value={draft.titulo} onChange={(e) => set("titulo", e.target.value)} />
              </Field>
              <div>
                <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <Label htmlFor="display-text">Fala final</Label>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      Texto que o avatar deve falar. Use a grafia correta para legenda e revisão.
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        const restored = buildNarrationText(
                          draft,
                          durationSeconds === 10 ? "" : outroText,
                        );
                        setNarrationText(restored);
                        setDisplayText(restored);
                        setSpokenText(restored);
                      }}
                    >
                      <RotateCcw className="mr-1 h-4 w-4" />
                      Restaurar
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      disabled={naturalizing || displayText.trim().length < 20}
                      onClick={() => void naturalizarFala()}
                    >
                      <Sparkles className="mr-1 h-4 w-4" />
                      {naturalizing
                        ? "Ajustando..."
                        : narrationWords > maximumWordsForDuration(durationSeconds)
                          ? `Encurtar para ${durationSeconds}s com Claude`
                          : "Melhorar com Claude"}
                    </Button>
                    <Button type="button" size="sm" onClick={salvarRoteiro} disabled={!dirty || saving}>
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
                    setDisplayText(event.target.value);
                    setNarrationText(event.target.value);
                  }}
                  className="leading-6"
                />
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted-foreground">
                  <span>
                    {narrationWords} palavras · ~{estimatedSpeechSeconds}s
                  </span>
                  <span
                    className={cn(
                      "rounded-full px-2.5 py-1 font-medium",
                      blockingQualityIssues.length
                        ? "bg-status-warn/10 text-status-warn-foreground"
                        : qualityIssues.length
                          ? "bg-status-info/10 text-status-info-foreground"
                          : "bg-status-success/10 text-status-success-foreground",
                    )}
                  >
                    {blockingQualityIssues.length
                      ? "Revisão necessária"
                      : qualityIssues.length
                        ? "Aviso de duração"
                        : "✓ Conteúdo seguro"}
                  </span>
                </div>
                {qualityIssues.length > 0 ? (
                  <div
                    className={`mt-2 rounded-md border px-3 py-2 text-[11px] leading-4 ${
                      blockingQualityIssues.length
                        ? "border-status-danger/30 bg-status-danger/10 text-status-danger"
                        : "border-status-info/30 bg-status-info/10 text-status-info"
                    }`}
                  >
                    <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5 font-semibold">
                        <TriangleAlert className="h-3.5 w-3.5" />
                        {blockingQualityIssues.length
                          ? "Revise antes de enviar ao HeyGen"
                          : "Aviso antes do envio"}
                      </div>
                      {qualityIssues.some((issue) => issue.includes("frase final")) ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          className="h-7 px-2 text-[11px]"
                          onClick={() =>
                            setDisplayText(normalizeNarrationOutro(displayText, outroText))
                          }
                        >
                          Corrigir encerramento
                        </Button>
                      ) : null}
                    </div>
                    <ul className="space-y-0.5 pl-5">
                      {qualityIssues.map((issue) => (
                        <li key={issue} className="list-disc">
                          {issue}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
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
                        <Textarea rows={2} value={draft.hook} onChange={(e) => set("hook", e.target.value)} />
                      </Field>
                      <Field label="Dor / conflito">
                        <Textarea rows={2} value={draft.dorConflito} onChange={(e) => set("dorConflito", e.target.value)} />
                      </Field>
                      <Field label="Explicação simples">
                        <Textarea rows={3} value={draft.explicacaoSimples} onChange={(e) => set("explicacaoSimples", e.target.value)} />
                      </Field>
                      <Field label="Virada / provocação">
                        <Textarea rows={3} value={draft.virada} onChange={(e) => set("virada", e.target.value)} />
                      </Field>
                      <Field label="Encerramento">
                        <Textarea rows={2} value={draft.cta} onChange={(e) => set("cta", e.target.value)} />
                      </Field>
                      <Field label="Cuidados médicos">
                        <Textarea rows={2} value={draft.cuidadosMedicos} onChange={(e) => set("cuidadosMedicos", e.target.value)} />
                      </Field>
                      <Field label="Formato">
                        <Input value={draft.formatoSugerido} onChange={(e) => set("formatoSugerido", e.target.value)} />
                      </Field>
                      <Field label="Prioridade">
                        <Select value={draft.prioridade} onValueChange={(v) => set("prioridade", v as Prioridade)}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="alta">Alta</SelectItem>
                            <SelectItem value="media">Media</SelectItem>
                            <SelectItem value="baixa">Baixa</SelectItem>
                          </SelectContent>
                        </Select>
                      </Field>
                      <Field label="Status">
                        <Select value={draft.status} onValueChange={(v) => set("status", v as ScriptStatus)}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
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
                      avatarMode === "single" && "border-primary bg-primary/5 ring-1 ring-primary/30",
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
                    : "O Video Agent organiza o ritmo e as cenas dentro deste tempo aproximado."}
                </p>
                {hasHighCreditConsumption ? <HighCreditConsumptionNotice /> : null}
              </div>
              <Accordion type="single" collapsible>
                <AccordionItem value="advanced-production">
                  <AccordionTrigger>Configurações avançadas</AccordionTrigger>
                  <AccordionContent>
                    <div className="grid gap-3 pt-2 md:grid-cols-2">
                      <Field label="Orientação">
                        <Select value={orientation} onValueChange={(value) => setOrientation(value as "portrait" | "landscape")}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
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
                        <Select value={generationMode} onValueChange={(value) => setGenerationMode(value as "direct" | "video_agent")}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="direct" disabled={selectedAvatar?.supportsDirectAvatar === false}>Direct Avatar</SelectItem>
                            <SelectItem value="video_agent">Video Agent</SelectItem>
                          </SelectContent>
                        </Select>
                      </Field>
                      <Field label="Jeito de falar">
                        <Select value={speechMode} onValueChange={(value) => setSpeechMode(value as "natural" | "fiel" | "direto" | "enfatico")}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="natural">Natural - conversa fluida</SelectItem>
                            <SelectItem value="fiel">Fiel - segue o roteiro</SelectItem>
                            <SelectItem value="direto">Direto - curto e dinâmico</SelectItem>
                            <SelectItem value="enfatico">Enfático - mais presença</SelectItem>
                          </SelectContent>
                        </Select>
                      </Field>
                      <Field label="Encerramento falado">
                        <Select value={ctaMode} onValueChange={(value) => setCtaMode(value as "auto" | "manual" | "none" | "visual")}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="auto">Automático com Claude</SelectItem>
                            <SelectItem value="manual">Manual</SelectItem>
                            <SelectItem value="none">Sem encerramento falado</SelectItem>
                            <SelectItem value="visual">Apenas visual</SelectItem>
                          </SelectContent>
                        </Select>
                      </Field>
                      {generationMode === "video_agent" ? (
                        <Field label="Direção visual HeyGen">
                          <Select value={styleId || "clean"} onValueChange={(value) => setStyleId(value === "clean" ? "" : value)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="clean">Clean - visual clínico</SelectItem>
                              {styles
                                .filter((style) => orientation === "portrait" ? style.aspect_ratio === "9:16" : style.aspect_ratio === "16:9")
                                .map((style) => (
                                  <SelectItem key={style.style_id} value={style.style_id}>
                                    Cinematic - {style.name}
                                  </SelectItem>
                                ))}
                            </SelectContent>
                          </Select>
                        </Field>
                      ) : null}
                    </div>
                    <div className="mt-3 grid gap-3 md:grid-cols-2">
                      <FriendlySwitch icon={<Captions className="h-4 w-4" />} label="Legendas automáticas" description="Texto em português acompanhando a fala" checked={captions} onCheckedChange={setCaptions} />
                      <FriendlySwitch icon={<Sparkles className="h-4 w-4" />} label="Melhorar pronúncia" description="Ajusta siglas, remédios e números para a voz" checked={optimizePronunciation} onCheckedChange={setOptimizePronunciation} />
                    </div>
                    {ctaMode === "manual" && durationSeconds !== 10 ? (
                      <div className="mt-3 rounded-md border border-status-info/30 bg-status-info/5 px-3 py-3">
                        <Label htmlFor="outro-text" className="text-xs font-medium">Frase final do vídeo</Label>
                        <div className="mt-2 flex gap-2">
                          <Input
                            id="outro-text"
                            value={outroText}
                            onChange={(event) => setOutroText(event.target.value)}
                            onBlur={() => setDisplayText((current) => normalizeNarrationOutro(current, outroText))}
                            placeholder="Ex.: Me siga para mais dicas."
                            maxLength={180}
                          />
                          <Button type="button" variant="secondary" onClick={() => setDisplayText((current) => normalizeNarrationOutro(current, outroText))}>
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
                      <Textarea id="spoken-text" rows={5} value={spokenText} onChange={(event) => setSpokenText(event.target.value)} className="mt-2 leading-6" />
                    </div>
                    {performancePlan ? (
                      <div className="mt-3 rounded-md border bg-muted/30 px-3 py-2 text-[11px] leading-4 text-muted-foreground">
                        <span className="font-medium text-foreground">Plano de performance:</span>{" "}
                        {performancePlan.tone} · {performancePlan.pace} · {performancePlan.emotion} · speed {performancePlan.recommendedVoiceSpeed}.
                      </div>
                    ) : null}
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
              <div className="mt-2 flex items-start gap-2 rounded-md border border-status-success/30 bg-status-success/10 px-3 py-2 text-[11px] leading-4 text-muted-foreground">
                <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-status-success" />A fala
                exata será validada antes do envio ao HeyGen. Se houver dose, promessa ou instrução
                prescritiva, o sistema mantém o alerta para revisão, mas não bloqueia o teste.
              </div>
            </div>
          </div>

          <div
            id="roteiro-direcao"
            className="scroll-mt-20 rounded-xl border bg-card p-4 shadow-sm"
          >
            <SectionHeading index={3} title="Direção" description="Prepare cenas, looks e apoios visuais sem expor o contrato técnico por padrão." />
            <div className="mt-4">
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
            </div>
          </div>

          <div id="roteiro-gerar" className="scroll-mt-20 rounded-xl border bg-card p-4 shadow-sm">
            <SectionHeading index={4} title="Gerar" description="Confirme que fala, avatar, direção e compliance estão prontos antes de gastar créditos." />
            <div className="mt-4 space-y-3">
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
              {latestPreview ? (
                <div className="rounded-lg border border-status-info/30 bg-status-info/5 p-3 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="font-semibold">Prévia técnica de avatar e voz</div>
                      <p className="mt-1 text-xs text-muted-foreground">Valida voz e enquadramento; não representa toda a composição final.</p>
                    </div>
                    <Button size="sm" variant="secondary" asChild>
                      <Link to="/producao/$id" params={{ id: latestPreview.id }}>Abrir prévia</Link>
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
                            <div className="text-[10px] font-semibold uppercase tracking-wider text-status-info">Teste {index + 1}</div>
                            <p className="mt-1 line-clamp-3 text-xs text-muted-foreground">{candidate.textoFalado}</p>
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
                      <Preview label="Dor / conflito" text={draft.dorConflito} palavras={palavras} />
                      <Preview label="Explicação" text={draft.explicacaoSimples} palavras={palavras} />
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

function AvatarPicker({
  value,
  avatars,
  loading,
  error,
  onChange,
}: {
  value: string;
  avatars: HeyGenCatalog["avatars"];
  loading: boolean;
  error: string | null;
  onChange: (value: string) => void;
}) {
  const selected = avatars.find((avatar) => avatar.id === value);
  const placeholder = loading
    ? "Carregando avatares..."
    : error
      ? "Nao foi possivel carregar avatares"
      : "Nenhum avatar pronto encontrado";

  if (!selected) {
    return (
      <div className="flex min-h-16 items-center gap-3 rounded-md border bg-muted/30 px-3 text-sm text-muted-foreground">
        <UserRound className="h-7 w-7 shrink-0" />
        <span>{placeholder}</span>
      </div>
    );
  }

  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          type="button"
          data-avatar-id={selected.id}
          className="flex min-h-16 w-full items-center gap-3 rounded-md border bg-background p-2 text-left shadow-sm transition-colors hover:border-primary/40 hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <AvatarThumbnail avatar={selected} className="h-14 w-14" />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-semibold">{selected.name}</span>
            <span className="block truncate text-xs text-muted-foreground">
              {selected.groupName || "Identidade HeyGen"} · {orientationLabel(selected.orientation)}
              {selected.defaultVoiceId ? " · voz padrão" : ""}
            </span>
          </span>
          <span className="shrink-0 px-1 text-xs font-medium text-primary">Trocar avatar</span>
        </button>
      </DialogTrigger>
      <DialogContent className="max-h-[86vh] max-w-4xl overflow-hidden p-0">
        <DialogHeader className="border-b px-5 py-4 pr-12">
          <DialogTitle>Escolha o avatar do vídeo</DialogTitle>
          <DialogDescription>
            A miniatura escolhida corresponde ao avatar enviado para o HeyGen.
          </DialogDescription>
        </DialogHeader>
        <div className="grid max-h-[68vh] auto-rows-max content-start grid-cols-2 gap-3 overflow-y-auto p-4 sm:grid-cols-3 md:grid-cols-4">
          {avatars.map((avatar) => {
            const active = avatar.id === value;
            return (
              <DialogClose asChild key={avatar.id}>
                <button
                  type="button"
                  data-avatar-id={avatar.id}
                  onClick={() => onChange(avatar.id)}
                  aria-pressed={active}
                  className={cn(
                    "overflow-hidden rounded-md border bg-background text-left transition-all hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    active && "border-primary ring-2 ring-primary/20",
                  )}
                >
                  <div className="relative h-28 bg-muted">
                    <AvatarThumbnail
                      avatar={avatar}
                      className="h-full w-full rounded-none border-0"
                      fit="contain"
                    />
                    {active ? (
                      <span className="absolute right-2 top-2 rounded bg-primary px-2 py-1 text-[10px] font-semibold text-primary-foreground">
                        Selecionado
                      </span>
                    ) : null}
                  </div>
                  <span className="block p-2.5">
                    <span className="block truncate text-xs font-semibold">{avatar.name}</span>
                    <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                      {avatar.groupName || "Identidade HeyGen"}
                    </span>
                    <span className="mt-1 block text-[10px] uppercase text-muted-foreground">
                      {[
                        avatar.type || "avatar",
                        orientationLabel(avatar.orientation),
                        avatar.status || "status indefinido",
                        avatar.defaultVoiceId ? "voz padrão" : "",
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </span>
                </button>
              </DialogClose>
            );
          })}
        </div>
      </DialogContent>
    </Dialog>
  );
}

const AVATAR_SET_ROLE_OPTIONS: Array<{ value: AvatarSetRole; label: string }> = [
  { value: "primary", label: "Principal" },
  { value: "front", label: "Frontal" },
  { value: "close", label: "Close" },
  { value: "three_quarter", label: "3/4" },
  { value: "standing", label: "Em pé" },
  { value: "wide", label: "Aberto" },
];

function avatarSetRoleLabel(role: AvatarSetRole) {
  return AVATAR_SET_ROLE_OPTIONS.find((option) => option.value === role)?.label || role;
}

function AvatarSetSelector({
  sets,
  selectedId,
  selected,
  avatars,
  selectedLooks,
  primaryAvatarId,
  loading,
  onSelect,
  onSaved,
  onCreate,
  onEdit,
  onDelete,
  onPrimaryChange,
}: {
  sets: AvatarSet[];
  selectedId: string | null;
  selected: AvatarSet | null;
  avatars: HeyGenCatalog["avatars"];
  selectedLooks: Array<{ look: AvatarSetLook; avatar: HeyGenCatalog["avatars"][number] }>;
  primaryAvatarId: string;
  loading: boolean;
  onSelect: (avatarSet: AvatarSet) => void;
  onSaved: (avatarSet: AvatarSet) => void | Promise<void>;
  onCreate: () => void;
  onEdit: (avatarSet: AvatarSet) => void;
  onDelete: (avatarSet: AvatarSet) => void;
  onPrimaryChange: (avatarId: string) => void;
}) {
  const [draftLooks, setDraftLooks] = useState<AvatarSetLook[]>([]);
  const [choosingRole, setChoosingRole] = useState<AvatarSetRole | null>(null);
  const [savingPack, setSavingPack] = useState(false);
  const [packError, setPackError] = useState<string | null>(null);

  useEffect(() => {
    setDraftLooks(selected?.looks || []);
    setChoosingRole(null);
    setPackError(null);
  }, [selected?.id, selected?.updatedAt]);

  const packDirty = Boolean(selected && JSON.stringify(draftLooks) !== JSON.stringify(selected.looks));

  function updateDraftAvatar(role: AvatarSetRole, avatarId: string) {
    setDraftLooks((current) =>
      current.map((look) => (look.role === role ? { ...look, avatarId } : look)),
    );
    setChoosingRole(null);
    setPackError(null);
  }

  function resetDraftPack() {
    setDraftLooks(selected?.looks || []);
    setChoosingRole(null);
    setPackError(null);
  }

  async function saveDraftPack() {
    if (!selected) return;
    if (draftLooks.length < 2 || new Set(draftLooks.map((look) => look.avatarId)).size < 2) {
      setPackError("Escolha pelo menos dois looks diferentes antes de salvar o pack.");
      return;
    }
    if (new Set(draftLooks.map((look) => look.role)).size !== draftLooks.length) {
      setPackError("Cada posição precisa ter um papel diferente.");
      return;
    }
    setSavingPack(true);
    setPackError(null);
    try {
      const saved = await saveAvatarSet(
        { name: selected.name, voiceId: selected.voiceId, looks: draftLooks },
        selected.id,
      );
      await onSaved(saved);
      setDraftLooks(saved.looks);
      setChoosingRole(null);
    } catch (error) {
      setPackError(error instanceof Error ? error.message : "Nao foi possivel salvar o pack.");
    } finally {
      setSavingPack(false);
    }
  }

  if (loading) {
    return <div className="rounded-lg border bg-muted/25 p-3 text-xs text-muted-foreground">Carregando Avatar Sets...</div>;
  }

  return (
    <div className="space-y-3 rounded-lg border bg-muted/20 p-3">
      <div className="flex flex-wrap items-center gap-2">
        {sets.length ? (
          <Select
            value={selectedId || undefined}
            onValueChange={(value) => {
              const next = sets.find((avatarSet) => avatarSet.id === value);
              if (next) onSelect(next);
            }}
          >
            <SelectTrigger className="min-w-56 flex-1 bg-background">
              <SelectValue placeholder="Selecione um Avatar Set" />
            </SelectTrigger>
            <SelectContent>
              {sets.map((avatarSet) => (
                <SelectItem key={avatarSet.id} value={avatarSet.id}>
                  {avatarSet.name} · {avatarSet.looks.length} looks
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <p className="flex-1 text-xs text-muted-foreground">Nenhum Avatar Set criado ainda.</p>
        )}
        <Button type="button" size="sm" variant="outline" onClick={onCreate}>
          <Plus className="h-3.5 w-3.5" /> Criar conjunto
        </Button>
      </div>

      {selected ? (
        <>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {draftLooks.map((look) => {
              const item =
                avatars.find((avatar) => avatar.id === look.avatarId) ||
                selectedLooks.find((candidate) => candidate.look.avatarId === look.avatarId)?.avatar;
              const primary = look.avatarId === primaryAvatarId;
              return (
                <div
                  key={`${look.role}-${look.avatarId}`}
                  className={cn(
                    "rounded-md border bg-background p-2 transition-colors",
                    primary && "border-primary ring-1 ring-primary/30",
                    choosingRole === look.role && "border-status-info bg-status-info/5",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => setChoosingRole((current) => (current === look.role ? null : look.role))}
                    className="flex w-full items-center gap-2 rounded-md text-left transition-colors hover:bg-muted/40"
                  >
                    {item ? (
                      <AvatarThumbnail avatar={item} className="h-14 w-14" fit="contain" />
                    ) : (
                      <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-md border bg-muted">
                        <UserRound className="h-7 w-7 text-muted-foreground" />
                      </div>
                    )}
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-xs font-semibold">{look.label}</span>
                      <span className="block truncate text-[11px] text-muted-foreground">
                        {avatarSetRoleLabel(look.role)} · {item?.name || "Look não carregado"}
                      </span>
                      <span className="mt-0.5 block text-[10px] font-medium text-status-info">
                        Clique para trocar
                      </span>
                    </span>
                  </button>
                  <div className="mt-2 flex items-center justify-between gap-2">
                    {primary ? (
                      <span className="text-[10px] font-medium text-primary">Posição principal</span>
                    ) : (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="h-7 px-2 text-[11px]"
                        onClick={() => onPrimaryChange(look.avatarId)}
                      >
                        Usar como principal
                      </Button>
                    )}
                    {packDirty ? (
                      <span className="rounded-full bg-status-warning/10 px-2 py-0.5 text-[10px] text-status-warning">
                        Não salvo
                      </span>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
          {choosingRole ? (
            <div className="rounded-lg border border-status-info/30 bg-background p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div>
                  <div className="text-xs font-semibold">Escolha o avatar para {avatarSetRoleLabel(choosingRole)}</div>
                  <p className="text-[11px] text-muted-foreground">Veja as miniaturas e clique no look que quer usar nesta posição.</p>
                </div>
                <Button type="button" size="sm" variant="ghost" onClick={() => setChoosingRole(null)}>
                  Fechar
                </Button>
              </div>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {avatars.map((avatar) => {
                  const active = draftLooks.some(
                    (look) => look.role === choosingRole && look.avatarId === avatar.id,
                  );
                  const alreadyUsed = draftLooks.some(
                    (look) => look.role !== choosingRole && look.avatarId === avatar.id,
                  );
                  return (
                    <button
                      key={avatar.id}
                      type="button"
                      onClick={() => updateDraftAvatar(choosingRole, avatar.id)}
                      className={cn(
                        "flex min-w-0 items-center gap-2 rounded-md border bg-muted/20 p-2 text-left transition-colors hover:border-primary/50 hover:bg-muted/40",
                        active && "border-primary bg-primary/5 ring-1 ring-primary/30",
                        alreadyUsed && !active && "opacity-70",
                      )}
                    >
                      <AvatarThumbnail avatar={avatar} className="h-14 w-14" fit="contain" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-xs font-semibold">{avatar.name}</span>
                        <span className="block truncate text-[10px] text-muted-foreground">
                          {avatar.groupName || "Identidade HeyGen"}
                        </span>
                        {alreadyUsed && !active ? (
                          <span className="mt-0.5 block text-[10px] text-status-warning">
                            Já usado neste pack
                          </span>
                        ) : null}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}
          {packError ? (
            <p className="rounded-md border border-status-danger/30 bg-status-danger/5 px-3 py-2 text-xs text-status-danger">
              {packError}
            </p>
          ) : null}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-[11px] leading-4 text-muted-foreground">
              Clique em um look para trocar por miniatura. Salve o pack para usar as mudanças na produção.
            </p>
            <div className="flex gap-1">
              {packDirty ? (
                <>
                  <Button type="button" size="sm" variant="ghost" onClick={resetDraftPack}>
                    Descartar
                  </Button>
                  <Button type="button" size="sm" onClick={() => void saveDraftPack()} disabled={savingPack}>
                    {savingPack ? "Salvando..." : "Salvar pack"}
                  </Button>
                </>
              ) : null}
              <Button type="button" size="sm" variant="ghost" onClick={() => onEdit(selected)}>
                <Pencil className="h-3.5 w-3.5" /> Editar
              </Button>
              <ConfirmAction
                title="Excluir este Avatar Set?"
                description="O conjunto será removido apenas da configuração local. Os looks da HeyGen não serão apagados."
                confirmLabel="Excluir conjunto"
                destructive
                onConfirm={() => onDelete(selected)}
                trigger={
                  <Button type="button" size="sm" variant="ghost" className="text-status-danger">
                    <Trash2 className="h-3.5 w-3.5" /> Excluir
                  </Button>
                }
              />
            </div>
          </div>
        </>
      ) : (
        <p className="text-xs text-muted-foreground">
          Crie um conjunto com pelo menos duas posições reais para habilitar a direção multicâmera.
        </p>
      )}
    </div>
  );
}

function AvatarSetEditorDialog({
  open,
  initial,
  avatars,
  voices,
  onOpenChange,
  onSaved,
}: {
  open: boolean;
  initial: AvatarSet | null;
  avatars: HeyGenCatalog["avatars"];
  voices: HeyGenCatalog["voices"];
  onOpenChange: (open: boolean) => void;
  onSaved: (avatarSet: AvatarSet) => void | Promise<void>;
}) {
  const [name, setName] = useState("");
  const [voiceId, setVoiceId] = useState("");
  const [looks, setLooks] = useState<AvatarSetLook[]>([]);
  const [choosingLookIndex, setChoosingLookIndex] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    const fallbackLooks: AvatarSetLook[] = avatars.slice(0, 2).map((avatar, index) => ({
      avatarId: avatar.id,
      role: index === 0 ? "close" : "front",
      label: index === 0 ? "Close" : "Frontal",
    }));
    setName(initial?.name || "");
    setVoiceId(initial?.voiceId || avatars[0]?.defaultVoiceId || voices[0]?.id || "");
    setLooks(initial?.looks?.length ? initial.looks : fallbackLooks);
    setChoosingLookIndex(null);
    setError(null);
  }, [avatars, initial, open, voices]);

  function updateLook(index: number, patch: Partial<AvatarSetLook>) {
    setLooks((current) => current.map((look, lookIndex) => (lookIndex === index ? { ...look, ...patch } : look)));
  }

  function addLook() {
    const nextAvatar = avatars.find((avatar) => !looks.some((look) => look.avatarId === avatar.id));
    const nextRole = AVATAR_SET_ROLE_OPTIONS.find((option) => !looks.some((look) => look.role === option.value));
    if (!nextAvatar || !nextRole) {
      setError("Não há outro look ou role disponível no catálogo atual.");
      return;
    }
    setLooks((current) => [...current, { avatarId: nextAvatar.id, role: nextRole.value, label: nextRole.label }]);
    setError(null);
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (looks.length < 2 || new Set(looks.map((look) => look.avatarId)).size < 2) {
      setError("Escolha pelo menos dois looks diferentes para criar duas posições.");
      return;
    }
    if (new Set(looks.map((look) => look.role)).size !== looks.length) {
      setError("Cada posição precisa ter um role diferente.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await saveAvatarSet({ name: name.trim(), voiceId, looks }, initial?.id);
      await onSaved(saved);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Nao foi possivel salvar o Avatar Set.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{initial ? "Editar Avatar Set" : "Criar Avatar Set"}</DialogTitle>
          <DialogDescription>
            Cadastre looks reais da mesma pessoa para alternar entre duas posições com cortes entre cenas.
          </DialogDescription>
        </DialogHeader>
        <form className="space-y-4" onSubmit={submit}>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Nome do conjunto">
              <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Guilherme — Casual Azul" required />
            </Field>
            <Field label="Voz">
              <Select value={voiceId} onValueChange={setVoiceId}>
                <SelectTrigger><SelectValue placeholder="Selecione uma voz" /></SelectTrigger>
                <SelectContent>
                  {voices.map((voice) => <SelectItem key={voice.id} value={voice.id}>{voice.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div>
                <Label className="text-xs">Looks e posições</Label>
                <p className="text-[11px] text-muted-foreground">Use pelo menos dois looks diferentes.</p>
              </div>
              <Button type="button" size="sm" variant="outline" onClick={addLook} disabled={looks.length >= 6}>
                <Plus className="h-3.5 w-3.5" /> Adicionar look
              </Button>
            </div>
            <div className="space-y-2">
              {looks.map((look, index) => {
                const selectedAvatar = avatars.find((avatar) => avatar.id === look.avatarId);
                return (
                  <div
                    key={`${index}-${look.avatarId}`}
                    className="grid gap-2 rounded-lg border bg-muted/20 p-2 sm:grid-cols-[minmax(0,1.45fr)_0.8fr_1fr_auto]"
                  >
                    <div className="flex min-w-0 items-center gap-2 rounded-md border bg-background p-1.5">
                      {selectedAvatar ? (
                        <AvatarThumbnail
                          avatar={selectedAvatar}
                          className="h-14 w-14"
                          fit="contain"
                        />
                      ) : (
                        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-md border bg-muted">
                          <UserRound className="h-6 w-6 text-muted-foreground" />
                        </div>
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium">
                          {selectedAvatar?.name || "Look não encontrado"}
                        </div>
                        <div className="truncate text-[11px] text-muted-foreground">
                          {selectedAvatar?.groupName || "Identidade HeyGen"}
                        </div>
                      </div>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="shrink-0"
                        onClick={() =>
                          setChoosingLookIndex((current) => (current === index ? null : index))
                        }
                      >
                        Escolher
                      </Button>
                    </div>
                    <Select value={look.role} onValueChange={(value) => updateLook(index, { role: value as AvatarSetRole, label: avatarSetRoleLabel(value as AvatarSetRole) })}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {AVATAR_SET_ROLE_OPTIONS.map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                    <Input value={look.label} onChange={(event) => updateLook(index, { label: event.target.value })} placeholder="Rótulo" />
                    <Button type="button" size="icon" variant="ghost" onClick={() => setLooks((current) => current.filter((_, lookIndex) => lookIndex !== index))} disabled={looks.length <= 2} aria-label="Remover look">
                      <Trash2 className="h-4 w-4 text-status-danger" />
                    </Button>
                    {choosingLookIndex === index ? (
                      <div className="grid gap-2 rounded-md border bg-background p-2 sm:col-span-4 sm:grid-cols-2 lg:grid-cols-3">
                        {avatars.map((avatar) => {
                          const active = avatar.id === look.avatarId;
                          const alreadyUsed = looks.some(
                            (candidate, lookIndex) =>
                              lookIndex !== index && candidate.avatarId === avatar.id,
                          );
                          return (
                            <button
                              key={avatar.id}
                              type="button"
                              onClick={() => {
                                updateLook(index, { avatarId: avatar.id });
                                setChoosingLookIndex(null);
                              }}
                              className={cn(
                                "flex min-w-0 items-center gap-2 rounded-md border p-2 text-left transition-colors hover:border-primary/50 hover:bg-muted/30",
                                active && "border-primary bg-primary/5 ring-1 ring-primary/30",
                                alreadyUsed && !active && "opacity-70",
                              )}
                            >
                              <AvatarThumbnail avatar={avatar} className="h-12 w-12" fit="contain" />
                              <span className="min-w-0 flex-1">
                                <span className="block truncate text-xs font-semibold">
                                  {avatar.name}
                                </span>
                                <span className="block truncate text-[10px] text-muted-foreground">
                                  {avatar.groupName || "Identidade HeyGen"}
                                </span>
                                {alreadyUsed && !active ? (
                                  <span className="mt-0.5 block text-[10px] text-status-warning">
                                    Já usado em outro look
                                  </span>
                                ) : null}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>
          {error ? <p className="rounded-md border border-status-danger/30 bg-status-danger/5 px-3 py-2 text-xs text-status-danger">{error}</p> : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancelar</Button>
            <Button type="submit" disabled={saving || avatars.length < 2 || looks.length < 2}>
              {saving ? "Salvando..." : "Salvar Avatar Set"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

type EditableScene = {
  id: string;
  text: string;
  lookRole: AvatarSetRole;
  estimatedStart: number;
  estimatedEnd: number;
};

function resolveSceneRole(
  requestedRole: AvatarSetRole,
  index: number,
  availableRoles: AvatarSetRole[],
): AvatarSetRole {
  return (
    (availableRoles.includes(requestedRole)
      ? requestedRole
      : availableRoles[index % Math.max(availableRoles.length, 1)]) || "primary"
  );
}

function defaultSceneDraft(text: string, roles: AvatarSetRole[]): EditableScene[] {
  const clean = text.replace(/\s+/g, " ").trim();
  const sentences = clean.match(/[^.!?…]+[.!?…]*/g)?.map((sentence) => sentence.trim()).filter(Boolean) || [];
  if (roles.length < 2 || !clean) {
    return [{ id: "scene-1", text: clean, lookRole: roles[0] || "primary", estimatedStart: 0, estimatedEnd: 0 }];
  }
  const splitAt = Math.max(1, Math.ceil(sentences.length / 2));
  const first = sentences.slice(0, splitAt).join(" ").trim();
  const second = sentences.slice(splitAt).join(" ").trim() || clean.slice(Math.ceil(clean.length / 2));
  return [
    { id: "scene-1", text: first, lookRole: roles[0], estimatedStart: 0, estimatedEnd: 0 },
    { id: "scene-2", text: second, lookRole: roles[1], estimatedStart: 0, estimatedEnd: 0 },
  ];
}

function coerceToTwoSceneDraft(
  suggestions: Array<{ text: string; lookRole: AvatarSetRole }>,
  roles: AvatarSetRole[],
  fallbackText: string,
): EditableScene[] {
  const source = suggestions.length
    ? suggestions
    : defaultSceneDraft(fallbackText, roles).map((scene) => ({
        text: scene.text,
        lookRole: scene.lookRole,
      }));
  const firstText = source[0]?.text || "";
  const secondText = source.slice(1).map((scene) => scene.text).join(" ").trim();
  const fallback = defaultSceneDraft(
    source.map((scene) => scene.text).join(" ").trim() || fallbackText,
    roles,
  );
  return [
    {
      id: "scene-1",
      text: firstText || fallback[0]?.text || "",
      lookRole: resolveSceneRole(source[0]?.lookRole || roles[0] || "primary", 0, roles),
      estimatedStart: 0,
      estimatedEnd: 0,
    },
    {
      id: "scene-2",
      text: secondText || fallback[1]?.text || "",
      lookRole: resolveSceneRole(source[1]?.lookRole || roles[1] || roles[0] || "primary", 1, roles),
      estimatedStart: 0,
      estimatedEnd: 0,
    },
  ];
}

function ScenePlanEditor({
  scriptId,
  loading,
  plan,
  fallbackText,
  displayText,
  spokenText,
  durationSeconds,
  performancePlan,
  availableRoles,
  transitionSlideGenerating = false,
  onSaved,
  onGenerateTransitionSlides,
}: {
  scriptId: string;
  loading: boolean;
  plan: ScenePlan | null;
  fallbackText: string;
  displayText: string;
  spokenText: string;
  durationSeconds: 10 | 15 | 30 | 45 | 60;
  performancePlan: { tone: string; pace: string; emotion: string; recommendedVoiceSpeed: number } | null;
  availableRoles: AvatarSetRole[];
  transitionSlideGenerating?: boolean;
  onSaved: (plan: ScenePlan) => void;
  onGenerateTransitionSlides?: (plan: ScenePlan) => Promise<void>;
}) {
  const [scenes, setScenes] = useState<EditableScene[]>([]);
  const [saving, setSaving] = useState(false);
  const [directing, setDirecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [directionNotice, setDirectionNotice] = useState<string | null>(null);

  useEffect(() => {
    if (loading) return;
    setScenes(
      plan?.scenes.map((scene, index) => ({
        id: scene.id,
        text: scene.text,
        lookRole: resolveSceneRole(scene.lookRole, index, availableRoles),
        estimatedStart: scene.estimatedStart,
        estimatedEnd: scene.estimatedEnd,
      })) || defaultSceneDraft(fallbackText, availableRoles),
    );
    setError(null);
  }, [availableRoles, loading, plan?.updatedAt]);

  function updateScene(index: number, patch: Partial<EditableScene>) {
    setScenes((current) => current.map((scene, sceneIndex) => (sceneIndex === index ? { ...scene, ...patch } : scene)));
  }

  function addScene() {
    const role = availableRoles[scenes.length % Math.max(availableRoles.length, 1)] || "primary";
    setScenes((current) => [
      ...current,
      {
        id: `scene-${current.length + 1}`,
        text: "",
        lookRole: role,
        estimatedStart: 0,
        estimatedEnd: 0,
      },
    ]);
  }

  function useTwoScenes() {
    const mergedText = scenes.map((scene) => scene.text).join(" ").replace(/\s+/g, " ").trim();
    setScenes(defaultSceneDraft(mergedText || fallbackText, availableRoles));
    setDirectionNotice("Plano reorganizado em 2 cenas. Revise os textos e salve.");
    setError(null);
  }

  async function requestDirection() {
    setDirecting(true);
    setError(null);
    setDirectionNotice(null);
    try {
      const result = await generateSceneDirection(scriptId, {
        displayText,
        spokenText,
        durationSeconds,
        tone: performancePlan?.tone,
        pace: performancePlan?.pace,
        emotion: performancePlan?.emotion,
      });
      const nextScenes =
        availableRoles.length >= 2
          ? coerceToTwoSceneDraft(result.scenes, availableRoles, displayText || fallbackText)
          : result.scenes.map((scene, index) => ({
              id: `scene-${index + 1}`,
              text: scene.text,
              lookRole: resolveSceneRole(scene.lookRole, index, availableRoles),
              estimatedStart: 0,
              estimatedEnd: 0,
            }));
      setScenes(nextScenes);
      setDirectionNotice(
        availableRoles.length >= 2
          ? "Claude sugeriu uma divisão e o app manteve em 2 cenas, para preservar um único corte de look."
          : "Claude sugeriu uma divisão. Revise e salve o plano quando estiver de acordo.",
      );
    } catch (directionError) {
      setError(directionError instanceof Error ? directionError.message : "Nao foi possivel gerar direção com Claude.");
    } finally {
      setDirecting(false);
    }
  }

  function validateScenes() {
    if (scenes.some((scene) => !scene.text.trim())) {
      return "Cada cena precisa ter um texto falado.";
    }
    if (availableRoles.length >= 2 && new Set(scenes.map((scene) => scene.lookRole)).size < 2) {
      return "Use pelo menos duas posições diferentes quando o Avatar Set estiver ativo.";
    }
    return null;
  }

  async function persistScenes(showToast = true) {
    const validationError = validateScenes();
    if (validationError) {
      setError(validationError);
      return null;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await saveScenePlan(scriptId, scenes);
      onSaved(saved);
      if (showToast) toast.success("Scene Plan salvo.");
      return saved;
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Nao foi possivel salvar o Scene Plan.");
      return null;
    } finally {
      setSaving(false);
    }
  }

  async function save() {
    await persistScenes(true);
  }

  async function generateTransitionSlides() {
    if (!onGenerateTransitionSlides) return;
    const saved = await persistScenes(false);
    if (!saved) return;
    setDirectionNotice(null);
    setError(null);
    try {
      await onGenerateTransitionSlides(saved);
      setDirectionNotice(
        saved.scenes.length > 2
          ? "Claude gerou os slides de transição. Revise a Direção visual dos apoios abaixo."
          : "Claude gerou o slide de transição. Revise a Direção visual dos apoios abaixo.",
      );
    } catch {
      setError("Nao foi possivel gerar o slide de transição com Claude.");
    }
  }

  return (
    <div className="space-y-3 rounded-lg border bg-muted/20 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h4 className="text-xs font-semibold">Plano de cenas</h4>
          <p className="mt-0.5 text-[11px] leading-4 text-muted-foreground">
            Cada cena usa uma única posição. A troca acontece somente com corte entre cenas.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="secondary" onClick={() => void requestDirection()} disabled={loading || directing}>
            <Sparkles className="h-3.5 w-3.5" /> {directing ? "Claude pensando..." : "Gerar 2 cenas com Claude"}
          </Button>
          {scenes.length !== 2 && availableRoles.length >= 2 ? (
            <Button type="button" size="sm" variant="outline" onClick={useTwoScenes}>
              Usar 2 cenas
            </Button>
          ) : null}
          <Button type="button" size="sm" variant="outline" onClick={addScene}>
            <Plus className="h-3.5 w-3.5" /> Adicionar cena
          </Button>
        </div>
      </div>
      <p className="text-[11px] text-muted-foreground">O botão de direção usa tokens Claude e não salva alterações automaticamente.</p>
      {loading ? (
        <p className="text-xs text-muted-foreground">Carregando Scene Plan...</p>
      ) : (
        <div className="space-y-2">
          {scenes.map((scene, index) => (
            <div key={scene.id} className="space-y-2">
              <div className="rounded-lg border bg-background p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold">Cena {index + 1}</span>
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    onClick={() => setScenes((current) => current.filter((_, sceneIndex) => sceneIndex !== index))}
                    disabled={scenes.length <= 1}
                    aria-label={`Remover cena ${index + 1}`}
                  >
                    <Trash2 className="h-4 w-4 text-status-danger" />
                  </Button>
                </div>
                <div className="grid gap-2 md:grid-cols-[1fr_180px]">
                  <Textarea
                    value={scene.text}
                    onChange={(event) => updateScene(index, { text: event.target.value })}
                    rows={3}
                    placeholder="Texto falado nesta cena"
                  />
                  <div className="space-y-2">
                    <Field label="Posição">
                      <Select
                        value={scene.lookRole}
                        onValueChange={(value) => updateScene(index, { lookRole: value as AvatarSetRole })}
                      >
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {availableRoles.map((role) => (
                            <SelectItem key={role} value={role}>{avatarSetRoleLabel(role)}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </Field>
                    <div className="grid grid-cols-2 gap-2">
                      <Input
                        type="number"
                        min={0}
                        step={0.1}
                        value={scene.estimatedStart}
                        onChange={(event) => updateScene(index, { estimatedStart: Number(event.target.value) || 0 })}
                        aria-label="Início estimado"
                        placeholder="Início"
                      />
                      <Input
                        type="number"
                        min={0}
                        step={0.1}
                        value={scene.estimatedEnd}
                        onChange={(event) => updateScene(index, { estimatedEnd: Number(event.target.value) || 0 })}
                        aria-label="Fim estimado"
                        placeholder="Fim"
                      />
                    </div>
                  </div>
                </div>
              </div>
              {index < scenes.length - 1 ? (
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-status-info/30 bg-status-info/5 px-3 py-2">
                  <div>
                    <div className="text-xs font-semibold text-status-info">
                      Transição Cena {index + 1} → Cena {index + 2}
                    </div>
                    <p className="mt-0.5 text-[11px] leading-4 text-muted-foreground">
                      Crie um slide visual para entrar durante a fala antes do próximo look.
                    </p>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    onClick={() => void generateTransitionSlides()}
                    disabled={saving || transitionSlideGenerating || !onGenerateTransitionSlides}
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    {transitionSlideGenerating ? "Claude gerando..." : "Gerar slide de transição"}
                  </Button>
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}
      {directionNotice ? <p className="rounded-md border border-status-info/30 bg-status-info/5 px-3 py-2 text-xs text-status-info">{directionNotice}</p> : null}
      {error ? <p className="rounded-md border border-status-danger/30 bg-status-danger/5 px-3 py-2 text-xs text-status-danger">{error}</p> : null}
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] text-muted-foreground">A direção automática com Claude será adicionada em um próximo slice.</p>
        <Button type="button" size="sm" onClick={() => void save()} disabled={loading || saving || scenes.length === 0}>
          {saving ? "Salvando..." : "Salvar plano de cenas"}
        </Button>
      </div>
    </div>
  );
}

const VIDEO_VISUAL_TYPE_OPTIONS: Array<{ value: VideoVisualType; label: string }> = [
  { value: "none", label: "Nenhum visual" },
  { value: "full_slide", label: "Slide completo" },
  { value: "overlay", label: "Overlay" },
  { value: "statistic", label: "Estatística" },
  { value: "comparison", label: "Comparação" },
  { value: "quote", label: "Citação" },
];

const VIDEO_VISUAL_LAYOUT_OPTIONS: Array<{ value: VideoVisualLayout; label: string }> = [
  { value: "hero_photo", label: "Hero com foto" },
  { value: "photo_split", label: "Foto dividida" },
  { value: "big_statement", label: "Big statement" },
  { value: "question", label: "Pergunta" },
  { value: "myth_fact", label: "Mito e fato" },
  { value: "number_stat", label: "Número" },
  { value: "three_points", label: "Três pontos" },
  { value: "explainer", label: "Explicador" },
  { value: "doctor_quote", label: "Citação médica" },
  { value: "photo_overlay", label: "Foto com overlay" },
  { value: "do_dont", label: "Faça / não faça" },
  { value: "cta_photo", label: "Encerramento com foto" },
];

function VisualPlanDirector({
  scriptId,
  scenePlan,
  visualPlan,
  loading,
  displayText,
  spokenText,
  durationSeconds,
  performancePlan,
  onSaved,
  videoSlideRender,
  videoSlideRenderLoading,
  onRendered,
}: {
  scriptId: string;
  scenePlan: ScenePlan | null;
  visualPlan: VisualPlan | null;
  loading: boolean;
  displayText: string;
  spokenText: string;
  durationSeconds: 10 | 15 | 30 | 45 | 60;
  performancePlan: { tone: string; pace: string; emotion: string; recommendedVoiceSpeed: number } | null;
  onSaved: (plan: VisualPlan) => void;
  videoSlideRender: VideoSlideRender | null;
  videoSlideRenderLoading: boolean;
  onRendered: (render: VideoSlideRender) => void;
}) {
  const [directing, setDirecting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [draftPlan, setDraftPlan] = useState<VisualPlan | null>(visualPlan);
  const [error, setError] = useState<string | null>(null);
  const requiredVisualCount = scenePlan ? Math.max(0, scenePlan.scenes.length - 1) : 0;

  useEffect(() => {
    setDraftPlan(visualPlan);
  }, [visualPlan?.updatedAt]);

  async function requestVisualDirection() {
    if (!scenePlan) {
      setError("Salve o Scene Plan antes de pedir direção visual.");
      return;
    }
    setDirecting(true);
    setError(null);
    try {
      const result = await generateVisualDirection(scriptId, {
        displayText,
        spokenText,
        durationSeconds,
        tone: performancePlan?.tone,
        pace: performancePlan?.pace,
        emotion: performancePlan?.emotion,
      });
      onSaved(result.visualPlan);
      setDraftPlan(result.visualPlan);
      toast.success("Direção visual gerada pelo Claude.");
    } catch (visualError) {
      setError(visualError instanceof Error ? visualError.message : "Nao foi possivel gerar direção visual.");
    } finally {
      setDirecting(false);
    }
  }

  function updateVisual(sceneId: string, patch: Partial<VisualPlan["scenes"][number]["visual"]>) {
    setDraftPlan((current) =>
      current
        ? {
            ...current,
            scenes: current.scenes.map((scene) =>
              scene.sceneId === sceneId ? { ...scene, visual: { ...scene.visual, ...patch } } : scene,
            ),
          }
        : current,
    );
  }

  async function save() {
    if (!draftPlan) return;
    setSaving(true);
    setError(null);
    try {
      const saved = await saveVisualPlan(scriptId, draftPlan);
      setDraftPlan(saved);
      onSaved(saved);
      toast.success("Direção visual salva.");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Nao foi possivel salvar a direção visual.");
    } finally {
      setSaving(false);
    }
  }

  async function renderPreviews(): Promise<VideoSlideRender | null> {
    if (!draftPlan) {
      setError("Salve ou gere a direção visual antes de renderizar os previews.");
      return null;
    }
    setRendering(true);
    setError(null);
    try {
      const savedPlan = await saveVisualPlan(scriptId, draftPlan);
      setDraftPlan(savedPlan);
      onSaved(savedPlan);
      const rendered = await renderVideoSlides(scriptId);
      onRendered(rendered);
      toast.success(`${rendered.renderedCount} preview(s) 1080×1920 renderizado(s).`);
      return rendered;
    } catch (renderError) {
      setError(renderError instanceof Error ? renderError.message : "Nao foi possivel renderizar os previews.");
      return null;
    } finally {
      setRendering(false);
    }
  }

  async function renderAndOpenSlide(sceneId: string) {
    const existing = videoSlideRender?.assets.find((asset) => asset.sceneId === sceneId && asset.url);
    if (existing?.url) {
      window.open(existing.url, "_blank", "noopener,noreferrer");
      return;
    }
    const rendered = await renderPreviews();
    const asset = rendered?.assets.find((candidate) => candidate.sceneId === sceneId && candidate.url);
    if (asset?.url) {
      window.open(asset.url, "_blank", "noopener,noreferrer");
    }
  }

  return (
    <div className="mt-3 space-y-3 rounded-lg border bg-muted/20 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h4 className="text-xs font-semibold">Direção visual dos apoios</h4>
          <p className="mt-0.5 text-[11px] leading-4 text-muted-foreground">
            Claude cria {requiredVisualCount} apoio(s) para entrar durante a fala antes dos cortes de look.
          </p>
        </div>
        <Button type="button" size="sm" variant="secondary" onClick={() => void requestVisualDirection()} disabled={loading || directing || !scenePlan}>
          <Sparkles className="h-3.5 w-3.5" /> {directing ? "Claude pensando..." : "Gerar direção visual com Claude"}
        </Button>
      </div>
      <p className="text-[11px] text-muted-foreground">Esta ação usa tokens Claude e salva uma direção estruturada, sem gerar imagens ou vídeo.</p>
      {loading ? <p className="text-xs text-muted-foreground">Carregando direção visual...</p> : null}
      {draftPlan ? (
        <div className="space-y-2">
          {draftPlan.scenes.map((scene, index) => {
            const requiresVisual = index < requiredVisualCount;
            const closesOnAvatar = requiredVisualCount > 0 && index >= requiredVisualCount;
            const previewAsset = videoSlideRender?.assets.find(
              (asset) => asset.sceneId === scene.sceneId && asset.url,
            );
            return (
            <div key={scene.sceneId} className="rounded-md border bg-background p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <span className="text-xs font-semibold">
                    {closesOnAvatar
                      ? `Cena ${index + 1}`
                      : `Transição Cena ${index + 1} → Cena ${index + 2}`}
                  </span>
                  {!closesOnAvatar ? (
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      Entra durante a fala antes do próximo look.
                    </p>
                  ) : null}
                </div>
                <div className="flex items-center gap-2">
                  {!closesOnAvatar && scene.visual.type !== "none" ? (
                    previewAsset?.url ? (
                      <Button type="button" size="sm" variant="outline" asChild>
                        <a href={previewAsset.url} target="_blank" rel="noreferrer">
                          <Film className="h-3.5 w-3.5" /> Ver slide
                        </a>
                      </Button>
                    ) : (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => void renderAndOpenSlide(scene.sceneId)}
                        disabled={rendering || loading}
                      >
                        <Film className="h-3.5 w-3.5" />
                        {rendering ? "Renderizando..." : "Renderizar e ver slide"}
                      </Button>
                    )
                  ) : null}
                  <span className="rounded-full bg-muted px-2 py-1 text-[10px] font-medium uppercase">
                    {closesOnAvatar ? "Fechamento no avatar" : scene.visual.type === "none" ? "Apoio obrigatório" : "Slide de transição"}
                  </span>
                </div>
              </div>
              <div className="grid gap-2 md:grid-cols-[180px_1fr]">
                <div className="space-y-2">
                  <Field label="Tipo">
                    <Select
                      value={scene.visual.type}
                      disabled={closesOnAvatar}
                      onValueChange={(value) =>
                        updateVisual(scene.sceneId, {
                          type: value as VideoVisualType,
                          layout: value === "none" ? "" : scene.visual.layout || "big_statement",
                          headline: value === "none" ? "" : scene.visual.headline,
                          body: value === "none" ? "" : scene.visual.body,
                        })
                      }
                    >
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {VIDEO_VISUAL_TYPE_OPTIONS.filter((option) => !requiresVisual || option.value !== "none").map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </Field>
                  {scene.visual.type !== "none" && !closesOnAvatar ? (
                    <Field label="Layout">
                      <Select
                        value={scene.visual.layout || "big_statement"}
                        onValueChange={(value) => updateVisual(scene.sceneId, { layout: value as VideoVisualLayout })}
                      >
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {VIDEO_VISUAL_LAYOUT_OPTIONS.map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </Field>
                  ) : null}
                </div>
                {closesOnAvatar ? (
                  <p className="flex items-center text-xs text-muted-foreground">A última cena fica limpa para o próximo look fechar a fala.</p>
                ) : scene.visual.type === "none" ? (
                  <p className="flex items-center text-xs text-muted-foreground">Esta cena precisa de um apoio visual antes do próximo corte de look.</p>
                ) : (
                  <div className="space-y-2">
                    <Input value={scene.visual.headline} onChange={(event) => updateVisual(scene.sceneId, { headline: event.target.value })} placeholder="Headline curta" />
                    <Textarea value={scene.visual.body} onChange={(event) => updateVisual(scene.sceneId, { body: event.target.value })} rows={2} placeholder="Body opcional — complemente a fala" />
                    <Input value={scene.visual.purpose} onChange={(event) => updateVisual(scene.sceneId, { purpose: event.target.value })} placeholder="Objetivo editorial" />
                  </div>
                )}
              </div>
            </div>
            );
          })}
        </div>
      ) : null}
      {draftPlan ? <div className="flex justify-end"><Button type="button" size="sm" onClick={() => void save()} disabled={saving || loading}>{saving ? "Salvando..." : "Salvar direção visual"}</Button></div> : null}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3">
        <div>
          <p className="text-xs font-semibold">Preview dos apoios</p>
          <p className="text-[11px] text-muted-foreground">Renderer local determinístico, sem Claude, HeyGen ou MP4.</p>
        </div>
        <Button type="button" size="sm" variant="outline" onClick={() => void renderPreviews()} disabled={rendering || loading || !draftPlan}>
          <Film className="h-3.5 w-3.5" /> {rendering ? "Renderizando..." : "Renderizar previews 1080×1920"}
        </Button>
      </div>
      {videoSlideRenderLoading ? <p className="text-xs text-muted-foreground">Carregando previews...</p> : null}
      {videoSlideRender && videoSlideRender.assets.some((asset) => asset.url) ? (
        <div className="grid gap-2 sm:grid-cols-3">
          {videoSlideRender.assets.filter((asset) => asset.url).map((asset) => (
            <a key={asset.sceneId} href={asset.url} target="_blank" rel="noreferrer" className="group overflow-hidden rounded-md border bg-background">
              <img src={asset.url} alt={`Preview da cena ${asset.index}`} className="aspect-[9/16] w-full object-cover transition group-hover:opacity-80" />
              <div className="p-2 text-[10px] text-muted-foreground">Cena {asset.index} · {asset.layout || asset.type}</div>
            </a>
          ))}
        </div>
      ) : null}
      {error ? <p className="rounded-md border border-status-danger/30 bg-status-danger/5 px-3 py-2 text-xs text-status-danger">{error}</p> : null}
    </div>
  );
}

function AvatarThumbnail({
  avatar,
  className,
  fit = "cover",
}: {
  avatar: HeyGenCatalog["avatars"][number];
  className?: string;
  fit?: "cover" | "contain";
}) {
  return (
    <span className={cn("block shrink-0 overflow-hidden rounded-md border bg-muted", className)}>
      {avatar.previewImageUrl ? (
        <img
          src={avatar.previewImageUrl}
          alt={`Miniatura de ${avatar.name}`}
          className={cn("h-full w-full", fit === "contain" ? "object-contain" : "object-cover")}
        />
      ) : (
        <UserRound className="m-auto h-full w-1/2 text-muted-foreground" />
      )}
    </span>
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
            Nenhum job foi criado. Antes de qualquer geração paga, confira cenas, looks, voz e duração.
          </p>
        </div>
      </div>
      {loading ? <p className="text-xs text-muted-foreground">Montando estimativa...</p> : null}
      {plan ? (
        <>
          <div className="flex flex-wrap gap-2 text-[11px]">
            <span className="rounded-full bg-background px-2 py-1">{plan.sceneCount} cenas</span>
            <span className="rounded-full bg-background px-2 py-1">{plan.estimatedCalls} chamadas HeyGen estimadas</span>
            <span className="rounded-full bg-background px-2 py-1">{durationSeconds}s selecionados</span>
            <span className="rounded-full bg-background px-2 py-1">{plan.requests[0]?.voiceId || "voz não definida"}</span>
          </div>
          <div className="space-y-1">
            {plan.requests.map((request) => (
              <div key={request.sceneId} className="grid gap-1 rounded-md border bg-background px-2 py-1.5 text-[11px] md:grid-cols-[80px_1fr_1.5fr]">
                <span className="font-semibold">Cena {request.order}</span>
                <span>{avatarMode === "set" ? `Look ${request.avatarId}` : "Avatar principal"}</span>
                <span className="truncate text-muted-foreground">{request.spokenText}</span>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-status-warning">{plan.warning}</p>
        </>
      ) : (
        <p className="text-[11px] text-muted-foreground">Salve um Scene Plan para visualizar a estimativa por cena.</p>
      )}
    </div>
  );
}

function orientationLabel(orientation: "portrait" | "landscape") {
  return orientation === "portrait" ? "Vertical" : "Horizontal";
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      {children}
    </div>
  );
}

function HighCreditConsumptionNotice({ compact = false }: { compact?: boolean }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex items-start gap-2 rounded-lg border border-status-warn/60 bg-status-warn/15 text-status-warn-foreground",
        compact ? "px-3 py-2" : "px-3 py-2.5",
      )}
    >
      <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0">
        <p className="text-xs font-semibold">Maior consumo de créditos</p>
        <p className="mt-0.5 text-[11px] leading-4">
          Vídeos de 45 segundos ou mais podem consumir mais créditos/tokens do HeyGen. Verifique o
          saldo antes de gerar.
        </p>
      </div>
    </div>
  );
}

function FriendlySwitch({
  icon,
  label,
  description,
  checked,
  onCheckedChange,
}: {
  icon: React.ReactNode;
  label: string;
  description: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex min-h-14 items-center gap-3 rounded-lg border bg-muted/25 px-3 py-2">
      <div className="text-muted-foreground">{icon}</div>
      <div className="min-w-0 flex-1">
        <Label className="text-xs font-medium">{label}</Label>
        <p className="text-[11px] leading-4 text-muted-foreground">{description}</p>
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} aria-label={label} />
    </div>
  );
}

function ProductionGateChecklist({
  items,
  blockedReason,
  latestJobId,
  dirty,
  narrationWords,
  estimatedSpeechSeconds,
  onOpenLatest,
  onSend,
}: {
  items: Array<{ label: string; ready: boolean; detail: string }>;
  blockedReason: string | null;
  latestJobId?: string;
  dirty: boolean;
  narrationWords: number;
  estimatedSpeechSeconds: number;
  onOpenLatest?: () => void;
  onSend: () => void;
}) {
  const nextPending = items.find((item) => !item.ready);
  const ready = !nextPending && !blockedReason;
  const nextIssue = blockedReason || nextPending?.detail || null;
  return (
    <div
      className={cn(
        "rounded-xl border p-4 shadow-sm",
        ready ? "border-status-success/30 bg-status-success/5" : "border-status-warning/30 bg-status-warning/10",
      )}
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-status-info">
            {ready ? (
              <CheckCircle2 className="h-3.5 w-3.5 text-status-success" />
            ) : (
              <TriangleAlert className="h-3.5 w-3.5 text-status-warning" />
            )}
            Checklist final
          </div>
          <h2 className="mt-1 font-display text-sm font-semibold">
            {ready ? "Tudo certo para enviar ao HeyGen" : "Falta resolver antes de gerar"}
          </h2>
          <p className="mt-0.5 max-w-3xl text-xs leading-5 text-muted-foreground">
            O botão só libera quando todos os itens abaixo estiverem validados.
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          {latestJobId && onOpenLatest ? (
            <Button type="button" size="sm" variant="secondary" onClick={onOpenLatest}>
              Ver vídeo
            </Button>
          ) : null}
          <Button type="button" size="sm" onClick={onSend} disabled={!ready}>
            Enviar para produção
            <ArrowRight className="ml-1 h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="mt-3 grid gap-2 md:grid-cols-2">
        {items.map((item) => (
          <div key={item.label} className="flex items-start gap-2 rounded-lg border bg-background/70 px-3 py-2">
            {item.ready ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-status-success" />
            ) : (
              <Circle className="mt-0.5 h-4 w-4 shrink-0 text-status-warning" />
            )}
            <div className="min-w-0">
              <div className="text-xs font-semibold">{item.label}</div>
              <div className="mt-0.5 text-[11px] leading-4 text-muted-foreground">{item.detail}</div>
            </div>
          </div>
        ))}
      </div>

      {nextIssue ? (
        <div className="mt-3 rounded-lg border border-status-warning/40 bg-background px-3 py-2 text-xs font-medium text-status-warn-foreground">
          Próximo ajuste: {nextIssue}
        </div>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-2 border-t border-status-info/15 pt-3 text-xs text-muted-foreground">
        <span className="rounded-full bg-background px-2.5 py-1">{narrationWords} palavras</span>
        <span className="rounded-full bg-background px-2.5 py-1">~{estimatedSpeechSeconds}s de fala</span>
        <span className="rounded-full bg-background px-2.5 py-1">{dirty ? "Alterações pendentes" : "Roteiro salvo"}</span>
      </div>
    </div>
  );
}

function ProductionReadinessCard({
  catalogLoading,
  catalogError,
  avatarReady,
  voiceReady,
  speechReady,
  speechIssue,
  approvalReady,
  saved,
}: {
  catalogLoading: boolean;
  catalogError: string | null;
  avatarReady: boolean;
  voiceReady: boolean;
  speechReady: boolean;
  speechIssue?: string;
  approvalReady: boolean;
  saved: boolean;
}) {
  const blockingReady =
    !catalogLoading && avatarReady && voiceReady && speechReady && approvalReady;
  const checks = [
    {
      label: "Avatar",
      ready: avatarReady,
      pending: catalogLoading,
      detail: catalogError ? "Atualize a lista da HeyGen" : "Identidade pronta",
    },
    {
      label: "Voz",
      ready: voiceReady,
      pending: catalogLoading,
      detail: "Voz selecionada para a fala",
    },
    {
      label: "Fala",
      ready: speechReady,
      pending: false,
      detail: speechIssue || "Sem alertas de duração ou encerramento",
    },
    {
      label: "Revisão",
      ready: approvalReady,
      pending: false,
      detail: approvalReady ? "Roteiro marcado como Pronto" : 'Altere o status para "Pronto"',
    },
    {
      label: "Sheets",
      ready: saved,
      pending: false,
      detail: saved ? "Roteiro sincronizado" : "Será salvo automaticamente ao enviar",
    },
  ];

  return (
    <div className="rounded-xl border bg-card p-4 shadow-sm">
      <div className="flex items-start gap-2">
        {blockingReady ? (
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-status-success" />
        ) : (
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-status-warn-foreground" />
        )}
        <div>
          <h3 className="font-display text-sm font-semibold">
            {blockingReady ? "Pronto para o HeyGen" : "Checklist de produção"}
          </h3>
          <p className="mt-1 text-[11px] leading-4 text-muted-foreground">
            {blockingReady
              ? "Tudo que impede o envio está resolvido."
              : "Resolva os itens pendentes para liberar o envio."}
          </p>
        </div>
      </div>
      <ul className="mt-3 space-y-2 border-t pt-3">
        {checks.map((check) => (
          <li key={check.label} className="flex items-start gap-2 text-xs">
            {check.pending ? (
              <Circle className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-pulse text-muted-foreground" />
            ) : check.ready ? (
              <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-status-success" />
            ) : (
              <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-status-warn-foreground" />
            )}
            <span className="min-w-0">
              <span className="font-medium">{check.label}</span>
              <span className="block text-[11px] leading-4 text-muted-foreground">
                {check.pending ? "Carregando catálogo..." : check.detail}
              </span>
            </span>
          </li>
        ))}
      </ul>
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
