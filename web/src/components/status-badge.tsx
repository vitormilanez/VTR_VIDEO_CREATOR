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
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap",
        statusToneClass[tone],
        className,
      )}
    >
      {label}
    </span>
  );
}
