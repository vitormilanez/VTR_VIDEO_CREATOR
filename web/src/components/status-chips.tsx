import { cn } from "@/lib/utils";
import type { StatusTone } from "@/lib/status";
import { statusToneClass } from "@/lib/status";

export interface StatusChip {
  value: string;
  label: string;
  count?: number;
  tone?: StatusTone;
}

export function StatusChips({
  value,
  onChange,
  options,
  allLabel = "Todos",
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  options: StatusChip[];
  allLabel?: string;
  className?: string;
}) {
  const total = options.reduce((a, o) => a + (o.count ?? 0), 0);
  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      <ChipBtn
        active={value === "todos"}
        onClick={() => onChange("todos")}
        count={total}
      >
        {allLabel}
      </ChipBtn>
      {options.map((o) => (
        <ChipBtn
          key={o.value}
          active={value === o.value}
          onClick={() => onChange(o.value)}
          tone={o.tone}
          count={o.count}
        >
          {o.label}
        </ChipBtn>
      ))}
    </div>
  );
}

function ChipBtn({
  active,
  onClick,
  children,
  count,
  tone,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  count?: number;
  tone?: StatusTone;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium transition-colors",
        active
          ? tone
            ? statusToneClass[tone]
            : "border-primary bg-primary text-primary-foreground"
          : "border-border bg-card text-muted-foreground hover:bg-muted",
      )}
    >
      <span>{children}</span>
      {typeof count === "number" && (
        <span
          className={cn(
            "rounded-full px-1.5 py-0 text-[10px] tabular-nums",
            active ? "bg-black/10 dark:bg-white/10" : "bg-muted-foreground/10",
          )}
        >
          {count}
        </span>
      )}
    </button>
  );
}
