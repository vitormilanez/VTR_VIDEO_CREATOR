import { cn } from "@/lib/utils";
import { statusToneClass, type StatusTone } from "@/lib/status";

export function StatusBadge({
  label,
  tone,
  className,
}: {
  label: string;
  tone: StatusTone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        statusToneClass[tone],
        className,
      )}
    >
      {label}
    </span>
  );
}
