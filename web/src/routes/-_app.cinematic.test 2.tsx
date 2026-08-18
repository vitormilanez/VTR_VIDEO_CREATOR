// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import type { ComponentType, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { toastMock } = vi.hoisted(() => ({
  toastMock: { error: vi.fn(), success: vi.fn() },
}));

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (config: Record<string, unknown>) => config,
  Link: ({ children }: { children: ReactNode }) => <a href="#test">{children}</a>,
}));

vi.mock("sonner", () => ({ toast: toastMock }));

vi.mock("@/components/app-shell", () => ({
  AppShell: ({ title, children }: { title: string; children: ReactNode }) => (
    <div>
      <h1>{title}</h1>
      {children}
    </div>
  ),
}));

vi.mock("@/components/script-editor/avatar-studio", () => ({
  AvatarPicker: ({
    value,
    avatars,
  }: {
    value: string;
    avatars: Array<{ id: string; name: string }>;
  }) => <div>{avatars.find((avatar) => avatar.id === value)?.name || "Sem avatar"}</div>,
}));

vi.mock("@/lib/api/local", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/local")>();
  return {
    ...actual,
    adjustCinematicWithClaude: vi.fn(),
    appendScript: vi.fn(),
    createHeyGenVideo: vi.fn(),
    fetchHeyGenCatalog: vi.fn(),
    fetchScriptEditorState: vi.fn(),
  };
});

import {
  adjustCinematicWithClaude,
  appendScript,
  createHeyGenVideo,
  fetchHeyGenCatalog,
  fetchScriptEditorState,
} from "@/lib/api/local";
import { useStore } from "@/lib/store";
import { Route } from "./_app.cinematic";

const CinematicPage = (Route as unknown as { component: ComponentType }).component;
const speech = Array.from({ length: 100 }, (_, index) => `palavra${index + 1}`).join(" ");
const adjustedSpeech = Array.from({ length: 65 }, (_, index) => `conteudo${index + 1}`).join(" ");

describe("Cinematic page", () => {
  beforeEach(() => {
    window.localStorage.clear();
    useStore.setState({ scripts: [], videoJobs: [] });
    vi.mocked(fetchHeyGenCatalog).mockResolvedValue({
      avatars: [
        {
          id: "avatar-gui",
          name: "Gui principal",
          orientation: "portrait",
          defaultVoiceId: "voice-gui",
        },
      ],
      voices: [{ id: "voice-gui", name: "Voz do Gui", gender: "male" }],
      defaultAvatarId: "avatar-gui",
      defaultVoiceId: "voice-gui",
    });
    vi.mocked(appendScript).mockImplementation(async (script) => script);
    vi.mocked(adjustCinematicWithClaude).mockResolvedValue({
      provider: "claude",
      model: "claude-sonnet-4-6",
      adjusted: {
        speech: adjustedSpeech,
        durationSeconds: 30,
        supportingImages: "auto",
        presenterMode: "intro_outro",
        mediaTypes: ["motion_graphics", "stock_media"],
        visualStyle: "documentary",
        requiredElements: "Show real daily routines and the selected presenter.",
        excludedElements: "Avoid unrelated gym stereotypes and synthetic bodies.",
        criticalOnScreenText: "Energia não é só força de vontade",
        directionNotes: "Use restrained pacing, natural light, and clean transitions.",
        rationale: "A ideia foi transformada em uma fala de 30 segundos com uma única tese.",
      },
      assessment: {
        durationSeconds: 30,
        wordCount: 65,
        estimatedSeconds: 27.08,
        estimatedSecondsDisplay: "~27s",
        targetWords: 72,
        hardLimitWords: 78,
        generationMinWords: 63,
        generationMaxWords: 67,
        status: "ideal",
        message: "Duração ideal para 30s.",
      },
      retryCount: 0,
      cacheHit: false,
    });
    vi.mocked(fetchScriptEditorState).mockResolvedValue({
      scriptId: "s-cinematic-test",
      durationSeconds: 45,
      humanReviewApproved: true,
      titleChoice: "current",
      schemaValid: true,
      technicalError: null,
      scriptRevision: 1,
      finalSpeechHash: "a".repeat(64),
      contractVersion: "2.0.0",
      approvalHistory: [],
      legacyFallback: false,
    });
    vi.mocked(createHeyGenVideo).mockResolvedValue({
      id: "video-cinematic",
      scriptId: "s-cinematic-test",
      status: "fila",
      provider: "heygen",
      progresso: 0,
      criadoEm: "2026-08-09T20:00:00.000Z",
      atualizadoEm: "2026-08-09T20:00:00.000Z",
    });
  });

  afterEach(() => cleanup());

  it("creates a reviewed open script and sends an explicit cinematic request", async () => {
    const user = userEvent.setup();
    render(<CinematicPage />);

    expect((await screen.findAllByText("Gui principal")).length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText("Ideia ou fala do Gui"), {
      target: { value: speech },
    });
    await user.type(
      screen.getByLabelText("O que precisa aparecer"),
      "consulta com nutricionista e refeição brasileira",
    );
    await user.type(screen.getByLabelText("Texto exato na tela"), "Saúde com acompanhamento");
    await user.click(screen.getByRole("checkbox", { name: /revisei e confirmo/i }));
    await user.click(screen.getByRole("button", { name: /gerar vídeo no heygen/i }));

    await waitFor(() => expect(createHeyGenVideo).toHaveBeenCalledOnce());
    expect(appendScript).toHaveBeenCalledWith(
      expect.objectContaining({
        textoFalado: speech,
        outroText: "",
        status: "aprovado_clinicamente",
      }),
    );
    expect(createHeyGenVideo).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        avatarId: "avatar-gui",
        voiceId: "voice-gui",
        durationSeconds: 45,
        generationMode: "cinematic",
        ctaMode: "none",
        narrationText: speech,
        displayText: speech,
        outroText: "",
        finalConfirmed: true,
        cinematicPrompt: expect.stringMatching(
          /The selected presenter[\s\S]*consulta com nutricionista[\s\S]*Saúde com acompanhamento/,
        ),
      }),
    );
    expect(screen.getByText("Vídeo enviado para produção")).toBeInTheDocument();
  });

  it("lets Sonnet turn a short idea and all screen context into a reviewed HeyGen package", async () => {
    const user = userEvent.setup();
    render(<CinematicPage />);

    expect((await screen.findAllByText("Gui principal")).length).toBeGreaterThan(0);
    const source = "Como o conforto excessivo afeta energia, hábitos e saúde masculina";
    await user.type(screen.getByLabelText("Ideia ou fala do Gui"), source);
    await user.type(screen.getByLabelText("O que deve ser evitado"), "cenas fora do tema");
    await user.click(screen.getByRole("checkbox", { name: /revisei e confirmo/i }));
    await user.click(screen.getByRole("button", { name: /ajustar tudo com claude sonnet/i }));

    await waitFor(() => expect(adjustCinematicWithClaude).toHaveBeenCalledOnce());
    expect(adjustCinematicWithClaude).toHaveBeenCalledWith(
      expect.objectContaining({
        sourceText: source,
        durationSeconds: 45,
        excludedElements: "cenas fora do tema",
        avatarName: "Gui principal",
        avatarOrientation: "portrait",
      }),
    );
    expect(screen.getByLabelText("Ideia ou fala do Gui")).toHaveValue(adjustedSpeech);
    expect(screen.getByRole("button", { name: "30s" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("O que precisa aparecer")).toHaveValue(
      "Show real daily routines and the selected presenter.",
    );
    expect(screen.getByLabelText("Texto exato na tela")).toHaveValue(
      "Energia não é só força de vontade",
    );
    expect(screen.getByRole("checkbox", { name: /revisei e confirmo/i })).not.toBeChecked();
    expect(screen.getByText(/a ideia foi transformada em uma fala de 30 segundos/i)).toBeVisible();
  });

  it("restores the complete cinematic draft after a remount", async () => {
    const user = userEvent.setup();
    const firstRender = render(<CinematicPage />);

    expect((await screen.findAllByText("Gui principal")).length).toBeGreaterThan(0);
    await user.type(
      screen.getByLabelText("Ideia ou fala do Gui"),
      "Uma ideia persistente sobre energia e hábitos masculinos no mundo moderno.",
    );
    await user.click(screen.getByRole("button", { name: "30s" }));
    await user.type(screen.getByLabelText("O que precisa aparecer"), "rotina real brasileira");

    await waitFor(() =>
      expect(window.localStorage.getItem("ai-video-creator:cinematic-draft:v1")).toContain(
        "rotina real brasileira",
      ),
    );
    firstRender.unmount();
    render(<CinematicPage />);

    expect(await screen.findByLabelText("Ideia ou fala do Gui")).toHaveValue(
      "Uma ideia persistente sobre energia e hábitos masculinos no mundo moderno.",
    );
    expect(screen.getByRole("button", { name: "30s" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("O que precisa aparecer")).toHaveValue("rotina real brasileira");
  });

  it("keeps and displays the local job id when HeyGen submission fails", async () => {
    const user = userEvent.setup();
    vi.mocked(createHeyGenVideo).mockResolvedValueOnce({
      id: "v-saved-after-failure",
      scriptId: "s-cinematic-test",
      status: "erro",
      provider: "heygen",
      progresso: 0,
      erro: "A conexão com a HeyGen foi interrompida.",
      warnings: ["Possível linguagem prescritiva"],
      criadoEm: "2026-08-10T14:00:00.000Z",
      atualizadoEm: "2026-08-10T14:00:00.000Z",
    });
    render(<CinematicPage />);

    expect((await screen.findAllByText("Gui principal")).length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText("Ideia ou fala do Gui"), {
      target: { value: speech },
    });
    await user.click(screen.getByRole("checkbox", { name: /revisei e confirmo/i }));
    await user.click(screen.getByRole("button", { name: /gerar vídeo no heygen/i }));

    expect(await screen.findByText("Job salvo; envio não concluído")).toBeVisible();
    expect(screen.getByText(/ID: v-saved-after-failure/)).toBeVisible();
    expect(screen.getByText("A conexão com a HeyGen foi interrompida.")).toBeVisible();
    expect(useStore.getState().videoJobs[0]?.id).toBe("v-saved-after-failure");
  });

  it("shows prescriptive language as a warning instead of disabling the flow", async () => {
    const user = userEvent.setup();
    render(<CinematicPage />);

    expect((await screen.findAllByText("Gui principal")).length).toBeGreaterThan(0);
    await user.type(
      screen.getByLabelText("Ideia ou fala do Gui"),
      "Prescreva uma rotina e converse com seu médico antes de tomar decisões individuais.",
    );

    expect(screen.getByText("Aviso de compliance — não bloqueia a geração")).toBeVisible();
    expect(screen.getByText(/termo de prescricao/i)).toBeVisible();
  });

  it("has no critical accessibility violations", async () => {
    render(<CinematicPage />);
    expect((await screen.findAllByText("Gui principal")).length).toBeGreaterThan(0);

    const result = await axe.run(document.body, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(result.violations.filter((violation) => violation.impact === "critical")).toEqual([]);
  });

  it("exposes structured HeyGen visual controls and a technical preview", async () => {
    render(<CinematicPage />);
    expect((await screen.findAllByText("Gui principal")).length).toBeGreaterThan(0);

    expect(screen.getByRole("group", { name: "Presença do Gui" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Tipos de apoio visual" })).toBeInTheDocument();
    expect(screen.getByLabelText("O que precisa aparecer")).toBeInTheDocument();
    expect(screen.getByLabelText("O que deve ser evitado")).toBeInTheDocument();
    expect(screen.getByLabelText("Texto exato na tela")).toBeInTheDocument();
    expect(screen.getByText("Instruções técnicas enviadas ao HeyGen")).toBeInTheDocument();
  });
});
