import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import {
  ArrowUpRight,
  Bookmark,
  Clock3,
  Flame,
  FileText,
  Instagram,
  Lightbulb,
  Loader2,
  Music2,
  Newspaper,
  Radar,
  Search,
  ShieldCheck,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { WeeklyArchiveSwitch } from "@/components/weekly-archive-switch";
import { ToneSelectDialog } from "@/components/tone-select-dialog";
import { CaptureScriptChoices } from "@/components/capture-script-choices";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { useStore } from "@/lib/store";
import type { EditorialTone, Idea, Script, ThemeFamily, Trend } from "@/lib/mock-data";
import { appendIdea, saveScript, setSheetStatus } from "@/lib/api/local";
import {
  generateAndPersistCaptureScripts,
  generateAndPersistScript,
} from "@/lib/script-generation";
import { DEFAULT_OUTRO } from "@/lib/script-quality";
import type { DurationPreset } from "@/lib/script-editor";
import { evaluateIdeaQuality } from "@/lib/idea-quality";
import { splitWeekly, type WeeklyView } from "@/lib/weekly-archive";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";

export const Route = createFileRoute("/_app/noticias")({
  head: () => ({
    meta: [
      { title: "Notícias — Rede Social | AI Video Creator" },
      {
        name: "description",
        content: "Tendências de saúde, bem-estar e emagrecimento no Instagram e TikTok.",
      },
    ],
  }),
  component: SocialNewsPage,
});

type Platform = "Instagram" | "TikTok";
type ViewMode = "Todos" | Platform | "Radar";
type Momentum = "Explodindo" | "Em alta" | "Crescendo";
type Risk = "Baixo" | "Moderado" | "Alto";

interface SocialTrend {
  id: string;
  title: string;
  summary: string;
  category: "Emagrecimento" | "Nutrição" | "Bem-estar" | "Fitness";
  platforms: Platform[];
  momentum: Momentum;
  opportunity: number;
  growth: string;
  risk: Risk;
  format: string;
  hook: string;
  tags: string[];
  age: string;
}

type TopicChartItem = SocialTrend & {
  shortTitle: string;
  radarMentions: number;
};

const trends: SocialTrend[] = [
  {
    id: "retatrutida",
    title: "Retatrutida e a nova geração dos GLP-1",
    summary:
      "O público quer entender resultados, diferenças entre moléculas e o que ainda não está disponível no Brasil.",
    category: "Emagrecimento",
    platforms: ["Instagram", "TikTok"],
    momentum: "Explodindo",
    opportunity: 96,
    growth: "Muito forte",
    risk: "Alto",
    format: "Mito ou verdade",
    hook: "A próxima caneta pode ser ainda mais potente — mas há um detalhe importante.",
    tags: ["GLP-1", "retatrutida", "obesidade"],
    age: "Atualizado hoje",
  },
  {
    id: "fibremaxxing",
    title: "Fibremaxxing: mais fibras no prato",
    summary:
      "Receitas e desafios de aumento de fibras conectam saciedade, microbiota e saúde metabólica.",
    category: "Nutrição",
    platforms: ["TikTok", "Instagram"],
    momentum: "Explodindo",
    opportunity: 92,
    growth: "Muito forte",
    risk: "Baixo",
    format: "Lista prática",
    hook: "Antes de cortar mais comida, talvez esteja faltando isto no seu prato.",
    tags: ["fibras", "microbiota", "saciedade"],
    age: "Atualizado hoje",
  },
  {
    id: "jejum-circadiano",
    title: "Jejum circadiano e horário das refeições",
    summary:
      "A conversa migrou de quantas horas ficar sem comer para a relação entre alimentação, luz e relógio biológico.",
    category: "Nutrição",
    platforms: ["TikTok"],
    momentum: "Em alta",
    opportunity: 88,
    growth: "Forte",
    risk: "Moderado",
    format: "Explicação em 45s",
    hook: "Seu jantar pode estar influenciando mais do que apenas as calorias do dia.",
    tags: ["jejum", "ritmo circadiano", "sono"],
    age: "Atualizado hoje",
  },
  {
    id: "massa-muscular",
    title: "Emagrecer sem perder massa muscular",
    summary:
      "Treino de força, proteína e acompanhamento durante o uso de medicamentos ganham espaço nas dúvidas.",
    category: "Fitness",
    platforms: ["Instagram", "TikTok"],
    momentum: "Em alta",
    opportunity: 90,
    growth: "Forte",
    risk: "Moderado",
    format: "3 cuidados essenciais",
    hook: "A balança caiu. Mas será que foi gordura que você perdeu?",
    tags: ["massa magra", "proteína", "força"],
    age: "Atualizado hoje",
  },
  {
    id: "microtreinos",
    title: "Microtreinos para uma rotina corrida",
    summary:
      "Blocos de 5 a 10 minutos reduzem a barreira de entrada e geram conteúdo altamente salvável.",
    category: "Fitness",
    platforms: ["Instagram"],
    momentum: "Crescendo",
    opportunity: 84,
    growth: "Consistente",
    risk: "Baixo",
    format: "Demonstração guiada",
    hook: "Sem uma hora livre? Comece com os próximos sete minutos.",
    tags: ["microtreino", "movimento", "rotina"],
    age: "Atualizado hoje",
  },
  {
    id: "cortisol",
    title: "Cortisol, estresse e fome emocional",
    summary:
      "Conteúdos que explicam o tema sem transformar cortisol no culpado por tudo têm alto potencial educativo.",
    category: "Bem-estar",
    platforms: ["Instagram", "TikTok"],
    momentum: "Em alta",
    opportunity: 86,
    growth: "Forte",
    risk: "Moderado",
    format: "Reação com contexto",
    hook: "Não, o cortisol não bloqueou sozinho o seu emagrecimento.",
    tags: ["cortisol", "estresse", "fome emocional"],
    age: "Atualizado hoje",
  },
  {
    id: "volume-eating",
    title: "Pratos de alto volume e baixa densidade calórica",
    summary:
      "Comparações visuais de pratos mostram como aumentar a saciedade sem prometer atalhos.",
    category: "Nutrição",
    platforms: ["TikTok", "Instagram"],
    momentum: "Crescendo",
    opportunity: 81,
    growth: "Consistente",
    risk: "Baixo",
    format: "Antes e depois do prato",
    hook: "Os dois pratos têm calorias parecidas. Qual deles sustentaria você por mais tempo?",
    tags: ["saciedade", "receita", "déficit calórico"],
    age: "Atualizado hoje",
  },
  {
    id: "saude-alem-balanca",
    title: "Saúde além da balança",
    summary:
      "Energia, sono, exames e força aparecem como contraponto à obsessão por transformações rápidas.",
    category: "Bem-estar",
    platforms: ["Instagram"],
    momentum: "Crescendo",
    opportunity: 78,
    growth: "Consistente",
    risk: "Baixo",
    format: "Carrossel educativo",
    hook: "Cinco sinais de evolução que a balança não consegue mostrar.",
    tags: ["saúde metabólica", "hábitos", "consistência"],
    age: "Atualizado hoje",
  },
  {
    id: "proteina-pratica",
    title: "Proteína prática em todas as refeições",
    summary:
      "Receitas simples e comparações de porções respondem à busca por saciedade e preservação de massa muscular.",
    category: "Nutrição",
    platforms: ["TikTok", "Instagram"],
    momentum: "Em alta",
    opportunity: 83,
    growth: "Forte",
    risk: "Baixo",
    format: "Receita comentada",
    hook: "Você não precisa viver de frango para atingir uma boa quantidade de proteína.",
    tags: ["proteína", "receita prática", "massa muscular"],
    age: "Atualizado hoje",
  },
  {
    id: "sono-emagrecimento",
    title: "Sono como parte do emagrecimento",
    summary:
      "Rotina noturna, apetite e recuperação ganham relevância em conteúdos que conectam hábitos sem soluções mágicas.",
    category: "Bem-estar",
    platforms: ["Instagram", "TikTok"],
    momentum: "Crescendo",
    opportunity: 80,
    growth: "Consistente",
    risk: "Baixo",
    format: "Checklist noturno",
    hook: "Dormir melhor não emagrece sozinho, mas pode mudar suas decisões no dia seguinte.",
    tags: ["sono", "apetite", "recuperação"],
    age: "Atualizado hoje",
  },
];

const SOCIAL_SNAPSHOT_AT = "2026-08-05T12:00:00-03:00";

const momentumStyles: Record<Momentum, string> = {
  Explodindo: "border-rose-200 bg-rose-50 text-rose-700",
  "Em alta": "border-amber-200 bg-amber-50 text-amber-700",
  Crescendo: "border-sky-200 bg-sky-50 text-sky-700",
};

const riskStyles: Record<Risk, string> = {
  Baixo: "text-emerald-700",
  Moderado: "text-amber-700",
  Alto: "text-rose-700",
};

const categoryFamily: Record<SocialTrend["category"], ThemeFamily> = {
  Emagrecimento: "obesidade",
  Nutrição: "metabolismo",
  "Bem-estar": "comportamento",
  Fitness: "comportamento",
};

const platformSources: Record<Platform, string> = {
  TikTok: "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/pt/",
  Instagram: "https://www.instagram.com/explore/",
};

function buildSocialIdea(trend: SocialTrend, platform: Platform, radarMatch?: Trend): Idea {
  const evidence = radarMatch
    ? `O Radar também encontrou “${radarMatch.titulo}” (${radarMatch.fonte}, potencial ${radarMatch.potencial ?? "não informado"}/10).`
    : "Ainda não há uma ocorrência correspondente no Radar; trate a leitura social como sinal editorial, não como evidência clínica.";
  const riskDirection =
    trend.risk === "Alto"
      ? "Validar afirmações médicas, disponibilidade no Brasil e limites da evidência. Não prescrever, citar doses ou prometer emagrecimento."
      : "Manter caráter educativo, sem promessa de resultado, diagnóstico, prescrição ou comparação corporal.";

  return {
    id: `i-social-${platform.toLowerCase()}-${trend.id}`,
    trendId: radarMatch?.id ?? `social-${platform.toLowerCase()}-${trend.id}`,
    titulo: trend.title,
    familia: categoryFamily[trend.category],
    hook: trend.hook,
    angulo: `${trend.summary} O sinal está ${trend.momentum.toLowerCase()} no ${platform}, com oportunidade ${trend.opportunity}/100 e aceleração ${trend.growth.toLowerCase()}. Formato recomendado: ${trend.format}. ${evidence}`,
    tipo: `${trend.format} · ${platform}`,
    publicoDor: `${trend.summary} A audiência busca uma explicação clara que diferencie tendência social, evidência disponível e orientação individual.`,
    cta: "Salve para rever com calma e procure orientação individual antes de tomar decisões de saúde.",
    linkOrigem: radarMatch?.link ?? platformSources[platform],
    observacaoCompliance: riskDirection,
    prioridade: trend.opportunity >= 90 ? "alta" : trend.opportunity >= 80 ? "media" : "baixa",
    status: "novo",
    criadoEm: new Date().toISOString(),
  };
}

interface SocialScriptPending {
  idea: Idea;
  actionKey: string;
}

function SocialNewsPage() {
  const navigate = useNavigate();
  const radarTrends = useStore((state) => state.trends);
  const addIdea = useStore((state) => state.addIdea);
  const updateIdea = useStore((state) => state.updateIdea);
  const addScript = useStore((state) => state.addScript);
  const updateScript = useStore((state) => state.updateScript);
  const [search, setSearch] = useState("");
  const [view, setView] = useState<ViewMode>("Todos");
  const [weeklyView, setWeeklyView] = useState<WeeklyView>("current");
  const [saved, setSaved] = useState<string[]>([]);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [scriptPending, setScriptPending] = useState<SocialScriptPending | null>(null);
  const [captureChoices, setCaptureChoices] = useState<Script[]>([]);
  const [editorialTone, setEditorialTone] = useState<EditorialTone>("neutro");
  const [scriptDuration, setScriptDuration] = useState<DurationPreset>(45);
  const [scriptOutro, setScriptOutro] = useState(DEFAULT_OUTRO);

  const socialWeekly = splitWeekly(trends, () => SOCIAL_SNAPSHOT_AT);
  const weeklySocialTrends = weeklyView === "current" ? socialWeekly.current : socialWeekly.archive;

  const filtered = useMemo(() => {
    const query = normalizeText(search.trim());
    return weeklySocialTrends.filter((trend) => {
      if (!query) return true;
      return normalizeText(
        [trend.title, trend.summary, trend.category, ...trend.tags].join(" "),
      ).includes(query);
    });
  }, [search, weeklySocialTrends]);

  const radarWeekly = splitWeekly(
    radarTrends.filter((trend) => trend.status !== "descartado"),
    (trend) => trend.criadoEm,
  );
  const weeklyRadarTrends = weeklyView === "current" ? radarWeekly.current : radarWeekly.archive;
  const activeRadar = useMemo(
    () => weeklyRadarTrends.sort((a, b) => (b.potencial ?? 0) - (a.potencial ?? 0)),
    [weeklyRadarTrends],
  );
  const tiktokTrends = filtered.filter((trend) => trend.platforms.includes("TikTok"));
  const instagramTrends = filtered.filter((trend) => trend.platforms.includes("Instagram"));
  const filteredRadar = useMemo(() => {
    const query = normalizeText(search.trim());
    if (!query) return activeRadar;
    return activeRadar.filter((trend) =>
      normalizeText(
        [trend.titulo, trend.subtema, trend.sinal, trend.dorPublico, trend.notas, trend.fonte]
          .filter(Boolean)
          .join(" "),
      ).includes(query),
    );
  }, [activeRadar, search]);
  const showTikTok = view === "Todos" || view === "TikTok";
  const showInstagram = view === "Todos" || view === "Instagram";
  const showRadar = view === "Todos" || view === "Radar";
  const visibleCount =
    (showTikTok ? tiktokTrends.length : 0) +
    (showInstagram ? instagramTrends.length : 0) +
    (showRadar ? filteredRadar.length : 0);
  const topTopics = useMemo(
    () =>
      [...weeklySocialTrends]
        .sort((a, b) => b.opportunity - a.opportunity)
        .slice(0, 10)
        .map((trend) => ({
          ...trend,
          shortTitle: shortenTopic(trend.title),
          radarMentions: activeRadar.filter((radarTrend) =>
            Boolean(findRadarMatch(trend, [radarTrend])),
          ).length,
        })),
    [activeRadar, weeklySocialTrends],
  );

  const lowRisk = weeklySocialTrends.filter((trend) => trend.risk === "Baixo").length;

  function toggleSaved(id: string) {
    setSaved((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  }

  async function createIdeaFromTrend(trend: SocialTrend, platform: Platform, radarMatch?: Trend) {
    const actionKey = `idea-${platform}-${trend.id}`;
    if (busyAction) return;
    setBusyAction(actionKey);
    try {
      const idea = buildSocialIdea(trend, platform, radarMatch);
      const savedIdea = await appendIdea(idea);
      addIdea(savedIdea);
      toast.success("Ideia criada e vinculada à tendência social.");
      navigate({ to: "/ideias/$id", params: { id: savedIdea.id } });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível criar a ideia.");
    } finally {
      setBusyAction(null);
    }
  }

  function openScriptFlow(trend: SocialTrend, platform: Platform, radarMatch?: Trend) {
    if (busyAction) return;
    const idea = buildSocialIdea(trend, platform, radarMatch);
    const quality = evaluateIdeaQuality(idea);
    if (!quality.ready) {
      toast.error(`A pauta precisa de mais contexto antes do roteiro: ${quality.issues[0]}`);
      return;
    }
    setEditorialTone("neutro");
    setScriptDuration(45);
    setScriptOutro(DEFAULT_OUTRO);
    setScriptPending({ idea, actionKey: `script-${platform}-${trend.id}` });
  }

  async function generateSocialScript() {
    if (!scriptPending || busyAction) return;
    setBusyAction(scriptPending.actionKey);
    try {
      if (scriptDuration <= 15) {
        const { idea, scripts } = await generateAndPersistCaptureScripts({
          idea: scriptPending.idea,
          persistIdea: true,
          durationSeconds: scriptDuration as 10 | 15,
          editorialTone,
          outro: scriptDuration === 10 ? "" : scriptOutro.trim() || DEFAULT_OUTRO,
        });
        addIdea(idea);
        scripts.forEach(addScript);
        updateIdea(idea.id, { status: "aprovado" });
        try {
          await setSheetStatus("ideias", idea.id, "aprovado");
        } catch {
          toast.warning("Roteiros salvos, mas o status da ideia não foi atualizado.");
        }
        setScriptPending(null);
        setCaptureChoices(scripts);
        toast.success(`Claude gerou e validou 3 roteiros de ${scriptDuration}s.`);
        return;
      }

      const { idea, script } = await generateAndPersistScript({
        idea: scriptPending.idea,
        editorialTone,
        durationSeconds: scriptDuration,
        outro: scriptOutro.trim() || DEFAULT_OUTRO,
        persistIdea: true,
      });
      addIdea(idea);
      addScript(script);
      updateIdea(idea.id, { status: "aprovado" });
      try {
        await setSheetStatus("ideias", idea.id, "aprovado");
      } catch {
        toast.warning("Roteiro salvo, mas o status da ideia não foi atualizado.");
      }
      setScriptPending(null);
      toast.success("Roteiro criado pelo Claude e enviado para revisão de fala.");
      navigate({ to: "/roteiros/$id", params: { id: script.id } });
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "O fluxo foi interrompido antes de salvar um roteiro inválido.",
      );
    } finally {
      setBusyAction(null);
    }
  }

  async function confirmCaptureScripts(selected: Script[]) {
    try {
      const updated = await Promise.all(
        selected.map((script) => saveScript({ ...script, status: "em_revisao" })),
      );
      updated.forEach((script) => updateScript(script.id, script));
      setCaptureChoices([]);
      toast.success(
        `${updated.length} ${updated.length === 1 ? "roteiro enviado" : "roteiros enviados"} para revisão de fala.`,
      );
      navigate({ to: "/roteiros/$id", params: { id: updated[0].id } });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível salvar a seleção.");
    }
  }

  return (
    <AppShell title="Notícias — Rede Social">
      <section className="relative overflow-hidden rounded-2xl border bg-primary px-5 py-6 text-primary-foreground shadow-lg md:px-8 md:py-8">
        <div className="pointer-events-none absolute -right-20 -top-24 h-72 w-72 rounded-full bg-status-success/20 blur-3xl" />
        <div className="pointer-events-none absolute bottom-0 right-1/3 h-32 w-32 rounded-full bg-white/10 blur-2xl" />
        <div className="relative grid gap-6 lg:grid-cols-[1fr_auto] lg:items-end">
          <div className="max-w-2xl">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Badge className="border-white/20 bg-white/10 text-white hover:bg-white/10">
                <Sparkles className="mr-1.5 h-3.5 w-3.5" /> Inteligência social
              </Badge>
              <span className="flex items-center gap-1.5 text-xs text-white/65">
                <Clock3 className="h-3.5 w-3.5" /> Leitura editorial de 5 ago 2026
              </span>
            </div>
            <h2 className="font-display text-2xl font-semibold tracking-tight md:text-3xl">
              O que está movimentando saúde e bem-estar agora
            </h2>
            <p className="mt-2 max-w-xl text-sm leading-6 text-white/72 md:text-base">
              Sinais de Instagram e TikTok traduzidos em pautas relevantes, seguras e prontas para
              virar conteúdo.
            </p>
          </div>
          <div className="flex gap-2">
            <a
              href="https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/pt/"
              target="_blank"
              rel="noreferrer"
            >
              <Button
                variant="secondary"
                className="cursor-pointer bg-white text-primary hover:bg-white/90"
              >
                Ver fonte ao vivo <ArrowUpRight className="ml-1.5 h-4 w-4" />
              </Button>
            </a>
          </div>
        </div>
      </section>

      <section
        className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
        aria-label="Resumo do radar social"
      >
        <Metric
          icon={<Flame className="h-4 w-4" />}
          label="Assuntos monitorados"
          value={String(weeklySocialTrends.length)}
          detail="nesta leitura"
          tone="rose"
        />
        <Metric
          icon={<Radar className="h-4 w-4" />}
          label="Sinais no Radar"
          value={String(activeRadar.length)}
          detail="fontes editoriais integradas"
          tone="cyan"
        />
        <Metric
          icon={<ShieldCheck className="h-4 w-4" />}
          label="Baixo risco editorial"
          value={String(lowRisk)}
          detail="pautas mais seguras"
          tone="emerald"
        />
        <Metric
          icon={<Bookmark className="h-4 w-4" />}
          label="Pautas salvas"
          value={String(saved.length)}
          detail="para trabalhar depois"
          tone="violet"
        />
      </section>

      <WeeklyArchiveSwitch
        className="mt-5"
        value={weeklyView}
        onChange={setWeeklyView}
        currentCount={socialWeekly.current.length + radarWeekly.current.length}
        archiveCount={socialWeekly.archive.length + radarWeekly.archive.length}
      />

      <section
        className="mt-4 rounded-xl border bg-card px-4 py-3 shadow-sm"
        aria-label="Fluxo de criação"
      >
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
          <span className="font-semibold text-foreground">Fluxo protegido</span>
          <span className="text-muted-foreground">Tendência</span>
          <span aria-hidden="true" className="text-muted-foreground">
            →
          </span>
          <span className="text-muted-foreground">Claude validado</span>
          <span aria-hidden="true" className="text-muted-foreground">
            →
          </span>
          <span className="text-muted-foreground">Ideia + roteiro salvos</span>
          <span aria-hidden="true" className="text-muted-foreground">
            →
          </span>
          <span className="text-muted-foreground">Revisão de fala</span>
          <span aria-hidden="true" className="text-muted-foreground">
            →
          </span>
          <span className="text-muted-foreground">HeyGen</span>
          <Badge
            variant="outline"
            className="ml-auto border-emerald-200 bg-emerald-50 text-emerald-700"
          >
            <ShieldCheck className="mr-1 h-3 w-3" /> Sem pular etapas
          </Badge>
        </div>
      </section>

      {topTopics.length ? <TopTopicsChart topics={topTopics} /> : null}

      <section className="mt-5 rounded-xl border bg-card p-3 shadow-sm">
        <div className="grid gap-3 xl:grid-cols-[minmax(320px,1fr)_auto] xl:items-center">
          <label className="relative block">
            <span className="sr-only">Buscar assunto</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Buscar assunto, dor ou palavra-chave..."
              className="h-10 pl-9"
            />
          </label>
          <div
            className="grid grid-cols-4 rounded-lg bg-muted p-1"
            role="group"
            aria-label="Escolher fonte exibida"
          >
            {(["Todos", "TikTok", "Instagram", "Radar"] as ViewMode[]).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setView(option)}
                aria-pressed={view === option}
                className={cn(
                  "cursor-pointer rounded-md px-3 py-2 text-xs font-medium transition-colors duration-200",
                  view === option
                    ? "bg-card text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {option}
              </button>
            ))}
          </div>
        </div>
        <p className="mt-2 px-1 text-[11px] text-muted-foreground" aria-live="polite">
          A busca consulta as três fontes ao mesmo tempo. Exibindo {visibleCount} resultados em{" "}
          {view}.
        </p>
      </section>

      {showRadar ? <RadarIntegration trends={filteredRadar} expanded={view === "Radar"} /> : null}

      {showTikTok || showInstagram ? (
        <section
          className={cn(
            "mt-5 grid items-start gap-4",
            showTikTok && showInstagram && "xl:grid-cols-2",
          )}
          aria-live="polite"
        >
          {showTikTok ? (
            <PlatformPanel
              platform="TikTok"
              trends={tiktokTrends}
              radarTrends={activeRadar}
              saved={saved}
              onSave={toggleSaved}
              busyAction={busyAction}
              onCreateIdea={createIdeaFromTrend}
              onGenerateScript={openScriptFlow}
            />
          ) : null}
          {showInstagram ? (
            <PlatformPanel
              platform="Instagram"
              trends={instagramTrends}
              radarTrends={activeRadar}
              saved={saved}
              onSave={toggleSaved}
              busyAction={busyAction}
              onCreateIdea={createIdeaFromTrend}
              onGenerateScript={openScriptFlow}
            />
          ) : null}
        </section>
      ) : null}

      {visibleCount === 0 ? (
        <section className="mt-5 flex min-h-64 flex-col items-center justify-center rounded-xl border border-dashed bg-card p-8 text-center">
          <Newspaper className="h-8 w-8 text-muted-foreground" />
          <h3 className="mt-3 font-display font-semibold">Nenhuma pauta encontrada</h3>
          <p className="mt-1 max-w-sm text-sm text-muted-foreground">
            {weeklySocialTrends.length === 0 && filteredRadar.length === 0
              ? weeklyView === "current"
                ? "Esta semana ainda não buscamos tendências. Quando a nova leitura for feita, ela aparecerá aqui."
                : "O arquivo ainda está vazio. As leituras anteriores serão preservadas aqui automaticamente."
              : "Ajuste a busca ou escolha outra fonte para ampliar os resultados."}
          </p>
          <Button
            variant="outline"
            className="mt-4 cursor-pointer"
            onClick={() => {
              setSearch("");
              setView("Todos");
            }}
          >
            Limpar filtros
          </Button>
        </section>
      ) : null}

      <ToneSelectDialog
        open={Boolean(scriptPending)}
        onOpenChange={(open) => !open && !busyAction && setScriptPending(null)}
        ideaTitle={scriptPending?.idea.titulo ?? ""}
        tone={editorialTone}
        onToneChange={setEditorialTone}
        durationSeconds={scriptDuration}
        onDurationChange={setScriptDuration}
        outro={scriptOutro}
        onOutroChange={setScriptOutro}
        isGenerating={Boolean(busyAction)}
        onConfirm={() => void generateSocialScript()}
      />
      <CaptureScriptChoices
        scripts={captureChoices}
        onOpenChange={(open) => !open && setCaptureChoices([])}
        onConfirm={confirmCaptureScripts}
      />
    </AppShell>
  );
}

function TopTopicsChart({ topics }: { topics: TopicChartItem[] }) {
  return (
    <section className="mt-5 overflow-hidden rounded-2xl border bg-card shadow-sm">
      <header className="flex flex-col gap-2 border-b bg-muted/35 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-status-info">
            Leitura da semana
          </p>
          <h3 className="mt-1 font-display text-lg font-semibold">Top 10 temas mais hypados</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Índice de oportunidade de 0 a 100, cruzado com ocorrências do Radar.
          </p>
        </div>
        <Badge
          variant="outline"
          className="w-fit border-status-info/25 bg-status-info/5 text-status-info"
        >
          <TrendingUp className="mr-1.5 h-3.5 w-3.5" /> Passe o mouse para aprofundar
        </Badge>
      </header>
      <div className="h-[480px] w-full px-2 py-4 sm:px-4">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={topics}
            layout="vertical"
            margin={{ top: 4, right: 28, bottom: 4, left: 8 }}
          >
            <CartesianGrid strokeDasharray="3 3" horizontal={false} opacity={0.35} />
            <XAxis
              type="number"
              domain={[0, 100]}
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 11 }}
            />
            <YAxis
              type="category"
              dataKey="shortTitle"
              width={150}
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 11 }}
            />
            <Tooltip
              cursor={{ fill: "oklch(0.92 0.04 200 / 0.35)" }}
              content={({ active, payload }) => {
                const topic = payload?.[0]?.payload as TopicChartItem | undefined;
                if (!active || !topic) return null;
                return (
                  <div className="max-w-sm rounded-xl border bg-popover p-4 text-popover-foreground shadow-xl">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-status-info">
                          #{topic.category}
                        </p>
                        <p className="mt-1 font-display text-sm font-semibold leading-5">
                          {topic.title}
                        </p>
                      </div>
                      <span className="shrink-0 font-display text-xl font-semibold text-status-info">
                        {topic.opportunity}
                      </span>
                    </div>
                    <p className="mt-2 text-xs leading-5 text-muted-foreground">{topic.summary}</p>
                    <div className="mt-3 grid grid-cols-2 gap-2 rounded-lg bg-muted/60 p-3 text-[11px]">
                      <span>
                        <strong>{topic.radarMentions}</strong> sinais no Radar
                      </span>
                      <span>
                        Risco <strong>{topic.risk.toLowerCase()}</strong>
                      </span>
                      <span>{topic.platforms.join(" + ")}</span>
                      <span>{topic.format}</span>
                    </div>
                    <div className="mt-3 border-t pt-3">
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                        Gancho sugerido
                      </p>
                      <p className="mt-1 text-xs font-medium leading-5">“{topic.hook}”</p>
                    </div>
                  </div>
                );
              }}
            />
            <Bar
              dataKey="opportunity"
              name="Índice de oportunidade"
              fill="oklch(0.6 0.09 210)"
              radius={[0, 6, 6, 0]}
              maxBarSize={24}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

function shortenTopic(title: string) {
  return title.length > 28 ? `${title.slice(0, 27)}…` : title;
}

function RadarIntegration({
  trends: radarTrends,
  expanded = false,
}: {
  trends: Trend[];
  expanded?: boolean;
}) {
  const visibleTrends = expanded ? radarTrends : radarTrends.slice(0, 3);
  return (
    <section className="mt-5 overflow-hidden rounded-xl border border-status-info/25 bg-card shadow-sm">
      <div className="flex flex-col gap-3 border-b bg-status-info/5 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-status-info/10 text-status-info">
            <Radar className="h-4.5 w-4.5" />
          </span>
          <div>
            <h3 className="font-display text-sm font-semibold">Integrado ao Radar de tendências</h3>
            <p className="text-xs text-muted-foreground">
              Cruzamento com notícias, pesquisas e demais fontes já capturadas pelo projeto.
            </p>
          </div>
        </div>
        <Button asChild variant="outline" size="sm" className="cursor-pointer">
          <Link to="/radar">
            Abrir Radar <ArrowUpRight className="ml-1.5 h-3.5 w-3.5" />
          </Link>
        </Button>
      </div>
      {radarTrends.length ? (
        <div className="grid divide-y md:grid-cols-3 md:divide-x md:divide-y-0">
          {visibleTrends.map((trend) => (
            <Link
              key={trend.id}
              to="/radar/$id"
              params={{ id: trend.id }}
              className="group cursor-pointer p-4 transition-colors duration-200 hover:bg-muted/45"
            >
              <div className="flex items-center justify-between gap-2">
                <Badge variant="secondary" className="font-normal">
                  Potencial {trend.potencial ?? "—"}/10
                </Badge>
                <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  {trend.fonte || "Radar"}
                </span>
              </div>
              <p className="mt-2 line-clamp-2 text-sm font-semibold leading-5 group-hover:text-status-info">
                {trend.titulo}
              </p>
              <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">
                {trend.sinal || trend.subtema || "Ver análise completa"}
              </p>
            </Link>
          ))}
        </div>
      ) : (
        <div className="flex flex-col gap-2 px-4 py-4 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <span>O Radar ainda não retornou sinais nesta sessão.</span>
          <Link to="/radar" className="cursor-pointer font-medium text-status-info hover:underline">
            Buscar tendências agora
          </Link>
        </div>
      )}
    </section>
  );
}

function PlatformPanel({
  platform,
  trends,
  radarTrends,
  saved,
  onSave,
  busyAction,
  onCreateIdea,
  onGenerateScript,
}: {
  platform: Platform;
  trends: SocialTrend[];
  radarTrends: Trend[];
  saved: string[];
  onSave: (id: string) => void;
  busyAction: string | null;
  onCreateIdea: (trend: SocialTrend, platform: Platform, radarMatch?: Trend) => void;
  onGenerateScript: (trend: SocialTrend, platform: Platform, radarMatch?: Trend) => void;
}) {
  const isTikTok = platform === "TikTok";
  const icon = isTikTok ? <Music2 className="h-5 w-5" /> : <Instagram className="h-5 w-5" />;

  return (
    <section
      data-testid={`social-panel-${platform.toLowerCase()}`}
      className="overflow-hidden rounded-2xl border bg-card shadow-sm"
    >
      <header
        className={cn(
          "flex items-center justify-between gap-3 border-b px-4 py-4",
          isTikTok
            ? "bg-linear-to-r from-slate-950 to-slate-800 text-white"
            : "bg-linear-to-r from-fuchsia-700 via-rose-600 to-amber-500 text-white",
        )}
      >
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/12">
            {icon}
          </span>
          <div>
            <h3 className="font-display text-lg font-semibold">Painel {platform}</h3>
            <p className="text-xs text-white/70">Tendências e oportunidades da plataforma</p>
          </div>
        </div>
        <Badge className="border-white/20 bg-white/10 text-white hover:bg-white/10">
          {trends.length} {trends.length === 1 ? "sinal" : "sinais"}
        </Badge>
      </header>

      {trends.length ? (
        <div className="grid gap-3 p-3 sm:p-4">
          {trends.map((trend) =>
            (() => {
              const radarMatch = findRadarMatch(trend, radarTrends);
              return (
                <TrendCard
                  key={`${platform}-${trend.id}`}
                  trend={trend}
                  platform={platform}
                  radarMatch={radarMatch}
                  saved={saved.includes(trend.id)}
                  onSave={() => onSave(trend.id)}
                  busyAction={busyAction}
                  onCreateIdea={() => onCreateIdea(trend, platform, radarMatch)}
                  onGenerateScript={() => onGenerateScript(trend, platform, radarMatch)}
                />
              );
            })(),
          )}
        </div>
      ) : (
        <div className="flex min-h-48 flex-col items-center justify-center p-6 text-center">
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
            {icon}
          </span>
          <p className="mt-3 text-sm font-medium">Nenhum sinal com estes filtros</p>
          <p className="mt-1 text-xs text-muted-foreground">O outro painel pode ter resultados.</p>
        </div>
      )}
    </section>
  );
}

function findRadarMatch(socialTrend: SocialTrend, radarTrends: Trend[]) {
  const socialTerms = [...socialTrend.tags, socialTrend.title]
    .flatMap((value) => normalizeText(value).split(/\s+/))
    .filter((value) => value.length >= 4 && !STOP_WORDS.has(value));

  return radarTrends
    .map((trend) => {
      const radarText = normalizeText(
        [trend.titulo, trend.subtema, trend.sinal, trend.dorPublico, trend.notas]
          .filter(Boolean)
          .join(" "),
      );
      const score = new Set(socialTerms.filter((term) => radarText.includes(term))).size;
      return { trend, score };
    })
    .filter((candidate) => candidate.score > 0)
    .sort((a, b) => b.score - a.score || (b.trend.potencial ?? 0) - (a.trend.potencial ?? 0))[0]
    ?.trend;
}

const STOP_WORDS = new Set([
  "para",
  "mais",
  "como",
  "sem",
  "uma",
  "novo",
  "nova",
  "saude",
  "prato",
  "rotina",
]);

function normalizeText(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR");
}

function Metric({
  icon,
  label,
  value,
  detail,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  detail: string;
  tone: "rose" | "cyan" | "emerald" | "violet";
}) {
  const tones = {
    rose: "bg-rose-50 text-rose-700",
    cyan: "bg-cyan-50 text-cyan-700",
    emerald: "bg-emerald-50 text-emerald-700",
    violet: "bg-violet-50 text-violet-700",
  };

  return (
    <article className="rounded-xl border bg-card p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          <p className="mt-1 font-display text-2xl font-semibold tabular-nums">{value}</p>
          <p className="mt-0.5 text-[11px] text-muted-foreground">{detail}</p>
        </div>
        <span className={cn("flex h-9 w-9 items-center justify-center rounded-lg", tones[tone])}>
          {icon}
        </span>
      </div>
    </article>
  );
}

function TrendCard({
  trend,
  platform,
  radarMatch,
  saved,
  onSave,
  busyAction,
  onCreateIdea,
  onGenerateScript,
}: {
  trend: SocialTrend;
  platform: Platform;
  radarMatch?: Trend;
  saved: boolean;
  onSave: () => void;
  busyAction: string | null;
  onCreateIdea: () => void;
  onGenerateScript: () => void;
}) {
  const ideaActionKey = `idea-${platform}-${trend.id}`;
  const scriptActionKey = `script-${platform}-${trend.id}`;
  return (
    <article
      data-testid={`social-trend-${platform.toLowerCase()}-${trend.id}`}
      className="group flex h-full flex-col rounded-xl border bg-card p-4 shadow-sm transition-[border-color,box-shadow] duration-200 hover:border-status-info/40 hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="outline" className={cn("border", momentumStyles[trend.momentum])}>
            {trend.momentum === "Explodindo" ? (
              <Flame className="mr-1 h-3 w-3" />
            ) : (
              <TrendingUp className="mr-1 h-3 w-3" />
            )}
            {trend.momentum}
          </Badge>
          <Badge variant="secondary" className="font-normal">
            {trend.category}
          </Badge>
          {radarMatch ? (
            <Badge className="border-status-info/20 bg-status-info/10 text-status-info hover:bg-status-info/10">
              <Radar className="mr-1 h-3 w-3" /> Radar vinculado
            </Badge>
          ) : null}
        </div>
        <Button
          variant="ghost"
          size="icon"
          aria-label={saved ? "Remover pauta dos salvos" : "Salvar pauta"}
          aria-pressed={saved}
          onClick={onSave}
          className={cn("h-8 w-8 shrink-0 cursor-pointer", saved && "bg-accent text-primary")}
        >
          <Bookmark className={cn("h-4 w-4", saved && "fill-current")} />
        </Button>
      </div>

      <h4 className="mt-3 font-display text-base font-semibold leading-snug transition-colors group-hover:text-status-info">
        {trend.title}
      </h4>
      <p className="mt-1.5 line-clamp-3 text-sm leading-5 text-muted-foreground">{trend.summary}</p>

      <div className="mt-4 rounded-lg bg-muted/55 p-3">
        <div className="flex items-center justify-between text-xs">
          <span className="font-medium">Oportunidade</span>
          <span className="font-semibold tabular-nums text-primary">{trend.opportunity}/100</span>
        </div>
        <Progress value={trend.opportunity} className="mt-2 h-1.5" />
        <div className="mt-2.5 flex items-center justify-between text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1">
            <TrendingUp className="h-3 w-3 text-emerald-600" /> Aceleração{" "}
            {trend.growth.toLowerCase()}
          </span>
          <span className={cn("font-medium", riskStyles[trend.risk])}>
            Risco {trend.risk.toLowerCase()}
          </span>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {trend.tags.map((tag) => (
          <span
            key={tag}
            className="rounded-md bg-secondary px-2 py-1 text-[10px] font-medium text-secondary-foreground"
          >
            #{tag.replaceAll(" ", "")}
          </span>
        ))}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 border-t pt-3">
        <Button
          variant="outline"
          size="sm"
          className="cursor-pointer"
          disabled={Boolean(busyAction)}
          onClick={onCreateIdea}
        >
          {busyAction === ideaActionKey ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <Lightbulb className="mr-1.5 h-3.5 w-3.5" />
          )}
          Criar ideia
        </Button>
        <Button
          size="sm"
          className="cursor-pointer"
          disabled={Boolean(busyAction)}
          onClick={onGenerateScript}
        >
          {busyAction === scriptActionKey ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <FileText className="mr-1.5 h-3.5 w-3.5" />
          )}
          Gerar roteiro
        </Button>
      </div>

      <div className="mt-3 flex items-center justify-between gap-3 text-xs text-muted-foreground">
        <span className="flex items-center gap-1" title={platform}>
          {platform === "Instagram" ? (
            <Instagram className="h-3.5 w-3.5" />
          ) : (
            <Music2 className="h-3.5 w-3.5" />
          )}
          {platform}
        </span>
        {radarMatch ? (
          <Link
            to="/radar/$id"
            params={{ id: radarMatch.id }}
            className="cursor-pointer font-medium text-status-info hover:underline"
          >
            Ver no Radar
          </Link>
        ) : (
          <span className="shrink-0">{trend.age}</span>
        )}
      </div>
    </article>
  );
}
