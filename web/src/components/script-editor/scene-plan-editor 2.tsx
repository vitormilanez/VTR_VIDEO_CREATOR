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
  type ClaudeSceneModel,
  type AvatarSetRole,
  type SceneDirectionResult,
  type ScenePlan,
  type SceneTransitionStyle,
} from "@/lib/api/local";
import type { DurationPreset } from "@/lib/script-editor";

const TRANSITION_OPTIONS: Array<{
  value: SceneTransitionStyle;
  label: string;
  description: string;
}> = [
  {
    value: "hard_cut",
    label: "Corte seco",
    description: "Troca imediata para preservar a voz e não misturar as tomadas.",
  },
];

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

function suggestionsToSceneDraft(
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
  return source.map((scene, index) => ({
    id: `scene-${index + 1}`,
    text: scene.text,
    lookRole: resolveSceneRole(
      scene.lookRole || roles[index % Math.max(roles.length, 1)] || "primary",
      index,
      roles,
    ),
    estimatedStart: 0,
    estimatedEnd: 0,
  }));
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
  onSaved,
  onApplyClaudePlan,
}: {
  scriptId: string;
  loading: boolean;
  plan: ScenePlan | null;
  fallbackText: string;
  displayText: string;
  spokenText: string;
  durationSeconds: DurationPreset;
  performancePlan: {
    tone: string;
    pace: string;
    emotion: string;
    recommendedVoiceSpeed: number;
  } | null;
  availableRoles: AvatarSetRole[];
  onSaved: (plan: ScenePlan) => void;
  onApplyClaudePlan?: (input: {
    adjustedScript: string;
    scenes: EditableScene[];
    transitionStyle: SceneTransitionStyle;
  }) => Promise<ScenePlan>;
}) {
  const [scenes, setScenes] = useState<EditableScene[]>([]);
  const [transitionStyle, setTransitionStyle] = useState<SceneTransitionStyle>("hard_cut");
  const [modelTier, setModelTier] = useState<ClaudeSceneModel>("haiku");
  const [claudeProposal, setClaudeProposal] = useState<SceneDirectionResult | null>(null);
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
    setTransitionStyle(plan?.transitionStyle || "hard_cut");
    setError(null);
    setClaudeProposal(null);
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
        modelTier,
      });
      const nextScenes = suggestionsToSceneDraft(
        result.scenes,
        availableRoles,
        displayText || fallbackText,
      );
      setScenes(nextScenes);
      setClaudeProposal(result);
      const fallbackNotice = result.fallbackUsed
        ? ` O modelo Sonnet configurado não estava disponível; foi usado ${result.model}.`
        : "";
      setDirectionNotice(
        `${result.modelTier === "sonnet" ? "Claude Sonnet" : "Claude Haiku"} ajustou o roteiro e sugeriu ${nextScenes.length} tomadas. Revise antes de aplicar.${fallbackNotice}`,
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
    const selectedRoleCount = new Set(targetScenes.map((scene) => scene.lookRole)).size;
    if (availableRoles.length >= 2 && selectedRoleCount !== 2) {
      return "O modo duas câmeras usa exatamente duas posições diferentes do Avatar Set.";
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
      const saved = await saveScenePlan(scriptId, targetScenes, transitionStyle);
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

  async function applyClaudeProposal() {
    if (!claudeProposal) return;
    if (!onApplyClaudePlan) {
      await persistScenes(true, scenes);
      return;
    }
    const validationError = validateScenes(scenes);
    if (validationError) {
      setError(validationError);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await onApplyClaudePlan({
        adjustedScript: claudeProposal.adjustedScript,
        scenes,
        transitionStyle,
      });
      onSaved(saved);
      setScenes(scenePlanToEditableScenes(saved, availableRoles));
      setClaudeProposal(null);
      setDirectionNotice(
        "Roteiro ajustado e cortes salvos. O vídeo usará somente as duas câmeras escolhidas.",
      );
      toast.success("Roteiro e Scene Plan aplicados.");
    } catch (applyError) {
      setError(
        applyError instanceof Error
          ? applyError.message
          : "Nao foi possivel aplicar o plano do Claude.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-3 rounded-lg border bg-muted/20 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h4 className="text-xs font-semibold">Direção multicâmera do Claude</h4>
          <p className="mt-0.5 text-[11px] leading-4 text-muted-foreground">
            O Claude simplifica o roteiro médico, preserva os números necessários e propõe cortes
            entre duas câmeras sem inserir cartela, música ou encerramento no meio do vídeo.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Select
            value={modelTier}
            onValueChange={(value) => setModelTier(value as ClaudeSceneModel)}
          >
            <SelectTrigger className="h-8 w-36 bg-background text-xs" aria-label="Modelo do Claude">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="haiku">Claude Haiku</SelectItem>
              <SelectItem value="sonnet">Claude Sonnet</SelectItem>
            </SelectContent>
          </Select>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={() => void requestDirection()}
            disabled={loading || directing}
          >
            <Sparkles className="h-3.5 w-3.5" />{" "}
            {directing ? "Claude revisando..." : "Revisar com Claude"}
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
        <span className="font-semibold text-foreground">Fluxo protegido:</span> cada tomada é gerada
        separadamente no HeyGen, com o look fixo, a mesma voz e corte seco. Nenhuma cartela, b-roll
        ou trilha entra entre as câmeras.
      </div>
      {scenes.length > 1 ? (
        <fieldset className="space-y-2">
          <legend className="text-xs font-semibold">Transição entre as cenas</legend>
          <div className="grid gap-2" role="radiogroup" aria-label="Transição entre as cenas">
            {TRANSITION_OPTIONS.map((option) => {
              const selected = transitionStyle === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => setTransitionStyle(option.value)}
                  className={`rounded-lg border px-3 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ${
                    selected
                      ? "border-primary bg-primary/5 shadow-sm"
                      : "bg-background hover:border-primary/40"
                  }`}
                >
                  <span className="block text-xs font-semibold">{option.label}</span>
                  <span className="mt-1 block text-[11px] leading-4 text-muted-foreground">
                    {option.description}
                  </span>
                </button>
              );
            })}
          </div>
        </fieldset>
      ) : null}
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
                <div className="rounded-lg border border-dashed bg-muted/30 px-3 py-2">
                  <div>
                    <div className="text-xs font-semibold">
                      Transição Cena {index + 1} → Cena {index + 2}
                    </div>
                    <p className="mt-0.5 text-[11px] leading-4 text-muted-foreground">
                      {TRANSITION_OPTIONS.find((option) => option.value === transitionStyle)?.label}
                      : troca direta de look, sem slide intermediário.
                    </p>
                  </div>
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
      {claudeProposal ? (
        <div className="space-y-3 rounded-lg border border-primary/30 bg-primary/5 p-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <h5 className="text-xs font-semibold">Proposta do Claude</h5>
              <p className="mt-0.5 text-[11px] leading-4 text-muted-foreground">
                Revise a fala e os cortes. Aplicar salva o roteiro ajustado antes do Scene Plan.
              </p>
            </div>
            <Button
              type="button"
              size="sm"
              onClick={() => void applyClaudeProposal()}
              disabled={saving}
            >
              {saving ? "Aplicando..." : "Aplicar roteiro e cortes"}
            </Button>
          </div>
          {claudeProposal.scriptChanges.length ? (
            <ul className="space-y-1 text-[11px] text-muted-foreground">
              {claudeProposal.scriptChanges.map((change, index) => (
                <li key={`${index}-${change}`}>• {change}</li>
              ))}
            </ul>
          ) : null}
          <Textarea
            aria-label="Roteiro ajustado pelo Claude"
            value={claudeProposal.adjustedScript}
            readOnly
            rows={5}
            className="bg-background text-xs leading-5"
          />
        </div>
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
