import { beforeEach, describe, expect, it, vi } from "vitest";

import { defaultSettings, type Script } from "./mock-data";
import { useStore } from "./store";

const baseScript: Script = {
  id: "s-save-race",
  categoria: "educativo",
  tema: "Teste",
  titulo: "Roteiro teste",
  hook: "Hook antigo",
  dorConflito: "",
  explicacaoSimples: "",
  virada: "",
  cta: "",
  cuidadosMedicos: "",
  risco: "medio",
  prioridade: "media",
  formatoSugerido: "Reels",
  status: "em_revisao",
  criadoEm: "2026-08-10T12:00:00.000Z",
  textoFalado: "Texto antigo",
  outroText: "",
};

describe("store hydration", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-10T12:00:00.000Z"));
    useStore.setState({
      trends: [],
      ideas: [],
      scripts: [],
      videoJobs: [],
      calendarPosts: [],
      performance: [],
      settings: defaultSettings,
      complianceRules: [],
      syncedAt: null,
    });
  });

  it("does not overwrite a freshly saved script with a stale hydrate payload", () => {
    useStore.getState().hydrate({
      scripts: [baseScript],
      updatedAt: "2026-08-10T12:00:00",
    });

    useStore.getState().updateScript(baseScript.id, { textoFalado: "Texto novo salvo" });

    useStore.getState().hydrate({
      scripts: [baseScript],
      updatedAt: "2026-08-10T11:59:00",
    });

    expect(useStore.getState().scripts[0]?.textoFalado).toBe("Texto novo salvo");
  });

  it("accepts hydrate payloads again after the local save protection expires", () => {
    useStore.getState().hydrate({
      scripts: [baseScript],
      updatedAt: "2026-08-10T12:00:00",
    });
    useStore.getState().updateScript(baseScript.id, { textoFalado: "Texto novo salvo" });

    vi.advanceTimersByTime(2 * 60 * 1000 + 1);

    useStore.getState().hydrate({
      scripts: [{ ...baseScript, textoFalado: "Texto vindo do Sheets depois" }],
      updatedAt: "2026-08-10T12:03:00",
    });

    expect(useStore.getState().scripts[0]?.textoFalado).toBe("Texto vindo do Sheets depois");
  });
});
