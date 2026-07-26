import { createFileRoute, Link, Outlet, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { DataToolbar } from "@/components/data-toolbar";
import { EmptyState } from "@/components/empty-state";
import { StatusChips } from "@/components/status-chips";
import { WithTooltip } from "@/components/with-tooltip";
import { ConfirmAction } from "@/components/confirm-action";
import { familiaLabel, prioridadeLabel, trendStatusLabel } from "@/lib/status";
import { genId, useStore } from "@/lib/store";
import { appendIdea, fetchState, huntTrends, setSheetStatus } from "@/lib/api/local";
import { defaultSettings } from "@/lib/mock-data";
import type { Idea } from "@/lib/mock-data";
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
import {
  ArrowDownUp,
  ExternalLink,
  Loader2,
  Plus,
  Radar,
  RefreshCcw,
  Sparkles,
  Trash2,
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
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState<Trend | null>(null);

  const filtered = trends.filter((t) => {
    if (familia !== "todas" && t.familia !== familia) return false;
    if (status !== "todos" && t.status !== status) return false;
    if (prioridade !== "todas" && t.prioridade !== prioridade) return false;
    if (fonte !== "todas" && fonteLabel(t.fonte) !== fonte) return false;
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
    new Set(trends.map((trend) => fonteLabel(trend.fonte)).filter(Boolean)),
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
  trends.forEach((t) => (statusCounts[t.status] += 1));

  async function gerarIdeia(t: Trend) {
    const idea: Idea = {
      id: genId("i"),
      trendId: t.id,
      titulo: `Ideia a partir de: ${t.titulo}`,
      familia: t.familia,
      hook: "Hook educativo sugerido — revise antes de aprovar.",
      angulo:
        "Angulo educativo: contextualizar o tema sem prescrever, reforcando avaliacao individual.",
      tipo: "Reel",
      publicoDor: t.dorPublico,
      cta: "Procure avaliacao individualizada com profissional de saude.",
      observacaoCompliance: "Rascunho gerado localmente. Revisar linguagem antes de virar roteiro.",
      prioridade: t.prioridade,
      status: "novo",
      criadoEm: new Date().toISOString(),
    };
    try {
      const saved = await appendIdea(idea);
      addIdea(saved);
      updateTrend(t.id, { status: "em_analise" });
      try {
        await setSheetStatus("radar", t.id, "em_analise");
      } catch {
        toast.warning("Ideia salva, mas o status da tendencia nao foi atualizado.");
      }
      toast.success("Ideia criada e salva no Sheets.");
      navigate({ to: "/ideias" });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Nao foi possivel criar a ideia.");
    }
  }

  async function descartarTrend(t: Trend) {
    updateTrend(t.id, { status: "descartado" });
    try {
      await setSheetStatus("radar", t.id, "descartado");
      toast.success("Tendencia descartada e sincronizada com o Sheets.");
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
      toast.success(
        res.added
          ? `${res.added} novas tendencias capturadas.${queryInfo}`
          : `Radar atualizado.${queryInfo}`,
        { id: aviso },
      );
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
          <WithTooltip label="Rodar busca real (Google News/Trends) e sincronizar com o Sheets">
            <Button size="sm" variant="secondary" onClick={handleBuscar} disabled={loading}>
              {loading ? (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              ) : (
                <RefreshCcw className="mr-1 h-4 w-4" />
              )}
              Buscar tendencias
            </Button>
          </WithTooltip>
          <Dialog open={open} onOpenChange={setOpen}>
            <WithTooltip label="Cadastrar tendencia manualmente">
              <DialogTrigger asChild>
                <Button size="sm">
                  <Plus className="mr-1 h-4 w-4" /> Nova tendencia
                </Button>
              </DialogTrigger>
            </WithTooltip>
            <NovaTendenciaDialog
              onClose={() => setOpen(false)}
              onCreate={(t) => {
                addTrend(t);
                toast.success("Tendencia registrada.");
                setOpen(false);
              }}
            />
          </Dialog>
        </>
      }
    >
      <StatusChips
        className="mb-3"
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
      <DataToolbar search={busca} onSearch={setBusca} placeholder="Buscar por titulo...">
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
            {prioridades.map((p) => (
              <SelectItem key={p} value={p}>
                {prioridadeLabel[p].label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={fonte} onValueChange={setFonte}>
          <SelectTrigger className="h-8 w-40">
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
        <Select value={potencialMinimo} onValueChange={setPotencialMinimo}>
          <SelectTrigger className="h-8 w-36">
            <SelectValue placeholder="Potencial" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="0">Qualquer potencial</SelectItem>
            <SelectItem value="5">5+ potencial</SelectItem>
            <SelectItem value="7">7+ potencial</SelectItem>
            <SelectItem value="9">9+ potencial</SelectItem>
          </SelectContent>
        </Select>
        <Select value={ordenacao} onValueChange={setOrdenacao}>
          <SelectTrigger className="h-8 w-40">
            <ArrowDownUp className="mr-1 h-3.5 w-3.5" />
            <SelectValue placeholder="Ordenar" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="recentes">Mais recentes</SelectItem>
            <SelectItem value="potencial">Maior potencial</SelectItem>
            <SelectItem value="prioridade">Maior prioridade</SelectItem>
          </SelectContent>
        </Select>
      </DataToolbar>

      {filtered.length === 0 ? (
        <EmptyState
          icon={<Radar className="h-4 w-4" />}
          title="Nenhuma tendencia com esses filtros"
          description="Ajuste os filtros ou capture novas tendencias."
          action={
            <Button size="sm" variant="secondary" onClick={handleBuscar}>
              <RefreshCcw className="mr-1 h-4 w-4" /> Buscar tendencias
            </Button>
          }
        />
      ) : (
        <div className="rounded-xl border bg-card shadow-sm">
          <Table className="w-full table-fixed">
            <TableHeader>
              <TableRow>
                <TableHead className="w-[22%]">Tendencia</TableHead>
                <TableHead className="w-[23%]">Sinal / Dor do publico</TableHead>
                <TableHead className="w-[11%]">Fonte</TableHead>
                <TableHead className="w-[9%] text-center">Potencial viral</TableHead>
                <TableHead className="w-[11%]">Prioridade</TableHead>
                <TableHead className="w-[10%]">Status</TableHead>
                <TableHead className="w-[14%] text-right">Acoes</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ordered.map((t) => (
                <TableRow key={t.id} className="cursor-pointer" onClick={() => setPreview(t)}>
                  <TableCell className="align-top">
                    <div className="truncate font-medium">{t.titulo}</div>
                    {t.subtema ? (
                      <div className="truncate text-xs text-muted-foreground">{t.subtema}</div>
                    ) : null}
                    <div className="mt-1">
                      <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                        {familiaLabel[t.familia]}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="align-top">
                    {t.sinal ? <div className="line-clamp-2 text-sm">{t.sinal}</div> : null}
                    {t.dorPublico ? (
                      <div className="line-clamp-2 text-xs text-muted-foreground">
                        {t.dorPublico}
                      </div>
                    ) : null}
                    {!t.sinal && !t.dorPublico ? (
                      <span className="text-xs text-muted-foreground">—</span>
                    ) : null}
                  </TableCell>
                  <TableCell className="align-top text-muted-foreground">
                    {t.link ? (
                      <a
                        href={t.link}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="flex items-center gap-1 truncate hover:text-foreground hover:underline"
                        title={t.fonte}
                      >
                        <span className="truncate">{fonteLabel(t.fonte)}</span>
                        <ExternalLink className="h-3 w-3 shrink-0" />
                      </a>
                    ) : (
                      <span className="block truncate" title={t.fonte}>
                        {fonteLabel(t.fonte)}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="text-center">
                    <PotencialBadge valor={t.potencial} />
                  </TableCell>
                  <TableCell>
                    <StatusBadge {...prioridadeLabel[t.prioridade]} />
                  </TableCell>
                  <TableCell>
                    <StatusBadge {...trendStatusLabel[t.status]} />
                  </TableCell>
                  <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                    <div className="flex justify-end gap-1">
                      <WithTooltip label="Gerar ideia a partir desta tendencia">
                        <Button size="sm" variant="secondary" onClick={() => gerarIdeia(t)}>
                          <Sparkles className="mr-1 h-3.5 w-3.5" /> Ideia
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
                <SheetDescription>
                  Preview rapido — abra a tela completa para mais acoes.
                </SheetDescription>
              </SheetHeader>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <StatusBadge {...trendStatusLabel[preview.status]} />
                <StatusBadge {...prioridadeLabel[preview.prioridade]} />
                <PotencialBadge valor={preview.potencial} />
              </div>
              <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
                <Meta label="Fonte" value={fonteLabel(preview.fonte)} />
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
                  onClick={() => {
                    gerarIdeia(preview);
                    setPreview(null);
                  }}
                >
                  <Sparkles className="mr-1 h-4 w-4" /> Gerar ideia
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
        <Button
          disabled={!titulo || !fonte}
          onClick={() =>
            onCreate({
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
            })
          }
        >
          Registrar
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}
