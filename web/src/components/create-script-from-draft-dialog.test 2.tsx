// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { navigateMock, toastMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  toastMock: { error: vi.fn(), success: vi.fn() },
}));

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => navigateMock,
}));

vi.mock("sonner", () => ({ toast: toastMock }));

vi.mock("@/lib/api/local", () => ({
  createScriptFromDraft: vi.fn(),
}));

import { createScriptFromDraft } from "@/lib/api/local";
import { useStore } from "@/lib/store";
import { CreateScriptFromDraftDialog } from "./create-script-from-draft-dialog";

const draft =
  "A obesidade é uma condição complexa e não depende apenas de força de vontade. O contexto clínico e as evidências precisam orientar a explicação.";

const script = {
  id: "s-draft-test",
  categoria: "educativo" as const,
  tema: "Obesidade sem simplificação",
  titulo: "Obesidade sem simplificação",
  hook: "Não é apenas força de vontade.",
  dorConflito: "Explicações simples demais confundem.",
  explicacaoSimples: "Existem fatores biológicos e ambientais.",
  virada: "O contexto importa.",
  cta: "Salve para rever",
  cuidadosMedicos: "Validar as fontes.",
  risco: "medio" as const,
  prioridade: "media" as const,
  formatoSugerido: "Reel educativo · 45 segundos",
  status: "aguardando_validacao" as const,
  criadoEm: "2026-08-13T18:00:00Z",
  editorialTone: "neutro" as const,
  textoFalado: draft,
  outroText: "Salve para rever",
  generationProvider: "claude" as const,
  generationFlowVersion: "draft-to-scenes-v1",
};

const result = {
  provider: "claude" as const,
  model: "claude-haiku-4-5",
  promptVersion: "draft-v1",
  cacheHit: false,
  deduplicated: false,
  script,
  scenePlan: {
    scriptId: script.id,
    scenes: [
      {
        id: "scene-1",
        order: 1,
        text: draft,
        lookRole: "primary" as const,
        avatarId: "",
        estimatedStart: 0,
        estimatedEnd: 0,
      },
    ],
    transitionStyle: "hard_cut" as const,
    updatedAt: "2026-08-13T18:00:00Z",
  },
  changes: ["Texto simplificado."],
};

describe("CreateScriptFromDraftDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    useStore.setState({ scripts: [] });
    vi.mocked(createScriptFromDraft).mockResolvedValue(result);
  });

  afterEach(() => cleanup());

  it("sends the pasted text to Claude and opens the existing script editor", async () => {
    const user = userEvent.setup();
    render(<CreateScriptFromDraftDialog />);

    await user.click(screen.getByRole("button", { name: "Novo roteiro" }));
    expect(
      screen.getByRole("heading", { name: "Criar roteiro a partir do seu texto" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Revisar e criar cenas" })).toBeDisabled();

    await user.type(screen.getByLabelText("Título (opcional)"), "Obesidade sem simplificação");
    await user.type(screen.getByLabelText("Texto do roteiro"), draft);
    await user.click(screen.getByRole("button", { name: "Revisar e criar cenas" }));

    await waitFor(() =>
      expect(createScriptFromDraft).toHaveBeenCalledWith({
        draftText: draft,
        title: "Obesidade sem simplificação",
        familia: "educativo",
        editorialTone: "neutro",
        durationSeconds: 45,
      }),
    );
    expect(useStore.getState().scripts).toContainEqual(script);
    expect(navigateMock).toHaveBeenCalledWith({
      to: "/roteiros/$id",
      params: { id: script.id },
    });
    expect(toastMock.success).toHaveBeenCalledWith("Roteiro revisado e 1 cena criada.");
  });

  it("keeps the text available when Claude returns an error", async () => {
    const user = userEvent.setup();
    vi.mocked(createScriptFromDraft).mockRejectedValueOnce(new Error("Claude indisponível"));
    render(<CreateScriptFromDraftDialog />);

    await user.click(screen.getByRole("button", { name: "Novo roteiro" }));
    await user.type(screen.getByLabelText("Texto do roteiro"), draft);
    await user.click(screen.getByRole("button", { name: "Revisar e criar cenas" }));

    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith("Claude indisponível"));
    expect(screen.getByLabelText("Texto do roteiro")).toHaveValue(draft);
    expect(navigateMock).not.toHaveBeenCalled();
  });
});
