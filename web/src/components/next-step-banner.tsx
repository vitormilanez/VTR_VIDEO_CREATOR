import type { ReactNode } from "react";
import { ArrowRight, CircleCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface NextStepBannerProps {
  eyebrow?: string;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  actionHref?: string;
  disabled?: boolean;
  disabledReason?: string;
  meta?: ReactNode;
  className?: string;
}

export function NextStepBanner({
  eyebrow = "Próximo passo",
  title,
  description,
  actionLabel,
  onAction,
  actionHref,
  disabled = false,
  disabledReason,
  meta,
  className,
}: NextStepBannerProps) {
  const action =
    actionLabel && actionHref ? (
      <Button size="sm" asChild>
        <a href={actionHref}>
          {actionLabel}
          <ArrowRight className="ml-1 h-4 w-4" />
        </a>
      </Button>
    ) : actionLabel && onAction ? (
      <Button size="sm" onClick={onAction} disabled={disabled} title={disabledReason}>
        {actionLabel}
        <ArrowRight className="ml-1 h-4 w-4" />
      </Button>
    ) : null;

  return (
    <section
      className={cn(
        "rounded-xl border border-status-info/25 bg-status-info/5 px-4 py-3 shadow-sm",
        className,
      )}
    >
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-status-info">
            <CircleCheck className="h-3.5 w-3.5" />
            {eyebrow}
          </div>
          <h2 className="mt-1 font-display text-sm font-semibold">{title}</h2>
          <p className="mt-0.5 max-w-3xl text-xs leading-5 text-muted-foreground">
            {description}
          </p>
          {disabled && disabledReason ? (
            <p className="mt-1 text-xs font-medium text-status-warn-foreground">
              {disabledReason}
            </p>
          ) : null}
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
      {meta ? <div className="mt-3 border-t border-status-info/15 pt-3">{meta}</div> : null}
    </section>
  );
}
