import { Archive, CalendarDays } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { currentWeekLabel, type WeeklyView } from "@/lib/weekly-archive";

export function WeeklyArchiveSwitch({
  value,
  onChange,
  currentCount,
  archiveCount,
  className,
}: {
  value: WeeklyView;
  onChange: (value: WeeklyView) => void;
  currentCount: number;
  archiveCount: number;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "flex flex-col gap-3 rounded-xl border bg-card p-3 shadow-sm sm:flex-row sm:items-center sm:justify-between",
        className,
      )}
      aria-label="Período dos conteúdos"
    >
      <div className="flex items-center gap-2.5">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-status-info/10 text-status-info">
          {value === "current" ? (
            <CalendarDays className="h-4 w-4" />
          ) : (
            <Archive className="h-4 w-4" />
          )}
        </span>
        <div>
          <p className="text-sm font-semibold">
            {value === "current" ? "Conteúdos desta semana" : "Arquivo de semanas anteriores"}
          </p>
          <p className="text-[11px] text-muted-foreground">
            {value === "current"
              ? `Semana de ${currentWeekLabel()}`
              : "Histórico preservado e disponível para consulta"}
          </p>
        </div>
      </div>
      <div
        className="grid grid-cols-2 rounded-lg bg-muted p-1"
        role="group"
        aria-label="Exibir atuais ou arquivo"
      >
        <ArchiveButton
          active={value === "current"}
          label="Atuais"
          count={currentCount}
          onClick={() => onChange("current")}
        />
        <ArchiveButton
          active={value === "archive"}
          label="Arquivo"
          count={archiveCount}
          onClick={() => onChange("archive")}
        />
      </div>
    </section>
  );
}

function ArchiveButton({
  active,
  label,
  count,
  onClick,
}: {
  active: boolean;
  label: string;
  count: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "flex cursor-pointer items-center justify-center gap-2 rounded-md px-3 py-1.5 text-xs font-medium transition-colors duration-200",
        active
          ? "bg-card text-foreground shadow-sm"
          : "text-muted-foreground hover:text-foreground",
      )}
    >
      {label}
      <Badge
        variant={active ? "default" : "secondary"}
        className="h-5 min-w-5 px-1.5 text-[10px] tabular-nums"
      >
        {count}
      </Badge>
    </button>
  );
}
