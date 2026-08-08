import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import {
  CheckCircle2,
  Download,
  Film,
  Image as ImageIcon,
  LoaderCircle,
  ShieldCheck,
  Upload,
  WandSparkles,
} from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Switch } from "@/components/ui/switch";
import {
  createLocalVideoKit,
  fetchLocalVideoKit,
  fetchLocalVideoKitJobs,
  localVideoKitCoverUrl,
  localVideoKitResultUrl,
  localVideoKitSourceUrl,
  uploadLocalVideoKitSource,
  type LocalVideoKitConfig,
  type LocalVideoKitJob,
} from "@/lib/api/local";

export const Route = createFileRoute("/_app/kit-local")({
  head: () => ({
    meta: [
      { title: "Kit gráfico local | AI Video Creator" },
      {
        name: "description",
        content: "Aplique identidade visual a um vídeo local sem HeyGen e sem tokens.",
      },
    ],
  }),
  component: LocalVideoKitPage,
});

const DEFAULT_CONFIG: LocalVideoKitConfig = {
  name: "Dr. Guilherme Martins",
  role: "Médico",
  title: "4 suplementos para melhorar seu rendimento",
  subtitle: "O que realmente ajuda na atividade física",
  sectionNumber: "Ponto 01",
  sectionTitle: "Cafeína, creatina e desempenho",
  cta: "Quer mais dicas? Siga e acompanhe.",
  site: "@drguilhermemartins",
  accent: "#c8e05a",
  sectionStartSeconds: null,
  includeOpening: true,
  includeLowerThird: true,
  includeSection: true,
  includeOutro: true,
};

function LocalVideoKitPage() {
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [sourcePreview, setSourcePreview] = useState<string | null>(null);
  const [config, setConfig] = useState<LocalVideoKitConfig>(DEFAULT_CONFIG);
  const [job, setJob] = useState<LocalVideoKitJob | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    void fetchLocalVideoKitJobs()
      .then((jobs) => {
        const savedId = window.localStorage.getItem("local-video-kit:last-job");
        const recovered = jobs.find((item) => item.id === savedId) || jobs[0];
        if (recovered) {
          setJob(recovered);
          setConfig(recovered.config);
        }
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!job || !["fila", "processando"].includes(job.status)) return;
    const timer = window.setInterval(() => {
      void fetchLocalVideoKit(job.id)
        .then((current) => {
          setJob(current);
          if (current.status === "pronto") toast.success("Kit gráfico aplicado localmente.");
          if (current.status === "erro") toast.error(current.erro || "A edição local falhou.");
        })
        .catch(() => undefined);
    }, 1800);
    return () => window.clearInterval(timer);
  }, [job?.id, job?.status]);

  useEffect(
    () => () => {
      if (sourcePreview) URL.revokeObjectURL(sourcePreview);
    },
    [sourcePreview],
  );

  function selectFile(selected?: File) {
    if (!selected) return;
    if (!selected.type.startsWith("video/")) {
      toast.error("Selecione um arquivo de vídeo.");
      return;
    }
    if (sourcePreview) URL.revokeObjectURL(sourcePreview);
    setFile(selected);
    setSourcePreview(URL.createObjectURL(selected));
  }

  function update<K extends keyof LocalVideoKitConfig>(key: K, value: LocalVideoKitConfig[K]) {
    setConfig((current) => ({ ...current, [key]: value }));
  }

  async function applyKit() {
    if (!file) {
      toast.error("Escolha um vídeo local primeiro.");
      return;
    }
    setSubmitting(true);
    try {
      const upload = await uploadLocalVideoKitSource(file);
      const created = await createLocalVideoKit({
        uploadId: upload.uploadId,
        sourceName: file.name,
        config,
      });
      window.localStorage.setItem("local-video-kit:last-job", created.id);
      setJob(created);
      toast.success("Edição local iniciada. Nenhum crédito externo será usado.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível aplicar o kit.");
    } finally {
      setSubmitting(false);
    }
  }

  const working = submitting || job?.status === "fila" || job?.status === "processando";
  const originalUrl = sourcePreview || (job ? localVideoKitSourceUrl(job.id) : null);

  return (
    <AppShell
      title="Kit gráfico local"
      actions={
        <div className="hidden items-center gap-1.5 rounded-full border border-status-success/30 bg-status-success/10 px-3 py-1 text-[11px] font-medium text-status-success md:flex">
          <ShieldCheck className="h-3.5 w-3.5" /> Zero HeyGen · zero tokens
        </div>
      }
    >
      <div className="grid gap-5 xl:grid-cols-[380px_minmax(0,1fr)]">
        <aside className="space-y-4">
          <Card>
            <CardHeader className="pb-4">
              <CardTitle className="text-base">1. Vídeo e identidade</CardTitle>
              <p className="text-xs leading-relaxed text-muted-foreground">
                O arquivo fica no computador e é renderizado com FFmpeg local.
              </p>
            </CardHeader>
            <CardContent className="space-y-4">
              <input
                ref={fileInput}
                id="local-kit-video"
                type="file"
                accept="video/mp4,video/quicktime,video/webm"
                className="sr-only"
                onChange={(event) => selectFile(event.target.files?.[0])}
              />
              <button
                type="button"
                onClick={() => fileInput.current?.click()}
                className="flex min-h-24 w-full cursor-pointer items-center gap-3 rounded-lg border border-dashed bg-muted/35 p-4 text-left transition-colors hover:border-primary/45 hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-card shadow-sm">
                  <Upload className="h-5 w-5 text-primary" />
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold">
                    {file?.name || job?.sourceName || "Escolher vídeo local"}
                  </span>
                  <span className="mt-1 block text-xs text-muted-foreground">MP4, MOV ou WebM · até 2 GB</span>
                </span>
              </button>

              <TextField id="kit-name" label="Nome" value={config.name} onChange={(value) => update("name", value)} />
              <TextField id="kit-role" label="Cargo" value={config.role} onChange={(value) => update("role", value)} />
              <TextField id="kit-title" label="Título" value={config.title} onChange={(value) => update("title", value)} />
              <TextField id="kit-subtitle" label="Subtítulo" value={config.subtitle} onChange={(value) => update("subtitle", value)} />
              <TextField id="kit-section" label="Cartela de tópico" value={config.sectionTitle} onChange={(value) => update("sectionTitle", value)} />
              <TextField id="kit-cta" label="Encerramento" value={config.cta} onChange={(value) => update("cta", value)} />
              <TextField id="kit-site" label="Perfil ou site" value={config.site} onChange={(value) => update("site", value)} />

              <div className="grid grid-cols-[1fr_72px] items-end gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="kit-section-time">Cartela aos segundos</Label>
                  <Input
                    id="kit-section-time"
                    type="number"
                    min={3}
                    step={0.5}
                    placeholder="Automático"
                    value={config.sectionStartSeconds ?? ""}
                    onChange={(event) =>
                      update(
                        "sectionStartSeconds",
                        event.target.value ? Number(event.target.value) : null,
                      )
                    }
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="kit-accent">Destaque</Label>
                  <Input
                    id="kit-accent"
                    type="color"
                    value={config.accent}
                    onChange={(event) => update("accent", event.target.value)}
                    className="cursor-pointer p-1"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">2. Peças aplicadas</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1">
              <PieceSwitch label="Abertura" detail="0–2 segundos" checked={config.includeOpening} onCheckedChange={(value) => update("includeOpening", value)} />
              <PieceSwitch label="Lower third" detail="Nome e cargo por 4 segundos" checked={config.includeLowerThird} onCheckedChange={(value) => update("includeLowerThird", value)} />
              <PieceSwitch label="Cartela" detail="Virada de assunto por 1 segundo" checked={config.includeSection} onCheckedChange={(value) => update("includeSection", value)} />
              <PieceSwitch label="Encerramento" detail="Últimos 3 segundos" checked={config.includeOutro} onCheckedChange={(value) => update("includeOutro", value)} />
            </CardContent>
          </Card>

          <Button className="h-11 w-full" onClick={applyKit} disabled={!file || working}>
            {working ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <WandSparkles className="mr-2 h-4 w-4" />}
            {working ? "Aplicando kit local..." : "Aplicar kit local"}
          </Button>
        </aside>

        <section className="space-y-5">
          <Card className="overflow-hidden">
            <CardHeader className="border-b bg-muted/25 pb-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-base">Comparação</CardTitle>
                  <p className="mt-1 text-xs text-muted-foreground">
                    O áudio e a duração são preservados; apenas o visual é renderizado.
                  </p>
                </div>
                {job?.status === "pronto" ? (
                  <div className="flex items-center gap-2">
                    <Button asChild size="sm" variant="secondary">
                      <a href={localVideoKitCoverUrl(job.id, true)}>
                        <ImageIcon className="mr-1.5 h-4 w-4" /> Baixar capa
                      </a>
                    </Button>
                    <Button asChild size="sm">
                      <a href={localVideoKitResultUrl(job.id, true)}>
                        <Download className="mr-1.5 h-4 w-4" /> Baixar MP4
                      </a>
                    </Button>
                  </div>
                ) : null}
              </div>
            </CardHeader>
            <CardContent className="p-4 md:p-5">
              <div className="grid gap-4 lg:grid-cols-2">
                <VideoPanel title="Original" url={originalUrl} />
                <VideoPanel
                  title="Com kit gráfico"
                  url={job?.status === "pronto" ? localVideoKitResultUrl(job.id) : null}
                  pending={working}
                />
              </div>
            </CardContent>
          </Card>

          {job ? (
            <Card>
              <CardContent className="space-y-3 p-5" aria-live="polite">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 text-sm font-semibold">
                    {job.status === "pronto" ? (
                      <CheckCircle2 className="h-4 w-4 text-status-success" />
                    ) : job.status === "erro" ? (
                      <Film className="h-4 w-4 text-destructive" />
                    ) : (
                      <LoaderCircle className="h-4 w-4 animate-spin text-primary" />
                    )}
                    {job.etapa}
                  </div>
                  <span className="text-xs tabular-nums text-muted-foreground">{job.progresso}%</span>
                </div>
                <Progress value={job.progresso} className="h-2" />
                {job.erro ? <p className="text-sm text-destructive">{job.erro}</p> : null}
                {job.status === "pronto" ? (
                  <div className="rounded-lg bg-status-success/8 p-3 text-xs leading-relaxed text-muted-foreground">
                    Salvo em <span className="font-mono text-foreground">{job.outputPath}</span>. Nenhum crédito externo foi utilizado.
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ) : (
            <div className="rounded-xl border border-dashed bg-muted/20 px-6 py-12 text-center">
              <Film className="mx-auto h-8 w-8 text-muted-foreground/60" />
              <h2 className="mt-3 text-sm font-semibold">Escolha um vídeo para começar</h2>
              <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-muted-foreground">
                A prévia original e o resultado editado aparecerão juntos aqui.
              </p>
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}

function TextField({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} value={value} onChange={(event) => onChange(event.target.value)} />
    </div>
  );
}

function PieceSwitch({
  label,
  detail,
  checked,
  onCheckedChange,
}: {
  label: string;
  detail: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg px-2 py-2.5">
      <div>
        <div className="text-sm font-medium">{label}</div>
        <div className="text-xs text-muted-foreground">{detail}</div>
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} aria-label={`Aplicar ${label}`} />
    </div>
  );
}

function VideoPanel({
  title,
  url,
  pending = false,
}: {
  title: string;
  url: string | null;
  pending?: boolean;
}) {
  return (
    <div>
      <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{title}</div>
      <div className="relative mx-auto aspect-[9/16] w-full max-w-[360px] overflow-hidden rounded-xl border bg-[#0f0f10] shadow-sm">
        {url ? (
          <video src={url} controls playsInline preload="metadata" className="h-full w-full object-contain" />
        ) : (
          <div className="flex h-full flex-col items-center justify-center px-8 text-center text-muted-foreground">
            {pending ? <LoaderCircle className="h-7 w-7 animate-spin" /> : <Film className="h-7 w-7" />}
            <p className="mt-3 text-xs leading-relaxed">
              {pending ? "Renderizando localmente..." : "O resultado aparecerá aqui."}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
