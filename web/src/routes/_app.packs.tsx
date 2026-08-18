import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { AppShell } from "@/components/app-shell";
import { ConfirmAction } from "@/components/confirm-action";
import { EmptyState } from "@/components/empty-state";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { formatPublicationCaption } from "@/lib/medical-identity";
import { prioridadeLabel, riskLabel } from "@/lib/status";
import { useStore } from "@/lib/store";
import {
  exportPack,
  fetchPack,
  fetchPackDesignSystem,
  fetchPackPhotoAssets,
  fetchPackVersions,
  generatePack,
  packSlidePreviewUrl,
  packSlideThumbnailUrl,
  refreshPackAvatar,
  regeneratePackSlide,
  restorePackVersion,
  updatePackCarouselLayout,
  updatePackCarouselPhoto,
  updatePackPresentation,
  updatePackSlideFields,
  type GeneratedPack,
  type PackClarity,
  type PackDesignSystem,
  type PackFamily,
  type PackLayout,
  type PackLayoutSpec,
  type PackPhotoAsset,
  type PackSlide,
  type PackSlideFields,
  type PackSlideItem,
  type PackTheme,
  type PackVersion,
} from "@/lib/api/local";
import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  FileText,
  FolderDown,
  History,
  Image as ImageIcon,
  Loader2,
  MessageSquareText,
  Palette,
  PanelsTopLeft,
  RefreshCw,
  RotateCcw,
  Sparkles,
  Wand2,
} from "lucide-react";

export const Route = createFileRoute("/_app/packs")({
  validateSearch: (search: Record<string, unknown>) => ({
    scriptId: typeof search.scriptId === "string" ? search.scriptId : undefined,
  }),
  head: () => ({
    meta: [
      { title: "Estúdio de Pack | AI Video Creator" },
      {
        name: "description",
        content:
          "Carrossel educativo de 7 slides com preview real, edição por slide e exportação em 1080 × 1350.",
      },
      { property: "og:title", content: "Estúdio de Pack | AI Video Creator" },
      {
        property: "og:description",
        content: "Veja o slide exatamente como ele vai ser publicado antes de exportar.",
      },
    ],
  }),
  component: PacksPage,
});

type Pack = GeneratedPack;

const REQUIRED_CAROUSEL_SLIDES = 7;
const NO_PHOTO_VALUE = "__no_photo__";

/** Etapas da trilha educativa. Espelham EDUCATIONAL_SLIDE_STEPS no backend. */
const educationalSteps = [
  { title: "Tema e objetivo", description: "Apresenta o assunto e o que será explicado." },
  { title: "Contexto", description: "Organiza a dúvida de forma neutra." },
  { title: "Conceito-chave", description: "Define o ponto central em linguagem simples." },
  { title: "Como funciona", description: "Conecta a explicação em etapas curtas." },
  { title: "O que a fonte mostra", description: "Traduz o dado ou a evidência com contexto." },
  { title: "Cuidados e limites", description: "Mostra a ressalva necessária com clareza." },
  { title: "Resumo e próximo passo", description: "Retoma o aprendizado e orienta com segurança." },
] as const;

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
  {
    id: "manifesto",
    label: "Manifesto",
    description: "Blocos gráficos, alto contraste e fotos monocromáticas.",
    whenToUse: "Alertas, posicionamento e quebra de mitos.",
  },
  {
    id: "clinico",
    label: "Clínico",
    description: "Grade técnica, painéis leves e leitura precisa.",
    whenToUse: "Dados, evidências e orientações em saúde.",
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
    id: "modernist-teal",
    label: "Editorial Teal",
    description: "Navy, teal e estrutura modernista sem cantos arredondados.",
    swatches: ["#17a697", "#0b2135", "#f3f1ec"],
  },
  {
    id: "ocean-deep",
    label: "Ocean Deep",
    description: "Azul profundo, teal e linguagem clínica.",
    swatches: ["#0c2340", "#2d8a9e", "#f2f5f6"],
  },
  {
    id: "soft-sage",
    label: "Sálvia Suave",
    description: "Verde sálvia, creme e contraste sereno.",
    swatches: ["#86a996", "#28443e", "#f3f4ee"],
  },
  {
    id: "soft-rose",
    label: "Rosé Suave",
    description: "Rosé empoeirado, nude e acabamento acolhedor.",
    swatches: ["#c78b93", "#513944", "#fbf5f2"],
  },
];

const versionOriginLabels: Record<string, string> = {
  "geracao-completa": "Antes de gerar nova versão",
  "regeneracao-do-slide": "Antes de reescrever um slide",
  "edicao-manual": "Antes da primeira edição manual",
  "antes-da-restauracao": "Antes de restaurar",
};

const densityTone: Record<string, { label: string; className: string; dot: string }> = {
  vazio: {
    label: "Pouco texto",
    className: "text-status-warn",
    dot: "bg-status-warn",
  },
  equilibrado: {
    label: "Equilibrado",
    className: "text-status-success",
    dot: "bg-status-success",
  },
  denso: {
    label: "Texto denso",
    className: "text-status-warn",
    dot: "bg-status-warn",
  },
};

/** Campos longos ganham textarea; o resto usa input de uma linha. */
const longFields = new Set<string>(["body", "coverNote", "quote", "disclaimer", "caption"]);

function familyOf(pack: Pack): PackFamily {
  return pack.family ?? "didatico";
}

function themeOf(pack: Pack): PackTheme {
  return pack.themeId ?? "ocean-deep";
}

function grayscalePhotosOf(pack: Pack): boolean {
  return pack.grayscalePhotos !== false;
}

function layoutOf(slide: PackSlide): PackLayout {
  return slide.layoutId ?? slide.layout ?? "explainer";
}

function fieldsOf(slide: PackSlide): PackSlideFields | undefined {
  return slide.fields;
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

function isItemField(name: string): boolean {
  return name === "item1" || name === "item2" || name === "item3";
}

function itemValue(fields: PackSlideFields | undefined, name: string): PackSlideItem {
  const raw = fields ? (fields as unknown as Record<string, unknown>)[name] : undefined;
  if (raw && typeof raw === "object") {
    const item = raw as Partial<PackSlideItem>;
    return { title: item.title ?? "", text: item.text ?? "" };
  }
  return { title: "", text: "" };
}

function textValue(fields: PackSlideFields | undefined, name: string): string {
  const raw = fields ? (fields as unknown as Record<string, unknown>)[name] : undefined;
  return typeof raw === "string" ? raw : "";
}

type SlideDraft = Record<string, string | PackSlideItem>;

function draftFromSlide(slide: PackSlide, spec: PackLayoutSpec | undefined): SlideDraft {
  const fields = fieldsOf(slide);
  const draft: SlideDraft = {};
  for (const name of spec?.editableFields ?? []) {
    draft[name] = isItemField(name) ? itemValue(fields, name) : textValue(fields, name);
  }
  return draft;
}

function draftsEqual(a: SlideDraft, b: SlideDraft): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function captionOf(pack: Pack): string {
  return formatPublicationCaption(pack.caption, pack.hashtags ?? []);
}

function detailLines(slide: PackSlide): string[] {
  const fields = slide.fields;
  if (!fields) return [];
  const lines: string[] = [];
  if (fields.statistic) lines.push(fields.statistic);
  for (const item of [fields.item1, fields.item2, fields.item3]) {
    const line = [item?.title, item?.text].filter(Boolean).join(": ");
    if (line) lines.push(line);
  }
  if (fields.quote) lines.push(fields.quote);
  if (fields.cta) lines.push(fields.cta);
  return lines;
}

function formatCarousel(slides: Pack["carousel"], labelOf: (layout: PackLayout) => string): string {
  return slides
    .map((slide, index) => {
      const content = [headlineOf(slide), bodyOf(slide), ...detailLines(slide)].filter(Boolean);
      return `Slide ${index + 1} — ${labelOf(layoutOf(slide))}\n${content.join("\n")}`;
    })
    .join("\n\n");
}

function copyText(label: string, text: string) {
  navigator.clipboard
    .writeText(text)
    .then(() => toast.success(`${label} copiado.`))
    .catch(() => toast.error("Nao consegui copiar automaticamente."));
}

/**
 * Preview do slide.
 *
 * O iframe carrega exatamente o HTML que o renderer transforma em PNG, então o
 * que aparece aqui é o arquivo que será publicado. É local e determinístico:
 * navegar entre slides, trocar tema, família ou foto não consome tokens.
 */
function SlidePreview({
  scriptId,
  slideIndex,
  nonce,
  width,
}: {
  scriptId: string;
  slideIndex: number;
  nonce: number;
  width: number;
}) {
  const scale = width / 1080;
  return (
    <div
      className="overflow-hidden rounded-xl border bg-muted shadow-sm"
      style={{ width, height: Math.round(1350 * scale) }}
    >
      <iframe
        key={`${scriptId}-${slideIndex}-${nonce}`}
        title={`Preview do slide ${slideIndex + 1}`}
        src={`${packSlidePreviewUrl(scriptId, slideIndex)}?v=${nonce}`}
        width={1080}
        height={1350}
        loading="lazy"
        sandbox="allow-scripts"
        className="origin-top-left border-0"
        style={{ transform: `scale(${scale})` }}
      />
    </div>
  );
}

function ClarityChip({ density }: { density: string }) {
  const tone = densityTone[density] ?? densityTone.equilibrado;
  return (
    <span className={`inline-flex items-center gap-1.5 text-[11px] font-medium ${tone.className}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${tone.dot}`} aria-hidden="true" />
      {tone.label}
    </span>
  );
}

function PacksPage() {
  const scripts = useStore((state) => state.scripts);
  const search = Route.useSearch();
  const navigate = useNavigate();

  const [selectedId, setSelectedId] = useState(search.scriptId ?? scripts[0]?.id ?? "");
  const [pack, setPack] = useState<Pack | null>(null);
  const [clarity, setClarity] = useState<PackClarity | null>(null);
  const [versions, setVersions] = useState<PackVersion[]>([]);
  const [designSystem, setDesignSystem] = useState<PackDesignSystem | null>(null);
  const [photoAssets, setPhotoAssets] = useState<PackPhotoAsset[]>([]);

  const [activeSlide, setActiveSlide] = useState(0);
  const [draft, setDraft] = useState<SlideDraft>({});
  const [previewNonce, setPreviewNonce] = useState(0);

  const [loadingPack, setLoadingPack] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [savingSlide, setSavingSlide] = useState(false);
  const [regeneratingSlide, setRegeneratingSlide] = useState(false);
  const [savingLayout, setSavingLayout] = useState(false);
  const [savingPhoto, setSavingPhoto] = useState(false);
  const [savingPresentation, setSavingPresentation] = useState(false);
  const [restoringVersion, setRestoringVersion] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);
  const [regenerateNote, setRegenerateNote] = useState("");
  const [localStatus, setLocalStatus] = useState("");

  const [outdatedAvatar, setOutdatedAvatar] = useState(false);
  const [outdatedPackSchema, setOutdatedPackSchema] = useState(false);
  const [outdatedEducationalFlow, setOutdatedEducationalFlow] = useState(false);

  const script = scripts.find((item) => item.id === selectedId);
  const packIsLegacy =
    pack !== null && (pack.carousel.length !== REQUIRED_CAROUSEL_SLIDES || outdatedPackSchema);

  const layoutSpecs = useMemo(() => {
    const map = new Map<PackLayout, PackLayoutSpec>();
    for (const layout of designSystem?.layouts ?? []) map.set(layout.id, layout);
    return map;
  }, [designSystem]);

  const labelOf = useCallback(
    (layout: PackLayout) => layoutSpecs.get(layout)?.label ?? layout,
    [layoutSpecs],
  );

  const slide = pack?.carousel[activeSlide];
  const slideLayout = slide ? layoutOf(slide) : undefined;
  const slideSpec = slideLayout ? layoutSpecs.get(slideLayout) : undefined;
  const slideClarity = clarity?.slides.find((entry) => entry.slide === activeSlide + 1);
  const savedDraft = useMemo(
    () => (slide ? draftFromSlide(slide, slideSpec) : {}),
    [slide, slideSpec],
  );
  const dirty = !draftsEqual(draft, savedDraft);

  /** Recebe o resultado de qualquer mutação local e sincroniza a tela. */
  const applyMutation = useCallback((next: { pack: Pack; clarity: PackClarity }) => {
    setPack(next.pack);
    setClarity(next.clarity);
    setPreviewNonce((value) => value + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchPackDesignSystem()
      .then((data) => {
        if (!cancelled) setDesignSystem(data);
      })
      .catch(() => {
        if (!cancelled) setDesignSystem(null);
      });
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

  useEffect(() => {
    if (!script) {
      setPack(null);
      setClarity(null);
      setVersions([]);
      setOutdatedAvatar(false);
      setOutdatedPackSchema(false);
      setOutdatedEducationalFlow(false);
      return;
    }
    let cancelled = false;
    setLoadingPack(true);
    setActiveSlide(0);
    fetchPack(script.id)
      .then((data) => {
        if (cancelled) return;
        setPack(data.pack);
        setClarity(data.clarity);
        setVersions(data.versions);
        setPreviewNonce((value) => value + 1);
        setOutdatedAvatar(
          Boolean((data.outdatedIdentity ?? data.outdatedAvatar) && !data.outdatedPackSchema),
        );
        setOutdatedPackSchema(data.outdatedPackSchema ?? false);
        setOutdatedEducationalFlow(data.outdatedEducationalFlow ?? false);
      })
      .catch((error) => {
        if (cancelled) return;
        setPack(null);
        toast.error(error instanceof Error ? error.message : "Nao foi possivel carregar o Pack.");
      })
      .finally(() => {
        if (!cancelled) setLoadingPack(false);
      });
    return () => {
      cancelled = true;
    };
  }, [script]);

  // O rascunho acompanha o slide selecionado e o conteúdo salvo. Trocar de
  // slide, de tema ou de foto nunca descarta texto: o rascunho é reconstruído
  // a partir do que está persistido.
  useEffect(() => {
    setDraft(savedDraft);
  }, [savedDraft]);

  const refreshVersions = useCallback(() => {
    if (!script) return;
    fetchPackVersions(script.id)
      .then(setVersions)
      .catch(() => undefined);
  }, [script]);

  function selectScript(scriptId: string) {
    setSelectedId(scriptId);
    navigate({ to: "/packs", search: { scriptId }, replace: true });
  }

  async function generateVisualPack() {
    if (!script) return;
    setGenerating(true);
    const notice = toast.loading("Criando os 7 slides com o Claude...");
    try {
      const response = await generatePack(
        script,
        pack
          ? {
              family: familyOf(pack),
              themeId: themeOf(pack),
              grayscalePhotos: grayscalePhotosOf(pack),
            }
          : undefined,
      );
      setPack(response.pack);
      setClarity(response.clarity);
      setPreviewNonce((value) => value + 1);
      setActiveSlide(0);
      setOutdatedAvatar(false);
      setOutdatedPackSchema(false);
      setOutdatedEducationalFlow(false);
      refreshVersions();
      toast.success("Carrossel educativo de 7 slides criado.", { id: notice });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Nao foi possivel gerar o Pack.", {
        id: notice,
      });
    } finally {
      setGenerating(false);
    }
  }

  async function saveSlideText() {
    if (!script || !pack || !dirty || savingSlide) return;
    setSavingSlide(true);
    try {
      const response = await updatePackSlideFields(
        script.id,
        activeSlide,
        draft as Parameters<typeof updatePackSlideFields>[2],
      );
      applyMutation(response);
      refreshVersions();
      setLocalStatus("Texto salvo. Nenhum token do Claude usado.");
      toast.success(`Slide ${activeSlide + 1} atualizado sem chamar o Claude.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Nao foi possivel salvar o slide.");
    } finally {
      setSavingSlide(false);
    }
  }

  async function regenerateSlide() {
    if (!script || !pack || regeneratingSlide) return;
    setRegeneratingSlide(true);
    const notice = toast.loading(`Reescrevendo apenas o slide ${activeSlide + 1}...`);
    try {
      const response = await regeneratePackSlide(script.id, activeSlide, regenerateNote.trim());
      applyMutation(response);
      refreshVersions();
      setRegenerateNote("");
      setLocalStatus("Slide reescrito. Os outros 6 slides foram preservados.");
      toast.success(`Slide ${activeSlide + 1} reescrito. Os outros slides não mudaram.`, {
        id: notice,
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Nao foi possivel reescrever o slide.", {
        id: notice,
      });
    } finally {
      setRegeneratingSlide(false);
    }
  }

  async function changeLayout(layout: PackLayout) {
    if (!script || !pack || savingLayout || slideLayout === layout) return;
    setSavingLayout(true);
    try {
      const response = await updatePackCarouselLayout(script.id, activeSlide, layout);
      applyMutation(response);
      setLocalStatus("Layout trocado localmente, sem regenerar o texto.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Nao foi possivel trocar o layout.");
    } finally {
      setSavingLayout(false);
    }
  }

  async function choosePhoto(photoAssetId: string | null) {
    if (!script || !pack || savingPhoto || !slide || photoIdOf(slide) === (photoAssetId ?? ""))
      return;
    setSavingPhoto(true);
    try {
      const response = await updatePackCarouselPhoto(script.id, activeSlide, photoAssetId);
      applyMutation(response);
      setLocalStatus(
        photoAssetId
          ? "Foto trocada localmente. Exporte quando quiser gerar os PNGs."
          : "Foto removida. O layout e o texto foram preservados.",
      );
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Nao foi possivel atualizar a foto.");
    } finally {
      setSavingPhoto(false);
    }
  }

  async function choosePresentation(next: {
    family: PackFamily;
    themeId: PackTheme;
    grayscalePhotos: boolean;
  }) {
    if (!script || !pack || savingPresentation) return;
    if (
      familyOf(pack) === next.family &&
      themeOf(pack) === next.themeId &&
      grayscalePhotosOf(pack) === next.grayscalePhotos
    )
      return;
    const previousPack = pack;
    setSavingPresentation(true);
    setPack({ ...pack, ...next });
    try {
      const response = await updatePackPresentation(script.id, next);
      applyMutation(response);
      setLocalStatus("Estilo salvo sem usar tokens do Claude.");
    } catch (error) {
      setPack(previousPack);
      toast.error(error instanceof Error ? error.message : "Nao foi possivel salvar o estilo.");
    } finally {
      setSavingPresentation(false);
    }
  }

  async function restoreVersion(versionId: number) {
    if (!script || restoringVersion !== null) return;
    setRestoringVersion(versionId);
    try {
      const response = await restorePackVersion(script.id, versionId);
      applyMutation(response);
      refreshVersions();
      setLocalStatus("Versão restaurada sem usar tokens do Claude.");
      toast.success("Versão restaurada. Nenhuma chamada ao Claude foi feita.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Nao foi possivel restaurar a versao.");
    } finally {
      setRestoringVersion(null);
    }
  }

  async function refreshIdentity() {
    if (!script || !pack) return;
    setGenerating(true);
    const notice = toast.loading("Atualizando a identidade visual sem regenerar a copy...");
    try {
      const response = await refreshPackAvatar(script.id);
      applyMutation(response);
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
    setExporting(true);
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
      setExporting(false);
    }
  }

  function updateDraftText(name: string, value: string) {
    setDraft((current) => ({ ...current, [name]: value }));
  }

  function updateDraftItem(name: string, part: "title" | "text", value: string) {
    setDraft((current) => {
      const item = current[name];
      const base: PackSlideItem = item && typeof item === "object" ? item : { title: "", text: "" };
      return { ...current, [name]: { ...base, [part]: value } };
    });
  }

  const generateLabel = packIsLegacy
    ? "Gerar 7 slides agora"
    : outdatedEducationalFlow
      ? "Gerar versão educativa"
      : pack
        ? "Gerar nova versão"
        : "Gerar Pack";

  return (
    <AppShell
      title="Estúdio de Pack"
      actions={
        <>
          {pack ? (
            <ConfirmAction
              trigger={
                <Button size="sm" disabled={!script || generating}>
                  {generating ? (
                    <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Wand2 className="mr-1 h-3.5 w-3.5" />
                  )}
                  {generateLabel}
                </Button>
              }
              title="Gerar uma nova versão de conteúdo?"
              description={
                <div className="space-y-2 text-sm">
                  <p>
                    Isso reescreve os <strong>7 slides</strong> com o Claude e consome tokens. As
                    edições manuais que você fez neste Pack serão substituídas.
                  </p>
                  <p>
                    A versão atual fica salva no histórico e pode ser restaurada depois sem custo.
                    Se você só quer corrigir uma tela, use <strong>Reescrever este slide</strong> —
                    o pedido leva bem menos contexto.
                  </p>
                </div>
              }
              confirmLabel="Gerar nova versão"
              onConfirm={() => void generateVisualPack()}
            />
          ) : (
            <Button
              size="sm"
              onClick={() => void generateVisualPack()}
              disabled={!script || generating}
            >
              {generating ? (
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Wand2 className="mr-1 h-3.5 w-3.5" />
              )}
              {generateLabel}
            </Button>
          )}
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
            disabled={!script || !pack || exporting || packIsLegacy}
          >
            {exporting ? (
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
          description="Crie um roteiro para gerar o carrossel educativo de 7 slides."
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
                  {clarity ? (
                    <StatusBadge
                      label={`${clarity.balanced}/${clarity.slides.length} slides equilibrados`}
                      tone={clarity.warnings === 0 ? "success" : "warn"}
                    />
                  ) : null}
                  {outdatedEducationalFlow ? (
                    <StatusBadge label="Trilha educativa anterior" tone="warn" />
                  ) : null}
                </div>
                <h2 className="font-display text-xl font-semibold tracking-tight">
                  {pack?.carousel[0]
                    ? headlineOf(pack.carousel[0])
                    : (script?.titulo ?? "Selecione um roteiro")}
                </h2>
                <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
                  {packIsLegacy
                    ? `Este Pack salvo ainda tem ${pack.carousel.length} slides. Gere a versão nova para liberar os PNGs.`
                    : "O preview mostra exatamente o PNG que será publicado. Editar texto, trocar layout, foto ou tema é local e não consome tokens."}
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
                <Button
                  size="sm"
                  onClick={() => void generateVisualPack()}
                  disabled={generating || loadingPack}
                >
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
                      slides. Por isso o app bloqueia “Salvar PNGs” até gerar a nova versão.
                    </p>
                  </div>
                </section>
              ) : null}

              <div className="grid items-start gap-4 xl:grid-cols-[196px_minmax(0,392px)_minmax(0,1fr)]">
                {/* Trilha: PNGs pequenos em cache, sem abrir sete iframes. */}
                <nav aria-label="Slides do carrossel" className="rounded-xl border bg-card p-2">
                  <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-1">
                    {pack.carousel.map((item, index) => {
                      const entry = clarity?.slides.find((row) => row.slide === index + 1);
                      const step =
                        educationalSteps[index] ?? educationalSteps[educationalSteps.length - 1];
                      const selected = index === activeSlide;
                      return (
                        <li key={`${layoutOf(item)}-${index}`}>
                          <button
                            type="button"
                            onClick={() => setActiveSlide(index)}
                            aria-current={selected ? "true" : undefined}
                            aria-label={`Abrir slide ${index + 1}: ${headlineOf(item)}`}
                            className={`w-full rounded-lg border px-2.5 py-2 text-left transition-colors ${
                              selected
                                ? "border-primary bg-primary/5"
                                : "border-transparent hover:border-primary/40 hover:bg-muted/50"
                            }`}
                          >
                            <span className="grid grid-cols-[68px_minmax(0,1fr)] items-start gap-2">
                              <img
                                src={packSlideThumbnailUrl(script.id, index, pack)}
                                width={270}
                                height={338}
                                loading="eager"
                                decoding="async"
                                alt=""
                                aria-hidden="true"
                                className="aspect-[270/338] w-[68px] rounded-md border bg-muted object-cover shadow-sm"
                              />
                              <span className="min-w-0">
                                <span className="flex items-center justify-between gap-2">
                                  <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                                    {String(index + 1).padStart(2, "0")}
                                  </span>
                                  {entry?.warnings.length ? (
                                    <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-status-warn" />
                                  ) : (
                                    <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-status-success" />
                                  )}
                                </span>
                                <span className="mt-1 block text-xs font-medium leading-snug">
                                  {step.title}
                                </span>
                                <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                                  {headlineOf(item)}
                                </span>
                                {entry ? (
                                  <span className="mt-1 block">
                                    <ClarityChip density={entry.density} />
                                  </span>
                                ) : null}
                              </span>
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </ol>
                </nav>

                {/* Preview: o mesmo HTML que vira PNG. */}
                <section className="rounded-xl border bg-card p-3">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <h3 className="text-sm font-semibold">
                      Slide {activeSlide + 1} · {slideLayout ? labelOf(slideLayout) : ""}
                    </h3>
                    <StatusBadge label="Preview real do PNG" tone="info" />
                  </div>
                  <SlidePreview
                    scriptId={script.id}
                    slideIndex={activeSlide}
                    nonce={previewNonce}
                    width={368}
                  />
                  <div className="mt-2 flex items-center justify-between gap-2">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setActiveSlide((index) => Math.max(0, index - 1))}
                      disabled={activeSlide === 0}
                    >
                      Anterior
                    </Button>
                    <span className="text-xs tabular-nums text-muted-foreground">
                      {activeSlide + 1} / {pack.carousel.length}
                    </span>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        setActiveSlide((index) => Math.min(pack.carousel.length - 1, index + 1))
                      }
                      disabled={activeSlide >= pack.carousel.length - 1}
                    >
                      Próximo
                    </Button>
                  </div>
                </section>

                {/* Inspetor: clareza, texto, layout e foto do slide selecionado. */}
                <section className="space-y-3">
                  {slideClarity ? (
                    <div className="rounded-xl border bg-card p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <h3 className="text-sm font-semibold">Clareza deste slide</h3>
                        <ClarityChip density={slideClarity.density} />
                      </div>
                      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
                        <div
                          className={`h-full rounded-full ${
                            slideClarity.density === "equilibrado"
                              ? "bg-status-success"
                              : "bg-status-warn"
                          }`}
                          style={{
                            width: `${Math.min(
                              100,
                              Math.round((slideClarity.characters / slideClarity.comfortMax) * 100),
                            )}%`,
                          }}
                        />
                      </div>
                      <p className="mt-1.5 text-[11px] tabular-nums text-muted-foreground">
                        {slideClarity.characters} caracteres · faixa confortável{" "}
                        {slideClarity.comfortMin}–{slideClarity.comfortMax} · frase mais longa{" "}
                        {slideClarity.longestSentenceWords} palavras
                      </p>
                      {slideClarity.warnings.length ? (
                        <ul className="mt-2 space-y-1">
                          {slideClarity.warnings.map((warning) => (
                            <li
                              key={warning}
                              className="flex items-start gap-1.5 text-[11px] leading-relaxed text-status-warn"
                            >
                              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                              <span>{warning}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="mt-2 text-[11px] text-status-success">
                          Sem alertas de clareza nesta tela.
                        </p>
                      )}
                    </div>
                  ) : null}

                  <div className="rounded-xl border bg-card p-3">
                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                      <h3 className="text-sm font-semibold">Texto do slide</h3>
                      <StatusBadge label="Edição sem tokens" tone="success" />
                    </div>
                    {slideSpec ? (
                      <div className="space-y-3">
                        {slideSpec.editableFields.map((name) => {
                          const label = designSystem?.fieldLabels[name] ?? name;
                          if (isItemField(name)) {
                            const item = (draft[name] as PackSlideItem | undefined) ?? {
                              title: "",
                              text: "",
                            };
                            const titleMax = slideSpec.itemMaxChars.title;
                            const textMax = slideSpec.itemMaxChars.text;
                            return (
                              <fieldset key={name} className="rounded-lg border p-2.5">
                                <legend className="px-1 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
                                  {label}
                                </legend>
                                <Input
                                  className="h-8 text-sm"
                                  value={item.title}
                                  aria-label={`${label} — título`}
                                  placeholder="Título curto"
                                  onChange={(event) =>
                                    updateDraftItem(name, "title", event.target.value)
                                  }
                                />
                                {titleMax ? (
                                  <span className="mt-1 block text-right text-[10px] tabular-nums text-muted-foreground">
                                    {item.title.length}/{titleMax}
                                  </span>
                                ) : null}
                                <Textarea
                                  className="mt-1.5 min-h-14 resize-y text-sm"
                                  value={item.text}
                                  aria-label={`${label} — texto`}
                                  placeholder="Frase completa"
                                  onChange={(event) =>
                                    updateDraftItem(name, "text", event.target.value)
                                  }
                                />
                                {textMax ? (
                                  <span
                                    className={`mt-1 block text-right text-[10px] tabular-nums ${
                                      item.text.length > textMax
                                        ? "text-status-danger"
                                        : "text-muted-foreground"
                                    }`}
                                  >
                                    {item.text.length}/{textMax}
                                  </span>
                                ) : null}
                              </fieldset>
                            );
                          }
                          const value = (draft[name] as string | undefined) ?? "";
                          const max = slideSpec.maxChars[name];
                          const over = Boolean(max && value.length > max);
                          return (
                            <div key={name}>
                              <label
                                htmlFor={`pack-field-${name}`}
                                className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground"
                              >
                                {label}
                              </label>
                              {longFields.has(name) ? (
                                <Textarea
                                  id={`pack-field-${name}`}
                                  className="mt-1 min-h-20 resize-y text-sm"
                                  value={value}
                                  onChange={(event) => updateDraftText(name, event.target.value)}
                                />
                              ) : (
                                <Input
                                  id={`pack-field-${name}`}
                                  className="mt-1 h-9 text-sm"
                                  value={value}
                                  onChange={(event) => updateDraftText(name, event.target.value)}
                                />
                              )}
                              {max ? (
                                <span
                                  className={`mt-0.5 block text-right text-[10px] tabular-nums ${
                                    over ? "text-status-danger" : "text-muted-foreground"
                                  }`}
                                >
                                  {value.length}/{max}
                                </span>
                              ) : null}
                            </div>
                          );
                        })}
                        <div className="flex flex-wrap items-center gap-2">
                          <Button
                            size="sm"
                            onClick={() => void saveSlideText()}
                            disabled={!dirty || savingSlide}
                          >
                            {savingSlide ? (
                              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                            ) : null}
                            Salvar texto do slide
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setDraft(savedDraft)}
                            disabled={!dirty || savingSlide}
                          >
                            <RotateCcw className="mr-1 h-3.5 w-3.5" /> Descartar
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground">
                        Carregando os limites deste layout…
                      </p>
                    )}
                  </div>

                  <div className="rounded-xl border bg-card p-3">
                    <h3 className="mb-2 text-sm font-semibold">Composição deste slide</h3>
                    <div className="grid gap-2 sm:grid-cols-2">
                      <div>
                        <label
                          htmlFor="pack-slide-layout"
                          className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground"
                        >
                          Layout
                        </label>
                        <Select
                          value={slideLayout}
                          onValueChange={(value) => void changeLayout(value as PackLayout)}
                          disabled={savingLayout || !designSystem}
                        >
                          <SelectTrigger id="pack-slide-layout" className="mt-1 h-9 text-sm">
                            <SelectValue placeholder="Escolher layout" />
                          </SelectTrigger>
                          <SelectContent>
                            {(designSystem?.layouts ?? []).map((option) => (
                              <SelectItem key={option.id} value={option.id}>
                                {option.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      {slideSpec?.usesPhoto ? (
                        <div>
                          <label
                            htmlFor="pack-slide-photo"
                            className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground"
                          >
                            Foto (opcional)
                          </label>
                          <Select
                            value={slide && photoIdOf(slide) ? photoIdOf(slide) : NO_PHOTO_VALUE}
                            onValueChange={(value) =>
                              void choosePhoto(value === NO_PHOTO_VALUE ? null : value)
                            }
                            disabled={savingPhoto || photoAssets.length === 0}
                          >
                            <SelectTrigger id="pack-slide-photo" className="mt-1 h-9 text-sm">
                              <SelectValue placeholder="Foto do acervo" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value={NO_PHOTO_VALUE}>Sem foto</SelectItem>
                              {photoAssets.map((asset) => (
                                <SelectItem key={asset.id} value={asset.id}>
                                  {asset.name}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      ) : null}
                    </div>
                    <p className="mt-2 text-[11px] text-muted-foreground">
                      Layout, foto opcional e tema são decisões locais: o texto aprovado é
                      preservado e nenhuma chamada ao Claude é feita.
                    </p>
                  </div>

                  <div className="rounded-xl border bg-card p-3">
                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                      <h3 className="flex items-center gap-2 text-sm font-semibold">
                        <Sparkles className="h-4 w-4 text-status-info" /> Reescrever só este slide
                      </h3>
                      <StatusBadge label="1 chamada, contexto mínimo" tone="warn" />
                    </div>
                    <Textarea
                      className="min-h-16 resize-y text-sm"
                      maxLength={400}
                      value={regenerateNote}
                      placeholder="O que melhorar? Ex.: explique o número em linguagem simples."
                      onChange={(event) => setRegenerateNote(event.target.value)}
                      aria-label="Instrução para reescrever o slide"
                    />
                    <ConfirmAction
                      trigger={
                        <Button
                          size="sm"
                          variant="secondary"
                          className="mt-2"
                          disabled={regeneratingSlide}
                        >
                          {regeneratingSlide ? (
                            <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Sparkles className="mr-1 h-3.5 w-3.5" />
                          )}
                          Reescrever slide {activeSlide + 1}
                        </Button>
                      }
                      title={`Reescrever apenas o slide ${activeSlide + 1}?`}
                      description={
                        <div className="space-y-2 text-sm">
                          <p>
                            O pedido leva só a etapa educativa desta posição, o texto atual do slide
                            e os limites do layout. Os outros seis slides não são reenviados nem
                            alterados.
                          </p>
                          <p>A versão atual fica salva no histórico e pode voltar sem custo.</p>
                        </div>
                      }
                      confirmLabel="Reescrever este slide"
                      onConfirm={() => void regenerateSlide()}
                    />
                  </div>

                  <p className="min-h-4 text-xs text-muted-foreground" aria-live="polite">
                    {localStatus}
                  </p>
                </section>
              </div>

              <Tabs defaultValue="caption" className="space-y-3">
                <TabsList className="grid w-full grid-cols-4 md:w-auto">
                  <TabsTrigger value="caption">Legenda</TabsTrigger>
                  <TabsTrigger value="style">Estilo</TabsTrigger>
                  <TabsTrigger value="versions">Versões</TabsTrigger>
                  <TabsTrigger value="briefing">Qualidade</TabsTrigger>
                </TabsList>

                <TabsContent value="caption">
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-sm">
                        <MessageSquareText className="h-4 w-4" /> Legenda pronta
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <Textarea readOnly className="min-h-[280px]" value={captionOf(pack)} />
                      <div className="flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => copyText("Legenda", captionOf(pack))}
                        >
                          <Copy className="mr-1 h-3.5 w-3.5" /> Copiar legenda
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() =>
                            copyText("Carrossel", formatCarousel(pack.carousel, labelOf))
                          }
                        >
                          <Copy className="mr-1 h-3.5 w-3.5" /> Copiar texto dos 7 slides
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                </TabsContent>

                <TabsContent value="style">
                  <section className="rounded-xl border bg-card p-4 shadow-sm">
                    <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <h2 className="flex items-center gap-2 text-sm font-semibold">
                          <Palette className="h-4 w-4 text-status-info" /> Estilo do Pack
                        </h2>
                        <p className="mt-1 text-sm text-muted-foreground">
                          Composição e tema valem para os 7 slides. A troca é local e preserva o
                          texto.
                        </p>
                      </div>
                      <StatusBadge label="Sem tokens do Claude" tone="success" />
                    </div>

                    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.55fr)_minmax(300px,1fr)]">
                      <fieldset>
                        <legend className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                          Composição
                        </legend>
                        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
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
                                      grayscalePhotos: grayscalePhotosOf(pack),
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
                                      grayscalePhotos: grayscalePhotosOf(pack),
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

                    <div className="mt-5 flex flex-col gap-3 border-t pt-4 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <label htmlFor="pack-grayscale-photos" className="text-sm font-semibold">
                          Fotos em preto e branco
                        </label>
                        <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                          Ativado por padrão. Desative para preservar as cores originais em todos os
                          slides deste Pack.
                        </p>
                      </div>
                      <Switch
                        id="pack-grayscale-photos"
                        checked={grayscalePhotosOf(pack)}
                        disabled={savingPresentation}
                        onCheckedChange={(checked) =>
                          void choosePresentation({
                            family: familyOf(pack),
                            themeId: themeOf(pack),
                            grayscalePhotos: checked,
                          })
                        }
                        aria-label="Usar fotos em preto e branco"
                      />
                    </div>
                  </section>
                </TabsContent>

                <TabsContent value="versions">
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-sm">
                        <History className="h-4 w-4" /> Histórico de conteúdo
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="mb-3 text-sm text-muted-foreground">
                        Cada geração e cada reescrita guarda a versão anterior. Restaurar é uma
                        operação local: não consome tokens do Claude.
                      </p>
                      {versions.length === 0 ? (
                        <p className="text-sm text-muted-foreground">
                          Ainda não há versões anteriores para este Pack.
                        </p>
                      ) : (
                        <ul className="space-y-2">
                          {versions.map((version) => (
                            <li
                              key={version.id}
                              className="flex flex-col gap-2 rounded-lg border bg-background p-3 sm:flex-row sm:items-center sm:justify-between"
                            >
                              <div className="min-w-0">
                                <div className="text-sm font-medium">
                                  {versionOriginLabels[version.origin] ?? version.origin}
                                </div>
                                <p className="mt-0.5 truncate text-xs text-muted-foreground">
                                  {version.summary}
                                </p>
                                <p className="text-[11px] text-muted-foreground">
                                  {new Date(version.createdAt).toLocaleString("pt-BR")}
                                </p>
                              </div>
                              <ConfirmAction
                                trigger={
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    disabled={restoringVersion !== null}
                                  >
                                    {restoringVersion === version.id ? (
                                      <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                                    ) : (
                                      <RotateCcw className="mr-1 h-3.5 w-3.5" />
                                    )}
                                    Restaurar
                                  </Button>
                                }
                                title="Restaurar esta versão?"
                                description="O conteúdo atual será guardado no histórico antes da troca. Nenhuma chamada ao Claude é feita."
                                confirmLabel="Restaurar"
                                onConfirm={() => void restoreVersion(version.id)}
                              />
                            </li>
                          ))}
                        </ul>
                      )}
                    </CardContent>
                  </Card>
                </TabsContent>

                <TabsContent value="briefing">
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-sm">Controle de qualidade do pacote</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="mb-4 grid gap-2 text-sm md:grid-cols-4">
                        <div className="rounded-lg border bg-background p-3">
                          <div className="text-xs text-muted-foreground">Sistema visual</div>
                          <div className="mt-1 font-medium">Instituto Guilherme Martins</div>
                        </div>
                        <div className="rounded-lg border bg-background p-3">
                          <div className="text-xs text-muted-foreground">Resolucao de saida</div>
                          <div className="mt-1 font-medium">1080 × 1350 px</div>
                        </div>
                        <div className="rounded-lg border bg-background p-3">
                          <div className="text-xs text-muted-foreground">Layouts distintos</div>
                          <div className="mt-1 font-medium">
                            {clarity?.distinctLayouts ?? new Set(pack.carousel.map(layoutOf)).size}{" "}
                            de {pack.carousel.length}
                          </div>
                        </div>
                        <div className="rounded-lg border bg-background p-3">
                          <div className="text-xs text-muted-foreground">Alertas de clareza</div>
                          <div className="mt-1 flex items-center gap-2 font-medium">
                            <ImageIcon className="h-4 w-4 text-status-info" />
                            {clarity?.warnings ?? 0}
                          </div>
                        </div>
                      </div>
                      {clarity && clarity.warnings > 0 ? (
                        <div className="mb-4 space-y-1 rounded-lg border border-amber-200 bg-amber-50 p-3">
                          {clarity.slides
                            .filter((entry) => entry.warnings.length)
                            .map((entry) => (
                              <button
                                type="button"
                                key={entry.slide}
                                onClick={() => setActiveSlide(entry.slide - 1)}
                                className="block w-full text-left text-xs text-amber-900 hover:underline"
                              >
                                <strong>Slide {entry.slide}:</strong> {entry.warnings.join(" · ")}
                              </button>
                            ))}
                        </div>
                      ) : null}
                      <div className="grid gap-2 md:grid-cols-2">
                        {(pack.checklist.length
                          ? pack.checklist
                          : [
                              "7 slides em sequencia narrativa",
                              "Conceito explicado antes de dados e cuidados",
                              "Uma ideia principal por tela, sem jargao ou confronto",
                              "Fotos opcionais, com no máximo 3 slides usando imagem",
                              "Texto curto, didático e fácil de entender",
                              "Resumo e próximo passo no slide final",
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
