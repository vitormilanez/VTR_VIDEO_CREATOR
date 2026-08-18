import type { ReactNode } from "react";
import { ArrowRight, CheckCircle2, Circle, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

export function HighCreditConsumptionNotice({ compact = false }: { compact?: boolean }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex items-start gap-2 rounded-lg border border-status-warn/60 bg-status-warn/15 text-status-warn-foreground",
        compact ? "px-3 py-2" : "px-3 py-2.5",
      )}
    >
      <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0">
        <p className="text-xs font-semibold">Maior consumo de créditos</p>
        <p className="mt-0.5 text-[11px] leading-4">
          Vídeos de 45 segundos ou mais podem consumir mais créditos/tokens do HeyGen. Verifique o
          saldo antes de gerar.
        </p>
      </div>
    </div>
  );
}

export function FriendlySwitch({
  icon,
  label,
  description,
  checked,
  onCheckedChange,
}: {
  icon: ReactNode;
  label: string;
  description: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex min-h-14 items-center gap-3 rounded-lg border bg-muted/25 px-3 py-2">
      <div className="text-muted-foreground">{icon}</div>
      <div className="min-w-0 flex-1">
        <Label className="text-xs font-medium">{label}</Label>
        <p className="text-[11px] leading-4 text-muted-foreground">{description}</p>
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} aria-label={label} />
    </div>
  );
}

export function ProductionGateChecklist({
  items,
  blockedReason,
  latestJobId,
  dirty,
  narrationWords,
  estimatedSpeechSeconds,
  onOpenLatest,
  onSend,
}: {
  items: Array<{ label: string; ready: boolean; detail: string }>;
  blockedReason: string | null;
  latestJobId?: string;
  dirty: boolean;
  narrationWords: number;
  estimatedSpeechSeconds: number;
  onOpenLatest?: () => void;
  onSend: () => void;
}) {
  const nextPending = items.find((item) => !item.ready);
  const ready = !nextPending && !blockedReason;
  const nextIssue = blockedReason || nextPending?.detail || null;
  return (
    <div
      className={cn(
        "rounded-xl border p-4 shadow-sm",
        ready
          ? "border-status-success/30 bg-status-success/5"
          : "border-status-warning/30 bg-status-warning/10",
      )}
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-status-info">
            {ready ? (
              <CheckCircle2 className="h-3.5 w-3.5 text-status-success" />
            ) : (
              <TriangleAlert className="h-3.5 w-3.5 text-status-warning" />
            )}
            Checklist final
          </div>
          <h2 className="mt-1 font-display text-sm font-semibold">
            {ready ? "Tudo certo para enviar ao HeyGen" : "Falta resolver antes de gerar"}
          </h2>
          <p className="mt-0.5 max-w-3xl text-xs leading-5 text-muted-foreground">
            O botão só libera quando todos os itens abaixo estiverem validados.
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          {latestJobId && onOpenLatest ? (
            <Button type="button" size="sm" variant="secondary" onClick={onOpenLatest}>
              Ver vídeo
            </Button>
          ) : null}
          <Button type="button" size="sm" onClick={onSend} disabled={!ready}>
            Enviar para produção
            <ArrowRight className="ml-1 h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="mt-3 grid gap-2 md:grid-cols-2">
        {items.map((item) => (
          <div
            key={item.label}
            className="flex items-start gap-2 rounded-lg border bg-background/70 px-3 py-2"
          >
            {item.ready ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-status-success" />
            ) : (
              <Circle className="mt-0.5 h-4 w-4 shrink-0 text-status-warning" />
            )}
            <div className="min-w-0">
              <div className="text-xs font-semibold">{item.label}</div>
              <div className="mt-0.5 text-[11px] leading-4 text-muted-foreground">
                {item.detail}
              </div>
            </div>
          </div>
        ))}
      </div>

      {nextIssue ? (
        <div className="mt-3 rounded-lg border border-status-warning/40 bg-background px-3 py-2 text-xs font-medium text-status-warn-foreground">
          Próximo ajuste: {nextIssue}
        </div>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-2 border-t border-status-info/15 pt-3 text-xs text-muted-foreground">
        <span className="rounded-full bg-background px-2.5 py-1">{narrationWords} palavras</span>
        <span className="rounded-full bg-background px-2.5 py-1">
          ~{estimatedSpeechSeconds}s de fala
        </span>
        <span className="rounded-full bg-background px-2.5 py-1">
          {dirty ? "Alterações pendentes" : "Roteiro salvo"}
        </span>
      </div>
    </div>
  );
}

export function ProductionReadinessCard({
  catalogLoading,
  catalogError,
  avatarReady,
  voiceReady,
  speechReady,
  speechIssue,
  saved,
}: {
  catalogLoading: boolean;
  catalogError: string | null;
  avatarReady: boolean;
  voiceReady: boolean;
  speechReady: boolean;
  speechIssue?: string;
  saved: boolean;
}) {
  const blockingReady = !catalogLoading && avatarReady && voiceReady && speechReady && saved;
  const checks = [
    {
      label: "Avatar",
      ready: avatarReady,
      pending: catalogLoading,
      detail: catalogError ? "Atualize a lista da HeyGen" : "Identidade pronta",
    },
    {
      label: "Voz",
      ready: voiceReady,
      pending: catalogLoading,
      detail: "Voz selecionada para a fala",
    },
    {
      label: "Fala",
      ready: speechReady,
      pending: false,
      detail: speechIssue || "Sem alertas de duração ou encerramento",
    },
    {
      label: "Roteiro",
      ready: saved,
      pending: false,
      detail: saved ? "Alterações salvas" : "Será salvo automaticamente ao enviar",
    },
  ];

  return (
    <div className="rounded-xl border bg-card p-4 shadow-sm">
      <div className="flex items-start gap-2">
        {blockingReady ? (
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-status-success" />
        ) : (
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-status-warn-foreground" />
        )}
        <div>
          <h3 className="font-display text-sm font-semibold">
            {blockingReady ? "Pronto para o HeyGen" : "Checklist de produção"}
          </h3>
          <p className="mt-1 text-[11px] leading-4 text-muted-foreground">
            {blockingReady
              ? "Tudo que impede o envio está resolvido."
              : "Resolva os itens pendentes para liberar o envio."}
          </p>
        </div>
      </div>
      <ul className="mt-3 space-y-2 border-t pt-3">
        {checks.map((check) => (
          <li key={check.label} className="flex items-start gap-2 text-xs">
            {check.pending ? (
              <Circle className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-pulse text-muted-foreground" />
            ) : check.ready ? (
              <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-status-success" />
            ) : (
              <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-status-warn-foreground" />
            )}
            <span className="min-w-0">
              <span className="font-medium">{check.label}</span>
              <span className="block text-[11px] leading-4 text-muted-foreground">
                {check.pending ? "Carregando catálogo..." : check.detail}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
