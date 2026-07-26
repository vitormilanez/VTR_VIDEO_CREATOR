import { createFileRoute, Link, Outlet } from "@tanstack/react-router";
import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { DataToolbar } from "@/components/data-toolbar";
import { EmptyState } from "@/components/empty-state";
import { StatusChips } from "@/components/status-chips";
import { familiaLabel, riskLabel, scriptStatusLabel } from "@/lib/status";
import { useStore } from "@/lib/store";
import type { ScriptStatus } from "@/lib/mock-data";
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
import { CircleCheck, ExternalLink, FileText, PanelsTopLeft } from "lucide-react";

export const Route = createFileRoute("/_app/roteiros")({
  head: () => ({
    meta: [
      { title: "Roteiros | AI Video Creator" },
      { name: "description", content: "Roteiros com validacao medica antes da producao." },
      { property: "og:title", content: "Roteiros | AI Video Creator" },
      { property: "og:description", content: "Fila de roteiros medicos." },
    ],
  }),
  component: RoteirosLayout,
});

function RoteirosLayout() {
  return <Outlet />;
}

export function RoteirosPage() {
  const scripts = useStore((s) => s.scripts);
  const videoJobs = useStore((s) => s.videoJobs);
  const [status, setStatus] = useState("todos");
  const [prioridade, setPrioridade] = useState("todas");
  const [busca, setBusca] = useState("");

  const filtered = scripts.filter((s) => {
    if (status !== "todos" && s.status !== status) return false;
    if (prioridade !== "todas" && s.prioridade !== prioridade) return false;
    const searchable = [s.titulo, s.tema, s.hook, s.cuidadosMedicos].join(" ").toLowerCase();
    if (busca && !searchable.includes(busca.toLowerCase())) return false;
    return true;
  });

  const ordered = [...filtered].sort(
    (a, b) => new Date(b.criadoEm).getTime() - new Date(a.criadoEm).getTime(),
  );

  const counts: Record<ScriptStatus, number> = {
    aguardando_validacao: 0,
    em_revisao: 0,
    aprovado_clinicamente: 0,
    rejeitado: 0,
  };
  scripts.forEach((s) => (counts[s.status] += 1));
  const usedScriptIds = new Set(
    videoJobs.filter((job) => job.status !== "erro").map((job) => job.scriptId),
  );
  const usedCount = scripts.filter((script) => usedScriptIds.has(script.id)).length;

  return (
    <AppShell title="Roteiros">
      {usedCount > 0 ? (
        <div className="mb-3 flex items-center gap-2 rounded-md border border-status-success/30 bg-status-success/5 px-3 py-2 text-xs">
          <CircleCheck className="h-4 w-4 shrink-0 text-status-success" />
          <span>
            {usedCount === 1
              ? "1 roteiro já foi utilizado em vídeo. Ele está identificado na lista."
              : `${usedCount} roteiros já foram utilizados em vídeos. Eles estão identificados na lista.`}
          </span>
        </div>
      ) : null}
      <StatusChips
        className="mb-3"
        value={status}
        onChange={setStatus}
        options={[
          {
            value: "aguardando_validacao",
            label: "Rascunho",
            tone: "neutral",
            count: counts.aguardando_validacao,
          },
          { value: "em_revisao", label: "Em edicao", tone: "info", count: counts.em_revisao },
          {
            value: "aprovado_clinicamente",
            label: "Prontos",
            tone: "success",
            count: counts.aprovado_clinicamente,
          },
          { value: "rejeitado", label: "Arquivados", tone: "neutral", count: counts.rejeitado },
        ]}
      />
      <DataToolbar search={busca} onSearch={setBusca} placeholder="Buscar roteiro...">
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

      {ordered.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-4 w-4" />}
          title="Nenhum roteiro encontrado"
          description="Gere um a partir de uma ideia."
          action={
            <Button asChild size="sm" variant="secondary">
              <Link to="/ideias">Ir para Ideias</Link>
            </Button>
          }
        />
      ) : (
        <div className="rounded-xl border bg-card shadow-sm">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[30%]">Titulo</TableHead>
                <TableHead>Formato</TableHead>
                <TableHead>Cuidados medicos</TableHead>
                <TableHead>Risco</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Acoes</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ordered.map((s) => (
                <TableRow key={s.id}>
                  <TableCell>
                    <Link
                      to="/roteiros/$id"
                      params={{ id: s.id }}
                      className="font-medium hover:underline"
                    >
                      {s.titulo}
                    </Link>
                    <div className="mt-1 flex flex-wrap items-center gap-1">
                      <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                        {familiaLabel[s.categoria]}
                      </span>
                      {s.tema ? (
                        <span className="text-[10px] text-muted-foreground">{s.tema}</span>
                      ) : null}
                      {usedScriptIds.has(s.id) ? (
                        <Badge
                          variant="outline"
                          className="h-5 border-status-success/40 px-1.5 text-[10px] text-status-success"
                        >
                          <CircleCheck className="mr-1 h-3 w-3" />
                          Vídeo produzido
                        </Badge>
                      ) : null}
                    </div>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {s.formatoSugerido}
                  </TableCell>
                  <TableCell className="max-w-xs">
                    <span className="line-clamp-2 text-xs text-muted-foreground">
                      {s.cuidadosMedicos || "—"}
                    </span>
                  </TableCell>
                  <TableCell>
                    <StatusBadge {...riskLabel[s.risco]} />
                  </TableCell>
                  <TableCell>
                    <StatusBadge {...scriptStatusLabel[s.status]} />
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button asChild size="sm" variant="secondary">
                        <Link to="/packs" search={{ scriptId: s.id }}>
                          <PanelsTopLeft className="mr-1 h-3.5 w-3.5" /> Pack
                        </Link>
                      </Button>
                      <Button asChild size="sm" variant="ghost">
                        <Link to="/roteiros/$id" params={{ id: s.id }}>
                          <ExternalLink className="h-3.5 w-3.5" />
                        </Link>
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </AppShell>
  );
}
