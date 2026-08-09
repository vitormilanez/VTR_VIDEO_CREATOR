import { useEffect, useState, type ReactNode } from "react";
import { Film, Sparkles } from "lucide-react";
import { toast } from "sonner";

import {
  VIDEO_VISUAL_LAYOUT_OPTIONS,
  VIDEO_VISUAL_TYPE_OPTIONS,
} from "@/components/script-editor/editor-options";
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
  generateVisualDirection,
  renderVideoSlides,
  saveVisualPlan,
  type ScenePlan,
  type VideoSlideRender,
  type VideoVisualLayout,
  type VideoVisualType,
  type VisualPlan,
} from "@/lib/api/local";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      {children}
    </div>
  );
}

export function VisualPlanDirector({
  scriptId,
  scenePlan,
  visualPlan,
  loading,
  displayText,
  spokenText,
  durationSeconds,
  performancePlan,
  onSaved,
  videoSlideRender,
  videoSlideRenderLoading,
  onRendered,
}: {
  scriptId: string;
  scenePlan: ScenePlan | null;
  visualPlan: VisualPlan | null;
  loading: boolean;
  displayText: string;
  spokenText: string;
  durationSeconds: 10 | 15 | 30 | 45 | 60;
  performancePlan: {
    tone: string;
    pace: string;
    emotion: string;
    recommendedVoiceSpeed: number;
  } | null;
  onSaved: (plan: VisualPlan) => void;
  videoSlideRender: VideoSlideRender | null;
  videoSlideRenderLoading: boolean;
  onRendered: (render: VideoSlideRender) => void;
}) {
  const [directing, setDirecting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [draftPlan, setDraftPlan] = useState<VisualPlan | null>(visualPlan);
  const [error, setError] = useState<string | null>(null);
  const requiredVisualCount = scenePlan ? Math.max(0, scenePlan.scenes.length - 1) : 0;

  useEffect(() => {
    setDraftPlan(visualPlan);
  }, [visualPlan]);

  async function requestVisualDirection() {
    if (!scenePlan) {
      setError("Salve o Scene Plan antes de pedir direção visual.");
      return;
    }
    setDirecting(true);
    setError(null);
    try {
      const result = await generateVisualDirection(scriptId, {
        displayText,
        spokenText,
        durationSeconds,
        tone: performancePlan?.tone,
        pace: performancePlan?.pace,
        emotion: performancePlan?.emotion,
      });
      onSaved(result.visualPlan);
      setDraftPlan(result.visualPlan);
      toast.success("Direção visual gerada pelo Claude.");
    } catch (visualError) {
      setError(
        visualError instanceof Error
          ? visualError.message
          : "Nao foi possivel gerar direção visual.",
      );
    } finally {
      setDirecting(false);
    }
  }

  function updateVisual(sceneId: string, patch: Partial<VisualPlan["scenes"][number]["visual"]>) {
    setDraftPlan((current) =>
      current
        ? {
            ...current,
            scenes: current.scenes.map((scene) =>
              scene.sceneId === sceneId
                ? { ...scene, visual: { ...scene.visual, ...patch } }
                : scene,
            ),
          }
        : current,
    );
  }

  async function save() {
    if (!draftPlan) return;
    setSaving(true);
    setError(null);
    try {
      const saved = await saveVisualPlan(scriptId, draftPlan);
      setDraftPlan(saved);
      onSaved(saved);
      toast.success("Direção visual salva.");
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? saveError.message
          : "Nao foi possivel salvar a direção visual.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function renderPreviews(): Promise<VideoSlideRender | null> {
    if (!draftPlan) {
      setError("Salve ou gere a direção visual antes de renderizar os previews.");
      return null;
    }
    setRendering(true);
    setError(null);
    try {
      const savedPlan = await saveVisualPlan(scriptId, draftPlan);
      setDraftPlan(savedPlan);
      onSaved(savedPlan);
      const rendered = await renderVideoSlides(scriptId);
      onRendered(rendered);
      toast.success(`${rendered.renderedCount} preview(s) 1080×1920 renderizado(s).`);
      return rendered;
    } catch (renderError) {
      setError(
        renderError instanceof Error
          ? renderError.message
          : "Nao foi possivel renderizar os previews.",
      );
      return null;
    } finally {
      setRendering(false);
    }
  }

  async function renderAndOpenSlide(sceneId: string) {
    const existing = videoSlideRender?.assets.find(
      (asset) => asset.sceneId === sceneId && asset.url,
    );
    if (existing?.url) {
      window.open(existing.url, "_blank", "noopener,noreferrer");
      return;
    }
    const rendered = await renderPreviews();
    const asset = rendered?.assets.find(
      (candidate) => candidate.sceneId === sceneId && candidate.url,
    );
    if (asset?.url) {
      window.open(asset.url, "_blank", "noopener,noreferrer");
    }
  }

  return (
    <div className="mt-3 space-y-3 rounded-lg border bg-muted/20 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h4 className="text-xs font-semibold">Direção visual dos apoios</h4>
          <p className="mt-0.5 text-[11px] leading-4 text-muted-foreground">
            Claude cria {requiredVisualCount} apoio(s) para entrar durante a fala antes dos cortes
            de look.
          </p>
        </div>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={() => void requestVisualDirection()}
          disabled={loading || directing || !scenePlan}
        >
          <Sparkles className="h-3.5 w-3.5" />{" "}
          {directing ? "Claude pensando..." : "Gerar direção visual com Claude"}
        </Button>
      </div>
      <p className="text-[11px] text-muted-foreground">
        Esta ação usa tokens Claude e salva uma direção estruturada, sem gerar imagens ou vídeo.
      </p>
      {loading ? (
        <p className="text-xs text-muted-foreground">Carregando direção visual...</p>
      ) : null}
      {draftPlan ? (
        <div className="space-y-2">
          {draftPlan.scenes.map((scene, index) => {
            const requiresVisual = index < requiredVisualCount;
            const closesOnAvatar = requiredVisualCount > 0 && index >= requiredVisualCount;
            const previewAsset = videoSlideRender?.assets.find(
              (asset) => asset.sceneId === scene.sceneId && asset.url,
            );
            return (
              <div key={scene.sceneId} className="rounded-md border bg-background p-3">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <span className="text-xs font-semibold">
                      {closesOnAvatar
                        ? `Cena ${index + 1}`
                        : `Transição Cena ${index + 1} → Cena ${index + 2}`}
                    </span>
                    {!closesOnAvatar ? (
                      <p className="mt-0.5 text-[11px] text-muted-foreground">
                        Entra durante a fala antes do próximo look.
                      </p>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-2">
                    {!closesOnAvatar && scene.visual.type !== "none" ? (
                      previewAsset?.url ? (
                        <Button type="button" size="sm" variant="outline" asChild>
                          <a href={previewAsset.url} target="_blank" rel="noreferrer">
                            <Film className="h-3.5 w-3.5" /> Ver slide
                          </a>
                        </Button>
                      ) : (
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => void renderAndOpenSlide(scene.sceneId)}
                          disabled={rendering || loading}
                        >
                          <Film className="h-3.5 w-3.5" />
                          {rendering ? "Renderizando..." : "Renderizar e ver slide"}
                        </Button>
                      )
                    ) : null}
                    <span className="rounded-full bg-muted px-2 py-1 text-[10px] font-medium uppercase">
                      {closesOnAvatar
                        ? "Fechamento no avatar"
                        : scene.visual.type === "none"
                          ? "Apoio obrigatório"
                          : "Slide de transição"}
                    </span>
                  </div>
                </div>
                <div className="grid gap-2 md:grid-cols-[180px_1fr]">
                  <div className="space-y-2">
                    <Field label="Tipo">
                      <Select
                        value={scene.visual.type}
                        disabled={closesOnAvatar}
                        onValueChange={(value) =>
                          updateVisual(scene.sceneId, {
                            type: value as VideoVisualType,
                            layout: value === "none" ? "" : scene.visual.layout || "big_statement",
                            headline: value === "none" ? "" : scene.visual.headline,
                            body: value === "none" ? "" : scene.visual.body,
                          })
                        }
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {VIDEO_VISUAL_TYPE_OPTIONS.filter(
                            (option) => !requiresVisual || option.value !== "none",
                          ).map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </Field>
                    {scene.visual.type !== "none" && !closesOnAvatar ? (
                      <Field label="Layout">
                        <Select
                          value={scene.visual.layout || "big_statement"}
                          onValueChange={(value) =>
                            updateVisual(scene.sceneId, { layout: value as VideoVisualLayout })
                          }
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {VIDEO_VISUAL_LAYOUT_OPTIONS.map((option) => (
                              <SelectItem key={option.value} value={option.value}>
                                {option.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </Field>
                    ) : null}
                  </div>
                  {closesOnAvatar ? (
                    <p className="flex items-center text-xs text-muted-foreground">
                      A última cena fica limpa para o próximo look fechar a fala.
                    </p>
                  ) : scene.visual.type === "none" ? (
                    <p className="flex items-center text-xs text-muted-foreground">
                      Esta cena precisa de um apoio visual antes do próximo corte de look.
                    </p>
                  ) : (
                    <div className="space-y-2">
                      <Input
                        value={scene.visual.headline}
                        onChange={(event) =>
                          updateVisual(scene.sceneId, { headline: event.target.value })
                        }
                        placeholder="Headline curta"
                      />
                      <Textarea
                        value={scene.visual.body}
                        onChange={(event) =>
                          updateVisual(scene.sceneId, { body: event.target.value })
                        }
                        rows={2}
                        placeholder="Body opcional — complemente a fala"
                      />
                      <Input
                        value={scene.visual.purpose}
                        onChange={(event) =>
                          updateVisual(scene.sceneId, { purpose: event.target.value })
                        }
                        placeholder="Objetivo editorial"
                      />
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : null}
      {draftPlan ? (
        <div className="flex justify-end">
          <Button type="button" size="sm" onClick={() => void save()} disabled={saving || loading}>
            {saving ? "Salvando..." : "Salvar direção visual"}
          </Button>
        </div>
      ) : null}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3">
        <div>
          <p className="text-xs font-semibold">Preview dos apoios</p>
          <p className="text-[11px] text-muted-foreground">
            Renderer local determinístico, sem Claude, HeyGen ou MP4.
          </p>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => void renderPreviews()}
          disabled={rendering || loading || !draftPlan}
        >
          <Film className="h-3.5 w-3.5" />{" "}
          {rendering ? "Renderizando..." : "Renderizar previews 1080×1920"}
        </Button>
      </div>
      {videoSlideRenderLoading ? (
        <p className="text-xs text-muted-foreground">Carregando previews...</p>
      ) : null}
      {videoSlideRender && videoSlideRender.assets.some((asset) => asset.url) ? (
        <div className="grid gap-2 sm:grid-cols-3">
          {videoSlideRender.assets
            .filter((asset) => asset.url)
            .map((asset) => (
              <a
                key={asset.sceneId}
                href={asset.url}
                target="_blank"
                rel="noreferrer"
                className="group overflow-hidden rounded-md border bg-background"
              >
                <img
                  src={asset.url}
                  alt={`Preview da cena ${asset.index}`}
                  className="aspect-[9/16] w-full object-cover transition group-hover:opacity-80"
                />
                <div className="p-2 text-[10px] text-muted-foreground">
                  Cena {asset.index} · {asset.layout || asset.type}
                </div>
              </a>
            ))}
        </div>
      ) : null}
      {error ? (
        <p className="rounded-md border border-status-danger/30 bg-status-danger/5 px-3 py-2 text-xs text-status-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
