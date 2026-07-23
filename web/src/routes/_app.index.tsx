import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { MetricCard } from "@/components/metric-card";
import { StatusBadge } from "@/components/status-badge";
import { PipelineFlow, type PipelineStep } from "@/components/pipeline-flow";
import { EmptyState } from "@/components/empty-state";
import { useStore } from "@/lib/store";
import { fetchAiCosts, type AiCosts } from "@/lib/api/local";
import {
  familiaLabel,
  postStatusLabel,
  prioridadeLabel,
  scriptStatusLabel,
  trendStatusLabel,
} from "@/lib/status";
import {
  Radar,
  Lightbulb,
  FileText,
  CalendarDays,
  ShieldAlert,
  TrendingUp,
  RefreshCcw,
  WalletCards,
} from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";

export const Route = createFileRoute("/_app/")({
  head: () => ({
    meta: [
      { title: "Dashboard | AI Video Creator" },
      {
        name: "description",
        content:
          "Painel de operacao: tendencias, ideias, roteiros, producao, calendario e performance do Dr. Guilherme.",
      },
      { property: "og:title", content: "Dashboard | AI Video Creator" },
      {
        property: "og:description",
        content: "Pipeline editorial ponta a ponta em modo mockado.",
      },
    ],
  }),
  component: Dashboard,
});

function Dashboard() {
  const trends = useStore((s) => s.trends);
  const ideas = useStore((s) => s.ideas);
  const scripts = useStore((s) => s.scripts);
  const jobs = useStore((s) => s.videoJobs);
  const posts = useStore((s) => s.calendarPosts);
  const performance = useStore((s) => s.performance);
  const [aiCosts, setAiCosts] = useState<AiCosts | null>(null);
  const [aiCostsError, setAiCostsError] = useState("");
  const [loadingAiCosts, setLoadingAiCosts] = useState(false);

  async function loadAiCosts() {
    setLoadingAiCosts(true);
    try {
      setAiCosts(await fetchAiCosts());
      setAiCostsError("");
    } catch (err) {
      setAiCostsError(
        err instanceof Error ? err.message : "Nao foi possivel consultar os custos de IA.",
      );
    } finally {
      setLoadingAiCosts(false);
    }
  }

  useEffect(() => {
    void loadAiCosts();
  }, []);

  const novasTendencias = trends.filter((t) => t.status !== "descartado").length;
  const ideiasNovas = ideas.filter((i) => i.status !== "descartado").length;
  const roteirosAguardando = scripts.filter(
    (s) => s.status === "aguardando_validacao" || s.status === "em_revisao",
  ).length;
  const producaoAtiva = jobs.filter(
    (j) => j.status === "fila" || j.status === "processando",
  ).length;
  const postsAgendados = posts.filter((p) => p.status !== "publicado").length;
  const publicados = posts.filter((p) => p.status === "publicado").length;

  const steps: PipelineStep[] = [
    {
      key: "radar",
      label: "Radar",
      count: novasTendencias,
      to: "/radar",
      tone: "info",
      hint: "capturadas",
    },
    {
      key: "ideias",
      label: "Ideias",
      count: ideiasNovas,
      to: "/ideias",
      tone: "info",
      hint: "no funil",
    },
    {
      key: "roteiros",
      label: "Roteiros",
      count: roteirosAguardando,
      to: "/roteiros",
      tone: "warn",
      hint: "em edicao",
    },
    {
      key: "producao",
      label: "Producao",
      count: producaoAtiva,
      to: "/producao",
      tone: "warn",
      hint: "em processamento",
    },
    {
      key: "calendario",
      label: "Calendario",
      count: postsAgendados,
      to: "/calendario",
      tone: "info",
      hint: "agendados/pendentes",
    },
    {
      key: "performance",
      label: "Performance",
      count: publicados,
      to: "/performance",
      tone: "success",
      hint: "publicados",
    },
  ];

  const totalViews = performance.reduce((acc, m) => acc + m.views, 0);
  const engajamento = performance.reduce(
    (acc, m) => acc + m.likes + m.comments + m.shares + m.saves,
    0,
  );

  const roteirosPendentes = scripts.filter(
    (s) => s.status === "aguardando_validacao" || s.status === "em_revisao",
  );
  const proximosPosts = [...posts]
    .filter((p) => p.status !== "publicado")
    .sort((a, b) => a.dataAgendada.localeCompare(b.dataAgendada))
    .slice(0, 5);
  const topTrends = [...trends]
    .sort((a, b) => new Date(b.criadoEm).getTime() - new Date(a.criadoEm).getTime())
    .slice(0, 5);

  return (
    <AppShell title="Dashboard">
      <div className="mb-4">
        <PipelineFlow steps={steps} />
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Tendencias ativas"
          value={novasTendencias}
          icon={<Radar className="h-4 w-4" />}
          tone="info"
        />
        <MetricCard
          label="Roteiros em edicao"
          value={roteirosAguardando}
          icon={<ShieldAlert className="h-4 w-4" />}
          tone="warn"
        />
        <MetricCard
          label="Videos em producao"
          value={producaoAtiva}
          icon={<FileText className="h-4 w-4" />}
        />
        <MetricCard
          label="Views (mock)"
          value={totalViews.toLocaleString("pt-BR")}
          icon={<TrendingUp className="h-4 w-4" />}
          tone="success"
          hint={`${engajamento.toLocaleString("pt-BR")} interacoes`}
        />
      </div>

      <section className="mt-6 rounded-xl border bg-card shadow-sm">
        <div className="flex items-center justify-between gap-3 border-b px-4 py-2.5">
          <div>
            <h2 className="font-display text-sm font-semibold">Custos de IA</h2>
            <p className="text-[11px] text-muted-foreground">
              Saldo e uso dos provedores conectados ao aplicativo.
            </p>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void loadAiCosts()}
            disabled={loadingAiCosts}
          >
            <RefreshCcw className={`mr-1 h-3.5 w-3.5 ${loadingAiCosts ? "animate-spin" : ""}`} />
            Atualizar
          </Button>
        </div>
        {aiCostsError ? (
          <p className="px-4 py-4 text-sm text-destructive">{aiCostsError}</p>
        ) : !aiCosts ? (
          <p className="px-4 py-4 text-sm text-muted-foreground">Consultando provedores...</p>
        ) : (
          <div>
            {aiCosts.providers.map((provider) => (
              <div
                key={provider.id}
                className="flex items-center justify-between gap-4 border-b px-4 py-3 last:border-b-0"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <WalletCards className="h-4 w-4 shrink-0 text-status-info" />
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium">{provider.name}</p>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${provider.status === "conectado" ? "bg-status-success/10 text-status-success" : provider.status === "nao_conectado" ? "bg-muted text-muted-foreground" : "bg-destructive/10 text-destructive"}`}
                      >
                        {provider.status === "conectado"
                          ? "Conectado"
                          : provider.status === "nao_conectado"
                            ? "Nao conectado"
                            : "Indisponivel"}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {provider.description}. {provider.note}
                    </p>
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  {provider.remainingBalance !== null && provider.currency ? (
                    <>
                      <p className="font-display text-base font-semibold tabular-nums">
                        {formatCurrency(provider.remainingBalance, provider.currency)}
                      </p>
                      <p className="text-[11px] text-muted-foreground">saldo disponivel</p>
                      {provider.trackedSpend !== null ? (
                        <p className="mt-1 text-[11px] text-muted-foreground">
                          Gasto rastreado:{" "}
                          {formatCurrency(provider.trackedSpend, provider.currency)}
                        </p>
                      ) : null}
                    </>
                  ) : (
                    <p className="text-xs text-muted-foreground">Sem uso registrado</p>
                  )}
                </div>
              </div>
            ))}
            <p className="border-t bg-muted/30 px-4 py-2 text-[11px] text-muted-foreground">
              Atualizado em {new Date(aiCosts.updatedAt).toLocaleString("pt-BR")}. O total gasto so
              aparece quando o provedor informar custo por chamada ou video.
            </p>
          </div>
        )}
      </section>

      <section className="mt-6 grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border bg-card shadow-sm">
          <div className="flex items-center justify-between border-b px-4 py-2.5">
            <div>
              <h2 className="font-display text-sm font-semibold">Roteiros em edicao</h2>
              <p className="text-[11px] text-muted-foreground">
                Rascunhos e roteiros em revisao editorial.
              </p>
            </div>
            <Button asChild variant="ghost" size="sm">
              <Link to="/roteiros">Ver todos</Link>
            </Button>
          </div>
          {roteirosPendentes.length === 0 ? (
            <EmptyState
              className="m-3"
              icon={<FileText className="h-4 w-4" />}
              title="Nada em edicao"
              description="Gere novos roteiros a partir da tela de Ideias."
              action={
                <Button asChild size="sm" variant="secondary">
                  <Link to="/ideias">Ir para Ideias</Link>
                </Button>
              }
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Titulo</TableHead>
                  <TableHead>Categoria</TableHead>
                  <TableHead>Prioridade</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {roteirosPendentes.slice(0, 5).map((s) => (
                  <TableRow key={s.id} className="cursor-pointer">
                    <TableCell className="font-medium">
                      <Link to="/roteiros/$id" params={{ id: s.id }} className="hover:underline">
                        {s.titulo}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {familiaLabel[s.categoria]}
                    </TableCell>
                    <TableCell>
                      <StatusBadge {...prioridadeLabel[s.prioridade]} />
                    </TableCell>
                    <TableCell>
                      <StatusBadge {...scriptStatusLabel[s.status]} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>

        <div className="rounded-xl border bg-card shadow-sm">
          <div className="flex items-center justify-between border-b px-4 py-2.5">
            <div>
              <h2 className="font-display text-sm font-semibold">Proximas publicacoes</h2>
              <p className="text-[11px] text-muted-foreground">
                Agenda editorial dos proximos reels.
              </p>
            </div>
            <Button asChild variant="ghost" size="sm">
              <Link to="/calendario">Abrir calendario</Link>
            </Button>
          </div>
          {proximosPosts.length === 0 ? (
            <EmptyState
              className="m-3"
              icon={<CalendarDays className="h-4 w-4" />}
              title="Sem agendamentos"
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Titulo</TableHead>
                  <TableHead>Canal</TableHead>
                  <TableHead>Data</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {proximosPosts.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="font-medium">{p.titulo}</TableCell>
                    <TableCell className="text-muted-foreground capitalize">
                      {p.canal.replace("_", " ")}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {new Date(p.dataAgendada).toLocaleDateString("pt-BR")}
                    </TableCell>
                    <TableCell>
                      <StatusBadge {...postStatusLabel[p.status]} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      </section>

      <section className="mt-6 rounded-xl border bg-card shadow-sm">
        <div className="flex items-center justify-between border-b px-4 py-2.5">
          <div>
            <h2 className="font-display text-sm font-semibold">Radar de tendencias</h2>
            <p className="text-[11px] text-muted-foreground">
              {ideas.filter((i) => i.status !== "descartado").length} ideias em aberto
            </p>
          </div>
          <Button asChild variant="ghost" size="sm">
            <Link to="/radar">Ver radar</Link>
          </Button>
        </div>
        <Table className="table-fixed">
          <TableHeader>
            <TableRow>
              <TableHead className="w-[26%]">Tendencia</TableHead>
              <TableHead className="w-[26%]">Sinal / Dor</TableHead>
              <TableHead className="w-[14%]">Fonte</TableHead>
              <TableHead className="w-[12%] text-center">Potencial</TableHead>
              <TableHead className="w-[12%]">Prioridade</TableHead>
              <TableHead className="w-[10%]">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {topTrends.map((t) => (
              <TableRow key={t.id}>
                <TableCell className="align-top font-medium">
                  <Link to="/radar/$id" params={{ id: t.id }} className="hover:underline">
                    <span className="block truncate">{t.titulo}</span>
                  </Link>
                  {t.subtema ? (
                    <div className="truncate text-xs text-muted-foreground">{t.subtema}</div>
                  ) : null}
                </TableCell>
                <TableCell className="align-top">
                  {t.sinal ? <div className="line-clamp-2 text-sm">{t.sinal}</div> : null}
                  {t.dorPublico ? (
                    <div className="line-clamp-2 text-xs text-muted-foreground">{t.dorPublico}</div>
                  ) : null}
                  {!t.sinal && !t.dorPublico ? (
                    <span className="text-xs text-muted-foreground">—</span>
                  ) : null}
                </TableCell>
                <TableCell className="align-top text-muted-foreground">
                  <span className="block truncate" title={t.fonte}>
                    {fonteLabel(t.fonte)}
                  </span>
                </TableCell>
                <TableCell className="text-center tabular-nums">
                  {t.potencial == null ? "—" : `${t.potencial}/10`}
                </TableCell>
                <TableCell>
                  <StatusBadge {...prioridadeLabel[t.prioridade]} />
                </TableCell>
                <TableCell>
                  <StatusBadge {...trendStatusLabel[t.status]} />
                </TableCell>
              </TableRow>
            ))}
            {trends.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="py-6 text-center text-sm text-muted-foreground">
                  Nenhuma tendencia capturada.{" "}
                  <Link to="/radar" className="text-status-info underline">
                    Ir para o Radar
                  </Link>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </section>

      <p className="mt-4 flex items-center gap-1 text-[11px] text-muted-foreground">
        Dados do Radar sao sincronizados do Google Sheets. A producao usa HeyGen; performance segue
        em modo mockado. Use{" "}
        <Link to="/configuracoes" className="text-status-info underline">
          Configuracoes
        </Link>{" "}
        para revisar temas prioritarios e palavras proibidas.
        <Lightbulb className="ml-1 h-3 w-3" />
      </p>
    </AppShell>
  );
}

function fonteLabel(fonte: string): string {
  if (!/^https?:\/\//i.test(fonte)) return fonte;
  try {
    return new URL(fonte).hostname.replace(/^www\./, "");
  } catch {
    return fonte;
  }
}

function formatCurrency(value: number, currency: string): string {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency }).format(value);
}
