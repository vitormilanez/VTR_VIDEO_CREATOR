import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { CompliancePanel } from "@/components/compliance-panel";
import { buildScriptFromIdea } from "@/lib/script-builder";
import { genId, useStore } from "@/lib/store";
import { appendScript, setSheetStatus } from "@/lib/api/local";
import { familiaLabel, ideaStatusLabel, prioridadeLabel } from "@/lib/status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { ArrowLeft, Save, Sparkles } from "lucide-react";
import type { Idea } from "@/lib/mock-data";
import { toast } from "sonner";

export const Route = createFileRoute("/_app/ideias/$id")({
  head: ({ params }) => ({
    meta: [{ title: `Ideia ${params.id} | AI Video Creator` }],
  }),
  component: IdeiaDetalhe,
});

function IdeiaDetalhe() {
  const { id } = Route.useParams();
  const idea = useStore((s) => s.ideas.find((i) => i.id === id));
  const updateIdea = useStore((s) => s.updateIdea);
  const addScript = useStore((s) => s.addScript);
  const palavras = useStore((s) => s.settings.palavrasProibidas);
  const navigate = useNavigate();

  const [draft, setDraft] = useState(idea);

  useEffect(() => {
    if (idea) setDraft(idea);
  }, [idea]);

  if (!idea || !draft) {
    return (
      <AppShell title="Ideia">
        <p className="text-sm text-muted-foreground">
          Ideia nao encontrada.{" "}
          <Link to="/ideias" className="text-status-info underline">
            Voltar
          </Link>
        </p>
      </AppShell>
    );
  }

  function set<K extends keyof Idea>(k: K, v: Idea[K]) {
    setDraft((d) => (d ? { ...d, [k]: v } : d));
  }

  async function gerarRoteiro() {
    if (!idea || !draft) return;
    const script = buildScriptFromIdea(draft, genId("s"));
    try {
      const saved = await appendScript(script);
      addScript(saved);
      updateIdea(idea.id, { status: "aprovado" });
      try {
        await setSheetStatus("ideias", idea.id, "aprovado");
      } catch {
        toast.warning("Roteiro salvo, mas o status da ideia nao foi atualizado.");
      }
      toast.success("Roteiro criado e salvo no Sheets.");
      navigate({ to: "/roteiros/$id", params: { id: saved.id } });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Nao foi possivel criar o roteiro.");
    }
  }

  return (
    <AppShell
      title={idea.titulo}
      actions={
        <>
          <Button variant="ghost" size="sm" asChild>
            <Link to="/ideias">
              <ArrowLeft className="mr-1 h-4 w-4" /> Voltar
            </Link>
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              updateIdea(idea.id, draft);
              toast.success("Ideia salva.");
            }}
          >
            <Save className="mr-1 h-4 w-4" /> Salvar
          </Button>
          <Button size="sm" onClick={gerarRoteiro}>
            <Sparkles className="mr-1 h-4 w-4" /> Gerar roteiro
          </Button>
        </>
      }
    >
      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge {...ideaStatusLabel[draft.status]} />
            <StatusBadge {...prioridadeLabel[draft.prioridade]} />
            <span className="text-xs text-muted-foreground">{familiaLabel[draft.familia]}</span>
          </div>
          <div className="rounded-xl border bg-card p-4 shadow-sm">
            <div className="grid gap-3">
              <div>
                <Label className="text-xs">Titulo</Label>
                <Input value={draft.titulo} onChange={(e) => set("titulo", e.target.value)} />
              </div>
              <div>
                <Label className="text-xs">Hook</Label>
                <Textarea
                  rows={2}
                  value={draft.hook}
                  onChange={(e) => set("hook", e.target.value)}
                />
              </div>
              <div>
                <Label className="text-xs">Angulo</Label>
                <Textarea
                  rows={3}
                  value={draft.angulo}
                  onChange={(e) => set("angulo", e.target.value)}
                />
              </div>
              <div>
                <Label className="text-xs">CTA</Label>
                <Textarea rows={2} value={draft.cta} onChange={(e) => set("cta", e.target.value)} />
              </div>
              <div>
                <Label className="text-xs">Observacao de compliance</Label>
                <Textarea
                  rows={3}
                  value={draft.observacaoCompliance}
                  onChange={(e) => set("observacaoCompliance", e.target.value)}
                />
              </div>
            </div>
          </div>
        </div>

        <CompliancePanel
          fields={{
            titulo: draft.titulo,
            hook: draft.hook,
            angulo: draft.angulo,
            cta: draft.cta,
            observacao: draft.observacaoCompliance,
          }}
          palavrasProibidas={palavras}
        />
      </div>
    </AppShell>
  );
}
