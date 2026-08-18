import { describe, expect, it } from "vitest";

import {
  CINEMATIC_DIRECTION_MAX_LENGTH,
  buildCinematicDirection,
  buildCinematicScript,
  cinematicProjectTitle,
} from "./cinematic";

const speech =
  "Você não precisa esperar a motivação aparecer para cuidar da sua saúde. Comece pelo próximo passo possível e mantenha acompanhamento profissional.";

describe("cinematic open-script contract", () => {
  it("turns the first sentence into a concise automatic title", () => {
    expect(cinematicProjectTitle(speech)).toBe(
      "Você não precisa esperar a motivação aparecer para cuidar da sua saúde",
    );
  });

  it("persists the exact reviewed speech without adding an outro", () => {
    const script = buildCinematicScript({
      id: "s-cinematic-test",
      speech: `  ${speech}  `,
      createdAt: "2026-08-09T20:00:00.000Z",
    });

    expect(script.id).toBe("s-cinematic-test");
    expect(script.textoFalado).toBe(speech);
    expect(script.outroText).toBe("");
    expect(script.status).toBe("aprovado_clinicamente");
    expect(script.generationProvider).toBe("manual");
    expect(script.generationFlowVersion).toBe("cinematic-open-v1");
  });

  it("builds a script-driven HeyGen brief with explicit visual elements", () => {
    const direction = buildCinematicDirection({
      durationSeconds: 45,
      supportingImages: "auto",
      presenterMode: "anchor",
      mediaTypes: ["motion_graphics", "stock_media"],
      visualStyle: "documentary",
      requiredElements: "balança de alimentos e consulta com nutricionista",
      excludedElements: "agulhas e cenas de hospital",
      criticalOnScreenText: "Saúde não é só o número da balança",
      notes: "Prefer Brazilian locations when local context is relevant.",
    });

    expect(direction).toContain("Target duration: 45 seconds");
    expect(direction).toContain("The selected presenter");
    expect(direction).toContain("Preserve the central thesis, factual boundaries, tone, and CTA");
    expect(direction).toContain("Use Motion Graphics");
    expect(direction).toContain("Use Stock Media");
    expect(direction).toContain("balança de alimentos e consulta com nutricionista");
    expect(direction).toContain("CRITICAL ON-SCREEN TEXT — DISPLAY LITERALLY");
    expect(direction).toContain("Saúde não é só o número da balança");
    expect(direction).toContain("agulhas e cenas de hospital");
    expect(direction).not.toContain("Gui principal");
  });

  it("keeps the avatar on screen when supporting images are disabled", () => {
    const direction = buildCinematicDirection({
      durationSeconds: 30,
      supportingImages: "avatar_only",
      presenterMode: "always",
      mediaTypes: ["motion_graphics", "stock_media", "ai_generated"],
      visualStyle: "clean",
      requiredElements: "",
      excludedElements: "",
      criticalOnScreenText: "",
      notes: "",
    });

    expect(direction).toContain("Keep the selected presenter visible throughout");
    expect(direction).toContain(
      "Do not use full-screen B-roll, Stock Media, or AI-generated visuals",
    );
    expect(direction).not.toContain("Use Stock Media for");
    expect(direction).not.toContain("Use AI-Generated visuals for");
  });

  it("keeps a representative detailed brief inside the API limit", () => {
    const direction = buildCinematicDirection({
      durationSeconds: 60,
      supportingImages: "auto",
      presenterMode: "intro_outro",
      mediaTypes: ["motion_graphics", "stock_media", "ai_generated"],
      visualStyle: "editorial",
      requiredElements: "Mostre uma consulta, uma refeição brasileira e uma caminhada ao ar livre.",
      excludedElements:
        "Evite hospitais, agulhas, marcas, embalagens e imagens de corpos sem contexto.",
      criticalOnScreenText: "Acompanhamento profissional\nResultados variam para cada pessoa",
      notes:
        "Use warm natural light, calm pacing, discreet camera movement, and seamless transitions.",
    });

    expect(direction.length).toBeLessThanOrEqual(CINEMATIC_DIRECTION_MAX_LENGTH);
  });
});
