import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  CheckCircle2,
  Copy,
  Download,
  Film,
  LoaderCircle,
  RotateCcw,
  Scissors,
  ShieldAlert,
  Square,
  Upload,
  Youtube,
} from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  cancelCutProject,
  createCutProject,
  cutFileUrl,
  fetchCutProjects,
  retryCutProject,
  type CutProject,
  uploadCutVideo,
} from "@/lib/api/local";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/cortes")({
  head: () => ({
    meta: [
      { title: "Cortes | AI Video Creator" },
      {
        name: "description",
        content: "Transforme videos longos em cortes verticais com legendas e ranking.",
      },
    ],
  }),
  component: CortesPage,
});

function CortesPage() {
  const videoJobs = useStore((state) => state.videoJobs);
  const scripts = useStore((state) => state.scripts);
  const [projects, setProjects] = useState<CutProject[]>([]);
  const [sourceMode, setSourceMode] = useState<"produced" | "upload" | "youtube">("upload");
  const [videoJobId, setVideoJobId] = useState("");
  const [uploadId, setUploadId] = useState("");
  const [uploadName, setUploadName] = useState("");
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [clipCount, setClipCount] = useState<"auto" | number>("auto");
  const [durationPreset, setDurationPreset] = useState("auto");
  const [analysisMode, setAnalysisMode] = useState<"full" | "range">("range");
  const [analysisStart, setAnalysisStart] = useState("00:00");
  const [analysisEnd, setAnalysisEnd] = useState("20:00");
  const [captions, setCaptions] = useState(true);
  const [layout, setLayout] = useState<"fit" | "fill">("fit");
  const [submitting, setSubmitting] = useState(false);
  const requestId = useRef("");
  const videos = useMemo(() => videoJobs.filter((job) => job.status === "pronto"), [videoJobs]);

  useEffect(() => {
    if (!videoJobId && videos[0]) setVideoJobId(videos[0].id);
  }, [videoJobId, videos]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const result = await fetchCutProjects();
        if (!cancelled) setProjects(result);
      } catch (error) {
        if (!cancelled) {
          toast.error(error instanceof Error ? error.message : "Falha ao carregar cortes.");
        }
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const sortedProjects = useMemo(
    () =>
      [...projects].sort(
        (left, right) => new Date(right.criadoEm).getTime() - new Date(left.criadoEm).getTime(),
      ),
    [projects],
  );

  async function selectUpload(file?: File) {
    if (!file) return;
    setSubmitting(true);
    try {
      const uploaded = await uploadCutVideo(file);
      setUploadId(uploaded.uploadId);
      setUploadName(file.name);
      toast.success("Video enviado. Agora escolha as configuracoes dos cortes.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Falha no upload.");
    } finally {
      setSubmitting(false);
    }
  }

  async function generate() {
    const [minDuration, maxDuration] =
      durationPreset === "auto" ? [18, 75] : durationPreset.split("-").map(Number);
    const analysisStartSeconds = analysisMode === "range" ? parseTimestamp(analysisStart) : 0;
    const analysisEndSeconds = analysisMode === "range" ? parseTimestamp(analysisEnd) : null;
    if (
      analysisStartSeconds == null ||
      (analysisMode === "range" &&
        (analysisEndSeconds == null || analysisEndSeconds <= analysisStartSeconds))
    ) {
      toast.error("Informe um intervalo válido. Exemplo: 10:00 até 20:00.");
      return;
    }
    if (!requestId.current) requestId.current = globalThis.crypto.randomUUID();
    setSubmitting(true);
    try {
      const project = await createCutProject({
        requestId: requestId.current,
        videoJobId: sourceMode === "produced" ? videoJobId : undefined,
        uploadId: sourceMode === "upload" ? uploadId : undefined,
        youtubeUrl: sourceMode === "youtube" ? youtubeUrl.trim() : undefined,
        sourceName:
          sourceMode === "upload"
            ? uploadName
            : sourceMode === "youtube"
              ? "Video do YouTube"
              : undefined,
        clipCount: clipCount === "auto" ? null : clipCount,
        minDuration,
        maxDuration,
        durationMode: durationPreset === "auto" ? "auto" : "preset",
        analysisStartSeconds,
        analysisEndSeconds,
        captions,
        layout,
      });
      requestId.current = "";
      setProjects((current) => [project, ...current.filter((item) => item.id !== project.id)]);
      toast.success("Analise iniciada. Voce pode acompanhar o progresso nesta tela.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Nao foi possivel criar os cortes.");
    } finally {
      setSubmitting(false);
    }
  }

  const sourceReady =
    sourceMode === "produced"
      ? Boolean(videoJobId)
      : sourceMode === "youtube"
        ? /^https:\/\/(www\.|m\.|music\.)?(youtube\.com|youtu\.be)\//i.test(youtubeUrl.trim())
        : Boolean(uploadId);
  const rangeReady =
    analysisMode === "full" ||
    (() => {
      const start = parseTimestamp(analysisStart);
      const end = parseTimestamp(analysisEnd);
      return start != null && end != null && end > start;
    })();

  return (
    <AppShell
      title="Cortes inteligentes"
      actions={
        <div className="hidden text-[11px] text-muted-foreground md:block">
          Transcrição, seleção editorial e renderização vertical
        </div>
      }
    >
      <div className="grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
        <aside className="h-fit rounded-md border bg-card">
          <div className="border-b px-4 py-3">
            <h2 className="text-sm font-semibold">Novo projeto</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Escolha a origem e deixe a ferramenta encontrar os melhores momentos.
            </p>
          </div>

          <div className="space-y-5 p-4">
            <div>
              <Label className="text-xs">Origem do vídeo</Label>
              <div className="mt-2 grid grid-cols-3 rounded-md bg-muted p-1">
                <button
                  type="button"
                  onClick={() => setSourceMode("upload")}
                  className={cn(
                    "flex h-9 items-center justify-center gap-1.5 rounded text-xs font-medium",
                    sourceMode === "upload" && "bg-card shadow-sm",
                  )}
                >
                  <Upload className="h-3.5 w-3.5" />
                  Enviar vídeo
                </button>
                <button
                  type="button"
                  onClick={() => setSourceMode("produced")}
                  className={cn(
                    "flex h-9 items-center justify-center gap-1.5 rounded text-xs font-medium",
                    sourceMode === "produced" && "bg-card shadow-sm",
                  )}
                >
                  <Film className="h-3.5 w-3.5" />
                  Produzido
                </button>
                <button
                  type="button"
                  onClick={() => setSourceMode("youtube")}
                  className={cn(
                    "flex h-9 items-center justify-center gap-1.5 rounded text-xs font-medium",
                    sourceMode === "youtube" && "bg-card shadow-sm",
                  )}
                >
                  <Youtube className="h-3.5 w-3.5" />
                  YouTube
                </button>
              </div>
            </div>

            {sourceMode === "upload" ? (
              <div>
                <input
                  id="cut-video-upload"
                  type="file"
                  accept="video/*"
                  className="sr-only"
                  onChange={(event) => void selectUpload(event.target.files?.[0])}
                />
                <Button asChild variant="secondary" className="w-full">
                  <label htmlFor="cut-video-upload" className="cursor-pointer">
                    <Upload className="mr-1.5 h-4 w-4" />
                    <span className="min-w-0 truncate">{uploadName || "Selecionar vídeo"}</span>
                  </label>
                </Button>
                <p className="mt-1.5 text-[11px] text-muted-foreground">
                  MP4, MOV ou WebM, com até 2 GB.
                </p>
              </div>
            ) : sourceMode === "produced" ? (
              <div>
                <Label className="text-xs">Vídeo pronto</Label>
                <Select value={videoJobId} onValueChange={setVideoJobId}>
                  <SelectTrigger className="mt-1.5">
                    <SelectValue placeholder="Selecione um vídeo" />
                  </SelectTrigger>
                  <SelectContent>
                    {videos.map((video) => {
                      const script = scripts.find((item) => item.id === video.scriptId);
                      return (
                        <SelectItem key={video.id} value={video.id}>
                          {script?.titulo || `Vídeo ${video.id}`}
                        </SelectItem>
                      );
                    })}
                  </SelectContent>
                </Select>
                {videos.length === 0 ? (
                  <p className="mt-1.5 text-[11px] text-muted-foreground">
                    Nenhum vídeo produzido está pronto.
                  </p>
                ) : null}
              </div>
            ) : (
              <div>
                <Label htmlFor="cut-youtube-url" className="text-xs">
                  Link do YouTube
                </Label>
                <Input
                  id="cut-youtube-url"
                  type="url"
                  inputMode="url"
                  value={youtubeUrl}
                  onChange={(event) => setYoutubeUrl(event.target.value)}
                  placeholder="https://youtube.com/watch?v=..."
                  className="mt-1.5"
                />
                <p className="mt-1.5 text-[11px] text-muted-foreground">
                  Vídeo público, Shorts ou link youtu.be, com até 2 horas.
                </p>
              </div>
            )}

            <div className="rounded-md border p-3">
              <Label className="text-xs">Parte do vídeo a analisar</Label>
              <div className="mt-2 grid grid-cols-2 rounded-md bg-muted p-1">
                <button
                  type="button"
                  onClick={() => setAnalysisMode("range")}
                  className={cn(
                    "h-9 rounded text-xs font-medium transition-colors",
                    analysisMode === "range" && "bg-card shadow-sm",
                  )}
                >
                  Escolher trecho
                </button>
                <button
                  type="button"
                  onClick={() => setAnalysisMode("full")}
                  className={cn(
                    "h-9 rounded text-xs font-medium transition-colors",
                    analysisMode === "full" && "bg-card shadow-sm",
                  )}
                >
                  Vídeo inteiro
                </button>
              </div>
              {analysisMode === "range" ? (
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <div>
                    <Label htmlFor="analysis-start" className="text-[11px] text-muted-foreground">
                      Início
                    </Label>
                    <Input
                      id="analysis-start"
                      value={analysisStart}
                      onChange={(event) => setAnalysisStart(event.target.value)}
                      placeholder="00:00"
                      inputMode="numeric"
                      className="mt-1 h-9 tabular-nums"
                    />
                  </div>
                  <div>
                    <Label htmlFor="analysis-end" className="text-[11px] text-muted-foreground">
                      Fim
                    </Label>
                    <Input
                      id="analysis-end"
                      value={analysisEnd}
                      onChange={(event) => setAnalysisEnd(event.target.value)}
                      placeholder="20:00"
                      inputMode="numeric"
                      className="mt-1 h-9 tabular-nums"
                    />
                  </div>
                </div>
              ) : (
                <p className="mt-2 text-[11px] leading-4 text-status-warn-foreground">
                  Vídeos longos podem exigir bastante processamento. Prefira escolher um trecho.
                </p>
              )}
              <p className="mt-2 text-[11px] text-muted-foreground">
                Use MM:SS ou HH:MM:SS. Somente esse intervalo será transcrito.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Quantidade</Label>
                <Select
                  value={String(clipCount)}
                  onValueChange={(value) => setClipCount(value === "auto" ? "auto" : Number(value))}
                >
                  <SelectTrigger className="mt-1.5">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">IA decide</SelectItem>
                    {[1, 3, 5, 8].map((count) => (
                      <SelectItem key={count} value={String(count)}>
                        {count} {count === 1 ? "corte" : "cortes"}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="mt-1.5 text-[11px] text-muted-foreground">
                  No automático, só cria trechos com potencial viral real.
                </p>
              </div>
              <div>
                <Label className="text-xs">Duração</Label>
                <Select value={durationPreset} onValueChange={setDurationPreset}>
                  <SelectTrigger className="mt-1.5">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">Automática</SelectItem>
                    <SelectItem value="18-75">18 a 75s</SelectItem>
                    <SelectItem value="8-20">8 a 20s</SelectItem>
                    <SelectItem value="15-45">15 a 45s</SelectItem>
                    <SelectItem value="30-60">30 a 60s</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div>
              <Label className="text-xs">Enquadramento vertical</Label>
              <div className="mt-2 grid grid-cols-2 rounded-md bg-muted p-1">
                <button
                  type="button"
                  onClick={() => setLayout("fit")}
                  className={cn(
                    "h-9 rounded text-xs font-medium",
                    layout === "fit" && "bg-card shadow-sm",
                  )}
                >
                  Fundo desfocado
                </button>
                <button
                  type="button"
                  onClick={() => setLayout("fill")}
                  className={cn(
                    "h-9 rounded text-xs font-medium",
                    layout === "fill" && "bg-card shadow-sm",
                  )}
                >
                  Preencher tela
                </button>
              </div>
            </div>

            <div className="flex min-h-14 items-center gap-3 rounded-md border px-3">
              <div className="min-w-0 flex-1">
                <div className="text-xs font-medium">Legendas grandes</div>
                <div className="text-[11px] text-muted-foreground">
                  Sincronizadas automaticamente
                </div>
              </div>
              <Switch checked={captions} onCheckedChange={setCaptions} />
            </div>

            <Button
              className="w-full"
              disabled={!sourceReady || !rangeReady || submitting}
              onClick={() => void generate()}
            >
              {submitting ? (
                <LoaderCircle className="mr-1.5 h-4 w-4 animate-spin" />
              ) : (
                <Scissors className="mr-1.5 h-4 w-4" />
              )}
              {submitting ? "Preparando..." : "Analisar e criar cortes"}
            </Button>
          </div>
        </aside>

        <div className="min-w-0 space-y-6">
          {sortedProjects.length === 0 ? (
            <EmptyState
              className="min-h-72"
              icon={<Scissors className="h-5 w-5" />}
              title="Comece por um vídeo longo"
              description="Envie uma aula, cole um link do YouTube ou reaproveite um vídeo pronto. A ferramenta transcreve, ranqueia os melhores momentos e entrega MP4 vertical com legenda."
              action={
                <div className="flex flex-wrap justify-center gap-2">
                  <Button size="sm" onClick={() => setSourceMode("upload")}>
                    <Upload className="mr-1.5 h-4 w-4" />
                    Enviar vídeo
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => setSourceMode("youtube")}>
                    <Youtube className="mr-1.5 h-4 w-4" />
                    Usar YouTube
                  </Button>
                  <Button size="sm" variant="ghost" asChild>
                    <Link to="/producao">Ver vídeos prontos</Link>
                  </Button>
                </div>
              }
            />
          ) : (
            sortedProjects.map((project) => (
              <ProjectResult
                key={project.id}
                project={project}
                onChange={(updated) =>
                  setProjects((current) =>
                    current.map((item) => (item.id === updated.id ? updated : item)),
                  )
                }
              />
            ))
          )}
        </div>
      </div>
    </AppShell>
  );
}

function ProjectResult({
  project,
  onChange,
}: {
  project: CutProject;
  onChange: (project: CutProject) => void;
}) {
  const active = project.status === "fila" || project.status === "processando";
  const [retrying, setRetrying] = useState(false);
  const [stopping, setStopping] = useState(false);
  return (
    <section className="border-b pb-6">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold">{project.sourceName}</h2>
            <ProjectStatus status={project.status} />
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {project.etapa} · {new Date(project.criadoEm).toLocaleString("pt-BR")}
          </p>
          {project.settings.analysisEndSeconds != null ? (
            <p className="mt-1 text-[11px] text-muted-foreground">
              Analisando {formatTimestamp(project.settings.analysisStartSeconds || 0)} até{" "}
              {formatTimestamp(project.settings.analysisEndSeconds)}
            </p>
          ) : null}
        </div>
        {active ? (
          <div className="flex items-center gap-3">
            <div className="flex w-44 items-center gap-2">
              <Progress value={project.progresso} className="h-1.5" />
              <span className="text-[11px] tabular-nums text-muted-foreground">
                {project.progresso}%
              </span>
            </div>
            <Button
              size="sm"
              variant="destructive"
              disabled={stopping}
              onClick={async () => {
                setStopping(true);
                try {
                  onChange(await cancelCutProject(project.id));
                  toast.success("Processamento interrompido.");
                } catch (error) {
                  toast.error(error instanceof Error ? error.message : "Não foi possível parar.");
                } finally {
                  setStopping(false);
                }
              }}
            >
              {stopping ? (
                <LoaderCircle className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Square className="mr-1.5 h-3.5 w-3.5" />
              )}
              Parar
            </Button>
          </div>
        ) : null}
      </div>

      {project.erro ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-status-danger/30 bg-status-danger/10 px-3 py-2 text-xs text-status-danger">
          <span>{friendlyCutError(project.erro)}</span>
          <Button
            size="sm"
            variant="secondary"
            disabled={retrying}
            onClick={async () => {
              setRetrying(true);
              try {
                onChange(await retryCutProject(project.id));
                toast.success("Novo processamento iniciado.");
              } catch (error) {
                toast.error(error instanceof Error ? error.message : "Falha ao tentar novamente.");
              } finally {
                setRetrying(false);
              }
            }}
          >
            <RotateCcw className={cn("mr-1.5 h-3.5 w-3.5", retrying && "animate-spin")} />
            Tentar novamente
          </Button>
        </div>
      ) : null}

      {project.status === "cancelado" ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border bg-muted/40 px-3 py-2 text-xs">
          <span>Processamento interrompido. Você pode iniciar novamente quando quiser.</span>
          <Button
            size="sm"
            variant="secondary"
            disabled={retrying}
            onClick={async () => {
              setRetrying(true);
              try {
                onChange(await retryCutProject(project.id));
                toast.success("Novo processamento iniciado.");
              } catch (error) {
                toast.error(error instanceof Error ? error.message : "Falha ao tentar novamente.");
              } finally {
                setRetrying(false);
              }
            }}
          >
            <RotateCcw className={cn("mr-1.5 h-3.5 w-3.5", retrying && "animate-spin")} />
            Tentar novamente
          </Button>
        </div>
      ) : null}

      {project.clips.length > 0 ? (
        <div className="grid gap-3 sm:grid-cols-[repeat(auto-fill,minmax(220px,230px))]">
          {[...project.clips]
            .sort((left, right) => right.score - left.score)
            .map((clip, index) => (
              <article
                key={clip.id || clip.filename || index}
                className="grid min-w-0 grid-cols-[112px_minmax(0,1fr)] overflow-hidden rounded-md border bg-card sm:block sm:w-[230px]"
              >
                {clip.filename ? (
                  <video
                    src={cutFileUrl(project.id, clip.filename)}
                    controls
                    playsInline
                    preload="metadata"
                    className="h-[200px] w-full bg-black object-contain sm:aspect-[9/16] sm:h-auto"
                  />
                ) : (
                  <div className="flex h-[200px] items-center justify-center bg-muted sm:aspect-[9/16] sm:h-auto">
                    <LoaderCircle className="h-6 w-6 animate-spin text-muted-foreground" />
                  </div>
                )}
                <div className="min-w-0 space-y-2 p-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h3 className="text-sm font-semibold">{clip.title}</h3>
                      <p className="mt-0.5 text-[11px] text-muted-foreground">
                        {clip.duration || Math.round(clip.end - clip.start)}s ·{" "}
                        {formatTimestamp(clip.start)} até {formatTimestamp(clip.end)}
                      </p>
                    </div>
                    <div className="rounded bg-status-success/15 px-2 py-1 text-xs font-semibold text-status-success-foreground">
                      {clip.score}
                    </div>
                  </div>
                  <p className="hidden text-xs leading-5 text-muted-foreground sm:block">
                    {clip.reason}
                  </p>
                  {clip.compliance?.blocked ? (
                    <div className="flex gap-1.5 rounded-md bg-status-warn/15 px-2 py-1.5 text-[11px] text-status-warn-foreground">
                      <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                      Revisar legenda e CTA antes de publicar.
                    </div>
                  ) : (
                    <div className="flex items-center gap-1.5 text-[11px] text-status-success">
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      Texto editorial sem alertas
                    </div>
                  )}
                  <div className="flex gap-2">
                    {clip.filename ? (
                      <Button asChild size="sm" className="flex-1">
                        <a href={cutFileUrl(project.id, clip.filename, true)}>
                          <Download className="mr-1.5 h-3.5 w-3.5" />
                          Baixar
                        </a>
                      </Button>
                    ) : null}
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        void navigator.clipboard.writeText(`${clip.caption}\n\n${clip.hashtags}`);
                        toast.success("Legenda copiada.");
                      }}
                    >
                      <Copy className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              </article>
            ))}
        </div>
      ) : project.status === "pronto" ? (
        <div className="rounded-md border border-dashed bg-muted/40 px-4 py-5 text-sm">
          <div className="font-medium">Nenhum corte criado</div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            A seleção automática não encontrou um trecho com força viral suficiente. Tente outro
            vídeo ou escolha uma quantidade fixa para forçar cortes editoriais.
          </p>
        </div>
      ) : null}
    </section>
  );
}

function ProjectStatus({ status }: { status: CutProject["status"] }) {
  const labels = {
    fila: "Na fila",
    processando: "Processando",
    pronto: "Pronto",
    erro: "Erro",
    cancelado: "Interrompido",
  };
  return (
    <span
      className={cn(
        "rounded px-2 py-0.5 text-[11px] font-medium",
        status === "pronto" && "bg-status-success/15 text-status-success-foreground",
        status === "erro" && "bg-status-danger/10 text-status-danger",
        status === "cancelado" && "bg-muted text-muted-foreground",
        activeStatus(status) && "bg-status-info/10 text-status-info",
      )}
    >
      {labels[status]}
    </span>
  );
}

function friendlyCutError(error: string) {
  const normalized = error.toLowerCase();
  if (
    normalized.includes("output_config") ||
    normalized.includes("invalid_request_error") ||
    normalized.includes("maxitems")
  ) {
    return "A IA recusou o formato da análise. A compatibilidade foi corrigida; tente novamente.";
  }
  if (normalized.includes("timeout") || normalized.includes("tempo esgotado")) {
    return "O processamento demorou além do limite. Tente um trecho menor do vídeo.";
  }
  if (error.length > 240 || normalized.startsWith("error code:")) {
    return "Não foi possível concluir a análise. Tente novamente ou selecione um trecho menor.";
  }
  return error;
}

function activeStatus(status: CutProject["status"]) {
  return status === "fila" || status === "processando";
}

function formatTimestamp(seconds: number) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = Math.floor(seconds % 60);
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`
    : `${minutes}:${String(remainder).padStart(2, "0")}`;
}

function parseTimestamp(value: string): number | null {
  const parts = value
    .trim()
    .split(":")
    .map((part) => Number(part));
  if (
    (parts.length !== 2 && parts.length !== 3) ||
    parts.some((part) => !Number.isInteger(part) || part < 0)
  ) {
    return null;
  }
  if (parts.length === 2) {
    const [minutes, seconds] = parts;
    return seconds < 60 ? minutes * 60 + seconds : null;
  }
  const [hours, minutes, seconds] = parts;
  return minutes < 60 && seconds < 60 ? hours * 3600 + minutes * 60 + seconds : null;
}
