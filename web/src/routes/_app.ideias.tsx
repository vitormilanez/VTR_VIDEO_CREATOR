import { createFileRoute, Link, Outlet, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { DataToolbar } from "@/components/data-toolbar";
import { EmptyState } from "@/components/empty-state";
import { StatusChips } from "@/components/status-chips";
import { WithTooltip } from "@/components/with-tooltip";
import { ConfirmAction } from "@/components/confirm-action";
import { buildScriptFromIdea } from "@/lib/script-builder";
import { familiaLabel, ideaStatusLabel, prioridadeLabel } from "@/lib/status";
import { genId, useStore } from "@/lib/store";
import { appendIdea, appendScript, expandIdeas, setSheetStatus } from "@/lib/api/local";
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
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  CircleCheck,
  ExternalLink,
  FileText,
  Lightbulb,
  Loader2,
  Plus,
  Sparkles,
  Trash2,
  Wand2,
} from "lucide-react";
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
  component: IdeiasLayout,
});

const familias: ThemeFamily[] = [
  "medicamento",
  "comportamento",
  "metabolismo",
  "obesidade",
  "educativo",
];

function IdeiasLayout() {
  return <Outlet />;
}

export function IdeiasPage() {
  const ideas = useStore((s) => s.ideas);
  const scripts = useStore((s) => s.scripts);
  const videoJobs = useStore((s) => s.videoJobs);
  const addIdea = useStore((s) => s.addIdea);
  const updateIdea = useStore((s) => s.updateIdea);
  const addScript = useStore((s) => s.addScript);
  const navigate = useNavigate();

  const [familia, setFamilia] = useState("todas");
  const [status, setStatus] = useState("todos");
  const [prioridade, setPrioridade] = useState("todas");
  const [busca, setBusca] = useState("");
  const [preview, setPreview] = useState<Idea | null>(null);
  const [manualOpen, setManualOpen] = useState(false);
  const [manualSeed, setManualSeed] = useState("");
  const [manualFamilia, setManualFamilia] = useState<ThemeFamily>("educativo");
  const [manualPrioridade, setManualPrioridade] = useState<Idea["prioridade"]>("media");
  const [manualIdeas, setManualIdeas] = useState<Idea[]>([]);
  const [isExpanding, setIsExpanding] = useState(false);
  const [savingIdeaId, setSavingIdeaId] = useState<string | null>(null);

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

  function scriptForIdea(idea: Idea) {
    const normalizedHook = idea.hook.trim().toLowerCase();
    return scripts.find(
      (script) =>
        script.ideaId === idea.id ||
        (normalizedHook && script.hook.trim().toLowerCase() === normalizedHook),
    );
  }

  function videoForScript(scriptId: string) {
    return videoJobs.find((job) => job.scriptId === scriptId && job.status !== "erro");
  }

  const usedIdeas = ideas.filter((idea) => Boolean(scriptForIdea(idea)));
  const previewScript = preview ? scriptForIdea(preview) : undefined;
  const previewVideo = previewScript ? videoForScript(previewScript.id) : undefined;

  async function gerarRoteiro(i: Idea) {
    const script = buildScriptFromIdea(i, genId("s"));
    try {
      const saved = await appendScript(script);
      addScript(saved);
      updateIdea(i.id, { status: "aprovado" });
      try {
        await setSheetStatus("ideias", i.id, "aprovado");
      } catch {
        toast.warning("Roteiro salvo, mas o status da ideia nao foi atualizado.");
      }
      toast.success("Roteiro criado e salvo no Sheets.");
      navigate({ to: "/roteiros/$id", params: { id: saved.id } });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Nao foi possivel criar o roteiro.");
    }
  }

  async function explorarIdeiaManual() {
    const seed = manualSeed.trim();
    if (seed.length < 8) {
      toast.error("Escreva um pouco mais sobre a ideia.");
      return;
    }
    setIsExpanding(true);
    try {
      const expanded = await expandIdeas({
        seed,
        quantity: 3,
        familia: manualFamilia,
        prioridade: manualPrioridade,
      });
      setManualIdeas(expanded);
      toast.success("Ideias exploradas. Escolha uma para virar roteiro.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Nao foi possivel explorar a ideia.");
    } finally {
      setIsExpanding(false);
    }
  }

  async function salvarIdeiaERoteiro(idea: Idea) {
    setSavingIdeaId(idea.id);
    try {
      const savedIdea = await appendIdea(idea);
      addIdea(savedIdea);
      const script = buildScriptFromIdea(savedIdea, genId("s"));
      const savedScript = await appendScript(script);
      addScript(savedScript);
      updateIdea(savedIdea.id, { status: "aprovado" });
      try {
        await setSheetStatus("ideias", savedIdea.id, "aprovado");
      } catch {
        toast.warning("Roteiro salvo, mas o status da ideia nao foi atualizado.");
      }
      setManualOpen(false);
      setManualSeed("");
      setManualIdeas([]);
      toast.success("Ideia contextualizada e roteiro criado.");
      navigate({ to: "/roteiros/$id", params: { id: savedScript.id } });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Nao foi possivel criar o roteiro.");
    } finally {
      setSavingIdeaId(null);
    }
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
    <AppShell
      title="Ideias"
      actions={
        <Dialog open={manualOpen} onOpenChange={setManualOpen}>
          <DialogTrigger asChild>
            <Button size="sm">
              <Plus className="mr-1 h-4 w-4" /> Nova ideia
            </Button>
          </DialogTrigger>
          <NovaIdeiaDialog
            seed={manualSeed}
            onSeedChange={(value) => {
              setManualSeed(value);
              if (manualIdeas.length) setManualIdeas([]);
            }}
            familia={manualFamilia}
            onFamiliaChange={setManualFamilia}
            prioridade={manualPrioridade}
            onPrioridadeChange={setManualPrioridade}
            ideas={manualIdeas}
            isExpanding={isExpanding}
            savingIdeaId={savingIdeaId}
            onExpand={explorarIdeiaManual}
            onCreateScript={salvarIdeiaERoteiro}
          />
        </Dialog>
      }
    >
      {usedIdeas.length > 0 ? (
        <div className="mb-3 flex items-center gap-2 rounded-md border border-status-info/30 bg-status-info/5 px-3 py-2 text-xs">
          <CircleCheck className="h-4 w-4 shrink-0 text-status-info" />
          <span>
            {usedIdeas.length}{" "}
            {usedIdeas.length === 1 ? "ideia já virou roteiro" : "ideias já viraram roteiros"}. As
            ideias utilizadas estão identificadas e abrem o roteiro existente.
          </span>
        </div>
      ) : null}
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
              <SelectItem key={f} value={f}>
                {familiaLabel[f]}
              </SelectItem>
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
              {ordered.map((i) => {
                const usedScript = scriptForIdea(i);
                const producedVideo = usedScript ? videoForScript(usedScript.id) : undefined;
                return (
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
                        {usedScript ? (
                          <Badge
                            variant="outline"
                            className="h-5 border-status-info/40 px-1.5 text-[10px] text-status-info"
                          >
                            {producedVideo ? (
                              <CircleCheck className="mr-1 h-3 w-3" />
                            ) : (
                              <FileText className="mr-1 h-3 w-3" />
                            )}
                            {producedVideo ? "Vídeo produzido" : "Roteiro criado"}
                          </Badge>
                        ) : null}
                      </div>
                    </TableCell>
                    <TableCell className="text-sm">{i.hook}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {i.publicoDor || "—"}
                    </TableCell>
                    <TableCell>
                      <StatusBadge {...prioridadeLabel[i.prioridade]} />
                    </TableCell>
                    <TableCell>
                      <StatusBadge {...ideaStatusLabel[i.status]} />
                    </TableCell>
                    <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex justify-end gap-1">
                        {usedScript ? (
                          <WithTooltip label="Abrir roteiro já criado">
                            <Button size="sm" variant="secondary" asChild>
                              <Link to="/roteiros/$id" params={{ id: usedScript.id }}>
                                <ExternalLink className="mr-1 h-3.5 w-3.5" /> Ver roteiro
                              </Link>
                            </Button>
                          </WithTooltip>
                        ) : (
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
                        )}
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
                );
              })}
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
              {preview.publicoDor ? (
                <Block label="Publico / Dor" text={preview.publicoDor} />
              ) : null}
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
                {previewScript ? (
                  <>
                    <div className="rounded-md border border-status-info/30 bg-status-info/5 px-3 py-2 text-xs">
                      {previewVideo
                        ? "Esta ideia já possui roteiro e vídeo produzido."
                        : "Esta ideia já possui um roteiro criado."}
                    </div>
                    <Button asChild size="sm">
                      <Link to="/roteiros/$id" params={{ id: previewScript.id }}>
                        <ExternalLink className="mr-1 h-4 w-4" /> Abrir roteiro existente
                      </Link>
                    </Button>
                  </>
                ) : (
                  <Button
                    size="sm"
                    disabled={preview.status === "descartado"}
                    onClick={() => {
                      gerarRoteiro(preview);
                      setPreview(null);
                    }}
                  >
                    <Sparkles className="mr-1 h-4 w-4" /> Gerar roteiro
                  </Button>
                )}
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

function NovaIdeiaDialog({
  seed,
  onSeedChange,
  familia,
  onFamiliaChange,
  prioridade,
  onPrioridadeChange,
  ideas,
  isExpanding,
  savingIdeaId,
  onExpand,
  onCreateScript,
}: {
  seed: string;
  onSeedChange: (value: string) => void;
  familia: ThemeFamily;
  onFamiliaChange: (value: ThemeFamily) => void;
  prioridade: Idea["prioridade"];
  onPrioridadeChange: (value: Idea["prioridade"]) => void;
  ideas: Idea[];
  isExpanding: boolean;
  savingIdeaId: string | null;
  onExpand: () => void;
  onCreateScript: (idea: Idea) => void;
}) {
  return (
    <DialogContent className="max-h-[88vh] max-w-3xl overflow-y-auto">
      <DialogHeader>
        <DialogTitle>Nova ideia</DialogTitle>
      </DialogHeader>

      <div className="grid gap-4">
        <div className="grid gap-2">
          <div className="flex items-center justify-between gap-3">
            <Label>Escreva a ideia bruta</Label>
            <span className="text-xs text-muted-foreground">{seed.length}/10000</span>
          </div>
          <Textarea
            rows={5}
            maxLength={10000}
            value={seed}
            onChange={(e) => onSeedChange(e.target.value)}
            placeholder="Ex: Quero falar que emagrecer com remédio sem mudar rotina faz a pessoa voltar para os mesmos hábitos depois..."
          />
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div className="grid gap-2">
            <Label>Família</Label>
            <Select value={familia} onValueChange={(value) => onFamiliaChange(value as ThemeFamily)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {familias.map((f) => (
                  <SelectItem key={f} value={f}>
                    {familiaLabel[f]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label>Prioridade</Label>
            <Select
              value={prioridade}
              onValueChange={(value) => onPrioridadeChange(value as Idea["prioridade"])}
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
          </div>
        </div>

        <Button onClick={onExpand} disabled={isExpanding || seed.trim().length < 8}>
          {isExpanding ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Wand2 className="mr-2 h-4 w-4" />
          )}
          Explorar com IA
        </Button>

        {ideas.length > 0 ? (
          <div className="grid gap-3">
            <div>
              <h3 className="font-display text-sm font-semibold">Sugestões prontas para roteiro</h3>
              <p className="text-xs text-muted-foreground">
                Escolha a melhor. Ela será salva em Ideias e já abrirá o roteiro.
              </p>
            </div>
            {ideas.map((idea) => (
              <div key={idea.id} className="rounded-lg border bg-card p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="font-semibold">{idea.titulo}</div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                        {familiaLabel[idea.familia]}
                      </span>
                      <StatusBadge {...prioridadeLabel[idea.prioridade]} />
                    </div>
                  </div>
                  <Button
                    size="sm"
                    onClick={() => onCreateScript(idea)}
                    disabled={Boolean(savingIdeaId)}
                  >
                    {savingIdeaId === idea.id ? (
                      <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Sparkles className="mr-1 h-3.5 w-3.5" />
                    )}
                    Criar roteiro
                  </Button>
                </div>
                <Block label="Hook" text={idea.hook} />
                <Block label="Contexto" text={idea.angulo} />
                {idea.publicoDor ? <Block label="Público / Dor" text={idea.publicoDor} /> : null}
                <Block label="Compliance" text={idea.observacaoCompliance} />
              </div>
            ))}
          </div>
        ) : null}
      </div>

      <DialogFooter>
        <p className="text-xs text-muted-foreground">
          O roteiro final continua passando pelas regras de conteúdo educativo e não prescritivo.
        </p>
      </DialogFooter>
    </DialogContent>
  );
}
