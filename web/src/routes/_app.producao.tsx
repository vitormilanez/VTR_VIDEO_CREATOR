import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { EmptyState } from "@/components/empty-state";
import { StatusChips } from "@/components/status-chips";
import { WithTooltip } from "@/components/with-tooltip";
import { videoJobStatusLabel } from "@/lib/status";
import { useStore } from "@/lib/store";
import type { VideoJobStatus } from "@/lib/mock-data";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ExternalLink, Film, PlayCircle } from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute("/_app/producao")({
  head: () => ({
    meta: [
      { title: "Producao de videos | AI Video Creator" },
      { name: "description", content: "Fila de producao HeyGen (mock)." },
      { property: "og:title", content: "Producao de videos | AI Video Creator" },
      { property: "og:description", content: "Fila HeyGen para reels medicos." },
    ],
  }),
  component: ProducaoPage,
});

function ProducaoPage() {
  const jobs = useStore((s) => s.videoJobs);
  const scripts = useStore((s) => s.scripts);
  const advance = useStore((s) => s.advanceVideoJob);
  const [status, setStatus] = useState("todos");

  const counts: Record<VideoJobStatus, number> = { fila: 0, processando: 0, pronto: 0, erro: 0 };
  jobs.forEach((j) => (counts[j.status] += 1));

  const filtered = jobs.filter((j) => status === "todos" || j.status === status);

  return (
    <AppShell
      title="Producao de videos"
      actions={
        <div className="text-[11px] text-muted-foreground">
          Modo mockado — nenhum credito HeyGen consumido.
        </div>
      }
    >
      <StatusChips
        className="mb-3"
        value={status}
        onChange={setStatus}
        options={[
          { value: "fila", label: "Na fila", tone: "info", count: counts.fila },
          { value: "processando", label: "Processando", tone: "warn", count: counts.processando },
          { value: "pronto", label: "Prontos", tone: "success", count: counts.pronto },
          { value: "erro", label: "Erro", tone: "danger", count: counts.erro },
        ]}
      />

      {filtered.length === 0 ? (
        <EmptyState
          icon={<Film className="h-4 w-4" />}
          title="Nenhum video nesta lista"
          description="Aprove clinicamente um roteiro e envie para producao."
          action={
            <Button asChild size="sm" variant="secondary">
              <Link to="/roteiros">Ir para Roteiros</Link>
            </Button>
          }
        />
      ) : (
        <div className="rounded-xl border bg-card shadow-sm">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Roteiro</TableHead>
                <TableHead>Provider</TableHead>
                <TableHead>Progresso</TableHead>
                <TableHead>Atualizado</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Acoes</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((j) => {
                const s = scripts.find((x) => x.id === j.scriptId);
                return (
                  <TableRow key={j.id}>
                    <TableCell className="font-medium">
                      <Link
                        to="/producao/$id"
                        params={{ id: j.id }}
                        className="hover:underline"
                      >
                        {s ? s.titulo : "—"}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{j.provider}</TableCell>
                    <TableCell className="min-w-[140px]">
                      <div className="flex items-center gap-2">
                        <Progress value={j.progresso} className="h-1.5" />
                        <span className="w-8 text-right text-[11px] tabular-nums text-muted-foreground">
                          {j.progresso}%
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      {new Date(j.atualizadoEm).toLocaleString("pt-BR")}
                    </TableCell>
                    <TableCell><StatusBadge {...videoJobStatusLabel[j.status]} /></TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <WithTooltip
                          label={
                            j.status === "pronto"
                              ? "Video ja esta pronto"
                              : "Avancar status (mock)"
                          }
                        >
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={j.status === "pronto"}
                            onClick={() => {
                              try {
                                const next = advance(j.id);
                                if (next)
                                  toast.success(
                                    `Status: ${videoJobStatusLabel[next].label}`,
                                  );
                              } catch {
                                toast.error("Falha ao avancar o video.");
                              }
                            }}
                          >
                            <PlayCircle className="mr-1 h-3.5 w-3.5" /> Avancar
                          </Button>
                        </WithTooltip>
                        <Button asChild size="sm" variant="ghost" title="Abrir detalhe do video">
                          <Link to="/producao/$id" params={{ id: j.id }}>
                            <ExternalLink className="h-3.5 w-3.5" />
                          </Link>
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </AppShell>
  );
}
