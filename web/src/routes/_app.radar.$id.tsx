import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { genId, useStore } from "@/lib/store";
import { familiaLabel, prioridadeLabel, trendStatusLabel } from "@/lib/status";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { appendIdea, expandIdeas, setSheetStatus, type CaptureHooksResult } from "@/lib/api/local";
import { generateAndPersistCaptureScripts } from "@/lib/script-generation";
import { ArrowLeft, ExternalLink, Loader2, Sparkles, Target, Zap } from "lucide-react";
import { toast } from "sonner";
import { useState } from "react";

export const Route = createFileRoute("/_app/radar/$id")({
  head: ({ params }) => ({
    meta: [
      { title: `Tendencia ${params.id} | AI Video Creator` },
      { name: "description", content: "Detalhe da tendencia capturada." },
    ],
  }),
  component: TendenciaDetalhe,
});

function TendenciaDetalhe() {
  const { id } = Route.useParams();
  const trend = useStore((s) => s.trends.find((t) => t.id === id));
  const ideas = useStore((s) =>
    s.ideas
      .filter((i) => i.trendId === id)
      .sort((a, b) => new Date(b.criadoEm).getTime() - new Date(a.criadoEm).getTime()),
  );
  const scripts = useStore((s) => s.scripts);
  const updateTrend = useStore((s) => s.updateTrend);
  const addIdea = useStore((s) => s.addIdea);
  const addScript = useStore((s) => s.addScript);
  const navigate = useNavigate();
  const [generating, setGenerating] = useState(false);
  const [generatingCaptures, setGeneratingCaptures] = useState(false);
  const [captureResult, setCaptureResult] = useState<CaptureHooksResult | null>(null);

  const captureIdeas = ideas.filter((idea) => idea.tipo === "Hook de captura 10s");
  const messageIdeas = ideas.filter((idea) => idea.tipo !== "Hook de captura 10s");
  const captureIdeaIds = new Set(captureIdeas.map((idea) => idea.id));
  const captureScripts = scripts
    .filter((script) => script.ideaId && captureIdeaIds.has(script.ideaId))
    .sort((a, b) => new Date(b.criadoEm).getTime() - new Date(a.criadoEm).getTime());

  if (!trend) {
    return (
      <AppShell title="Tendencia">
        <p className="text-sm text-muted-foreground">
          Tendencia nao encontrada.{" "}
          <Link to="/radar" className="text-status-info underline">
            Voltar
          </Link>
        </p>
      </AppShell>
    );
  }

  async function gerarIdeia() {
    if (!trend) return;
    if (messageIdeas[0]) {
      navigate({ to: "/ideias/$id", params: { id: messageIdeas[0].id } });
      return;
    }
    setGenerating(true);
    try {
      const [generated] = await expandIdeas({
        seed: [trend.titulo, trend.subtema, trend.sinal, trend.dorPublico, trend.notas]
          .filter(Boolean)
          .join("\n"),
        quantity: 1,
        familia: trend.familia,
        prioridade: trend.prioridade,
        sourceUrl: trend.link || null,
      });
      if (!generated) throw new Error("A IA nao retornou uma ideia contextualizada.");
      const idea = {
        ...generated,
        id: genId("i"),
        trendId: trend.id,
        linkOrigem: trend.link || generated.linkOrigem,
        criadoEm: new Date().toISOString(),
      };
      const saved = await appendIdea(idea);
      addIdea(saved);
      updateTrend(trend.id, { status: "em_analise" });
      try {
        await setSheetStatus("radar", trend.id, "em_analise");
      } catch {
        toast.warning("Ideia salva, mas o status da tendencia nao foi atualizado.");
      }
      toast.success("Ideia criada e salva no banco de dados.");
      navigate({ to: "/ideias/$id", params: { id: saved.id } });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Nao foi possivel criar a ideia.");
    } finally {
      setGenerating(false);
    }
  }

  async function gerarHooksCaptura() {
    if (!trend) return;
    setGeneratingCaptures(true);
    try {
      const result = await generateAndPersistCaptureScripts({
        idea: {
          id: genId("i"),
          trendId: trend.id,
          titulo: trend.titulo,
          familia: trend.familia,
          hook: trend.sinal || trend.titulo,
          angulo: trend.sinal || trend.subtema || trend.titulo,
          tipo: trend.subtema || "Hook de captura 10s",
          publicoDor: trend.dorPublico,
          cta: "",
          linkOrigem: trend.link,
          observacaoCompliance: trend.notas || "",
          prioridade: trend.prioridade,
          status: "novo",
          criadoEm: new Date().toISOString(),
        },
        persistIdea: true,
        durationSeconds: 10,
        editorialTone: "neutro",
        outro: "",
      });
      addIdea(result.idea);
      result.scripts.forEach(addScript);
      setCaptureResult({
        provider: result.provider,
        analysis: result.analysis,
        variants: result.variants,
      });

      updateTrend(trend.id, { status: "em_analise" });
      try {
        await setSheetStatus("radar", trend.id, "em_analise");
      } catch {
        toast.warning("Hooks salvos, mas o status da tendencia nao foi atualizado.");
      }
      if (result.provider === "fallback") {
        toast.warning("Claude indisponivel. Salvamos 3 hooks seguros de contingencia.");
      } else {
        toast.success("Claude avaliou a tendencia e salvou 3 hooks de captura.");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Nao foi possivel gerar os hooks.");
    } finally {
      setGeneratingCaptures(false);
    }
  }

  async function atualizarStatus(status: "em_analise" | "descartado") {
    if (!trend) return;
    const anterior = trend.status;
    updateTrend(trend.id, { status });
    try {
      await setSheetStatus("radar", trend.id, status);
      toast.success(
        status === "descartado"
          ? "Tendência descartada e atualizada no banco de dados."
          : "Tendencia marcada como em analise.",
      );
    } catch (err) {
      updateTrend(trend.id, { status: anterior });
      toast.error(err instanceof Error ? err.message : "Falha ao sincronizar status.");
    }
  }

  return (
    <AppShell
      title={trend.titulo}
      actions={
        <>
          <Button variant="ghost" size="sm" asChild>
            <Link to="/radar">
              <ArrowLeft className="mr-1 h-4 w-4" /> Voltar
            </Link>
          </Button>
          <Button size="sm" onClick={gerarIdeia} disabled={generating}>
            {generating ? (
              <Loader2 className="mr-1 h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="mr-1 h-4 w-4" />
            )}{" "}
            {generating
              ? "Lendo e contextualizando"
              : messageIdeas[0]
                ? "Ver ideia"
                : "Gerar ideia"}
          </Button>
        </>
      }
    >
      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge {...trendStatusLabel[trend.status]} />
            <StatusBadge {...prioridadeLabel[trend.prioridade]} />
            <PotencialBadge valor={trend.potencial} />
            {messageIdeas[0] || trend.status === "em_analise" ? (
              <Badge variant="outline" className="border-status-success/40 text-status-success">
                Ideia gerada
              </Badge>
            ) : null}
          </div>
          <div className="rounded-xl border bg-card p-4 shadow-sm">
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Fonte
                </dt>
                <dd className="break-words">{fonteLabel(trend.fonte)}</dd>
              </div>
              <div>
                <dt className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Familia
                </dt>
                <dd>{familiaLabel[trend.familia]}</dd>
              </div>
              <div>
                <dt className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Potencial viral
                </dt>
                <dd className="tabular-nums">
                  {trend.potencial == null ? "—" : `${trend.potencial}/10`}
                </dd>
              </div>
              {trend.subtema ? (
                <div>
                  <dt className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Subtema
                  </dt>
                  <dd className="break-words">{trend.subtema}</dd>
                </div>
              ) : null}
              {trend.sinal ? (
                <div className="sm:col-span-2">
                  <dt className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Sinal de tendencia
                  </dt>
                  <dd className="break-words">{trend.sinal}</dd>
                </div>
              ) : null}
              {trend.dorPublico ? (
                <div className="sm:col-span-2">
                  <dt className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Dor do publico
                  </dt>
                  <dd className="break-words text-muted-foreground">{trend.dorPublico}</dd>
                </div>
              ) : null}
              {trend.link ? (
                <div className="sm:col-span-2">
                  <dt className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Link de referencia
                  </dt>
                  <dd>
                    <a
                      href={trend.link}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex max-w-full items-center gap-1 break-all text-status-info hover:underline"
                    >
                      {trend.link} <ExternalLink className="h-3.5 w-3.5 shrink-0" />
                    </a>
                  </dd>
                </div>
              ) : null}
              <div>
                <dt className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Capturado em
                </dt>
                <dd className="text-muted-foreground">
                  {new Date(trend.criadoEm).toLocaleString("pt-BR")}
                </dd>
              </div>
              {trend.notas ? (
                <div className="col-span-2">
                  <dt className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Notas
                  </dt>
                  <dd className="text-sm text-muted-foreground">{trend.notas}</dd>
                </div>
              ) : null}
            </dl>
          </div>

          <section className="overflow-hidden rounded-xl border border-status-info/30 bg-card shadow-sm">
            <div className="flex flex-col gap-4 bg-status-info/5 p-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="max-w-2xl">
                <div className="mb-1 flex items-center gap-2">
                  <Target className="h-4 w-4 text-status-info" />
                  <h2 className="font-display text-base font-semibold">3 hooks de captura</h2>
                  <Badge variant="outline" className="border-status-info/40 text-status-info">
                    10s cada
                  </Badge>
                </div>
                <p className="text-sm text-muted-foreground">
                  Um experimento de aquisicao: tres tentativas curtas para interromper o scroll e
                  levar a pessoa ao perfil. Nao substitui o video de mensagem.
                </p>
              </div>
              <Button
                onClick={gerarHooksCaptura}
                disabled={generatingCaptures}
                className="shrink-0"
              >
                {generatingCaptures ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Zap className="mr-2 h-4 w-4" />
                )}
                {generatingCaptures
                  ? "Claude esta avaliando"
                  : captureScripts.length
                    ? "Gerar novo trio"
                    : "Gerar 3 hooks de 10s"}
              </Button>
            </div>

            {captureResult ? (
              <div className="border-t p-4">
                <div className="mb-4 grid gap-3 sm:grid-cols-[120px_1fr]">
                  <div className="rounded-lg bg-muted p-3 text-center">
                    <div className="text-2xl font-bold tabular-nums text-status-info">
                      {captureResult.analysis.capturePotential}/10
                    </div>
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                      Potencial de captura
                    </div>
                  </div>
                  <div className="rounded-lg border p-3 text-sm">
                    <div className="font-medium">Angulo recomendado</div>
                    <p className="mt-1 text-muted-foreground">
                      {captureResult.analysis.recommendedAngle}
                    </p>
                  </div>
                </div>
                <div className="grid gap-3 lg:grid-cols-3">
                  {captureResult.variants.map((variant) => {
                    const savedScript = captureScripts.find(
                      (script) => script.titulo === `Captura ${variant.variant}: ${variant.title}`,
                    );
                    return (
                      <article
                        key={variant.variant}
                        className="flex flex-col rounded-lg border p-3"
                      >
                        <div className="mb-2 flex items-start justify-between gap-2">
                          <div>
                            <div className="text-[10px] font-semibold uppercase tracking-wider text-status-info">
                              Teste {variant.variant} · {variant.strategy}
                            </div>
                            <h3 className="mt-1 text-sm font-semibold">{variant.title}</h3>
                          </div>
                          <Badge variant="secondary">{variant.wordCount} palavras</Badge>
                        </div>
                        <p className="flex-1 text-sm leading-relaxed">“{variant.spokenText}”</p>
                        <div className="mt-3 flex items-center justify-between border-t pt-3 text-xs text-muted-foreground">
                          <span>
                            Parada {variant.stopScore}/10 · Perfil {variant.profileScore}/10
                          </span>
                          {savedScript ? (
                            <Button size="sm" variant="ghost" asChild>
                              <Link to="/roteiros/$id" params={{ id: savedScript.id }}>
                                Produzir
                              </Link>
                            </Button>
                          ) : null}
                        </div>
                      </article>
                    );
                  })}
                </div>
              </div>
            ) : captureScripts.length ? (
              <div className="border-t p-4">
                <div className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Ultimos roteiros salvos
                </div>
                <div className="grid gap-2 sm:grid-cols-3">
                  {captureScripts.slice(0, 3).map((script) => (
                    <Link
                      key={script.id}
                      to="/roteiros/$id"
                      params={{ id: script.id }}
                      className="rounded-lg border p-3 text-sm transition-colors hover:border-status-info/50 hover:bg-status-info/5"
                    >
                      <div className="font-medium">{script.titulo}</div>
                      <p className="mt-1 line-clamp-3 text-xs text-muted-foreground">
                        {script.textoFalado}
                      </p>
                    </Link>
                  ))}
                </div>
              </div>
            ) : null}
          </section>

          <div className="rounded-xl border bg-card p-4 shadow-sm">
            <h3 className="mb-2 font-display text-sm font-semibold">
              Ideias de mensagem ({messageIdeas.length})
            </h3>
            {messageIdeas.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                Ainda nao ha ideias de mensagem vinculadas a esta tendencia.
              </p>
            ) : (
              <ul className="space-y-2">
                {messageIdeas.map((i) => (
                  <li key={i.id} className="rounded-md border p-2 text-sm">
                    <Link
                      to="/ideias/$id"
                      params={{ id: i.id }}
                      className="font-medium hover:underline"
                    >
                      {i.titulo}
                    </Link>
                    <div className="mt-1 text-xs text-muted-foreground">{i.hook}</div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <aside className="space-y-3">
          <div className="rounded-xl border bg-card p-3 text-xs text-muted-foreground shadow-sm">
            O status é salvo no banco de dados para manter o Radar atualizado.
          </div>
          <Button
            size="sm"
            variant="secondary"
            className="w-full"
            onClick={() => atualizarStatus("em_analise")}
          >
            Marcar como em analise
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="w-full"
            onClick={() => atualizarStatus("descartado")}
          >
            Descartar tendencia
          </Button>
        </aside>
      </div>
    </AppShell>
  );
}

function fonteLabel(fonte: string): string {
  if (!/^https?:\/\//i.test(fonte)) return fonte;
  try {
    return new URL(fonte).hostname.replace(/^www\./, "");
  } catch {
    return fonte;
  }
}

function PotencialBadge({ valor }: { valor?: number }) {
  if (valor == null) return null;
  return (
    <span className="inline-flex items-center rounded-md bg-status-info/10 px-2 py-0.5 text-xs font-semibold text-status-info">
      Potencial {valor}/10
    </span>
  );
}
