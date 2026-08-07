import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
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
import { familiaLabel, prioridadeLabel, riskLabel } from "@/lib/status";
import { useStore } from "@/lib/store";
import {
  exportPack,
  fetchPack,
  fetchPackPhotoAssets,
  generatePack,
  refreshPackAvatar,
  updatePackCarouselLayout,
  updatePackCarouselPhoto,
  type GeneratedPack,
  type PackLayout,
  type PackPhotoAsset,
} from "@/lib/api/local";
import type { Script } from "@/lib/mock-data";
import {
  CalendarPlus,
  CheckCircle2,
  Copy,
  FileText,
  FolderDown,
  Loader2,
  RefreshCcw,
  Image,
  ImageOff,
  Instagram,
  Layers3,
  MessageSquareText,
  PanelsTopLeft,
  TriangleAlert,
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
      { name: "description", content: "Pacote multiformato gerado a partir de um roteiro." },
      { property: "og:title", content: "Pack de conteudo | AI Video Creator" },
      { property: "og:description", content: "Video, carrossel, post fixo, legenda e stories." },
    ],
  }),
  component: PacksPage,
});

type Pack = GeneratedPack;

const slideLayoutOptions: Array<{ value: PackLayout; label: string }> = [
  { value: "hero_avatar", label: "Capa com avatar" },
  { value: "avatar_split", label: "Avatar dividido" },
  { value: "big_statement", label: "Frase de impacto" },
  { value: "myth_fact", label: "Mito ou fato" },
  { value: "number_stat", label: "Numero ou dado" },
  { value: "three_points", label: "Tres pontos" },
  { value: "quote_card", label: "Cartao de citacao" },
  { value: "editorial_photo", label: "Editorial com foto" },
  { value: "minimal_explainer", label: "Explicacao minimalista" },
  { value: "cta_avatar", label: "CTA com avatar" },
];

function clean(value?: string) {
  return value?.trim() || "";
}

function sentence(value: string, fallback: string) {
  const text = clean(value);
  return text.endsWith(".") || text.endsWith("?") || text.endsWith("!")
    ? text
    : `${text || fallback}.`;
}

/** Remove pontuacao final para usar como titulo/headline. */
function stripEnd(value: string) {
  return clean(value).replace(/[\s.?!:;,]+$/, "");
}

/** Titulo contextual do slide de reforco, conforme a familia do roteiro. */
function reinforcementSlide(script: Script): { title: string; body: string } {
  const map: Record<string, { title: string; body: string }> = {
    medicamento: {
      title: "Não existe atalho mágico",
      body: "Medicamento pode ajudar, mas indicação, acompanhamento e mudança de hábito andam juntos. Cada caso é um caso.",
    },
    comportamento: {
      title: "Não é falta de força de vontade",
      body: "Comportamento alimentar envolve sono, rotina, emoções e contexto. Julgar só atrapalha o cuidado.",
    },
    metabolismo: {
      title: "Seu corpo dá sinais",
      body: "O metabolismo responde a vários fatores. Entender os sinais ajuda a buscar avaliação no momento certo.",
    },
    obesidade: {
      title: "Obesidade é multifatorial",
      body: "Genética, ambiente, hormônios e rotina influenciam o peso. Cuidado de verdade começa sem culpa.",
    },
    educativo: {
      title: "Cada pessoa é única",
      body: "O que funciona para um pode não servir para outro. Por isso a avaliação individual importa tanto.",
    },
  };
  return map[script.categoria] ?? map.educativo;
}

/** Hashtags derivadas da familia e do tema do roteiro. */
function hashtags(script: Script): string {
  const base = ["saudemetabolica", "educacaoemsaude", "drguilherme"];
  const porFamilia: Record<string, string[]> = {
    medicamento: ["glp1", "emagrecimentocomsaude", "obesidade"],
    comportamento: ["comportamentoalimentar", "habitossaudaveis"],
    metabolismo: ["metabolismo", "resistenciainsulinica"],
    obesidade: ["obesidade", "saudesemjulgamento"],
    educativo: ["saude", "bemestar"],
  };
  const blob = `${script.tema} ${script.titulo}`.toLowerCase();
  const porTema = [
    ["mounjaro", "mounjaro"],
    ["ozempic", "ozempic"],
    ["wegovy", "wegovy"],
    ["glp", "glp1"],
    ["jejum", "jejumintermitente"],
    ["compuls", "compulsaoalimentar"],
    ["insulin", "resistenciainsulinica"],
  ]
    .filter(([k]) => blob.includes(k))
    .map(([, tag]) => tag);

  const tags = [...new Set([...base, ...(porFamilia[script.categoria] ?? []), ...porTema])];
  return tags.map((t) => `#${t}`).join(" ");
}

function buildPack(script: Script): Pack {
  const tema = clean(script.tema) || clean(script.titulo) || "tema principal";
  const hook = sentence(script.hook, `Entenda um ponto importante sobre ${tema}`);
  const dor = sentence(
    script.dorConflito,
    "Muita gente sente isso e acha que o problema é só com ela",
  );
  const explicacao = sentence(
    script.explicacaoSimples,
    "A explicação precisa ser educativa, simples e individualizada",
  );
  const virada = sentence(script.virada, "A virada é trocar promessa por clareza e cuidado real");
  const cta = sentence(script.cta, "Procure avaliação individual com um profissional de saúde");
  const cuidados = sentence(
    script.cuidadosMedicos,
    "Conteúdo educativo: sem dose, sem prescrição e sem promessa de resultado",
  );
  const reforco = reinforcementSlide(script);

  const carousel: Pack["carousel"] = [
    { title: stripEnd(hook), body: "Arraste para entender por que isso importa. 👉" },
    { title: "A real situação", body: dor },
    { title: "O que quase ninguém explica", body: explicacao },
    { title: "A virada de chave", body: virada },
    { title: "Importante saber", body: cuidados },
    reforco,
    { title: "Seu próximo passo", body: `${cta} Salve este post e envie para quem precisa. 💙` },
  ];

  const caption = [
    hook,
    "",
    dor,
    explicacao,
    "",
    `👉 ${virada}`,
    "",
    `⚠️ ${cuidados}`,
    "",
    cta,
    "",
    "Conteúdo educativo. Não substitui avaliação médica individual.",
    "",
    hashtags(script),
  ].join("\n");

  return {
    carousel,
    staticPost: {
      headline: stripEnd(script.titulo || hook),
      subline: stripEnd(virada),
    },
    caption,
    stories: [
      { title: "Capa", body: hook },
      { title: "A dor real", body: dor },
      { title: "Enquete", body: "Você já passou por isso? Responda: 👉 Sim / Ainda não" },
      { title: "Em 1 frase", body: explicacao },
      { title: "Próximo passo", body: `${cta} Toque no link da bio.` },
    ],
    checklist: [
      `Carrossel com ${carousel.length} slides educativos`,
      "Post fixo com frase central de impacto",
      "Legenda pronta com hashtags e aviso de compliance",
      "5 stories com enquete e CTA",
      "Tudo alinhado ao roteiro e às regras de compliance médico",
    ],
  };
}

function copyText(label: string, text: string) {
  navigator.clipboard
    .writeText(text)
    .then(() => toast.success(`${label} copiado.`))
    .catch(() => toast.error("Nao consegui copiar automaticamente."));
}

function formatCarousel(slides: Pack["carousel"]) {
  return slides
    .map((slide, index) => `Slide ${index + 1}: ${slide.title}\n${slide.body}`)
    .join("\n\n");
}

function PacksPage() {
  const scripts = useStore((s) => s.scripts);
  const jobs = useStore((s) => s.videoJobs);
  const posts = useStore((s) => s.calendarPosts);
  const search = Route.useSearch();
  const navigate = useNavigate();
  const [selectedId, setSelectedId] = useState(search.scriptId ?? scripts[0]?.id ?? "");
  const [salvando, setSalvando] = useState(false);
  const [loadingPack, setLoadingPack] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [refreshingAvatar, setRefreshingAvatar] = useState(false);
  const [pack, setPack] = useState<Pack | null>(null);
  const [outdatedAvatar, setOutdatedAvatar] = useState(false);
  const [currentAvatarName, setCurrentAvatarName] = useState("");
  const [savingSlideIndex, setSavingSlideIndex] = useState<number | null>(null);
  const [savingPhotoIndex, setSavingPhotoIndex] = useState<number | null>(null);
  const [photoAssets, setPhotoAssets] = useState<PackPhotoAsset[]>([]);

  const script = scripts.find((item) => item.id === selectedId);
  const mockPack = useMemo(() => (script ? buildPack(script) : null), [script]);
  const videoJob = script ? jobs.find((job) => job.scriptId === script.id) : undefined;
  const scheduledPost = script ? posts.find((post) => post.scriptId === script.id) : undefined;

  useEffect(() => {
    if (!script) {
      setPack(null);
      return;
    }
    let cancelled = false;
    setLoadingPack(true);
    fetchPack(script.id)
      .then((data) => {
        if (cancelled) return;
        setPack(data.pack);
        setOutdatedAvatar(data.outdatedAvatar);
        setCurrentAvatarName(data.pack?.avatarAsset?.avatarName || "");
      })
      .catch((err) => {
        if (!cancelled) {
          setPack(null);
          toast.error(err instanceof Error ? err.message : "Nao foi possivel carregar o Pack.");
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

  function selectScript(id: string) {
    setSelectedId(id);
    navigate({ to: "/packs", search: { scriptId: id }, replace: true });
  }

  async function salvarLocal() {
    if (!script || !pack) return;
    setSalvando(true);
    const aviso = toast.loading("Salvando pack na pasta local...");
    try {
      const res = await exportPack(script, pack);
      toast.success(`Pack salvo em ${res.relative} (${res.files} arquivos).`, {
        id: aviso,
        duration: 8000,
      });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao salvar o pack.", { id: aviso });
    } finally {
      setSalvando(false);
    }
  }

  async function gerarPackVisual() {
    if (!script) return;
    setGenerating(true);
    const aviso = toast.loading("Gerando Pack visual com Claude...");
    try {
      const res = await generatePack(script);
      setPack(res.pack);
      setOutdatedAvatar(false);
      setCurrentAvatarName(res.pack.avatarAsset?.avatarName || "");
      toast.success("Pack visual gerado.", { id: aviso });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Nao foi possivel gerar o Pack.", {
        id: aviso,
      });
    } finally {
      setGenerating(false);
    }
  }

  async function atualizarAvatarDoPack() {
    if (!script) return;
    setRefreshingAvatar(true);
    const aviso = toast.loading("Atualizando Pack com avatar atual...");
    try {
      const res = await refreshPackAvatar(script.id);
      setPack(res.pack);
      setOutdatedAvatar(false);
      setCurrentAvatarName(res.pack.avatarAsset?.avatarName || "");
      toast.success("Pack rerenderizado com o avatar atual, sem chamar Claude.", { id: aviso });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Nao foi possivel atualizar o avatar.", {
        id: aviso,
      });
    } finally {
      setRefreshingAvatar(false);
    }
  }

  async function escolherLayoutDoSlide(slideIndex: number, layout: PackLayout) {
    if (!script || !pack || pack.carousel[slideIndex]?.layout === layout) return;
    const previousPack = pack;
    setSavingSlideIndex(slideIndex);
    setPack({
      ...pack,
      carousel: pack.carousel.map((slide, index) =>
        index === slideIndex ? { ...slide, layout } : slide,
      ),
    });
    try {
      const res = await updatePackCarouselLayout(script.id, slideIndex, layout);
      setPack(res.pack);
      toast.success(`Modelo do slide ${slideIndex + 1} atualizado.`);
    } catch (err) {
      setPack(previousPack);
      toast.error(err instanceof Error ? err.message : "Nao foi possivel atualizar o slide.");
    } finally {
      setSavingSlideIndex(null);
    }
  }

  async function escolherFotoDoSlide(slideIndex: number, photoAssetId: string | null) {
    if (!script || !pack || pack.carousel[slideIndex]?.photoAsset?.id === photoAssetId) return;
    const previousPack = pack;
    const selectedAsset = photoAssets.find((asset) => asset.id === photoAssetId);
    setSavingPhotoIndex(slideIndex);
    setPack({
      ...pack,
      carousel: pack.carousel.map((slide, index) =>
        index === slideIndex
          ? {
              ...slide,
              photoAsset: selectedAsset
                ? {
                    id: selectedAsset.id,
                    name: selectedAsset.name,
                    cachedAssetPath: selectedAsset.cachedAssetPath,
                  }
                : null,
            }
          : slide,
      ),
    });
    try {
      const res = await updatePackCarouselPhoto(script.id, slideIndex, photoAssetId);
      setPack(res.pack);
      toast.success(`Foto do slide ${slideIndex + 1} atualizada.`);
    } catch (err) {
      setPack(previousPack);
      toast.error(err instanceof Error ? err.message : "Nao foi possivel atualizar a foto.");
    } finally {
      setSavingPhotoIndex(null);
    }
  }

  return (
    <AppShell
      title="Pack de conteudo"
      actions={
        <>
          <Button size="sm" onClick={gerarPackVisual} disabled={!script || generating}>
            {generating ? (
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Wand2 className="mr-1 h-3.5 w-3.5" />
            )}
            {pack ? "Gerar nova versao" : "Gerar Pack"}
          </Button>
          {outdatedAvatar ? (
            <Button
              size="sm"
              variant="secondary"
              onClick={atualizarAvatarDoPack}
              disabled={refreshingAvatar}
            >
              {refreshingAvatar ? (
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCcw className="mr-1 h-3.5 w-3.5" />
              )}
              Atualizar Pack com avatar atual
            </Button>
          ) : null}
          <Button
            size="sm"
            variant="secondary"
            onClick={salvarLocal}
            disabled={!script || !pack || salvando}
          >
            {salvando ? (
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
            ) : (
              <FolderDown className="mr-1 h-3.5 w-3.5" />
            )}
            Salvar local
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
          title="Nenhum roteiro para empacotar"
          description="Gere um roteiro primeiro para montar video, carrossel, post e stories."
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
                  <StatusBadge label={pack ? "Pack visual" : "Aguardando geracao"} tone="info" />
                  {script ? <StatusBadge {...riskLabel[script.risco]} /> : null}
                  {script ? <StatusBadge {...prioridadeLabel[script.prioridade]} /> : null}
                  {pack?.designDirection ? (
                    <StatusBadge label={pack.designDirection.replaceAll("_", " ")} tone="success" />
                  ) : null}
                  {outdatedAvatar ? <StatusBadge label="Avatar desatualizado" tone="warn" /> : null}
                </div>
                <h2 className="font-display text-xl font-semibold tracking-tight">
                  {script?.titulo ?? "Selecione um roteiro"}
                </h2>
                <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
                  O Pack herda o avatar escolhido no roteiro e usa layouts fechados do renderer.
                </p>
                {currentAvatarName ? (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Avatar do Pack: {currentAvatarName}
                  </p>
                ) : null}
              </div>
              <div>
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
              title={loadingPack ? "Carregando Pack" : "Nenhum Pack visual gerado"}
              description={
                loadingPack
                  ? "Buscando o Pack salvo para este roteiro."
                  : "Gere o Pack com Claude depois de escolher um avatar na tela do Roteiro."
              }
              action={
                <Button size="sm" onClick={gerarPackVisual} disabled={generating || loadingPack}>
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
              {outdatedAvatar ? (
                <div className="rounded-xl border border-status-warn/40 bg-status-warn/10 p-4 text-sm text-status-warn-foreground">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-start gap-2">
                      <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
                      <div>
                        <div className="font-semibold">Este Pack foi criado com outro avatar.</div>
                        <p className="mt-1 text-xs opacity-85">
                          A atualização reutiliza conteúdo, designPlan, textos e layouts; apenas
                          resolve a nova imagem e renderiza novamente.
                        </p>
                      </div>
                    </div>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={atualizarAvatarDoPack}
                      disabled={refreshingAvatar}
                    >
                      {refreshingAvatar ? (
                        <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <RefreshCcw className="mr-1 h-3.5 w-3.5" />
                      )}
                      Atualizar Pack com avatar atual
                    </Button>
                  </div>
                </div>
              ) : null}

              <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
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
                    {pack.carousel.length} slides
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center gap-2 text-sm">
                      <Image className="h-4 w-4 text-status-info" /> Post fixo
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="text-sm text-muted-foreground">
                    1 peca estatica
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center gap-2 text-sm">
                      <Instagram className="h-4 w-4 text-status-info" /> Stories
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="text-sm text-muted-foreground">
                    {pack.stories.length} telas
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
                <TabsList className="grid w-full grid-cols-2 md:w-auto md:grid-cols-5">
                  <TabsTrigger value="carousel">Carrossel</TabsTrigger>
                  <TabsTrigger value="static">Post fixo</TabsTrigger>
                  <TabsTrigger value="caption">Legenda</TabsTrigger>
                  <TabsTrigger value="stories">Stories</TabsTrigger>
                  <TabsTrigger value="briefing">Briefing</TabsTrigger>
                </TabsList>

                <TabsContent value="carousel">
                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                    {pack.carousel.map((slide, index) => (
                      <div
                        key={`${slide.title}-${index}`}
                        className="flex min-h-[190px] flex-col justify-between rounded-lg border bg-card p-4 shadow-sm"
                      >
                        <div>
                          <div className="mb-3 text-xs font-semibold uppercase text-muted-foreground">
                            Slide {index + 1}
                          </div>
                          <div className="mb-3 flex flex-wrap items-center gap-2">
                            <Select
                              value={slide.layout ?? "minimal_explainer"}
                              onValueChange={(value) =>
                                escolherLayoutDoSlide(index, value as PackLayout)
                              }
                              disabled={savingSlideIndex === index}
                            >
                              <SelectTrigger
                                className="h-8 w-[190px] text-xs"
                                aria-label={`Modelo do slide ${index + 1}`}
                              >
                                <SelectValue placeholder="Escolher modelo" />
                              </SelectTrigger>
                              <SelectContent>
                                {slideLayoutOptions.map((option) => (
                                  <SelectItem key={option.value} value={option.value}>
                                    {option.label}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            {savingSlideIndex === index ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                            ) : null}
                            <Select
                              value={slide.photoAsset?.id ?? "none"}
                              onValueChange={(value) =>
                                escolherFotoDoSlide(index, value === "none" ? null : value)
                              }
                              disabled={savingPhotoIndex === index || photoAssets.length === 0}
                            >
                              <SelectTrigger
                                className="h-8 w-[148px] text-xs"
                                aria-label={`Foto do slide ${index + 1}`}
                              >
                                <SelectValue placeholder="Foto do acervo" />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="none">Sem foto</SelectItem>
                                {photoAssets.map((asset) => (
                                  <SelectItem key={asset.id} value={asset.id}>
                                    {asset.name}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            {slide.photoAsset ? (
                              <img
                                src={
                                  photoAssets.find((asset) => asset.id === slide.photoAsset?.id)
                                    ?.url
                                }
                                alt="Foto escolhida"
                                className="h-8 w-8 rounded object-cover"
                              />
                            ) : null}
                            {savingPhotoIndex === index ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                            ) : null}
                            {slide.avatar?.show ? (
                              <span className="rounded-md bg-status-info/10 px-2 py-0.5 text-[11px] text-status-info">
                                avatar
                              </span>
                            ) : null}
                          </div>
                          {photoAssets.length ? (
                            <div
                              className="mb-4 flex max-w-full gap-1 overflow-x-auto pb-1"
                              aria-label={`Fotos disponíveis para o slide ${index + 1}`}
                            >
                              <button
                                type="button"
                                title="Sem foto"
                                aria-label="Sem foto"
                                onClick={() => escolherFotoDoSlide(index, null)}
                                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded border transition-colors ${
                                  !slide.photoAsset
                                    ? "border-primary bg-primary/10 text-primary"
                                    : "border-border bg-muted text-muted-foreground hover:border-primary/50"
                                }`}
                              >
                                <ImageOff className="h-3.5 w-3.5" />
                              </button>
                              {photoAssets.map((asset) => (
                                <button
                                  key={asset.id}
                                  type="button"
                                  title={asset.name}
                                  aria-label={`Usar ${asset.name}`}
                                  onClick={() => escolherFotoDoSlide(index, asset.id)}
                                  className={`h-9 w-9 shrink-0 overflow-hidden rounded border transition-colors ${
                                    slide.photoAsset?.id === asset.id
                                      ? "border-primary ring-2 ring-primary/30"
                                      : "border-border hover:border-primary/50"
                                  }`}
                                >
                                  <img
                                    src={asset.url}
                                    alt=""
                                    className="h-full w-full object-cover"
                                  />
                                </button>
                              ))}
                            </div>
                          ) : null}
                          <h3 className="font-display text-lg font-semibold leading-tight">
                            {slide.title}
                          </h3>
                          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                            {slide.body}
                          </p>
                          {slide.highlight ? (
                            <p className="mt-3 text-xs font-medium text-foreground">
                              Destaque: {slide.highlight}
                            </p>
                          ) : null}
                        </div>
                      </div>
                    ))}
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

                <TabsContent value="static">
                  <div className="grid gap-4 lg:grid-cols-[420px_minmax(0,1fr)]">
                    <div className="flex aspect-square flex-col justify-between rounded-lg border bg-card p-6 shadow-sm">
                      <div className="text-xs font-semibold uppercase text-muted-foreground">
                        {familiaLabel[script.categoria]}
                      </div>
                      <h3 className="font-display text-3xl font-semibold leading-tight">
                        {pack.staticPost.headline}
                      </h3>
                      <p className="text-sm leading-relaxed text-muted-foreground">
                        {pack.staticPost.subline}
                      </p>
                    </div>
                    <Card>
                      <CardHeader>
                        <CardTitle className="text-sm">Texto da peca estatica</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-3">
                        <Textarea
                          readOnly
                          className="min-h-[190px]"
                          value={`${pack.staticPost.headline}\n\n${pack.staticPost.subline}`}
                        />
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() =>
                            copyText(
                              "Post fixo",
                              `${pack.staticPost.headline}\n\n${pack.staticPost.subline}`,
                            )
                          }
                        >
                          <Copy className="mr-1 h-3.5 w-3.5" /> Copiar post
                        </Button>
                      </CardContent>
                    </Card>
                  </div>
                </TabsContent>

                <TabsContent value="caption">
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-sm">
                        <MessageSquareText className="h-4 w-4" /> Legenda
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <Textarea readOnly className="min-h-[280px]" value={pack.caption} />
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => copyText("Legenda", pack.caption)}
                      >
                        <Copy className="mr-1 h-3.5 w-3.5" /> Copiar legenda
                      </Button>
                    </CardContent>
                  </Card>
                </TabsContent>

                <TabsContent value="stories">
                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                    {pack.stories.map((story, index) => (
                      <div
                        key={`${story.title}-${index}`}
                        className="aspect-[9/16] rounded-lg border bg-card p-4 shadow-sm"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="text-xs font-semibold uppercase text-muted-foreground">
                            {story.title}
                          </div>
                          {story.layout ? (
                            <span className="rounded-md bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
                              {story.layout}
                            </span>
                          ) : null}
                        </div>
                        <p className="mt-8 font-display text-xl font-semibold leading-tight">
                          {story.body}
                        </p>
                      </div>
                    ))}
                  </div>
                </TabsContent>

                <TabsContent value="briefing">
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-sm">Checklist do pacote</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="mb-4 grid gap-2 text-sm md:grid-cols-3">
                        <div className="rounded-lg border bg-background p-3">
                          <div className="text-xs text-muted-foreground">Direcao visual</div>
                          <div className="mt-1 font-medium">
                            {pack.designDirection?.replaceAll("_", " ") || "medical modern"}
                          </div>
                        </div>
                        <div className="rounded-lg border bg-background p-3">
                          <div className="text-xs text-muted-foreground">Avatar herdado</div>
                          <div className="mt-1 font-medium">
                            {pack.avatarAsset?.avatarName || pack.sourceAvatarId || "Nao resolvido"}
                          </div>
                        </div>
                        <div className="rounded-lg border bg-background p-3">
                          <div className="text-xs text-muted-foreground">Layouts usados</div>
                          <div className="mt-1 font-medium">
                            {
                              new Set(pack.carousel.map((slide) => slide.layout).filter(Boolean))
                                .size
                            }
                          </div>
                        </div>
                      </div>
                      <div className="grid gap-2 md:grid-cols-2">
                        {pack.checklist.map((item) => (
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
