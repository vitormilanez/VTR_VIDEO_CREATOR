import type { ReactNode } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function MetricCard({
  label,
  value,
  hint,
  icon,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  icon?: ReactNode;
  tone?: "default" | "warn" | "danger" | "success" | "info";
}) {
  const toneStyles: Record<string, { border: string; icon: string; accent: string }> = {
    default: { border: "", icon: "text-muted-foreground bg-muted", accent: "" },
    warn: {
      border: "border-status-warn/40",
      icon: "text-status-warn-foreground bg-status-warn/20",
      accent: "bg-status-warn",
    },
    danger: {
      border: "border-status-danger/40",
      icon: "text-status-danger bg-status-danger/10",
      accent: "bg-status-danger",
    },
    success: {
      border: "border-status-success/40",
      icon: "text-status-success-foreground bg-status-success/20",
      accent: "bg-status-success",
    },
    info: {
      border: "border-status-info/40",
      icon: "text-status-info bg-status-info/10",
      accent: "bg-status-info",
    },
  };
  const t = toneStyles[tone];
  return (
    <Card
      className={cn(
        "relative overflow-hidden rounded-xl border bg-gradient-to-br from-card to-muted/40 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md",
        t.border,
      )}
    >
      {tone !== "default" && <div className={cn("absolute inset-x-0 top-0 h-0.5", t.accent)} />}
      <CardContent className="flex items-start justify-between gap-3 p-4">
        <div className="min-w-0">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            {label}
          </div>
          <div className="mt-2 font-display text-3xl font-bold tabular-nums leading-none">
            {value}
          </div>
          {hint ? <div className="mt-2 text-xs text-muted-foreground">{hint}</div> : null}
        </div>
        {icon ? (
          <div
            className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-lg", t.icon)}
          >
            {icon}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
