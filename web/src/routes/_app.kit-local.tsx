import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import {
  AudioLines,
  Captions,
  CheckCircle2,
  Download,
  Film,
  Image as ImageIcon,
  LoaderCircle,
  Mic2,
  ScanLine,
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
  fetchMusicTracks,
  fetchLocalVideoKit,
  fetchLocalVideoKitJobs,
  localVideoKitCoverUrl,
  localVideoKitResultUrl,
  localVideoKitSourceUrl,
  uploadLocalVideoKitSource,
  videoFileUrl,
  type LocalVideoKitConfig,
  type LocalVideoKitJob,
  type MusicTrack,
} from "@/lib/api/local";

export const Route = createFileRoute("/_app/kit-local")({
  validateSearch: (search: Record<string, unknown>) => ({
    videoJobId:
      typeof search.videoJobId === "string" && search.videoJobId.trim()
        ? search.videoJobId.trim().slice(0, 160)
        : undefined,
    sourceName:
      typeof search.sourceName === "string" && search.sourceName.trim()
        ? search.sourceName.trim().slice(0, 300)
        : undefined,
  }),
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
  sectionDurationSeconds: 3,
  sectionTransition: "fade",
  musicTrackId: null,
  musicVolume: 0.12,
  includeCaptions: true,
  captionStyle: "dynamic",
  captionPosition: "safe_bottom",
  highlightKeywords: true,
  duckMusicDuringSpeech: true,
  motionPreset: "subtle",
  enhanceVoice: true,
  outroTailSeconds: 10,
  includeOpening: true,
  includeLowerThird: true,
  includeSection: true,
  includeOutro: true,
};

const CAPTION_STYLES: Array<{
  id: LocalVideoKitConfig["captionStyle"];
  name: string;
  detail: string;
}> = [
  {
    id: "dynamic",
    name: "Dinâmica",
    detail: "Alto contraste e palavras-chave em destaque.",
  },
  {
    id: "clean",
    name: "Clean clínico",
    detail: "Bloco discreto para conteúdos técnicos.",
  },
  {
    id: "editorial",
    name: "Editorial",
    detail: "Serifa elegante com ritmo mais calmo.",
  },
];

const CAPTION_POSITIONS: Array<{
  id: LocalVideoKitConfig["captionPosition"];
  name: string;
}> = [
  { id: "upper", name: "Superior" },
  { id: "center", name: "Centro" },
  { id: "safe_bottom", name: "Inferior seguro" },
];

const MOTION_PRESETS: Array<{
  id: LocalVideoKitConfig["motionPreset"];
  name: string;
  detail: string;
  strength: string;
}> = [
  {
    id: "subtle",
    name: "Natural",
    detail: "Aproximação suave no rosto, com entrada e saída delicadas.",
    strength: "14%",
  },
  {
    id: "social",
    name: "Social",
    detail: "Chega mais perto do rosto com movimento mais presente.",
    strength: "22%",
  },
  {
    id: "none",
    name: "Sem zoom",
    detail: "Mantém o enquadramento original durante toda a fala.",
    strength: "0%",
  },
];

function LocalVideoKitPage() {
  const { videoJobId, sourceName } = Route.useSearch();
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [sourcePreview, setSourcePreview] = useState<string | null>(null);
  const [config, setConfig] = useState<LocalVideoKitConfig>(DEFAULT_CONFIG);
  const [musicTracks, setMusicTracks] = useState<MusicTrack[]>([]);
  const [job, setJob] = useState<LocalVideoKitJob | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    void fetchMusicTracks()
      .then(setMusicTracks)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (videoJobId) return;
    void fetchLocalVideoKitJobs()
      .then((jobs) => {
        const savedId = window.localStorage.getItem("local-video-kit:last-job");
        const recovered = jobs.find((item) => item.id === savedId) || jobs[0];
        if (recovered) {
          setJob(recovered);
          setConfig({ ...DEFAULT_CONFIG, ...recovered.config });
        }
      })
      .catch(() => undefined);
  }, [videoJobId]);

  useEffect(() => {
    if (!videoJobId) return;
    setFile(null);
    setJob(null);
    setConfig((current) => ({
      ...current,
      title: (sourceName || current.title).slice(0, 120),
      subtitle: "Informação clara, direto ao ponto.",
      sectionNumber: "Destaque",
      sectionTitle: "Ponto principal",
    }));
  }, [sourceName, videoJobId]);

  const activeJobId = job?.id;
  const activeJobStatus = job?.status;

  useEffect(() => {
    if (!activeJobId || !activeJobStatus || !["fila", "processando"].includes(activeJobStatus)) {
      return;
    }
    const timer = window.setInterval(() => {
      void fetchLocalVideoKit(activeJobId)
        .then((current) => {
          setJob(current);
          if (current.status === "pronto") toast.success("Kit gráfico aplicado localmente.");
          if (current.status === "erro") toast.error(current.erro || "A edição local falhou.");
        })
        .catch(() => undefined);
    }, 1800);
    return () => window.clearInterval(timer);
  }, [activeJobId, activeJobStatus]);

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
    if (!file && !videoJobId && job?.status !== "pronto") {
      toast.error("Escolha um vídeo local primeiro.");
      return;
    }
    setSubmitting(true);
    try {
      const upload = file ? await uploadLocalVideoKitSource(file) : null;
      const created = await createLocalVideoKit({
        uploadId: upload?.uploadId,
        videoJobId: file ? undefined : videoJobId,
        sourceKitJobId: file || videoJobId || job?.status !== "pronto" ? undefined : job.id,
        sourceName: file?.name || sourceName || job?.sourceName || `video-${videoJobId}.mp4`,
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
  const selectedMusicTrack = musicTracks.find((track) => track.id === config.musicTrackId) || null;
  const originalUrl =
    sourcePreview ||
    (videoJobId ? videoFileUrl(videoJobId) : job ? localVideoKitSourceUrl(job.id) : null);

  return (
    <AppShell
      title="Kit gráfico local"
      actions={
        <div className="hidden items-center gap-1.5 rounded-full border border-status-success/30 bg-status-success/10 px-3 py-1 text-[11px] font-medium text-status-success md:flex">
          <ShieldCheck className="h-3.5 w-3.5" /> Zero HeyGen · zero tokens
        </div>
      }
    >
      <div className="grid gap-5 xl:grid-cols-[minmax(440px,500px)_minmax(0,1fr)] 2xl:grid-cols-[520px_minmax(0,1fr)]">
        <aside className="grid content-start gap-4 self-start md:grid-cols-2 xl:grid-cols-1">
          <Card className="overflow-hidden md:col-span-2 xl:col-span-1">
            <CardHeader className="border-b bg-muted/20 pb-4">
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
                    {file?.name ||
                      (videoJobId ? sourceName || `Vídeo ${videoJobId}` : null) ||
                      job?.sourceName ||
                      "Escolher vídeo local"}
                  </span>
                  <span className="mt-1 block text-xs text-muted-foreground">
                    {videoJobId && !file
                      ? "Carregado da Produção · clique para substituir"
                      : "MP4, MOV ou WebM · até 2 GB"}
                  </span>
                </span>
              </button>

              <TextField
                id="kit-name"
                label="Nome"
                value={config.name}
                onChange={(value) => update("name", value)}
              />
              <TextField
                id="kit-role"
                label="Cargo"
                value={config.role}
                onChange={(value) => update("role", value)}
              />
              <TextField
                id="kit-title"
                label="Título"
                value={config.title}
                onChange={(value) => update("title", value)}
              />
              <TextField
                id="kit-subtitle"
                label="Subtítulo"
                value={config.subtitle}
                onChange={(value) => update("subtitle", value)}
              />
              <TextField
                id="kit-section"
                label="Cartela de tópico"
                value={config.sectionTitle}
                onChange={(value) => update("sectionTitle", value)}
              />
              <TextField
                id="kit-cta"
                label="Encerramento"
                value={config.cta}
                onChange={(value) => update("cta", value)}
              />
              <TextField
                id="kit-site"
                label="Perfil ou site"
                value={config.site}
                onChange={(value) => update("site", value)}
              />

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="kit-section-start">Cartela entra aos</Label>
                  <Input
                    id="kit-section-start"
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
                  <p className="text-[11px] text-muted-foreground">segundos do vídeo</p>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="kit-section-duration">Fica na tela por</Label>
                  <Input
                    id="kit-section-duration"
                    type="number"
                    min={0.5}
                    max={120}
                    step={0.5}
                    value={config.sectionDurationSeconds ?? 3}
                    onChange={(event) =>
                      update(
                        "sectionDurationSeconds",
                        event.target.value ? Number(event.target.value) : 3,
                      )
                    }
                  />
                  <p className="text-[11px] text-muted-foreground">segundos</p>
                </div>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="kit-accent">Destaque</Label>
                <Input
                  id="kit-accent"
                  type="color"
                  value={config.accent}
                  onChange={(event) => update("accent", event.target.value)}
                  className="h-10 w-full cursor-pointer p-1"
                />
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="kit-section-transition">Transição da cartela</Label>
                  <select
                    id="kit-section-transition"
                    value={config.sectionTransition ?? "fade"}
                    onChange={(event) =>
                      update(
                        "sectionTransition",
                        event.target.value as LocalVideoKitConfig["sectionTransition"],
                      )
                    }
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus:ring-2 focus:ring-ring"
                  >
                    <option value="fade">Fade suave</option>
                    <option value="slide_up">Deslizar de baixo</option>
                    <option value="none">Corte direto</option>
                  </select>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="kit-music">Música de fundo</Label>
                  <select
                    id="kit-music"
                    value={config.musicTrackId ?? ""}
                    onChange={(event) => update("musicTrackId", event.target.value || null)}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus:ring-2 focus:ring-ring"
                  >
                    <option value="">Sem música</option>
                    {musicTracks.map((track) => (
                      <option key={track.id} value={track.id}>
                        {track.name} · {track.mood}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {selectedMusicTrack ? (
                <div className="space-y-1.5 rounded-lg border bg-muted/20 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <Label htmlFor="kit-music-preview">Prévia da música</Label>
                    <span className="truncate text-xs text-muted-foreground">
                      {selectedMusicTrack.name}
                    </span>
                  </div>
                  <audio
                    id="kit-music-preview"
                    controls
                    preload="none"
                    src={selectedMusicTrack.url}
                    className="h-9 w-full"
                  />
                </div>
              ) : null}

              {config.musicTrackId ? (
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between gap-3">
                    <Label htmlFor="kit-music-volume">Volume da música</Label>
                    <span className="text-xs tabular-nums text-muted-foreground">
                      {Math.round((config.musicVolume ?? 0.12) * 100)}%
                    </span>
                  </div>
                  <Input
                    id="kit-music-volume"
                    type="range"
                    min={3}
                    max={25}
                    step={1}
                    value={Math.round((config.musicVolume ?? 0.12) * 100)}
                    onChange={(event) => update("musicVolume", Number(event.target.value) / 100)}
                    className="cursor-pointer px-0"
                  />
                  <p className="text-[11px] text-muted-foreground">
                    A trilha entra baixa e preserva o áudio original.
                  </p>
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card className="overflow-hidden md:col-span-2 xl:col-span-1">
            <CardHeader className="border-b bg-muted/20 pb-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Captions className="h-4 w-4 text-primary" />
                    2. Legendas e acabamento
                  </CardTitle>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    Sincronização automática em PT-BR, feita neste computador.
                  </p>
                </div>
                <span className="shrink-0 rounded-full border border-status-success/25 bg-status-success/8 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-status-success">
                  Local
                </span>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between gap-3 rounded-xl border bg-muted/20 p-3">
                <div>
                  <div className="text-sm font-semibold">Legendas automáticas</div>
                  <div className="mt-0.5 text-xs text-muted-foreground">
                    Frases curtas, sincronizadas com a fala.
                  </div>
                </div>
                <Switch
                  checked={config.includeCaptions}
                  onCheckedChange={(value) => update("includeCaptions", value)}
                  aria-label="Aplicar legendas automáticas"
                />
              </div>

              {config.includeCaptions ? (
                <>
                  <CaptionPreview config={config} />

                  <div className="space-y-2">
                    <Label>Estilo da legenda</Label>
                    <div className="space-y-2">
                      {CAPTION_STYLES.map((style) => {
                        const selected = config.captionStyle === style.id;
                        return (
                          <button
                            key={style.id}
                            type="button"
                            aria-pressed={selected}
                            onClick={() => update("captionStyle", style.id)}
                            className={`flex w-full cursor-pointer items-start gap-3 rounded-lg border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                              selected
                                ? "border-primary/60 bg-primary/8"
                                : "bg-background hover:border-primary/30 hover:bg-muted/35"
                            }`}
                          >
                            <span
                              className="mt-0.5 h-3 w-3 shrink-0 rounded-full border-2"
                              style={{
                                borderColor: selected ? config.accent : undefined,
                                backgroundColor: selected ? config.accent : "transparent",
                              }}
                            />
                            <span>
                              <span className="block text-sm font-semibold">{style.name}</span>
                              <span className="mt-0.5 block text-xs text-muted-foreground">
                                {style.detail}
                              </span>
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label>Posição no vídeo</Label>
                    <div className="grid grid-cols-3 rounded-lg border bg-muted/25 p-1">
                      {CAPTION_POSITIONS.map((position) => (
                        <button
                          key={position.id}
                          type="button"
                          aria-pressed={config.captionPosition === position.id}
                          onClick={() => update("captionPosition", position.id)}
                          className={`min-h-9 cursor-pointer rounded-md px-2 text-[11px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                            config.captionPosition === position.id
                              ? "bg-background text-foreground shadow-sm"
                              : "text-muted-foreground hover:text-foreground"
                          }`}
                        >
                          {position.name}
                        </button>
                      ))}
                    </div>
                    <p className="text-[11px] leading-relaxed text-muted-foreground">
                      “Inferior seguro” evita os controles e textos das redes sociais.
                    </p>
                  </div>

                  <PieceSwitch
                    label="Palavras-chave"
                    detail="Destaca automaticamente os termos mais importantes"
                    checked={config.highlightKeywords}
                    onCheckedChange={(value) => update("highlightKeywords", value)}
                  />
                </>
              ) : null}

              {config.musicTrackId ? (
                <PieceSwitch
                  label="Mixagem inteligente"
                  detail="Abaixa a música durante a fala e recupera nas pausas"
                  checked={config.duckMusicDuringSpeech}
                  onCheckedChange={(value) => update("duckMusicDuringSpeech", value)}
                />
              ) : (
                <div className="flex items-center gap-3 rounded-lg border border-dashed px-3 py-3 text-xs leading-relaxed text-muted-foreground">
                  <AudioLines className="h-4 w-4 shrink-0" />
                  Escolha uma música acima para ativar a mixagem inteligente.
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="overflow-hidden">
            <CardHeader className="border-b bg-muted/20 pb-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <ScanLine className="h-4 w-4 text-primary" />
                    3. Ritmo e movimento
                  </CardTitle>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    Aproximações suaves priorizam o rosto e ajudam a manter a atenção.
                  </p>
                </div>
                <span className="shrink-0 rounded-full border border-primary/20 bg-primary/8 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-primary">
                  Automático
                </span>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <MotionPreview preset={config.motionPreset} accent={config.accent} />

              <div className="space-y-2">
                <Label>Ritmo do enquadramento</Label>
                <div className="space-y-2">
                  {MOTION_PRESETS.map((preset) => {
                    const selected = config.motionPreset === preset.id;
                    return (
                      <button
                        key={preset.id}
                        type="button"
                        aria-pressed={selected}
                        onClick={() => update("motionPreset", preset.id)}
                        className={`flex w-full cursor-pointer items-start justify-between gap-3 rounded-lg border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                          selected
                            ? "border-primary/60 bg-primary/8"
                            : "bg-background hover:border-primary/30 hover:bg-muted/35"
                        }`}
                      >
                        <span className="flex items-start gap-3">
                          <span
                            className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border"
                            style={{
                              borderColor: selected
                                ? accentWithOpacity(config.accent, "99")
                                : undefined,
                              backgroundColor: selected
                                ? accentWithOpacity(config.accent, "18")
                                : undefined,
                            }}
                          >
                            <span
                              className={`block rounded-sm border ${
                                preset.id === "social"
                                  ? "h-2 w-2"
                                  : preset.id === "subtle"
                                    ? "h-2.5 w-2.5"
                                    : "h-3 w-3"
                              }`}
                            />
                          </span>
                          <span>
                            <span className="block text-sm font-semibold">{preset.name}</span>
                            <span className="mt-0.5 block text-xs text-muted-foreground">
                              {preset.detail}
                            </span>
                          </span>
                        </span>
                        <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold tabular-nums text-muted-foreground">
                          {preset.strength}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="rounded-xl border bg-muted/20 p-1">
                <div className="flex items-center justify-between gap-3 rounded-lg px-2 py-2.5">
                  <div className="flex gap-3">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-background shadow-sm">
                      <Mic2 className="h-4 w-4 text-primary" />
                    </span>
                    <div>
                      <div className="text-sm font-medium">Clareza de voz</div>
                      <div className="text-xs leading-relaxed text-muted-foreground">
                        Reduz graves, equilibra volume e evita picos
                      </div>
                    </div>
                  </div>
                  <Switch
                    checked={config.enhanceVoice}
                    onCheckedChange={(value) => update("enhanceVoice", value)}
                    aria-label="Aplicar clareza de voz"
                  />
                </div>
              </div>

              <p className="text-[11px] leading-relaxed text-muted-foreground">
                O movimento usa aceleração suave, prioriza o rosto e não entra sobre a cartela.
              </p>
            </CardContent>
          </Card>

          <Card className="overflow-hidden">
            <CardHeader className="border-b bg-muted/20 pb-3">
              <CardTitle className="text-base">4. Peças aplicadas</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1">
              <PieceSwitch
                label="Abertura"
                detail="0–2 segundos"
                checked={config.includeOpening}
                onCheckedChange={(value) => update("includeOpening", value)}
              />
              <PieceSwitch
                label="Lower third"
                detail="Nome e cargo por 4 segundos"
                checked={config.includeLowerThird}
                onCheckedChange={(value) => update("includeLowerThird", value)}
              />
              <PieceSwitch
                label="Cartela"
                detail={`${config.sectionTransition === "slide_up" ? "Desliza" : config.sectionTransition === "none" ? "Corte direto" : "Fade"} · ${config.sectionDurationSeconds ?? 3} segundos`}
                checked={config.includeSection}
                onCheckedChange={(value) => update("includeSection", value)}
              />
              <div className="space-y-1.5 rounded-lg border bg-muted/20 px-3 py-2.5">
                <div className="flex items-center justify-between gap-3">
                  <Label htmlFor="kit-outro-tail">Slide final acrescenta</Label>
                  <span className="text-xs text-muted-foreground">segundos</span>
                </div>
                <Input
                  id="kit-outro-tail"
                  type="number"
                  min={0}
                  max={120}
                  step={0.5}
                  value={config.outroTailSeconds ?? 10}
                  onChange={(event) =>
                    update("outroTailSeconds", event.target.value ? Number(event.target.value) : 10)
                  }
                />
              </div>
              <PieceSwitch
                label="Encerramento"
                detail={`Fim do vídeo + ${config.outroTailSeconds ?? 10}s${config.musicTrackId ? " só com música" : ""}`}
                checked={config.includeOutro}
                onCheckedChange={(value) => update("includeOutro", value)}
              />
            </CardContent>
          </Card>

          <Button
            className="h-11 w-full md:col-span-2 xl:col-span-1"
            onClick={applyKit}
            disabled={(!file && !videoJobId && job?.status !== "pronto") || working}
          >
            {working ? (
              <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <WandSparkles className="mr-2 h-4 w-4" />
            )}
            {working
              ? "Aplicando acabamento local..."
              : videoJobId && !file
                ? "Aplicar acabamento neste vídeo"
                : job?.status === "pronto" && !file
                  ? "Aplicar acabamento novamente"
                  : "Aplicar kit e acabamento"}
          </Button>
        </aside>

        <section className="space-y-5">
          <Card className="overflow-hidden bg-card xl:sticky xl:top-4 xl:z-10">
            <CardHeader className="border-b bg-muted/25 pb-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-base">Comparação</CardTitle>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Legendas, identidade, ritmo e mixagem são renderizados localmente no MP4 final.
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
                  <span className="text-xs tabular-nums text-muted-foreground">
                    {job.progresso}%
                  </span>
                </div>
                <Progress value={job.progresso} className="h-2" />
                {job.erro ? <p className="text-sm text-destructive">{job.erro}</p> : null}
                {job.status === "pronto" ? (
                  <div className="rounded-lg bg-status-success/8 p-3 text-xs leading-relaxed text-muted-foreground">
                    Salvo em <span className="font-mono text-foreground">{job.outputPath}</span>.
                    Nenhum crédito externo foi utilizado.
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ) : file || videoJobId ? (
            <div className="rounded-xl border border-status-success/25 bg-status-success/5 px-6 py-10 text-center">
              <CheckCircle2 className="mx-auto h-8 w-8 text-status-success" />
              <h2 className="mt-3 text-sm font-semibold">Vídeo pronto para edição local</h2>
              <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-muted-foreground">
                Ajuste as peças, escolha o ritmo e aplique o acabamento local.
              </p>
            </div>
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

function accentWithOpacity(color: string, opacity: string) {
  return /^#[0-9a-fA-F]{6}$/.test(color) ? `${color}${opacity}` : undefined;
}

function MotionPreview({
  preset,
  accent,
}: {
  preset: LocalVideoKitConfig["motionPreset"];
  accent: string;
}) {
  const frameClass = preset === "social" ? "inset-7" : preset === "subtle" ? "inset-5" : "inset-1";
  const label =
    preset === "social" ? "Zoom suave 22%" : preset === "subtle" ? "Zoom suave 14%" : "Sem zoom";
  const moments = preset === "social" ? [12, 34, 58, 80] : preset === "subtle" ? [20, 54, 82] : [];

  return (
    <div
      className="rounded-xl border bg-muted/20 p-3"
      aria-label="Prévia do ritmo de enquadramento"
    >
      <div className="relative h-32 overflow-hidden rounded-lg bg-[radial-gradient(circle_at_50%_24%,#506879_0%,#1c2d37_48%,#091319_100%)]">
        <div className="absolute left-1/2 top-5 h-10 w-10 -translate-x-1/2 rounded-full border border-white/10 bg-white/16" />
        <div className="absolute left-1/2 top-14 h-24 w-20 -translate-x-1/2 rounded-t-[2rem] border border-white/10 bg-white/12" />
        <div
          className={`absolute ${frameClass} rounded-md border`}
          style={{ borderColor: accentWithOpacity(accent, preset === "none" ? "3D" : "B3") }}
        />
        <span className="absolute right-2 top-2 rounded bg-black/45 px-2 py-1 text-[9px] font-semibold uppercase tracking-wide text-white/75">
          {label}
        </span>
      </div>
      <div className="relative mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
        {moments.map((position) => (
          <span
            key={position}
            className="absolute top-0 h-full w-[11%] rounded-full"
            style={{
              left: `${position}%`,
              backgroundImage: `linear-gradient(90deg, transparent, ${accent}, ${accent}, transparent)`,
            }}
          />
        ))}
      </div>
      <div className="mt-1.5 flex justify-between text-[9px] font-medium uppercase tracking-wide text-muted-foreground">
        <span>Início</span>
        <span>{moments.length ? `${moments.length} momentos` : "Enquadramento fixo"}</span>
        <span>Fim</span>
      </div>
    </div>
  );
}

function CaptionPreview({ config }: { config: LocalVideoKitConfig }) {
  const positionClass =
    config.captionPosition === "upper"
      ? "justify-start pt-5"
      : config.captionPosition === "center"
        ? "justify-center"
        : "justify-end pb-6";
  const captionClass =
    config.captionStyle === "clean"
      ? "rounded-xl border border-white/15 bg-slate-950/85 px-3 py-2 text-base font-bold leading-tight shadow-xl"
      : config.captionStyle === "editorial"
        ? "font-serif text-xl font-bold italic leading-tight drop-shadow-[0_3px_1px_rgba(0,0,0,0.9)]"
        : "text-lg font-black uppercase leading-none tracking-tight drop-shadow-[0_3px_1px_rgba(0,0,0,0.95)]";

  return (
    <div
      className={`relative flex h-44 flex-col items-center overflow-hidden rounded-xl border bg-[radial-gradient(circle_at_50%_25%,#496578_0%,#172630_48%,#081116_100%)] px-5 ${positionClass}`}
      aria-label="Prévia do estilo da legenda"
    >
      <div className="absolute left-1/2 top-4 h-24 w-16 -translate-x-1/2 rounded-full bg-white/8 blur-xl" />
      <div className={`relative z-10 mx-auto max-w-[290px] text-center text-white ${captionClass}`}>
        Informação com{" "}
        <span style={{ color: config.highlightKeywords ? config.accent : undefined }}>clareza</span>
      </div>
      <span className="absolute bottom-2 right-2 rounded bg-black/35 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide text-white/65">
        Prévia
      </span>
    </div>
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
      <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </div>
      <div className="relative mx-auto aspect-[9/16] w-full max-w-[360px] overflow-hidden rounded-xl border bg-[#0f0f10] shadow-sm">
        {url ? (
          <video
            src={url}
            controls
            playsInline
            preload="metadata"
            className="h-full w-full object-contain"
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center px-8 text-center text-muted-foreground">
            {pending ? (
              <LoaderCircle className="h-7 w-7 animate-spin" />
            ) : (
              <Film className="h-7 w-7" />
            )}
            <p className="mt-3 text-xs leading-relaxed">
              {pending ? "Renderizando localmente..." : "O resultado aparecerá aqui."}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
