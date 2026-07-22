import { Check, Circle, X } from "lucide-react";
import { cn } from "@/lib/utils";

export interface TimelineStep {
  key: string;
  label: string;
  hint?: string;
  timestamp?: string;
  state: "done" | "current" | "pending" | "error";
}

export function StatusTimeline({
  steps,
  className,
}: {
  steps: TimelineStep[];
  className?: string;
}) {
  return (
    <ol className={cn("relative space-y-3", className)}>
      {steps.map((s, idx) => {
        const isLast = idx === steps.length - 1;
        return (
          <li key={s.key} className="relative flex gap-3">
            {!isLast && (
              <span
                aria-hidden
                className={cn(
                  "absolute left-[11px] top-6 h-full w-px",
                  s.state === "done"
                    ? "bg-status-success/50"
                    : s.state === "error"
                    ? "bg-status-danger/40"
                    : "bg-border",
                )}
              />
            )}
            <span
              className={cn(
                "z-10 mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border",
                s.state === "done" &&
                  "border-status-success/50 bg-status-success/20 text-status-success-foreground",
                s.state === "current" &&
                  "border-status-info/60 bg-status-info/15 text-status-info ring-2 ring-status-info/20",
                s.state === "pending" &&
                  "border-border bg-card text-muted-foreground",
                s.state === "error" &&
                  "border-status-danger/50 bg-status-danger/15 text-status-danger",
              )}
            >
              {s.state === "done" ? (
                <Check className="h-3.5 w-3.5" />
              ) : s.state === "error" ? (
                <X className="h-3.5 w-3.5" />
              ) : (
                <Circle className="h-2 w-2 fill-current" />
              )}
            </span>
            <div className="min-w-0 pb-1">
              <div
                className={cn(
                  "text-sm font-medium",
                  s.state === "pending" && "text-muted-foreground",
                )}
              >
                {s.label}
              </div>
              {s.hint ? (
                <div className="text-[11px] text-muted-foreground">{s.hint}</div>
              ) : null}
              {s.timestamp ? (
                <div className="text-[10px] text-muted-foreground">
                  {s.timestamp}
                </div>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
