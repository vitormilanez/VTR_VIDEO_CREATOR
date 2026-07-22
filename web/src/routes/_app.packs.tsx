import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMemo, useState } from "react";
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
import { generatePack, type GeneratedPack, type PackCompliance } from "@/lib/api/local";
import type { Script } from "@/lib/mock-data";
import {
  CalendarPlus,
  CheckCircle2,
  Copy,
  FileText,
  Loader2,
  Sparkles,
  Image,
  Instagram,
  Layers3,
  MessageSquareText,
  PanelsTopLeft,
  Video,
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

type Pack = {
  carousel: Array<{ title: string; body: string }>;
  staticPost: { headline: string; subline: string };
  caption: string;
  stories: Array<{ title: string; body: string }>;
  checklist: string[];
};

function clean(value?: string) {
  return value?.trim() || "";
}

function sentence(value: string, fallback: string) {
  const text = clean(value);
  return text.endsWith(".") || text.endsWith("?") || text.endsWith("!") ? text : `${text || fallback}.`;
}

/** Remove pontuacao final para usar como titulo/headline. */
function stripEnd(value: string) {
  return clean(value).replace(/[\s.?!:;,]+$/, "");
}

/** Titulo contextual do slide de reforco, conforme a familia do roteiro. */
function reinforcementSlide(script: Script): { title: string; body: string } {
  const map: Record<string, { title: string; body: string }> = {
    medicamento: {
      title: "Nao existe atalho magico",
      body: "Medicamento pode ajudar, mas indicacao, acompanhamento e mudanca de habito andam juntos. Cada caso e um caso.",
    },
    comportamento: {
      title: "Nao e falta de forca de vontade",
      body: "Comportamento alimentar envolve sono, rotina, emocoes e contexto. Julgar so atrapalha o cuidado.",
    },
    metabolismo: {
      title: "Seu corpo tem sinais",
      body: "O metabolismo responde a varios fatores. Entender os sinais ajuda a buscar avaliacao no momento certo.",
    },
    obesidade: {
      title: "Obesidade e multifatorial",
      body: "Genetica, ambiente, hormonios e rotina influenciam o peso. Cuidado de verdade comeca sem culpa.",
    },
    educativo: {
      title: "Cada pessoa e unica",
      body: "O que funciona para um pode nao servir para outro. Por isso a avaliacao individual importa tanto.",
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
  const dor = sentence(script.dorConflito, "Muita gente sente isso e acha que o problema e so com ela");
  const explicacao = sentence(
    script.explicacaoSimples,
    "A explicacao precisa ser educativa, simples e individualizada",
  );
  const virada = sentence(script.virada, "A virada e trocar promessa por clareza e cuidado real");
  const cta = sentence(script.cta, "Procure avaliacao individual com um profissional de saude");
  const cuidados = sentence(
    script.cuidadosMedicos,
    "Conteudo educativo: sem dose, sem prescricao e sem promessa de resultado",
  );
  const reforco = reinforcementSlide(script);

  const carousel: Pack["carousel"] = [
    { title: stripEnd(hook), body: "Arraste para entender por que isso importa. 👉" },
    { title: "A real situacao", body: dor },
    { title: "O que quase ninguem explica", body: explicacao },
    { title: "A virada de chave", body: virada },
    { title: "Importante saber", body: cuidados },
    reforco,
    { title: "Seu proximo passo", body: `${cta} Salve este post e envie para quem precisa. 💙` },
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
    "Conteudo educativo. Nao substitui avaliacao medica individual.",
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
      { title: "Enquete", body: "Voce ja passou por isso? Responda: 👉 Sim / Ainda nao" },
      { title: "Em 1 frase", body: explicacao },
      { title: "Proximo passo", body: `${cta} Toque no link da bio.` },
    ],
    checklist: [
      `Carrossel com ${carousel.length} slides educativos`,
      "Post fixo com frase central de impacto",
      "Legenda pronta com hashtags e aviso de compliance",
      "5 stories com enquete e CTA",
      "Tudo alinhado ao roteiro e as regras de compliance medico",
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
  return slides.map((slide, index) => `Slide ${index + 1}: ${slide.title}\n${slide.body}`).join("\n\n");
}

function PacksPage() {
  const scripts = useStore((s) => s.scripts);
  const jobs = useStore((s) => s.videoJobs);
  const posts = useStore((s) => s.calendarPosts);
  const search = Route.useSearch();
  const navigate = useNavigate();
  const [selectedId, setSelectedId] = useState(search.scriptId ?? scripts[0]?.id ?? "");
  const [aiPack, setAiPack] = useState<GeneratedPack | null>(null);
  const [compliance, setCompliance] = useState<PackCompliance | null>(null);
  const [gerando, setGerando] = useState(false);

  const script = scripts.find((item) => item.id === selectedId);
  const mockPack = useMemo(() => (script ? buildPack(script) : null), [script]);
  const pack: Pack | null = aiPack ?? mockPack;
  const videoJob = script ? jobs.find((job) => job.scriptId === script.id) : undefined;
  const scheduledPost = script ? posts.find((post) => post.scriptId === script.id) : undefined;

  function selectScript(id: string) {
    setSelectedId(id);
    setAiPack(null); // volta ao rascunho ao trocar de roteiro
    setCompliance(null);
    navigate({ to: "/packs", search: { scriptId: id }, replace: true });
  }

  async function gerarComClaude() {
    if (!script) return;
    setGerando(true);
    const aviso = toast.loading("Gerando pack com o Claude...");
    try {
      const gerado = await generatePack(script);
      setAiPack(gerado.pack);
      setCompliance(gerado.compliance);
      if (gerado.compliance.blocked) {
        toast.warning("Pack gerado, mas precisa de revisao de compliance.", { id: aviso });
      } else {
        toast.success("Pack gerado pelo Claude.", { id: aviso });
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao gerar o pack.", { id: aviso });
    } finally {
      setGerando(false);
    }
  }

  return (
    <AppShell
      title="Pack de conteudo"
      actions={
        <>
          <Button size="sm" onClick={gerarComClaude} disabled={!script || gerando}>
            {gerando ? (
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Sparkles className="mr-1 h-3.5 w-3.5" />
            )}
            Gerar com Claude
          </Button>
          <Button asChild size="sm" variant="secondary">
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
                  <StatusBadge label={aiPack ? "Pack Claude" : "Rascunho"} tone={aiPack ? "success" : "neutral"} />
                  {script ? <StatusBadge {...riskLabel[script.risco]} /> : null}
                  {script ? <StatusBadge {...prioridadeLabel[script.prioridade]} /> : null}
                </div>
                <h2 className="font-display text-xl font-semibold tracking-tight">
                  {script?.titulo ?? "Selecione um roteiro"}
                </h2>
                <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
                  Uma ideia vira um conjunto de pecas para revisar, produzir e agendar.
                </p>
                {compliance?.blocked ? (
                  <div className="mt-3 rounded-lg border border-status-danger/30 bg-status-danger/10 p-3 text-sm text-status-danger">
                    <strong>Revisao necessaria:</strong> {compliance.issues.join("; ")}
                  </div>
                ) : aiPack ? (
                  <div className="mt-3 text-sm text-status-success">Pack passou pelo checker de compliance.</div>
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

          {script && pack ? (
            <>
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
                          <h3 className="font-display text-lg font-semibold leading-tight">
                            {slide.title}
                          </h3>
                          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                            {slide.body}
                          </p>
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
                            copyText("Post fixo", `${pack.staticPost.headline}\n\n${pack.staticPost.subline}`)
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
                      <Button size="sm" variant="secondary" onClick={() => copyText("Legenda", pack.caption)}>
                        <Copy className="mr-1 h-3.5 w-3.5" /> Copiar legenda
                      </Button>
                    </CardContent>
                  </Card>
                </TabsContent>

                <TabsContent value="stories">
                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                    {pack.stories.map((story) => (
                      <div key={story.title} className="aspect-[9/16] rounded-lg border bg-card p-4 shadow-sm">
                        <div className="text-xs font-semibold uppercase text-muted-foreground">
                          {story.title}
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
