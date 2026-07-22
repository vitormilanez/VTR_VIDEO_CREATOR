import { AlertTriangle } from "lucide-react";

export function ComplianceBanner() {
  return (
    <div className="flex items-center gap-2 border-b border-status-warn/40 bg-status-warn/15 px-4 py-2 text-[11px] font-medium text-status-warn-foreground">
      <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
      <span>
        Conteudo educativo, nao prescritivo. Sem doses, sem promessas de
        resultado. Toda geracao exige clique explicito.
      </span>
    </div>
  );
}

export function ComplianceHints() {
  const rules = [
    "Nao prescrever medicamento.",
    "Nao citar doses.",
    "Nao prometer resultado.",
    "Nao fazer sensacionalismo.",
    "Reforcar avaliacao individual.",
  ];
  return (
    <div className="rounded-md border border-status-warn/40 bg-status-warn/10 p-3 text-xs">
      <div className="mb-1 font-semibold text-status-warn-foreground">
        Regras de compliance medico
      </div>
      <ul className="list-disc space-y-0.5 pl-4 text-status-warn-foreground/90">
        {rules.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
    </div>
  );
}
