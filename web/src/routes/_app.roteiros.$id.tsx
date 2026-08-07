import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { CompliancePanel, HighlightedText } from "@/components/compliance-panel";
import { StatusTimeline, type TimelineStep } from "@/components/status-timeline";
import { NextStepBanner } from "@/components/next-step-banner";
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
  fetchScenePlan,
  generateSceneDirection,
  naturalizeScript,
  saveAvatarSet,
  saveProductionProfile,
  saveScript,
  saveScenePlan,
  type AvatarSet,
  type AvatarSetLook,
  type AvatarSetRole,
  type HeyGenCatalog,
  type HeyGenStyle,
  type ScenePlan,
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
  const productionModeReady = avatarMode === "single";
  const selectedAvatarReady = avatarMode === "single" ? Boolean(avatarId) : avatarSetReady;
  const sceneRoles = useMemo<AvatarSetRole[]>(
    () =>
      selectedAvatarSet?.looks.map((look) => look.role) || ["primary"],
    [selectedAvatarSet],
  );
  const canSendToProduction =
    qualityIssues.length === 0 && approvalReady && selectedAvatarReady && productionModeReady;

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
  const productionBlockedReason = qualityIssues[0]
    ? `Revise a fala final: ${qualityIssues[0]}`
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
              : avatarMode === "set"
                ? "Scene Plan ainda não está implementado para gerar vídeos com duas posições."
                : !avatarId
                  ? "Selecione um avatar pronto."
            : !voiceId
              ? "Selecione uma voz."
              : saving
                ? "Salvando roteiro."
                : null;

  async function enviarProducao(forceNewVersion = false) {
    if (!draft || !script) return;
    if (avatarMode === "set") {
      toast.error("A geração com duas posições será habilitada após o Scene Plan.");
      return;
    }
    if (!canSendToProduction) {
      toast.error(
        qualityIssues[0]
          ? `Revise o texto falado antes de enviar: ${qualityIssues[0]}`
          : 'Conclua a revisão e altere o status do roteiro para "Pronto".',
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
    if (avatarMode === "set") {
      toast.error("A prévia de Avatar Set será habilitada após o Scene Plan.");
      return;
    }
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
                      !canSendToProduction
                        ? "Revise o texto falado antes de enviar"
                        : dirty
                          ? "Salvar alteracoes e gerar outra versao"
                          : "Gerar outra versão deste roteiro"
                    }
                    disabled={
                      saving || sending || !selectedAvatarReady || !voiceId || !canSendToProduction
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
                description="Este clique envia somente o começo naturalizado ao HeyGen e pode consumir créditos da conta."
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
                      !approvalReady ||
                      !productionModeReady
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
                      !canSendToProduction
                        ? "Revise o texto falado antes de enviar"
                        : dirty
                          ? "Salvar alteracoes e enviar roteiro ao HeyGen"
                          : "Enviar roteiro ao HeyGen"
                    }
                    disabled={
                      saving || sending || !selectedAvatarReady || !voiceId || !canSendToProduction
                    }
                  >
                    <Film className="mr-1 h-4 w-4" />{" "}
                    {dirty ? "Salvar e gerar" : "Gerar vídeo final"}
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

          <NextStepBanner
            title={
              latestJob
                ? "Este roteiro já tem vídeo criado"
                : dirty
                  ? "Salvar ajustes e enviar para o HeyGen"
                  : "Enviar roteiro para produção"
            }
            description={
              latestJob
                ? "Você pode abrir a produção existente ou gerar uma nova versão se quiser testar outro avatar, duração ou fala."
                : "Revise a fala final do avatar, confira avatar/voz e envie para criar o vídeo."
            }
            actionLabel={
              latestJob ? "Ver vídeo" : dirty ? "Salvar e enviar" : "Enviar para produção"
            }
            onAction={
              latestJob
                ? () => navigate({ to: "/producao/$id", params: { id: latestJob.id } })
                : () => void enviarProducao(false)
            }
            disabled={!latestJob && Boolean(productionBlockedReason)}
            disabledReason={!latestJob ? productionBlockedReason || undefined : undefined}
            meta={
              <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                <span className="rounded-full bg-background px-2.5 py-1">
                  {narrationWords} palavras
                </span>
                <span className="rounded-full bg-background px-2.5 py-1">
                  ~{estimatedSpeechSeconds}s de fala
                </span>
                <span className="rounded-full bg-background px-2.5 py-1">
                  {dirty ? "Alterações pendentes" : "Roteiro salvo"}
                </span>
              </div>
            }
          />

          {latestPreview ? (
            <div className="rounded-xl border border-status-info/30 bg-status-info/5 p-4 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="font-semibold">
                    Prévia técnica de avatar e voz — Direct Avatar
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Avalia avatar, voz, ritmo e pronúncia; não representa a composição visual do
                    Video Agent.
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
            <div className="rounded-xl border border-status-info/30 bg-status-info/5 p-4">
              <div className="mb-3 text-sm font-semibold">Compare os 3 roteiros de 10s</div>
              <div className="grid gap-2 sm:grid-cols-3">
                {siblingCaptureScripts.map((candidate, index) => (
                  <Link
                    key={candidate.id}
                    to="/roteiros/$id"
                    params={{ id: candidate.id }}
                    className={`rounded-lg border p-3 text-sm transition-colors ${
                      candidate.id === script.id
                        ? "border-status-info bg-background"
                        : "bg-background/60 hover:border-status-info/50"
                    }`}
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
            </div>
          ) : null}

          {durationSeconds > 15 ? <WorkflowJump /> : null}

          {durationSeconds > 15 ? (
            <div
              id="roteiro-editar"
              className="scroll-mt-20 rounded-xl border bg-card p-4 shadow-sm"
            >
              <div className="mb-4">
                <h3 className="font-display text-sm font-semibold">1. Briefing do roteiro</h3>
                <p className="mt-1 text-xs text-muted-foreground">
                  Campos que orientam a IA e preservam o contexto médico. A fala final fica na etapa
                  de vídeo.
                </p>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <Field label="Titulo">
                  <Input value={draft.titulo} onChange={(e) => set("titulo", e.target.value)} />
                </Field>
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
                <Field label="Explicacao simples">
                  <Textarea
                    rows={3}
                    value={draft.explicacaoSimples}
                    onChange={(e) => set("explicacaoSimples", e.target.value)}
                  />
                </Field>
                <Field label="Virada / provocacao">
                  <Textarea
                    rows={3}
                    value={draft.virada}
                    onChange={(e) => set("virada", e.target.value)}
                  />
                </Field>
                <Field label="CTA">
                  <Textarea
                    rows={2}
                    value={draft.cta}
                    onChange={(e) => set("cta", e.target.value)}
                  />
                </Field>
                <Field label="Cuidados medicos">
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
                      <SelectItem value="em_revisao">Em edicao</SelectItem>
                      <SelectItem value="aprovado_clinicamente">Pronto</SelectItem>
                      <SelectItem value="rejeitado">Arquivado</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
              </div>
            </div>
          ) : null}

          <div
            id="roteiro-produzir"
            className="scroll-mt-20 rounded-xl border bg-card p-4 shadow-sm"
          >
            <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="font-display text-sm font-semibold">
                  {durationSeconds === 10 ? "Hook e vídeo" : "2. Fala final e vídeo"}
                </h3>
                <p className="mt-1 text-xs text-muted-foreground">
                  Edite exatamente o que o avatar vai falar e escolha visual, duração e ritmo.
                </p>
              </div>
              <div
                className={`rounded-md border px-2.5 py-1.5 text-right text-[11px] ${
                  qualityIssues.length
                    ? "border-status-warn/40 bg-status-warn/10 text-status-warn-foreground"
                    : "border-status-success/30 bg-status-success/10 text-status-success-foreground"
                }`}
              >
                <div className="font-semibold">
                  {qualityIssues.length ? "Revisão necessária" : "Fala pronta"}
                </div>
                <div className="mt-0.5 opacity-80">
                  {narrationWords} palavras · ~{estimatedSpeechSeconds}s
                </div>
              </div>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-3 md:col-span-2">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <Label className="text-xs">Avatar e posições</Label>
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
                    selectedLooks={selectedSetLooks}
                    primaryAvatarId={primaryAvatarId}
                    loading={avatarSetsLoading}
                    onSelect={chooseAvatarSet}
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
              <div className="md:col-span-2">
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
                  onSaved={setScenePlan}
                />
              </div>
              <Field label="Formato do vídeo">
                <Select
                  value={orientation}
                  onValueChange={(value) => setOrientation(value as "portrait" | "landscape")}
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
                <div className="flex min-h-14 items-center rounded-md border bg-muted/30 px-3 text-sm text-muted-foreground">
                  {selectedVoiceName}
                </div>
              </div>
              <Field label="Modo de geração">
                <Select
                  value={generationMode}
                  onValueChange={(value) => setGenerationMode(value as "direct" | "video_agent")}
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
                  </SelectContent>
                </Select>
              </Field>
              <div className="space-y-2">
                <Field label="Duração aproximada">
                  <Select
                    value={String(durationSeconds)}
                    onValueChange={(value) => {
                      const nextDuration = Number(value) as 10 | 15 | 30 | 45 | 60;
                      setDurationSeconds(nextDuration);
                      if (nextDuration === 10) {
                        setDisplayText((current) => removeNarrationOutro(current, outroText));
                        setSpokenText((current) => removeNarrationOutro(current, outroText));
                        setNarrationText((current) => removeNarrationOutro(current, outroText));
                        setOutroText("");
                        setSpeechMode("direto");
                      } else if (!outroText.trim()) {
                        setOutroText(DEFAULT_OUTRO);
                        setDisplayText((current) =>
                          normalizeNarrationOutro(current, DEFAULT_OUTRO),
                        );
                        setSpokenText((current) => normalizeNarrationOutro(current, DEFAULT_OUTRO));
                        setNarrationText((current) =>
                          normalizeNarrationOutro(current, DEFAULT_OUTRO),
                        );
                      }
                    }}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="10">10 segundos - impacto rápido</SelectItem>
                      <SelectItem value="15">15 segundos - ultracurto</SelectItem>
                      <SelectItem value="30">30 segundos - rápido</SelectItem>
                      <SelectItem value="45">45 segundos - maior consumo</SelectItem>
                      <SelectItem value="60">60 segundos - alto consumo</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
                <p className="text-[11px] leading-4 text-muted-foreground">
                  {durationSeconds <= 15
                    ? "A duração final acompanha a fala, sem silêncio para completar o tempo."
                    : "O Video Agent organiza o ritmo e as cenas dentro deste tempo aproximado."}
                </p>
                {hasHighCreditConsumption ? <HighCreditConsumptionNotice /> : null}
              </div>
              <Field label="Jeito de falar">
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
              <Field label="CTA falado">
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
                    <SelectItem value="none">Sem CTA falado</SelectItem>
                    <SelectItem value="visual">Apenas visual</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              {generationMode === "direct" ? (
                <div className="rounded-md border border-status-info/30 bg-status-info/5 px-3 py-2.5">
                  <div className="text-xs font-medium">Clipe contínuo</div>
                  <p className="mt-0.5 text-[11px] leading-4 text-muted-foreground">
                    O avatar fala em uma tomada direta para 10, 15, 30, 45 ou 60 segundos.
                  </p>
                </div>
              ) : (
                <Field label="Direção visual">
                  <Select
                    value={styleId || "clean"}
                    onValueChange={(value) => setStyleId(value === "clean" ? "" : value)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="clean">Clean - visual clínico</SelectItem>
                      {styles
                        .filter((style) =>
                          orientation === "portrait"
                            ? style.aspect_ratio === "9:16"
                            : style.aspect_ratio === "16:9",
                        )
                        .map((style) => (
                          <SelectItem key={style.style_id} value={style.style_id}>
                            Cinematic - {style.name}
                          </SelectItem>
                        ))}
                    </SelectContent>
                  </Select>
                </Field>
              )}
            </div>
            <div className="mt-4 grid gap-3 border-t pt-4 md:grid-cols-2">
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
            {ctaMode !== "manual" ? (
              <div className="mt-3 rounded-md border border-status-info/30 bg-status-info/5 px-3 py-3">
                <div className="text-xs font-medium">
                  {ctaMode === "auto"
                    ? "CTA definido na naturalização"
                    : ctaMode === "visual"
                      ? "CTA apenas visual"
                      : "Sem CTA falado"}
                </div>
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  O texto falado não recebe a frase final fixa automaticamente.
                </p>
              </div>
            ) : durationSeconds === 10 ? (
              <div className="mt-3 rounded-md border border-status-info/30 bg-status-info/5 px-3 py-3">
                <div className="text-xs font-medium">Sem frase final nos vídeos de 10 segundos</div>
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  A fala termina diretamente no ponto de maior impacto do hook.
                </p>
              </div>
            ) : (
              <div className="mt-3 rounded-md border border-status-info/30 bg-status-info/5 px-3 py-3">
                <Label htmlFor="outro-text" className="text-xs font-medium">
                  Escolha a frase final do vídeo
                </Label>
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  A frase será colocada uma única vez no fim da fala. Você pode editar livremente.
                </p>
                <div className="mt-2 flex gap-2">
                  <Input
                    id="outro-text"
                    value={outroText}
                    onChange={(event) => setOutroText(event.target.value)}
                    onBlur={() =>
                      setDisplayText((current) => normalizeNarrationOutro(current, outroText))
                    }
                    placeholder="Ex.: Me siga para mais dicas."
                    maxLength={180}
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() =>
                      setDisplayText((current) => normalizeNarrationOutro(current, outroText))
                    }
                  >
                    Aplicar
                  </Button>
                </div>
              </div>
            )}
            <div className="mt-4 border-t pt-4">
              <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
                <div>
                  <Label htmlFor="display-text">Texto exibido</Label>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    Use a grafia correta aqui. Este texto alimenta interface, legenda e subtitles.
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
                        ? `Encurtar para ${durationSeconds}s com IA`
                        : "Deixar natural com IA"}
                  </Button>
                </div>
              </div>
              <Textarea
                id="display-text"
                rows={8}
                value={displayText}
                onChange={(event) => {
                  setDisplayText(event.target.value);
                  setNarrationText(event.target.value);
                }}
                className="leading-6"
              />
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
                  {performancePlan.tone} · {performancePlan.pace} · {performancePlan.emotion} ·
                  speed {performancePlan.recommendedVoiceSpeed}. Pausas e ênfases orientam a edição;
                  o HeyGen ainda usa o preset de voz selecionado.
                </div>
              ) : null}
              {qualityIssues.length > 0 ? (
                <div className="mt-2 rounded-md border border-status-danger/30 bg-status-danger/10 px-3 py-2 text-[11px] leading-4 text-status-danger">
                  <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 font-semibold">
                      <TriangleAlert className="h-3.5 w-3.5" />
                      Revise antes de enviar ao HeyGen
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
              <div className="mt-2 flex justify-between text-[11px] text-muted-foreground">
                <span>{narrationWords} palavras</span>
                <span>Aproximadamente {estimatedSpeechSeconds}s de fala</span>
              </div>
              <div className="mt-2 flex items-start gap-2 rounded-md border border-status-success/30 bg-status-success/10 px-3 py-2 text-[11px] leading-4 text-muted-foreground">
                <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-status-success" />A fala
                exata será validada antes do envio ao HeyGen. Se houver dose, promessa ou instrução
                prescritiva, o sistema mantém o alerta para revisão, mas não bloqueia o teste.
              </div>
            </div>
          </div>

          <div
            id="roteiro-revisar"
            className="scroll-mt-20 rounded-xl border bg-card p-4 shadow-sm"
          >
            <h3 className="mb-2 font-display text-sm font-semibold">3. Revisar com highlight</h3>
            <div className="space-y-2 text-sm leading-relaxed">
              <Preview label="Hook" text={draft.hook} palavras={palavras} />
              <Preview label="Dor / conflito" text={draft.dorConflito} palavras={palavras} />
              <Preview label="Explicacao" text={draft.explicacaoSimples} palavras={palavras} />
              <Preview label="Virada" text={draft.virada} palavras={palavras} />
              <Preview label="CTA" text={draft.cta} palavras={palavras} />
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
            speechReady={qualityIssues.length === 0}
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
  selectedLooks,
  primaryAvatarId,
  loading,
  onSelect,
  onCreate,
  onEdit,
  onDelete,
  onPrimaryChange,
}: {
  sets: AvatarSet[];
  selectedId: string | null;
  selected: AvatarSet | null;
  selectedLooks: Array<{ look: AvatarSetLook; avatar: HeyGenCatalog["avatars"][number] }>;
  primaryAvatarId: string;
  loading: boolean;
  onSelect: (avatarSet: AvatarSet) => void;
  onCreate: () => void;
  onEdit: (avatarSet: AvatarSet) => void;
  onDelete: (avatarSet: AvatarSet) => void;
  onPrimaryChange: (avatarId: string) => void;
}) {
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
            {selected.looks.map((look) => {
              const item = selectedLooks.find((candidate) => candidate.look.avatarId === look.avatarId);
              const primary = look.avatarId === primaryAvatarId;
              return (
                <button
                  key={`${look.role}-${look.avatarId}`}
                  type="button"
                  onClick={() => onPrimaryChange(look.avatarId)}
                  className={cn(
                    "flex items-center gap-2 rounded-md border bg-background p-2 text-left transition-colors hover:border-primary/50",
                    primary && "border-primary ring-1 ring-primary/30",
                  )}
                >
                  {item?.avatar ? <AvatarThumbnail avatar={item.avatar} className="h-12 w-12" /> : <UserRound className="h-8 w-8 text-muted-foreground" />}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs font-semibold">{look.label}</span>
                    <span className="block truncate text-[11px] text-muted-foreground">
                      {avatarSetRoleLabel(look.role)} · {item?.avatar?.name || "Look não carregado"}
                    </span>
                    {primary ? <span className="mt-0.5 block text-[10px] font-medium text-primary">Posição principal</span> : null}
                  </span>
                </button>
              );
            })}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-[11px] leading-4 text-muted-foreground">
              Para preservar continuidade, use looks da mesma pessoa, roupa e sessão visual sempre que possível.
            </p>
            <div className="flex gap-1">
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
              {looks.map((look, index) => (
                <div key={`${index}-${look.avatarId}`} className="grid gap-2 rounded-lg border bg-muted/20 p-2 sm:grid-cols-[1.2fr_0.8fr_1fr_auto]">
                  <Select value={look.avatarId} onValueChange={(value) => updateLook(index, { avatarId: value })}>
                    <SelectTrigger><SelectValue placeholder="Look do catálogo" /></SelectTrigger>
                    <SelectContent>
                      {avatars.map((avatar) => <SelectItem key={avatar.id} value={avatar.id}>{avatar.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
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
                </div>
              ))}
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
  onSaved,
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
  onSaved: (plan: ScenePlan) => void;
}) {
  const [scenes, setScenes] = useState<EditableScene[]>([]);
  const [saving, setSaving] = useState(false);
  const [directing, setDirecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [directionNotice, setDirectionNotice] = useState<string | null>(null);

  useEffect(() => {
    if (loading) return;
    setScenes(
      plan?.scenes.map((scene) => ({
        id: scene.id,
        text: scene.text,
        lookRole: availableRoles.includes(scene.lookRole) ? scene.lookRole : availableRoles[0] || "primary",
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
      setScenes(
        result.scenes.map((scene, index) => ({
          id: `scene-${index + 1}`,
          text: scene.text,
          lookRole: availableRoles.includes(scene.lookRole) ? scene.lookRole : availableRoles[0] || "primary",
          estimatedStart: 0,
          estimatedEnd: 0,
        })),
      );
      setDirectionNotice("Claude sugeriu uma divisão. Revise e salve o plano quando estiver de acordo.");
    } catch (directionError) {
      setError(directionError instanceof Error ? directionError.message : "Nao foi possivel gerar direção com Claude.");
    } finally {
      setDirecting(false);
    }
  }

  async function save() {
    if (scenes.some((scene) => !scene.text.trim())) {
      setError("Cada cena precisa ter um texto falado.");
      return;
    }
    if (availableRoles.length >= 2 && new Set(scenes.map((scene) => scene.lookRole)).size < 2) {
      setError("Use pelo menos duas posições diferentes quando o Avatar Set estiver ativo.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await saveScenePlan(scriptId, scenes);
      onSaved(saved);
      toast.success("Scene Plan salvo.");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Nao foi possivel salvar o Scene Plan.");
    } finally {
      setSaving(false);
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
            <Sparkles className="h-3.5 w-3.5" /> {directing ? "Claude pensando..." : "Gerar direção com Claude"}
          </Button>
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
            <div key={scene.id} className="rounded-lg border bg-background p-3">
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

function orientationLabel(orientation: "portrait" | "landscape") {
  return orientation === "portrait" ? "Vertical" : "Horizontal";
}

function WorkflowJump() {
  const items = [
    { href: "#roteiro-editar", label: "Editar", helper: "campos do roteiro" },
    { href: "#roteiro-produzir", label: "Produzir", helper: "avatar e fala" },
    { href: "#roteiro-revisar", label: "Revisar", helper: "highlight" },
    { href: "#roteiro-compliance", label: "Compliance", helper: "bloqueios" },
  ];
  return (
    <nav className="grid gap-2 rounded-xl border bg-muted/25 p-2 sm:grid-cols-4">
      {items.map((item, index) => (
        <a
          key={item.href}
          href={item.href}
          className="flex min-h-14 items-center gap-3 rounded-lg px-3 py-2 text-left transition-colors hover:bg-card"
        >
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-background text-xs font-semibold shadow-sm">
            {index + 1}
          </span>
          <span className="min-w-0">
            <span className="block text-sm font-medium">{item.label}</span>
            <span className="block truncate text-[11px] text-muted-foreground">{item.helper}</span>
          </span>
        </a>
      ))}
    </nav>
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
