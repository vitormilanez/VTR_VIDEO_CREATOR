import { Link } from "@tanstack/react-router";
import {
  Radar,
  Lightbulb,
  FileText,
  Film,
  CalendarDays,
  BarChart3,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";

export interface PipelineStep {
  key: string;
  label: string;
  count: number;
  hint?: string;
  to: string;
  tone?: "info" | "warn" | "success" | "danger" | "neutral";
}

const iconMap = {
  radar: Radar,
  ideias: Lightbulb,
  roteiros: FileText,
  producao: Film,
  calendario: CalendarDays,
  performance: BarChart3,
};

const toneRing: Record<string, string> = {
  info: "bg-status-info/10 text-status-info ring-status-info/30",
  warn: "bg-status-warn/20 text-status-warn-foreground ring-status-warn/40",
  success: "bg-status-success/15 text-status-success-foreground ring-status-success/40",
  danger: "bg-status-danger/10 text-status-danger ring-status-danger/30",
  neutral: "bg-muted text-muted-foreground ring-border",
};

export function PipelineFlow({ steps }: { steps: PipelineStep[] }) {
  return (
    <div className="rounded-xl border bg-card p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="font-display text-sm font-semibold">Pipeline editorial</h2>
          <p className="text-xs text-muted-foreground">
            Da captura de tendencias ate metricas — todos os passos mockados.
          </p>
        </div>
      </div>
      <div className="flex snap-x gap-2 overflow-x-auto pb-1">
        {steps.map((s, idx) => {
          const Icon = iconMap[s.key as keyof typeof iconMap] ?? Radar;
          return (
            <div key={s.key} className="flex items-stretch">
              <Link
                to={s.to}
                className={cn(
                  "group flex min-w-[140px] snap-start flex-col gap-1 rounded-lg px-3 py-2.5 ring-1 transition-transform hover:-translate-y-0.5",
                  toneRing[s.tone ?? "neutral"],
                )}
              >
                <div className="flex items-center gap-1.5">
                  <Icon className="h-3.5 w-3.5" />
                  <span className="text-[10px] font-semibold uppercase tracking-wider">
                    {s.label}
                  </span>
                </div>
                <div className="font-display text-2xl font-bold tabular-nums leading-none">
                  {s.count}
                </div>
                {s.hint ? (
                  <div className="text-[10px] text-current/80 opacity-75">{s.hint}</div>
                ) : null}
              </Link>
              {idx < steps.length - 1 && (
                <div className="flex items-center px-1 text-muted-foreground/50">
                  <ChevronRight className="h-4 w-4" />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
