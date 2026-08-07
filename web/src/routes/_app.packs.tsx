import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { prioridadeLabel, riskLabel } from "@/lib/status";
import { useStore } from "@/lib/store";
import {
  exportPack,
  fetchPack,
  fetchPackPhotoAssets,
  generatePack,
  refreshPackAvatar,
  updatePackCarouselPhoto,
  type GeneratedPack,
  type PackLayout,
  type PackPhotoAsset,
  type PackSlide,
} from "@/lib/api/local";
import {
  CalendarPlus,
  CheckCircle2,
  Copy,
  FileText,
  FolderDown,
  Image as ImageIcon,
  Layers3,
  Loader2,
  MessageSquareText,
  PanelsTopLeft,
  RefreshCw,
  Video,
  Wand2,
} from "lucide-react";

export const Route = createFileRoute("/_app/packs")({
  validateSearch: (search: Record<string, unknown>) => ({
    scriptId: typeof search.scriptId === "string" ? search.scriptId : undefined,
  }),
  head: () => ({
    meta: [
      { title: "Pack de conteudo | AI Video Creator" },
      {
        name: "description",
        content: "Carrossel editorial de 7 slides criado a partir de um roteiro.",
      },
      { property: "og:title", content: "Pack de conteudo | AI Video Creator" },
      {
        property: "og:description",
        content: "Seis slides, legenda pronta e identidade visual consistente.",
      },
    ],
  }),
  component: PacksPage,
});

type Pack = GeneratedPack;

const layoutLabels: Record<PackLayout, string> = {
  hero_photo: "Capa com foto",
  photo_split: "Foto dividida",
  big_statement: "Frase de impacto",
  question: "Pergunta",
  myth_fact: "Mito e fato",
  number_stat: "Numero ou dado",
  three_points: "Tres pontos",
  explainer: "Explicacao em etapas",
  doctor_quote: "Citacao medica",
  photo_overlay: "Foto com texto",
  do_dont: "Evite e prefira",
  cta_photo: "CTA com foto",
};

const photoLayouts = new Set<PackLayout>([
  "hero_photo",
  "photo_split",
  "doctor_quote",
  "photo_overlay",
  "cta_photo",
]);

function layoutOf(slide: PackSlide): PackLayout {
  return slide.layoutId ?? slide.layout ?? "explainer";
}

function headlineOf(slide: PackSlide): string {
  const fields = slide.fields;
  return (
    fields?.headline || fields?.quote || fields?.item1?.text || slide.title || "Texto do slide"
  );
}

function bodyOf(slide: PackSlide): string {
  const fields = slide.fields;
  return fields?.body || fields?.subheadline || slide.body || "";
}

function photoIdOf(slide: PackSlide): string {
  return slide.fields?.photoId || slide.photoAsset?.id || "";
}

function detailLines(slide: PackSlide): string[] {
  const fields = slide.fields;
  if (!fields) return slide.highlight ? [slide.highlight] : [];
  const lines: string[] = [];
  if (fields.statistic) lines.push(fields.statistic);
  for (const item of [fields.item1, fields.item2, fields.item3]) {
    const line = [item?.title, item?.text].filter(Boolean).join(": ");
    if (line) lines.push(line);
  }
  if (fields.caption && fields.caption !== bodyOf(slide)) lines.push(fields.caption);
  if (fields.cta) lines.push(fields.cta);
  if (fields.disclaimer) lines.push(fields.disclaimer);
  return lines;
}

function captionOf(pack: Pack): string {
  const tags = (pack.hashtags ?? []).map((tag) => (tag.startsWith("#") ? tag : `#${tag}`));
  const suffix = tags.join(" ");
  if (!suffix || pack.caption.includes(tags[0] ?? "\u0000")) return pack.caption;
  return `${pack.caption.trim()}\n\n${suffix}`;
}

function formatCarousel(slides: Pack["carousel"]): string {
  return slides
    .map((slide, index) => {
      const content = [headlineOf(slide), bodyOf(slide), ...detailLines(slide)].filter(Boolean);
      return `Slide ${index + 1} — ${layoutLabels[layoutOf(slide)]}\n${content.join("\n")}`;
    })
    .join("\n\n");
}

function copyText(label: string, text: string) {
  navigator.clipboard
    .writeText(text)
    .then(() => toast.success(`${label} copiado.`))
    .catch(() => toast.error("Nao consegui copiar automaticamente."));
}

function PacksPage() {
  const scripts = useStore((state) => state.scripts);
  const jobs = useStore((state) => state.videoJobs);
  const posts = useStore((state) => state.calendarPosts);
  const search = Route.useSearch();
  const navigate = useNavigate();
  const [selectedId, setSelectedId] = useState(search.scriptId ?? scripts[0]?.id ?? "");
  const [pack, setPack] = useState<Pack | null>(null);
  const [photoAssets, setPhotoAssets] = useState<PackPhotoAsset[]>([]);
  const [loadingPack, setLoadingPack] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savingPhotoIndex, setSavingPhotoIndex] = useState<number | null>(null);
  const [outdatedAvatar, setOutdatedAvatar] = useState(false);

  const script = scripts.find((item) => item.id === selectedId);
  const videoJob = script ? jobs.find((job) => job.scriptId === script.id) : undefined;
  const scheduledPost = script ? posts.find((post) => post.scriptId === script.id) : undefined;

  useEffect(() => {
    if (!script) {
      setPack(null);
      setOutdatedAvatar(false);
      return;
    }
    let cancelled = false;
    setLoadingPack(true);
    fetchPack(script.id)
      .then((data) => {
        if (!cancelled) {
          setPack(data.pack);
          setOutdatedAvatar(data.outdatedIdentity ?? data.outdatedAvatar);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setPack(null);
          toast.error(error instanceof Error ? error.message : "Nao foi possivel carregar o Pack.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingPack(false);
      });
    return () => {
      cancelled = true;
    };
  }, [script]);

  useEffect(() => {
    let cancelled = false;
    fetchPackPhotoAssets()
      .then((assets) => {
        if (!cancelled) setPhotoAssets(assets);
      })
      .catch(() => {
        if (!cancelled) setPhotoAssets([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function selectScript(scriptId: string) {
    setSelectedId(scriptId);
    navigate({ to: "/packs", search: { scriptId }, replace: true });
  }

  async function generateVisualPack() {
    if (!script) return;
    setGenerating(true);
    const notice = toast.loading("Criando carrossel com texto direto e design editorial...");
    try {
      const response = await generatePack(script);
      setPack(response.pack);
      setOutdatedAvatar(false);
      toast.success("Carrossel de 7 slides criado.", { id: notice });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Nao foi possivel gerar o Pack.", {
        id: notice,
      });
    } finally {
      setGenerating(false);
    }
  }

  async function refreshIdentity() {
    if (!script || !pack) return;
    setGenerating(true);
    const notice = toast.loading("Atualizando a identidade visual sem regenerar a copy...");
    try {
      const response = await refreshPackAvatar(script.id);
      setPack(response.pack);
      setOutdatedAvatar(false);
      toast.success("Identidade do Pack atualizada sem nova chamada ao Claude.", { id: notice });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Nao foi possivel atualizar a identidade.", { id: notice });
    } finally {
      setGenerating(false);
    }
  }

  async function saveLocal() {
    if (!script || !pack) return;
    setSaving(true);
    const notice = toast.loading("Renderizando os slides em alta resolucao...");
    try {
      const response = await exportPack(script, pack);
      toast.success(`Pack salvo em ${response.relative} (${response.files} arquivos).`, {
        id: notice,
        duration: 8000,
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Falha ao salvar o Pack.", {
        id: notice,
      });
    } finally {
      setSaving(false);
    }
  }

  async function choosePhoto(slideIndex: number, photoAssetId: string) {
    if (!script || !pack || photoIdOf(pack.carousel[slideIndex]) === photoAssetId) return;
    const previousPack = pack;
    const selectedAsset = photoAssets.find((asset) => asset.id === photoAssetId);
    if (!selectedAsset) return;
    setSavingPhotoIndex(slideIndex);
    setPack({
      ...pack,
      carousel: pack.carousel.map((slide, index) =>
        index === slideIndex
          ? {
              ...slide,
              fields: slide.fields ? { ...slide.fields, photoId: photoAssetId } : slide.fields,
              photoAsset: {
                id: selectedAsset.id,
                name: selectedAsset.name,
                description: selectedAsset.description,
                cachedAssetPath: selectedAsset.cachedAssetPath,
                facePointX: selectedAsset.facePointX,
                facePointY: selectedAsset.facePointY,
                brightness: selectedAsset.brightness,
              },
            }
          : slide,
      ),
    });
    try {
      const response = await updatePackCarouselPhoto(script.id, slideIndex, photoAssetId);
      setPack(response.pack);
      toast.success(`Foto do slide ${slideIndex + 1} atualizada.`);
    } catch (error) {
      setPack(previousPack);
      toast.error(error instanceof Error ? error.message : "Nao foi possivel atualizar a foto.");
    } finally {
      setSavingPhotoIndex(null);
    }
  }

  return (
    <AppShell
      title="Pack de conteudo"
      actions={
        <>
          <Button size="sm" onClick={generateVisualPack} disabled={!script || generating}>
            {generating ? (
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Wand2 className="mr-1 h-3.5 w-3.5" />
            )}
            {pack ? "Gerar nova versao" : "Gerar Pack"}
          </Button>
          {outdatedAvatar && pack ? (
            <Button size="sm" variant="outline" onClick={() => void refreshIdentity()} disabled={generating}>
              <RefreshCw className="mr-1 h-3.5 w-3.5" /> Atualizar identidade sem Claude
            </Button>
          ) : null}
          <Button
            size="sm"
            variant="secondary"
            onClick={saveLocal}
            disabled={!script || !pack || saving}
          >
            {saving ? (
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
            ) : (
              <FolderDown className="mr-1 h-3.5 w-3.5" />
            )}
            Salvar PNGs
          </Button>
          <Button asChild size="sm" variant="ghost">
            <Link to="/roteiros">
              <FileText className="mr-1 h-3.5 w-3.5" /> Roteiros
            </Link>
          </Button>
        </>
      }
    >
      {scripts.length === 0 ? (
        <EmptyState
          icon={<PanelsTopLeft className="h-4 w-4" />}
          title="Nenhum roteiro para transformar"
          description="Crie um roteiro para gerar o carrossel editorial de 7 slides."
          action={
            <Button asChild size="sm" variant="secondary">
              <Link to="/ideias">Ir para Ideias</Link>
            </Button>
          }
        />
      ) : (
        <div className="space-y-4">
          <section className="rounded-xl border bg-card p-4 shadow-sm">
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
              <div className="min-w-0">
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <StatusBadge
                    label={pack ? "Carrossel pronto" : "Aguardando geracao"}
                    tone="info"
                  />
                  {script ? <StatusBadge {...riskLabel[script.risco]} /> : null}
                  {script ? <StatusBadge {...prioridadeLabel[script.prioridade]} /> : null}
                  {pack?.schemaVersion ? (
                    <StatusBadge label="Sistema Instituto" tone="success" />
                  ) : null}
                </div>
                <h2 className="font-display text-xl font-semibold tracking-tight">
                  {script?.titulo ?? "Selecione um roteiro"}
                </h2>
                <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
                  Seis slides com uma ideia por tela, leitura em poucos segundos e composicao visual
                  fixa.
                </p>
              </div>
              <Select value={selectedId} onValueChange={selectScript}>
                <SelectTrigger>
                  <SelectValue placeholder="Escolher roteiro" />
                </SelectTrigger>
                <SelectContent>
                  {scripts.map((item) => (
                    <SelectItem key={item.id} value={item.id}>
                      {item.titulo}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </section>

          {script && !pack ? (
            <EmptyState
              icon={
                loadingPack ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <PanelsTopLeft className="h-4 w-4" />
                )
              }
              title={loadingPack ? "Carregando Pack" : "Nenhum carrossel gerado"}
              description={
                loadingPack
                  ? "Buscando a versao salva deste roteiro."
                  : "Gere 7 slides com copy curta, contexto explicado e identidade visual consistente."
              }
              action={
                <Button size="sm" onClick={generateVisualPack} disabled={generating || loadingPack}>
                  {generating ? (
                    <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Wand2 className="mr-1 h-3.5 w-3.5" />
                  )}
                  Gerar Pack
                </Button>
              }
            />
          ) : null}

          {script && pack ? (
            <>
              <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center gap-2 text-sm">
                      <Video className="h-4 w-4 text-status-info" /> Video
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="text-sm text-muted-foreground">
                    {videoJob ? `Status: ${videoJob.status}` : "Ainda nao enviado ao HeyGen"}
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center gap-2 text-sm">
                      <Layers3 className="h-4 w-4 text-status-info" /> Carrossel
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="text-sm text-muted-foreground">
                    {pack.carousel.length} slides editoriais
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center gap-2 text-sm">
                      <ImageIcon className="h-4 w-4 text-status-info" /> Qualidade
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="text-sm text-muted-foreground">
                    PNG 1080 × 1350
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center gap-2 text-sm">
                      <CalendarPlus className="h-4 w-4 text-status-info" /> Calendario
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="text-sm text-muted-foreground">
                    {scheduledPost ? "Ja agendado" : "Pronto para agendar"}
                  </CardContent>
                </Card>
              </section>

              <Tabs defaultValue="carousel" className="space-y-3">
                <TabsList className="grid w-full grid-cols-3 md:w-auto">
                  <TabsTrigger value="carousel">Carrossel</TabsTrigger>
                  <TabsTrigger value="caption">Legenda</TabsTrigger>
                  <TabsTrigger value="briefing">Briefing</TabsTrigger>
                </TabsList>

                <TabsContent value="carousel">
                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                    {pack.carousel.map((slide, index) => {
                      const layout = layoutOf(slide);
                      const hasPhoto = photoLayouts.has(layout);
                      const details = detailLines(slide);
                      const selectedPhoto = photoAssets.find(
                        (asset) => asset.id === photoIdOf(slide),
                      );
                      return (
                        <div
                          key={`${layout}-${headlineOf(slide)}-${index}`}
                          className="flex min-h-[260px] flex-col rounded-lg border bg-card p-4 shadow-sm"
                        >
                          <div className="mb-3 flex items-center justify-between gap-2">
                            <span className="text-xs font-semibold uppercase text-muted-foreground">
                              Slide {index + 1}
                            </span>
                            <span className="rounded-md bg-muted px-2 py-1 text-[11px] font-medium text-muted-foreground">
                              {layoutLabels[layout]}
                            </span>
                          </div>

                          {hasPhoto ? (
                            <div className="mb-4 flex items-center gap-2">
                              <Select
                                value={photoIdOf(slide)}
                                onValueChange={(value) => choosePhoto(index, value)}
                                disabled={savingPhotoIndex === index || photoAssets.length === 0}
                              >
                                <SelectTrigger
                                  className="h-9 min-w-0 flex-1 text-xs"
                                  aria-label={`Foto do slide ${index + 1}`}
                                >
                                  <SelectValue placeholder="Foto do acervo" />
                                </SelectTrigger>
                                <SelectContent>
                                  {photoAssets.map((asset) => (
                                    <SelectItem key={asset.id} value={asset.id}>
                                      {asset.name}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                              {selectedPhoto?.url ? (
                                <img
                                  src={selectedPhoto.url}
                                  alt={selectedPhoto.name}
                                  className="h-9 w-9 rounded object-cover"
                                />
                              ) : null}
                              {savingPhotoIndex === index ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                              ) : null}
                            </div>
                          ) : null}

                          {slide.fields?.eyebrow ? (
                            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-status-info">
                              {slide.fields.eyebrow}
                            </p>
                          ) : null}
                          <h3 className="font-display text-lg font-semibold leading-tight">
                            {headlineOf(slide)}
                          </h3>
                          {bodyOf(slide) ? (
                            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                              {bodyOf(slide)}
                            </p>
                          ) : null}
                          {details.length ? (
                            <div className="mt-4 space-y-2 border-t pt-3">
                              {details.map((detail, detailIndex) => (
                                <p
                                  key={`${detail}-${detailIndex}`}
                                  className="text-xs leading-relaxed"
                                >
                                  {detail}
                                </p>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                  <div className="mt-3">
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => copyText("Carrossel", formatCarousel(pack.carousel))}
                    >
                      <Copy className="mr-1 h-3.5 w-3.5" /> Copiar carrossel
                    </Button>
                  </div>
                </TabsContent>

                <TabsContent value="caption">
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-sm">
                        <MessageSquareText className="h-4 w-4" /> Legenda pronta
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <Textarea readOnly className="min-h-[280px]" value={captionOf(pack)} />
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => copyText("Legenda", captionOf(pack))}
                      >
                        <Copy className="mr-1 h-3.5 w-3.5" /> Copiar legenda
                      </Button>
                    </CardContent>
                  </Card>
                </TabsContent>

                <TabsContent value="briefing">
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-sm">Controle de qualidade do pacote</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="mb-4 grid gap-2 text-sm md:grid-cols-3">
                        <div className="rounded-lg border bg-background p-3">
                          <div className="text-xs text-muted-foreground">Sistema visual</div>
                          <div className="mt-1 font-medium">Instituto Guilherme Martins</div>
                        </div>
                        <div className="rounded-lg border bg-background p-3">
                          <div className="text-xs text-muted-foreground">Resolucao de saida</div>
                          <div className="mt-1 font-medium">1080 × 1350 px</div>
                        </div>
                        <div className="rounded-lg border bg-background p-3">
                          <div className="text-xs text-muted-foreground">Layouts usados</div>
                          <div className="mt-1 font-medium">
                            {new Set(pack.carousel.map(layoutOf)).size} de {pack.carousel.length}
                          </div>
                        </div>
                      </div>
                      <div className="grid gap-2 md:grid-cols-2">
                        {(pack.checklist.length
                          ? pack.checklist
                          : [
                              "7 slides em sequencia narrativa",
                              "1 slide explicativo com contexto da IA",
                              "Uma ideia principal por tela",
                              "No maximo 3 slides com foto",
                              "Texto curto e sem jargao",
                              "Capa forte e CTA no slide final",
                              "Legenda pronta para publicar",
                            ]
                        ).map((item) => (
                          <div key={item} className="flex items-start gap-2 text-sm">
                            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-status-success" />
                            <span>{item}</span>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                </TabsContent>
              </Tabs>
            </>
          ) : null}
        </div>
      )}
    </AppShell>
  );
}
