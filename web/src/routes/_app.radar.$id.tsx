import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { genId, useStore } from "@/lib/store";
import {
  familiaLabel,
  prioridadeLabel,
  trendStatusLabel,
} from "@/lib/status";
import { Button } from "@/components/ui/button";
import { appendIdea, setSheetStatus } from "@/lib/api/local";
import type { Idea } from "@/lib/mock-data";
import { ArrowLeft, ExternalLink, Sparkles } from "lucide-react";
import { toast } from "sonner";

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
  const ideas = useStore((s) => s.ideas.filter((i) => i.trendId === id));
  const updateTrend = useStore((s) => s.updateTrend);
  const addIdea = useStore((s) => s.addIdea);
  const navigate = useNavigate();

  if (!trend) {
    return (
      <AppShell title="Tendencia">
        <p className="text-sm text-muted-foreground">
          Tendencia nao encontrada.{" "}
          <Link to="/radar" className="text-status-info underline">Voltar</Link>
        </p>
      </AppShell>
    );
  }

  function gerarIdeia() {
    if (!trend) return;
    const idea: Idea = {
      id: genId("i"),
      trendId: trend.id,
      titulo: `Ideia a partir de: ${trend.titulo}`,
      familia: trend.familia,
      hook: "Hook educativo sugerido — revise antes de aprovar.",
      angulo:
        "Angulo educativo: contextualizar o tema sem prescrever, reforcando avaliacao individual.",
      tipo: "Reel",
      publicoDor: trend.dorPublico,
      cta: "Procure avaliacao individualizada com profissional de saude.",
      observacaoCompliance: "Rascunho gerado localmente. Revisar linguagem.",
      prioridade: trend.prioridade,
      status: "novo",
      criadoEm: new Date().toISOString(),
    };
    addIdea(idea);
    updateTrend(trend.id, { status: "em_analise" });
    appendIdea(idea)
      .then(() => toast.success("Ideia criada e salva no Sheets."))
      .catch((err) =>
        toast.error(
          `Ideia criada localmente, mas falhou ao salvar: ${err instanceof Error ? err.message : ""}`,
        ),
      );
    navigate({ to: "/ideias" });
  }

  async function atualizarStatus(status: "em_analise" | "descartado") {
    if (!trend) return;
    const anterior = trend.status;
    updateTrend(trend.id, { status });
    try {
      await setSheetStatus("radar", trend.id, status);
      toast.success(
        status === "descartado"
          ? "Tendencia descartada e sincronizada com o Sheets."
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
            <Link to="/radar"><ArrowLeft className="mr-1 h-4 w-4" /> Voltar</Link>
          </Button>
          <Button size="sm" onClick={gerarIdeia}>
            <Sparkles className="mr-1 h-4 w-4" /> Gerar ideia
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
          </div>
          <div className="rounded-xl border bg-card p-4 shadow-sm">
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Fonte</dt>
                <dd className="break-words">{fonteLabel(trend.fonte)}</dd>
              </div>
              <div>
                <dt className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Familia</dt>
                <dd>{familiaLabel[trend.familia]}</dd>
              </div>
              <div>
                <dt className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Potencial viral</dt>
                <dd className="tabular-nums">{trend.potencial == null ? "—" : `${trend.potencial}/10`}</dd>
              </div>
              {trend.subtema ? (
                <div>
                  <dt className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Subtema</dt>
                  <dd className="break-words">{trend.subtema}</dd>
                </div>
              ) : null}
              {trend.sinal ? (
                <div className="sm:col-span-2">
                  <dt className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Sinal de tendencia</dt>
                  <dd className="break-words">{trend.sinal}</dd>
                </div>
              ) : null}
              {trend.dorPublico ? (
                <div className="sm:col-span-2">
                  <dt className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Dor do publico</dt>
                  <dd className="break-words text-muted-foreground">{trend.dorPublico}</dd>
                </div>
              ) : null}
              {trend.link ? (
                <div className="sm:col-span-2">
                  <dt className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Link de referencia</dt>
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
                <dt className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Capturado em</dt>
                <dd className="text-muted-foreground">
                  {new Date(trend.criadoEm).toLocaleString("pt-BR")}
                </dd>
              </div>
              {trend.notas ? (
                <div className="col-span-2">
                  <dt className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Notas</dt>
                  <dd className="text-sm text-muted-foreground">{trend.notas}</dd>
                </div>
              ) : null}
            </dl>
          </div>

          <div className="rounded-xl border bg-card p-4 shadow-sm">
            <h3 className="mb-2 font-display text-sm font-semibold">
              Ideias geradas ({ideas.length})
            </h3>
            {ideas.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                Ainda nao ha ideias vinculadas a esta tendencia.
              </p>
            ) : (
              <ul className="space-y-2">
                {ideas.map((i) => (
                  <li key={i.id} className="rounded-md border p-2 text-sm">
                    <Link to="/ideias/$id" params={{ id: i.id }} className="font-medium hover:underline">
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
            O status e salvo no Google Sheets para manter o Radar sincronizado.
          </div>
          <Button size="sm" variant="secondary" className="w-full" onClick={() => atualizarStatus("em_analise")}>
            Marcar como em analise
          </Button>
          <Button size="sm" variant="ghost" className="w-full" onClick={() => atualizarStatus("descartado")}>
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
