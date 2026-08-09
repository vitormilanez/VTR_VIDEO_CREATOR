// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import type { ComponentType, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { EditorAssistResult } from "@/lib/script-editor";
import type { Script } from "@/lib/mock-data";

const { navigateMock, toastMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  toastMock: {
    error: vi.fn(),
    info: vi.fn(),
    loading: vi.fn(() => "toast-id"),
    success: vi.fn(),
  },
}));

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (config: Record<string, unknown>) => ({
    ...config,
    useParams: () => ({ id: "script-test" }),
  }),
  Link: ({ children }: { children: ReactNode }) => <a href="#test">{children}</a>,
  useNavigate: () => navigateMock,
}));

vi.mock("sonner", () => ({ toast: toastMock }));

vi.mock("@/components/app-shell", () => ({
  AppShell: ({
    title,
    actions,
    children,
  }: {
    title: string;
    actions?: ReactNode;
    children: ReactNode;
  }) => (
    <div>
      <header>
        <h1>{title}</h1>
        {actions}
      </header>
      <main>{children}</main>
    </div>
  ),
}));

vi.mock("@/components/with-tooltip", () => ({
  WithTooltip: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("@/components/confirm-action", () => ({
  ConfirmAction: ({ trigger }: { trigger: ReactNode }) => <>{trigger}</>,
}));

vi.mock("@/lib/api/local", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/local")>();
  return {
    ...actual,
    createHeyGenPreview: vi.fn(),
    createHeyGenVideo: vi.fn(),
    composeFinalVideo: vi.fn(),
    deleteAvatarSet: vi.fn(),
    fetchAvatarSets: vi.fn(),
    fetchHeyGenCatalog: vi.fn(),
    fetchMusicTracks: vi.fn(),
    fetchProductionProfile: vi.fn(),
    fetchSceneGenerationPlan: vi.fn(),
    fetchScenePlan: vi.fn(),
    fetchScriptEditorState: vi.fn(),
    fetchVideoSlideRender: vi.fn(),
    fetchVisualPlan: vi.fn(),
    generateSceneDirection: vi.fn(),
    generateVisualDirection: vi.fn(),
    renderVideoSlides: vi.fn(),
    runScriptEditorAssist: vi.fn(),
    saveAvatarSet: vi.fn(),
    saveProductionProfile: vi.fn(),
    saveScenePlan: vi.fn(),
    saveScript: vi.fn(),
    saveScriptEditorState: vi.fn(),
    saveVisualPlan: vi.fn(),
    submitSceneGeneration: vi.fn(),
  };
});

import {
  fetchAvatarSets,
  fetchHeyGenCatalog,
  fetchMusicTracks,
  fetchProductionProfile,
  fetchScenePlan,
  fetchScriptEditorState,
  fetchVideoSlideRender,
  fetchVisualPlan,
  runScriptEditorAssist,
  saveScript,
  saveScriptEditorState,
} from "@/lib/api/local";
import { useStore } from "@/lib/store";
import { Route } from "./_app.roteiros.$id";

const RoteiroDetalhe = (Route as unknown as { component: ComponentType }).component;

const makeWords = (amount: number) =>
  Array.from({ length: amount }, (_, index) => `palavra${index + 1}`).join(" ");

const baseScript: Script = {
  id: "script-test",
  categoria: "educativo",
  tema: "Saúde metabólica",
  titulo: "Como cuidar da saúde metabólica",
  hook: "Você sabe o que muda sua saúde metabólica?",
  dorConflito: "Informações conflitantes dificultam boas escolhas.",
  explicacaoSimples: "Hábitos e acompanhamento profissional ajudam.",
  virada: "Pequenas decisões consistentes fazem diferença.",
  cta: "Converse com seu médico.",
  cuidadosMedicos: "Conteúdo educativo; não substitui consulta.",
  risco: "medio",
  prioridade: "media",
  formatoSugerido: "Vídeo educativo",
  status: "aprovado_clinicamente",
  criadoEm: "2026-08-09T00:00:00.000Z",
  textoFalado: makeWords(100),
  outroText: "Quer mais dicas? Siga e acompanhe.",
};

function assistResult(overrides: Partial<EditorAssistResult> = {}): EditorAssistResult {
  return {
    ok: true,
    operation: "medical_rewrite",
    script: makeWords(98),
    summaryOfChanges: ["Texto ajustado"],
    titleAlignment: { status: "aligned" },
    medicalSafety: {
      meaningPreserved: true,
      newClaimsAdded: false,
      unsupportedPersonalExperienceAdded: false,
      requiresHumanReview: false,
      reasons: [],
    },
    warnings: [],
    durationAssessment: {
      durationSeconds: 45,
      wordCount: 98,
      estimatedSeconds: 40.83,
      estimatedSecondsDisplay: "~41s",
      targetWords: 108,
      hardLimitWords: 116,
      generationMinWords: 95,
      generationMaxWords: 101,
      status: "ideal",
      message: "Duração ideal para 45s.",
    },
    medicalReviewStatus: "recommended",
    qualityChecks: [],
    promptVersion: "medical-script-editor-v2",
    provider: "mock",
    model: "mock",
    cacheHit: false,
    retryCount: 0,
    schemaValid: true,
    technicalError: null,
    ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

function editorState(overrides: Record<string, unknown> = {}) {
  return {
    scriptId: "script-test",
    durationSeconds: 45 as const,
    humanReviewApproved: false,
    titleChoice: "current" as const,
    suggestedTitle: null,
    schemaValid: true,
    technicalError: null,
    previousScript: null,
    lastResult: null,
    scriptRevision: 1,
    finalSpeechHash: "a".repeat(64),
    approvedScriptRevision: null,
    approvedFinalSpeechHash: null,
    approvalHistory: [],
    contractVersion: "2.0.0",
    legacyFallback: false,
    ...overrides,
  };
}

function setStoreScript(script: Script = baseScript) {
  useStore.setState({
    scripts: [script],
    videoJobs: [],
    complianceRules: [],
  });
}

function getEditor() {
  const editor = document.querySelector("#roteiro-editar");
  if (!(editor instanceof HTMLElement)) throw new Error("Editor não renderizado");
  return editor;
}

async function expectNoCriticalAxeViolations() {
  const result = await axe.run(getEditor());
  expect(result.violations.filter((violation) => violation.impact === "critical")).toEqual([]);
}

async function renderEditor(script: Script = baseScript) {
  setStoreScript(script);
  const result = render(<RoteiroDetalhe />);
  await screen.findByLabelText("Fala final");
  await waitFor(() => expect(fetchScriptEditorState).toHaveBeenCalledWith("script-test"));
  return result;
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  setStoreScript();
  vi.mocked(fetchScriptEditorState).mockResolvedValue(editorState());
  vi.mocked(fetchProductionProfile).mockResolvedValue(null);
  vi.mocked(fetchHeyGenCatalog).mockResolvedValue({
    avatars: [],
    voices: [],
    defaultAvatarId: null,
  });
  vi.mocked(fetchAvatarSets).mockResolvedValue([]);
  vi.mocked(fetchMusicTracks).mockResolvedValue([]);
  vi.mocked(fetchScenePlan).mockResolvedValue(null);
  vi.mocked(fetchVisualPlan).mockResolvedValue(null);
  vi.mocked(fetchVideoSlideRender).mockResolvedValue(null);
  vi.mocked(saveScriptEditorState).mockImplementation(async (scriptId, state) => ({
    scriptId,
    ...state,
    scriptRevision: 1,
    finalSpeechHash: "a".repeat(64),
    approvedScriptRevision: null,
    approvedFinalSpeechHash: null,
    approvalHistory: [],
    contractVersion: "2.0.0",
  }));
  vi.mocked(saveScript).mockImplementation(async (script) => script);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("script editor React interactions", () => {
  it("starts clean with Save disabled", async () => {
    await renderEditor();
    expect(within(getEditor()).getByRole("button", { name: "Salvar" })).toBeDisabled();
  });

  it.each([
    [10, 24, 26],
    [15, 36, 39],
    [30, 72, 78],
    [45, 108, 116],
    [60, 144, 155],
  ] as const)("covers the %ss preset boundaries", async (seconds, target, hardLimit) => {
    await renderEditor();
    const user = userEvent.setup();
    const editor = getEditor();
    const textarea = within(editor).getByLabelText("Fala final");

    await user.click(within(editor).getByRole("button", { name: `${seconds}s` }));
    expect(within(editor).getByRole("button", { name: `Ajustar para ${seconds}s` })).toBeEnabled();

    fireEvent.change(textarea, { target: { value: makeWords(target) } });
    expect(within(editor).getByText("Duração ideal")).toBeInTheDocument();
    expect(within(editor).getByText(new RegExp(`${target} palavras`))).toBeInTheDocument();

    fireEvent.change(textarea, { target: { value: makeWords(target + 1) } });
    expect(within(editor).getByText("Atenção ao ritmo")).toBeInTheDocument();

    fireEvent.change(textarea, { target: { value: makeWords(hardLimit + 1) } });
    expect(within(editor).getByText("Ajuste necessário")).toBeInTheDocument();
  });

  it.each([
    [108, "Duração ideal"],
    [109, "Atenção ao ritmo"],
    [117, "Ajuste necessário"],
  ] as const)("keeps Save enabled with %s words", async (wordCount, expectedStatus) => {
    await renderEditor();
    const editor = getEditor();
    fireEvent.change(within(editor).getByLabelText("Fala final"), {
      target: { value: makeWords(wordCount) },
    });

    expect(within(editor).getByText(expectedStatus)).toBeInTheDocument();
    expect(within(editor).getByRole("button", { name: "Salvar" })).toBeEnabled();
  });

  it("saves the final speech and restores it after remount", async () => {
    const firstRender = await renderEditor();
    const user = userEvent.setup();
    const nextSpeech = makeWords(109);
    fireEvent.change(within(getEditor()).getByLabelText("Fala final"), {
      target: { value: nextSpeech },
    });
    await user.click(within(getEditor()).getByRole("button", { name: "Salvar" }));

    await waitFor(() =>
      expect(saveScript).toHaveBeenCalledWith(
        expect.objectContaining({
          id: "script-test",
          textoFalado: nextSpeech,
          titulo: baseScript.titulo,
        }),
      ),
    );
    await waitFor(() =>
      expect(within(getEditor()).getByRole("button", { name: "Salvar" })).toBeDisabled(),
    );

    firstRender.unmount();
    render(<RoteiroDetalhe />);
    expect(await screen.findByLabelText("Fala final")).toHaveValue(
      `${nextSpeech}.\n\n${baseScript.outroText}`,
    );
  });

  it("blocks duplicate and incompatible AI actions while one request is active", async () => {
    const pending = deferred<EditorAssistResult>();
    vi.mocked(runScriptEditorAssist).mockReturnValue(pending.promise);
    await renderEditor();
    const user = userEvent.setup();
    const editor = getEditor();

    await user.click(within(editor).getByRole("button", { name: "Revisar com IA" }));
    expect(within(editor).getByRole("button", { name: "Revisando..." })).toBeDisabled();
    expect(within(editor).getByRole("button", { name: "Ajustar para 45s" })).toBeDisabled();
    expect(
      screen.getByText("Revisão com inteligência artificial em andamento."),
    ).toBeInTheDocument();
    expect(runScriptEditorAssist).toHaveBeenCalledTimes(1);

    await act(async () => pending.resolve(assistResult()));
    await waitFor(() =>
      expect(within(editor).getByRole("button", { name: "Revisar com IA" })).toBeEnabled(),
    );
  });

  it("preserves the text when fit duration returns a no-op", async () => {
    await renderEditor();
    const original = (within(getEditor()).getByLabelText("Fala final") as HTMLTextAreaElement)
      .value;
    vi.mocked(runScriptEditorAssist).mockResolvedValue(
      assistResult({
        operation: "fit_duration",
        script: original,
        noOp: true,
        message: "O roteiro já está na faixa confortável.",
      }),
    );
    await userEvent.click(within(getEditor()).getByRole("button", { name: "Ajustar para 45s" }));

    await waitFor(() =>
      expect(toastMock.info).toHaveBeenCalledWith("O roteiro já está na faixa confortável."),
    );
    expect(within(getEditor()).getByLabelText("Fala final")).toHaveValue(original);
    expect(
      within(getEditor()).queryByRole("button", { name: "Desfazer IA" }),
    ).not.toBeInTheDocument();
  });

  it("preserves the previous speech after an invalid AI response", async () => {
    await renderEditor();
    const original = (within(getEditor()).getByLabelText("Fala final") as HTMLTextAreaElement)
      .value;
    vi.mocked(runScriptEditorAssist).mockResolvedValue(
      assistResult({
        schemaValid: false,
        technicalError: "Resposta inválida.",
        warnings: ["JSON inválido"],
        script: "",
      }),
    );
    await userEvent.click(within(getEditor()).getByRole("button", { name: "Revisar com IA" }));

    const alert = await within(getEditor()).findByRole("alert");
    expect(alert).toHaveTextContent("Resposta inválida");
    expect(alert).toHaveFocus();
    const speech = within(getEditor()).getByLabelText("Fala final");
    expect(speech).toHaveValue(original);
    expect(speech).toHaveAttribute(
      "aria-describedby",
      "script-duration-feedback script-editor-error",
    );
    expect(runScriptEditorAssist).toHaveBeenCalledTimes(1);
    await expectNoCriticalAxeViolations();
  });

  it("ends loading and preserves the speech after a request timeout", async () => {
    await renderEditor();
    const original = (within(getEditor()).getByLabelText("Fala final") as HTMLTextAreaElement)
      .value;
    vi.mocked(runScriptEditorAssist).mockRejectedValue(new Error("Tempo limite excedido."));

    await userEvent.click(within(getEditor()).getByRole("button", { name: "Revisar com IA" }));

    expect(await within(getEditor()).findByRole("alert")).toHaveTextContent(
      "Tempo limite excedido",
    );
    expect(within(getEditor()).getByLabelText("Fala final")).toHaveValue(original);
    expect(within(getEditor()).getByRole("button", { name: "Revisar com IA" })).toBeEnabled();
    expect(runScriptEditorAssist).toHaveBeenCalledTimes(1);
  });

  it("undoes a valid AI edit exactly", async () => {
    await renderEditor();
    const original = makeWords(104);
    fireEvent.change(within(getEditor()).getByLabelText("Fala final"), {
      target: { value: original },
    });
    const changed = makeWords(96);
    vi.mocked(runScriptEditorAssist).mockResolvedValue(assistResult({ script: changed }));
    const user = userEvent.setup();

    await user.click(within(getEditor()).getByRole("button", { name: "Revisar com IA" }));
    await waitFor(() =>
      expect(within(getEditor()).getByLabelText("Fala final")).toHaveValue(changed),
    );
    await user.click(within(getEditor()).getByRole("button", { name: "Desfazer IA" }));

    expect(within(getEditor()).getByLabelText("Fala final")).toHaveValue(original);
    expect(within(getEditor()).getByRole("button", { name: "Salvar" })).toBeEnabled();
  });

  it("requires an explicit choice before applying a suggested title", async () => {
    const suggestion = "Novo título coerente";
    vi.mocked(runScriptEditorAssist).mockResolvedValue(
      assistResult({
        titleAlignment: {
          status: "possible_mismatch",
          suggestedTitle: suggestion,
          reason: "A fala mudou de foco.",
        },
      }),
    );
    await renderEditor();
    const user = userEvent.setup();
    const title = within(getEditor()).getByLabelText("Título");

    await user.click(within(getEditor()).getByRole("button", { name: "Revisar com IA" }));
    await screen.findByText("Possível desalinhamento de título");
    expect(title).toHaveValue(baseScript.titulo);
    await expectNoCriticalAxeViolations();

    await user.click(within(getEditor()).getByRole("button", { name: "Usar título sugerido" }));
    expect(title).toHaveValue(suggestion);
    await user.click(within(getEditor()).getByRole("button", { name: "Manter título atual" }));
    expect(title).toHaveValue(baseScript.titulo);
  });

  it("reopens medical review for AI output that requires human review", async () => {
    vi.mocked(fetchScriptEditorState).mockResolvedValue(editorState({ humanReviewApproved: true }));
    vi.mocked(runScriptEditorAssist).mockResolvedValue(
      assistResult({
        medicalSafety: {
          meaningPreserved: true,
          newClaimsAdded: true,
          unsupportedPersonalExperienceAdded: false,
          requiresHumanReview: true,
          reasons: ["Nova alegação numérica"],
        },
        medicalReviewStatus: "required",
      }),
    );
    await renderEditor();
    const user = userEvent.setup();
    await waitFor(() =>
      expect(
        within(getEditor()).getByRole("button", { name: "Reabrir revisão" }),
      ).toBeInTheDocument(),
    );

    await user.click(within(getEditor()).getByRole("button", { name: "Revisar com IA" }));
    expect(
      await within(getEditor()).findByRole("button", { name: "Aprovar revisão médica" }),
    ).toBeInTheDocument();
    await expectNoCriticalAxeViolations();
    await user.click(within(getEditor()).getByRole("button", { name: "Aprovar revisão médica" }));
    expect(
      within(getEditor()).getByRole("button", { name: "Reabrir revisão" }),
    ).toBeInTheDocument();
  });

  it("does not overwrite a newer manual edit with a stale AI response", async () => {
    const pending = deferred<EditorAssistResult>();
    vi.mocked(runScriptEditorAssist).mockReturnValue(pending.promise);
    await renderEditor();
    const user = userEvent.setup();
    const textarea = within(getEditor()).getByLabelText("Fala final");

    await user.click(within(getEditor()).getByRole("button", { name: "Revisar com IA" }));
    const newerSpeech = makeWords(101);
    fireEvent.change(textarea, { target: { value: newerSpeech } });
    await act(async () => pending.resolve(assistResult({ script: makeWords(99) })));

    expect(textarea).toHaveValue(newerSpeech);
    expect(
      await within(getEditor()).findByText("Resultado de IA desatualizado"),
    ).toBeInTheDocument();
    expect(toastMock.info).toHaveBeenCalledWith(
      "A fala mudou durante a revisão. O resultado antigo não foi aplicado.",
    );
  });

  it.each([
    ["ideal", 108],
    ["warning", 109],
    ["blocking", 117],
  ] as const)("has no critical axe violations in the %s duration state", async (_state, words) => {
    await renderEditor();
    fireEvent.change(within(getEditor()).getByLabelText("Fala final"), {
      target: { value: makeWords(words) },
    });
    await expectNoCriticalAxeViolations();
  });
});
