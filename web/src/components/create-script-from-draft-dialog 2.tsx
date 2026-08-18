import { useState, type ComponentProps, type FormEvent } from "react";
import { useNavigate } from "@tanstack/react-router";
import { FilePenLine, Loader2, ShieldCheck, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { createScriptFromDraft } from "@/lib/api/local";
import type { DurationPreset } from "@/lib/script-editor";
import type { EditorialTone, ThemeFamily } from "@/lib/mock-data";
import { useStore } from "@/lib/store";

const DURATION_OPTIONS: DurationPreset[] = [10, 15, 30, 45, 60, 90, 120, 180];

const FAMILY_OPTIONS: Array<{ value: ThemeFamily; label: string }> = [
  { value: "educativo", label: "Educativo" },
  { value: "medicamento", label: "Medicamento" },
  { value: "comportamento", label: "Comportamento" },
  { value: "metabolismo", label: "Metabolismo" },
  { value: "obesidade", label: "Obesidade" },
];

const TONE_OPTIONS: Array<{ value: EditorialTone; label: string }> = [
  { value: "neutro", label: "Neutro" },
  { value: "positivo", label: "Positivo" },
  { value: "apreensivo", label: "Apreensivo" },
];

export function CreateScriptFromDraftDialog({
  triggerVariant = "default",
}: {
  triggerVariant?: ComponentProps<typeof Button>["variant"];
}) {
  const navigate = useNavigate();
  const addScript = useStore((state) => state.addScript);
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [draftText, setDraftText] = useState("");
  const [familia, setFamilia] = useState<ThemeFamily>("educativo");
  const [editorialTone, setEditorialTone] = useState<EditorialTone>("neutro");
  const [durationSeconds, setDurationSeconds] = useState<DurationPreset>(45);
  const [isCreating, setIsCreating] = useState(false);

  const cleanDraft = draftText.trim();
  const wordCount = cleanDraft ? cleanDraft.split(/\s+/).length : 0;

  function resetForm() {
    setTitle("");
    setDraftText("");
    setFamilia("educativo");
    setEditorialTone("neutro");
    setDurationSeconds(45);
  }

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (cleanDraft.length < 40 || isCreating) return;
    setIsCreating(true);
    try {
      const result = await createScriptFromDraft({
        draftText: cleanDraft,
        title: title.trim(),
        familia,
        editorialTone,
        durationSeconds,
      });
      addScript(result.script);
      setOpen(false);
      resetForm();
      toast.success(
        `Roteiro revisado e ${result.scenePlan.scenes.length} ${result.scenePlan.scenes.length === 1 ? "cena criada" : "cenas criadas"}.`,
      );
      navigate({ to: "/roteiros/$id", params: { id: result.script.id } });
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Não foi possível revisar o texto e criar as cenas.",
      );
    } finally {
      setIsCreating(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !isCreating && setOpen(nextOpen)}>
      <DialogTrigger asChild>
        <Button size="sm" variant={triggerVariant}>
          <FilePenLine className="mr-1 h-4 w-4" /> Novo roteiro
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader className="pr-8">
          <DialogTitle>Criar roteiro a partir do seu texto</DialogTitle>
          <DialogDescription>
            Cole o rascunho. O Claude revisa conforme o Perfil Editorial do Dr. Guilherme e divide a
            fala em cenas editáveis. Nenhum vídeo será gerado nesta etapa.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={create} className="space-y-5" aria-busy={isCreating}>
          <div className="space-y-2">
            <Label htmlFor="draft-script-title">Título (opcional)</Label>
            <Input
              id="draft-script-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="O Claude pode sugerir um título se você deixar em branco"
              maxLength={300}
              disabled={isCreating}
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-end justify-between gap-3">
              <Label htmlFor="draft-script-text">Texto do roteiro</Label>
              <span className="text-xs tabular-nums text-muted-foreground">
                {wordCount} palavras · {cleanDraft.length}/6000 caracteres
              </span>
            </div>
            <Textarea
              id="draft-script-text"
              value={draftText}
              onChange={(event) => setDraftText(event.target.value)}
              placeholder="Cole aqui sua ideia, rascunho ou fala completa. Inclua no texto os dados e as fontes que precisam ser preservados."
              rows={5}
              maxLength={6000}
              autoFocus
              disabled={isCreating}
              className="resize-y leading-6"
              aria-describedby="draft-script-help"
            />
            <p id="draft-script-help" className="text-xs leading-5 text-muted-foreground">
              O Claude não deve inventar evidências. Quando o texto não trouxer sustentação para uma
              afirmação clínica, a revisão reduz a certeza e sinaliza o ponto para validação médica.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="draft-script-family">Família</Label>
              <Select
                value={familia}
                onValueChange={(value) => setFamilia(value as ThemeFamily)}
                disabled={isCreating}
              >
                <SelectTrigger id="draft-script-family" aria-label="Família do roteiro">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {FAMILY_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="draft-script-duration">Duração alvo</Label>
              <Select
                value={String(durationSeconds)}
                onValueChange={(value) => setDurationSeconds(Number(value) as DurationPreset)}
                disabled={isCreating}
              >
                <SelectTrigger id="draft-script-duration" aria-label="Duração alvo">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DURATION_OPTIONS.map((seconds) => (
                    <SelectItem key={seconds} value={String(seconds)}>
                      {seconds} segundos
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="draft-script-tone">Tom editorial</Label>
              <Select
                value={editorialTone}
                onValueChange={(value) => setEditorialTone(value as EditorialTone)}
                disabled={isCreating}
              >
                <SelectTrigger id="draft-script-tone" aria-label="Tom editorial">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TONE_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex items-start gap-2 rounded-lg border border-status-info/30 bg-status-info/5 px-3 py-2.5 text-xs leading-5 text-muted-foreground">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-status-info" />
            <span>
              A revisão remove CTAs comerciais, mantém Guilherme como médico e cria apenas os cortes
              de cena. Avatar, voz e geração do vídeo continuam no editor atual.
            </span>
          </div>

          <p className="sr-only" aria-live="polite">
            {isCreating ? "Claude revisando o texto e criando as cenas." : ""}
          </p>

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setOpen(false)}
              disabled={isCreating}
            >
              Cancelar
            </Button>
            <Button type="submit" disabled={cleanDraft.length < 40 || isCreating}>
              {isCreating ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="mr-2 h-4 w-4" />
              )}
              {isCreating ? "Revisando e criando cenas..." : "Revisar e criar cenas"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
