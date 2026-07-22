import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-muted/30 px-6 py-10 text-center",
        className,
      )}
    >
      {icon ? (
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-background text-muted-foreground shadow-sm">
          {icon}
        </div>
      ) : null}
      <div className="font-display text-sm font-semibold">{title}</div>
      {description ? (
        <div className="max-w-md text-xs text-muted-foreground">{description}</div>
      ) : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
