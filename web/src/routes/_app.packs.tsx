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
import { formatPublicationCaption } from "@/lib/medical-identity";
import { prioridadeLabel, riskLabel } from "@/lib/status";
import { useStore } from "@/lib/store";
import {
  exportPack,
  fetchPack,
  fetchPackPhotoAssets,
  generatePack,
  refreshPackAvatar,
  updatePackCoverNote,
  updatePackCarouselPhoto,
  updatePackPresentation,
  type GeneratedPack,
  type PackFamily,
  type PackLayout,
  type PackPhotoAsset,
  type PackSlide,
  type PackTheme,
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
  Palette,
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
        content: "Sete slides, legenda pronta e identidade visual consistente.",
      },
    ],
  }),
  component: PacksPage,
});

type Pack = GeneratedPack;

const REQUIRED_CAROUSEL_SLIDES = 7;

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

const familyOptions: Array<{
  id: PackFamily;
  label: string;
  description: string;
  whenToUse: string;
}> = [
  {
    id: "editorial",
    label: "Editorial",
    description: "Foto ampla, autoridade e mais respiro.",
    whenToUse: "Opinião médica e posicionamento.",
  },
  {
    id: "didatico",
    label: "Didático",
    description: "Grade clara, relações e passos numerados.",
    whenToUse: "Explicações e conteúdo científico.",
  },
  {
    id: "storytelling",
    label: "Storytelling",
    description: "Foto presente, texto curto e ritmo narrativo.",
    whenToUse: "Histórias, tensão e transformação.",
  },
];

const themeOptions: Array<{
  id: PackTheme;
  label: string;
  description: string;
  swatches: [string, string, string];
}> = [
  {
    id: "modernist-red",
    label: "Modernist",
    description: "Vermelho, contraste gráfico e tipografia Archivo.",
    swatches: ["#c8392b", "#171717", "#f4efe6"],
  },
  {
    id: "ocean-deep",
    label: "Ocean Deep",
    description: "Azul profundo, teal e linguagem clínica.",
    swatches: ["#0c2340", "#2d8a9e", "#f2f5f6"],
  },
];

function familyOf(pack: Pack): PackFamily {
  return pack.family ?? "didatico";
}

function themeOf(pack: Pack): PackTheme {
  return pack.themeId ?? "ocean-deep";
}

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
  if (fields.coverNote) lines.push(`Mensagem na capa: ${fields.coverNote}`);
  if (fields.cta) lines.push(fields.cta);
  if (fields.disclaimer) lines.push(fields.disclaimer);
  if (layoutOf(slide) === "cta_photo" && fields.footer) lines.push(fields.footer);
  return lines;
}

function captionOf(pack: Pack): string {
  return formatPublicationCaption(pack.caption, pack.hashtags ?? []);
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
  const [coverNoteDraft, setCoverNoteDraft] = useState("");
  const [savingCoverNote, setSavingCoverNote] = useState(false);
  const [savingPresentation, setSavingPresentation] = useState(false);
  const [presentationStatus, setPresentationStatus] = useState("");
  const [outdatedAvatar, setOutdatedAvatar] = useState(false);
  const [outdatedPackSchema, setOutdatedPackSchema] = useState(false);

  const script = scripts.find((item) => item.id === selectedId);
  const videoJob = script ? jobs.find((job) => job.scriptId === script.id) : undefined;
  const scheduledPost = script ? posts.find((post) => post.scriptId === script.id) : undefined;
  const packIsLegacy =
    pack !== null && (pack.carousel.length !== REQUIRED_CAROUSEL_SLIDES || outdatedPackSchema);
  const savedCoverNote = pack?.carousel[0]?.fields?.coverNote ?? "";
  const coverNoteDirty = coverNoteDraft.trim().replace(/\s+/g, " ") !== savedCoverNote;

  useEffect(() => {
    setCoverNoteDraft(savedCoverNote);
  }, [savedCoverNote]);

  useEffect(() => {
    if (!script) {
      setPack(null);
      setOutdatedAvatar(false);
      setOutdatedPackSchema(false);
      return;
    }
    let cancelled = false;
    setLoadingPack(true);
    fetchPack(script.id)
      .then((data) => {
        if (!cancelled) {
          setPack(data.pack);
          setOutdatedAvatar(
            Boolean((data.outdatedIdentity ?? data.outdatedAvatar) && !data.outdatedPackSchema),
          );
          setOutdatedPackSchema(data.outdatedPackSchema ?? false);
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
      const response = await generatePack(
        script,
        pack ? { family: familyOf(pack), themeId: themeOf(pack) } : undefined,
      );
      setPack(response.pack);
      setOutdatedAvatar(false);
      setOutdatedPackSchema(false);
      toast.success("Carrossel de 7 slides criado.", { id: notice });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Nao foi possivel gerar o Pack.", {
        id: notice,
      });
    } finally {
      setGenerating(false);
    }
  }

  async function choosePresentation(next: { family: PackFamily; themeId: PackTheme }) {
    if (!script || !pack || savingPresentation) return;
    if (familyOf(pack) === next.family && themeOf(pack) === next.themeId) return;

    const previousPack = pack;
    setSavingPresentation(true);
    setPresentationStatus("Salvando preferência visual…");
    setPack({ ...pack, ...next });
    try {
      const response = await updatePackPresentation(script.id, next);
      setPack(response.pack);
      setPresentationStatus("Estilo salvo sem usar tokens do Claude.");
      toast.success("Estilo do Pack atualizado sem regenerar o texto.");
    } catch (error) {
      setPack(previousPack);
      setPresentationStatus("");
      toast.error(error instanceof Error ? error.message : "Nao foi possivel salvar o estilo.");
    } finally {
      setSavingPresentation(false);
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
      setOutdatedPackSchema(false);
      toast.success("Identidade do Pack atualizada sem nova chamada ao Claude.", { id: notice });
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Nao foi possivel atualizar a identidade.",
        { id: notice },
      );
    } finally {
      setGenerating(false);
    }
  }

  async function saveLocal() {
    if (!script || !pack) return;
    if (packIsLegacy) {
      toast.error(
        "Salvar PNGs esta bloqueado porque este Pack ainda tem 6 slides. Gere a versao com 7 slides primeiro.",
      );
      return;
    }
    setSaving(true);
    const notice = toast.loading("Renderizando os slides em alta resolucao...");
    try {
      const response = await exportPack(script, pack);
      toast.success(`Pack salvo em ${response.relative} (${response.images} PNGs).`, {
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
    if (
      !script ||
      !pack ||
      savingPhotoIndex !== null ||
      photoIdOf(pack.carousel[slideIndex]) === photoAssetId
    )
      return;
    const previousPack = pack;
    const selectedAsset = photoAssets.find((asset) => asset.id === photoAssetId);
    if (!selectedAsset) return;
    setSavingPhotoIndex(slideIndex);
    const notice = toast.loading(`Atualizando a foto do slide ${slideIndex + 1}...`);
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
      try {
        const exported = await exportPack(script, response.pack);
        toast.success(
          `Foto do slide ${slideIndex + 1} atualizada e ${exported.images} PNGs regenerados.`,
          { id: notice },
        );
      } catch (error) {
        toast.error(
          `A foto foi salva, mas os PNGs não foram regenerados: ${
            error instanceof Error ? error.message : "erro na exportação"
          }`,
          { id: notice, duration: 9000 },
        );
      }
    } catch (error) {
      setPack(previousPack);
      toast.error(error instanceof Error ? error.message : "Nao foi possivel atualizar a foto.", {
        id: notice,
      });
    } finally {
      setSavingPhotoIndex(null);
    }
  }

  async function saveCoverNote() {
    if (!script || !pack || savingCoverNote || !coverNoteDirty) return;
    setSavingCoverNote(true);
    const notice = toast.loading("Salvando a mensagem da capa...");
    try {
      const response = await updatePackCoverNote(script.id, coverNoteDraft);
      const saved = response.pack.carousel[0]?.fields?.coverNote ?? "";
      setPack(response.pack);
      setCoverNoteDraft(saved);
      toast.success(
        saved
          ? "Mensagem da capa salva. A fonte se ajusta automaticamente no PNG."
          : "Caixa de texto removida da capa.",
        { id: notice },
      );
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Nao foi possivel salvar a mensagem da capa.",
        { id: notice },
      );
    } finally {
      setSavingCoverNote(false);
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
            {packIsLegacy ? "Gerar 7 slides agora" : pack ? "Gerar nova versao" : "Gerar Pack"}
          </Button>
          {outdatedAvatar && pack ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => void refreshIdentity()}
              disabled={generating}
            >
              <RefreshCw className="mr-1 h-3.5 w-3.5" /> Atualizar identidade sem Claude
            </Button>
          ) : null}
          <Button
            size="sm"
            variant="secondary"
            onClick={saveLocal}
            disabled={!script || !pack || saving || packIsLegacy}
          >
            {saving ? (
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
            ) : (
              <FolderDown className="mr-1 h-3.5 w-3.5" />
            )}
            {packIsLegacy ? "Salvar PNGs bloqueado" : "Salvar PNGs"}
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
                    label={
                      packIsLegacy
                        ? "Versao antiga"
                        : pack
                          ? "Carrossel pronto"
                          : "Aguardando geracao"
                    }
                    tone={packIsLegacy ? "warn" : "info"}
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
                  {packIsLegacy
                    ? `Este Pack salvo ainda tem ${pack.carousel.length} slides. Gere a versao nova para adicionar o slide de contexto e liberar os PNGs.`
                    : "7 slides com uma ideia por tela, leitura em poucos segundos e composicao visual fixa."}
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
              {packIsLegacy ? (
                <section className="flex flex-col gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 shadow-sm md:flex-row md:items-center md:justify-between">
                  <div>
                    <div className="font-semibold">
                      Ainda nao existe a versao de 7 slides deste Pack.
                    </div>
                    <p className="mt-1">
                      O arquivo salvo tem {pack.carousel.length} de {REQUIRED_CAROUSEL_SLIDES}{" "}
                      slides. Por isso o app bloqueia “Salvar PNGs” até gerar a nova versão com o
                      slide de contexto.
                    </p>
                  </div>
                  <Button size="sm" onClick={generateVisualPack} disabled={generating}>
                    {generating ? (
                      <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Wand2 className="mr-1 h-3.5 w-3.5" />
                    )}
                    Gerar 7 slides agora
                  </Button>
                </section>
              ) : null}
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
                    {packIsLegacy
                      ? `${pack.carousel.length} de ${REQUIRED_CAROUSEL_SLIDES} slides — gere nova versao`
                      : `${pack.carousel.length} slides editoriais`}
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

              <section className="rounded-xl border bg-card p-4 shadow-sm">
                <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <h2 className="flex items-center gap-2 text-sm font-semibold">
                      <Palette className="h-4 w-4 text-status-info" /> Estilo do Pack
                    </h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Escolha a composição e o tema visual. A troca é local e preserva o texto.
                    </p>
                  </div>
                  <StatusBadge label="Sem tokens do Claude" tone="success" />
                </div>

                <div className="grid gap-5 xl:grid-cols-[minmax(0,1.55fr)_minmax(300px,1fr)]">
                  <fieldset>
                    <legend className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                      Composição
                    </legend>
                    <div className="grid gap-2 md:grid-cols-3">
                      {familyOptions.map((option) => {
                        const selected = familyOf(pack) === option.id;
                        return (
                          <label
                            key={option.id}
                            className={`cursor-pointer rounded-lg border p-3 transition-colors duration-200 focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2 ${
                              selected
                                ? "border-primary bg-primary/5"
                                : "bg-background hover:border-primary/40 hover:bg-muted/40"
                            } ${savingPresentation ? "cursor-wait opacity-70" : ""}`}
                          >
                            <input
                              className="sr-only"
                              type="radio"
                              name="pack-family"
                              value={option.id}
                              checked={selected}
                              disabled={savingPresentation}
                              onChange={() =>
                                void choosePresentation({
                                  family: option.id,
                                  themeId: themeOf(pack),
                                })
                              }
                            />
                            <span className="flex items-center justify-between gap-2">
                              <span className="text-sm font-semibold">{option.label}</span>
                              {selected ? (
                                <CheckCircle2 className="h-4 w-4 shrink-0 text-status-success" />
                              ) : null}
                            </span>
                            <span className="mt-1 block text-xs leading-relaxed text-muted-foreground">
                              {option.description}
                            </span>
                            <span className="mt-2 block text-[11px] font-medium text-foreground/75">
                              {option.whenToUse}
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  </fieldset>

                  <fieldset>
                    <legend className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                      Tema
                    </legend>
                    <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
                      {themeOptions.map((option) => {
                        const selected = themeOf(pack) === option.id;
                        return (
                          <label
                            key={option.id}
                            className={`cursor-pointer rounded-lg border p-3 transition-colors duration-200 focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2 ${
                              selected
                                ? "border-primary bg-primary/5"
                                : "bg-background hover:border-primary/40 hover:bg-muted/40"
                            } ${savingPresentation ? "cursor-wait opacity-70" : ""}`}
                          >
                            <input
                              className="sr-only"
                              type="radio"
                              name="pack-theme"
                              value={option.id}
                              checked={selected}
                              disabled={savingPresentation}
                              onChange={() =>
                                void choosePresentation({
                                  family: familyOf(pack),
                                  themeId: option.id,
                                })
                              }
                            />
                            <span className="flex items-center gap-3">
                              <span
                                className="flex shrink-0 overflow-hidden rounded border"
                                aria-hidden="true"
                              >
                                {option.swatches.map((color) => (
                                  <span
                                    key={color}
                                    className="h-8 w-4"
                                    style={{ backgroundColor: color }}
                                  />
                                ))}
                              </span>
                              <span className="min-w-0 flex-1">
                                <span className="flex items-center justify-between gap-2 text-sm font-semibold">
                                  {option.label}
                                  {selected ? (
                                    <CheckCircle2 className="h-4 w-4 shrink-0 text-status-success" />
                                  ) : null}
                                </span>
                                <span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground">
                                  {option.description}
                                </span>
                              </span>
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  </fieldset>
                </div>

                <p className="mt-3 min-h-4 text-xs text-muted-foreground" aria-live="polite">
                  {presentationStatus}
                </p>
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
                                disabled={savingPhotoIndex !== null || photoAssets.length === 0}
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

                          {index === 0 ? (
                            <div className="mb-4 rounded-lg border border-dashed border-primary/35 bg-primary/5 p-3">
                              <label
                                htmlFor="pack-cover-note"
                                className="text-xs font-semibold text-foreground"
                              >
                                Mensagem opcional na capa
                              </label>
                              <p
                                id="pack-cover-note-help"
                                className="mt-1 text-[11px] leading-relaxed text-muted-foreground"
                              >
                                Ela aparece em uma caixa no Slide 1. A fonte diminui automaticamente
                                para caber no PNG.
                              </p>
                              <Textarea
                                id="pack-cover-note"
                                className="mt-2 min-h-20 resize-y text-sm"
                                rows={3}
                                maxLength={180}
                                value={coverNoteDraft}
                                onChange={(event) => setCoverNoteDraft(event.target.value)}
                                placeholder="Ex.: Atendimento individual, com escuta e estratégia."
                                aria-describedby="pack-cover-note-help pack-cover-note-count"
                              />
                              <div className="mt-2 flex items-center justify-between gap-2">
                                <span
                                  id="pack-cover-note-count"
                                  className="text-[11px] tabular-nums text-muted-foreground"
                                >
                                  {coverNoteDraft.length}/180
                                </span>
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="secondary"
                                  onClick={() => void saveCoverNote()}
                                  disabled={!coverNoteDirty || savingCoverNote}
                                >
                                  {savingCoverNote ? (
                                    <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                                  ) : null}
                                  {savingCoverNote ? "Salvando..." : "Salvar mensagem"}
                                </Button>
                              </div>
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
