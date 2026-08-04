import { createFileRoute, Link, Outlet, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { DataToolbar } from "@/components/data-toolbar";
import { EmptyState } from "@/components/empty-state";
import { NextStepBanner } from "@/components/next-step-banner";
import { StatusChips } from "@/components/status-chips";
import { WithTooltip } from "@/components/with-tooltip";
import { ConfirmAction } from "@/components/confirm-action";
import { ToneSelectDialog } from "@/components/tone-select-dialog";
import { CaptureScriptChoices } from "@/components/capture-script-choices";
import { evaluateIdeaQuality } from "@/lib/idea-quality";
import {
  generateAndPersistCaptureScripts,
  generateAndPersistScript,
} from "@/lib/script-generation";
import { DEFAULT_OUTRO } from "@/lib/script-quality";
import { familiaLabel, ideaStatusLabel, prioridadeLabel } from "@/lib/status";
import { useStore } from "@/lib/store";
import {
  analyzeArticle,
  expandIdeas,
  saveScript,
  setSheetStatus,
  type ArticleAnalysis,
  type ArticleIdeasResult,
} from "@/lib/api/local";
import type { EditorialTone, Idea, IdeaStatus, Script, ThemeFamily } from "@/lib/mock-data";
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
import { Input } from "@/components/ui/input";
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
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
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
  const updateScript = useStore((s) => s.updateScript);
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
  const [articleOpen, setArticleOpen] = useState(false);
  const [articleText, setArticleText] = useState("");
  const [articleUrl, setArticleUrl] = useState("");
  const [articleFamilia, setArticleFamilia] = useState<ThemeFamily>("medicamento");
  const [articlePrioridade, setArticlePrioridade] = useState<Idea["prioridade"]>("alta");
  const [articleResult, setArticleResult] = useState<ArticleIdeasResult | null>(null);
  const [isAnalyzingArticle, setIsAnalyzingArticle] = useState(false);

  // Escolha do tom editorial: abre depois que o usuario define a ideia e
  // ANTES da chamada paga que gera o roteiro final com a IA.
  const [tonePending, setTonePending] = useState<{
    idea: Idea;
    analysis?: ArticleAnalysis | null;
    persistIdea: boolean;
  } | null>(null);
  const [editorialTone, setEditorialTone] = useState<EditorialTone>("neutro");
  const [scriptDuration, setScriptDuration] = useState<10 | 15 | 30 | 45 | 60>(45);
  const [scriptOutro, setScriptOutro] = useState(DEFAULT_OUTRO);
  const [isGeneratingScript, setIsGeneratingScript] = useState(false);
  const [captureChoices, setCaptureChoices] = useState<Script[]>([]);

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
  const pendingIdeas = ordered.filter(
    (idea) => !scriptForIdea(idea) && idea.status !== "descartado",
  );
  const nextIdea = pendingIdeas[0];
  const savingIdeaId = isGeneratingScript ? (tonePending?.idea.id ?? null) : null;
  const previewScript = preview ? scriptForIdea(preview) : undefined;
  const previewVideo = previewScript ? videoForScript(previewScript.id) : undefined;

  /** Ideia ja salva no Sheets: so falta escolher o tom e gerar o roteiro. */
  function gerarRoteiro(i: Idea) {
    const quality = evaluateIdeaQuality(i);
    if (!quality.ready) {
      toast.error(`Ideia ainda precisa de contexto (${quality.score}/100): ${quality.issues[0]}`);
      setPreview(i);
      return;
    }
    abrirEscolhaDeTom(i, { persistIdea: false });
  }

  /** Abre o dialogo de tom editorial antes de qualquer geracao paga. */
  function abrirEscolhaDeTom(
    idea: Idea,
    options: { persistIdea: boolean; analysis?: ArticleAnalysis | null } = { persistIdea: false },
  ) {
    setEditorialTone("neutro");
    setScriptDuration(45);
    setScriptOutro(DEFAULT_OUTRO);
    setTonePending({ idea, analysis: options.analysis ?? null, persistIdea: options.persistIdea });
  }

  /** Chamada apos o usuario confirmar o tom: unica chamada paga ao Claude. */
  async function confirmarTomEGerarRoteiro() {
    if (!tonePending) return;
    setIsGeneratingScript(true);
    try {
      if (scriptDuration <= 15) {
        const {
          idea: savedIdea,
          scripts: captureScripts,
          provider,
        } = await generateAndPersistCaptureScripts({
          idea: tonePending.idea,
          persistIdea: tonePending.persistIdea,
          durationSeconds: scriptDuration as 10 | 15,
        });
        if (tonePending.persistIdea) addIdea(savedIdea);
        captureScripts.forEach(addScript);
        updateIdea(savedIdea.id, { status: "aprovado" });
        setTonePending(null);
        setManualOpen(false);
        setArticleOpen(false);
        setCaptureChoices(captureScripts);
        toast[provider === "fallback" ? "warning" : "success"](
          provider === "fallback"
            ? "Claude indisponível. Três hooks locais foram salvos."
            : `Claude gerou e salvou os 3 hooks de ${scriptDuration} segundos.`,
        );
        return;
      }
      const {
        idea: savedIdea,
        script,
        provider,
      } = await generateAndPersistScript({
        idea: tonePending.idea,
        articleAnalysis: tonePending.analysis,
        editorialTone,
        durationSeconds: scriptDuration,
        outro: scriptDuration === 10 ? "" : scriptOutro.trim() || DEFAULT_OUTRO,
        persistIdea: tonePending.persistIdea,
      });
      if (tonePending.persistIdea) {
        addIdea(savedIdea);
      }
      addScript(script);
      updateIdea(savedIdea.id, { status: "aprovado" });
      try {
        await setSheetStatus("ideias", savedIdea.id, "aprovado");
      } catch {
        toast.warning("Roteiro salvo, mas o status da ideia nao foi atualizado.");
      }
      setTonePending(null);
      setManualOpen(false);
      setArticleOpen(false);
      setManualSeed("");
      setManualIdeas([]);
      if (provider === "fallback") {
        toast.warning("Claude indisponível. Roteiro local criado sem consumo de tokens.");
      } else {
        toast.success("Roteiro gerado com IA e salvo no Sheets.");
      }
      navigate({ to: "/roteiros/$id", params: { id: script.id } });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Nao foi possivel gerar o roteiro.");
    } finally {
      setIsGeneratingScript(false);
    }
  }

  async function confirmarRoteirosDeCaptura(selected: Script[]) {
    try {
      const updated = await Promise.all(
        selected.map((script) => saveScript({ ...script, status: "em_revisao" })),
      );
      updated.forEach((script) => updateScript(script.id, script));
      setCaptureChoices([]);
      toast.success(
        `${updated.length} ${updated.length === 1 ? "roteiro selecionado" : "roteiros selecionados"} para produção.`,
      );
      navigate({ to: "/roteiros/$id", params: { id: updated[0].id } });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Não foi possível salvar a seleção.");
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

  async function analisarArtigo() {
    const article = articleText.trim();
    if (article.length < 120) {
      toast.error("Cole um trecho maior do artigo para a análise fazer sentido.");
      return;
    }
    setArticleResult(null);
    setIsAnalyzingArticle(true);
    try {
      const result = await analyzeArticle({
        article,
        sourceUrl: articleUrl.trim() || null,
        quantity: 5,
        familia: articleFamilia,
        prioridade: articlePrioridade,
      });
      setArticleResult(result);
      toast.success("Artigo analisado. Revise os limites antes de criar roteiro.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Nao foi possivel analisar o artigo.");
    } finally {
      setIsAnalyzingArticle(false);
    }
  }

  /**
   * Ideia ainda nao salva (sugestao vinda de artigo ou de ideia manual): abre
   * a escolha de tom primeiro. A ideia so e persistida quando o tom for
   * confirmado, junto com o roteiro, em uma unica chamada paga.
   */
  function salvarIdeiaERoteiro(idea: Idea) {
    const quality = evaluateIdeaQuality(idea);
    if (!quality.ready) {
      toast.error(`Ideia ainda precisa de contexto (${quality.score}/100): ${quality.issues[0]}`);
      return;
    }
    abrirEscolhaDeTom(idea, {
      persistIdea: true,
      analysis: articleOpen ? articleResult?.analysis : null,
    });
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
        <div className="flex flex-wrap gap-2">
          <Dialog open={articleOpen} onOpenChange={setArticleOpen}>
            <DialogTrigger asChild>
              <Button size="sm" variant="secondary">
                <FileText className="mr-1 h-4 w-4" /> Importar artigo
              </Button>
            </DialogTrigger>
            <ArticleImportDialog
              article={articleText}
              onArticleChange={(value) => {
                setArticleText(value);
                if (articleResult) setArticleResult(null);
              }}
              sourceUrl={articleUrl}
              onSourceUrlChange={setArticleUrl}
              familia={articleFamilia}
              onFamiliaChange={setArticleFamilia}
              prioridade={articlePrioridade}
              onPrioridadeChange={setArticlePrioridade}
              result={articleResult}
              isAnalyzing={isAnalyzingArticle}
              savingIdeaId={savingIdeaId}
              onAnalyze={analisarArtigo}
              onCreateScript={salvarIdeiaERoteiro}
              onClear={() => {
                setArticleText("");
                setArticleUrl("");
                setArticleResult(null);
              }}
            />
          </Dialog>
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
              onClear={() => {
                setManualSeed("");
                setManualIdeas([]);
              }}
            />
          </Dialog>
        </div>
      }
    >
      <NextStepBanner
        className="mb-3"
        title={
          nextIdea
            ? `Transformar "${nextIdea.titulo}" em roteiro`
            : "Criar uma nova ideia para alimentar a esteira"
        }
        description={
          nextIdea
            ? "Esta é a ideia mais recente ainda sem roteiro. Gere o roteiro ou abra a ideia para revisar antes."
            : "Importe um artigo, cole uma ideia bruta ou volte ao Radar para capturar novos temas."
        }
        actionLabel={nextIdea ? "Criar roteiro" : "Importar artigo"}
        onAction={nextIdea ? () => void gerarRoteiro(nextIdea) : () => setArticleOpen(true)}
        meta={
          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            <span className="rounded-full bg-background px-2.5 py-1">
              {pendingIdeas.length} sem roteiro
            </span>
            <span className="rounded-full bg-background px-2.5 py-1">
              {usedIdeas.length} já viraram roteiro
            </span>
            <span className="rounded-full bg-background px-2.5 py-1">
              {ideas.length} ideias no total
            </span>
          </div>
        }
      />
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
              {ordered.map((i, index) => {
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
                        {index === 0 ? (
                          <Badge
                            variant="outline"
                            className="h-5 border-status-info/30 bg-status-info/5 px-1.5 text-[10px] text-status-info"
                          >
                            Mais recente
                          </Badge>
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
                              disabled={i.status === "descartado" || !evaluateIdeaQuality(i).ready}
                              onClick={() => gerarRoteiro(i)}
                            >
                              <Sparkles className="mr-1 h-3.5 w-3.5" /> Criar roteiro
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
                <IdeaQualityBadge idea={preview} />
              </div>
              <Block label="Hook" text={preview.hook} />
              {preview.publicoDor ? (
                <Block label="Publico / Dor" text={preview.publicoDor} />
              ) : null}
              <Block label="Angulo" text={preview.angulo} />
              <Block label="CTA" text={preview.cta} />
              {!evaluateIdeaQuality(preview).ready ? (
                <div className="mt-4 rounded-md border border-status-warn/30 bg-status-warn/10 px-3 py-2 text-xs leading-5 text-status-warn-foreground">
                  <div className="font-semibold">Revise antes de criar o roteiro</div>
                  <ul className="mt-1 list-disc pl-4">
                    {evaluateIdeaQuality(preview).issues.map((issue) => (
                      <li key={issue}>{issue}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
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
                    disabled={
                      preview.status === "descartado" || !evaluateIdeaQuality(preview).ready
                    }
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

      <ToneSelectDialog
        open={Boolean(tonePending)}
        onOpenChange={(open) => !open && setTonePending(null)}
        ideaTitle={tonePending?.idea.titulo ?? ""}
        tone={editorialTone}
        onToneChange={setEditorialTone}
        durationSeconds={scriptDuration}
        onDurationChange={setScriptDuration}
        outro={scriptOutro}
        onOutroChange={setScriptOutro}
        isGenerating={isGeneratingScript}
        onConfirm={() => void confirmarTomEGerarRoteiro()}
      />
      <CaptureScriptChoices
        scripts={captureChoices}
        onOpenChange={(open) => !open && setCaptureChoices([])}
        onConfirm={confirmarRoteirosDeCaptura}
      />
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

function ArticleImportDialog({
  article,
  onArticleChange,
  sourceUrl,
  onSourceUrlChange,
  familia,
  onFamiliaChange,
  prioridade,
  onPrioridadeChange,
  result,
  isAnalyzing,
  savingIdeaId,
  onAnalyze,
  onCreateScript,
  onClear,
}: {
  article: string;
  onArticleChange: (value: string) => void;
  sourceUrl: string;
  onSourceUrlChange: (value: string) => void;
  familia: ThemeFamily;
  onFamiliaChange: (value: ThemeFamily) => void;
  prioridade: Idea["prioridade"];
  onPrioridadeChange: (value: Idea["prioridade"]) => void;
  result: ArticleIdeasResult | null;
  isAnalyzing: boolean;
  savingIdeaId: string | null;
  onAnalyze: () => void;
  onCreateScript: (idea: Idea) => void;
  onClear: () => void;
}) {
  return (
    <DialogContent className="max-h-[88vh] max-w-5xl overflow-y-auto">
      <DialogHeader>
        <DialogTitle>Importar artigo</DialogTitle>
        <p className="text-sm text-muted-foreground">
          Transforme evidência em uma ideia clara, com os limites clínicos preservados.
        </p>
      </DialogHeader>

      <div className="grid gap-4">
        <div className="grid gap-2">
          <div className="flex items-center justify-between gap-3">
            <Label>Cole artigo, resumo, abstract, link ou DOI</Label>
            <span className="text-xs text-muted-foreground">{article.length}/50000</span>
          </div>
          <Textarea
            rows={7}
            maxLength={50000}
            value={article}
            onChange={(event) => onArticleChange(event.target.value)}
            placeholder="Cole aqui o abstract, highlights, discussão ou o texto completo do artigo..."
          />
        </div>

        <div className="grid gap-3 md:grid-cols-[1.3fr_0.8fr_0.8fr]">
          <div className="grid gap-2">
            <Label>Link, DOI ou PubMed</Label>
            <Input
              value={sourceUrl}
              onChange={(event) => onSourceUrlChange(event.target.value)}
              placeholder="https://doi.org/... ou PMID..."
            />
          </div>
          <div className="grid gap-2">
            <Label>Família</Label>
            <Select
              value={familia}
              onValueChange={(value) => onFamiliaChange(value as ThemeFamily)}
            >
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

        <div className="flex flex-wrap items-center justify-between gap-2">
          <Button onClick={onAnalyze} disabled={isAnalyzing || article.trim().length < 120}>
            {isAnalyzing ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <FileText className="mr-2 h-4 w-4" />
            )}
            Analisar artigo
          </Button>
          {(article || sourceUrl || result) && (
            <Button size="sm" variant="ghost" onClick={onClear}>
              Limpar artigo
            </Button>
          )}
        </div>

        {result ? (
          <div className="grid gap-4">
            <div className="rounded-lg border border-status-info/30 bg-status-info/5 p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h3 className="font-display text-sm font-semibold">Resumo do artigo</h3>
                  <p className="text-xs text-muted-foreground">
                    A leitura usada para construir a ideia, antes de chegar ao avatar.
                  </p>
                </div>
                <Badge variant="outline" className="text-[10px]">
                  {result.provider === "claude" ? "Analisado por IA" : "Análise local"}
                </Badge>
              </div>
              <p className="mt-3 text-sm leading-6">{result.analysis.achadoPrincipal}</p>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <ArticleFact label="Tipo de estudo" value={result.analysis.tipoEstudo} />
                <ArticleFact label="População" value={result.analysis.populacao} />
              </div>
              <Accordion type="single" collapsible className="mt-2 border-t border-status-info/20">
                <AccordionItem value="detalhes" className="border-b-0">
                  <AccordionTrigger className="py-3 text-xs text-muted-foreground hover:no-underline">
                    Ver dados, números e limites da leitura
                  </AccordionTrigger>
                  <AccordionContent>
                    <div className="grid gap-3 md:grid-cols-2">
                      <ArticleFact label="Amostra" value={result.analysis.amostra} />
                      <ArticleFact label="Seguimento" value={result.analysis.seguimento} />
                      <ArticleList title="Números-chave" rows={result.analysis.numerosChave} />
                      <ArticleList title="Limitações" rows={result.analysis.limitacoes} />
                      <ArticleList title="Pode falar" rows={result.analysis.podeFalar} />
                      <ArticleList
                        title="Não pode falar"
                        rows={result.analysis.naoPodeFalar}
                        danger
                      />
                    </div>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            </div>

            <div>
              <h3 className="font-display text-sm font-semibold">
                Escolha uma ideia para criar roteiro
              </h3>
              <p className="text-xs text-muted-foreground">
                A primeira foi priorizada como ponto de partida. As outras mantêm ângulos
                alternativos.
              </p>
            </div>
            {result.ideas.map((idea, index) => (
              <IdeaSuggestionCard
                key={idea.id}
                idea={idea}
                recommended={index === 0}
                isSaving={savingIdeaId === idea.id}
                disabled={Boolean(savingIdeaId)}
                onCreateScript={() => onCreateScript(idea)}
              />
            ))}
          </div>
        ) : null}
      </div>

      <DialogFooter>
        <p className="text-xs text-muted-foreground">
          Artigos observacionais viram conteúdo educativo: associação não deve ser vendida como
          causalidade ou promessa clínica.
        </p>
      </DialogFooter>
    </DialogContent>
  );
}

function ArticleFact({ label, value }: { label: string; value?: string }) {
  return (
    <div className="rounded-md border bg-background px-3 py-2">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <p className="mt-1 text-xs leading-5">{value || "—"}</p>
    </div>
  );
}

function ArticleList({
  title,
  rows,
  danger = false,
}: {
  title: string;
  rows?: string[];
  danger?: boolean;
}) {
  return (
    <div
      className={`rounded-md border bg-background px-3 py-2 ${danger ? "border-status-danger/30" : ""}`}
    >
      <div
        className={`text-[10px] font-semibold uppercase tracking-wider ${
          danger ? "text-status-danger" : "text-muted-foreground"
        }`}
      >
        {title}
      </div>
      <ul className="mt-1 space-y-1 text-xs leading-5">
        {(rows?.length ? rows : ["—"]).map((row, index) => (
          <li key={`${title}-${index}`}>{row}</li>
        ))}
      </ul>
    </div>
  );
}

function IdeaSuggestionCard({
  idea,
  recommended = false,
  isSaving,
  disabled,
  onCreateScript,
}: {
  idea: Idea;
  recommended?: boolean;
  isSaving: boolean;
  disabled: boolean;
  onCreateScript: () => void;
}) {
  return (
    <div
      className={`rounded-lg border bg-card p-4 ${
        recommended ? "border-status-info/40 bg-status-info/5" : "border-border"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <div className="font-semibold leading-6">{idea.titulo}</div>
            {recommended ? (
              <Badge className="bg-status-info text-status-info-foreground">Recomendada</Badge>
            ) : null}
            <IdeaQualityBadge idea={idea} />
          </div>
          <div className="mt-1 flex flex-wrap gap-1">
            <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
              {familiaLabel[idea.familia]}
            </span>
            <StatusBadge {...prioridadeLabel[idea.prioridade]} />
          </div>
        </div>
        <Button
          size="sm"
          onClick={onCreateScript}
          disabled={disabled || !evaluateIdeaQuality(idea).ready}
        >
          {isSaving ? (
            <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
          ) : (
            <Sparkles className="mr-1 h-3.5 w-3.5" />
          )}
          Criar roteiro
        </Button>
      </div>

      {recommended ? (
        <>
          <Block label="Hook" text={idea.hook} />
          <Block label="Como o avatar deve explicar" text={idea.angulo} />
          {idea.publicoDor ? <Block label="Para quem" text={idea.publicoDor} /> : null}
          <p className="mt-3 rounded-md border border-status-warn/30 bg-status-warn/10 px-3 py-2 text-xs leading-5 text-status-warn-foreground">
            {idea.observacaoCompliance}
          </p>
        </>
      ) : (
        <Accordion type="single" collapsible className="mt-2">
          <AccordionItem value="detalhes" className="border-b-0">
            <AccordionTrigger className="py-2 text-xs text-muted-foreground hover:no-underline">
              Ver hook e contexto
            </AccordionTrigger>
            <AccordionContent>
              <Block label="Hook" text={idea.hook} />
              <Block label="Como o avatar deve explicar" text={idea.angulo} />
              {idea.publicoDor ? <Block label="Para quem" text={idea.publicoDor} /> : null}
              <Block label="Limite clínico" text={idea.observacaoCompliance} />
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      )}
      {!evaluateIdeaQuality(idea).ready ? (
        <p className="mt-3 rounded-md border border-status-warn/30 bg-status-warn/10 px-3 py-2 text-xs leading-5 text-status-warn-foreground">
          Roteiro bloqueado até completar o contexto desta ideia.
        </p>
      ) : null}
    </div>
  );
}

function IdeaQualityBadge({ idea }: { idea: Idea }) {
  const quality = evaluateIdeaQuality(idea);
  return (
    <Badge
      variant="outline"
      className={
        quality.ready
          ? "border-status-success/40 bg-status-success/5 text-status-success-foreground"
          : "border-status-warn/40 bg-status-warn/10 text-status-warn-foreground"
      }
    >
      {quality.ready ? `Pronta ${quality.score}/100` : `Revisar ${quality.score}/100`}
    </Badge>
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
  onClear,
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
  onClear: () => void;
}) {
  return (
    <DialogContent className="max-h-[88vh] max-w-3xl overflow-y-auto">
      <DialogHeader>
        <DialogTitle>Nova ideia</DialogTitle>
        <p className="text-sm text-muted-foreground">
          Escreva o ponto de partida. A IA organiza os melhores ângulos para o roteiro.
        </p>
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
            <Select
              value={familia}
              onValueChange={(value) => onFamiliaChange(value as ThemeFamily)}
            >
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

        <div className="flex flex-wrap items-center justify-between gap-2">
          <Button onClick={onExpand} disabled={isExpanding || seed.trim().length < 8}>
            {isExpanding ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Wand2 className="mr-2 h-4 w-4" />
            )}
            Explorar com IA
          </Button>
          {(seed || ideas.length > 0) && (
            <Button size="sm" variant="ghost" onClick={onClear}>
              Limpar ideia
            </Button>
          )}
        </div>

        {ideas.length > 0 ? (
          <div className="grid gap-3">
            <div>
              <h3 className="font-display text-sm font-semibold">
                Escolha uma ideia para criar roteiro
              </h3>
              <p className="text-xs text-muted-foreground">
                A primeira foi priorizada como ponto de partida. As outras trazem variações de
                ângulo.
              </p>
            </div>
            {ideas.map((idea, index) => (
              <IdeaSuggestionCard
                key={idea.id}
                idea={idea}
                recommended={index === 0}
                isSaving={savingIdeaId === idea.id}
                disabled={Boolean(savingIdeaId)}
                onCreateScript={() => onCreateScript(idea)}
              />
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
