import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { CompliancePanel, HighlightedText } from "@/components/compliance-panel";
import { StatusTimeline, type TimelineStep } from "@/components/status-timeline";
import { WithTooltip } from "@/components/with-tooltip";
import { ConfirmAction } from "@/components/confirm-action";
import { prioridadeLabel, riskLabel, scriptStatusLabel } from "@/lib/status";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  ArrowLeft,
  Captions,
  Film,
  History,
  RotateCcw,
  Save,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute("/_app/roteiros/$id")({
  head: ({ params }) => ({
    meta: [
      { title: `Roteiro ${params.id} | AI Video Creator` },
      { name: "description", content: "Edicao de roteiro e preparacao para producao de video." },
    ],
  }),
  component: RoteiroDetalhe,
});

function RoteiroDetalhe() {
  const { id } = Route.useParams();
  const script = useStore((s) => s.scripts.find((x) => x.id === id));
  const updateScript = useStore((s) => s.updateScript);
  const addVideoJob = useStore((s) => s.addVideoJob);
  const videoJobs = useStore((s) => s.videoJobs);
  const palavras = useStore((s) => s.settings.palavrasProibidas);
  const navigate = useNavigate();

  const [draft, setDraft] = useState<Script | undefined>(script);
  const [sending, setSending] = useState(false);
  const [saving, setSaving] = useState(false);
  const [catalog, setCatalog] = useState<HeyGenCatalog | null>(null);
  const [styles, setStyles] = useState<HeyGenStyle[]>([]);
  const [avatarId, setAvatarId] = useState("");
  const [voiceId, setVoiceId] = useState("");
  const [orientation, setOrientation] = useState<"portrait" | "landscape">("portrait");
  const [durationSeconds, setDurationSeconds] = useState<10 | 15 | 30 | 45 | 60>(45);
  const [speechMode, setSpeechMode] = useState<"natural" | "fiel" | "direto">("natural");
  const [captions, setCaptions] = useState(true);
  const [optimizePronunciation, setOptimizePronunciation] = useState(true);
  const [styleId, setStyleId] = useState("");
  const [narrationText, setNarrationText] = useState(() =>
    script ? buildNarrationText(script) : "",
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

  useEffect(() => {
    if (script) {
      setDraft(script);
      setNarrationText(buildNarrationText(script));
    }
  }, [script]);

  useEffect(() => {
    fetchHeyGenCatalog()
      .then((data) => {
        setCatalog(data);
        setAvatarId(data.defaultAvatarId || data.avatars[0]?.id || "");
        setVoiceId(data.defaultVoiceId || data.voices[0]?.id || "");
      })
      .catch((err) =>
        toast.error(err instanceof Error ? err.message : "Falha ao carregar HeyGen."),
      );
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

  async function enviarProducao(forceNewVersion = false) {
    if (!draft || !script) return;
    setSending(true);
    try {
      const job = await createHeyGenVideo(script.id, {
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
      });
      addVideoJob(job);
      toast.success("Roteiro enviado para producao no HeyGen.");
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
      setNarrationText(
        await naturalizeScript({
          text: narrationText,
          medicalCautions: draft.cuidadosMedicos,
          durationSeconds,
        }),
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
                title="Criar uma nova versão?"
                description={`Este roteiro já possui ${existingJobs.length} ${
                  existingJobs.length === 1 ? "vídeo" : "vídeos"
                }. A nova versão consumirá créditos adicionais do HeyGen.`}
                confirmLabel="Criar nova versão"
                onConfirm={() => void enviarProducao(true)}
                trigger={
                  <Button
                    size="sm"
                    variant="secondary"
                    title="Gerar outra versão deste roteiro"
                    disabled={dirty || sending || !avatarId || !voiceId}
                  >
                    <History className="mr-1 h-4 w-4" /> Nova versão
                  </Button>
                }
              />
            </>
          ) : (
            <ConfirmAction
              title="Enviar para producao?"
              description="Este clique envia o roteiro ao HeyGen e pode consumir creditos da conta."
              confirmLabel="Enviar"
              onConfirm={() => void enviarProducao(false)}
              trigger={
                <Button
                  size="sm"
                  title={dirty ? "Salve as alteracoes antes de enviar" : "Enviar roteiro ao HeyGen"}
                  disabled={dirty || sending || !avatarId || !voiceId}
                >
                  <Film className="mr-1 h-4 w-4" /> Enviar para producao
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
          </div>

          <WorkflowJump />

          <div id="roteiro-editar" className="scroll-mt-20 rounded-xl border bg-card p-4 shadow-sm">
            <div className="mb-4">
              <h3 className="font-display text-sm font-semibold">1. Editar roteiro</h3>
              <p className="mt-1 text-xs text-muted-foreground">
                Ajuste a ideia, o cuidado médico e o status antes de preparar o vídeo.
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
                <Textarea rows={2} value={draft.cta} onChange={(e) => set("cta", e.target.value)} />
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

          <div
            id="roteiro-produzir"
            className="scroll-mt-20 rounded-xl border bg-card p-4 shadow-sm"
          >
            <div className="mb-4">
              <h3 className="font-display text-sm font-semibold">2. Preparar vídeo</h3>
              <p className="mt-1 text-xs text-muted-foreground">
                Escolha o visual e o ritmo. A voz do Dr. Guilherme já está configurada.
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Avatar">
                <Select value={avatarId} onValueChange={setAvatarId} disabled={!catalog}>
                  <SelectTrigger>
                    <SelectValue placeholder="Carregando avatares..." />
                  </SelectTrigger>
                  <SelectContent>
                    {catalog?.avatars.map((avatar) => (
                      <SelectItem key={avatar.id} value={avatar.id}>
                        {avatar.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
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
              <Field label="Duração aproximada">
                <Select
                  value={String(durationSeconds)}
                  onValueChange={(value) =>
                    setDurationSeconds(Number(value) as 10 | 15 | 30 | 45 | 60)
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="10">10 segundos - impacto rápido</SelectItem>
                    <SelectItem value="15">15 segundos - ultracurto</SelectItem>
                    <SelectItem value="30">30 segundos - rápido</SelectItem>
                    <SelectItem value="45">45 segundos - recomendado</SelectItem>
                    <SelectItem value="60">60 segundos - mais completo</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
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
            <div className="mt-3 rounded-md border border-status-info/30 bg-status-info/5 px-3 py-2">
              <div className="text-xs font-medium">Encerramento padrão</div>
              <div className="mt-0.5 text-[11px] text-muted-foreground">
                “Me siga para mais dicas, e obrigado.”
              </div>
            </div>
            <div className="mt-4 border-t pt-4">
              <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
                <div>
                  <Label htmlFor="narration-text">Texto falado</Label>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    Edite livremente. Isso muda apenas a fala do vídeo, não o roteiro no Sheets.
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => setNarrationText(buildNarrationText(draft))}
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
                    {naturalizing ? "Ajustando..." : "Deixar natural com IA"}
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
              <div className="mt-2 flex justify-between text-[11px] text-muted-foreground">
                <span>{narrationText.trim().split(/\s+/).filter(Boolean).length} palavras</span>
                <span>
                  Aproximadamente{" "}
                  {Math.max(
                    1,
                    Math.round(narrationText.trim().split(/\s+/).filter(Boolean).length / 2.4),
                  )}
                  s de fala
                </span>
              </div>
              <div className="mt-2 flex items-start gap-2 rounded-md border border-status-success/30 bg-status-success/10 px-3 py-2 text-[11px] leading-4 text-muted-foreground">
                <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-status-success" />A fala
                exata será validada pelo compliance antes de qualquer envio ao HeyGen. Se houver
                dose, promessa ou instrução prescritiva, a produção será bloqueada.
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
          <CompliancePanel fields={complianceFields} palavrasProibidas={palavras} />
        </div>
      </div>
    </AppShell>
  );
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

function buildNarrationText(script: Script): string {
  const outro = "Me siga para mais dicas, e obrigado.";
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
  return body.toLocaleLowerCase("pt-BR").includes(outro.toLocaleLowerCase("pt-BR"))
    ? body
    : `${body}\n\n${outro}`;
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
