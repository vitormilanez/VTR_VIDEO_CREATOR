import { CircleAlert } from "lucide-react";
import type { Prioridade } from "@/lib/mock-data";
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const priorityDotClass: Record<Prioridade, string> = {
  alta: "bg-status-danger ring-status-danger/25",
  media: "bg-status-warn ring-status-warn/30",
  baixa: "bg-status-success ring-status-success/25",
};

const priorityDescription: Record<Prioridade, string> = {
  alta: "Prioridade alta — conteúdo importante para a próxima etapa da produção.",
  media: "Prioridade média — conteúdo relevante, sem urgência imediata.",
  baixa: "Prioridade baixa — conteúdo que pode aguardar na fila editorial.",
};

export function EditorialSignals({
  priority,
  note,
  noteLabel,
}: {
  priority: Prioridade;
  note?: string;
  noteLabel: string;
}) {
  return (
    <TooltipProvider delayDuration={180}>
      <div className="flex items-center justify-center gap-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              aria-label={priorityDescription[priority]}
              className="inline-flex h-9 w-9 cursor-help items-center justify-center rounded-md transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span
                aria-hidden="true"
                className={cn("h-3 w-3 rounded-full ring-4", priorityDotClass[priority])}
              />
            </button>
          </TooltipTrigger>
          <TooltipContent className="max-w-xs border bg-popover p-3 text-left leading-5 text-popover-foreground shadow-lg">
            {priorityDescription[priority]}
          </TooltipContent>
        </Tooltip>
        {note ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                aria-label={`Ver ${noteLabel.toLowerCase()}`}
                className="inline-flex h-9 w-9 cursor-help items-center justify-center rounded-md text-status-warn-foreground transition-colors hover:bg-status-warn/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <CircleAlert className="h-4 w-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent className="max-w-sm border bg-popover p-3 text-left text-popover-foreground shadow-lg">
              <div className="mb-1 text-xs font-semibold">{noteLabel}</div>
              <p className="text-xs leading-5 text-muted-foreground">{note}</p>
            </TooltipContent>
          </Tooltip>
        ) : null}
      </div>
    </TooltipProvider>
  );
}
