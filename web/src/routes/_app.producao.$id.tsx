import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { StatusTimeline, type TimelineStep } from "@/components/status-timeline";
import { WithTooltip } from "@/components/with-tooltip";
import { ConfirmAction } from "@/components/confirm-action";
import { videoJobStatusLabel, canalLabel } from "@/lib/status";
import { useStore } from "@/lib/store";
import {
  appendCalendarPost,
  publishVideoToInstagram,
  refreshHeyGenVideo,
  videoDownloadUrl,
} from "@/lib/api/local";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
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
import {
  ArrowLeft,
  CalendarPlus,
  Check,
  Copy,
  Download,
  ExternalLink,
  Film,
  Instagram,
  Loader2,
  RefreshCcw,
} from "lucide-react";
import type { Canal, Script, VideoJobStatus } from "@/lib/mock-data";
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
  const updateVideoJob = useStore((s) => s.updateVideoJob);
  const addCalendarPost = useStore((s) => s.addCalendarPost);
  const navigate = useNavigate();

  const [open, setOpen] = useState(false);
  const [data, setData] = useState("");
  const [canal, setCanal] = useState<Canal>("instagram");
  const [scheduling, setScheduling] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);
  const [instagramFormat, setInstagramFormat] = useState<"REELS" | "STORIES">("REELS");
  const [instagramCaption, setInstagramCaption] = useState(() =>
    script ? buildReelCaption(script) : "",
  );
  const [captionCopied, setCaptionCopied] = useState(false);
  const [shareToFeed, setShareToFeed] = useState(true);
  const [publishing, setPublishing] = useState(false);

  useEffect(() => {
    if (!script) return;
    const storageKey = reelCaptionStorageKey(job?.id ?? id);
    const savedCaption = window.localStorage.getItem(storageKey);
    setInstagramCaption(savedCaption || buildReelCaption(script));
  }, [id, job?.id, script]);

  function updateInstagramCaption(value: string) {
    const next = value.slice(0, 2200);
    setInstagramCaption(next);
    window.localStorage.setItem(reelCaptionStorageKey(job?.id ?? id), next);
  }

  async function copyInstagramCaption() {
    if (!instagramCaption.trim()) return;
    try {
      await navigator.clipboard.writeText(instagramCaption);
      setCaptionCopied(true);
      toast.success("Legenda copiada. Pronta para colar no Reel.");
      window.setTimeout(() => setCaptionCopied(false), 1800);
    } catch {
      toast.error("Não foi possível copiar a legenda.");
    }
  }

  if (!job) {
    return (
      <AppShell title="Video">
        <p className="text-sm text-muted-foreground">
          Video nao encontrado.{" "}
          <Link to="/producao" className="text-status-info underline">
            Voltar
          </Link>
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
            <Link to="/producao">
              <ArrowLeft className="mr-1 h-4 w-4" /> Voltar
            </Link>
          </Button>
          <WithTooltip label="Consultar status no HeyGen">
            <Button
              size="sm"
              variant="secondary"
              onClick={async () => {
                try {
                  const updated = await refreshHeyGenVideo(job.id);
                  updateVideoJob(job.id, updated);
                  toast.success(`Status: ${videoJobStatusLabel[updated.status].label}`);
                } catch (err) {
                  toast.error(err instanceof Error ? err.message : "Falha ao consultar o HeyGen.");
                }
              }}
            >
              <RefreshCcw className="mr-1 h-4 w-4" /> Atualizar status
            </Button>
          </WithTooltip>
          {script ? (
            <Button size="sm" variant="secondary" asChild>
              <Link to="/roteiros/$id" params={{ id: script.id }}>
                <Film className="mr-1 h-4 w-4" /> Refazer vídeo
              </Link>
            </Button>
          ) : null}
          {job.videoUrl ? (
            <Button size="sm" variant="secondary" asChild>
              <a href={videoDownloadUrl(job.id)}>
                <Download className="mr-1 h-4 w-4" />
                Baixar vídeo
              </a>
            </Button>
          ) : null}
          <Dialog open={publishOpen} onOpenChange={setPublishOpen}>
            <DialogTrigger asChild>
              <Button size="sm" disabled={job.status !== "pronto" || !job.videoUrl}>
                <Instagram className="mr-1 h-4 w-4" /> Publicar no Instagram
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Publicar no Instagram</DialogTitle>
              </DialogHeader>
              <div className="grid gap-4">
                <div>
                  <Label>Formato</Label>
                  <Select
                    value={instagramFormat}
                    onValueChange={(value) => setInstagramFormat(value as "REELS" | "STORIES")}
                  >
                    <SelectTrigger className="mt-1.5">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="REELS">Reel</SelectItem>
                      <SelectItem value="STORIES">Story</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {instagramFormat === "REELS" ? (
                  <>
                    <div>
                      <Label htmlFor="instagram-caption">Legenda</Label>
                      <Textarea
                        id="instagram-caption"
                        className="mt-1.5"
                        rows={6}
                        maxLength={2200}
                        value={instagramCaption}
                        onChange={(event) => updateInstagramCaption(event.target.value)}
                      />
                      <p className="mt-1 text-right text-[11px] text-muted-foreground">
                        {instagramCaption.length}/2200
                      </p>
                    </div>
                    <div className="flex items-center justify-between rounded border p-3">
                      <div>
                        <div className="text-sm font-medium">Mostrar tambem no feed</div>
                        <div className="text-xs text-muted-foreground">
                          O Reel aparece no feed e na aba Reels.
                        </div>
                      </div>
                      <Switch checked={shareToFeed} onCheckedChange={setShareToFeed} />
                    </div>
                  </>
                ) : (
                  <p className="rounded border bg-muted/40 p-3 text-xs text-muted-foreground">
                    Stories publicados pela API nao recebem legenda nem stickers interativos e
                    desaparecem normalmente apos 24 horas.
                  </p>
                )}
              </div>
              <DialogFooter>
                <Button variant="ghost" onClick={() => setPublishOpen(false)} disabled={publishing}>
                  Cancelar
                </Button>
                <ConfirmAction
                  title={`Publicar este ${instagramFormat === "REELS" ? "Reel" : "Story"} agora?`}
                  description="Esta acao envia o video para a conta profissional conectada e nao pode ser desfeita pelo app."
                  confirmLabel="Publicar agora"
                  onConfirm={async () => {
                    setPublishing(true);
                    try {
                      const publication = await publishVideoToInstagram({
                        videoJobId: job.id,
                        mediaType: instagramFormat,
                        caption: instagramFormat === "REELS" ? instagramCaption : "",
                        shareToFeed,
                      });
                      toast.success(
                        `${instagramFormat === "REELS" ? "Reel" : "Story"} publicado. ID ${publication.mediaId}`,
                      );
                      setPublishOpen(false);
                    } catch (error) {
                      toast.error(
                        error instanceof Error ? error.message : "Nao foi possivel publicar.",
                      );
                    } finally {
                      setPublishing(false);
                    }
                  }}
                  trigger={
                    <Button disabled={publishing}>
                      {publishing ? (
                        <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                      ) : (
                        <Instagram className="mr-1 h-4 w-4" />
                      )}
                      {publishing ? "Publicando..." : "Revisar e publicar"}
                    </Button>
                  }
                />
              </DialogFooter>
            </DialogContent>
          </Dialog>
          <Dialog open={open} onOpenChange={setOpen}>
            <WithTooltip
              label={
                job.status === "pronto"
                  ? "Agendar publicacao no calendario"
                  : "Disponivel quando o video estiver pronto"
              }
            >
              <DialogTrigger asChild>
                <Button size="sm" disabled={job.status !== "pronto"}>
                  <CalendarPlus className="mr-1 h-4 w-4" /> Agendar publicacao
                </Button>
              </DialogTrigger>
            </WithTooltip>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Agendar publicacao</DialogTitle>
              </DialogHeader>
              <div className="grid gap-3">
                <div>
                  <Label>Data</Label>
                  <Input type="date" value={data} onChange={(e) => setData(e.target.value)} />
                </div>
                <div>
                  <Label>Canal</Label>
                  <Select value={canal} onValueChange={(v) => setCanal(v as Canal)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="instagram">Instagram</SelectItem>
                      <SelectItem value="tiktok">TikTok</SelectItem>
                      <SelectItem value="youtube_shorts">YouTube Shorts</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <DialogFooter>
                <Button variant="ghost" onClick={() => setOpen(false)}>
                  Cancelar
                </Button>
                <ConfirmAction
                  title="Agendar esta publicacao?"
                  description={`O post sera agendado para ${data || "..."} no canal ${canalLabel[canal]}.`}
                  confirmLabel="Agendar"
                  onConfirm={async () => {
                    if (!script || !data) return;
                    setScheduling(true);
                    try {
                      const post = await appendCalendarPost({
                        scriptId: script.id,
                        videoJobId: job.id,
                        titulo: script.titulo,
                        dataAgendada: new Date(`${data}T12:00:00`).toISOString(),
                        canal,
                        status: "agendado",
                        tema: script.tema,
                        formato: script.formatoSugerido,
                      });
                      addCalendarPost(post);
                      toast.success("Publicacao agendada e salva no Sheets.");
                      setOpen(false);
                      navigate({ to: "/calendario" });
                    } catch (err) {
                      toast.error(err instanceof Error ? err.message : "Nao foi possivel agendar.");
                    } finally {
                      setScheduling(false);
                    }
                  }}
                  trigger={
                    <Button disabled={!data || !script || scheduling}>
                      {scheduling ? "Salvando..." : "Agendar"}
                    </Button>
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
              <Info
                label="Atualizado em"
                value={new Date(job.atualizadoEm).toLocaleString("pt-BR")}
              />
              {job.duracaoSegundos ? (
                <Info label="Duracao" value={`${job.duracaoSegundos}s`} />
              ) : null}
              {job.videoUrl ? <Info label="Arquivo" value="Video disponivel" /> : null}
            </div>
            {job.videoUrl ? (
              <div className="mt-3 flex flex-wrap gap-2">
                <Button size="sm" variant="secondary" asChild>
                  <a href={videoDownloadUrl(job.id)}>
                    <Download className="mr-1 h-4 w-4" />
                    Baixar MP4
                  </a>
                </Button>
                <Button size="sm" variant="ghost" asChild>
                  <a href={job.videoUrl} target="_blank" rel="noreferrer">
                    Abrir no HeyGen <ExternalLink className="ml-1 h-3.5 w-3.5" />
                  </a>
                </Button>
              </div>
            ) : null}
          </div>

          <div className="rounded-xl border bg-card p-4 shadow-sm">
            <h3 className="mb-2 font-display text-sm font-semibold">Preview</h3>
            {job.videoUrl ? (
              <video
                src={job.videoUrl}
                poster={job.thumbnailUrl}
                controls
                playsInline
                preload="metadata"
                className="aspect-[9/16] max-h-[68vh] w-full max-w-[420px] rounded-lg bg-black object-contain"
              >
                Seu navegador não conseguiu reproduzir este vídeo.
              </video>
            ) : job.thumbnailUrl ? (
              <img
                src={job.thumbnailUrl}
                alt={`Preview de ${script?.titulo ?? "video"}`}
                className="aspect-[9/16] max-w-[240px] rounded-lg object-cover"
              />
            ) : (
              <div className="flex aspect-[9/16] max-w-[240px] items-center justify-center rounded-lg bg-muted text-muted-foreground">
                <Film className="h-10 w-10" />
              </div>
            )}
            <p className="mt-2 text-[11px] text-muted-foreground">
              {job.videoUrl
                ? "Assista aqui ou baixe o arquivo MP4."
                : job.thumbnailUrl
                  ? "Preview retornado pelo HeyGen."
                  : "O preview aparece quando o HeyGen disponibiliza o video."}
            </p>
          </div>
        </div>

        <aside className="space-y-3">
          <section
            className="rounded-xl border border-status-info/20 bg-card p-4 shadow-sm"
            aria-labelledby="reel-caption-title"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 id="reel-caption-title" className="font-display text-sm font-semibold">
                  Legenda do Reel
                </h3>
                <p className="mt-1 text-[11px] leading-4 text-muted-foreground">
                  Texto para publicar junto com o vídeo. Você pode ajustar antes de copiar ou
                  publicar.
                </p>
              </div>
              <span
                className={
                  instagramCaption.trim()
                    ? "shrink-0 rounded-full bg-status-success/10 px-2 py-1 text-[10px] font-semibold text-status-success"
                    : "shrink-0 rounded-full bg-muted px-2 py-1 text-[10px] font-semibold text-muted-foreground"
                }
              >
                {instagramCaption.trim() ? "Pronta" : "Aguardando"}
              </span>
            </div>
            <Label htmlFor="reel-caption-panel" className="sr-only">
              Texto da legenda do Reel
            </Label>
            <Textarea
              id="reel-caption-panel"
              value={instagramCaption}
              maxLength={2200}
              rows={14}
              onChange={(event) => updateInstagramCaption(event.target.value)}
              className="mt-3 min-h-64 resize-y text-sm leading-5"
              placeholder="A legenda aparecerá quando o roteiro de origem estiver disponível."
            />
            <div className="mt-2 flex items-center justify-between gap-3">
              <span className="text-[11px] tabular-nums text-muted-foreground">
                {instagramCaption.length}/2200
              </span>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                className="cursor-pointer"
                disabled={!instagramCaption.trim()}
                onClick={() => void copyInstagramCaption()}
              >
                {captionCopied ? (
                  <Check className="mr-1.5 h-3.5 w-3.5 text-status-success" />
                ) : (
                  <Copy className="mr-1.5 h-3.5 w-3.5" />
                )}
                {captionCopied ? "Copiada" : "Copiar legenda"}
              </Button>
            </div>
          </section>
          <div className="rounded-xl border bg-card p-4 shadow-sm">
            <h3 className="mb-3 font-display text-sm font-semibold">Timeline</h3>
            <StatusTimeline steps={timeline} />
          </div>
          <div className="rounded-xl border bg-card p-3 shadow-sm">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Roteiro origem
            </div>
            {script ? (
              <Link
                to="/roteiros/$id"
                params={{ id: script.id }}
                className="text-sm font-medium hover:underline"
              >
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
    const state: TimelineStep["state"] = i < idx ? "done" : i === idx ? "current" : "pending";
    const step: TimelineStep = { key: k, label: labels[k], state };
    if (k === "fila" && (state === "done" || state === "current"))
      step.timestamp = fmt(ts.criadoEm);
    if (k === status) step.timestamp = fmt(ts.atualizadoEm);
    return step;
  });
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="truncate">{value}</div>
    </div>
  );
}

function reelCaptionStorageKey(jobId: string) {
  return `ai-video-creator-reel-caption:${jobId}`;
}

function buildReelCaption(script: Script): string {
  const sections: string[] = [];
  const addUnique = (value?: string) => {
    const clean = value?.replace(/\s+/g, " ").trim();
    if (
      !clean ||
      sections.some((item) => item.toLocaleLowerCase("pt-BR") === clean.toLocaleLowerCase("pt-BR"))
    ) {
      return;
    }
    sections.push(clean);
  };

  addUnique(script.hook || script.titulo);
  addUnique(script.dorConflito);
  addUnique(script.explicacaoSimples);
  addUnique(script.virada);
  addUnique(script.cta);

  const familyHashtags: Record<Script["categoria"], string[]> = {
    medicamento: ["#Saude", "#Obesidade", "#GLP1", "#ConteudoMedico"],
    comportamento: ["#Saude", "#BemEstar", "#Comportamento", "#Emagrecimento"],
    metabolismo: ["#SaudeMetabolica", "#Nutricao", "#BemEstar", "#Emagrecimento"],
    obesidade: ["#Obesidade", "#Emagrecimento", "#Saude", "#ConteudoMedico"],
    educativo: ["#Saude", "#BemEstar", "#Informacao", "#ConteudoMedico"],
  };
  const disclaimer = "Conteúdo educativo. Não substitui avaliação médica individual.";
  const caption = [...sections, disclaimer, familyHashtags[script.categoria].join(" ")].join(
    "\n\n",
  );
  return caption.slice(0, 2200);
}
