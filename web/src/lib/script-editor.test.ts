import { describe, expect, it } from "vitest";
import {
  assessScriptDuration,
  countScriptWords,
  evaluateGenerationGate,
  type DurationPreset,
} from "./script-editor";

const words = (amount: number) =>
  Array.from({ length: amount }, (_, index) => `palavra${index}`).join(" ");

describe("script editor duration contract", () => {
  it.each([
    [10, 24, 26, 21, 22],
    [15, 36, 39, 31, 33],
    [30, 72, 78, 63, 67],
    [45, 108, 116, 95, 101],
    [60, 144, 155, 126, 135],
  ] as const)(
    "%ss exposes target, warning and generation ranges",
    (duration, target, hard, generationMin, generationMax) => {
      const assessment = assessScriptDuration(words(target), duration);
      expect(assessment).toMatchObject({
        targetWords: target,
        hardLimitWords: hard,
        generationMinWords: generationMin,
        generationMaxWords: generationMax,
        status: "ideal",
      });
      expect(assessScriptDuration(words(target + 1), duration).status).toBe("warning");
      expect(assessScriptDuration(words(hard + 1), duration).status).toBe("blocking");
    },
  );

  it.each([
    [108, "ideal"],
    [109, "warning"],
    [116, "warning"],
    [117, "blocking"],
  ] as const)("45s with %s words is %s", (amount, status) => {
    expect(assessScriptDuration(words(amount), 45).status).toBe(status);
  });

  it("uses the same punctuation, accent and GLP-1 tokenization", () => {
    expect(countScriptWords("  Saúde,\nGLP-1 e médico-paciente; d'água...  ")).toBe(5);
  });
});

describe("editor permissions", () => {
  const base = {
    durationSeconds: 45 as DurationPreset,
    aiOperationInFlight: false,
    schemaValid: true,
    medicalReviewStatus: "recommended" as const,
    humanReviewApproved: false,
    scriptStatus: "aprovado_clinicamente",
    finalSaved: true,
    finalConfirmed: true,
  };

  it("allows HeyGen in the warning range", () => {
    expect(evaluateGenerationGate({ ...base, speech: words(109) }).allowed).toBe(true);
  });

  it("blocks HeyGen beyond the hard limit without affecting save policy", () => {
    const gate = evaluateGenerationGate({ ...base, speech: words(117) });
    expect(gate.allowed).toBe(false);
    expect(gate.reasons[0]?.code).toBe("duration_blocking");
  });

  it("blocks required medical review independently of ideal duration", () => {
    const gate = evaluateGenerationGate({
      ...base,
      speech: words(108),
      medicalReviewStatus: "required",
    });
    expect(gate.allowed).toBe(false);
    expect(gate.reasons.some((reason) => reason.code === "duration_blocking")).toBe(false);
    expect(gate.reasons.some((reason) => reason.code === "medical_review_required")).toBe(true);
  });
});
