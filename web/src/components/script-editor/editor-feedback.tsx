import { ShieldCheck, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DURATION_PRESETS,
  durationStatusLabel,
  type DurationAssessment,
  type DurationPreset,
  type EditorAssistResult,
  type MedicalReviewStatus,
} from "@/lib/script-editor";
import { cn } from "@/lib/utils";

export function DurationControl({
  assessment,
  durationSeconds,
  onDurationChange,
}: {
  assessment: DurationAssessment;
  durationSeconds: DurationPreset;
  onDurationChange: (duration: DurationPreset) => void;
}) {
  return (
    <>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <div
          className="flex flex-wrap items-center gap-1.5"
          role="group"
          aria-label="Duração da fala"
        >
          {DURATION_PRESETS.map((seconds) => (
            <button
              key={seconds}
              type="button"
              aria-pressed={durationSeconds === seconds}
              onClick={() => onDurationChange(seconds)}
              className={cn(
                "min-h-9 cursor-pointer rounded-full border px-3 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
                durationSeconds === seconds
                  ? "border-primary bg-primary text-primary-foreground"
                  : "bg-background text-muted-foreground hover:border-primary/50 hover:text-foreground",
              )}
            >
              {seconds}s
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span>
            {assessment.wordCount} palavras · {assessment.estimatedSecondsDisplay}
          </span>
          <span>
            Meta {assessment.targetWords} · margem {assessment.hardLimitWords}
          </span>
        </div>
        <span
          className={cn(
            "rounded-full px-2.5 py-1 text-xs font-semibold",
            assessment.status === "blocking"
              ? "bg-status-danger/10 text-status-danger"
              : assessment.status === "warning"
                ? "bg-status-warn/15 text-status-warn-foreground"
                : "bg-status-success/10 text-status-success-foreground",
          )}
        >
          {durationStatusLabel(assessment.status)}
        </span>
      </div>
      <div
        id="script-duration-feedback"
        className={cn(
          "mt-2 rounded-lg border px-3 py-2 text-xs leading-5",
          assessment.status === "blocking"
            ? "border-status-danger/30 bg-status-danger/10 text-status-danger"
            : assessment.status === "warning"
              ? "border-status-warn/30 bg-status-warn/10 text-status-warn-foreground"
              : "border-status-success/25 bg-status-success/5 text-foreground",
        )}
      >
        {assessment.message}
        <span className="ml-1 text-muted-foreground">
          A IA mira {assessment.generationMinWords}–{assessment.generationMaxWords} palavras sem
          preencher todo o limite.
        </span>
      </div>
    </>
  );
}

export function StaleEditorResult({
  result,
  onDiscard,
}: {
  result: EditorAssistResult;
  onDiscard: () => void;
}) {
  return (
    <div
      className="mt-2 rounded-lg border border-status-info/30 bg-status-info/10 px-3 py-2 text-xs text-status-info"
      role="status"
    >
      <p className="font-semibold">Resultado de IA desatualizado</p>
      <p className="mt-1 leading-5">
        A fala foi editada enquanto a IA trabalhava. A versão atual foi preservada.
      </p>
      <details className="mt-2">
        <summary className="cursor-pointer font-medium">Ver resultado antigo</summary>
        <p className="mt-2 whitespace-pre-wrap rounded-md bg-background p-2 text-foreground">
          {result.script}
        </p>
      </details>
      <Button type="button" size="sm" variant="ghost" className="mt-2" onClick={onDiscard}>
        Descartar resultado antigo
      </Button>
    </div>
  );
}

export function QualityIssuesCard({
  issues,
  hasBlockingIssues,
  onFixOutro,
}: {
  issues: string[];
  hasBlockingIssues: boolean;
  onFixOutro: () => void;
}) {
  if (!issues.length) return null;
  return (
    <div
      className={cn(
        "mt-2 rounded-md border px-3 py-2 text-[11px] leading-4",
        hasBlockingIssues
          ? "border-status-danger/30 bg-status-danger/10 text-status-danger"
          : "border-status-info/30 bg-status-info/10 text-status-info",
      )}
    >
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 font-semibold">
          <TriangleAlert className="h-3.5 w-3.5" />
          {hasBlockingIssues ? "Validação técnica necessária" : "Sugestão editorial"}
        </div>
        {issues.some((issue) => issue.includes("frase final")) ? (
          <Button
            type="button"
            size="sm"
            variant="secondary"
            className="h-7 px-2 text-[11px]"
            onClick={onFixOutro}
          >
            Corrigir encerramento
          </Button>
        ) : null}
      </div>
      <ul className="space-y-0.5 pl-5">
        {issues.map((issue) => (
          <li key={issue} className="list-disc">
            {issue}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function TitleAlignmentCard({
  result,
  selected,
  onUseSuggested,
  onKeepCurrent,
}: {
  result: EditorAssistResult;
  selected: "current" | "suggested";
  onUseSuggested: (title: string) => void;
  onKeepCurrent: () => void;
}) {
  if (result.titleAlignment.status !== "possible_mismatch") return null;
  const suggestion = result.titleAlignment.suggestedTitle;
  return (
    <div className="mt-3 rounded-xl border border-status-warn/30 bg-status-warn/5 p-3">
      <div className="flex items-start gap-2">
        <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-status-warn-foreground" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold">Possível desalinhamento de título</p>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            {result.titleAlignment.reason}
          </p>
          {suggestion ? (
            <p className="mt-2 rounded-md bg-background px-3 py-2 text-sm font-medium">
              {suggestion}
            </p>
          ) : null}
          <div className="mt-2 flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              variant={selected === "suggested" ? "default" : "secondary"}
              disabled={!suggestion}
              onClick={() => suggestion && onUseSuggested(suggestion)}
            >
              Usar título sugerido
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={onKeepCurrent}>
              Manter título atual
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function MedicalReviewCard({
  status,
  approved,
  onToggle,
}: {
  status: MedicalReviewStatus;
  approved: boolean;
  onToggle: () => void;
}) {
  return (
    <div
      className={cn(
        "mt-3 flex flex-col gap-3 rounded-xl border p-3 sm:flex-row sm:items-center sm:justify-between",
        status === "required" ? "border-status-danger/30 bg-status-danger/5" : "bg-muted/20",
      )}
    >
      <div>
        <p className="text-xs font-semibold">Revisão médica</p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          {status === "approved"
            ? "Aprovação humana registrada para esta versão editorial."
            : status === "required"
              ? "Obrigatória pelo risco alto. A duração pode estar ideal e ainda assim exigir esta aprovação."
              : status === "recommended"
                ? "Recomendada pelo risco do tema, sem transformar aviso de duração em erro médico."
                : "Não obrigatória para o nível de risco atual."}
        </p>
      </div>
      {status !== "not_required" ? (
        <Button
          type="button"
          size="sm"
          variant={approved ? "secondary" : "default"}
          onClick={onToggle}
        >
          <ShieldCheck className="mr-1 h-4 w-4" />
          {approved ? "Reabrir revisão" : "Aprovar revisão médica"}
        </Button>
      ) : null}
    </div>
  );
}

export function QualityChecks({ result }: { result: EditorAssistResult }) {
  return (
    <details className="mt-3 rounded-xl border bg-muted/10 p-3">
      <summary className="cursor-pointer text-xs font-semibold">
        Checks de qualidade explicáveis ({result.qualityChecks.length})
      </summary>
      {result.summaryOfChanges.length ? (
        <ul className="mt-3 space-y-1 pl-5 text-xs text-muted-foreground">
          {result.summaryOfChanges.map((change) => (
            <li key={change} className="list-disc">
              {change}
            </li>
          ))}
        </ul>
      ) : null}
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {result.qualityChecks.map((check) => (
          <div key={check.id} className="rounded-lg border bg-background p-2.5">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold">{check.label}</span>
              <span
                className={cn(
                  "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
                  check.status === "blocking"
                    ? "bg-status-danger/10 text-status-danger"
                    : check.status === "warning"
                      ? "bg-status-warn/15 text-status-warn-foreground"
                      : check.status === "pass" || check.status === "ideal"
                        ? "bg-status-success/10 text-status-success-foreground"
                        : "bg-status-info/10 text-status-info-foreground",
                )}
              >
                {check.status}
              </span>
            </div>
            <p className="mt-1 text-[11px] leading-4 text-muted-foreground">{check.detail}</p>
            <p className="mt-1 text-[10px] text-muted-foreground">
              {check.source === "deterministic"
                ? "Regra local"
                : check.source === "policy"
                  ? "Política editorial"
                  : "Análise de IA + validação local"}
            </p>
          </div>
        ))}
      </div>
    </details>
  );
}
