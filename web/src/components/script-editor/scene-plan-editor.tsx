import { useEffect, useState, type ReactNode } from "react";
import { Plus, Sparkles, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { avatarSetRoleLabel } from "@/components/script-editor/editor-options";
import { Button } from "@/components/ui/button";
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
import {
  generateSceneDirection,
  saveScenePlan,
  type AvatarSetRole,
  type ScenePlan,
} from "@/lib/api/local";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      {children}
    </div>
  );
}

type EditableScene = {
  id: string;
  text: string;
  lookRole: AvatarSetRole;
  estimatedStart: number;
  estimatedEnd: number;
};

function resolveSceneRole(
  requestedRole: AvatarSetRole,
  index: number,
  availableRoles: AvatarSetRole[],
): AvatarSetRole {
  return (
    (availableRoles.includes(requestedRole)
      ? requestedRole
      : availableRoles[index % Math.max(availableRoles.length, 1)]) || "primary"
  );
}

function defaultSceneDraft(text: string, roles: AvatarSetRole[]): EditableScene[] {
  const clean = text.replace(/\s+/g, " ").trim();
  const sentences =
    clean
      .match(/[^.!?…]+[.!?…]*/g)
      ?.map((sentence) => sentence.trim())
      .filter(Boolean) || [];
  if (roles.length < 2 || !clean) {
    return [
      {
        id: "scene-1",
        text: clean,
        lookRole: roles[0] || "primary",
        estimatedStart: 0,
        estimatedEnd: 0,
      },
    ];
  }
  const splitAt = Math.max(1, Math.ceil(sentences.length / 2));
  const first = sentences.slice(0, splitAt).join(" ").trim();
  const second =
    sentences.slice(splitAt).join(" ").trim() || clean.slice(Math.ceil(clean.length / 2));
  return [
    { id: "scene-1", text: first, lookRole: roles[0], estimatedStart: 0, estimatedEnd: 0 },
    { id: "scene-2", text: second, lookRole: roles[1], estimatedStart: 0, estimatedEnd: 0 },
  ];
}

function coerceToTwoSceneDraft(
  suggestions: Array<{ text: string; lookRole: AvatarSetRole }>,
  roles: AvatarSetRole[],
  fallbackText: string,
): EditableScene[] {
  const source = suggestions.length
    ? suggestions
    : defaultSceneDraft(fallbackText, roles).map((scene) => ({
        text: scene.text,
        lookRole: scene.lookRole,
      }));
  const firstText = source[0]?.text || "";
  const secondText = source
    .slice(1)
    .map((scene) => scene.text)
    .join(" ")
    .trim();
  const fallback = defaultSceneDraft(
    source
      .map((scene) => scene.text)
      .join(" ")
      .trim() || fallbackText,
    roles,
  );
  return [
    {
      id: "scene-1",
      text: firstText || fallback[0]?.text || "",
      lookRole: resolveSceneRole(source[0]?.lookRole || roles[0] || "primary", 0, roles),
      estimatedStart: 0,
      estimatedEnd: 0,
    },
    {
      id: "scene-2",
      text: secondText || fallback[1]?.text || "",
      lookRole: resolveSceneRole(
        source[1]?.lookRole || roles[1] || roles[0] || "primary",
        1,
        roles,
      ),
      estimatedStart: 0,
      estimatedEnd: 0,
    },
  ];
}

function scenePlanToEditableScenes(plan: ScenePlan, roles: AvatarSetRole[]): EditableScene[] {
  return plan.scenes.map((scene, index) => ({
    id: scene.id,
    text: scene.text,
    lookRole: resolveSceneRole(scene.lookRole, index, roles),
    estimatedStart: scene.estimatedStart,
    estimatedEnd: scene.estimatedEnd,
  }));
}

export function ScenePlanEditor({
  scriptId,
  loading,
  plan,
  fallbackText,
  displayText,
  spokenText,
  durationSeconds,
  performancePlan,
  availableRoles,
  transitionSlideGenerating = false,
  onSaved,
  onGenerateTransitionSlides,
}: {
  scriptId: string;
  loading: boolean;
  plan: ScenePlan | null;
  fallbackText: string;
  displayText: string;
  spokenText: string;
  durationSeconds: 10 | 15 | 30 | 45 | 60;
  performancePlan: {
    tone: string;
    pace: string;
    emotion: string;
    recommendedVoiceSpeed: number;
  } | null;
  availableRoles: AvatarSetRole[];
  transitionSlideGenerating?: boolean;
  onSaved: (plan: ScenePlan) => void;
  onGenerateTransitionSlides?: (plan: ScenePlan) => Promise<void>;
}) {
  const [scenes, setScenes] = useState<EditableScene[]>([]);
  const [saving, setSaving] = useState(false);
  const [directing, setDirecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [directionNotice, setDirectionNotice] = useState<string | null>(null);

  useEffect(() => {
    if (loading) return;
    setScenes(
      plan
        ? scenePlanToEditableScenes(plan, availableRoles)
        : defaultSceneDraft(fallbackText, availableRoles),
    );
    setError(null);
  }, [availableRoles, fallbackText, loading, plan]);

  function updateScene(index: number, patch: Partial<EditableScene>) {
    setScenes((current) =>
      current.map((scene, sceneIndex) => (sceneIndex === index ? { ...scene, ...patch } : scene)),
    );
  }

  function addScene() {
    const role = availableRoles[scenes.length % Math.max(availableRoles.length, 1)] || "primary";
    setScenes((current) => [
      ...current,
      {
        id: `scene-${current.length + 1}`,
        text: "",
        lookRole: role,
        estimatedStart: 0,
        estimatedEnd: 0,
      },
    ]);
  }

  function useTwoScenes() {
    const mergedText = scenes
      .map((scene) => scene.text)
      .join(" ")
      .replace(/\s+/g, " ")
      .trim();
    setScenes(defaultSceneDraft(mergedText || fallbackText, availableRoles));
    setDirectionNotice("Plano reorganizado em 2 cenas. Revise os textos e salve.");
    setError(null);
  }

  async function requestDirection() {
    setDirecting(true);
    setError(null);
    setDirectionNotice(null);
    try {
      const result = await generateSceneDirection(scriptId, {
        displayText,
        spokenText,
        durationSeconds,
        tone: performancePlan?.tone,
        pace: performancePlan?.pace,
        emotion: performancePlan?.emotion,
      });
      const nextScenes =
        availableRoles.length >= 2
          ? coerceToTwoSceneDraft(result.scenes, availableRoles, displayText || fallbackText)
          : result.scenes.map((scene, index) => ({
              id: `scene-${index + 1}`,
              text: scene.text,
              lookRole: resolveSceneRole(scene.lookRole, index, availableRoles),
              estimatedStart: 0,
              estimatedEnd: 0,
            }));
      setScenes(nextScenes);
      setDirectionNotice(
        availableRoles.length >= 2
          ? "Claude sugeriu uma divisão e o app manteve em 2 cenas, para preservar um único corte de look."
          : "Claude sugeriu uma divisão. Revise e salve o plano quando estiver de acordo.",
      );
    } catch (directionError) {
      setError(
        directionError instanceof Error
          ? directionError.message
          : "Nao foi possivel gerar direção com Claude.",
      );
    } finally {
      setDirecting(false);
    }
  }

  function validateScenes(targetScenes = scenes) {
    if (targetScenes.some((scene) => !scene.text.trim())) {
      return "Cada cena precisa ter um texto falado.";
    }
    if (
      availableRoles.length >= 2 &&
      new Set(targetScenes.map((scene) => scene.lookRole)).size < 2
    ) {
      return "Use pelo menos duas posições diferentes quando o Avatar Set estiver ativo.";
    }
    return null;
  }

  async function persistScenes(showToast = true, targetScenes = scenes) {
    const validationError = validateScenes(targetScenes);
    if (validationError) {
      setError(validationError);
      return null;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await saveScenePlan(scriptId, targetScenes);
      onSaved(saved);
      setScenes(scenePlanToEditableScenes(saved, availableRoles));
      if (showToast) toast.success("Scene Plan salvo.");
      return saved;
    } catch (saveError) {
      setError(
        saveError instanceof Error ? saveError.message : "Nao foi possivel salvar o Scene Plan.",
      );
      return null;
    } finally {
      setSaving(false);
    }
  }

  async function save() {
    await persistScenes(true);
  }

  async function generateTransitionSlides() {
    if (!onGenerateTransitionSlides) return;
    const saved = await persistScenes(false);
    if (!saved) return;
    setDirectionNotice(null);
    setError(null);
    try {
      await onGenerateTransitionSlides(saved);
      setDirectionNotice(
        saved.scenes.length > 2
          ? "Claude gerou os slides de transição. Revise a Direção visual dos apoios abaixo."
          : "Claude gerou o slide de transição. Revise a Direção visual dos apoios abaixo.",
      );
    } catch {
      setError("Nao foi possivel gerar o slide de transição com Claude.");
    }
  }

  async function organizeEverythingWithClaude() {
    setDirecting(true);
    setError(null);
    setDirectionNotice(null);
    try {
      const result = await generateSceneDirection(scriptId, {
        displayText,
        spokenText,
        durationSeconds,
        tone: performancePlan?.tone,
        pace: performancePlan?.pace,
        emotion: performancePlan?.emotion,
      });
      const nextScenes =
        availableRoles.length >= 2
          ? coerceToTwoSceneDraft(result.scenes, availableRoles, displayText || fallbackText)
          : result.scenes.map((scene, index) => ({
              id: `scene-${index + 1}`,
              text: scene.text,
              lookRole: resolveSceneRole(scene.lookRole, index, availableRoles),
              estimatedStart: 0,
              estimatedEnd: 0,
            }));
      const saved = await persistScenes(false, nextScenes);
      if (!saved) return;
      if (onGenerateTransitionSlides && saved.scenes.length > 1) {
        await onGenerateTransitionSlides(saved);
      }
      setDirectionNotice(
        saved.scenes.length > 1
          ? "Claude organizou as cenas, salvou o plano e preparou o slide de transição."
          : "Claude organizou e salvou o plano de cenas.",
      );
    } catch (directionError) {
      setError(
        directionError instanceof Error
          ? directionError.message
          : "Nao foi possivel organizar com Claude.",
      );
    } finally {
      setDirecting(false);
    }
  }

  return (
    <div className="space-y-3 rounded-lg border bg-muted/20 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h4 className="text-xs font-semibold">Claude organiza o vídeo</h4>
          <p className="mt-0.5 text-[11px] leading-4 text-muted-foreground">
            Você escolhe duração e avatar. O Claude divide a fala, alterna os looks e cria o slide
            entre as cenas.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={() => void organizeEverythingWithClaude()}
            disabled={loading || directing || transitionSlideGenerating}
          >
            <Sparkles className="h-3.5 w-3.5" />{" "}
            {directing || transitionSlideGenerating
              ? "Claude organizando..."
              : "Fazer tudo com Claude"}
          </Button>
          {scenes.length !== 2 && availableRoles.length >= 2 ? (
            <Button type="button" size="sm" variant="outline" onClick={useTwoScenes}>
              Usar 2 cenas
            </Button>
          ) : null}
          <Button type="button" size="sm" variant="outline" onClick={addScene}>
            <Plus className="h-3.5 w-3.5" /> Adicionar cena
          </Button>
        </div>
      </div>
      <div className="rounded-lg border border-status-info/30 bg-status-info/5 px-3 py-2 text-[11px] leading-4 text-muted-foreground">
        <span className="font-semibold text-foreground">Fluxo automático:</span> 2 cenas com
        posições diferentes, 1 slide de transição renderizado e checklist final antes de enviar ao
        HeyGen.
      </div>
      {loading ? (
        <p className="text-xs text-muted-foreground">Carregando Scene Plan...</p>
      ) : (
        <div className="space-y-2">
          {scenes.map((scene, index) => (
            <div key={scene.id} className="space-y-2">
              <div className="rounded-lg border bg-background p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold">Cena {index + 1}</span>
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    onClick={() =>
                      setScenes((current) =>
                        current.filter((_, sceneIndex) => sceneIndex !== index),
                      )
                    }
                    disabled={scenes.length <= 1}
                    aria-label={`Remover cena ${index + 1}`}
                  >
                    <Trash2 className="h-4 w-4 text-status-danger" />
                  </Button>
                </div>
                <div className="grid gap-2 md:grid-cols-[1fr_180px]">
                  <Textarea
                    value={scene.text}
                    onChange={(event) => updateScene(index, { text: event.target.value })}
                    rows={3}
                    placeholder="Texto falado nesta cena"
                  />
                  <div className="space-y-2">
                    <Field label="Posição">
                      <Select
                        value={scene.lookRole}
                        onValueChange={(value) =>
                          updateScene(index, { lookRole: value as AvatarSetRole })
                        }
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {availableRoles.map((role) => (
                            <SelectItem key={role} value={role}>
                              {avatarSetRoleLabel(role)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </Field>
                    <div className="grid grid-cols-2 gap-2">
                      <Input
                        type="number"
                        min={0}
                        step={0.1}
                        value={scene.estimatedStart}
                        onChange={(event) =>
                          updateScene(index, { estimatedStart: Number(event.target.value) || 0 })
                        }
                        aria-label="Início estimado"
                        placeholder="Início"
                      />
                      <Input
                        type="number"
                        min={0}
                        step={0.1}
                        value={scene.estimatedEnd}
                        onChange={(event) =>
                          updateScene(index, { estimatedEnd: Number(event.target.value) || 0 })
                        }
                        aria-label="Fim estimado"
                        placeholder="Fim"
                      />
                    </div>
                  </div>
                </div>
              </div>
              {index < scenes.length - 1 ? (
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-status-info/30 bg-status-info/5 px-3 py-2">
                  <div>
                    <div className="text-xs font-semibold text-status-info">
                      Transição Cena {index + 1} → Cena {index + 2}
                    </div>
                    <p className="mt-0.5 text-[11px] leading-4 text-muted-foreground">
                      O Claude cria este slide para aparecer durante a fala, antes do próximo look
                      entrar.
                    </p>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    onClick={() => void generateTransitionSlides()}
                    disabled={saving || transitionSlideGenerating || !onGenerateTransitionSlides}
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    {transitionSlideGenerating ? "Claude gerando..." : "Gerar slide de transição"}
                  </Button>
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}
      {directionNotice ? (
        <p className="rounded-md border border-status-info/30 bg-status-info/5 px-3 py-2 text-xs text-status-info">
          {directionNotice}
        </p>
      ) : null}
      {error ? (
        <p className="rounded-md border border-status-danger/30 bg-status-danger/5 px-3 py-2 text-xs text-status-danger">
          {error}
        </p>
      ) : null}
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] text-muted-foreground">
          Use o salvamento manual só se você editou alguma cena depois do Claude.
        </p>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => void save()}
          disabled={loading || saving || scenes.length === 0}
        >
          {saving ? "Salvando..." : "Salvar ajuste manual"}
        </Button>
      </div>
    </div>
  );
}
