// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import type { ComponentType, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { routeSearch, toastMock } = vi.hoisted(() => ({
  routeSearch: {
    current: {
      videoJobId: "video-ready-1" as string | undefined,
      sourceName: "Vídeo pronto" as string | undefined,
    },
  },
  toastMock: {
    error: vi.fn(),
    info: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
  },
}));

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (config: Record<string, unknown>) => ({
    ...config,
    useSearch: () => routeSearch.current,
  }),
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

vi.mock("@/lib/api/local", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/local")>();
  return {
    ...actual,
    createLocalVideoKit: vi.fn(),
    createPostProduction: vi.fn(),
    createUploadedPostProduction: vi.fn(),
    fetchLocalVideoKitJobs: vi.fn(),
    fetchMusicTracks: vi.fn(),
    fetchPostProduction: vi.fn(),
    uploadLocalVideoKitSource: vi.fn(),
  };
});

import {
  createLocalVideoKit,
  createPostProduction,
  createUploadedPostProduction,
  fetchLocalVideoKitJobs,
  fetchMusicTracks,
  fetchPostProduction,
  uploadLocalVideoKitSource,
  type PostProductionJob,
} from "@/lib/api/local";
import { Route } from "./_app.kit-local";

const LocalVideoKitPage = (Route as unknown as { component: ComponentType }).component;

const queuedAnalysis: PostProductionJob = {
  id: "post-1234567890abcdef",
  kind: "post_production",
  videoJobId: "video-ready-1",
  status: "queued",
  progresso: 2,
  etapa: "Na fila para análise",
  criadoEm: "2026-08-16T12:00:00.000Z",
  atualizadoEm: "2026-08-16T12:00:00.000Z",
};

describe("Local video editor start gate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    routeSearch.current = {
      videoJobId: "video-ready-1",
      sourceName: "Vídeo pronto",
    };
    vi.mocked(fetchMusicTracks).mockResolvedValue([]);
    vi.mocked(fetchLocalVideoKitJobs).mockResolvedValue([]);
    vi.mocked(createPostProduction).mockResolvedValue(queuedAnalysis);
    vi.mocked(createUploadedPostProduction).mockResolvedValue({
      ...queuedAnalysis,
      videoJobId: null,
      uploadId: "kit-upload-1234567890abcdef",
      sourceName: "consulta.mp4",
    });
    vi.mocked(fetchPostProduction).mockResolvedValue(queuedAnalysis);
    vi.mocked(uploadLocalVideoKitSource).mockResolvedValue({
      uploadId: "kit-upload-1234567890abcdef",
      filename: "consulta.mp4",
      size: 2048,
    });
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:consulta"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
  });

  afterEach(() => cleanup());

  it("waits for explicit confirmation when opened from a finished production", async () => {
    const user = userEvent.setup();
    render(<LocalVideoKitPage />);

    expect(await screen.findByText("Aguardando sua definição")).toBeInTheDocument();
    expect(createLocalVideoKit).not.toHaveBeenCalled();
    expect(createPostProduction).not.toHaveBeenCalled();
    expect(fetchPostProduction).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /confirmar e iniciar preparação/i }));

    await waitFor(() =>
      expect(createPostProduction).toHaveBeenCalledWith("video-ready-1", false, {
        requireClaude: true,
        generatePack: true,
      }),
    );
    expect(createPostProduction).toHaveBeenCalledTimes(1);
  });

  it("makes the video identity optional", async () => {
    const user = userEvent.setup();
    render(<LocalVideoKitPage />);

    expect(await screen.findByText("Identidade do vídeo")).toBeInTheDocument();
    const identitySwitch = screen.getByRole("switch", { name: "Usar identidade no vídeo" });
    expect(identitySwitch).toBeChecked();
    expect(screen.getAllByText("Opcional").length).toBeGreaterThanOrEqual(4);

    await user.click(identitySwitch);

    expect(identitySwitch).not.toBeChecked();
    expect(screen.getByLabelText("Quem aparece")).toBeDisabled();
    expect(screen.getByLabelText("Identificação profissional")).toBeDisabled();
    expect(screen.getByLabelText("Título de abertura")).toBeDisabled();
  });

  it("uploads a local file passively and queues analysis only after confirmation", async () => {
    routeSearch.current = { videoJobId: undefined, sourceName: undefined };
    const user = userEvent.setup();
    render(<LocalVideoKitPage />);
    const input = document.getElementById("local-kit-video") as HTMLInputElement;
    const file = new File(["video"], "consulta.mp4", { type: "video/mp4" });

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(uploadLocalVideoKitSource).toHaveBeenCalledWith(file));
    expect(await screen.findByText("Aguardando sua definição")).toBeInTheDocument();
    expect(createLocalVideoKit).not.toHaveBeenCalled();
    expect(createUploadedPostProduction).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /confirmar e iniciar preparação/i }));

    await waitFor(() =>
      expect(createUploadedPostProduction).toHaveBeenCalledWith(
        "kit-upload-1234567890abcdef",
        "consulta.mp4",
      ),
    );
    expect(createUploadedPostProduction).toHaveBeenCalledTimes(1);
  });

  it("keeps the explicit confirmation state free of critical accessibility violations", async () => {
    render(<LocalVideoKitPage />);
    expect(await screen.findByText("Aguardando sua definição")).toBeInTheDocument();

    const result = await axe.run(document.body, {
      rules: { "color-contrast": { enabled: false } },
    });

    expect(result.violations.filter((violation) => violation.impact === "critical")).toEqual([]);
  });
});
