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
  createPostProduction,
  fetchLatestPostProduction,
  fetchPostProduction,
  fetchPostProductionArtifacts,
  postProductionPreviewUrl,
  publishVideoToInstagram,
  regenerateSceneVideo,
  refreshHeyGenVideo,
  replanPostProduction,
  renderPostProductionPreview,
  runPostProductionPreflight,
  updatePostProductionEvents,
  videoDownloadUrl,
  type PostProductionArtifacts,
  type PostProductionJob,
  type PreflightReport,
  type VisualTimelineEvent,
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
  FolderOpen,
  Instagram,
  Layers3,
  Loader2,
  Save,
  Sparkles,
  RefreshCcw,
} from "lucide-react";
import type { Canal, Script, VideoJobStatus } from "@/lib/mock-data";
import {
  ensureMedicalProfessionalIdentification,
  formatPublicationCaption,
  safeEditorialCta,
} from "@/lib/medical-identity";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

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
  const addVideoJob = useStore((s) => s.addVideoJob);
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
  const [postJob, setPostJob] = useState<PostProductionJob | null>(null);
  const [postArtifacts, setPostArtifacts] = useState<PostProductionArtifacts | null>(null);
  const [preflightReport, setPreflightReport] = useState<PreflightReport | null>(null);
  const [postBusy, setPostBusy] = useState(false);
  const [autoRefreshing, setAutoRefreshing] = useState(false);
  const [regeneratingScene, setRegeneratingScene] = useState(false);
  const trackedJobId = job?.id;
  const trackedJobProvider = job?.provider;
  const trackedJobStatus = job?.status;
  const postJobId = postJob?.id;
  const postJobStatus = postJob?.status;

  useEffect(() => {
    if (!script) return;
    const storageKey = reelCaptionStorageKey(job?.id ?? id);
    const savedCaption = window.localStorage.getItem(storageKey);
    setInstagramCaption(
      ensureMedicalProfessionalIdentification(savedCaption || buildReelCaption(script), 2200),
    );
  }, [id, job?.id, script]);

  useEffect(() => {
    const savedId = window.localStorage.getItem(`post-production:${id}`);
    let cancelled = false;
    const recover = async () => {
      let recovered: PostProductionJob | null = null;
      if (savedId) {
        try {
          recovered = await fetchPostProduction(savedId);
        } catch {
          window.localStorage.removeItem(`post-production:${id}`);
        }
      }
      if (!recovered) recovered = await fetchLatestPostProduction(id);
      if (cancelled || !recovered) return;
      window.localStorage.setItem(`post-production:${id}`, recovered.id);
      setPostJob(recovered);
    };
    void recover().catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [id]);

  useEffect(() => {
    if (!postJobId || !postJobStatus) return;
    const active = [
      "queued",
      "transcribing",
      "planning",
      "preflight",
      "rendering_preview",
    ].includes(postJobStatus);
    const refresh = async () => {
      try {
        const current = await fetchPostProduction(postJobId);
        setPostJob(current);
        if (["needs_review", "preview_ready", "failed", "stale"].includes(current.status)) {
          const artifacts = await fetchPostProductionArtifacts(current.id);
          setPostArtifacts(artifacts);
        }
      } catch {
        // O próximo poll tenta novamente; a tela principal continua utilizável.
      }
    };
    if (!active) {
      void refresh();
      return;
    }
    const timer = window.setInterval(() => void refresh(), 2500);
    return () => window.clearInterval(timer);
  }, [postJobId, postJobStatus]);

  useEffect(() => {
    const active =
      trackedJobProvider === "heygen" &&
      (trackedJobStatus === "fila" || trackedJobStatus === "processando");
    if (!trackedJobId || !active) {
      setAutoRefreshing(false);
      return;
    }

    let cancelled = false;
    let timer: number | undefined;
    setAutoRefreshing(true);

    const poll = async () => {
      try {
        const result = await refreshHeyGenVideo(trackedJobId);
        if (cancelled) return;
        updateVideoJob(trackedJobId, result.job);
        if (result.composedJob) addVideoJob(result.composedJob);
        if (result.job.status === "pronto") {
          setAutoRefreshing(false);
          toast.success(
            result.composedJob
              ? "Vídeo final composto pronto."
              : "Nova versão pronta e salva em content/videos.",
          );
          return;
        }
        if (result.job.status === "erro") {
          setAutoRefreshing(false);
          toast.error(result.job.erro || "A produção falhou no HeyGen.");
          return;
        }
        timer = window.setTimeout(() => void poll(), 5000);
      } catch (error) {
        if (cancelled) return;
        console.warn("[video-status] atualização automática falhou", {
          jobId: trackedJobId,
          error: error instanceof Error ? error.message : String(error),
        });
        timer = window.setTimeout(() => void poll(), 8000);
      }
    };

    timer = window.setTimeout(() => void poll(), 1200);
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [addVideoJob, trackedJobId, trackedJobProvider, trackedJobStatus, updateVideoJob]);

  async function applyElegantPostProduction() {
    if (postJob?.status === "preview_ready") {
      document.getElementById("post-production")?.scrollIntoView({ behavior: "smooth" });
      return;
    }
    setPostBusy(true);
    try {
      const created = await createPostProduction(job!.id, true);
      window.localStorage.setItem(`post-production:${job!.id}`, created.id);
      setPostJob(created);
      setPostArtifacts(null);
      setPreflightReport(null);
      toast.success("Edição elegante iniciada. A prévia será renderizada automaticamente.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível aplicar a edição.");
    } finally {
      setPostBusy(false);
    }
  }

  function updateInstagramCaption(value: string) {
    const next = ensureMedicalProfessionalIdentification(value, 2200);
    setInstagramCaption(next);
    window.localStorage.setItem(reelCaptionStorageKey(job?.id ?? id), next);
  }

  async function copyInstagramCaption() {
    if (!instagramCaption.trim()) return;
    try {
      await navigator.clipboard.writeText(
        ensureMedicalProfessionalIdentification(instagramCaption, 2200),
      );
      setCaptionCopied(true);
      toast.success("Legenda copiada. Pronta para colar no Reel.");
      window.setTimeout(() => setCaptionCopied(false), 1800);
    } catch {
      toast.error("Não foi possível copiar a legenda.");
    }
  }

  async function regenerateOnlyThisScene() {
    if (!job?.isScene) return;
    setRegeneratingScene(true);
    try {
      const replacement = await regenerateSceneVideo(job.id);
      addVideoJob(replacement);
      toast.success("Nova versão desta tomada foi enviada. As outras cenas serão mantidas.");
      navigate({ to: "/producao/$id", params: { id: replacement.id } });
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Não foi possível regenerar esta tomada.",
      );
    } finally {
      setRegeneratingScene(false);
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
  const postApplying = Boolean(
    postJob &&
    ["queued", "transcribing", "planning", "preflight", "rendering_preview"].includes(
      postJob.status,
    ),
  );

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
              disabled={job.provider === "local" || autoRefreshing}
              onClick={async () => {
                try {
                  const result = await refreshHeyGenVideo(job.id);
                  updateVideoJob(job.id, result.job);
                  if (result.composedJob) addVideoJob(result.composedJob);
                  toast.success(
                    result.composedJob
                      ? "Vídeo final composto pronto."
                      : `Status: ${videoJobStatusLabel[result.job.status].label}`,
                  );
                } catch (err) {
                  toast.error(err instanceof Error ? err.message : "Falha ao consultar o HeyGen.");
                }
              }}
            >
              <RefreshCcw className={cn("mr-1 h-4 w-4", autoRefreshing && "animate-spin")} />
              {autoRefreshing ? "Acompanhando..." : "Atualizar status"}
            </Button>
          </WithTooltip>
          {job.isScene ? (
            <ConfirmAction
              title="Regenerar somente esta tomada?"
              description="O HeyGen receberá apenas esta cena, com o mesmo look, voz, texto e corte seco. As outras tomadas do lote serão preservadas."
              confirmLabel="Regenerar tomada"
              onConfirm={regenerateOnlyThisScene}
              trigger={
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={
                    regeneratingScene || job.status === "fila" || job.status === "processando"
                  }
                >
                  {regeneratingScene ? (
                    <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCcw className="mr-1 h-4 w-4" />
                  )}
                  Regenerar esta tomada
                </Button>
              }
            />
          ) : null}
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
                {job.isComposed ? "Baixar vídeo final" : "Baixar vídeo"}
              </a>
            </Button>
          ) : null}
          {job.status === "pronto" && job.videoUrl ? (
            <Button size="sm" variant="secondary" asChild>
              <Link
                to="/kit-local"
                search={{
                  videoJobId: job.id,
                  sourceName: script?.titulo ?? `Video ${job.id}`,
                }}
              >
                <Layers3 className="mr-1 h-4 w-4" /> Abrir no editor
              </Link>
            </Button>
          ) : null}
          {job.status === "pronto" && job.videoUrl ? (
            <Button
              size="sm"
              onClick={() => void applyElegantPostProduction()}
              disabled={postBusy || postApplying}
            >
              {postBusy || postApplying ? (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="mr-1 h-4 w-4" />
              )}
              {postJob?.status === "preview_ready"
                ? "Ver edição elegante"
                : postApplying
                  ? "Aplicando edição..."
                  : "Aplicar edição elegante"}
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
                        caption:
                          instagramFormat === "REELS"
                            ? ensureMedicalProfessionalIdentification(instagramCaption, 2200)
                            : "",
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
              {job.videoUrl ? (
                <Info
                  label="Arquivo"
                  value={job.isComposed ? "Vídeo final composto" : "Video disponivel"}
                />
              ) : null}
              {job.regeneratedFromJobId ? (
                <Info label="Regeneração" value={`Tomada ${job.regenerationCount || 1}`} />
              ) : null}
            </div>
            {job.exportPath ? (
              <div
                className="mt-3 rounded-lg border border-status-success/25 bg-status-success/5 p-3"
                aria-live="polite"
              >
                <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
                  <FolderOpen className="h-4 w-4 text-status-success" aria-hidden="true" />
                  Arquivos organizados · versão {job.exportVersion ?? "1.1"}
                </div>
                <code className="mt-1.5 block break-all text-[11px] leading-4 text-muted-foreground">
                  {job.exportPath}
                </code>
                <p className="mt-1 text-[11px] leading-4 text-muted-foreground">
                  A pasta reúne o vídeo final, tomadas, legendas, roteiro e metadados disponíveis.
                </p>
              </div>
            ) : job.exportWarning ? (
              <p
                className="mt-3 rounded-lg border border-status-warning/25 bg-status-warning/5 p-3 text-xs text-muted-foreground"
                role="status"
              >
                {job.exportWarning}
              </p>
            ) : null}
            {job.videoUrl ? (
              <div className="mt-3 flex flex-wrap gap-2">
                <Button size="sm" variant="secondary" asChild>
                  <a href={videoDownloadUrl(job.id)}>
                    <Download className="mr-1 h-4 w-4" />
                    {job.isComposed ? "Baixar MP4 final" : "Baixar MP4"}
                  </a>
                </Button>
                {!job.isComposed && job.remoteVideoUrl ? (
                  <Button size="sm" variant="ghost" asChild>
                    <a href={job.remoteVideoUrl} target="_blank" rel="noreferrer">
                      Abrir no HeyGen <ExternalLink className="ml-1 h-3.5 w-3.5" />
                    </a>
                  </Button>
                ) : null}
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

          {postJob ? (
            <PostProductionPanel
              originalUrl={job.videoUrl}
              job={postJob}
              artifacts={postArtifacts}
              report={preflightReport}
              busy={postBusy}
              onArtifactsChange={setPostArtifacts}
              onJobChange={setPostJob}
              onReportChange={setPreflightReport}
              onBusyChange={setPostBusy}
            />
          ) : null}
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

function PostProductionPanel({
  originalUrl,
  job,
  artifacts,
  report,
  busy,
  onArtifactsChange,
  onJobChange,
  onReportChange,
  onBusyChange,
}: {
  originalUrl?: string;
  job: PostProductionJob;
  artifacts: PostProductionArtifacts | null;
  report: PreflightReport | null;
  busy: boolean;
  onArtifactsChange: (value: PostProductionArtifacts | null) => void;
  onJobChange: (value: PostProductionJob) => void;
  onReportChange: (value: PreflightReport | null) => void;
  onBusyChange: (value: boolean) => void;
}) {
  async function saveEvents() {
    if (!artifacts) return;
    onBusyChange(true);
    try {
      const result = await updatePostProductionEvents(
        job.id,
        artifacts.timeline.events.map(
          ({ id, enabled, visualText, interactionType, reviewStatus }) => ({
            id,
            enabled,
            visualText,
            interactionType,
            reviewStatus,
          }),
        ),
      );
      onJobChange(result.job);
      onArtifactsChange({ ...artifacts, timeline: result.timeline });
      onReportChange(null);
      toast.success("Eventos visuais salvos.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível salvar os eventos.");
    } finally {
      onBusyChange(false);
    }
  }

  async function runPreflight() {
    onBusyChange(true);
    try {
      const result = await runPostProductionPreflight(job.id);
      onJobChange(result.job);
      onReportChange(result.report);
      toast[result.ok ? "success" : "error"](
        result.ok ? "Preflight aprovado." : "O preflight encontrou blockers.",
      );
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Preflight indisponível.");
    } finally {
      onBusyChange(false);
    }
  }

  async function renderPreview() {
    onBusyChange(true);
    try {
      onJobChange(await renderPostProductionPreview(job.id));
      toast.success("Prévia em renderização.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível gerar a prévia.");
    } finally {
      onBusyChange(false);
    }
  }

  async function regeneratePlan() {
    onBusyChange(true);
    try {
      onJobChange(await replanPostProduction(job.id));
      onArtifactsChange(null);
      onReportChange(null);
      toast.success("Plano visual em regeneração.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível regenerar o plano.");
    } finally {
      onBusyChange(false);
    }
  }

  function patchEvent(
    eventId: string,
    patch: {
      enabled?: boolean;
      visualText?: string;
      interactionType?: VisualTimelineEvent["interactionType"];
    },
  ) {
    if (!artifacts) return;
    onArtifactsChange({
      ...artifacts,
      timeline: {
        ...artifacts.timeline,
        events: artifacts.timeline.events.map((event) =>
          event.id === eventId ? { ...event, ...patch } : event,
        ),
      },
    });
  }

  return (
    <section
      id="post-production"
      className="rounded-xl border border-status-info/30 bg-card p-4 shadow-sm"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-sm font-semibold">Pós-produção inteligente</h3>
          <p className="mt-1 text-xs text-muted-foreground">{job.etapa}</p>
        </div>
        <span className="rounded-full bg-muted px-2.5 py-1 text-[11px] font-semibold">
          {job.status.replaceAll("_", " ")} · {job.progresso}%
        </span>
      </div>
      <Progress value={job.progresso} className="mt-3" />
      {job.erro ? (
        <p className="mt-3 rounded bg-destructive/10 p-2 text-xs text-destructive">{job.erro}</p>
      ) : null}

      {artifacts ? (
        <>
          <div className="mt-4 rounded-lg bg-muted/40 p-3">
            <div className="text-xs font-semibold">Transcrição</div>
            <p className="mt-1 max-h-28 overflow-y-auto text-xs leading-5 text-muted-foreground">
              {artifacts.transcript.text}
            </p>
          </div>
          <div className="mt-4 space-y-3">
            {artifacts.timeline.events.map((event) => (
              <div key={event.id} className="rounded-lg border p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-xs font-semibold">
                    {(event.startMs / 1000).toFixed(1)}s–{(event.endMs / 1000).toFixed(1)}s
                  </div>
                  <Switch
                    checked={event.enabled}
                    onCheckedChange={(enabled) => patchEvent(event.id, { enabled })}
                    aria-label={`Ativar evento ${event.id}`}
                  />
                </div>
                <p className="mt-2 text-[11px] text-muted-foreground">{event.spokenText}</p>
                <Select
                  value={event.interactionType}
                  disabled={!event.enabled}
                  onValueChange={(interactionType) =>
                    patchEvent(event.id, {
                      interactionType: interactionType as VisualTimelineEvent["interactionType"],
                    })
                  }
                >
                  <SelectTrigger className="mt-2" aria-label={`Tipo visual do evento ${event.id}`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="caption_emphasis">Destaque de legenda</SelectItem>
                    <SelectItem value="kinetic_text">Texto cinético</SelectItem>
                    <SelectItem value="progressive_list">Lista progressiva</SelectItem>
                    <SelectItem value="supporting_visual">Imagem de apoio</SelectItem>
                    <SelectItem value="cta_card">CTA</SelectItem>
                    <SelectItem value="none">Sem intervenção</SelectItem>
                  </SelectContent>
                </Select>
                <Textarea
                  className="mt-2 min-h-20 resize-y whitespace-pre-wrap"
                  maxLength={100}
                  value={event.visualText}
                  disabled={!event.enabled}
                  onChange={(input) => patchEvent(event.id, { visualText: input.target.value })}
                  aria-label={`Texto visual do evento ${event.id}`}
                />
              </div>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => void regeneratePlan()}>
              <RefreshCcw className="mr-1 h-4 w-4" /> Regenerar plano
            </Button>
            <Button size="sm" variant="secondary" disabled={busy} onClick={() => void saveEvents()}>
              <Save className="mr-1 h-4 w-4" /> Salvar eventos
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={busy}
              onClick={() => void runPreflight()}
            >
              Executar preflight
            </Button>
            <Button
              size="sm"
              disabled={busy || report?.ok === false}
              onClick={() => void renderPreview()}
            >
              Gerar prévia
            </Button>
          </div>
        </>
      ) : null}

      {report ? (
        <div className="mt-4 space-y-1 rounded-lg border p-3 text-xs">
          {report.findings.map((finding) => (
            <div key={`${finding.code}-${finding.eventId ?? "timeline"}`}>
              <strong>{finding.classification}</strong> · {finding.message}
            </div>
          ))}
        </div>
      ) : null}

      {job.status === "preview_ready" ? (
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <div>
            <div className="mb-2 text-xs font-semibold">Original</div>
            {originalUrl ? (
              <video src={originalUrl} controls className="aspect-[9/16] w-full rounded bg-black" />
            ) : null}
          </div>
          <div>
            <div className="mb-2 text-xs font-semibold">Prévia editada</div>
            <video
              src={postProductionPreviewUrl(job.id)}
              controls
              className="aspect-[9/16] w-full rounded bg-black"
            />
            <Button className="mt-2" size="sm" variant="secondary" asChild>
              <a href={postProductionPreviewUrl(job.id, true)}>
                <Download className="mr-1 h-4 w-4" /> Baixar prévia
              </a>
            </Button>
          </div>
        </div>
      ) : null}
    </section>
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
  addUnique(safeEditorialCta(script.cta, ""));

  const familyHashtags: Record<Script["categoria"], string[]> = {
    medicamento: ["#Saude", "#Obesidade", "#GLP1", "#ConteudoMedico"],
    comportamento: ["#Saude", "#BemEstar", "#Comportamento", "#Emagrecimento"],
    metabolismo: ["#SaudeMetabolica", "#Nutricao", "#BemEstar", "#Emagrecimento"],
    obesidade: ["#Obesidade", "#Emagrecimento", "#Saude", "#ConteudoMedico"],
    educativo: ["#Saude", "#BemEstar", "#Informacao", "#ConteudoMedico"],
  };
  return formatPublicationCaption(
    sections.join("\n\n"),
    familyHashtags[script.categoria],
    2200,
  );
}
