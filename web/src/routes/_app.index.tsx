import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { StatusBadge } from "@/components/status-badge";
import { useStore } from "@/lib/store";
import { fetchAiCosts, type AiCosts } from "@/lib/api/local";
import { postStatusLabel } from "@/lib/status";
import type { VideoJob, VideoJobStatus } from "@/lib/mock-data";
import { Button } from "@/components/ui/button";
import {
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  Film,
  Lightbulb,
  Loader2,
  Radar,
  RefreshCcw,
  WalletCards,
} from "lucide-react";

export const Route = createFileRoute("/_app/")({
  head: () => ({
    meta: [
      { title: "Dashboard | AI Video Creator" },
      {
        name: "description",
        content: "Central de operacao: prioridades, videos, custos e agenda.",
      },
      { property: "og:title", content: "Dashboard | AI Video Creator" },
      { property: "og:description", content: "Central de operacao do pipeline editorial." },
    ],
  }),
  component: Dashboard,
});

type CostedVideoJob = VideoJob & { costUsd?: number; currency?: string };

function Dashboard() {
  const trends = useStore((s) => s.trends);
  const ideas = useStore((s) => s.ideas);
  const scripts = useStore((s) => s.scripts);
  const jobs = useStore((s) => s.videoJobs as CostedVideoJob[]);
  const posts = useStore((s) => s.calendarPosts);
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

  const scriptsComVideo = new Set(jobs.filter((j) => j.status !== "erro").map((j) => j.scriptId));
  const jobsAgendados = new Set(posts.map((p) => p.videoJobId).filter(Boolean));

  const filas = [
    {
      key: "radar",
      count: trends.filter((t) => t.status === "novo").length,
      title: "tendências novas",
      action: "Triar e gerar ideias",
      to: "/radar",
      icon: Radar,
      tone: "info" as const,
    },
    {
      key: "ideias",
      count: ideas.filter((i) => i.status === "novo" || i.status === "em_analise").length,
      title: "ideias em aberto",
      action: "Transformar em roteiro",
      to: "/ideias",
      icon: Lightbulb,
      tone: "info" as const,
    },
    {
      key: "roteiros",
      count: scripts.filter(
        (s) => s.status === "aprovado_clinicamente" && !scriptsComVideo.has(s.id),
      ).length,
      title: "roteiros prontos",
      action: "Enviar para vídeo",
      to: "/roteiros",
      icon: Film,
      tone: "warn" as const,
    },
    {
      key: "agenda",
      count: jobs.filter((j) => j.status === "pronto" && !jobsAgendados.has(j.id)).length,
      title: "vídeos sem agenda",
      action: "Agendar publicação",
      to: "/producao",
      icon: CalendarClock,
      tone: "warn" as const,
    },
  ].filter((item) => item.count > 0);

  const provider = aiCosts?.providers.find((item) => item.id === "heygen");
  const claudeProvider = aiCosts?.providers.find((item) => item.id === "anthropic");
  const videos = useMemo(
    () => [...jobs].sort((a, b) => new Date(b.criadoEm).getTime() - new Date(a.criadoEm).getTime()),
    [jobs],
  );
  const videosProntos = jobs.filter((j) => j.status === "pronto").length;
  const videosAtivos = jobs.filter((j) => j.status === "fila" || j.status === "processando").length;
  const videosErro = jobs.filter((j) => j.status === "erro").length;
  const gastoLocal = jobs.reduce((acc, job) => acc + Number(job.costUsd || 0), 0);
  const currency = provider?.currency || jobs.find((job) => job.currency)?.currency || "USD";
  const gastoRastreado = provider?.trackedSpend ?? gastoLocal;
  const custoMedio = videos.length > 0 ? gastoRastreado / videos.length : 0;

  const proximosPosts = [...posts]
    .filter((p) => p.status !== "publicado")
    .sort((a, b) => a.dataAgendada.localeCompare(b.dataAgendada))
    .slice(0, 4);

  return (
    <AppShell title="Dashboard">
      <section className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
        <div className="rounded-lg border bg-card p-4 shadow-sm">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="font-display text-base font-semibold">Operação agora</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                O que precisa de ação para o conteúdo continuar andando.
              </p>
            </div>
            <Button asChild size="sm" variant="secondary">
              <Link to="/radar">
                Buscar tendências <ArrowRight className="ml-1 h-3.5 w-3.5" />
              </Link>
            </Button>
          </div>

          {filas.length === 0 ? (
            <div className="mt-4 flex items-center gap-3 rounded-md border border-status-success/35 bg-status-success/10 px-3 py-3">
              <CheckCircle2 className="h-5 w-5 text-status-success" />
              <div>
                <p className="text-sm font-medium">Tudo em dia.</p>
                <p className="text-xs text-muted-foreground">
                  Nenhuma fila importante esperando por você agora.
                </p>
              </div>
            </div>
          ) : (
            <div className="mt-4 grid gap-2 sm:grid-cols-2">
              {filas.map((fila) => (
                <ActionCard key={fila.key} item={fila} />
              ))}
            </div>
          )}
        </div>

        <VideoCostPanel
          aiCosts={aiCosts}
          error={aiCostsError}
          loading={loadingAiCosts}
          onRefresh={loadAiCosts}
          totalVideos={videos.length}
          readyVideos={videosProntos}
          activeVideos={videosAtivos}
          errorVideos={videosErro}
          trackedSpend={gastoRastreado}
          averageCost={custoMedio}
          currency={currency}
          balance={provider?.remainingBalance ?? null}
          claudeProvider={claudeProvider}
        />
      </section>

      <section className="mt-4 grid gap-4 xl:grid-cols-[1.25fr_0.75fr]">
        <div className="rounded-lg border bg-card shadow-sm">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <div>
              <h2 className="font-display text-sm font-semibold">Vídeos recentes</h2>
              <p className="text-[11px] text-muted-foreground">
                Últimas criações no HeyGen, com status e custo rastreado.
              </p>
            </div>
            <Button asChild size="sm" variant="ghost">
              <Link to="/producao">Ver produção</Link>
            </Button>
          </div>
          {videos.length === 0 ? (
            <EmptyState
              className="m-3"
              icon={<Film className="h-4 w-4" />}
              title="Nenhum vídeo criado"
              description="Quando um roteiro for enviado ao HeyGen, ele aparece aqui."
            />
          ) : (
            <div className="divide-y">
              {videos.slice(0, 6).map((job) => (
                <VideoRow key={job.id} job={job} currency={currency} />
              ))}
            </div>
          )}
        </div>

        <div className="rounded-lg border bg-card shadow-sm">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <div>
              <h2 className="font-display text-sm font-semibold">Próximas publicações</h2>
              <p className="text-[11px] text-muted-foreground">Agenda editorial mais próxima.</p>
            </div>
            <Button asChild size="sm" variant="ghost">
              <Link to="/calendario">Abrir</Link>
            </Button>
          </div>
          {proximosPosts.length === 0 ? (
            <EmptyState
              className="m-3"
              icon={<CalendarClock className="h-4 w-4" />}
              title="Sem agendamentos"
              description="Agende vídeos prontos para manter a cadência."
            />
          ) : (
            <div className="divide-y">
              {proximosPosts.map((post) => (
                <div key={post.id} className="flex items-center justify-between gap-3 px-4 py-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{post.titulo}</p>
                    <p className="text-xs text-muted-foreground">
                      {post.canal.replace("_", " ")} ·{" "}
                      {new Date(post.dataAgendada).toLocaleDateString("pt-BR")}
                    </p>
                  </div>
                  <StatusBadge {...postStatusLabel[post.status]} />
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </AppShell>
  );
}

function VideoCostPanel({
  aiCosts,
  error,
  loading,
  onRefresh,
  totalVideos,
  readyVideos,
  activeVideos,
  errorVideos,
  trackedSpend,
  averageCost,
  currency,
  balance,
  claudeProvider,
}: {
  aiCosts: AiCosts | null;
  error: string;
  loading: boolean;
  onRefresh: () => void | Promise<void>;
  totalVideos: number;
  readyVideos: number;
  activeVideos: number;
  errorVideos: number;
  trackedSpend: number;
  averageCost: number;
  currency: string;
  balance: number | null;
  claudeProvider?: AiCosts["providers"][number];
}) {
  const claudeInputTokens = claudeProvider?.inputTokens ?? 0;
  const claudeOutputTokens = claudeProvider?.outputTokens ?? 0;
  const claudeCacheReadTokens = claudeProvider?.cacheReadTokens ?? 0;
  const claudeCacheWriteTokens = claudeProvider?.cacheWriteTokens ?? 0;
  const claudeTotalTokens =
    claudeInputTokens + claudeOutputTokens + claudeCacheReadTokens + claudeCacheWriteTokens;
  const formatTokens = (value: number) => value.toLocaleString("pt-BR");

  return (
    <div className="rounded-lg border bg-card p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-base font-semibold">Vídeos e custos</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            HeyGen, Claude e gastos rastreados no projeto.
          </p>
        </div>
        <Button size="sm" variant="secondary" onClick={() => void onRefresh()} disabled={loading}>
          {loading ? (
            <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCcw className="mr-1 h-3.5 w-3.5" />
          )}
          Atualizar
        </Button>
      </div>

      {error ? <p className="mt-3 text-xs text-destructive">{error}</p> : null}

      <div className="mt-4 grid grid-cols-2 gap-2">
        <SummaryTile label="Criados" value={totalVideos} />
        <SummaryTile label="Prontos" value={readyVideos} />
        <SummaryTile label="Em produção" value={activeVideos} />
        <SummaryTile label="Com erro" value={errorVideos} muted={errorVideos === 0} />
      </div>

      <div className="mt-4 rounded-md border bg-muted/30 p-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <WalletCards className="h-4 w-4 text-status-info" />
            <span className="text-xs font-medium">HeyGen — créditos de vídeo</span>
          </div>
          <span className="font-display text-lg font-semibold tabular-nums">
            {formatCurrency(trackedSpend, currency)}
          </span>
        </div>
        <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] text-muted-foreground">
          <span>Custo médio por vídeo: {formatCurrency(averageCost, currency)}</span>
          <span className="text-right">
            Saldo: {balance == null ? "indisponível" : formatCurrency(balance, currency)}
          </span>
        </div>
      </div>

      <div className="mt-3 rounded-md border border-status-info/25 bg-status-info/5 p-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs font-medium">Claude — tokens usados</p>
            <p className="text-[11px] text-muted-foreground">
              {claudeProvider?.status === "conectado"
                ? "Uso registrado pela API"
                : "API não conectada"}
            </p>
          </div>
          <div className="text-right">
            <span className="block font-display text-lg font-semibold tabular-nums">
              {formatTokens(claudeTotalTokens)}
            </span>
            <span className="text-[10px] text-muted-foreground">tokens no total</span>
          </div>
        </div>
        <div className="mt-3 grid grid-cols-3 gap-2 text-[11px] text-muted-foreground">
          <span>Entrada: {formatTokens(claudeInputTokens)}</span>
          <span>Saída: {formatTokens(claudeOutputTokens)}</span>
          <span className="text-right">Chamadas: {claudeProvider?.calls ?? 0}</span>
        </div>
        {(claudeCacheReadTokens > 0 || claudeCacheWriteTokens > 0) ? (
          <div className="mt-1 grid grid-cols-2 gap-2 text-[10px] text-muted-foreground">
            <span>Cache lido: {formatTokens(claudeCacheReadTokens)}</span>
            <span className="text-right">Cache criado: {formatTokens(claudeCacheWriteTokens)}</span>
          </div>
        ) : null}
        <div className="mt-2 flex items-center justify-between gap-2 border-t border-status-info/15 pt-2 text-[11px] text-muted-foreground">
          <span>Custo estimado</span>
          <span className="font-medium tabular-nums text-foreground">
            {formatCurrency(claudeProvider?.trackedSpend ?? 0, claudeProvider?.currency || "USD")}
          </span>
        </div>
        <p className="mt-2 text-[10px] leading-4 text-muted-foreground">
          Estimativa por tokens retornados. Respostas repetidas são reaproveitadas pelo cache e não
          geram nova chamada.
        </p>
      </div>

      {aiCosts?.updatedAt ? (
        <p className="mt-3 text-[11px] text-muted-foreground">
          Atualizado em {new Date(aiCosts.updatedAt).toLocaleString("pt-BR")}.
        </p>
      ) : null}
    </div>
  );
}

function SummaryTile({
  label,
  value,
  muted = false,
}: {
  label: string;
  value: number;
  muted?: boolean;
}) {
  return (
    <div className="rounded-md border bg-background px-3 py-2">
      <div
        className={`font-display text-xl font-semibold tabular-nums ${muted ? "opacity-45" : ""}`}
      >
        {value}
      </div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
    </div>
  );
}

function VideoRow({ job, currency }: { job: CostedVideoJob; currency: string }) {
  return (
    <Link
      to="/producao/$id"
      params={{ id: job.id }}
      className="flex items-center justify-between gap-3 px-4 py-3 transition-colors hover:bg-muted/35"
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <VideoStatusDot status={job.status} />
          <p className="truncate text-sm font-medium">{videoStatusLabel[job.status]}</p>
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {new Date(job.atualizadoEm || job.criadoEm).toLocaleString("pt-BR")}
          {job.duracaoSegundos ? ` · ${job.duracaoSegundos}s` : ""}
        </p>
      </div>
      <div className="shrink-0 text-right">
        <p className="text-sm font-medium tabular-nums">
          {job.costUsd && job.costUsd > 0
            ? formatCurrency(job.costUsd, job.currency || currency)
            : job.status === "fila" || job.status === "processando"
              ? "Aguardando custo"
              : "Custo não rastreado"}
        </p>
        <p className="text-[11px] text-muted-foreground">{job.provider}</p>
      </div>
    </Link>
  );
}

function VideoStatusDot({ status }: { status: VideoJobStatus }) {
  const color =
    status === "pronto"
      ? "bg-status-success"
      : status === "erro"
        ? "bg-status-danger"
        : "bg-status-warn";
  return <span className={`h-2 w-2 rounded-full ${color}`} />;
}

const videoStatusLabel: Record<VideoJobStatus, string> = {
  fila: "Na fila",
  processando: "Processando",
  pronto: "Vídeo pronto",
  erro: "Erro na produção",
};

function ActionCard({
  item,
}: {
  item: {
    count: number;
    title: string;
    action: string;
    to: string;
    icon: typeof Radar;
    tone: "info" | "warn";
  };
}) {
  const Icon = item.icon;
  const tone =
    item.tone === "warn"
      ? "border-status-warn/35 hover:border-status-warn/70"
      : "border-status-info/30 hover:border-status-info/60";
  return (
    <Link
      to={item.to}
      className={`group flex items-center gap-3 rounded-md border bg-background px-3 py-3 transition-colors hover:bg-muted/30 ${tone}`}
    >
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-muted">
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">
          <span className="font-display text-lg font-semibold tabular-nums">{item.count}</span>{" "}
          {item.title}
        </p>
        <p className="truncate text-xs text-muted-foreground">{item.action}</p>
      </div>
      <ArrowRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
    </Link>
  );
}

function formatCurrency(value: number, currency: string): string {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency }).format(value);
}
