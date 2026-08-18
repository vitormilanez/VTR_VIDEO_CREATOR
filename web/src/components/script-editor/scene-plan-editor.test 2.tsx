// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { render, screen, waitFor } from "@testing-library/react";
import type { ComponentProps } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const { generateSceneDirectionMock, saveScenePlanMock } = vi.hoisted(() => ({
  generateSceneDirectionMock: vi.fn(),
  saveScenePlanMock: vi.fn(),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn() } }));

vi.mock("@/lib/api/local", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/local")>();
  return {
    ...actual,
    generateSceneDirection: generateSceneDirectionMock,
    saveScenePlan: saveScenePlanMock,
  };
});

import { ScenePlanEditor } from "./scene-plan-editor";
import type { ScenePlan, SceneTransitionStyle } from "@/lib/api/local";

type ClaudePlanInput = Parameters<
  NonNullable<ComponentProps<typeof ScenePlanEditor>["onApplyClaudePlan"]>
>[0];

const adjustedScript =
  "Primeiro dado: 20% das pessoas podem ter esse sintoma. Isso não define um diagnóstico. " +
  "Observe a duração e os sinais associados. Procure avaliação se persistir.";

function scenePlanFromInput(input: ClaudePlanInput): ScenePlan {
  return {
    scriptId: "script-1",
    transitionStyle: input.transitionStyle,
    updatedAt: "2026-08-11T12:00:00Z",
    scenes: input.scenes.map((scene, index) => ({
      ...scene,
      order: index + 1,
      avatarId: scene.lookRole === "standing" ? "look-standing" : "look-seated",
    })),
  };
}

describe("ScenePlanEditor two-camera Claude proposal", () => {
  beforeAll(() => {
    // Radix Select expects these browser pointer-capture APIs, which jsdom
    // deliberately leaves unimplemented.
    Object.defineProperties(HTMLElement.prototype, {
      hasPointerCapture: { configurable: true, value: () => false },
      releasePointerCapture: { configurable: true, value: () => undefined },
      scrollIntoView: { configurable: true, value: () => undefined },
      setPointerCapture: { configurable: true, value: () => undefined },
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("keeps all mocked Sonnet cuts and applies the adjusted script before the scene plan", async () => {
    generateSceneDirectionMock.mockResolvedValue({
      provider: "claude",
      promptVersion: "mock-two-camera",
      model: "claude-sonnet-4-6",
      modelTier: "sonnet",
      adjustedScript,
      scriptChanges: ["Mantive o número de 20% e simplifiquei a orientação."],
      scenes: [
        {
          text: "Primeiro dado: 20% das pessoas podem ter esse sintoma.",
          lookRole: "standing",
          reason: "abre com o dado",
        },
        {
          text: "Isso não define um diagnóstico.",
          lookRole: "seated",
          reason: "faz a ressalva",
        },
        {
          text: "Observe a duração e os sinais associados.",
          lookRole: "standing",
          reason: "detalha o contexto",
        },
        {
          text: "Procure avaliação se persistir.",
          lookRole: "seated",
          reason: "fecha a orientação",
        },
      ],
    });
    const onSaved = vi.fn();
    const onApplyClaudePlan = vi.fn(async (input: ClaudePlanInput) => scenePlanFromInput(input));
    const user = userEvent.setup();

    render(
      <ScenePlanEditor
        scriptId="script-1"
        loading={false}
        plan={null}
        fallbackText={adjustedScript}
        displayText={adjustedScript}
        spokenText={adjustedScript}
        durationSeconds={90}
        performancePlan={{
          tone: "calmo",
          pace: "frases curtas",
          emotion: "seguro",
          recommendedVoiceSpeed: 1,
        }}
        availableRoles={["standing", "seated"]}
        onSaved={onSaved}
        onApplyClaudePlan={onApplyClaudePlan}
      />,
    );

    await user.click(screen.getByRole("combobox", { name: "Modelo do Claude" }));
    await user.click(await screen.findByRole("option", { name: "Claude Sonnet" }));
    await user.click(screen.getByRole("button", { name: "Revisar com Claude" }));

    await waitFor(() =>
      expect(generateSceneDirectionMock).toHaveBeenCalledWith(
        "script-1",
        expect.objectContaining({ durationSeconds: 90, modelTier: "sonnet" }),
      ),
    );
    expect(screen.getAllByPlaceholderText("Texto falado nesta cena")).toHaveLength(4);
    expect(screen.getByLabelText("Roteiro ajustado pelo Claude")).toHaveValue(adjustedScript);

    await user.click(screen.getByRole("button", { name: "Aplicar roteiro e cortes" }));

    await waitFor(() =>
      expect(onApplyClaudePlan).toHaveBeenCalledWith(
        expect.objectContaining({
          adjustedScript,
          transitionStyle: "hard_cut",
          scenes: expect.arrayContaining([
            expect.objectContaining({ lookRole: "standing" }),
            expect.objectContaining({ lookRole: "seated" }),
          ]),
        }),
      ),
    );
    expect(onApplyClaudePlan.mock.calls[0]?.[0].scenes).toHaveLength(4);
    expect(saveScenePlanMock).not.toHaveBeenCalled();
    expect(onSaved).toHaveBeenCalledTimes(1);
  });
});
