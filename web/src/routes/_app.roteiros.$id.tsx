import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
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
  createHeyGenVideo,
  fetchHeyGenCatalog,
  fetchHeyGenStyles,
  naturalizeScript,
  saveScript,
  type HeyGenCatalog,
  type HeyGenStyle,
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
  RotateCcw,
  Save,
  ShieldCheck,
  Sparkles,
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
  const [saving, setSaving] = useState(false);
  const [catalog, setCatalog] = useState<HeyGenCatalog | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [styles, setStyles] = useState<HeyGenStyle[]>([]);
  const [avatarId, setAvatarId] = useState("");
  const [voiceId, setVoiceId] = useState("");
  const [orientation, setOrientation] = useState<"portrait" | "landscape">("portrait");
  const [durationSeconds, setDurationSeconds] = useState<10 | 15 | 30 | 45 | 60>(
    initialCaptureDuration ?? 45,
  );
  const [speechMode, setSpeechMode] = useState<"natural" | "fiel" | "direto">("natural");
  const [captions, setCaptions] = useState(true);
  const [optimizePronunciation, setOptimizePronunciation] = useState(true);
  const [styleId, setStyleId] = useState("");
  const [outroText, setOutroText] = useState(initialOutro);
  const [narrationText, setNarrationText] = useState(() =>
    script ? buildNarrationText(script, initialOutro) : "",
  );
  const [naturalizing, setNaturalizing] = useState(false);
  const existingJobs = useMemo(
    () =>
      videoJobs
        .filter((job) => job.scriptId === id && job.status !== "erro")
        .sort(
          (left, right) => new Date(right.criadoEm).getTime() - new Date(left.criadoEm).getTime(),
        ),
    [id, videoJobs],
  );
  const latestJob = existingJobs[0];
  const qualityIssues = useMemo(
    () => narrationQualityIssues(narrationText, durationSeconds, outroText),
    [durationSeconds, narrationText, outroText],
  );
  const hasHighCreditConsumption = durationSeconds >= 45;
  const approvalReady = draft?.status === "aprovado_clinicamente";
  const canSendToProduction = qualityIssues.length === 0 && approvalReady;
  const narrationWords = narrationText.trim().split(/\s+/).filter(Boolean).length;
  const estimatedSpeechSeconds = Math.max(1, Math.round(narrationWords / 2.4));

  useEffect(() => {
    if (script) {
      setDraft(script);
      const savedCaptureDuration = captureHookDuration(script);
      const savedOutro = savedCaptureDuration === 10 ? "" : script.outroText || DEFAULT_OUTRO;
      setOutroText(savedOutro);
      setNarrationText(buildNarrationText(script, savedOutro));
      if (savedCaptureDuration !== null) {
        setDurationSeconds(savedCaptureDuration);
        setSpeechMode("direto");
      }
    }
  }, [script]);

  const loadCatalog = (showSuccess = false) => {
    setCatalogLoading(true);
    setCatalogError(null);
    fetchHeyGenCatalog()
      .then((data) => {
        setCatalog(data);
        setAvatarId(data.defaultAvatarId || data.avatars[0]?.id || "");
        setVoiceId(data.defaultVoiceId || data.voices[0]?.id || "");
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
        : !avatarId
          ? "Selecione um avatar pronto."
          : !voiceId
            ? "Selecione uma voz."
            : saving
              ? "Salvando roteiro."
              : null;

  async function enviarProducao(forceNewVersion = false) {
    if (!draft || !script) return;
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
        captions,
        optimizePronunciation,
        styleId: styleId || undefined,
        forceNewVersion,
        narrationText,
        outroText: durationSeconds === 10 ? "" : outroText,
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
        text: narrationText,
        medicalCautions: draft.cuidadosMedicos,
        durationSeconds,
        outro: durationSeconds === 10 ? "" : outroText,
      });
      setNarrationText(
        durationSeconds === 10
          ? removeNarrationOutro(naturalized, outroText)
          : normalizeNarrationOutro(naturalized, outroText),
      );
      toast.success("Texto naturalizado. Revise a fala antes de enviar.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível naturalizar o texto.");
    } finally {
      setNaturalizing(false);
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
                    disabled={saving || sending || !avatarId || !voiceId || !canSendToProduction}
                  >
                    <History className="mr-1 h-4 w-4" /> Refazer vídeo
                  </Button>
                }
              />
            </>
          ) : (
            <ConfirmAction
              title="Enviar para producao?"
              description={
                <div className="space-y-3">
                  <p>Este clique envia o roteiro ao HeyGen e pode consumir créditos da conta.</p>
                  {hasHighCreditConsumption ? <HighCreditConsumptionNotice compact /> : null}
                </div>
              }
              confirmLabel="Enviar"
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
                  disabled={saving || sending || !avatarId || !voiceId || !canSendToProduction}
                >
                  <Film className="mr-1 h-4 w-4" />{" "}
                  {dirty ? "Salvar e enviar" : "Enviar para producao"}
                </Button>
              }
            />
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
              <div className="space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <Label className="text-xs">Avatar</Label>
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
                <AvatarPicker
                  value={avatarId}
                  avatars={catalog?.avatars || []}
                  loading={catalogLoading}
                  error={catalogError}
                  onChange={setAvatarId}
                />
                {catalogError ? (
                  <p className="text-[11px] leading-4 text-status-danger">
                    HeyGen demorou para responder. Tente atualizar; se houver cache, o app usa a
                    ultima lista salva.
                  </p>
                ) : null}
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
              <div className="space-y-2">
                <Field label="Duração aproximada">
                  <Select
                    value={String(durationSeconds)}
                    onValueChange={(value) => {
                      const nextDuration = Number(value) as 10 | 15 | 30 | 45 | 60;
                      setDurationSeconds(nextDuration);
                      if (nextDuration === 10) {
                        setNarrationText((current) => removeNarrationOutro(current, outroText));
                        setOutroText("");
                        setSpeechMode("direto");
                      } else if (!outroText.trim()) {
                        setOutroText(DEFAULT_OUTRO);
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
                  onValueChange={(value) => setSpeechMode(value as "natural" | "fiel" | "direto")}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="natural">Natural - conversa fluida</SelectItem>
                    <SelectItem value="fiel">Fiel - segue o roteiro</SelectItem>
                    <SelectItem value="direto">Direto - curto e dinâmico</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              {durationSeconds <= 15 ? (
                <div className="rounded-md border border-status-info/30 bg-status-info/5 px-3 py-2.5">
                  <div className="text-xs font-medium">Clipe contínuo</div>
                  <p className="mt-0.5 text-[11px] leading-4 text-muted-foreground">
                    O avatar fala em uma tomada direta, com ritmo ajustado automaticamente.
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
            {durationSeconds === 10 ? (
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
                      setNarrationText((current) => normalizeNarrationOutro(current, outroText))
                    }
                    placeholder="Ex.: Me siga para mais dicas."
                    maxLength={180}
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() =>
                      setNarrationText((current) => normalizeNarrationOutro(current, outroText))
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
                  <Label htmlFor="narration-text">Fala final do avatar</Label>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    Edite livremente. Isso muda apenas a fala do vídeo, não o roteiro no Sheets.
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      setNarrationText(
                        buildNarrationText(draft, durationSeconds === 10 ? "" : outroText),
                      )
                    }
                  >
                    <RotateCcw className="mr-1 h-4 w-4" />
                    Restaurar
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    disabled={naturalizing || narrationText.trim().length < 20}
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
                id="narration-text"
                rows={8}
                value={narrationText}
                onChange={(event) => setNarrationText(event.target.value)}
                className="leading-6"
              />
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
                          setNarrationText(normalizeNarrationOutro(narrationText, outroText))
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
            avatarReady={Boolean(avatarId)}
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
                      {orientationLabel(avatar.orientation)}
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
