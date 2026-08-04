import { useEffect, useState } from "react";
import { CheckSquare2, Loader2, Zap } from "lucide-react";
import type { Script } from "@/lib/mock-data";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export function CaptureScriptChoices({
  scripts,
  onOpenChange,
  onConfirm,
}: {
  scripts: Script[];
  onOpenChange: (open: boolean) => void;
  onConfirm: (selected: Script[]) => Promise<void> | void;
}) {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [confirming, setConfirming] = useState(false);
  const duration = scripts[0]?.formatoSugerido.match(/(10|15) segundos/i)?.[1] ?? "10";

  useEffect(() => {
    setSelectedIds(scripts.map((script) => script.id));
  }, [scripts]);

  function toggle(scriptId: string, checked: boolean) {
    setSelectedIds((current) =>
      checked
        ? Array.from(new Set([...current, scriptId]))
        : current.filter((id) => id !== scriptId),
    );
  }

  async function confirmSelection() {
    const selected = scripts.filter((script) => selectedIds.includes(script.id));
    if (!selected.length) return;
    setConfirming(true);
    try {
      await onConfirm(selected);
    } finally {
      setConfirming(false);
    }
  }

  return (
    <Dialog open={scripts.length > 0} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-status-info" /> Escolha quais hooks de {duration}s produzir
          </DialogTitle>
          <p className="text-sm text-muted-foreground">
            Os três roteiros estão abaixo. Marque um, dois ou os três para seguir para produção.
          </p>
        </DialogHeader>
        <div className="grid gap-3 md:grid-cols-3">
          {scripts.map((script, index) => (
            <article
              key={script.id}
              className={`flex cursor-pointer flex-col rounded-xl border p-4 transition-colors ${
                selectedIds.includes(script.id)
                  ? "border-status-info bg-status-info/5"
                  : "hover:border-status-info/40"
              }`}
              onClick={() => toggle(script.id, !selectedIds.includes(script.id))}
            >
              <div className="mb-3 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Checkbox
                    checked={selectedIds.includes(script.id)}
                    onCheckedChange={(checked) => toggle(script.id, checked === true)}
                    onClick={(event) => event.stopPropagation()}
                    aria-label={`Selecionar teste ${index + 1}`}
                  />
                  <Badge variant="outline">Teste {index + 1}</Badge>
                </div>
                <span className="text-xs text-muted-foreground">
                  {script.textoFalado?.trim().split(/\s+/).length ?? 0} palavras
                </span>
              </div>
              <h3 className="text-sm font-semibold">{script.titulo}</h3>
              <p className="mt-2 flex-1 text-sm leading-relaxed">“{script.textoFalado}”</p>
            </article>
          ))}
        </div>
        <DialogFooter>
          <Button
            onClick={() => void confirmSelection()}
            disabled={confirming || selectedIds.length === 0}
          >
            {confirming ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <CheckSquare2 className="mr-2 h-4 w-4" />
            )}
            Continuar com {selectedIds.length} {selectedIds.length === 1 ? "roteiro" : "roteiros"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
