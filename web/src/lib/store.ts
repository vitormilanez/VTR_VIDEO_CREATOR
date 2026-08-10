import { create } from "zustand";
import { persist } from "zustand/middleware";
import {
  defaultSettings,
  type AppSettings,
  type CalendarPost,
  type Canal,
  type Idea,
  type PerformanceMetric,
  type Script,
  type Trend,
  type VideoJob,
  type VideoJobStatus,
} from "./mock-data";
import type { ComplianceRule } from "./compliance";

interface State {
  trends: Trend[];
  ideas: Idea[];
  scripts: Script[];
  videoJobs: VideoJob[];
  calendarPosts: CalendarPost[];
  performance: PerformanceMetric[];
  settings: AppSettings;
  complianceRules: ComplianceRule[];
  syncedAt: string | null;
  // acoes basicas
  addTrend: (t: Trend) => void;
  updateTrend: (id: string, patch: Partial<Trend>) => void;
  addIdea: (i: Idea) => void;
  updateIdea: (id: string, patch: Partial<Idea>) => void;
  addScript: (s: Script) => void;
  updateScript: (id: string, patch: Partial<Script>) => void;
  removeScript: (id: string) => void;
  addVideoJob: (v: VideoJob) => void;
  updateVideoJob: (id: string, patch: Partial<VideoJob>) => void;
  addCalendarPost: (p: CalendarPost) => void;
  updateCalendarPost: (id: string, patch: Partial<CalendarPost>) => void;
  setSettings: (s: AppSettings) => void;
  resetSeed: () => void;
  advanceVideoJob: (id: string) => VideoJobStatus | null;
  agendarPost: (input: {
    scriptId: string;
    videoJobId?: string;
    titulo: string;
    dataAgendada: string;
    canal: Canal;
  }) => string;
  marcarPublicado: (postId: string) => void;
  registrarMetricasFake: (postId: string) => void;
  // hidratacao a partir da API local (dados reais do Google Sheets)
  hydrate: (payload: Partial<HydratePayload> & { updatedAt?: string | null }) => void;
}

export interface HydratePayload {
  trends: Trend[];
  ideas: Idea[];
  scripts: Script[];
  videoJobs: VideoJob[];
  calendarPosts: CalendarPost[];
  performance: PerformanceMetric[];
  settings: AppSettings;
  complianceRules?: ComplianceRule[];
  updatedAt?: string | null;
}

// Estado inicial vazio: os dados reais chegam da API local (hydrate) no load.
const initial = {
  trends: [] as Trend[],
  ideas: [] as Idea[],
  scripts: [] as Script[],
  videoJobs: [] as VideoJob[],
  calendarPosts: [] as CalendarPost[],
  performance: [] as PerformanceMetric[],
  settings: defaultSettings,
  complianceRules: [] as ComplianceRule[],
  syncedAt: null as string | null,
};

const nextStatus: Record<VideoJobStatus, VideoJobStatus | null> = {
  fila: "processando",
  processando: "pronto",
  pronto: null,
  erro: "fila",
};

const nextProgresso: Record<VideoJobStatus, number> = {
  fila: 10,
  processando: 65,
  pronto: 100,
  erro: 0,
};

const LOCAL_SCRIPT_WRITE_TTL_MS = 2 * 60 * 1000;
const localScriptWrites = new Map<string, number>();

function markLocalScriptWrite(id: string) {
  localScriptWrites.set(id, Date.now());
}

function hasFreshLocalScriptWrite(id: string) {
  const writtenAt = localScriptWrites.get(id);
  if (!writtenAt) return false;
  if (Date.now() - writtenAt <= LOCAL_SCRIPT_WRITE_TTL_MS) return true;
  localScriptWrites.delete(id);
  return false;
}

function mergeHydratedScripts(incoming: Script[], current: Script[]) {
  const currentById = new Map(current.map((script) => [script.id, script]));
  return incoming.map((script) => {
    const local = currentById.get(script.id);
    return local && hasFreshLocalScriptWrite(script.id) ? local : script;
  });
}

function randomInt(min: number, max: number) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

export const useStore = create<State>()(
  persist(
    (set, get) => ({
      ...initial,
      addTrend: (t) => set((s) => ({ trends: [t, ...s.trends] })),
      updateTrend: (id, patch) =>
        set((s) => ({
          trends: s.trends.map((t) => (t.id === id ? { ...t, ...patch } : t)),
        })),
      addIdea: (i) =>
        set((s) => ({
          ideas: s.ideas.some((idea) => idea.id === i.id)
            ? s.ideas.map((idea) => (idea.id === i.id ? i : idea))
            : [i, ...s.ideas],
        })),
      updateIdea: (id, patch) =>
        set((s) => ({
          ideas: s.ideas.map((i) => (i.id === id ? { ...i, ...patch } : i)),
        })),
      addScript: (sc) =>
        set((s) => {
          markLocalScriptWrite(sc.id);
          return {
            scripts: s.scripts.some((script) => script.id === sc.id)
              ? s.scripts.map((script) => (script.id === sc.id ? sc : script))
              : [sc, ...s.scripts],
          };
        }),
      updateScript: (id, patch) =>
        set((s) => {
          markLocalScriptWrite(id);
          return {
            scripts: s.scripts.map((sc) => (sc.id === id ? { ...sc, ...patch } : sc)),
          };
        }),
      removeScript: (id) =>
        set((s) => ({
          scripts: s.scripts.filter((script) => script.id !== id),
        })),
      addVideoJob: (v) =>
        set((s) => ({
          videoJobs: s.videoJobs.some((job) => job.id === v.id)
            ? s.videoJobs.map((job) => (job.id === v.id ? v : job))
            : [v, ...s.videoJobs],
        })),
      updateVideoJob: (id, patch) =>
        set((s) => ({
          videoJobs: s.videoJobs.map((v) => (v.id === id ? { ...v, ...patch } : v)),
        })),
      addCalendarPost: (p) => set((s) => ({ calendarPosts: [p, ...s.calendarPosts] })),
      updateCalendarPost: (id, patch) =>
        set((s) => ({
          calendarPosts: s.calendarPosts.map((p) => (p.id === id ? { ...p, ...patch } : p)),
        })),
      setSettings: (settings) => set(() => ({ settings })),
      resetSeed: () => set(() => ({ ...initial })),
      hydrate: (payload) =>
        set((s) => ({
          trends: payload.trends ?? s.trends,
          ideas: payload.ideas ?? s.ideas,
          scripts: payload.scripts ? mergeHydratedScripts(payload.scripts, s.scripts) : s.scripts,
          videoJobs: payload.videoJobs ?? s.videoJobs,
          calendarPosts: payload.calendarPosts ?? s.calendarPosts,
          performance: payload.performance ?? s.performance,
          settings: payload.settings ?? s.settings,
          complianceRules: payload.complianceRules ?? s.complianceRules,
          syncedAt: payload.updatedAt ?? s.syncedAt,
        })),

      advanceVideoJob: (id) => {
        const state = get();
        const job = state.videoJobs.find((v) => v.id === id);
        if (!job) return null;
        const next = nextStatus[job.status];
        if (!next) return null;
        const patch: Partial<VideoJob> = {
          status: next,
          progresso: nextProgresso[next],
          atualizadoEm: new Date().toISOString(),
        };
        if (next === "pronto") {
          patch.videoUrl = `mock://heygen/${id}.mp4`;
          patch.thumbnailUrl = `mock://heygen/${id}.jpg`;
          patch.duracaoSegundos = randomInt(30, 90);
        }
        set((s) => ({
          videoJobs: s.videoJobs.map((v) => (v.id === id ? { ...v, ...patch } : v)),
        }));
        return next;
      },

      agendarPost: (input) => {
        const id = `p-${Math.random().toString(36).slice(2, 8)}`;
        const post: CalendarPost = {
          id,
          scriptId: input.scriptId,
          videoJobId: input.videoJobId,
          titulo: input.titulo,
          dataAgendada: input.dataAgendada,
          canal: input.canal,
          status: "agendado",
        };
        set((s) => ({ calendarPosts: [post, ...s.calendarPosts] }));
        return id;
      },

      marcarPublicado: (postId) => {
        set((s) => ({
          calendarPosts: s.calendarPosts.map((p) =>
            p.id === postId
              ? {
                  ...p,
                  status: "publicado",
                  publicadoEm: new Date().toISOString(),
                }
              : p,
          ),
        }));
      },

      registrarMetricasFake: (postId) => {
        const state = get();
        const existing = state.performance.find((m) => m.postId === postId);
        const views = randomInt(5000, 90000);
        const likes = Math.round(views * (randomInt(30, 80) / 1000));
        const comments = Math.round(likes * (randomInt(50, 150) / 1000));
        const shares = Math.round(likes * (randomInt(80, 220) / 1000));
        const saves = Math.round(likes * (randomInt(120, 260) / 1000));
        const metric: PerformanceMetric = {
          id: existing?.id ?? `m-${Math.random().toString(36).slice(2, 8)}`,
          postId,
          views,
          likes,
          comments,
          shares,
          saves,
          coletadoEm: new Date().toISOString(),
        };
        if (existing) {
          set((s) => ({
            performance: s.performance.map((m) => (m.id === existing.id ? metric : m)),
          }));
        } else {
          set((s) => ({ performance: [metric, ...s.performance] }));
        }
      },
    }),
    { name: "avc-store", version: 3 },
  ),
);

export const genId = (prefix: string) => `${prefix}-${Math.random().toString(36).slice(2, 8)}`;
