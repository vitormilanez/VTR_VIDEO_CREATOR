// Escolha do "Tom editorial" antes da geracao paga do roteiro com IA.
// Chamado de tela em tela, nunca de "Humor" — o tom nao autoriza inventar
// risco: ele so muda o enquadramento de uma evidencia que ja existe.
import { Loader2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { EditorialTone } from "@/lib/mock-data";
import type { DurationPreset } from "@/lib/script-editor";

const TONE_OPTIONS: Array<{ value: EditorialTone; label: string; description: string }> = [
  {
    value: "positivo",
    label: "Positivo",
    description: "Leitura otimista e construtiva. Destaca oportunidades sem prometer resultado.",
  },
  {
    value: "neutro",
    label: "Neutro",
    description: "Linguagem jornalística: achado, números, contexto e limitações.",
  },
  {
    value: "apreensivo",
    label: "Apreensivo",
    description: "Atenção a riscos e incertezas reais do estudo, sem alarmismo.",
  },
];

const DURATIONS: DurationPreset[] = [10, 15, 30, 45, 60, 90, 120, 180];

export function ToneSelectDialog({
  open,
  onOpenChange,
  ideaTitle,
  tone,
  onToneChange,
  durationSeconds,
  onDurationChange,
  outro,
  onOutroChange,
  isGenerating,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  ideaTitle: string;
  tone: EditorialTone;
  onToneChange: (tone: EditorialTone) => void;
  durationSeconds: DurationPreset;
  onDurationChange: (value: DurationPreset) => void;
  outro: string;
  onOutroChange: (value: string) => void;
  isGenerating: boolean;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={(next) => !isGenerating && onOpenChange(next)}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Escolha o tom editorial</DialogTitle>
          <p className="text-sm text-muted-foreground">
            <span className="font-medium text-foreground">&ldquo;{ideaTitle}&rdquo;</span> — o tom
            define como a IA vai escrever o texto falado. Essa escolha acontece antes da geração
            paga, em uma única chamada
            {durationSeconds <= 15 ? " que cria três alternativas." : "."}
          </p>
        </DialogHeader>

        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label className="text-xs">Tom editorial</Label>
            <ToggleGroup
              type="single"
              value={tone}
              onValueChange={(value) => value && onToneChange(value as EditorialTone)}
              className="grid grid-cols-1 gap-2 sm:grid-cols-3"
            >
              {TONE_OPTIONS.map((option) => (
                <ToggleGroupItem
                  key={option.value}
                  value={option.value}
                  className="h-auto flex-col items-start gap-1 whitespace-normal rounded-lg border p-3 text-left data-[state=on]:border-status-info data-[state=on]:bg-status-info/10"
                >
                  <span className="text-sm font-semibold">{option.label}</span>
                  <span className="text-xs font-normal text-muted-foreground">
                    {option.description}
                  </span>
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </div>

          <div className="grid gap-2">
            <Label className="text-xs">Duração alvo</Label>
            <ToggleGroup
              type="single"
              value={String(durationSeconds)}
              onValueChange={(value) => value && onDurationChange(Number(value) as DurationPreset)}
              className="justify-start"
            >
              {DURATIONS.map((seconds) => (
                <ToggleGroupItem key={seconds} value={String(seconds)} className="text-xs">
                  {seconds}s
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </div>

          {durationSeconds > 60 ? (
            <div className="rounded-md border border-status-info/30 bg-status-info/5 px-3 py-2 text-xs text-muted-foreground">
              Vídeos longos serão produzidos depois pelo Avatar Set de duas câmeras, em tomadas
              separadas e com corte seco.
            </div>
          ) : null}

          {durationSeconds === 10 ? (
            <div className="rounded-md border border-status-info/30 bg-status-info/5 px-3 py-2 text-xs text-muted-foreground">
              Vídeos de 10 segundos terminam diretamente no impacto, sem frase final.
            </div>
          ) : (
            <div className="grid gap-2">
              <Label className="text-xs">Frase final do vídeo</Label>
              <Textarea
                rows={2}
                value={outro}
                onChange={(event) => onOutroChange(event.target.value)}
              />
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={isGenerating}>
            Cancelar
          </Button>
          <Button
            onClick={onConfirm}
            disabled={isGenerating || (durationSeconds !== 10 && !outro.trim())}
          >
            {isGenerating ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="mr-2 h-4 w-4" />
            )}
            {durationSeconds <= 15 ? "Gerar 3 roteiros" : "Gerar um roteiro"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
