import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { StatusTimeline, type TimelineStep } from "@/components/status-timeline";
import { WithTooltip } from "@/components/with-tooltip";
import { ConfirmAction } from "@/components/confirm-action";
import { videoJobStatusLabel, canalLabel } from "@/lib/status";
import { useStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ArrowLeft, CalendarPlus, Film, PlayCircle } from "lucide-react";
import type { Canal, VideoJobStatus } from "@/lib/mock-data";
import { toast } from "sonner";

export const Route = createFileRoute("/_app/producao/$id")({
  head: ({ params }) => ({
    meta: [{ title: `Video ${params.id} | AI Video Creator` }],
  }),
  component: VideoDetalhe,
});

function VideoDetalhe() {
  const { id } = Route.useParams();
  const job = useStore((s) => s.videoJobs.find((v) => v.id === id));
  const script = useStore((s) => (job ? s.scripts.find((x) => x.id === job.scriptId) : undefined));
  const advance = useStore((s) => s.advanceVideoJob);
  const agendar = useStore((s) => s.agendarPost);
  const navigate = useNavigate();

  const [open, setOpen] = useState(false);
  const [data, setData] = useState("");
  const [canal, setCanal] = useState<Canal>("instagram");

  if (!job) {
    return (
      <AppShell title="Video">
        <p className="text-sm text-muted-foreground">
          Video nao encontrado.{" "}
          <Link to="/producao" className="text-status-info underline">Voltar</Link>
        </p>
      </AppShell>
    );
  }

  const timeline = buildVideoTimeline(job.status, {
    criadoEm: job.criadoEm,
    atualizadoEm: job.atualizadoEm,
  });

  return (
    <AppShell
      title={script?.titulo ?? `Video ${job.id}`}
      actions={
        <>
          <Button variant="ghost" size="sm" asChild>
            <Link to="/producao"><ArrowLeft className="mr-1 h-4 w-4" /> Voltar</Link>
          </Button>
          <WithTooltip label={job.status === "pronto" ? "Video ja concluido" : "Avancar status mockado"}>
            <Button
              size="sm"
              variant="secondary"
              disabled={job.status === "pronto"}
              onClick={() => {
                try {
                  const next = advance(job.id);
                  if (next) toast.success(`Status: ${videoJobStatusLabel[next].label}`);
                } catch {
                  toast.error("Falha ao avancar status.");
                }
              }}
            >
              <PlayCircle className="mr-1 h-4 w-4" /> Avancar status
            </Button>
          </WithTooltip>
          <Dialog open={open} onOpenChange={setOpen}>
            <WithTooltip
              label={job.status === "pronto" ? "Agendar publicacao no calendario" : "Disponivel quando o video estiver pronto"}
            >
              <DialogTrigger asChild>
                <Button size="sm" disabled={job.status !== "pronto"}>
                  <CalendarPlus className="mr-1 h-4 w-4" /> Agendar publicacao
                </Button>
              </DialogTrigger>
            </WithTooltip>
            <DialogContent>
              <DialogHeader><DialogTitle>Agendar publicacao</DialogTitle></DialogHeader>
              <div className="grid gap-3">
                <div>
                  <Label>Data</Label>
                  <Input type="date" value={data} onChange={(e) => setData(e.target.value)} />
                </div>
                <div>
                  <Label>Canal</Label>
                  <Select value={canal} onValueChange={(v) => setCanal(v as Canal)}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="instagram">Instagram</SelectItem>
                      <SelectItem value="tiktok">TikTok</SelectItem>
                      <SelectItem value="youtube_shorts">YouTube Shorts</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <DialogFooter>
                <Button variant="ghost" onClick={() => setOpen(false)}>Cancelar</Button>
                <ConfirmAction
                  title="Agendar esta publicacao?"
                  description={`O post sera agendado para ${data || "..."} no canal ${canalLabel[canal]}.`}
                  confirmLabel="Agendar"
                  onConfirm={() => {
                    if (!script || !data) return;
                    try {
                      agendar({
                        scriptId: script.id,
                        videoJobId: job.id,
                        titulo: script.titulo,
                        dataAgendada: new Date(`${data}T12:00:00`).toISOString(),
                        canal,
                      });
                      toast.success("Publicacao agendada.");
                      setOpen(false);
                      navigate({ to: "/calendario" });
                    } catch {
                      toast.error("Nao foi possivel agendar.");
                    }
                  }}
                  trigger={
                    <Button disabled={!data || !script}>Agendar</Button>
                  }
                />
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </>
      }
    >
      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge {...videoJobStatusLabel[job.status]} />
            <span className="text-xs text-muted-foreground">Provider: {job.provider}</span>
          </div>

          <div className="rounded-xl border bg-card p-4 shadow-sm">
            <div className="mb-2 flex items-center justify-between">
              <div className="font-display text-sm font-semibold">Progresso</div>
              <div className="tabular-nums text-sm">{job.progresso}%</div>
            </div>
            <Progress value={job.progresso} />
            <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
              <Info label="Criado em" value={new Date(job.criadoEm).toLocaleString("pt-BR")} />
              <Info label="Atualizado em" value={new Date(job.atualizadoEm).toLocaleString("pt-BR")} />
              {job.duracaoSegundos ? <Info label="Duracao" value={`${job.duracaoSegundos}s`} /> : null}
              {job.videoUrl ? <Info label="Arquivo" value={job.videoUrl} /> : null}
            </div>
          </div>

          <div className="rounded-xl border bg-card p-4 shadow-sm">
            <h3 className="mb-2 font-display text-sm font-semibold">Preview (mock)</h3>
            <div className="flex aspect-[9/16] max-w-[240px] items-center justify-center rounded-lg bg-linear-to-br from-primary/30 via-primary/10 to-transparent text-primary">
              <Film className="h-10 w-10" />
            </div>
            <p className="mt-2 text-[11px] text-muted-foreground">
              Preview real disponivel apos integracao com HeyGen.
            </p>
          </div>
        </div>

        <aside className="space-y-3">
          <div className="rounded-xl border bg-card p-4 shadow-sm">
            <h3 className="mb-3 font-display text-sm font-semibold">Timeline</h3>
            <StatusTimeline steps={timeline} />
          </div>
          <div className="rounded-xl border bg-card p-3 shadow-sm">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Roteiro origem
            </div>
            {script ? (
              <Link to="/roteiros/$id" params={{ id: script.id }} className="text-sm font-medium hover:underline">
                {script.titulo}
              </Link>
            ) : (
              <span className="text-sm text-muted-foreground">—</span>
            )}
          </div>
        </aside>
      </div>
    </AppShell>
  );
}

function buildVideoTimeline(
  status: VideoJobStatus,
  ts: { criadoEm: string; atualizadoEm: string },
): TimelineStep[] {
  const fmt = (iso?: string) => (iso ? new Date(iso).toLocaleString("pt-BR") : undefined);
  if (status === "erro") {
    return [
      { key: "fila", label: "Na fila", state: "done", timestamp: fmt(ts.criadoEm) },
      { key: "erro", label: "Erro na producao", state: "error", timestamp: fmt(ts.atualizadoEm) },
    ];
  }
  const order: VideoJobStatus[] = ["fila", "processando", "pronto"];
  const idx = order.indexOf(status);
  const labels: Record<VideoJobStatus, string> = {
    fila: "Na fila do HeyGen",
    processando: "Processando video",
    pronto: "Video pronto",
    erro: "Erro",
  };
  return order.map((k, i) => {
    const state: TimelineStep["state"] =
      i < idx ? "done" : i === idx ? "current" : "pending";
    const step: TimelineStep = { key: k, label: labels[k], state };
    if (k === "fila" && (state === "done" || state === "current")) step.timestamp = fmt(ts.criadoEm);
    if (k === status) step.timestamp = fmt(ts.atualizadoEm);
    return step;
  });
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="truncate">{value}</div>
    </div>
  );
}
