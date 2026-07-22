import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { DataToolbar } from "@/components/data-toolbar";
import { EmptyState } from "@/components/empty-state";
import { StatusChips } from "@/components/status-chips";
import { WithTooltip } from "@/components/with-tooltip";
import { ConfirmAction } from "@/components/confirm-action";
import {
  familiaLabel,
  ideaStatusLabel,
  prioridadeLabel,
} from "@/lib/status";
import { genId, useStore } from "@/lib/store";
import { setSheetStatus } from "@/lib/api/local";
import type { Idea, IdeaStatus, ThemeFamily } from "@/lib/mock-data";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { ExternalLink, Lightbulb, Sparkles, Trash2 } from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute("/_app/ideias")({
  head: () => ({
    meta: [
      { title: "Ideias | AI Video Creator" },
      { name: "description", content: "Ideias editoriais em portugues-BR." },
      { property: "og:title", content: "Ideias | AI Video Creator" },
      { property: "og:description", content: "Funil de ideias educativas." },
    ],
  }),
  component: IdeiasPage,
});

const familias: ThemeFamily[] = [
  "medicamento",
  "comportamento",
  "metabolismo",
  "obesidade",
  "educativo",
];

function IdeiasPage() {
  const ideas = useStore((s) => s.ideas);
  const updateIdea = useStore((s) => s.updateIdea);
  const addScript = useStore((s) => s.addScript);
  const navigate = useNavigate();

  const [familia, setFamilia] = useState("todas");
  const [status, setStatus] = useState("todos");
  const [prioridade, setPrioridade] = useState("todas");
  const [busca, setBusca] = useState("");
  const [preview, setPreview] = useState<Idea | null>(null);

  const filtered = ideas.filter((i) => {
    if (familia !== "todas" && i.familia !== familia) return false;
    if (status !== "todos" && i.status !== status) return false;
    if (prioridade !== "todas" && i.prioridade !== prioridade) return false;
    if (busca && !i.titulo.toLowerCase().includes(busca.toLowerCase())) return false;
    return true;
  });

  // Ideia mais recente sempre no topo.
  const ordered = [...filtered].sort(
    (a, b) => new Date(b.criadoEm).getTime() - new Date(a.criadoEm).getTime(),
  );

  const counts: Record<IdeaStatus, number> = { novo: 0, em_analise: 0, aprovado: 0, descartado: 0 };
  ideas.forEach((i) => (counts[i.status] += 1));

  function gerarRoteiro(i: Idea) {
    const id = genId("s");
    addScript({
      id,
      ideaId: i.id,
      categoria: i.familia,
      tema: i.titulo,
      titulo: i.titulo,
      hook: i.hook,
      dorConflito:
        i.publicoDor || "Rascunho: descrever a dor/conflito do publico sem sensacionalismo.",
      explicacaoSimples: i.angulo
        ? `Angulo: ${i.angulo}. Explicar o tema sem prescrever nem citar doses.`
        : "Rascunho: explicar o tema sem prescrever nem citar doses.",
      virada: "Rascunho: virada educativa reforcando avaliacao individual.",
      cta: i.cta,
      cuidadosMedicos:
        i.observacaoCompliance ||
        "Nao prescrever. Nao citar doses. Nao prometer resultado.",
      risco: i.familia === "medicamento" ? "alto" : "medio",
      prioridade: i.prioridade,
      formatoSugerido: i.tipo || "Reels",
      status: "aguardando_validacao",
      criadoEm: new Date().toISOString(),
    });
    updateIdea(i.id, { status: "aprovado" });
    toast.success("Roteiro criado como rascunho.");
    navigate({ to: "/roteiros/$id", params: { id } });
  }

  async function descartarIdeia(i: Idea) {
    updateIdea(i.id, { status: "descartado" });
    try {
      await setSheetStatus("ideias", i.id, "descartado");
      toast.success("Ideia descartada e sincronizada com o Sheets.");
    } catch (err) {
      updateIdea(i.id, { status: i.status });
      toast.error(err instanceof Error ? err.message : "Falha ao sincronizar.");
    }
  }

  return (
    <AppShell title="Ideias">
      <StatusChips
        className="mb-3"
        value={status}
        onChange={setStatus}
        options={[
          { value: "novo", label: "Novas", tone: "info", count: counts.novo },
          { value: "em_analise", label: "Em analise", tone: "warn", count: counts.em_analise },
          { value: "aprovado", label: "Aprovadas", tone: "success", count: counts.aprovado },
          { value: "descartado", label: "Descartadas", tone: "neutral", count: counts.descartado },
        ]}
      />
      <DataToolbar search={busca} onSearch={setBusca} placeholder="Buscar ideia...">
        <Select value={familia} onValueChange={setFamilia}>
          <SelectTrigger className="h-8 w-44">
            <SelectValue placeholder="Familia" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="todas">Todas as familias</SelectItem>
            {familias.map((f) => (
              <SelectItem key={f} value={f}>{familiaLabel[f]}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={prioridade} onValueChange={setPrioridade}>
          <SelectTrigger className="h-8 w-40">
            <SelectValue placeholder="Prioridade" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="todas">Todas as prioridades</SelectItem>
            <SelectItem value="alta">Alta</SelectItem>
            <SelectItem value="media">Media</SelectItem>
            <SelectItem value="baixa">Baixa</SelectItem>
          </SelectContent>
        </Select>
      </DataToolbar>

      {filtered.length === 0 ? (
        <EmptyState
          icon={<Lightbulb className="h-4 w-4" />}
          title="Nenhuma ideia encontrada"
          description="Capture tendencias no Radar para gerar novas ideias."
          action={
            <Button asChild size="sm" variant="secondary">
              <Link to="/radar">Ir para Radar</Link>
            </Button>
          }
        />
      ) : (
        <div className="rounded-xl border bg-card shadow-sm">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[24%]">Tema</TableHead>
                <TableHead className="w-[28%]">Hook</TableHead>
                <TableHead>Publico / Dor</TableHead>
                <TableHead>Prioridade</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Acoes</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ordered.map((i) => (
                <TableRow key={i.id} className="cursor-pointer" onClick={() => setPreview(i)}>
                  <TableCell>
                    <div className="font-medium">{i.titulo}</div>
                    <div className="mt-1 flex flex-wrap items-center gap-1">
                      <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                        {familiaLabel[i.familia]}
                      </span>
                      {i.tipo ? (
                        <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                          {i.tipo}
                        </span>
                      ) : null}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">{i.hook}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {i.publicoDor || "—"}
                  </TableCell>
                  <TableCell><StatusBadge {...prioridadeLabel[i.prioridade]} /></TableCell>
                  <TableCell><StatusBadge {...ideaStatusLabel[i.status]} /></TableCell>
                  <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                    <div className="flex justify-end gap-1">
                      <WithTooltip label="Gerar roteiro a partir da ideia">
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={i.status === "descartado"}
                          onClick={() => gerarRoteiro(i)}
                        >
                          <Sparkles className="mr-1 h-3.5 w-3.5" /> Roteiro
                        </Button>
                      </WithTooltip>
                      <ConfirmAction
                        destructive
                        title="Descartar ideia?"
                        description="Voce podera restaurar mudando o status manualmente."
                        confirmLabel="Descartar"
                        onConfirm={() => descartarIdeia(i)}
                        trigger={
                          <WithTooltip label="Descartar ideia">
                            <Button size="sm" variant="ghost">
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </WithTooltip>
                        }
                      />
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Sheet open={!!preview} onOpenChange={(o) => !o && setPreview(null)}>
        <SheetContent side="right" className="w-full sm:max-w-md">
          {preview && (
            <>
              <SheetHeader>
                <SheetTitle>{preview.titulo}</SheetTitle>
                <SheetDescription>Preview da ideia.</SheetDescription>
              </SheetHeader>
              <div className="mt-4 flex flex-wrap gap-2">
                <StatusBadge {...ideaStatusLabel[preview.status]} />
                <StatusBadge {...prioridadeLabel[preview.prioridade]} />
                <span className="text-xs text-muted-foreground">
                  {familiaLabel[preview.familia]}
                </span>
              </div>
              <Block label="Hook" text={preview.hook} />
              {preview.publicoDor ? <Block label="Publico / Dor" text={preview.publicoDor} /> : null}
              <Block label="Angulo" text={preview.angulo} />
              <Block label="CTA" text={preview.cta} />
              {preview.observacaoCompliance ? (
                <Block label="Compliance" text={preview.observacaoCompliance} />
              ) : null}
              {preview.linkOrigem ? (
                <a
                  href={preview.linkOrigem}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-3 inline-flex items-center gap-1 text-sm text-status-info hover:underline"
                >
                  <ExternalLink className="h-3.5 w-3.5" /> Link de origem
                </a>
              ) : null}
              <div className="mt-6 flex flex-col gap-2">
                <Button
                  size="sm"
                  disabled={preview.status === "descartado"}
                  onClick={() => { gerarRoteiro(preview); setPreview(null); }}
                >
                  <Sparkles className="mr-1 h-4 w-4" /> Gerar roteiro
                </Button>
                <Button asChild size="sm" variant="secondary">
                  <Link to="/ideias/$id" params={{ id: preview.id }}>
                    <ExternalLink className="mr-1 h-4 w-4" /> Abrir tela completa
                  </Link>
                </Button>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </AppShell>
  );
}

function Block({ label, text }: { label: string; text: string }) {
  return (
    <div className="mt-3">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <p className="mt-0.5 text-sm">{text}</p>
    </div>
  );
}
