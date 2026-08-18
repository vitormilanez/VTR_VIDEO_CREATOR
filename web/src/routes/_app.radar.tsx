import { createFileRoute, Link, Outlet, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { EmptyState } from "@/components/empty-state";
import { StatusChips } from "@/components/status-chips";
import { WithTooltip } from "@/components/with-tooltip";
import { ConfirmAction } from "@/components/confirm-action";
import { WeeklyArchiveSwitch } from "@/components/weekly-archive-switch";
import { EditorialSignals } from "@/components/editorial-signals";
import { familiaLabel, prioridadeLabel, trendStatusLabel } from "@/lib/status";
import { genId, useStore } from "@/lib/store";
import { splitWeekly, type WeeklyView } from "@/lib/weekly-archive";
import {
  appendIdea,
  appendTrend,
  expandIdeas,
  fetchState,
  huntTrends,
  setSheetStatus,
  summarizeTrendSource,
} from "@/lib/api/local";
import type { TrendSourceSummary } from "@/lib/api/local";
import { defaultSettings } from "@/lib/mock-data";
import type { Prioridade, ThemeFamily, Trend, TrendStatus } from "@/lib/mock-data";
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
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  ArrowDownUp,
  ExternalLink,
  Loader2,
  Plus,
  Radar,
  RefreshCcw,
  Search,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute("/_app/radar")({
  head: () => ({
    meta: [
      { title: "Radar de tendencias | AI Video Creator" },
      {
        name: "description",
        content: "Capture tendencias medicas e transforme em ideias educativas.",
      },
      { property: "og:title", content: "Radar de tendencias | AI Video Creator" },
      { property: "og:description", content: "Captura de tendencias para reels medicos." },
    ],
  }),
  component: RadarLayout,
});

const familias: ThemeFamily[] = [
  "medicamento",
  "comportamento",
  "metabolismo",
  "obesidade",
  "educativo",
];
const prioridades: Prioridade[] = ["alta", "media", "baixa"];

function RadarLayout() {
  return <Outlet />;
}

export function RadarPage() {
  const trends = useStore((s) => s.trends);
  const ideas = useStore((s) => s.ideas);
  const addTrend = useStore((s) => s.addTrend);
  const addIdea = useStore((s) => s.addIdea);
  const updateTrend = useStore((s) => s.updateTrend);
  const hydrate = useStore((s) => s.hydrate);
  const radarSettings = useStore((s) => s.settings.radar ?? defaultSettings.radar);
  const navigate = useNavigate();

  const [familia, setFamilia] = useState<string>("todas");
  const [status, setStatus] = useState<string>("todos");
  const [prioridade, setPrioridade] = useState<string>("todas");
  const [fonte, setFonte] = useState<string>("todas");
  const [potencialMinimo, setPotencialMinimo] = useState<string>(
    String(radarSettings.potencialMinimo),
  );
  const [ordenacao, setOrdenacao] = useState<string>("recentes");
  const [busca, setBusca] = useState("");
  const [weeklyView, setWeeklyView] = useState<WeeklyView>("current");
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [generatingIdeaId, setGeneratingIdeaId] = useState<string | null>(null);
  const [preview, setPreview] = useState<Trend | null>(null);
  const [sourceSummary, setSourceSummary] = useState<TrendSourceSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState("");

  useEffect(() => {
    let active = true;
    setSourceSummary(null);
    setSummaryError("");
    if (!preview?.link) {
      setSummaryLoading(false);
      return () => {
        active = false;
      };
    }
    setSummaryLoading(true);
    summarizeTrendSource(preview.sinal || preview.subtema || preview.titulo, preview.link)
      .then((result) => {
        if (active) setSourceSummary(result);
      })
      .catch((error: unknown) => {
        if (active) {
          setSummaryError(error instanceof Error ? error.message : "Resumo indisponivel.");
        }
      })
      .finally(() => {
        if (active) setSummaryLoading(false);
      });
    return () => {
      active = false;
    };
  }, [preview?.id, preview?.link, preview?.sinal, preview?.subtema, preview?.titulo]);

  const weekly = splitWeekly(trends, (trend) => trend.criadoEm);
  const weeklyTrends = weeklyView === "current" ? weekly.current : weekly.archive;

  const filtered = weeklyTrends.filter((t) => {
    if (familia !== "todas" && t.familia !== familia) return false;
    if (status !== "todos" && t.status !== status) return false;
    if (prioridade !== "todas" && t.prioridade !== prioridade) return false;
    if (fonte !== "todas" && sourceGroup(t.fonte) !== fonte) return false;
    if ((t.potencial || 0) < Number(potencialMinimo || 0)) return false;
    if (busca) {
      const q = busca.toLowerCase();
      const alvo = [t.titulo, t.subtema, t.sinal, t.dorPublico, t.fonte, t.notas]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      if (!alvo.includes(q)) return false;
    }
    return true;
  });

  const fontes = Array.from(
    new Set(weeklyTrends.map((trend) => sourceGroup(trend.fonte)).filter(Boolean)),
  ).sort();
  const ordered = [...filtered].sort((a, b) => {
    if (ordenacao === "potencial") return (b.potencial || 0) - (a.potencial || 0);
    if (ordenacao === "prioridade")
      return priorityWeight(b.prioridade) - priorityWeight(a.prioridade);
    return new Date(b.criadoEm).getTime() - new Date(a.criadoEm).getTime();
  });

  const statusCounts: Record<TrendStatus, number> = {
    novo: 0,
    em_analise: 0,
    descartado: 0,
  };
  weeklyTrends.forEach((t) => (statusCounts[t.status] += 1));
  const activeFilterCount = [
    familia !== "todas",
    prioridade !== "todas",
    fonte !== "todas",
    potencialMinimo !== "0",
    ordenacao !== "recentes",
  ].filter(Boolean).length;

  function clearAdvancedFilters() {
    setFamilia("todas");
    setPrioridade("todas");
    setFonte("todas");
    setPotencialMinimo("0");
    setOrdenacao("recentes");
  }

  function ideaForTrend(trend: Trend) {
    return ideas
      .filter((idea) => idea.trendId === trend.id)
      .sort((a, b) => new Date(b.criadoEm).getTime() - new Date(a.criadoEm).getTime())[0];
  }

  function trendHasIdea(trend: Trend) {
    return Boolean(ideaForTrend(trend)) || trend.status === "em_analise";
  }

  async function gerarIdeia(t: Trend) {
    const existingIdea = ideaForTrend(t);
    if (existingIdea) {
      navigate({ to: "/ideias/$id", params: { id: existingIdea.id } });
      return;
    }
    if (t.status === "em_analise") {
      toast.warning(
        "Esta tendencia ja esta marcada como em analise, mas a ideia vinculada nao foi encontrada localmente. Atualize a pagina (Buscar tendencias) antes de gerar outra ideia.",
      );
      return;
    }
    setGeneratingIdeaId(t.id);
    try {
      const [generated] = await expandIdeas({
        seed: [t.titulo, t.subtema, t.sinal, t.dorPublico, t.notas].filter(Boolean).join("\n"),
        quantity: 1,
        familia: t.familia,
        prioridade: t.prioridade,
        sourceUrl: t.link || null,
      });
      if (!generated) throw new Error("A IA nao retornou uma ideia contextualizada.");
      const idea = {
        ...generated,
        id: genId("i"),
        trendId: t.id,
        linkOrigem: t.link || generated.linkOrigem,
        criadoEm: new Date().toISOString(),
      };
      const saved = await appendIdea(idea);
      addIdea(saved);
      updateTrend(t.id, { status: "em_analise" });
      try {
        await setSheetStatus("radar", t.id, "em_analise");
      } catch {
        toast.warning("Ideia salva, mas o status da tendencia nao foi atualizado.");
      }
      toast.success("Ideia criada e salva no banco de dados.");
      navigate({ to: "/ideias/$id", params: { id: saved.id } });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Nao foi possivel criar a ideia.");
    } finally {
      setGeneratingIdeaId(null);
    }
  }

  async function descartarTrend(t: Trend) {
    updateTrend(t.id, { status: "descartado" });
    try {
      await setSheetStatus("radar", t.id, "descartado");
      toast.success("Tendência descartada e atualizada no banco de dados.");
    } catch (err) {
      updateTrend(t.id, { status: t.status });
      toast.error(err instanceof Error ? err.message : "Falha ao sincronizar.");
    }
  }

  async function handleBuscar() {
    setLoading(true);
    const aviso = toast.loading("Rodando busca real de tendencias...");
    try {
      const res = await huntTrends();
      const data = await fetchState();
      hydrate(data);
      const queryInfo = res.queries?.length ? ` ${res.queries.length} termos usados.` : "";
      if (res.partial) {
        toast.warning(
          res.detail ||
            `Tendências capturadas localmente, mas a persistência falhou no passo '${res.failedStep}'.`,
          { id: aviso },
        );
      } else {
        toast.success(
          res.added
            ? `${res.added} novas tendencias capturadas.${queryInfo}`
            : `Radar atualizado.${queryInfo}`,
          { id: aviso },
        );
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Nao foi possivel buscar tendencias.", {
        id: aviso,
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell
      title="Radar de tendencias"
      actions={
        <>
          <WithTooltip label="Rodar busca real (Google News/Trends) e salvar no banco de dados">
            <Button
              size="sm"
              variant="secondary"
              onClick={handleBuscar}
              disabled={loading}
              aria-label="Buscar tendências"
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin sm:mr-1" />
              ) : (
                <RefreshCcw className="h-4 w-4 sm:mr-1" />
              )}
              <span className="hidden sm:inline">Buscar tendências</span>
            </Button>
          </WithTooltip>
          <Dialog open={open} onOpenChange={setOpen}>
            <WithTooltip label="Cadastrar tendencia manualmente">
              <DialogTrigger asChild>
                <Button size="sm" aria-label="Nova tendência">
                  <Plus className="h-4 w-4 sm:mr-1" />
                  <span className="hidden sm:inline">Nova tendência</span>
                </Button>
              </DialogTrigger>
            </WithTooltip>
            <NovaTendenciaDialog
              onClose={() => setOpen(false)}
              onCreate={(t) => {
                addTrend(t);
                toast.success("Tendência registrada e salva no banco de dados.");
                setOpen(false);
              }}
            />
          </Dialog>
        </>
      }
    >
      <WeeklyArchiveSwitch
        className="mb-3"
        value={weeklyView}
        onChange={setWeeklyView}
        currentCount={weekly.current.length}
        archiveCount={weekly.archive.length}
      />
      <div className="mb-3 flex flex-col gap-2 rounded-xl border bg-card p-2 shadow-sm lg:flex-row lg:items-center">
        <StatusChips
          className="flex-1"
          value={status}
          onChange={setStatus}
          options={[
            { value: "novo", label: "Novas", tone: "info", count: statusCounts.novo },
            {
              value: "em_analise",
              label: "Em analise",
              tone: "warn",
              count: statusCounts.em_analise,
            },
            {
              value: "descartado",
              label: "Descartadas",
              tone: "neutral",
              count: statusCounts.descartado,
            },
          ]}
        />
        <div className="flex min-w-0 items-center gap-2">
          <div className="relative min-w-0 flex-1 lg:w-64 lg:flex-none">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={busca}
              onChange={(event) => setBusca(event.target.value)}
              placeholder="Buscar tendência..."
              className="h-8 w-full pl-8"
            />
          </div>
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="outline" size="sm" className="cursor-pointer">
                <SlidersHorizontal className="mr-1.5 h-3.5 w-3.5" />
                Filtros
                {activeFilterCount ? (
                  <Badge className="ml-1.5 h-5 min-w-5 px-1.5 text-[10px]">
                    {activeFilterCount}
                  </Badge>
                ) : null}
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-80">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold">Refinar resultados</p>
                  <p className="text-[11px] text-muted-foreground">
                    Use apenas quando precisar reduzir a lista.
                  </p>
                </div>
                {activeFilterCount ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 cursor-pointer px-2 text-xs"
                    onClick={clearAdvancedFilters}
                  >
                    <X className="mr-1 h-3.5 w-3.5" /> Limpar
                  </Button>
                ) : null}
              </div>
              <div className="mt-4 grid gap-3">
                <FilterField label="Família">
                  <Select value={familia} onValueChange={setFamilia}>
                    <SelectTrigger className="w-full" aria-label="Filtrar por família">
                      <SelectValue placeholder="Família" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="todas">Todas as famílias</SelectItem>
                      {familias.map((f) => (
                        <SelectItem key={f} value={f}>
                          {familiaLabel[f]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FilterField>
                <FilterField label="Prioridade">
                  <Select value={prioridade} onValueChange={setPrioridade}>
                    <SelectTrigger className="w-full" aria-label="Filtrar por prioridade">
                      <SelectValue placeholder="Prioridade" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="todas">Todas as prioridades</SelectItem>
                      {prioridades.map((p) => (
                        <SelectItem key={p} value={p}>
                          {prioridadeLabel[p].label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FilterField>
                <FilterField label="Fonte">
                  <Select value={fonte} onValueChange={setFonte}>
                    <SelectTrigger className="w-full" aria-label="Filtrar por fonte">
                      <SelectValue placeholder="Fonte" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="todas">Todas as fontes</SelectItem>
                      {fontes.map((item) => (
                        <SelectItem key={item} value={item}>
                          {item}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FilterField>
                <div className="grid grid-cols-2 gap-2">
                  <FilterField label="Potencial mínimo">
                    <Select value={potencialMinimo} onValueChange={setPotencialMinimo}>
                      <SelectTrigger className="w-full" aria-label="Potencial mínimo">
                        <SelectValue placeholder="Potencial" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="0">Qualquer</SelectItem>
                        <SelectItem value="5">5 ou mais</SelectItem>
                        <SelectItem value="7">7 ou mais</SelectItem>
                        <SelectItem value="9">9 ou mais</SelectItem>
                      </SelectContent>
                    </Select>
                  </FilterField>
                  <FilterField label="Ordenação">
                    <Select value={ordenacao} onValueChange={setOrdenacao}>
                      <SelectTrigger className="w-full" aria-label="Ordenar tendências">
                        <ArrowDownUp className="mr-1 h-3.5 w-3.5" />
                        <SelectValue placeholder="Ordenar" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="recentes">Recentes</SelectItem>
                        <SelectItem value="potencial">Potencial</SelectItem>
                        <SelectItem value="prioridade">Prioridade</SelectItem>
                      </SelectContent>
                    </Select>
                  </FilterField>
                </div>
              </div>
            </PopoverContent>
          </Popover>
        </div>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          icon={<Radar className="h-4 w-4" />}
          title={
            weeklyTrends.length === 0
              ? weeklyView === "current"
                ? "Esta semana ainda não buscamos tendências"
                : "O arquivo ainda está vazio"
              : "Nenhuma tendência com esses filtros"
          }
          description={
            weeklyTrends.length === 0
              ? weeklyView === "current"
                ? "Quando a próxima busca for realizada, os novos sinais aparecerão aqui."
                : "As tendências de semanas anteriores serão preservadas aqui automaticamente."
              : "Ajuste os filtros para ampliar os resultados."
          }
          action={
            <Button size="sm" variant="secondary" onClick={handleBuscar}>
              <RefreshCcw className="mr-1 h-4 w-4" /> Buscar tendencias
            </Button>
          }
        />
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
          <Table className="min-w-[620px] table-fixed">
            <TableHeader>
              <TableRow>
                <TableHead className="w-[31%]">Tema</TableHead>
                <TableHead className="w-[29%]">Resumo</TableHead>
                <TableHead className="w-[11%] text-center">Sinais</TableHead>
                <TableHead className="w-[11%]">Oportunidade</TableHead>
                <TableHead className="w-[18%] text-right">Ação</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ordered.map((t) => {
                const generated = trendHasIdea(t);
                const linkedIdea = ideaForTrend(t);
                return (
                  <TableRow
                    key={t.id}
                    className={
                      generated
                        ? "group cursor-pointer bg-status-success/5"
                        : "group cursor-pointer"
                    }
                    onClick={() => setPreview(t)}
                  >
                    <TableCell className="align-top py-4">
                      <div className="flex items-center gap-2">
                        <div className="line-clamp-2 font-semibold leading-5">{t.titulo}</div>
                        {generated ? (
                          <Badge
                            variant="outline"
                            className="h-5 shrink-0 border-status-success/40 px-1.5 text-[10px] text-status-success"
                          >
                            Ideia gerada
                          </Badge>
                        ) : null}
                      </div>
                      <div className="mt-2 flex min-w-0 items-center gap-2">
                        <span className="rounded-md bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                          {familiaLabel[t.familia]}
                        </span>
                        {t.link ? (
                          <a
                            href={t.link}
                            target="_blank"
                            rel="noreferrer"
                            onClick={(event) => event.stopPropagation()}
                            className="flex min-w-0 items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground hover:underline"
                            title={t.fonte}
                          >
                            <span className="truncate">{sourceGroup(t.fonte)}</span>
                            <ExternalLink className="h-3 w-3 shrink-0" />
                          </a>
                        ) : (
                          <span className="truncate text-[10px] text-muted-foreground">
                            {sourceGroup(t.fonte)}
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="align-top py-4">
                      <div className="line-clamp-2 text-xs leading-5 text-muted-foreground">
                        {t.sinal || t.dorPublico || t.subtema || "Resumo não informado."}
                      </div>
                      <span className="mt-1 block text-[10px] font-medium text-status-info opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
                        Ver completo
                      </span>
                    </TableCell>
                    <TableCell
                      className="align-top py-3 text-center"
                      onClick={(event) => event.stopPropagation()}
                    >
                      <EditorialSignals
                        priority={t.prioridade}
                        note={t.notas}
                        noteLabel="Notas editoriais"
                      />
                    </TableCell>
                    <TableCell className="align-top py-4">
                      <PotencialBadge valor={t.potencial} />
                      <div className="mt-1.5 text-[11px] text-muted-foreground">
                        {trendStatusLabel[t.status].label}
                      </div>
                    </TableCell>
                    <TableCell
                      className="align-top py-3 text-right"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="flex justify-end gap-1">
                        <WithTooltip label="Gerar ideia a partir desta tendencia">
                          <Button
                            size="sm"
                            variant={generated ? "ghost" : "secondary"}
                            aria-label={generated ? "Abrir ideia gerada" : "Gerar ideia"}
                            disabled={generatingIdeaId === t.id}
                            onClick={() =>
                              linkedIdea
                                ? navigate({ to: "/ideias/$id", params: { id: linkedIdea.id } })
                                : gerarIdeia(t)
                            }
                          >
                            {generatingIdeaId === t.id ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin xl:mr-1" />
                            ) : (
                              <Sparkles className="h-3.5 w-3.5 xl:mr-1" />
                            )}
                            <span className="hidden xl:inline">
                              {generatingIdeaId === t.id
                                ? "Lendo fonte"
                                : generated
                                  ? "Ver ideia"
                                  : "Ideia"}
                            </span>
                          </Button>
                        </WithTooltip>
                        <ConfirmAction
                          destructive
                          title="Descartar tendencia?"
                          description="Voce pode restaurar depois editando o status."
                          confirmLabel="Descartar"
                          onConfirm={() => descartarTrend(t)}
                          trigger={
                            <WithTooltip label="Descartar tendencia">
                              <Button size="sm" variant="ghost" aria-label="Descartar tendência">
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
                <SheetDescription>
                  Preview rapido — abra a tela completa para mais acoes.
                </SheetDescription>
              </SheetHeader>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <StatusBadge {...trendStatusLabel[preview.status]} />
                <StatusBadge {...prioridadeLabel[preview.prioridade]} />
                <PotencialBadge valor={preview.potencial} />
                {trendHasIdea(preview) ? (
                  <Badge variant="outline" className="border-status-success/40 text-status-success">
                    Ideia gerada
                  </Badge>
                ) : null}
              </div>
              <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
                <Meta label="Fonte" value={preview.fonte} />
                <Meta label="Familia" value={familiaLabel[preview.familia]} />
                {preview.subtema ? <Meta label="Subtema" value={preview.subtema} /> : null}
                <Meta
                  label="Capturado"
                  value={new Date(preview.criadoEm).toLocaleDateString("pt-BR")}
                />
              </dl>
              {preview.sinal ? (
                <div className="mt-4">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Sinal de tendencia
                  </div>
                  <p className="mt-1 text-sm">{preview.sinal}</p>
                </div>
              ) : null}
              {preview.dorPublico ? (
                <div className="mt-4">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Dor do publico
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">{preview.dorPublico}</p>
                </div>
              ) : null}
              <div className="mt-4 rounded-md border bg-muted/35 p-3">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Resumo da noticia
                </div>
                {summaryLoading ? (
                  <div className="mt-2 flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" /> Lendo a fonte...
                  </div>
                ) : sourceSummary ? (
                  <div className="mt-2 space-y-2">
                    <p className="text-sm leading-relaxed">{sourceSummary.summary}</p>
                    {sourceSummary.keyPoints.length ? (
                      <ul className="space-y-1 text-xs text-muted-foreground">
                        {sourceSummary.keyPoints.map((point) => (
                          <li key={point} className="flex gap-2">
                            <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-status-info" />
                            <span>{point}</span>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                ) : (
                  <p className="mt-2 text-xs text-muted-foreground">
                    {summaryError || "Esta tendencia nao possui uma fonte legivel para resumir."}
                  </p>
                )}
              </div>
              {preview.link ? (
                <a
                  href={preview.link}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-4 inline-flex items-center gap-1 text-sm text-status-info hover:underline"
                >
                  <ExternalLink className="h-3.5 w-3.5" /> Abrir referencia
                </a>
              ) : null}
              {preview.notas ? (
                <div className="mt-4">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Notas
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">{preview.notas}</p>
                </div>
              ) : null}
              <div className="mt-6 flex flex-col gap-2">
                <Button
                  size="sm"
                  disabled={generatingIdeaId === preview.id}
                  onClick={() => {
                    const linkedIdea = ideaForTrend(preview);
                    if (linkedIdea) {
                      navigate({ to: "/ideias/$id", params: { id: linkedIdea.id } });
                    } else {
                      gerarIdeia(preview);
                    }
                    setPreview(null);
                  }}
                >
                  {generatingIdeaId === preview.id ? (
                    <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                  ) : (
                    <Sparkles className="mr-1 h-4 w-4" />
                  )}{" "}
                  {generatingIdeaId === preview.id
                    ? "Lendo e contextualizando"
                    : trendHasIdea(preview)
                      ? "Ver ideia gerada"
                      : "Gerar ideia"}
                </Button>
                <Button asChild size="sm" variant="secondary">
                  <Link to="/radar/$id" params={{ id: preview.id }}>
                    <ExternalLink className="mr-1 h-4 w-4" /> Abrir tela completa
                  </Link>
                </Button>
                <ConfirmAction
                  destructive
                  title="Descartar tendencia?"
                  onConfirm={() => {
                    descartarTrend(preview);
                    setPreview(null);
                  }}
                  trigger={
                    <Button size="sm" variant="ghost">
                      <Trash2 className="mr-1 h-4 w-4" /> Descartar
                    </Button>
                  }
                />
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </AppShell>
  );
}

function fonteLabel(fonte: string): string {
  if (/^https?:\/\//i.test(fonte)) {
    try {
      return new URL(fonte).hostname.replace(/^www\./, "");
    } catch {
      return fonte;
    }
  }
  return fonte;
}

function sourceGroup(fonte: string): string {
  if (fonte.startsWith("GDELT")) return "GDELT";
  if (fonte.startsWith("Reddit")) return "Reddit";
  if (fonte.startsWith("PubMed")) return "PubMed";
  if (fonte.startsWith("SerpAPI")) return "Google Trends";
  if (fonte.startsWith("Google News")) return "Google News";
  return fonteLabel(fonte);
}

function priorityWeight(priority: Prioridade): number {
  return priority === "alta" ? 3 : priority === "media" ? 2 : 1;
}

function PotencialBadge({ valor }: { valor?: number }) {
  if (valor == null) return <span className="text-xs text-muted-foreground">—</span>;
  const tone =
    valor >= 8
      ? "bg-status-danger/10 text-status-danger"
      : valor >= 5
        ? "bg-status-warn/10 text-status-warn"
        : "bg-status-info/10 text-status-info";
  return (
    <span
      className={`inline-flex min-w-9 items-center justify-center rounded-md px-2 py-0.5 text-xs font-semibold tabular-nums ${tone}`}
    >
      {valor}/10
    </span>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </dt>
      <dd className="break-words tabular-nums">{value}</dd>
    </div>
  );
}

function FilterField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-1.5">
      <span className="text-[11px] font-medium text-muted-foreground">{label}</span>
      {children}
    </div>
  );
}

function NovaTendenciaDialog({
  onClose,
  onCreate,
}: {
  onClose: () => void;
  onCreate: (t: Trend) => void;
}) {
  const [titulo, setTitulo] = useState("");
  const [subtema, setSubtema] = useState("");
  const [fonte, setFonte] = useState("");
  const [potencial, setPotencial] = useState("5");
  const [familia, setFamilia] = useState<ThemeFamily>("obesidade");
  const [prioridade, setPrioridade] = useState<Prioridade>("media");
  const [sinal, setSinal] = useState("");
  const [dorPublico, setDorPublico] = useState("");
  const [notas, setNotas] = useState("");
  const [salvando, setSalvando] = useState(false);

  async function handleSubmit() {
    const draft: Trend = {
      id: genId("t"),
      titulo,
      subtema: subtema || undefined,
      sinal: sinal || undefined,
      dorPublico: dorPublico || undefined,
      fonte,
      volume: 0,
      potencial: Math.max(0, Math.min(10, Number(potencial) || 0)),
      familia,
      risco: "medio",
      prioridade,
      status: "novo",
      notas,
      criadoEm: new Date().toISOString(),
    };
    setSalvando(true);
    try {
      const saved = await appendTrend(draft);
      onCreate(saved);
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : "Não foi possível salvar a tendência no banco de dados.",
      );
    } finally {
      setSalvando(false);
    }
  }

  return (
    <DialogContent>
      <DialogHeader>
        <DialogTitle>Nova tendencia</DialogTitle>
      </DialogHeader>
      <div className="grid gap-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>Tema (titulo)</Label>
            <Input value={titulo} onChange={(e) => setTitulo(e.target.value)} />
          </div>
          <div>
            <Label>Subtema</Label>
            <Input value={subtema} onChange={(e) => setSubtema(e.target.value)} />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>Fonte</Label>
            <Input value={fonte} onChange={(e) => setFonte(e.target.value)} />
          </div>
          <div>
            <Label>Potencial (0-10)</Label>
            <Input
              type="number"
              min={0}
              max={10}
              value={potencial}
              onChange={(e) => setPotencial(e.target.value)}
            />
          </div>
        </div>
        <div>
          <Label>Sinal de tendencia</Label>
          <Input value={sinal} onChange={(e) => setSinal(e.target.value)} />
        </div>
        <div>
          <Label>Dor do publico</Label>
          <Input value={dorPublico} onChange={(e) => setDorPublico(e.target.value)} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>Familia</Label>
            <Select value={familia} onValueChange={(v) => setFamilia(v as ThemeFamily)}>
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
          <div>
            <Label>Prioridade</Label>
            <Select value={prioridade} onValueChange={(v) => setPrioridade(v as Prioridade)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {prioridades.map((p) => (
                  <SelectItem key={p} value={p}>
                    {prioridadeLabel[p].label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div>
          <Label>Notas</Label>
          <Textarea value={notas} onChange={(e) => setNotas(e.target.value)} rows={3} />
        </div>
      </div>
      <DialogFooter>
        <Button variant="ghost" onClick={onClose}>
          Cancelar
        </Button>
        <Button disabled={!titulo || !fonte || salvando} onClick={handleSubmit}>
          {salvando ? "Salvando..." : "Registrar"}
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}
