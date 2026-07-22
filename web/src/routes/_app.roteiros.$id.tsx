import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { CompliancePanel, HighlightedText } from "@/components/compliance-panel";
import { StatusTimeline, type TimelineStep } from "@/components/status-timeline";
import { WithTooltip } from "@/components/with-tooltip";
import { ConfirmAction } from "@/components/confirm-action";
import {
  prioridadeLabel,
  riskLabel,
  scriptStatusLabel,
} from "@/lib/status";
import { useStore } from "@/lib/store";
import { createHeyGenVideo, fetchHeyGenCatalog, type HeyGenCatalog } from "@/lib/api/local";
import type { Prioridade, Script, ScriptStatus } from "@/lib/mock-data";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ArrowLeft, Film, Save } from "lucide-react";
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
  const palavras = useStore((s) => s.settings.palavrasProibidas);
  const navigate = useNavigate();

  const [draft, setDraft] = useState<Script | undefined>(script);
  const [sending, setSending] = useState(false);
  const [catalog, setCatalog] = useState<HeyGenCatalog | null>(null);
  const [avatarId, setAvatarId] = useState("");
  const [voiceId, setVoiceId] = useState("");

  useEffect(() => {
    if (script) setDraft(script);
  }, [script]);

  useEffect(() => {
    fetchHeyGenCatalog()
      .then((data) => {
        setCatalog(data);
        setAvatarId(data.defaultAvatarId || data.avatars[0]?.id || "");
        setVoiceId(data.defaultVoiceId || data.voices[0]?.id || "");
      })
      .catch((err) => toast.error(err instanceof Error ? err.message : "Falha ao carregar HeyGen."));
  }, []);
  const dirty = useMemo(
    () => JSON.stringify(draft) !== JSON.stringify(script),
    [draft, script],
  );

  if (!script || !draft) {
    return (
      <AppShell title="Roteiro">
        <p className="text-sm text-muted-foreground">
          Roteiro nao encontrado.{" "}
          <Link to="/roteiros" className="text-status-info underline">Voltar</Link>
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

  async function enviarProducao() {
    if (!draft || !script) return;
    setSending(true);
    try {
      const job = await createHeyGenVideo(script.id, { avatarId, voiceId });
      addVideoJob(job);
      toast.success("Roteiro enviado para producao no HeyGen.");
      navigate({ to: "/producao/$id", params: { id: job.id } });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Nao foi possivel enviar ao HeyGen.");
    } finally {
      setSending(false);
    }
  }

  return (
    <AppShell
      title={`Roteiro: ${script.titulo}`}
      actions={
        <>
          <Button variant="ghost" size="sm" asChild>
            <Link to="/roteiros"><ArrowLeft className="mr-1 h-4 w-4" /> Voltar</Link>
          </Button>
          <WithTooltip label={dirty ? "Salvar alteracoes" : "Nenhuma alteracao pendente"}>
            <Button
              size="sm"
              variant="secondary"
              disabled={!dirty}
              onClick={() => {
                try {
                  updateScript(script.id, draft);
                  toast.success("Roteiro salvo.");
                } catch {
                  toast.error("Nao foi possivel salvar.");
                }
              }}
            >
              <Save className="mr-1 h-4 w-4" /> Salvar
            </Button>
          </WithTooltip>
          <ConfirmAction
            title="Enviar para producao?"
            description="Este clique envia o roteiro ao HeyGen e pode consumir creditos da conta."
            confirmLabel="Enviar"
            onConfirm={enviarProducao}
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

          <div className="rounded-xl border bg-card p-4 shadow-sm">
            <div className="grid gap-3 md:grid-cols-2">
              <Field label="Titulo">
                <Input value={draft.titulo} onChange={(e) => set("titulo", e.target.value)} />
              </Field>
              <Field label="Tema">
                <Input value={draft.tema} onChange={(e) => set("tema", e.target.value)} />
              </Field>
              <Field label="Hook">
                <Textarea rows={2} value={draft.hook} onChange={(e) => set("hook", e.target.value)} />
              </Field>
              <Field label="Dor / conflito">
                <Textarea rows={2} value={draft.dorConflito} onChange={(e) => set("dorConflito", e.target.value)} />
              </Field>
              <Field label="Explicacao simples">
                <Textarea rows={3} value={draft.explicacaoSimples} onChange={(e) => set("explicacaoSimples", e.target.value)} />
              </Field>
              <Field label="Virada / provocacao">
                <Textarea rows={3} value={draft.virada} onChange={(e) => set("virada", e.target.value)} />
              </Field>
              <Field label="CTA">
                <Textarea rows={2} value={draft.cta} onChange={(e) => set("cta", e.target.value)} />
              </Field>
              <Field label="Cuidados medicos">
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
                    <SelectItem value="em_revisao">Em edicao</SelectItem>
                    <SelectItem value="aprovado_clinicamente">Pronto</SelectItem>
                    <SelectItem value="rejeitado">Arquivado</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Avatar HeyGen">
                <Select value={avatarId} onValueChange={setAvatarId} disabled={!catalog}>
                  <SelectTrigger><SelectValue placeholder="Carregando avatares..." /></SelectTrigger>
                  <SelectContent>
                    {catalog?.avatars.map((avatar) => (
                      <SelectItem key={avatar.id} value={avatar.id}>
                        {avatar.name} ({avatar.orientation === "portrait" ? "vertical" : "horizontal"})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Voz HeyGen">
                <Select value={voiceId} onValueChange={setVoiceId} disabled={!catalog}>
                  <SelectTrigger><SelectValue placeholder="Carregando vozes..." /></SelectTrigger>
                  <SelectContent>
                    {catalog?.voices.map((voice) => (
                      <SelectItem key={voice.id} value={voice.id}>{voice.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
            </div>
          </div>

          <div className="rounded-xl border bg-card p-4 shadow-sm">
            <h3 className="mb-2 font-display text-sm font-semibold">Preview com highlight</h3>
            <div className="space-y-2 text-sm leading-relaxed">
              <Preview label="Hook" text={draft.hook} palavras={palavras} />
              <Preview label="Dor / conflito" text={draft.dorConflito} palavras={palavras} />
              <Preview label="Explicacao" text={draft.explicacaoSimples} palavras={palavras} />
              <Preview label="Virada" text={draft.virada} palavras={palavras} />
              <Preview label="CTA" text={draft.cta} palavras={palavras} />
            </div>
          </div>
        </div>

        <div className="space-y-3">
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
  const order: ScriptStatus[] = [
    "aguardando_validacao",
    "em_revisao",
    "aprovado_clinicamente",
  ];
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
      hint: status === "aprovado_clinicamente" ? "Pronto para producao" : "Quando o roteiro estiver pronto",
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

function Preview({ label, text, palavras }: { label: string; text: string; palavras: string[] }) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="text-sm">
        <HighlightedText text={text} palavrasProibidas={palavras} />
      </div>
    </div>
  );
}
