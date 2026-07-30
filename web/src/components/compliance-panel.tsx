import { AlertTriangle, CheckCircle2, ShieldAlert, ShieldCheck } from "lucide-react";
import { scanCompliance, tokenizeWithForbidden, type ComplianceRule } from "@/lib/compliance";
import { cn } from "@/lib/utils";

export function CompliancePanel({
  fields,
  palavrasProibidas,
  rules,
  className,
}: {
  fields: Record<string, string>;
  palavrasProibidas: string[];
  rules?: ComplianceRule[];
  className?: string;
}) {
  const { hits, alertas, ok } = scanCompliance(fields, palavrasProibidas, rules);

  return (
    <div className={cn("rounded-xl border bg-card shadow-sm", className)}>
      <div
        className={cn(
          "flex items-center gap-2 rounded-t-xl border-b px-3 py-2 text-xs font-semibold",
          ok
            ? "bg-status-success/15 text-status-success-foreground"
            : "bg-status-warn/15 text-status-warn-foreground",
        )}
      >
        {ok ? <ShieldCheck className="h-4 w-4" /> : <ShieldAlert className="h-4 w-4" />}
        {ok ? "Compliance ok" : `${hits.length + alertas.length} pontos a revisar`}
      </div>

      <div className="space-y-3 p-3">
        <section>
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Palavras proibidas
          </div>
          {hits.length === 0 ? (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <CheckCircle2 className="h-3.5 w-3.5 text-status-success" />
              Nenhuma ocorrencia.
            </div>
          ) : (
            <ul className="space-y-1">
              {hits.map((h) => (
                <li
                  key={h.palavra}
                  className="flex items-center justify-between rounded-md border border-status-danger/30 bg-status-danger/10 px-2 py-1 text-xs"
                >
                  <span className="font-medium text-status-danger">{h.palavra}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {h.count}x · {h.campo}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Alertas medicos
          </div>
          {alertas.length === 0 ? (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <CheckCircle2 className="h-3.5 w-3.5 text-status-success" />
              Nenhum alerta detectado.
            </div>
          ) : (
            <ul className="space-y-1.5">
              {alertas.map((a) => (
                <li
                  key={a.id}
                  className={cn(
                    "rounded-md border p-2 text-xs",
                    a.severidade === "alta"
                      ? "border-status-danger/30 bg-status-danger/10"
                      : "border-status-warn/40 bg-status-warn/10",
                  )}
                >
                  <div className="flex items-center gap-1.5 font-semibold">
                    <AlertTriangle
                      className={cn(
                        "h-3.5 w-3.5",
                        a.severidade === "alta"
                          ? "text-status-danger"
                          : "text-status-warn-foreground",
                      )}
                    />
                    {a.titulo}
                  </div>
                  <div className="mt-0.5 pl-5 text-muted-foreground">{a.detalhe}</div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <p className="rounded-md bg-muted/60 p-2 text-[11px] leading-relaxed text-muted-foreground">
          Regras: nao prescrever, nao citar doses, nao prometer resultado, sem sensacionalismo,
          reforcar avaliacao individual.
        </p>
      </div>
    </div>
  );
}

export function HighlightedText({
  text,
  palavrasProibidas,
  className,
}: {
  text: string;
  palavrasProibidas: string[];
  className?: string;
}) {
  const tokens = tokenizeWithForbidden(text, palavrasProibidas);
  return (
    <span className={cn("whitespace-pre-wrap", className)}>
      {tokens.map((t, i) =>
        t.forbidden ? (
          <mark key={i} className="rounded bg-status-danger/20 px-0.5 text-status-danger">
            {t.text}
          </mark>
        ) : (
          <span key={i}>{t.text}</span>
        ),
      )}
    </span>
  );
}
