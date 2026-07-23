import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/app-shell";
import { MetricCard } from "@/components/metric-card";
import { EmptyState } from "@/components/empty-state";
import { canalLabel } from "@/lib/status";
import { useStore } from "@/lib/store";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { BarChart3, Eye, MessageCircle, Share2, Bookmark, UserPlus } from "lucide-react";

export const Route = createFileRoute("/_app/performance")({
  head: () => ({
    meta: [
      { title: "Performance | AI Video Creator" },
      { name: "description", content: "Metricas por post da aba Performance." },
      { property: "og:title", content: "Performance | AI Video Creator" },
      { property: "og:description", content: "Metricas de reels publicados." },
    ],
  }),
  component: PerformancePage,
});

function PerformancePage() {
  const metrics = useStore((s) => s.performance);
  const metaOn = useStore((s) => s.settings.integracoes.meta);

  const totals = metrics.reduce(
    (acc, m) => {
      acc.views += m.views;
      acc.comments += m.comments;
      acc.shares += m.shares;
      acc.saves += m.saves;
      acc.novosSeguidores += m.novosSeguidores ?? 0;
      return acc;
    },
    { views: 0, comments: 0, shares: 0, saves: 0, novosSeguidores: 0 },
  );

  const fmt = (n: number) => n.toLocaleString("pt-BR");

  return (
    <AppShell title="Performance">
      {!metaOn && (
        <div className="mb-3 flex items-start gap-2 rounded-md border border-status-info/40 bg-status-info/10 p-3 text-xs">
          <BarChart3 className="mt-0.5 h-4 w-4 text-status-info" />
          <div>
            Metricas vindas da aba <strong>Performance</strong> do Google Sheets. A coleta
            automatica via Meta ainda nao esta conectada.
          </div>
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <MetricCard
          label="Views"
          value={fmt(totals.views)}
          icon={<Eye className="h-4 w-4" />}
          tone="info"
        />
        <MetricCard
          label="Comentarios"
          value={fmt(totals.comments)}
          icon={<MessageCircle className="h-4 w-4" />}
        />
        <MetricCard
          label="Compartilhamentos"
          value={fmt(totals.shares)}
          icon={<Share2 className="h-4 w-4" />}
          tone="success"
        />
        <MetricCard
          label="Salvamentos"
          value={fmt(totals.saves)}
          icon={<Bookmark className="h-4 w-4" />}
          tone="warn"
        />
        <MetricCard
          label="Novos seguidores"
          value={fmt(totals.novosSeguidores)}
          icon={<UserPlus className="h-4 w-4" />}
          tone="danger"
        />
      </div>

      <div className="mt-6 rounded-xl border bg-card shadow-sm">
        <div className="border-b px-4 py-2.5 font-display text-sm font-semibold">
          Metricas por post
        </div>
        {metrics.length === 0 ? (
          <EmptyState
            className="m-3"
            icon={<BarChart3 className="h-4 w-4" />}
            title="Sem metricas registradas"
            description="Preencha a aba Performance na planilha para acompanhar aqui."
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tema</TableHead>
                <TableHead>Canal</TableHead>
                <TableHead className="text-right">Views</TableHead>
                <TableHead className="text-right">Retencao</TableHead>
                <TableHead className="text-right">Coment.</TableHead>
                <TableHead className="text-right">Salv.</TableHead>
                <TableHead className="text-right">Compart.</TableHead>
                <TableHead className="text-right">Novos seg.</TableHead>
                <TableHead className="text-right">Cliques</TableHead>
                <TableHead className="text-right">Leads</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {metrics.map((m) => (
                <TableRow key={m.id}>
                  <TableCell className="font-medium">{m.tema || "—"}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {m.canal ? canalLabel[m.canal] : "—"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{fmt(m.views)}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {m.retencao != null ? `${m.retencao}%` : "—"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{fmt(m.comments)}</TableCell>
                  <TableCell className="text-right tabular-nums">{fmt(m.saves)}</TableCell>
                  <TableCell className="text-right tabular-nums">{fmt(m.shares)}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {fmt(m.novosSeguidores ?? 0)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{fmt(m.cliques ?? 0)}</TableCell>
                  <TableCell className="text-right tabular-nums">{fmt(m.leads ?? 0)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </AppShell>
  );
}
