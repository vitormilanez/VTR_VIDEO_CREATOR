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
import { BarChart3, Eye, Heart, MessageCircle, Share2, Bookmark } from "lucide-react";

export const Route = createFileRoute("/_app/performance")({
  head: () => ({
    meta: [
      { title: "Performance | AI Video Creator" },
      { name: "description", content: "Metricas por post publicado (mock)." },
      { property: "og:title", content: "Performance | AI Video Creator" },
      { property: "og:description", content: "Metricas de reels publicados." },
    ],
  }),
  component: PerformancePage,
});

function PerformancePage() {
  const posts = useStore((s) => s.calendarPosts);
  const metrics = useStore((s) => s.performance);
  const metaOn = useStore((s) => s.settings.integracoes.meta);
  const registrar = useStore((s) => s.registrarMetricasFake);

  const publicados = posts.filter((p) => p.status === "publicado");
  const totals = metrics.reduce(
    (acc, m) => {
      acc.views += m.views;
      acc.likes += m.likes;
      acc.comments += m.comments;
      acc.shares += m.shares;
      acc.saves += m.saves;
      return acc;
    },
    { views: 0, likes: 0, comments: 0, shares: 0, saves: 0 },
  );

  return (
    <AppShell title="Performance">
      {!metaOn && (
        <div className="mb-3 flex items-start gap-2 rounded-md border border-status-warn/40 bg-status-warn/10 p-3 text-xs">
          <BarChart3 className="mt-0.5 h-4 w-4 text-status-warn-foreground" />
          <div>
            Modo mockado — metricas geradas localmente. Ative a integracao Meta em
            Configuracoes para usar dados reais.
          </div>
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <MetricCard label="Views" value={totals.views.toLocaleString("pt-BR")} icon={<Eye className="h-4 w-4" />} tone="info" />
        <MetricCard label="Likes" value={totals.likes.toLocaleString("pt-BR")} icon={<Heart className="h-4 w-4" />} tone="danger" />
        <MetricCard label="Comentarios" value={totals.comments.toLocaleString("pt-BR")} icon={<MessageCircle className="h-4 w-4" />} />
        <MetricCard label="Compartilhamentos" value={totals.shares.toLocaleString("pt-BR")} icon={<Share2 className="h-4 w-4" />} tone="success" />
        <MetricCard label="Saves" value={totals.saves.toLocaleString("pt-BR")} icon={<Bookmark className="h-4 w-4" />} tone="warn" />
      </div>

      <div className="mt-6 rounded-xl border bg-card shadow-sm">
        <div className="border-b px-4 py-2.5 font-display text-sm font-semibold">
          Metricas por post publicado
        </div>
        {publicados.length === 0 ? (
          <EmptyState className="m-3" icon={<BarChart3 className="h-4 w-4" />} title="Sem posts publicados" description="Marque um post como publicado no Calendario." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Post</TableHead>
                <TableHead>Canal</TableHead>
                <TableHead className="text-right">Views</TableHead>
                <TableHead className="text-right">Likes</TableHead>
                <TableHead className="text-right">Coment.</TableHead>
                <TableHead className="text-right">Compart.</TableHead>
                <TableHead className="text-right">Saves</TableHead>
                <TableHead className="text-right">Acoes</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {publicados.map((p) => {
                const m = metrics.find((x) => x.postId === p.id);
                return (
                  <TableRow key={p.id}>
                    <TableCell className="font-medium">{p.titulo}</TableCell>
                    <TableCell className="text-muted-foreground">{canalLabel[p.canal]}</TableCell>
                    <TableCell className="text-right tabular-nums">{m?.views.toLocaleString("pt-BR") ?? 0}</TableCell>
                    <TableCell className="text-right tabular-nums">{m?.likes.toLocaleString("pt-BR") ?? 0}</TableCell>
                    <TableCell className="text-right tabular-nums">{m?.comments.toLocaleString("pt-BR") ?? 0}</TableCell>
                    <TableCell className="text-right tabular-nums">{m?.shares.toLocaleString("pt-BR") ?? 0}</TableCell>
                    <TableCell className="text-right tabular-nums">{m?.saves.toLocaleString("pt-BR") ?? 0}</TableCell>
                    <TableCell className="text-right">
                      <button
                        onClick={() => registrar(p.id)}
                        className="text-[11px] text-status-info hover:underline"
                      >
                        Registrar novas metricas
                      </button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </div>
    </AppShell>
  );
}
