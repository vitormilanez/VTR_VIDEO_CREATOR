import { describe, expect, it } from "vitest";
import type { LocalVideoKitConfig, VisualTimelineEvent } from "@/lib/api/local";
import { validateLocalVideoVisualTiming } from "@/lib/local-video-visual-timing";

const EVENT: VisualTimelineEvent = {
  id: "comparison",
  startWordIndex: 15,
  endWordIndex: 21,
  startMs: 6310,
  endMs: 8990,
  timingSource: "transcript",
  spokenText: "dois sinais de saciedade ao mesmo tempo",
  interactionType: "comparison_card",
  visualText: "dois sinais de saciedade ao mesmo tempo",
  enabled: true,
  reviewStatus: "pending",
  reason: "fixture",
  confidence: 0.95,
};

const CONFIG = {
  includeSection: false,
  sectionTitle: "",
  manualVisualsEnabled: true,
  claudeInserts: {
    mechanismBars: {
      enabled: true,
      startSeconds: 4,
      durationSeconds: 4,
      fields: ["UM ALVO VS. DOIS"],
    },
  },
} as LocalVideoKitConfig;

describe("local video visual timing", () => {
  it("detecta o conflito real entre o modelo manual e o visual do Claude", () => {
    const result = validateLocalVideoVisualTiming([EVENT], CONFIG, 86);

    expect(result.issues).toEqual(
      expect.arrayContaining([expect.stringContaining("UM ALVO VS. DOIS")]),
    );
    expect(result.issuesByItemId[`event:${EVENT.id}`]).toHaveLength(1);
    expect(result.issuesByItemId["manual:mechanismBars"]).toHaveLength(1);
  });

  it("aceita a entrada ajustada para depois do visual manual", () => {
    const adjusted = { ...EVENT, startMs: 8200, endMs: 10200, timingSource: "manual" as const };

    expect(validateLocalVideoVisualTiming([adjusted], CONFIG, 86).issues).toEqual([]);
  });

  it("ignora modelos legados quando os complementos manuais não foram ativados", () => {
    const legacyConfig = { ...CONFIG, manualVisualsEnabled: false };

    expect(validateLocalVideoVisualTiming([EVENT], legacyConfig, 86).issues).toEqual([]);
  });

  it("avisa antes do render quando a duração fica curta demais", () => {
    const short = { ...EVENT, startMs: 8100, endMs: 9000, timingSource: "manual" as const };
    const config = { ...CONFIG, claudeInserts: undefined };

    expect(validateLocalVideoVisualTiming([short], config, 86).issues[0]).toContain(
      "entre 1,5 e 5,5 segundos",
    );
  });
});
