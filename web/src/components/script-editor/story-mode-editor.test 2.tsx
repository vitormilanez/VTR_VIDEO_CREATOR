import { describe, expect, it } from "vitest";

import type { StoryBrief, StoryPlan, StoryVersion } from "@/lib/api/local";
import {
  canApproveStory,
  makeStoryEditorState,
  storyModeReducer,
  type StoryEditorState,
} from "./story-mode-editor";

const brief: StoryBrief = {
  storyType: "narrative_explainer",
  educationalGoal: "Explicar o tema com clareza e segurança.",
  period: "",
  location: "",
  realismLevel: "high",
  historicalAccuracy: "not_applicable",
  tone: "curious_educational",
  durationSeconds: 20,
  orientation: "portrait",
  productionTier: "cinematic",
  maxHeyGenJobs: 2,
  maxRegenerationsPerShot: 1,
  maxBudgetUsd: 20,
  characterId: null,
  lookId: null,
  characterDescription: "",
  wardrobeDirection: "",
  referenceAssets: [],
};

const plan = {
  shots: [{ id: "shot-01", order: 1, action: "Ação inicial" }],
} as unknown as StoryPlan;

function editableState(): StoryEditorState {
  return {
    ...makeStoryEditorState(brief),
    phase: "ready",
    plan,
    reviews: [
      {
        promptOverride: "",
        lockIdentity: true,
        lockWardrobe: true,
        lockEnvironment: false,
        approved: false,
      },
    ],
    version: {
      id: "version-1",
      storyRevision: 1,
      storyBibleApproved: false,
      approved: false,
    } as StoryVersion,
  };
}

describe("Story Mode editor state", () => {
  it("exposes loading failures without losing the brief", () => {
    const state = storyModeReducer(makeStoryEditorState(brief), {
      type: "load-error",
      message: "Falha de rede",
    });

    expect(state.phase).toBe("error");
    expect(state.error).toBe("Falha de rede");
    expect(state.brief.educationalGoal).toBe(brief.educationalGoal);
  });

  it("undoes a shot edit from the local revision history", () => {
    const original = editableState();
    const editedShot = { ...plan.shots[0], action: "Nova ação" } as StoryPlan["shots"][number];
    const edited = storyModeReducer(original, { type: "shot-change", index: 0, shot: editedShot });
    const undone = storyModeReducer(edited, { type: "undo" });

    expect(edited.dirty).toBe(true);
    expect(edited.history).toHaveLength(1);
    expect(undone.plan?.shots[0].action).toBe("Ação inicial");
    expect(undone.history).toHaveLength(0);
  });

  it("only enables final approval for approved shots, Bible, critique and budget", () => {
    const state = editableState();
    expect(canApproveStory(state)).toBe(false);

    const ready = {
      ...state,
      storyBibleApproved: true,
      reviews: [{ ...state.reviews[0], approved: true }],
      version: {
        ...state.version!,
        storyBibleApproved: true,
        activeCritique: {
          critique: { decision: "ready" },
          budget: { approvalEligible: true },
        },
      } as StoryVersion,
    };

    expect(canApproveStory(ready)).toBe(true);
    expect(canApproveStory({ ...ready, dirty: true })).toBe(false);
  });
});
