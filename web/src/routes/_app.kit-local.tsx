import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  AudioLines,
  BrainCircuit,
  Captions,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Copy,
  Download,
  Film,
  Image as ImageIcon,
  LoaderCircle,
  Mic2,
  Move,
  Palette,
  Plus,
  RefreshCcw,
  ScanLine,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
  Upload,
  WandSparkles,
} from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  createLocalVideoKit,
  createPostProduction,
  createUploadedPostProduction,
  fetchMusicTracks,
  fetchLocalVideoKit,
  fetchLocalVideoKitJobs,
  fetchPostProduction,
  fetchPostProductionArtifacts,
  fetchPostProductionPack,
  localVideoKitCoverUrl,
  localVideoKitInsertUrl,
  localVideoKitResultUrl,
  localVideoKitSourceUrl,
  replanPostProduction,
  retryLocalVideoKit,
  runPostProductionPreflight,
  updatePostProductionEvents,
  uploadLocalVideoKitSource,
  uploadLocalVideoKitInsert,
  videoFileUrl,
  type LocalVideoKitClaudeInserts,
  type LocalVideoKitClaudeModel,
  type LocalVideoKitClaudeModelId,
  type LocalVideoKitConfig,
  type LocalVideoKitFiveStack,
  type LocalVideoKitInsert,
  type LocalVideoKitInsertAsset,
  type LocalVideoKitJob,
  type MusicTrack,
  type GeneratedContentPack,
  type PostProductionArtifacts,
  type PostProductionJob,
  type VisualScreenPosition,
  type VisualTimelineEvent,
} from "@/lib/api/local";
import {
  createInsertFromAsset,
  createNextUnusedInsert,
  type InsertTimeField,
  updateInsertTime,
  validateLocalVideoKitInserts,
} from "@/lib/local-video-inserts";
import {
  MANUAL_VISUAL_TIMING,
  validateLocalVideoVisualTiming,
  type VisualTimingValidation,
} from "@/lib/local-video-visual-timing";
import {
  MEDICAL_DEFAULT_SAFE_CTA,
  MEDICAL_MINIMUM_END_CARD_SECONDS,
  MEDICAL_PUBLICATION_NOTICE,
} from "@/lib/medical-identity";

export const Route = createFileRoute("/_app/kit-local")({
  validateSearch: (search: Record<string, unknown>) => ({
    videoJobId:
      typeof search.videoJobId === "string" && search.videoJobId.trim()
        ? search.videoJobId.trim().slice(0, 160)
        : undefined,
    sourceName:
      typeof search.sourceName === "string" && search.sourceName.trim()
        ? search.sourceName.trim().slice(0, 300)
        : undefined,
  }),
  head: () => ({
    meta: [
      { title: "Editor de vídeo | AI Video Creator" },
      {
        name: "description",
        content: "Edite um vídeo local com identidade, inserts, legendas e acabamento.",
      },
    ],
  }),
  component: LocalVideoKitPage,
});

const DEFAULT_FIVE_STACK: LocalVideoKitFiveStack = {
  enabled: false,
  startSeconds: null,
  durationSeconds: 4.5,
  lines: [
    "GLP-1 — sinal de saciedade",
    "Amilina — controle da fome",
    "Esvaziamento gástrico mais lento",
    "Oral: ~13% em 12 semanas",
    "Injetável: 24,3% em 36 semanas",
  ],
};

const CLAUDE_MIDNIGHT_MODEL_SPECS: Array<{
  id: LocalVideoKitClaudeModelId;
  title: string;
  detail: string;
  fieldLabels: string[];
}> = [
  {
    id: "numberGlass",
    title: "Número em Vidro",
    detail: "Dado clínico grande, com número âmbar e suporte em vidro.",
    fieldLabels: ["Etiqueta", "Número", "Texto de apoio", "Detalhe"],
  },
  {
    id: "editorialClip",
    title: "Recorte Editorial",
    detail: "Cartela de notícia compacta para o lado do avatar.",
    fieldLabels: ["Editor", "Edição", "Manchete", "Resumo", "Rodapé"],
  },
  {
    id: "mechanismBars",
    title: "Barras de Mecanismo",
    detail: "Comparativo visual entre um alvo e dois receptores.",
    fieldLabels: ["Etiqueta", "Primeira barra", "Segunda barra", "Nota"],
  },
  {
    id: "evidenceStamp",
    title: "Selo de Evidência",
    detail: "Status clínico em cinco etapas, sem esconder o vídeo.",
    fieldLabels: [
      "Etiqueta",
      "Selo",
      "Status",
      "Pré-clínica",
      "Fase 1",
      "Fase 2",
      "Fase 3",
      "Aprovação",
      "Aviso",
    ],
  },
  {
    id: "glossarySource",
    title: "Glossário + Fonte",
    detail: "Definição no alto e fonte persistente no rodapé.",
    fieldLabels: ["Etiqueta", "Termo", "Definição", "Rótulo da fonte", "Fonte", "Nota"],
  },
];

const DEFAULT_CLAUDE_INSERTS: LocalVideoKitClaudeInserts = {
  numberGlass: {
    enabled: false,
    startSeconds: null,
    durationSeconds: 3.8,
    fields: [
      "DADO CLÍNICO",
      "24,3%",
      "de redução de peso em 36 semanas",
      "formulação injetável · fase inicial",
    ],
  },
  editorialClip: {
    enabled: false,
    startSeconds: null,
    durationSeconds: 4.2,
    fields: [
      "BOLETIM CLÍNICO",
      "N.º 04",
      "Uma molécula, dois receptores",
      "A Amycretin foi desenvolvida para agir no GLP-1 e na amilina ao mesmo tempo.",
      "Ensaios iniciais · em desenvolvimento",
    ],
  },
  mechanismBars: {
    enabled: false,
    startSeconds: null,
    durationSeconds: 3.6,
    fields: [
      "UM ALVO VS. DOIS",
      "Terapias atuais · 1 receptor",
      "Amycretin · GLP-1 + amilina",
      "Esquema de mecanismos — não é comparação de eficácia",
    ],
  },
  evidenceStamp: {
    enabled: false,
    startSeconds: null,
    durationSeconds: 4.4,
    fields: [
      "STATUS REGULATÓRIO",
      "AMYCRETIN",
      "Em desenvolvimento clínico",
      "PRÉ-CLÍN.",
      "FASE 1",
      "FASE 2",
      "FASE 3",
      "APROV.",
      "Ainda não disponível comercialmente.",
    ],
  },
  glossarySource: {
    enabled: false,
    startSeconds: null,
    durationSeconds: 4.2,
    fields: [
      "O TERMO",
      "Amilina",
      "Hormônio liberado junto com a insulina. Sinaliza saciedade ao cérebro e desacelera o esvaziamento do estômago.",
      "FONTE",
      "Ensaios clínicos iniciais · fase 1/2",
      "Resultados preliminares, grupos específicos",
    ],
  },
};

function normalizeFiveStack(value?: LocalVideoKitFiveStack): LocalVideoKitFiveStack {
  const sourceLines = Array.isArray(value?.lines) ? value.lines : [];
  return {
    ...DEFAULT_FIVE_STACK,
    ...value,
    lines: DEFAULT_FIVE_STACK.lines.map((fallback, index) => sourceLines[index] || fallback),
  };
}

function normalizeClaudeInserts(
  value?: Partial<LocalVideoKitClaudeInserts>,
): LocalVideoKitClaudeInserts {
  return Object.fromEntries(
    Object.entries(DEFAULT_CLAUDE_INSERTS).map(([id, fallback]) => {
      const current = value?.[id as LocalVideoKitClaudeModelId];
      const sourceFields = Array.isArray(current?.fields) ? current.fields : [];
      return [
        id,
        {
          ...fallback,
          ...current,
          startSeconds:
            typeof current?.startSeconds === "number" && Number.isFinite(current.startSeconds)
              ? Math.max(0, current.startSeconds)
              : null,
          durationSeconds: Math.min(
            8,
            Math.max(1, Number(current?.durationSeconds ?? fallback.durationSeconds ?? 4)),
          ),
          fields: fallback.fields.map((field, index) => sourceFields[index] || field),
        },
      ];
    }),
  ) as LocalVideoKitClaudeInserts;
}

function disableClaudeInserts(
  value?: Partial<LocalVideoKitClaudeInserts>,
): LocalVideoKitClaudeInserts {
  return Object.fromEntries(
    Object.entries(normalizeClaudeInserts(value)).map(([id, model]) => [
      id,
      { ...model, enabled: false },
    ]),
  ) as LocalVideoKitClaudeInserts;
}

const DEFAULT_CONFIG: LocalVideoKitConfig = {
  name: "Dr. Guilherme Martins",
  role: "Médico",
  title: "4 suplementos para melhorar seu rendimento",
  subtitle: "O que realmente ajuda na atividade física",
  sectionNumber: "Ponto 01",
  sectionTitle: "Cafeína, creatina e desempenho",
  cta: MEDICAL_DEFAULT_SAFE_CTA,
  site: "@drguilhermemartins",
  accent: "#c8e05a",
  sectionStartSeconds: null,
  sectionDurationSeconds: 3,
  sectionTransition: "fade",
  musicTrackId: null,
  musicVolume: 0.12,
  includeCaptions: true,
  captionStyle: "dynamic",
  captionPosition: "safe_bottom",
  highlightKeywords: true,
  duckMusicDuringSpeech: true,
  motionPreset: "subtle",
  enhanceVoice: true,
  outroTailSeconds: 10,
  includeOpening: true,
  includeLowerThird: true,
  includeSection: true,
  includeOutro: true,
  manualVisualsEnabled: false,
  inserts: [],
  fiveStack: DEFAULT_FIVE_STACK,
  claudeInserts: DEFAULT_CLAUDE_INSERTS,
};

const CAPTION_STYLES: Array<{
  id: LocalVideoKitConfig["captionStyle"];
  name: string;
  detail: string;
}> = [
  {
    id: "dynamic",
    name: "Dinâmica",
    detail: "Alto contraste e palavras-chave em destaque.",
  },
  {
    id: "clean",
    name: "Clean clínico",
    detail: "Bloco discreto para conteúdos técnicos.",
  },
  {
    id: "editorial",
    name: "Editorial",
    detail: "Serifa elegante com ritmo mais calmo.",
  },
];

const CAPTION_POSITIONS: Array<{
  id: LocalVideoKitConfig["captionPosition"];
  name: string;
}> = [
  { id: "upper", name: "Superior" },
  { id: "center", name: "Centro" },
  { id: "safe_bottom", name: "Inferior seguro" },
];

const MOTION_PRESETS: Array<{
  id: LocalVideoKitConfig["motionPreset"];
  name: string;
  detail: string;
  strength: string;
}> = [
  {
    id: "subtle",
    name: "Natural",
    detail: "Aproximação suave no rosto, com entrada e saída delicadas.",
    strength: "14%",
  },
  {
    id: "social",
    name: "Social",
    detail: "Chega mais perto do rosto com movimento mais presente.",
    strength: "22%",
  },
  {
    id: "none",
    name: "Sem zoom",
    detail: "Mantém o enquadramento original durante toda a fala.",
    strength: "0%",
  },
];

const STANDARD_VISUAL_MODELS: Array<{
  id: VisualTimelineEvent["interactionType"];
  name: string;
}> = [
  { id: "caption_emphasis", name: "Destaque simples" },
  { id: "definition_card", name: "Definição" },
  { id: "number_card", name: "Número ou dado" },
  { id: "comparison_card", name: "Comparação" },
  { id: "progressive_list", name: "Lista" },
  { id: "quote_card", name: "Citação" },
  { id: "evidence_card", name: "Evidência" },
  { id: "supporting_visual", name: "Apoio visual" },
  { id: "cta_card", name: "Chamada para ação" },
];

const DEFAULT_VISUAL_APPEARANCE = {
  screenPosition: "top_right" as VisualScreenPosition,
  backgroundColor: "#073e4b",
  backgroundOpacity: 0.9,
};

const VISUAL_SCREEN_POSITIONS: Array<{
  id: VisualScreenPosition;
  label: string;
}> = [
  { id: "top_left", label: "Superior esquerdo" },
  { id: "top_center", label: "Superior centro" },
  { id: "top_right", label: "Superior direito" },
  { id: "center_left", label: "Centro esquerdo" },
  { id: "center", label: "Centro" },
  { id: "center_right", label: "Centro direito" },
  { id: "bottom_left", label: "Inferior esquerdo" },
  { id: "bottom_center", label: "Inferior centro" },
  { id: "bottom_right", label: "Inferior direito" },
];

type EditorFlowState =
  | "choose"
  | "uploading"
  | "upload_failed"
  | "configure"
  | "queueing"
  | "transcribing"
  | "analyzing"
  | "analysis_failed"
  | "review"
  | "fix_visuals"
  | "fix_clips"
  | "ready"
  | "rendering"
  | "render_failed"
  | "done";

function LocalVideoKitPage() {
  const { videoJobId, sourceName } = Route.useSearch();
  const fileInput = useRef<HTMLInputElement>(null);
  const sourceSelection = useRef(0);
  const analysisStartInFlight = useRef(false);
  const [file, setFile] = useState<File | null>(null);
  const [sourcePreview, setSourcePreview] = useState<string | null>(null);
  const [sourceDuration, setSourceDuration] = useState<number | null>(null);
  const [sourceUpload, setSourceUpload] = useState<Awaited<
    ReturnType<typeof uploadLocalVideoKitSource>
  > | null>(null);
  const [uploadingSource, setUploadingSource] = useState(false);
  const [sourceUploadError, setSourceUploadError] = useState<string | null>(null);
  const [analysisJob, setAnalysisJob] = useState<PostProductionJob | null>(null);
  const [analysisArtifacts, setAnalysisArtifacts] = useState<PostProductionArtifacts | null>(null);
  const [analysisPack, setAnalysisPack] = useState<GeneratedContentPack | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [startingAnalysis, setStartingAnalysis] = useState(false);
  const [retryingAnalysis, setRetryingAnalysis] = useState(false);
  const [visualReviewConfirmed, setVisualReviewConfirmed] = useState(false);
  const [activeEditorTab, setActiveEditorTab] = useState("base");
  const [config, setConfig] = useState<LocalVideoKitConfig>(DEFAULT_CONFIG);
  const [musicTracks, setMusicTracks] = useState<MusicTrack[]>([]);
  const [musicLibraryState, setMusicLibraryState] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const [musicLibraryRetry, setMusicLibraryRetry] = useState(0);
  const [job, setJob] = useState<LocalVideoKitJob | null>(null);
  const [renderConfigDirty, setRenderConfigDirty] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [retryingRender, setRetryingRender] = useState(false);
  const [uploadingInsert, setUploadingInsert] = useState(false);
  const configTouched = useRef(false);

  useEffect(() => {
    let cancelled = false;
    setMusicLibraryState("loading");
    void fetchMusicTracks()
      .then((tracks) => {
        if (cancelled) return;
        setMusicTracks(tracks);
        setMusicLibraryState("ready");
      })
      .catch(() => {
        if (cancelled) return;
        setMusicTracks([]);
        setMusicLibraryState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [musicLibraryRetry]);

  useEffect(() => {
    if (videoJobId) return;
    const selectionAtStart = sourceSelection.current;
    void fetchLocalVideoKitJobs()
      .then((jobs) => {
        if (sourceSelection.current !== selectionAtStart) return;
        const savedId = window.localStorage.getItem("local-video-kit:last-job");
        const recovered = jobs.find((item) => item.id === savedId) || jobs[0];
        if (recovered) {
          setJob(recovered);
          setRenderConfigDirty(false);
          setVisualReviewConfirmed(false);
          if (recovered.analysisJobId) {
            void fetchPostProduction(recovered.analysisJobId)
              .then((current) => {
                if (sourceSelection.current !== selectionAtStart) return;
                setAnalysisJob(current);
                setAnalysisError(
                  current.status === "failed"
                    ? current.erro || "A análise visual recuperada falhou."
                    : null,
                );
              })
              .catch(() => {
                if (sourceSelection.current !== selectionAtStart) return;
                setAnalysisError("Não foi possível recuperar a direção visual deste projeto.");
              });
          }
          if (!configTouched.current) {
            const recoveredManualVisualsEnabled = recovered.config.manualVisualsEnabled === true;
            setConfig({
              ...DEFAULT_CONFIG,
              ...recovered.config,
              manualVisualsEnabled: recoveredManualVisualsEnabled,
              fiveStack: recoveredManualVisualsEnabled
                ? recovered.config.fiveStack
                : {
                    ...normalizeFiveStack(recovered.config.fiveStack),
                    enabled: false,
                  },
              claudeInserts: recoveredManualVisualsEnabled
                ? recovered.config.claudeInserts
                : disableClaudeInserts(recovered.config.claudeInserts),
              includeOutro: true,
              outroTailSeconds: Math.max(
                MEDICAL_MINIMUM_END_CARD_SECONDS,
                recovered.config.outroTailSeconds ?? 10,
              ),
            });
          }
        }
      })
      .catch(() => undefined);
  }, [videoJobId]);

  useEffect(() => {
    if (!videoJobId) return;
    sourceSelection.current += 1;
    setFile(null);
    setSourcePreview((current) => {
      if (current) URL.revokeObjectURL(current);
      return null;
    });
    setSourceUpload(null);
    setSourceUploadError(null);
    setAnalysisJob(null);
    setAnalysisArtifacts(null);
    setAnalysisPack(null);
    setAnalysisError(null);
    setVisualReviewConfirmed(false);
    setStartingAnalysis(false);
    setUploadingSource(false);
    setSourceDuration(null);
    setJob(null);
    setRenderConfigDirty(false);
    setConfig((current) => ({
      ...current,
      title: (sourceName || current.title).slice(0, 120),
      subtitle: "Informação clara, direto ao ponto.",
      sectionNumber: "Destaque",
      sectionTitle: "Ponto principal",
      inserts: [],
      fiveStack: DEFAULT_FIVE_STACK,
      claudeInserts: DEFAULT_CLAUDE_INSERTS,
    }));
  }, [sourceName, videoJobId]);

  const activeJobId = job?.id;
  const activeJobStatus = job?.status;

  useEffect(() => {
    if (!activeJobId || !activeJobStatus || !["fila", "processando"].includes(activeJobStatus)) {
      return;
    }
    const timer = window.setInterval(() => {
      void fetchLocalVideoKit(activeJobId)
        .then((current) => {
          setJob(current);
          if (current.status === "pronto") toast.success("Kit gráfico aplicado localmente.");
          if (current.status === "erro") toast.error(current.erro || "A edição local falhou.");
        })
        .catch(() => undefined);
    }, 1800);
    return () => window.clearInterval(timer);
  }, [activeJobId, activeJobStatus]);

  const activeAnalysisId = analysisJob?.id;
  const activeAnalysisStatus = analysisJob?.status;

  useEffect(() => {
    if (
      !activeAnalysisId ||
      !activeAnalysisStatus ||
      !["queued", "transcribing", "planning", "preflight", "generating_pack"].includes(
        activeAnalysisStatus,
      )
    ) {
      return;
    }
    const refresh = () => {
      void fetchPostProduction(activeAnalysisId)
        .then((current) => {
          setAnalysisJob(current);
          if (current.status === "failed") {
            setAnalysisError(current.erro || "A análise visual do Claude falhou.");
          }
        })
        .catch(() => undefined);
    };
    refresh();
    const timer = window.setInterval(refresh, 1600);
    return () => window.clearInterval(timer);
  }, [activeAnalysisId, activeAnalysisStatus]);

  useEffect(() => {
    if (
      !activeAnalysisId ||
      !activeAnalysisStatus ||
      !["needs_review", "preview_ready"].includes(activeAnalysisStatus)
    ) {
      return;
    }
    let cancelled = false;
    void fetchPostProductionArtifacts(activeAnalysisId)
      .then((artifacts) => {
        if (cancelled) return;
        setAnalysisArtifacts(artifacts);
        setAnalysisError(null);
      })
      .catch((error) => {
        if (cancelled) return;
        setAnalysisError(
          error instanceof Error ? error.message : "Não foi possível abrir a análise visual.",
        );
      });
    if (analysisJob?.packStatus === "ready") {
      void fetchPostProductionPack(activeAnalysisId)
        .then((pack) => {
          if (!cancelled) setAnalysisPack(pack);
        })
        .catch(() => {
          if (!cancelled) setAnalysisPack(null);
        });
    }
    return () => {
      cancelled = true;
    };
  }, [activeAnalysisId, activeAnalysisStatus, analysisJob?.packStatus]);

  useEffect(
    () => () => {
      if (sourcePreview) URL.revokeObjectURL(sourcePreview);
    },
    [sourcePreview],
  );

  function acceptSourceUpload(uploaded: Awaited<ReturnType<typeof uploadLocalVideoKitSource>>) {
    setSourceUpload(uploaded);
    setAnalysisJob(null);
    setAnalysisArtifacts(null);
    setAnalysisPack(null);
    setAnalysisError(null);
    setVisualReviewConfirmed(false);
    toast.success("Vídeo carregado. Ajuste a edição e confirme quando quiser iniciar.");
  }

  async function selectFile(selected?: File) {
    if (!selected) return;
    if (!selected.type.startsWith("video/")) {
      toast.error("Selecione um arquivo de vídeo.");
      return;
    }
    const selection = sourceSelection.current + 1;
    sourceSelection.current = selection;
    if (sourcePreview) URL.revokeObjectURL(sourcePreview);
    setFile(selected);
    setSourceDuration(null);
    setSourcePreview(URL.createObjectURL(selected));
    setSourceUpload(null);
    setSourceUploadError(null);
    setAnalysisJob(null);
    setAnalysisArtifacts(null);
    setAnalysisPack(null);
    setAnalysisError(null);
    setVisualReviewConfirmed(false);
    setStartingAnalysis(false);
    setJob(null);
    setRenderConfigDirty(false);
    setActiveEditorTab("base");
    setConfig((current) => ({
      ...current,
      inserts: [],
      fiveStack: DEFAULT_FIVE_STACK,
      claudeInserts: DEFAULT_CLAUDE_INSERTS,
      sectionStartSeconds: null,
    }));
    setUploadingSource(true);
    try {
      const uploaded = await uploadLocalVideoKitSource(selected);
      if (sourceSelection.current !== selection) return;
      acceptSourceUpload(uploaded);
    } catch (error) {
      if (sourceSelection.current !== selection) return;
      const message =
        error instanceof Error ? error.message : "Não foi possível carregar o vídeo no editor.";
      setSourceUploadError(message);
      toast.error(message);
    } finally {
      if (sourceSelection.current === selection) setUploadingSource(false);
    }
  }

  async function retrySourceUpload() {
    if (!file) return;
    const selection = sourceSelection.current;
    setUploadingSource(true);
    setSourceUploadError(null);
    try {
      const uploaded = await uploadLocalVideoKitSource(file);
      if (sourceSelection.current !== selection) return;
      acceptSourceUpload(uploaded);
    } catch (error) {
      if (sourceSelection.current !== selection) return;
      const message =
        error instanceof Error ? error.message : "Não foi possível carregar o vídeo no editor.";
      setSourceUploadError(message);
      toast.error(message);
    } finally {
      if (sourceSelection.current === selection) setUploadingSource(false);
    }
  }

  function update<K extends keyof LocalVideoKitConfig>(key: K, value: LocalVideoKitConfig[K]) {
    configTouched.current = true;
    setVisualReviewConfirmed(false);
    setRenderConfigDirty(true);
    setConfig((current) => ({ ...current, [key]: value }));
  }

  function updateIdentityEnabled(enabled: boolean) {
    configTouched.current = true;
    setVisualReviewConfirmed(false);
    setRenderConfigDirty(true);
    setConfig((current) => ({
      ...current,
      includeOpening: enabled,
      includeLowerThird: enabled,
    }));
  }

  const fiveStack = normalizeFiveStack(config.fiveStack);
  const claudeInserts = normalizeClaudeInserts(config.claudeInserts);
  const manualVisualsEnabled = config.manualVisualsEnabled === true;
  const activeManualVisualCount =
    Number(fiveStack.enabled) +
    Object.values(claudeInserts).filter((model) => model.enabled).length;

  function updateFiveStack(patch: Partial<LocalVideoKitFiveStack>) {
    update("fiveStack", { ...fiveStack, ...patch });
  }

  function updateFiveStackLine(index: number, value: string) {
    updateFiveStack({
      lines: fiveStack.lines.map((line, lineIndex) => (lineIndex === index ? value : line)),
    });
  }

  function updateClaudeInsert(
    id: LocalVideoKitClaudeModelId,
    patch: Partial<LocalVideoKitClaudeModel>,
  ) {
    update("claudeInserts", {
      ...claudeInserts,
      [id]: { ...claudeInserts[id], ...patch },
    });
  }

  function updateClaudeInsertField(id: LocalVideoKitClaudeModelId, index: number, value: string) {
    updateClaudeInsert(id, {
      fields: claudeInserts[id].fields.map((field, fieldIndex) =>
        fieldIndex === index ? value : field,
      ),
    });
  }

  function nextInsertId() {
    return `insert-${globalThis.crypto?.randomUUID?.() || Date.now().toString(36)}`;
  }

  async function selectInsertFiles(selected: File[]) {
    if (!selected.length) return;
    const validFiles = selected.filter((file) => file.type.startsWith("video/"));
    if (!validFiles.length) {
      toast.error("Selecione arquivos de vídeo para usar como inserts.");
      return;
    }
    if (validFiles.length !== selected.length) {
      toast.warning("Arquivos que não eram vídeos foram ignorados.");
    }
    const availableSlots = Math.max(0, 24 - config.inserts.length);
    if (!availableSlots) {
      toast.info("O limite de 24 trechos de insert já foi alcançado.");
      return;
    }
    const filesToUpload = validFiles.slice(0, availableSlots);
    if (filesToUpload.length < validFiles.length) {
      toast.warning(`Somente ${availableSlots} vídeos cabem na timeline atual.`);
    }
    setUploadingInsert(true);
    try {
      const uploadedAssets: LocalVideoKitInsertAsset[] = [];
      for (const selectedFile of filesToUpload) {
        uploadedAssets.push(await uploadLocalVideoKitInsert(selectedFile));
      }
      configTouched.current = true;
      setRenderConfigDirty(true);
      setConfig((current) => {
        const remainingSlots = Math.max(0, 24 - current.inserts.length);
        let lastEnd = Math.max(2, ...current.inserts.map((insert) => insert.timelineEndSeconds));
        const placements = uploadedAssets.slice(0, remainingSlots).map((asset) => {
          const placement = createInsertFromAsset(asset, nextInsertId(), lastEnd + 1);
          lastEnd = placement.timelineEndSeconds;
          return placement;
        });
        return { ...current, inserts: [...current.inserts, ...placements] };
      });
      toast.success(
        uploadedAssets.length === 1
          ? "Vídeo adicionado aos inserts."
          : `${uploadedAssets.length} vídeos adicionados aos inserts.`,
      );
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível enviar os inserts.");
    } finally {
      setUploadingInsert(false);
    }
  }

  function changeInsertTime(id: string, field: InsertTimeField, value: number) {
    update(
      "inserts",
      config.inserts.map((insert) =>
        insert.id === id ? updateInsertTime(insert, field, value) : insert,
      ),
    );
  }

  function removeInsert(id: string) {
    update(
      "inserts",
      config.inserts.filter((insert) => insert.id !== id),
    );
  }

  function reuseNextInsert(insert: LocalVideoKitInsert) {
    const next = createNextUnusedInsert(insert, config.inserts, nextInsertId());
    if (!next) {
      toast.info("Todo o clipe já foi usado. Envie outro arquivo para continuar.");
      return;
    }
    update("inserts", [...config.inserts, next]);
    toast.success(`Próximo trecho iniciado em ${next.sourceStartSeconds.toFixed(1)}s.`);
  }

  function updateAnalysisEvent(id: string, patch: Partial<VisualTimelineEvent>) {
    const appearanceKeys: Set<string> = new Set([
      "screenPosition",
      "backgroundColor",
      "backgroundOpacity",
    ]);
    const appearanceOnly =
      Object.keys(patch).length > 0 && Object.keys(patch).every((key) => appearanceKeys.has(key));
    if (!appearanceOnly) setVisualReviewConfirmed(false);
    setRenderConfigDirty(true);
    setAnalysisArtifacts((current) =>
      current
        ? {
            ...current,
            timeline: {
              ...current.timeline,
              events: current.timeline.events.map((event) =>
                event.id === id ? { ...event, ...patch } : event,
              ),
            },
          }
        : current,
    );
  }

  async function startAnalysis() {
    if (analysisStartInFlight.current || analysisJob) return;
    if (!sourceUpload && !videoJobId) {
      toast.error("Escolha um vídeo antes de iniciar a preparação.");
      return;
    }
    const selection = sourceSelection.current;
    analysisStartInFlight.current = true;
    setStartingAnalysis(true);
    setAnalysisError(null);
    setAnalysisArtifacts(null);
    setAnalysisPack(null);
    setVisualReviewConfirmed(false);
    try {
      const current = sourceUpload
        ? await createUploadedPostProduction(sourceUpload.uploadId, sourceUpload.filename)
        : await createPostProduction(videoJobId!, false, {
            requireClaude: true,
            generatePack: true,
          });
      if (sourceSelection.current !== selection) return;
      setAnalysisJob(current);
      toast.success("Preparação confirmada e adicionada à fila.");
    } catch (error) {
      if (sourceSelection.current !== selection) return;
      const message =
        error instanceof Error ? error.message : "Não foi possível adicionar a preparação à fila.";
      setAnalysisError(message);
      toast.error(message);
    } finally {
      analysisStartInFlight.current = false;
      if (sourceSelection.current === selection) setStartingAnalysis(false);
    }
  }

  async function retryVisualAnalysis() {
    if (!sourceUpload && !analysisJob && !videoJobId) return;
    setRetryingAnalysis(true);
    setAnalysisError(null);
    setAnalysisArtifacts(null);
    setAnalysisPack(null);
    setVisualReviewConfirmed(false);
    try {
      const current = analysisJob
        ? await replanPostProduction(analysisJob.id)
        : sourceUpload
          ? await createUploadedPostProduction(sourceUpload.uploadId, sourceUpload.filename)
          : await createPostProduction(videoJobId!, false, {
              requireClaude: true,
              generatePack: true,
            });
      setAnalysisJob(current);
      toast.success("Claude reiniciou a análise visual e a geração do Pack.");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Não foi possível reiniciar a análise.";
      setAnalysisError(message);
      toast.error(message);
    } finally {
      setRetryingAnalysis(false);
    }
  }

  async function retryRender() {
    if (!job) return;
    setRetryingRender(true);
    try {
      const current = await retryLocalVideoKit(job.id);
      setJob(current);
      setRenderConfigDirty(false);
      toast.success("Render local reiniciado com monitoramento de progresso.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível reiniciar o render.");
    } finally {
      setRetryingRender(false);
    }
  }

  async function applyKit() {
    if (!file && !videoJobId && !job) {
      toast.error("Escolha um vídeo local primeiro.");
      return;
    }
    if (uploadingSource) {
      toast.info("Aguarde o vídeo terminar de carregar.");
      return;
    }
    if ((file || videoJobId) && !analysisJob) {
      toast.error("A análise visual do Claude precisa ser concluída antes do render.");
      return;
    }
    if (analysisJob && !["needs_review", "preview_ready"].includes(analysisJob.status)) {
      toast.info("Aguarde o Claude concluir a análise e o Pack.");
      return;
    }
    if (analysisReady && analysisArtifacts && !visualReviewConfirmed) {
      setActiveEditorTab("visuais");
      toast.info("Revise e aprove a direção visual antes de gerar o vídeo.");
      return;
    }
    if (visualTimingIssues.length) {
      setActiveEditorTab("visuais");
      toast.error(visualTimingIssues[0]);
      return;
    }
    const insertErrors = validateLocalVideoKitInserts(config.inserts, sourceDuration);
    if (insertErrors.length) {
      toast.error(insertErrors[0]);
      return;
    }
    setSubmitting(true);
    try {
      let upload = file ? sourceUpload : null;
      if (file && !upload) {
        setUploadingSource(true);
        setSourceUploadError(null);
        try {
          upload = await uploadLocalVideoKitSource(file);
          acceptSourceUpload(upload);
        } finally {
          setUploadingSource(false);
        }
      }
      if (analysisJob && analysisArtifacts) {
        const saved = await updatePostProductionEvents(
          analysisJob.id,
          analysisArtifacts.timeline.events.map((event) => ({
            id: event.id,
            enabled: event.enabled,
            startMs: event.startMs,
            endMs: event.endMs,
            timingSource: event.timingSource || "transcript",
            screenPosition: event.screenPosition || DEFAULT_VISUAL_APPEARANCE.screenPosition,
            backgroundColor: event.backgroundColor || DEFAULT_VISUAL_APPEARANCE.backgroundColor,
            backgroundOpacity:
              event.backgroundOpacity ?? DEFAULT_VISUAL_APPEARANCE.backgroundOpacity,
            interactionType: event.interactionType,
            visualText: event.visualText,
            reviewStatus: event.enabled ? "approved" : "rejected",
          })),
        );
        setAnalysisJob(saved.job);
        setAnalysisArtifacts((current) =>
          current ? { ...current, timeline: saved.timeline } : current,
        );
        const checked = await runPostProductionPreflight(analysisJob.id);
        setAnalysisJob(checked.job);
        if (!checked.ok) {
          const blocker = checked.report.findings.find(
            (finding) => finding.classification === "BLOCKER",
          );
          throw new Error(blocker?.message || "O plano visual tem conflitos para corrigir.");
        }
      }
      const sectionTitle = config.sectionTitle.trim();
      const created = await createLocalVideoKit({
        uploadId: upload?.uploadId,
        videoJobId: file ? undefined : videoJobId,
        sourceKitJobId: file || videoJobId ? undefined : job?.id,
        analysisJobId: analysisJob?.id,
        sourceName: file?.name || sourceName || job?.sourceName || `video-${videoJobId}.mp4`,
        config: {
          ...config,
          sectionTitle,
          includeSection: Boolean(sectionTitle && config.includeSection),
        },
      });
      window.localStorage.setItem("local-video-kit:last-job", created.id);
      setJob(created);
      setRenderConfigDirty(false);
      toast.success("Edição local iniciada. Nenhum crédito externo será usado.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível aplicar o kit.");
    } finally {
      setSubmitting(false);
    }
  }

  const working =
    submitting || retryingRender || job?.status === "fila" || job?.status === "processando";
  const transcriptionRunning = Boolean(
    analysisJob && ["queued", "transcribing"].includes(analysisJob.status),
  );
  const claudeRunning = Boolean(
    analysisJob && ["planning", "preflight", "generating_pack"].includes(analysisJob.status),
  );
  const analysisRunning = transcriptionRunning || claudeRunning;
  const legacyProject = Boolean(job && !job.analysisJobId && !file && !videoJobId);
  const captionsReady = analysisJob?.captionsStatus === "ready" || legacyProject;
  const analysisReady = Boolean(
    analysisJob
      ? ["needs_review", "preview_ready"].includes(analysisJob.status) && analysisArtifacts
      : legacyProject,
  );
  const analysisFailed = Boolean(analysisError || analysisJob?.status === "failed");
  const sourceReady = file ? Boolean(sourceUpload) : Boolean(videoJobId || job);
  const reviewRequired = Boolean(analysisJob && analysisArtifacts);
  const reviewReady = !reviewRequired || visualReviewConfirmed;
  const insertErrors = validateLocalVideoKitInserts(config.inserts, sourceDuration);
  const visualTimelineDuration =
    sourceDuration ??
    job?.duracaoSegundos ??
    (analysisArtifacts?.transcript.durationMs ? analysisArtifacts.transcript.durationMs / 1000 : 0);
  const visualTimingConfig = { ...config, fiveStack, claudeInserts };
  const visualTimingValidation = validateLocalVideoVisualTiming(
    analysisArtifacts?.timeline.events || [],
    visualTimingConfig,
    visualTimelineDuration,
  );
  const visualTimingIssues = visualTimingValidation.issues;
  const canRender =
    sourceReady &&
    analysisReady &&
    reviewReady &&
    !insertErrors.length &&
    !visualTimingIssues.length;
  const hasSectionContent = Boolean(config.sectionTitle.trim());
  const identityEnabled = config.includeOpening || config.includeLowerThird;
  const selectedMusicTrack = musicTracks.find((track) => track.id === config.musicTrackId) || null;
  const originalUrl =
    sourcePreview ||
    (videoJobId ? videoFileUrl(videoJobId) : job ? localVideoKitSourceUrl(job.id) : null);
  const enabledVisualCount =
    analysisArtifacts?.timeline.events.filter((event) => event.enabled).length ?? 0;
  const preparationConfirmed = Boolean(startingAnalysis || analysisJob || legacyProject || job);
  const flowState: EditorFlowState = uploadingSource
    ? "uploading"
    : sourceUploadError
      ? "upload_failed"
      : startingAnalysis
        ? "queueing"
        : analysisFailed && Boolean(file || videoJobId)
          ? "analysis_failed"
          : transcriptionRunning
            ? "transcribing"
            : claudeRunning ||
                (sourceReady && !analysisReady && Boolean(analysisJob || job?.analysisJobId))
              ? "analyzing"
              : analysisReady && reviewRequired && !visualReviewConfirmed
                ? "review"
                : sourceReady && analysisReady && reviewReady && visualTimingIssues.length
                  ? "fix_visuals"
                  : sourceReady && analysisReady && reviewReady && insertErrors.length
                    ? "fix_clips"
                    : working
                      ? "rendering"
                      : job?.status === "erro" && !renderConfigDirty
                        ? "render_failed"
                        : job?.status === "pronto" && !renderConfigDirty
                          ? "done"
                          : canRender
                            ? "ready"
                            : sourceReady && !analysisJob && Boolean(file || videoJobId)
                              ? "configure"
                              : "choose";
  const currentStep =
    flowState === "choose" ||
    flowState === "uploading" ||
    flowState === "upload_failed" ||
    flowState === "configure"
      ? 1
      : flowState === "queueing" || flowState === "transcribing"
        ? 2
        : flowState === "analyzing" ||
            flowState === "analysis_failed" ||
            flowState === "review" ||
            flowState === "fix_visuals"
          ? 3
          : 4;
  const renderSummary = [
    config.includeCaptions ? "Legendas automáticas" : "Sem legendas",
    enabledVisualCount
      ? `${enabledVisualCount} ${enabledVisualCount === 1 ? "visual do Claude" : "visuais do Claude"}`
      : "Sem visual extra",
    config.inserts.length
      ? `${config.inserts.length} ${config.inserts.length === 1 ? "trecho de apoio" : "trechos de apoio"}`
      : "Sem clipes de apoio",
    config.motionPreset === "none"
      ? "Enquadramento fixo"
      : config.motionPreset === "social"
        ? "Movimento social"
        : "Movimento suave",
  ];
  const preparationSummary = [
    "Transcrição local para análise",
    config.includeCaptions ? "Legendas no vídeo final" : "Sem legendas no vídeo final",
    "Direção visual do Claude + Pack",
    config.inserts.length
      ? `${config.inserts.length} ${config.inserts.length === 1 ? "clipe escolhido" : "clipes escolhidos"}`
      : "Sem clipes de apoio",
  ];

  return (
    <AppShell
      title="Editor de vídeo"
      actions={
        <div className="hidden items-center gap-1.5 rounded-full border border-status-success/30 bg-status-success/10 px-3 py-1 text-[11px] font-medium text-status-success md:flex">
          <ShieldCheck className="h-3.5 w-3.5" /> Render local · direção Claude
        </div>
      }
    >
      <div className="mx-auto max-w-[1600px] space-y-5 pb-6">
        <section className="overflow-hidden rounded-2xl border bg-card shadow-sm">
          <div className="grid gap-5 p-4 sm:p-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-primary">
                <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
                Editor local
              </div>
              <h2 className="mt-2 font-display text-xl font-semibold tracking-tight">
                Carregue, defina a edição e confirme para iniciar
              </h2>
              <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                Entrar no editor ou carregar um vídeo não inicia nenhum processamento. Ajuste o que
                quiser e confirme; só então entram na fila a transcrição local, a direção do Claude
                e o Pack. O render final continua dependendo da sua revisão.
              </p>
            </div>
            <ol
              className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4"
              aria-label="Etapas da edição"
            >
              {(
                [
                  ["1", "Definir", preparationConfirmed],
                  ["2", "Legendas", captionsReady],
                  ["3", "Claude", analysisReady && reviewReady],
                  ["4", "Render", job?.status === "pronto"],
                ] as Array<[string, string, boolean]>
              ).map(([number, label, complete]) => {
                const current = !complete && currentStep === Number(number);
                return (
                  <li
                    key={number}
                    aria-current={current ? "step" : undefined}
                    className={`flex min-w-20 items-center gap-2 rounded-lg border px-3 py-2 ${
                      complete
                        ? "border-status-success/25 bg-status-success/8"
                        : current
                          ? "border-primary/30 bg-primary/8"
                          : "border-transparent bg-muted/35 text-muted-foreground"
                    }`}
                  >
                    <span
                      className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
                        complete
                          ? "bg-status-success text-white"
                          : current
                            ? "bg-primary text-primary-foreground"
                            : "bg-muted text-muted-foreground"
                      }`}
                    >
                      {complete ? "✓" : number}
                    </span>
                    <span className="font-medium">{label}</span>
                  </li>
                );
              })}
            </ol>
          </div>
          <div className="border-t bg-muted/15 p-4 sm:p-5">
            <input
              ref={fileInput}
              id="local-kit-video"
              type="file"
              accept="video/mp4,video/quicktime,video/webm"
              aria-label="Selecionar vídeo local"
              className="hidden"
              onChange={(event) => {
                const selected = event.target.files?.[0];
                event.currentTarget.value = "";
                void selectFile(selected);
              }}
            />
            <div className="flex flex-col gap-3 sm:flex-row sm:items-stretch">
              <button
                type="button"
                onClick={() => fileInput.current?.click()}
                className="group flex min-h-20 min-w-0 flex-1 cursor-pointer items-center gap-3 rounded-xl border border-dashed bg-background p-4 text-left transition-colors duration-200 hover:border-primary/45 hover:bg-muted/35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/8 transition-colors group-hover:bg-primary/12">
                  {uploadingSource ? (
                    <LoaderCircle className="h-5 w-5 animate-spin text-primary" />
                  ) : sourceReady ? (
                    <CheckCircle2 className="h-5 w-5 text-status-success" />
                  ) : (
                    <Upload className="h-5 w-5 text-primary" />
                  )}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold">
                    {file?.name ||
                      (videoJobId ? sourceName || `Vídeo ${videoJobId}` : null) ||
                      job?.sourceName ||
                      "Selecionar vídeo para editar"}
                  </span>
                  <span
                    className={`mt-1 block text-xs ${
                      sourceUploadError ? "text-destructive" : "text-muted-foreground"
                    }`}
                    aria-live="polite"
                  >
                    {uploadingSource
                      ? "Carregando o vídeo no editor..."
                      : sourceUploadError
                        ? sourceUploadError
                        : file && sourceUpload
                          ? analysisRunning
                            ? `${analysisJob?.etapa || "Processando transcrição e direção visual"} · ${analysisJob?.progresso ?? 0}%`
                            : analysisFailed
                              ? "Vídeo enviado · a análise precisa ser reiniciada"
                              : analysisReady
                                ? `Análise e Pack prontos · ${formatFileSize(sourceUpload.size)}`
                                : `Vídeo carregado · aguardando sua confirmação · ${formatFileSize(sourceUpload.size)}`
                          : videoJobId
                            ? analysisRunning
                              ? `${analysisJob?.etapa || "Processando transcrição e direção visual"} · ${analysisJob?.progresso ?? 0}%`
                              : analysisFailed
                                ? "Carregado da Produção · a análise precisa ser reiniciada"
                                : analysisReady
                                  ? "Carregado da Produção · análise e Pack prontos"
                                  : "Carregado da Produção · aguardando sua confirmação"
                            : job
                              ? job.status === "erro"
                                ? "Tentativa anterior recuperada · clique para trocar"
                                : job.status === "pronto"
                                  ? "Projeto concluído recuperado · clique para trocar"
                                  : "Render local recuperado · clique para trocar"
                              : "MP4, MOV ou WebM · até 2 GB"}
                  </span>
                </span>
                <span className="hidden shrink-0 rounded-md border bg-card px-3 py-1.5 text-xs font-medium sm:block">
                  {sourceReady ? "Trocar vídeo" : "Escolher arquivo"}
                </span>
              </button>
            </div>
          </div>
        </section>

        <EditorNextStepCard
          state={flowState}
          progress={
            flowState === "transcribing" || flowState === "analyzing"
              ? (analysisJob?.progresso ?? 4)
              : flowState === "rendering"
                ? (job?.progresso ?? 3)
                : undefined
          }
          stage={
            flowState === "transcribing" || flowState === "analyzing"
              ? analysisJob?.etapa
              : job?.etapa
          }
          captionCueCount={analysisJob?.captionCueCount ?? 0}
          visualCount={enabledVisualCount}
          summary={flowState === "configure" ? preparationSummary : renderSummary}
          job={job}
          busy={startingAnalysis || retryingAnalysis || retryingRender}
          error={
            flowState === "upload_failed"
              ? sourceUploadError
              : flowState === "analysis_failed"
                ? humanizeAnalysisError(analysisError || analysisJob?.erro || "")
                : flowState === "render_failed"
                  ? humanizeRenderError(job?.erro || "")
                  : flowState === "fix_visuals"
                    ? visualTimingIssues[0]
                    : flowState === "fix_clips"
                      ? insertErrors[0]
                      : null
          }
          onChoose={() => fileInput.current?.click()}
          onRetryUpload={() => void retrySourceUpload()}
          onStartAnalysis={() => void startAnalysis()}
          onRetryAnalysis={() => void retryVisualAnalysis()}
          onReview={() => setActiveEditorTab("visuais")}
          onFixVisuals={() => setActiveEditorTab("visuais")}
          onFixClips={() => setActiveEditorTab("inserts")}
          onGenerate={() => void applyKit()}
          onRetryRender={() => void retryRender()}
        />

        <div className="grid items-start gap-5 xl:grid-cols-[minmax(420px,500px)_minmax(0,1fr)] 2xl:grid-cols-[520px_minmax(0,1fr)]">
          <aside className="min-w-0 self-start">
            <Tabs value={activeEditorTab} onValueChange={setActiveEditorTab}>
              <TabsList className="grid h-auto w-full grid-cols-4 gap-1 rounded-xl border bg-card p-1.5 shadow-sm">
                <TabsTrigger value="base" className="min-h-11 px-2 text-xs">
                  Identidade
                </TabsTrigger>
                <TabsTrigger value="inserts" className="min-h-11 px-2 text-xs">
                  Clipes
                </TabsTrigger>
                <TabsTrigger value="visuais" className="min-h-11 px-2 text-xs">
                  Visuais IA
                </TabsTrigger>
                <TabsTrigger value="acabamento" className="min-h-11 px-2 text-xs">
                  Estilo
                </TabsTrigger>
              </TabsList>

              <TabsContent value="base" className="mt-4">
                <Card className="overflow-hidden">
                  <CardHeader className="border-b bg-muted/20 pb-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="space-y-1.5">
                        <div className="flex flex-wrap items-center gap-2">
                          <CardTitle className="text-base">Identidade do vídeo</CardTitle>
                          <span className="rounded-full border bg-background px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                            Opcional
                          </span>
                        </div>
                        <p className="text-xs leading-relaxed text-muted-foreground">
                          Desative para não aplicar abertura nem identificação durante o vídeo.
                        </p>
                      </div>
                      <Switch
                        checked={identityEnabled}
                        onCheckedChange={updateIdentityEnabled}
                        aria-label="Usar identidade no vídeo"
                      />
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <TextField
                      id="kit-name"
                      label="Quem aparece"
                      value={config.name}
                      onChange={(value) => update("name", value)}
                      optional
                      disabled={!identityEnabled}
                    />
                    <TextField
                      id="kit-role"
                      label="Identificação profissional"
                      value={config.role}
                      onChange={(value) => update("role", value)}
                      optional
                      disabled={!identityEnabled}
                    />
                    <TextField
                      id="kit-title"
                      label="Título de abertura"
                      value={config.title}
                      onChange={(value) => update("title", value)}
                      optional
                      disabled={!identityEnabled}
                    />
                    <details className="group overflow-hidden rounded-xl border bg-muted/10">
                      <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring">
                        <span className="flex items-center gap-2">
                          <SlidersHorizontal className="h-4 w-4 text-primary" />
                          Personalizar textos, marca e música
                        </span>
                        <span className="text-xs font-medium text-primary group-open:hidden">
                          Abrir
                        </span>
                        <span className="hidden text-xs font-medium text-primary group-open:inline">
                          Fechar
                        </span>
                      </summary>
                      <div className="space-y-4 border-t bg-background p-4">
                        <TextField
                          id="kit-subtitle"
                          label="Subtítulo"
                          value={config.subtitle}
                          onChange={(value) => update("subtitle", value)}
                        />
                        <TextField
                          id="kit-section"
                          label="Cartela de tópico"
                          value={config.sectionTitle}
                          onChange={(value) => update("sectionTitle", value)}
                        />
                        {!hasSectionContent ? (
                          <p className="-mt-2 text-[11px] leading-relaxed text-muted-foreground">
                            Sem texto, nenhuma cartela de tópico será criada.
                          </p>
                        ) : null}
                        {hasSectionContent ? (
                          <div className="grid grid-cols-2 gap-3">
                            <div className="space-y-1.5">
                              <Label htmlFor="kit-section-start">Cartela entra aos</Label>
                              <Input
                                id="kit-section-start"
                                type="number"
                                min={3}
                                step={0.5}
                                placeholder="Automático"
                                value={config.sectionStartSeconds ?? ""}
                                onChange={(event) =>
                                  update(
                                    "sectionStartSeconds",
                                    event.target.value ? Number(event.target.value) : null,
                                  )
                                }
                              />
                              <p className="text-[11px] text-muted-foreground">segundos do vídeo</p>
                            </div>
                            <div className="space-y-1.5">
                              <Label htmlFor="kit-section-duration">Fica na tela por</Label>
                              <Input
                                id="kit-section-duration"
                                type="number"
                                min={0.5}
                                max={120}
                                step={0.5}
                                value={config.sectionDurationSeconds ?? 3}
                                onChange={(event) =>
                                  update(
                                    "sectionDurationSeconds",
                                    event.target.value ? Number(event.target.value) : 3,
                                  )
                                }
                              />
                              <p className="text-[11px] text-muted-foreground">segundos</p>
                            </div>
                          </div>
                        ) : null}

                        <div className="space-y-1.5">
                          <Label htmlFor="kit-accent">Destaque</Label>
                          <Input
                            id="kit-accent"
                            type="color"
                            value={config.accent}
                            onChange={(event) => update("accent", event.target.value)}
                            className="h-10 w-full cursor-pointer p-1"
                          />
                        </div>

                        <div className={`grid gap-3 ${hasSectionContent ? "sm:grid-cols-2" : ""}`}>
                          {hasSectionContent ? (
                            <div className="space-y-1.5">
                              <Label htmlFor="kit-section-transition">Transição da cartela</Label>
                              <select
                                id="kit-section-transition"
                                value={config.sectionTransition ?? "fade"}
                                onChange={(event) =>
                                  update(
                                    "sectionTransition",
                                    event.target.value as LocalVideoKitConfig["sectionTransition"],
                                  )
                                }
                                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus:ring-2 focus:ring-ring"
                              >
                                <option value="fade">Fade suave</option>
                                <option value="slide_up">Deslizar de baixo</option>
                                <option value="none">Corte direto</option>
                              </select>
                            </div>
                          ) : null}
                          <div className="space-y-1.5">
                            <div className="flex items-center justify-between gap-2">
                              <Label htmlFor="kit-music">Música de fundo</Label>
                              {musicLibraryState === "error" ? (
                                <button
                                  type="button"
                                  onClick={() => setMusicLibraryRetry((value) => value + 1)}
                                  className="inline-flex cursor-pointer items-center gap-1 text-[11px] font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                >
                                  <RefreshCcw className="h-3 w-3" /> Tentar novamente
                                </button>
                              ) : null}
                            </div>
                            <select
                              id="kit-music"
                              value={config.musicTrackId ?? ""}
                              onChange={(event) =>
                                update("musicTrackId", event.target.value || null)
                              }
                              disabled={musicLibraryState !== "ready"}
                              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus:ring-2 focus:ring-ring"
                            >
                              <option value="">
                                {musicLibraryState === "loading"
                                  ? "Carregando músicas..."
                                  : musicLibraryState === "error"
                                    ? "Não foi possível carregar as músicas"
                                    : musicTracks.length
                                      ? "Sem música"
                                      : "Nenhuma música local encontrada"}
                              </option>
                              {musicTracks.map((track) => (
                                <option key={track.id} value={track.id}>
                                  {track.name} · {track.mood}
                                </option>
                              ))}
                            </select>
                          </div>
                        </div>

                        {selectedMusicTrack ? (
                          <div className="space-y-1.5 rounded-lg border bg-muted/20 p-3">
                            <div className="flex items-center justify-between gap-3">
                              <Label htmlFor="kit-music-preview">Prévia da música</Label>
                              <span className="truncate text-xs text-muted-foreground">
                                {selectedMusicTrack.name}
                              </span>
                            </div>
                            <audio
                              id="kit-music-preview"
                              controls
                              preload="none"
                              src={selectedMusicTrack.url}
                              className="h-9 w-full"
                            />
                          </div>
                        ) : null}

                        {config.musicTrackId ? (
                          <div className="space-y-1.5">
                            <div className="flex items-center justify-between gap-3">
                              <Label htmlFor="kit-music-volume">Volume da música</Label>
                              <span className="text-xs tabular-nums text-muted-foreground">
                                {Math.round((config.musicVolume ?? 0.12) * 100)}%
                              </span>
                            </div>
                            <Input
                              id="kit-music-volume"
                              type="range"
                              min={3}
                              max={25}
                              step={1}
                              value={Math.round((config.musicVolume ?? 0.12) * 100)}
                              onChange={(event) =>
                                update("musicVolume", Number(event.target.value) / 100)
                              }
                              className="cursor-pointer px-0"
                            />
                            <p className="text-[11px] text-muted-foreground">
                              A trilha entra baixa e preserva o áudio original.
                            </p>
                          </div>
                        ) : null}
                      </div>
                    </details>
                  </CardContent>
                </Card>
              </TabsContent>
              <TabsContent value="inserts" className="mt-4">
                <InsertEditorCard
                  inserts={config.inserts}
                  uploading={uploadingInsert}
                  errors={insertErrors}
                  onFiles={selectInsertFiles}
                  onChangeTime={changeInsertTime}
                  onReuse={reuseNextInsert}
                  onRemove={removeInsert}
                />
              </TabsContent>
              <TabsContent value="visuais" className="mt-4 space-y-4">
                {visualTimingIssues.length ? (
                  <div
                    className="rounded-xl border border-destructive/35 bg-destructive/[0.045] p-4"
                    role="alert"
                    aria-live="polite"
                  >
                    <div className="flex items-start gap-3">
                      <CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
                      <div className="min-w-0">
                        <p className="text-sm font-semibold">Ajuste os tempos antes do render</p>
                        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                          Há {visualTimingIssues.length}{" "}
                          {visualTimingIssues.length === 1
                            ? "conflito visual"
                            : "conflitos visuais"}
                          . Corrija a entrada ou a saída destacada abaixo.
                        </p>
                        <ul className="mt-2 space-y-1 text-[11px] leading-relaxed text-destructive">
                          {visualTimingIssues.slice(0, 4).map((issue) => (
                            <li key={issue}>• {issue}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  </div>
                ) : null}

                <ClaudeVisualAnalysisCard
                  job={analysisJob}
                  artifacts={analysisArtifacts}
                  pack={analysisPack}
                  error={analysisError}
                  starting={startingAnalysis}
                  retrying={retryingAnalysis}
                  hasSource={sourceReady}
                  existingProjectWithoutAnalysis={legacyProject}
                  reviewConfirmed={visualReviewConfirmed}
                  timingValidation={visualTimingValidation}
                  videoDurationSeconds={visualTimelineDuration}
                  onEventChange={updateAnalysisEvent}
                  onRetry={() => void retryVisualAnalysis()}
                  onConfirm={() => {
                    setVisualReviewConfirmed(true);
                    setRenderConfigDirty(true);
                    toast.success("Direção visual aprovada. O vídeo está pronto para gerar.");
                    window.requestAnimationFrame(() => {
                      document
                        .getElementById("editor-next-step")
                        ?.scrollIntoView({ behavior: "smooth", block: "center" });
                    });
                  }}
                />

                <details className="group overflow-hidden rounded-xl border bg-card">
                  <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring">
                    <span>
                      Modelos manuais avançados
                      <span className="mt-0.5 block text-xs font-normal text-muted-foreground">
                        Use apenas quando quiser acrescentar uma peça fora da direção do Claude.
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-2 text-xs font-medium">
                      <span
                        className={`rounded-full px-2 py-1 ${
                          manualVisualsEnabled
                            ? "bg-primary/10 text-primary"
                            : "bg-muted text-muted-foreground"
                        }`}
                      >
                        {manualVisualsEnabled
                          ? `${activeManualVisualCount} ${activeManualVisualCount === 1 ? "ativo" : "ativos"}`
                          : "Desativados"}
                      </span>
                      <span className="text-primary group-open:hidden">Abrir</span>
                      <span className="hidden text-primary group-open:inline">Fechar</span>
                    </span>
                  </summary>
                  <div className="space-y-4 border-t bg-muted/10 p-3">
                    <div className="flex items-start justify-between gap-4 rounded-xl border bg-background p-4">
                      <div className="min-w-0">
                        <Label htmlFor="manual-visuals-enabled" className="text-sm font-semibold">
                          Usar complementos manuais
                        </Label>
                        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                          Desligado por padrão. Ative somente para adicionar peças além das
                          sugestões do Claude.
                        </p>
                      </div>
                      <Switch
                        id="manual-visuals-enabled"
                        checked={manualVisualsEnabled}
                        onCheckedChange={(enabled) => update("manualVisualsEnabled", enabled)}
                        aria-label="Usar complementos manuais"
                      />
                    </div>

                    {manualVisualsEnabled ? (
                      <>
                        <FiveStackEditorCard
                          value={fiveStack}
                          onChange={updateFiveStack}
                          onLineChange={updateFiveStackLine}
                        />

                        <ClaudeMidnightModelsCard
                          value={claudeInserts}
                          timingIssuesByItemId={visualTimingValidation.issuesByItemId}
                          videoDurationSeconds={visualTimelineDuration}
                          onChange={updateClaudeInsert}
                          onFieldChange={updateClaudeInsertField}
                        />
                      </>
                    ) : (
                      <div className="rounded-xl border border-dashed bg-background/70 px-4 py-5 text-center">
                        <p className="text-sm font-medium">
                          Somente a direção do Claude será usada
                        </p>
                        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                          Modelos antigos ou ocultos não entram no render e não geram conflitos.
                        </p>
                      </div>
                    )}
                  </div>
                </details>
              </TabsContent>
              <TabsContent value="acabamento" className="mt-4 space-y-4">
                <Card className="border-status-success/25 bg-status-success/[0.035]">
                  <CardContent className="p-4">
                    <div className="flex items-start gap-3">
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-status-success/10">
                        <CheckCircle2 className="h-4 w-4 text-status-success" />
                      </span>
                      <div className="min-w-0">
                        <div className="text-sm font-semibold">Acabamento recomendado</div>
                        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                          Já está pronto para uso. Abra os controles abaixo somente se quiser mudar
                          o estilo.
                        </p>
                        <div className="mt-3 flex flex-wrap gap-1.5">
                          {[
                            config.includeCaptions ? "Legendas ligadas" : "Sem legendas",
                            config.enhanceVoice ? "Voz aprimorada" : "Áudio original",
                            config.motionPreset === "none" ? "Sem movimento" : "Movimento suave",
                            config.musicTrackId ? "Com música" : "Sem música",
                          ].map((item) => (
                            <span
                              key={item}
                              className="rounded-full border bg-background px-2.5 py-1 text-[11px] font-medium text-muted-foreground"
                            >
                              {item}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <details className="group overflow-hidden rounded-xl border bg-card">
                  <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring">
                    <span>
                      Personalizar legendas, áudio e movimento
                      <span className="mt-0.5 block text-xs font-normal text-muted-foreground">
                        Controles opcionais para quem quiser ajustar o acabamento.
                      </span>
                    </span>
                    <span className="text-xs font-medium text-primary group-open:hidden">
                      Abrir
                    </span>
                    <span className="hidden text-xs font-medium text-primary group-open:inline">
                      Fechar
                    </span>
                  </summary>
                  <div className="space-y-4 border-t bg-muted/10 p-3">
                    <Card className="overflow-hidden">
                      <CardHeader className="border-b bg-muted/20 pb-3">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <CardTitle className="flex items-center gap-2 text-base">
                              <Captions className="h-4 w-4 text-primary" />
                              Legendas e áudio
                            </CardTitle>
                            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                              Sincronização automática em PT-BR, feita neste computador.
                            </p>
                          </div>
                          <span className="shrink-0 rounded-full border border-status-success/25 bg-status-success/8 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-status-success">
                            Local
                          </span>
                        </div>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        <div className="flex items-center justify-between gap-3 rounded-xl border bg-muted/20 p-3">
                          <div>
                            <div className="text-sm font-semibold">Legendas automáticas</div>
                            <div className="mt-0.5 text-xs text-muted-foreground">
                              Frases curtas, sincronizadas com a fala.
                            </div>
                          </div>
                          <Switch
                            checked={config.includeCaptions}
                            onCheckedChange={(value) => update("includeCaptions", value)}
                            aria-label="Aplicar legendas automáticas"
                          />
                        </div>

                        {config.includeCaptions ? (
                          <>
                            <CaptionPreview config={config} />

                            <div className="space-y-2">
                              <Label>Estilo da legenda</Label>
                              <div className="space-y-2">
                                {CAPTION_STYLES.map((style) => {
                                  const selected = config.captionStyle === style.id;
                                  return (
                                    <button
                                      key={style.id}
                                      type="button"
                                      aria-pressed={selected}
                                      onClick={() => update("captionStyle", style.id)}
                                      className={`flex w-full cursor-pointer items-start gap-3 rounded-lg border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                                        selected
                                          ? "border-primary/60 bg-primary/8"
                                          : "bg-background hover:border-primary/30 hover:bg-muted/35"
                                      }`}
                                    >
                                      <span
                                        className="mt-0.5 h-3 w-3 shrink-0 rounded-full border-2"
                                        style={{
                                          borderColor: selected ? config.accent : undefined,
                                          backgroundColor: selected ? config.accent : "transparent",
                                        }}
                                      />
                                      <span>
                                        <span className="block text-sm font-semibold">
                                          {style.name}
                                        </span>
                                        <span className="mt-0.5 block text-xs text-muted-foreground">
                                          {style.detail}
                                        </span>
                                      </span>
                                    </button>
                                  );
                                })}
                              </div>
                            </div>

                            <div className="space-y-2">
                              <Label>Posição no vídeo</Label>
                              <div className="grid grid-cols-3 rounded-lg border bg-muted/25 p-1">
                                {CAPTION_POSITIONS.map((position) => (
                                  <button
                                    key={position.id}
                                    type="button"
                                    aria-pressed={config.captionPosition === position.id}
                                    onClick={() => update("captionPosition", position.id)}
                                    className={`min-h-9 cursor-pointer rounded-md px-2 text-[11px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                                      config.captionPosition === position.id
                                        ? "bg-background text-foreground shadow-sm"
                                        : "text-muted-foreground hover:text-foreground"
                                    }`}
                                  >
                                    {position.name}
                                  </button>
                                ))}
                              </div>
                              <p className="text-[11px] leading-relaxed text-muted-foreground">
                                “Inferior seguro” evita os controles e textos das redes sociais.
                              </p>
                            </div>

                            <PieceSwitch
                              label="Palavras-chave"
                              detail="Destaca automaticamente os termos mais importantes"
                              checked={config.highlightKeywords}
                              onCheckedChange={(value) => update("highlightKeywords", value)}
                            />
                          </>
                        ) : null}

                        {config.musicTrackId ? (
                          <PieceSwitch
                            label="Mixagem inteligente"
                            detail="Abaixa a música durante a fala e recupera nas pausas"
                            checked={config.duckMusicDuringSpeech}
                            onCheckedChange={(value) => update("duckMusicDuringSpeech", value)}
                          />
                        ) : (
                          <div className="flex items-center gap-3 rounded-lg border border-dashed px-3 py-3 text-xs leading-relaxed text-muted-foreground">
                            <AudioLines className="h-4 w-4 shrink-0" />
                            Escolha uma música acima para ativar a mixagem inteligente.
                          </div>
                        )}
                      </CardContent>
                    </Card>

                    <Card className="overflow-hidden">
                      <CardHeader className="border-b bg-muted/20 pb-3">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <CardTitle className="flex items-center gap-2 text-base">
                              <ScanLine className="h-4 w-4 text-primary" />
                              Ritmo e movimento
                            </CardTitle>
                            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                              Aproximações suaves priorizam o rosto e ajudam a manter a atenção.
                            </p>
                          </div>
                          <span className="shrink-0 rounded-full border border-primary/20 bg-primary/8 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-primary">
                            Automático
                          </span>
                        </div>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        <MotionPreview preset={config.motionPreset} accent={config.accent} />

                        <div className="space-y-2">
                          <Label>Ritmo do enquadramento</Label>
                          <div className="space-y-2">
                            {MOTION_PRESETS.map((preset) => {
                              const selected = config.motionPreset === preset.id;
                              return (
                                <button
                                  key={preset.id}
                                  type="button"
                                  aria-pressed={selected}
                                  onClick={() => update("motionPreset", preset.id)}
                                  className={`flex w-full cursor-pointer items-start justify-between gap-3 rounded-lg border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                                    selected
                                      ? "border-primary/60 bg-primary/8"
                                      : "bg-background hover:border-primary/30 hover:bg-muted/35"
                                  }`}
                                >
                                  <span className="flex items-start gap-3">
                                    <span
                                      className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border"
                                      style={{
                                        borderColor: selected
                                          ? accentWithOpacity(config.accent, "99")
                                          : undefined,
                                        backgroundColor: selected
                                          ? accentWithOpacity(config.accent, "18")
                                          : undefined,
                                      }}
                                    >
                                      <span
                                        className={`block rounded-sm border ${
                                          preset.id === "social"
                                            ? "h-2 w-2"
                                            : preset.id === "subtle"
                                              ? "h-2.5 w-2.5"
                                              : "h-3 w-3"
                                        }`}
                                      />
                                    </span>
                                    <span>
                                      <span className="block text-sm font-semibold">
                                        {preset.name}
                                      </span>
                                      <span className="mt-0.5 block text-xs text-muted-foreground">
                                        {preset.detail}
                                      </span>
                                    </span>
                                  </span>
                                  <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold tabular-nums text-muted-foreground">
                                    {preset.strength}
                                  </span>
                                </button>
                              );
                            })}
                          </div>
                        </div>

                        <div className="rounded-xl border bg-muted/20 p-1">
                          <div className="flex items-center justify-between gap-3 rounded-lg px-2 py-2.5">
                            <div className="flex gap-3">
                              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-background shadow-sm">
                                <Mic2 className="h-4 w-4 text-primary" />
                              </span>
                              <div>
                                <div className="text-sm font-medium">Clareza de voz</div>
                                <div className="text-xs leading-relaxed text-muted-foreground">
                                  Reduz graves, equilibra volume e evita picos
                                </div>
                              </div>
                            </div>
                            <Switch
                              checked={config.enhanceVoice}
                              onCheckedChange={(value) => update("enhanceVoice", value)}
                              aria-label="Aplicar clareza de voz"
                            />
                          </div>
                        </div>

                        <p className="text-[11px] leading-relaxed text-muted-foreground">
                          {hasSectionContent
                            ? "O movimento usa aceleração suave, prioriza o rosto e não entra sobre a cartela."
                            : "O movimento usa aceleração suave e prioriza o rosto."}
                        </p>
                      </CardContent>
                    </Card>

                    <Card className="overflow-hidden">
                      <CardHeader className="border-b bg-muted/20 pb-3">
                        <CardTitle className="text-base">Peças aplicadas</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-1">
                        <PieceSwitch
                          label="Abertura"
                          detail="0–2 segundos"
                          checked={config.includeOpening}
                          onCheckedChange={(value) => update("includeOpening", value)}
                        />
                        <PieceSwitch
                          label="Lower third"
                          detail="Nome e cargo por 4 segundos"
                          checked={config.includeLowerThird}
                          onCheckedChange={(value) => update("includeLowerThird", value)}
                        />
                        {hasSectionContent ? (
                          <PieceSwitch
                            label="Cartela"
                            detail={`${config.sectionTransition === "slide_up" ? "Desliza" : config.sectionTransition === "none" ? "Corte direto" : "Fade"} · ${config.sectionDurationSeconds ?? 3} segundos`}
                            checked={config.includeSection}
                            onCheckedChange={(value) => update("includeSection", value)}
                          />
                        ) : null}
                        <div className="space-y-1.5 rounded-lg border bg-muted/20 px-3 py-2.5">
                          <div className="flex items-center justify-between gap-3">
                            <Label htmlFor="kit-outro-tail">Slide final acrescenta</Label>
                            <span className="text-xs text-muted-foreground">segundos</span>
                          </div>
                          <Input
                            id="kit-outro-tail"
                            type="number"
                            min={MEDICAL_MINIMUM_END_CARD_SECONDS}
                            max={120}
                            step={0.5}
                            value={config.outroTailSeconds ?? 10}
                            onChange={(event) =>
                              update(
                                "outroTailSeconds",
                                event.target.value ? Number(event.target.value) : 10,
                              )
                            }
                          />
                        </div>
                        <div className="space-y-1.5 rounded-lg border border-primary/25 bg-primary/5 px-3 py-2.5">
                          <div className="text-sm font-medium">Encerramento obrigatório</div>
                          <p className="text-xs text-muted-foreground">
                            Slide final por pelo menos {MEDICAL_MINIMUM_END_CARD_SECONDS} segundos,
                            sem locução adicional.
                          </p>
                          <p className="text-xs font-medium leading-relaxed text-foreground">
                            {MEDICAL_PUBLICATION_NOTICE}
                          </p>
                        </div>
                      </CardContent>
                    </Card>
                  </div>
                </details>
              </TabsContent>
            </Tabs>
          </aside>

          <section className="space-y-5">
            <Card className="overflow-hidden bg-card xl:sticky xl:top-20 xl:z-10">
              <CardHeader className="border-b bg-muted/25 pb-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <CardTitle className="text-base">Prévia lado a lado</CardTitle>
                    <p className="mt-1 text-xs text-muted-foreground">
                      O original fica à esquerda; o vídeo editado aparece à direita quando o render
                      terminar.
                    </p>
                  </div>
                  {job?.status === "pronto" ? (
                    <span className="rounded-full border border-status-success/25 bg-status-success/8 px-2.5 py-1 text-[11px] font-semibold text-status-success">
                      Resultado pronto
                    </span>
                  ) : null}
                </div>
              </CardHeader>
              <CardContent className="p-4 md:p-5">
                <div className="grid gap-4 lg:grid-cols-2">
                  <VideoPanel
                    title="Vídeo original"
                    url={originalUrl}
                    onDuration={setSourceDuration}
                  />
                  <VideoPanel
                    title="Vídeo editado"
                    url={job?.status === "pronto" ? localVideoKitResultUrl(job.id) : null}
                    pending={working}
                  />
                </div>
              </CardContent>
            </Card>
          </section>
        </div>
      </div>
    </AppShell>
  );
}

function EditorNextStepCard({
  state,
  progress,
  stage,
  captionCueCount,
  visualCount,
  summary,
  job,
  busy,
  error,
  onChoose,
  onRetryUpload,
  onStartAnalysis,
  onRetryAnalysis,
  onReview,
  onFixVisuals,
  onFixClips,
  onGenerate,
  onRetryRender,
}: {
  state: EditorFlowState;
  progress?: number;
  stage?: string;
  captionCueCount: number;
  visualCount: number;
  summary: string[];
  job: LocalVideoKitJob | null;
  busy: boolean;
  error: string | null;
  onChoose: () => void;
  onRetryUpload: () => void;
  onStartAnalysis: () => void;
  onRetryAnalysis: () => void;
  onReview: () => void;
  onFixVisuals: () => void;
  onFixClips: () => void;
  onGenerate: () => void;
  onRetryRender: () => void;
}) {
  const copy = (() => {
    switch (state) {
      case "uploading":
        return {
          eyebrow: "Etapa 1 de 4",
          title: "Carregando o vídeo",
          detail:
            "Somente o arquivo está sendo carregado. Nenhuma transcrição, análise ou edição será iniciada automaticamente.",
        };
      case "upload_failed":
        return {
          eyebrow: "Envio interrompido",
          title: "Não foi possível carregar o vídeo",
          detail: error || "O arquivo foi preservado e pode ser enviado novamente.",
        };
      case "configure":
        return {
          eyebrow: "Aguardando sua definição",
          title: "Defina a edição antes de iniciar",
          detail:
            "Revise identidade, clipes, visuais manuais e estilo. Quando estiver satisfeito, confirme para adicionar a preparação à fila.",
        };
      case "queueing":
        return {
          eyebrow: "Confirmação recebida",
          title: "Adicionando a preparação à fila",
          detail:
            "Aguarde enquanto registramos sua escolha. A transcrição será a primeira ação da sequência.",
        };
      case "transcribing":
        return {
          eyebrow: "Etapa 2 de 4 · Legendas locais",
          title: stage || "Transcrevendo áudio e sincronizando legendas",
          detail:
            "O Whisper local está criando a legenda com o tempo exato de cada palavra. O Claude ainda não foi chamado.",
        };
      case "analyzing":
        return {
          eyebrow: "Etapa 3 de 4 · Claude",
          title: stage || "Claude analisando a transcrição",
          detail: `${captionCueCount ? `${captionCueCount} trechos de legenda já estão sincronizados. ` : "As legendas já estão sincronizadas. "}O Claude agora decide onde um visual ajuda e escolhe os pontos usando os segundos da fala.`,
        };
      case "analysis_failed":
        return {
          eyebrow: "Análise interrompida",
          title: "A direção visual precisa ser refeita",
          detail: error || "O vídeo continua salvo; somente a análise será reiniciada.",
        };
      case "review":
        return {
          eyebrow: "Etapa 3 de 4 · Revisão do Claude",
          title: "Revise a direção do Claude",
          detail:
            visualCount > 0
              ? `${visualCount} ${visualCount === 1 ? "visual foi sugerido" : "visuais foram sugeridos"}. Confirme o que entra antes de gerar.`
              : "O Claude recomenda não adicionar visuais extras. Confirme essa decisão antes de gerar.",
        };
      case "fix_clips":
        return {
          eyebrow: "Ajuste necessário",
          title: "Corrija a timeline dos clipes",
          detail: error || "Um clipe está fora da duração disponível no vídeo.",
        };
      case "fix_visuals":
        return {
          eyebrow: "Ajuste necessário",
          title: "Corrija a entrada e a saída dos visuais",
          detail: error || "Dois elementos estão ocupando o mesmo momento do vídeo.",
        };
      case "ready":
        return {
          eyebrow: "Etapa 4 de 4",
          title: "Tudo pronto para gerar",
          detail: "Confira o resumo e inicie o render local. Nenhum crédito externo será usado.",
        };
      case "rendering":
        return {
          eyebrow: "Render local em andamento",
          title: stage || "Gerando o vídeo editado",
          detail:
            "Você pode acompanhar o progresso aqui. Ao terminar, os botões de download aparecerão automaticamente.",
        };
      case "render_failed":
        return {
          eyebrow: "Render interrompido",
          title: "O MP4 não foi finalizado",
          detail: error || "O vídeo e os ajustes foram preservados para uma nova tentativa.",
        };
      case "done":
        return {
          eyebrow: "Concluído",
          title: "Seu vídeo editado está pronto",
          detail:
            "Baixe o MP4 final ou a capa. Você também pode gerar outra versão com novos ajustes.",
        };
      default:
        return {
          eyebrow: "Comece aqui",
          title: "Escolha o vídeo que será editado",
          detail:
            "O vídeo será apenas carregado. Você poderá definir todos os ajustes antes de iniciar qualquer processamento.",
        };
    }
  })();

  const failed = [
    "upload_failed",
    "analysis_failed",
    "fix_visuals",
    "fix_clips",
    "render_failed",
  ].includes(state);
  const complete = state === "done";
  const inProgress = ["uploading", "queueing", "transcribing", "analyzing", "rendering"].includes(
    state,
  );
  const Icon = failed
    ? CircleAlert
    : complete
      ? CheckCircle2
      : inProgress
        ? LoaderCircle
        : state === "configure"
          ? SlidersHorizontal
          : state === "review"
            ? BrainCircuit
            : state === "ready"
              ? WandSparkles
              : state === "fix_visuals"
                ? Clock3
                : state === "fix_clips"
                  ? Film
                  : Upload;

  return (
    <section
      id="editor-next-step"
      className={`rounded-2xl border p-4 shadow-sm sm:p-5 ${
        failed
          ? "border-destructive/30 bg-destructive/[0.035]"
          : complete
            ? "border-status-success/30 bg-status-success/[0.04]"
            : "border-primary/25 bg-primary/[0.035]"
      }`}
      role={failed ? "alert" : complete ? "status" : undefined}
    >
      <div className="grid gap-4 lg:grid-cols-[auto_minmax(0,1fr)_auto] lg:items-center">
        <span
          className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${
            failed
              ? "bg-destructive/10 text-destructive"
              : complete
                ? "bg-status-success/10 text-status-success"
                : "bg-primary/10 text-primary"
          }`}
        >
          <span className={inProgress ? "animate-spin" : undefined}>
            <Icon className="h-5 w-5" aria-hidden="true" />
          </span>
        </span>
        <div className="min-w-0">
          <div
            className={`text-[10px] font-semibold uppercase tracking-[0.14em] ${
              failed ? "text-destructive" : complete ? "text-status-success" : "text-primary"
            }`}
          >
            {copy.eyebrow}
          </div>
          <h2 className="mt-1 text-base font-semibold tracking-tight">{copy.title}</h2>
          <p className="mt-1 max-w-3xl text-xs leading-relaxed text-muted-foreground">
            {copy.detail}
          </p>
          {state === "configure" || state === "ready" ? (
            <div className="mt-3 flex flex-wrap gap-1.5" aria-label="Resumo da preparação">
              {summary.map((item) => (
                <span
                  key={item}
                  className="rounded-full border bg-background px-2.5 py-1 text-[11px] font-medium text-muted-foreground"
                >
                  {item}
                </span>
              ))}
            </div>
          ) : null}
          {inProgress && typeof progress === "number" ? (
            <div className="mt-3 flex max-w-xl items-center gap-3">
              <Progress value={progress} className="h-2 flex-1" />
              <span className="w-9 text-right text-xs tabular-nums text-muted-foreground">
                {progress}%
              </span>
            </div>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2 lg:justify-end">
          {state === "choose" ? (
            <Button type="button" size="lg" className="min-h-11" onClick={onChoose}>
              <Upload className="mr-2 h-4 w-4" /> Escolher vídeo
            </Button>
          ) : state === "configure" ? (
            <Button
              type="button"
              size="lg"
              className="min-h-11"
              disabled={busy}
              onClick={onStartAnalysis}
            >
              {busy ? (
                <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <ArrowRight className="mr-2 h-4 w-4" />
              )}
              Confirmar e iniciar preparação
            </Button>
          ) : state === "upload_failed" ? (
            <Button type="button" className="min-h-11" disabled={busy} onClick={onRetryUpload}>
              {busy ? (
                <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <RefreshCcw className="mr-2 h-4 w-4" />
              )}
              Tentar envio novamente
            </Button>
          ) : state === "analysis_failed" ? (
            <Button type="button" className="min-h-11" disabled={busy} onClick={onRetryAnalysis}>
              {busy ? (
                <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <RefreshCcw className="mr-2 h-4 w-4" />
              )}
              Refazer análise
            </Button>
          ) : state === "review" ? (
            <Button type="button" size="lg" className="min-h-11" onClick={onReview}>
              Revisar direção <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          ) : state === "fix_clips" ? (
            <Button type="button" className="min-h-11" onClick={onFixClips}>
              Abrir clipes <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          ) : state === "fix_visuals" ? (
            <Button type="button" className="min-h-11" onClick={onFixVisuals}>
              Ajustar tempos <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          ) : state === "ready" ? (
            <Button type="button" size="lg" className="min-h-11" onClick={onGenerate}>
              <WandSparkles className="mr-2 h-4 w-4" /> Gerar vídeo editado
            </Button>
          ) : state === "render_failed" ? (
            <>
              <Button type="button" className="min-h-11" disabled={busy} onClick={onRetryRender}>
                {busy ? (
                  <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCcw className="mr-2 h-4 w-4" />
                )}
                Tentar render novamente
              </Button>
              <Button type="button" className="min-h-11" variant="secondary" onClick={onChoose}>
                Usar outro vídeo
              </Button>
            </>
          ) : state === "done" && job ? (
            <>
              <Button asChild size="lg" className="min-h-11">
                <a href={localVideoKitResultUrl(job.id, true)}>
                  <Download className="mr-2 h-4 w-4" /> Baixar MP4
                </a>
              </Button>
              <Button asChild size="lg" variant="secondary" className="min-h-11">
                <a href={localVideoKitCoverUrl(job.id, true)}>
                  <ImageIcon className="mr-2 h-4 w-4" /> Baixar capa
                </a>
              </Button>
              <Button type="button" className="min-h-11" variant="ghost" onClick={onGenerate}>
                Gerar nova versão
              </Button>
            </>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(bytes < 10 * 1024 * 1024 ? 1 : 0)} MB`;
}

function humanizeRenderError(error: string): string {
  if (error.includes("Starting second pass: moving the moov atom")) {
    return "O render anterior concluiu os frames, mas travou ao finalizar o MP4. Esse gargalo foi removido; use Tentar render novamente.";
  }
  if (error.length > 700) {
    return "O FFmpeg interrompeu o render local. Os ajustes e o vídeo original foram preservados; tente novamente para usar o novo monitoramento.";
  }
  return error;
}

function humanizeAnalysisError(error: string): string {
  if (
    error.includes("output_config.format.schema") ||
    error.includes("Invalid schema") ||
    error.includes("invalid_request_error")
  ) {
    return "O Claude recusou o formato antigo do plano visual. O formato foi corrigido; refaça a análise para reutilizar a transcrição e as legendas já processadas.";
  }
  if (error.length > 500) {
    return "O Claude não concluiu a direção visual. A transcrição e as legendas foram preservadas; refaça somente a análise.";
  }
  return error;
}

function InsertEditorCard({
  inserts,
  uploading,
  errors,
  onFiles,
  onChangeTime,
  onReuse,
  onRemove,
}: {
  inserts: LocalVideoKitInsert[];
  uploading: boolean;
  errors: string[];
  onFiles: (files: File[]) => void | Promise<void>;
  onChangeTime: (id: string, field: InsertTimeField, value: number) => void;
  onReuse: (insert: LocalVideoKitInsert) => void;
  onRemove: (id: string) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const sourceCount = new Set(inserts.map((insert) => insert.uploadId)).size;
  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b bg-muted/20 pb-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Film className="h-4 w-4 text-primary" />
              Inserts de apoio
            </CardTitle>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              Cubra momentos específicos com vídeos de apoio sem interromper a voz original.
            </p>
          </div>
          <span className="shrink-0 rounded-full border border-primary/20 bg-primary/8 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-primary">
            {sourceCount} {sourceCount === 1 ? "vídeo" : "vídeos"} · {inserts.length}{" "}
            {inserts.length === 1 ? "trecho" : "trechos"}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <input
          ref={input}
          id="local-kit-insert-video"
          type="file"
          multiple
          accept="video/mp4,video/quicktime,video/webm"
          className="hidden"
          onChange={(event) => {
            const selected = Array.from(event.target.files || []);
            event.currentTarget.value = "";
            void onFiles(selected);
          }}
        />
        <button
          type="button"
          onClick={() => input.current?.click()}
          disabled={uploading || inserts.length >= 24}
          className="flex min-h-20 w-full cursor-pointer items-center gap-3 rounded-xl border border-dashed bg-muted/30 p-4 text-left transition-colors hover:border-primary/45 hover:bg-muted/55 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
        >
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-card shadow-sm">
            {uploading ? (
              <LoaderCircle className="h-5 w-5 animate-spin text-primary" />
            ) : (
              <Plus className="h-5 w-5 text-primary" />
            )}
          </span>
          <span>
            <span className="block text-sm font-semibold">
              {inserts.length >= 24
                ? "Limite de inserts alcançado"
                : uploading
                  ? "Enviando vídeos..."
                  : inserts.length
                    ? "Adicionar outros vídeos de insert"
                    : "Adicionar vídeos de insert"}
            </span>
            <span className="mt-1 block text-xs text-muted-foreground">
              Selecione um ou vários arquivos. Cada vídeo fica disponível de forma independente.
            </span>
          </span>
        </button>

        {inserts.length ? (
          <div className="space-y-3">
            {inserts.map((insert, index) => {
              const usedPercent = Math.min(
                100,
                ((insert.sourceEndSeconds - insert.sourceStartSeconds) /
                  insert.sourceDurationSeconds) *
                  100,
              );
              const usedOffset = Math.min(
                100,
                (insert.sourceStartSeconds / insert.sourceDurationSeconds) * 100,
              );
              const remaining = insert.sourceDurationSeconds - insert.sourceEndSeconds;
              return (
                <article
                  key={insert.id}
                  className="overflow-hidden rounded-xl border bg-background"
                >
                  <div className="flex items-start gap-3 border-b bg-muted/20 p-3">
                    <video
                      src={localVideoKitInsertUrl(insert.uploadId)}
                      muted
                      controls
                      playsInline
                      preload="metadata"
                      className="aspect-video w-28 shrink-0 rounded-lg bg-black object-contain"
                      aria-label={`Prévia de ${insert.sourceName}`}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-semibold">{insert.sourceName}</div>
                          <div className="mt-0.5 text-[11px] text-muted-foreground">
                            Uso {index + 1} · arquivo com {insert.sourceDurationSeconds.toFixed(1)}s
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => onRemove(insert.id)}
                          className="flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          aria-label={`Remover insert ${index + 1}`}
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
                        <span
                          className="block h-full rounded-full bg-primary"
                          style={{ marginLeft: `${usedOffset}%`, width: `${usedPercent}%` }}
                        />
                      </div>
                      <div className="mt-1 flex justify-between text-[9px] font-medium uppercase tracking-wide text-muted-foreground">
                        <span>0s</span>
                        <span>Trecho usado</span>
                        <span>{insert.sourceDurationSeconds.toFixed(1)}s</span>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-4 p-3">
                    <div>
                      <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold">
                        <Clock3 className="h-3.5 w-3.5 text-primary" /> No vídeo final
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <InsertTimeInput
                          id={`${insert.id}-timeline-start`}
                          label="Entra aos"
                          value={insert.timelineStartSeconds}
                          onChange={(value) =>
                            onChangeTime(insert.id, "timelineStartSeconds", value)
                          }
                        />
                        <InsertTimeInput
                          id={`${insert.id}-timeline-end`}
                          label="Sai aos"
                          value={insert.timelineEndSeconds}
                          onChange={(value) => onChangeTime(insert.id, "timelineEndSeconds", value)}
                        />
                      </div>
                    </div>

                    <div>
                      <div className="mb-2 text-xs font-semibold">Trecho dentro do arquivo</div>
                      <div className="grid grid-cols-2 gap-3">
                        <InsertTimeInput
                          id={`${insert.id}-source-start`}
                          label="Começa em"
                          value={insert.sourceStartSeconds}
                          max={insert.sourceDurationSeconds}
                          onChange={(value) => onChangeTime(insert.id, "sourceStartSeconds", value)}
                        />
                        <InsertTimeInput
                          id={`${insert.id}-source-end`}
                          label="Termina em"
                          value={insert.sourceEndSeconds}
                          max={insert.sourceDurationSeconds}
                          onChange={(value) => onChangeTime(insert.id, "sourceEndSeconds", value)}
                        />
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-muted/30 px-3 py-2">
                      <span className="text-[11px] text-muted-foreground">
                        Duração:{" "}
                        {(insert.timelineEndSeconds - insert.timelineStartSeconds).toFixed(1)}s
                      </span>
                      <button
                        type="button"
                        onClick={() => onReuse(insert)}
                        disabled={remaining < 0.25}
                        className="inline-flex min-h-9 cursor-pointer items-center gap-1.5 rounded-md px-2.5 text-xs font-semibold text-primary transition-colors hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-45"
                      >
                        <Copy className="h-3.5 w-3.5" /> Usar próximo trecho
                      </button>
                    </div>
                  </div>
                </article>
              );
            })}
            <button
              type="button"
              onClick={() => input.current?.click()}
              disabled={uploading || inserts.length >= 24}
              className="flex min-h-11 w-full cursor-pointer items-center justify-center gap-2 rounded-lg border bg-background px-3 text-sm font-semibold text-primary transition-colors hover:border-primary/35 hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            >
              {uploading ? (
                <LoaderCircle className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              Adicionar mais vídeos
            </button>
          </div>
        ) : (
          <div className="rounded-xl border border-dashed px-4 py-5 text-center">
            <Film className="mx-auto h-6 w-6 text-muted-foreground/60" />
            <p className="mt-2 text-xs font-medium">Nenhum insert adicionado</p>
            <p className="mx-auto mt-1 max-w-sm text-[11px] leading-relaxed text-muted-foreground">
              O apresentador permanece em cena durante todo o vídeo.
            </p>
          </div>
        )}

        {errors.length ? (
          <div className="rounded-xl border border-amber-500/35 bg-amber-500/8 p-3" role="alert">
            <div className="text-xs font-semibold text-amber-800 dark:text-amber-200">
              Ajuste a timeline dos inserts
            </div>
            <ul className="mt-1.5 space-y-1 text-[11px] leading-relaxed text-amber-800/85 dark:text-amber-100/80">
              {errors.map((error) => (
                <li key={error}>• {error}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <p className="text-[11px] leading-relaxed text-muted-foreground">
          “Usar próximo trecho” continua do ponto ainda não usado, evitando repetir as mesmas
          imagens. O áudio do insert é descartado; a fala principal continua sincronizada.
        </p>
      </CardContent>
    </Card>
  );
}

function ClaudeVisualAnalysisCard({
  job,
  artifacts,
  pack,
  error,
  starting,
  retrying,
  hasSource,
  existingProjectWithoutAnalysis,
  reviewConfirmed,
  timingValidation,
  videoDurationSeconds,
  onEventChange,
  onRetry,
  onConfirm,
}: {
  job: PostProductionJob | null;
  artifacts: PostProductionArtifacts | null;
  pack: GeneratedContentPack | null;
  error: string | null;
  starting: boolean;
  retrying: boolean;
  hasSource: boolean;
  existingProjectWithoutAnalysis: boolean;
  reviewConfirmed: boolean;
  timingValidation: VisualTimingValidation;
  videoDurationSeconds: number;
  onEventChange: (id: string, patch: Partial<VisualTimelineEvent>) => void;
  onRetry: () => void;
  onConfirm: () => void;
}) {
  const running = Boolean(
    starting ||
    (job &&
      ["queued", "transcribing", "planning", "preflight", "generating_pack"].includes(job.status)),
  );
  const events = artifacts?.timeline.events || [];
  const enabledCount = events.filter((event) => event.enabled).length;
  const failed = Boolean(error || job?.status === "failed");

  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b bg-muted/20 pb-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <BrainCircuit className="h-4 w-4 text-primary" />
              Direção visual do Claude
            </CardTitle>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              Recebe a transcrição já sincronizada e escolhe os visuais pelos segundos da fala.
            </p>
          </div>
          <span className="shrink-0 rounded-full border border-primary/20 bg-primary/8 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-primary">
            {job?.plannerMode === "anthropic"
              ? "Claude"
              : starting
                ? "Enfileirando"
                : running
                  ? "Analisando"
                  : "Sob confirmação"}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {existingProjectWithoutAnalysis ? (
          <div className="rounded-xl border border-status-success/25 bg-status-success/[0.04] p-4">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-status-success" />
              <div>
                <p className="text-sm font-semibold">Configuração existente preservada</p>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  Este projeto mantém os visuais e ajustes da tentativa anterior. Para receber uma
                  nova direção do Claude e um novo Pack, escolha outro vídeo no topo.
                </p>
              </div>
            </div>
          </div>
        ) : !hasSource ? (
          <div className="rounded-xl border border-dashed px-4 py-6 text-center">
            <Upload className="mx-auto h-6 w-6 text-muted-foreground/60" />
            <p className="mt-2 text-sm font-semibold">Escolha um vídeo para configurar</p>
            <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-muted-foreground">
              Após sua confirmação, primeiro criamos a legenda local. Só depois o Claude analisa a
              transcrição.
            </p>
          </div>
        ) : !job && !failed && !starting ? (
          <div className="rounded-xl border border-dashed bg-muted/10 px-4 py-6 text-center">
            <Clock3 className="mx-auto h-6 w-6 text-primary/70" />
            <p className="mt-2 text-sm font-semibold">Aguardando sua confirmação</p>
            <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-muted-foreground">
              Nenhuma análise foi iniciada. Defina os ajustes e use “Confirmar e iniciar preparação”
              quando quiser colocar as ações na fila.
            </p>
          </div>
        ) : running ? (
          <div
            className="space-y-3 rounded-xl border border-status-info/25 bg-status-info/5 p-4"
            aria-live="polite"
          >
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <LoaderCircle className="h-4 w-4 animate-spin text-status-info" />
                {job?.etapa || "Preparando a análise"}
              </div>
              <span className="text-xs tabular-nums text-muted-foreground">
                {job?.progresso ?? 0}%
              </span>
            </div>
            <Progress value={job?.progresso ?? 4} className="h-2" />
            <p className="text-xs leading-relaxed text-muted-foreground">
              {job?.captionsStatus === "ready"
                ? "Legendas prontas. Avaliando os momentos úteis e montando o Pack sem inventar informações."
                : "Transcrevendo e sincronizando a legenda local antes de iniciar a direção visual."}
            </p>
          </div>
        ) : failed ? (
          <div
            className="rounded-xl border border-destructive/30 bg-destructive/5 p-4"
            role="alert"
          >
            <div className="flex items-start gap-3">
              <CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold">A análise não foi concluída</p>
                <p className="mt-1 break-words text-xs leading-relaxed text-muted-foreground">
                  {humanizeAnalysisError(
                    error || job?.erro || "O Claude não conseguiu montar a direção visual.",
                  )}
                </p>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  className="mt-3"
                  disabled={retrying}
                  onClick={onRetry}
                >
                  {retrying ? (
                    <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCcw className="mr-2 h-4 w-4" />
                  )}
                  Refazer análise
                </Button>
              </div>
            </div>
          </div>
        ) : artifacts ? (
          <>
            <div className="rounded-xl border bg-muted/20 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-primary">
                  {artifacts.visualPlan?.contentType || "Direção editorial"}
                </span>
                <span className="rounded-full bg-background px-2.5 py-1 text-[11px] font-medium text-muted-foreground shadow-sm">
                  {enabledCount} {enabledCount === 1 ? "visual sugerido" : "visuais sugeridos"}
                </span>
              </div>
              {artifacts.visualPlan?.summary ? (
                <p className="mt-3 text-sm font-semibold leading-snug">
                  {artifacts.visualPlan.summary}
                </p>
              ) : null}
              {artifacts.visualPlan?.strategy ? (
                <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
                  {artifacts.visualPlan.strategy}
                </p>
              ) : null}
            </div>

            {events.length ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <Label>Revisar propostas</Label>
                  <span className="text-[11px] text-muted-foreground">Você decide o que entra</span>
                </div>
                {events.map((event, index) => {
                  const eventTimingIssues =
                    timingValidation.issuesByItemId[`event:${event.id}`] || [];
                  const transcriptStart = artifacts.transcript.words[event.startWordIndex]?.startMs;
                  const transcriptEnd = artifacts.transcript.words[event.endWordIndex]?.endMs;
                  return (
                    <article
                      key={event.id}
                      className={`rounded-xl border p-3 transition-colors ${
                        eventTimingIssues.length
                          ? "border-destructive/45 bg-destructive/[0.035]"
                          : event.enabled
                            ? "border-primary/30 bg-primary/[0.035]"
                            : "bg-muted/20 opacity-75"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                            Visual {index + 1} · {formatPreciseTimelineTime(event.startMs)}–
                            {formatPreciseTimelineTime(event.endMs)}
                          </div>
                          <p className="mt-1 line-clamp-2 text-xs italic leading-relaxed text-muted-foreground">
                            “{event.spokenText}”
                          </p>
                        </div>
                        <Switch
                          checked={event.enabled}
                          onCheckedChange={(enabled) =>
                            onEventChange(event.id, {
                              enabled,
                              reviewStatus: enabled ? "approved" : "rejected",
                            })
                          }
                          aria-label={`${event.enabled ? "Remover" : "Usar"} visual ${index + 1}`}
                        />
                      </div>

                      <div className="mt-3 grid gap-3 sm:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
                        <div className="space-y-1.5">
                          <Label htmlFor={`visual-type-${event.id}`}>Modelo</Label>
                          <select
                            id={`visual-type-${event.id}`}
                            value={event.interactionType}
                            disabled={!event.enabled}
                            onChange={(changeEvent) =>
                              onEventChange(event.id, {
                                interactionType: changeEvent.target
                                  .value as VisualTimelineEvent["interactionType"],
                              })
                            }
                            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus:ring-2 focus:ring-ring disabled:opacity-60"
                          >
                            {STANDARD_VISUAL_MODELS.map((model) => (
                              <option key={model.id} value={model.id}>
                                {model.name}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor={`visual-copy-${event.id}`}>Texto na tela</Label>
                          <Input
                            id={`visual-copy-${event.id}`}
                            value={event.visualText}
                            maxLength={80}
                            disabled={!event.enabled}
                            onChange={(changeEvent) =>
                              onEventChange(event.id, { visualText: changeEvent.target.value })
                            }
                          />
                        </div>
                      </div>

                      <div
                        className={`mt-3 rounded-lg border p-3 ${
                          eventTimingIssues.length
                            ? "border-destructive/30 bg-background"
                            : "bg-background/75"
                        }`}
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-1.5 text-xs font-semibold">
                            <Clock3 className="h-3.5 w-3.5 text-primary" /> Tempo na tela
                          </div>
                          <span className="rounded-full bg-muted px-2 py-1 text-[10px] font-medium text-muted-foreground">
                            {event.timingSource === "manual"
                              ? "Ajustado por você"
                              : "Sugerido pelo Claude"}
                          </span>
                        </div>
                        <div className="mt-3 grid grid-cols-2 gap-3">
                          <TimelineTimeInput
                            id={`visual-start-${event.id}`}
                            label="Entrada"
                            valueMs={event.startMs}
                            maxSeconds={videoDurationSeconds || undefined}
                            disabled={!event.enabled}
                            invalid={Boolean(eventTimingIssues.length)}
                            describedBy={
                              eventTimingIssues.length ? `visual-time-error-${event.id}` : undefined
                            }
                            onCommit={(startMs) =>
                              onEventChange(event.id, { startMs, timingSource: "manual" })
                            }
                          />
                          <TimelineTimeInput
                            id={`visual-end-${event.id}`}
                            label="Saída"
                            valueMs={event.endMs}
                            maxSeconds={videoDurationSeconds || undefined}
                            disabled={!event.enabled}
                            invalid={Boolean(eventTimingIssues.length)}
                            describedBy={
                              eventTimingIssues.length ? `visual-time-error-${event.id}` : undefined
                            }
                            onCommit={(endMs) =>
                              onEventChange(event.id, { endMs, timingSource: "manual" })
                            }
                          />
                        </div>
                        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                          <span className="text-[10px] tabular-nums text-muted-foreground">
                            Duração: {Math.max(0, (event.endMs - event.startMs) / 1000).toFixed(2)}s
                          </span>
                          {event.timingSource === "manual" &&
                          typeof transcriptStart === "number" &&
                          typeof transcriptEnd === "number" ? (
                            <button
                              type="button"
                              className="min-h-9 cursor-pointer rounded-md px-2.5 text-[11px] font-semibold text-primary transition-colors hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                              onClick={() =>
                                onEventChange(event.id, {
                                  startMs: transcriptStart,
                                  endMs: transcriptEnd,
                                  timingSource: "transcript",
                                })
                              }
                            >
                              Restaurar tempo do Claude
                            </button>
                          ) : null}
                        </div>
                        {eventTimingIssues.length ? (
                          <ul
                            id={`visual-time-error-${event.id}`}
                            className="mt-2 space-y-1 border-t border-destructive/20 pt-2 text-[11px] leading-relaxed text-destructive"
                            role="alert"
                          >
                            {eventTimingIssues.map((issue) => (
                              <li key={issue}>• {issue}</li>
                            ))}
                          </ul>
                        ) : null}
                      </div>
                      <VisualAppearanceControls
                        event={event}
                        disabled={!event.enabled}
                        onChange={(patch) => onEventChange(event.id, patch)}
                      />
                      <div className="mt-3 flex items-start justify-between gap-3 border-t pt-2.5">
                        <p className="text-[11px] leading-relaxed text-muted-foreground">
                          {event.reason}
                        </p>
                        <span className="shrink-0 text-[10px] font-semibold tabular-nums text-primary">
                          {Math.round(event.confidence * 100)}% confiança
                        </span>
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className="rounded-xl border border-status-success/25 bg-status-success/5 p-4">
                <div className="flex items-center gap-2 text-sm font-semibold">
                  <CheckCircle2 className="h-4 w-4 text-status-success" />
                  Nenhum visual é a melhor decisão
                </div>
                <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
                  {artifacts.visualPlan?.noVisualReason ||
                    "A fala já está clara e uma cartela extra não acrescentaria compreensão."}
                </p>
              </div>
            )}

            <div className="rounded-xl border bg-muted/15 p-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold">Pack automático</div>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Carrossel de 7 slides derivado da mesma transcrição.
                  </p>
                </div>
                <span
                  className={`rounded-full px-2 py-1 text-[10px] font-semibold uppercase tracking-wide ${
                    pack
                      ? "bg-status-success/10 text-status-success"
                      : job?.packStatus === "failed"
                        ? "bg-destructive/10 text-destructive"
                        : "bg-muted text-muted-foreground"
                  }`}
                >
                  {pack ? "7 slides prontos" : job?.packStatus === "failed" ? "Falhou" : "Gerando"}
                </span>
              </div>
              {pack?.images.length ? (
                <div className="mt-3 grid grid-cols-4 gap-2">
                  {pack.images.slice(0, 4).map((image, index) => (
                    <img
                      key={image}
                      src={image}
                      alt={`Slide ${index + 1} do Pack`}
                      className="aspect-[4/5] w-full rounded-md border object-cover"
                      loading="lazy"
                    />
                  ))}
                </div>
              ) : job?.packError ? (
                <p className="mt-3 text-xs leading-relaxed text-destructive">{job.packError}</p>
              ) : null}
            </div>

            <div
              className={`flex flex-col gap-3 rounded-xl border p-4 sm:flex-row sm:items-center sm:justify-between ${
                reviewConfirmed
                  ? "border-status-success/30 bg-status-success/[0.045]"
                  : "border-primary/30 bg-primary/[0.045]"
              }`}
            >
              <div>
                <div className="flex items-center gap-2 text-sm font-semibold">
                  {reviewConfirmed ? (
                    <CheckCircle2 className="h-4 w-4 text-status-success" />
                  ) : (
                    <BrainCircuit className="h-4 w-4 text-primary" />
                  )}
                  {reviewConfirmed
                    ? "Direção visual aprovada"
                    : timingValidation.issues.length
                      ? "Corrija os tempos para continuar"
                      : "Confirme a direção visual"}
                </div>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  {reviewConfirmed
                    ? "Essas escolhas serão usadas no próximo render."
                    : timingValidation.issues.length
                      ? "Entrada e saída não podem se sobrepor a outro visual. Os conflitos estão destacados acima."
                      : enabledCount
                        ? `Serão usados ${enabledCount} ${enabledCount === 1 ? "visual" : "visuais"}. Você ainda pode desligar ou editar cada proposta.`
                        : "Nenhum visual extra será aplicado; a fala permanecerá como foco."}
                </p>
              </div>
              <Button
                type="button"
                className="min-h-11 shrink-0"
                variant={reviewConfirmed ? "secondary" : "default"}
                disabled={reviewConfirmed || Boolean(timingValidation.issues.length)}
                onClick={onConfirm}
              >
                {reviewConfirmed ? (
                  <CheckCircle2 className="mr-2 h-4 w-4" />
                ) : (
                  <ArrowRight className="mr-2 h-4 w-4" />
                )}
                {reviewConfirmed ? "Direção aprovada" : "Aprovar e continuar"}
              </Button>
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}

function formatTimelineTime(milliseconds: number): string {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function formatPreciseTimelineTime(milliseconds: number): string {
  return `${(Math.max(0, milliseconds) / 1000).toFixed(2)}s`;
}

function TimelineTimeInput({
  id,
  label,
  valueMs,
  maxSeconds,
  disabled,
  invalid,
  describedBy,
  onCommit,
}: {
  id: string;
  label: string;
  valueMs: number;
  maxSeconds?: number;
  disabled?: boolean;
  invalid?: boolean;
  describedBy?: string;
  onCommit: (milliseconds: number) => void;
}) {
  const formatted = (Math.max(0, valueMs) / 1000).toFixed(2);
  const [draft, setDraft] = useState(formatted);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    setDraft(formatted);
    setLocalError(null);
  }, [formatted]);

  function commit(rawValue: string) {
    const seconds = Number(rawValue.replace(",", "."));
    if (
      !Number.isFinite(seconds) ||
      seconds < 0 ||
      (maxSeconds !== undefined && seconds > maxSeconds)
    ) {
      setLocalError(
        maxSeconds
          ? `Use um valor entre 0 e ${maxSeconds.toFixed(2)} segundos.`
          : "Informe um tempo válido em segundos.",
      );
      return;
    }
    setLocalError(null);
    const milliseconds = Math.round(seconds * 1000);
    setDraft((milliseconds / 1000).toFixed(2));
    onCommit(milliseconds);
  }

  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <div className="relative">
        <Input
          id={id}
          type="text"
          inputMode="decimal"
          value={draft}
          disabled={disabled}
          aria-invalid={Boolean(invalid || localError)}
          aria-describedby={
            [describedBy, localError ? `${id}-error` : null].filter(Boolean).join(" ") || undefined
          }
          onChange={(event) => {
            setDraft(event.target.value);
            setLocalError(null);
          }}
          onBlur={(event) => commit(event.currentTarget.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              event.currentTarget.blur();
            }
            if (event.key === "Escape") {
              event.preventDefault();
              setDraft(formatted);
              setLocalError(null);
            }
          }}
          className="pr-8 tabular-nums"
        />
        <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-[10px] text-muted-foreground">
          s
        </span>
      </div>
      {localError ? (
        <p id={`${id}-error`} className="text-[10px] leading-relaxed text-destructive" role="alert">
          {localError}
        </p>
      ) : null}
    </div>
  );
}

function VisualAppearanceControls({
  event,
  disabled,
  onChange,
}: {
  event: VisualTimelineEvent;
  disabled: boolean;
  onChange: (patch: Partial<VisualTimelineEvent>) => void;
}) {
  const position = event.screenPosition || DEFAULT_VISUAL_APPEARANCE.screenPosition;
  const color = /^#[0-9a-fA-F]{6}$/.test(event.backgroundColor || "")
    ? event.backgroundColor!
    : DEFAULT_VISUAL_APPEARANCE.backgroundColor;
  const opacity = Math.min(
    1,
    Math.max(0.15, event.backgroundOpacity ?? DEFAULT_VISUAL_APPEARANCE.backgroundOpacity),
  );
  const positionLabel =
    VISUAL_SCREEN_POSITIONS.find((option) => option.id === position)?.label || "Superior direito";
  const customized =
    position !== DEFAULT_VISUAL_APPEARANCE.screenPosition ||
    color.toLowerCase() !== DEFAULT_VISUAL_APPEARANCE.backgroundColor ||
    opacity !== DEFAULT_VISUAL_APPEARANCE.backgroundOpacity;
  const presets = ["#073e4b", "#111827", "#164e3f", "#4a1f2b", "#312e81"];

  return (
    <details
      className={`group/appearance mt-3 overflow-hidden rounded-lg border bg-background/75 ${
        disabled ? "opacity-60" : ""
      }`}
    >
      <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 px-3 py-2.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring">
        <span className="flex items-center gap-2 text-xs font-semibold">
          <Move className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
          Posição e aparência
        </span>
        <span className="flex min-w-0 items-center gap-2 text-[10px] text-muted-foreground">
          <span
            className="h-4 w-4 shrink-0 rounded border shadow-sm"
            style={{ backgroundColor: color, opacity }}
            aria-hidden="true"
          />
          <span className="truncate">{positionLabel}</span>
          <span className="shrink-0 tabular-nums">{Math.round(opacity * 100)}%</span>
        </span>
      </summary>

      <div className="border-t p-3">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <span className="rounded-full bg-primary/10 px-2 py-1 text-[10px] font-semibold text-primary">
            Ajuste local · não usa Claude
          </span>
          {customized ? (
            <button
              type="button"
              disabled={disabled}
              className="min-h-9 cursor-pointer rounded-md px-2.5 text-[11px] font-semibold text-primary transition-colors hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              onClick={() => onChange(DEFAULT_VISUAL_APPEARANCE)}
            >
              Restaurar padrão
            </button>
          ) : null}
        </div>

        <div className="grid gap-4 sm:grid-cols-[9rem_minmax(0,1fr)]">
          <fieldset disabled={disabled} className="min-w-0">
            <legend className="mb-2 text-xs font-semibold">Onde aparece</legend>
            <div
              className="grid aspect-[9/16] w-36 grid-cols-3 grid-rows-3 gap-1 rounded-xl border-2 bg-[linear-gradient(145deg,#4b5f6b,#17242c)] p-1.5 shadow-inner"
              aria-label="Posição do visual na tela"
            >
              {VISUAL_SCREEN_POSITIONS.map((option) => {
                const selected = option.id === position;
                return (
                  <button
                    key={option.id}
                    type="button"
                    title={option.label}
                    aria-label={option.label}
                    aria-pressed={selected}
                    disabled={disabled}
                    onClick={() => onChange({ screenPosition: option.id })}
                    className={`flex min-h-11 cursor-pointer items-center justify-center rounded-md border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white disabled:cursor-not-allowed ${
                      selected
                        ? "border-white bg-white/15 shadow-sm"
                        : "border-white/10 bg-black/10 hover:border-white/45 hover:bg-white/10"
                    }`}
                  >
                    <span
                      className={`block rounded-sm border border-white/70 shadow ${
                        selected ? "h-5 w-8" : "h-2.5 w-4 bg-white/20"
                      }`}
                      style={selected ? { backgroundColor: color, opacity } : undefined}
                      aria-hidden="true"
                    />
                  </button>
                );
              })}
            </div>
            <p className="mt-2 text-center text-[11px] font-medium text-muted-foreground">
              {positionLabel}
            </p>
          </fieldset>

          <div className="space-y-4">
            <div className="space-y-2">
              <div className="flex items-center gap-1.5 text-xs font-semibold">
                <Palette className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
                Cor do fundo
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <label
                  htmlFor={`visual-color-${event.id}`}
                  className="flex min-h-11 cursor-pointer items-center gap-2 rounded-md border bg-background px-2.5 text-[11px] font-medium focus-within:ring-2 focus-within:ring-ring"
                >
                  <input
                    id={`visual-color-${event.id}`}
                    type="color"
                    value={color}
                    disabled={disabled}
                    onChange={(changeEvent) =>
                      onChange({ backgroundColor: changeEvent.target.value.toLowerCase() })
                    }
                    className="h-7 w-8 cursor-pointer border-0 bg-transparent p-0 disabled:cursor-not-allowed"
                  />
                  {color.toUpperCase()}
                </label>
                {presets.map((preset) => (
                  <button
                    key={preset}
                    type="button"
                    title={`Usar a cor ${preset.toUpperCase()}`}
                    aria-label={`Usar a cor ${preset.toUpperCase()}`}
                    aria-pressed={color.toLowerCase() === preset}
                    disabled={disabled}
                    onClick={() => onChange({ backgroundColor: preset })}
                    className="h-11 w-11 cursor-pointer rounded-md border-2 border-background shadow-sm ring-1 ring-border transition-shadow hover:ring-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                    style={{ backgroundColor: preset }}
                  />
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <Label htmlFor={`visual-opacity-${event.id}`}>Opacidade do fundo</Label>
                <span className="text-xs font-semibold tabular-nums text-primary">
                  {Math.round(opacity * 100)}%
                </span>
              </div>
              <Input
                id={`visual-opacity-${event.id}`}
                type="range"
                min={15}
                max={100}
                step={1}
                value={Math.round(opacity * 100)}
                disabled={disabled}
                onInput={(inputEvent) =>
                  onChange({ backgroundOpacity: Number(inputEvent.currentTarget.value) / 100 })
                }
                className="cursor-pointer px-0 disabled:cursor-not-allowed"
              />
              <div className="flex justify-between text-[10px] text-muted-foreground">
                <span>Mais transparente</span>
                <span>Mais sólido</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </details>
  );
}

function FiveStackEditorCard({
  value,
  onChange,
  onLineChange,
}: {
  value: LocalVideoKitFiveStack;
  onChange: (patch: Partial<LocalVideoKitFiveStack>) => void;
  onLineChange: (index: number, value: string) => void;
}) {
  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b bg-muted/20 pb-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Film className="h-4 w-4 text-primary" />
              Lista em 5 pontos
            </CardTitle>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              Apresente cinco informações em sequência sobre o vídeo, sem cobrir toda a imagem.
            </p>
          </div>
          <Switch
            checked={value.enabled}
            onCheckedChange={(enabled) => onChange({ enabled })}
            aria-label="Aplicar a Pilha de Cinco"
          />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="five-stack-start">Entra aos</Label>
            <Input
              id="five-stack-start"
              type="number"
              min={0.5}
              step={0.25}
              disabled={!value.enabled}
              value={value.startSeconds ?? ""}
              placeholder="Automático"
              onChange={(event) =>
                onChange({ startSeconds: event.target.value ? Number(event.target.value) : null })
              }
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="five-stack-duration">Fica na tela por</Label>
            <Input
              id="five-stack-duration"
              type="number"
              min={1}
              max={8}
              step={0.25}
              disabled={!value.enabled}
              value={value.durationSeconds ?? 4.5}
              onChange={(event) => onChange({ durationSeconds: Number(event.target.value) || 4.5 })}
            />
          </div>
        </div>

        <div className="space-y-2">
          {value.lines.slice(0, 5).map((line, index) => {
            const highlighted = index === 4;
            return (
              <div key={index} className="flex items-center gap-2">
                <span
                  className="flex h-9 w-10 shrink-0 items-center justify-center border-l-[3px] bg-[#08181c] text-xs font-extrabold tracking-wider"
                  style={{
                    borderColor: highlighted ? "#ffb84d" : "#6fe3d2",
                    color: highlighted ? "#ffb84d" : "#6fe3d2",
                  }}
                >
                  {String(index + 1).padStart(2, "0")}
                </span>
                <Input
                  value={line}
                  disabled={!value.enabled}
                  maxLength={118}
                  aria-label={`Texto da linha ${index + 1}`}
                  onChange={(event) => onLineChange(index, event.target.value)}
                />
              </div>
            );
          })}
        </div>

        <p className="text-[11px] leading-relaxed text-muted-foreground">
          As linhas entram em sequência de 0,1 s. A quinta recebe o destaque âmbar; as demais usam
          ciano e vidro translúcido.
        </p>
      </CardContent>
    </Card>
  );
}

function ClaudeMidnightModelsCard({
  value,
  timingIssuesByItemId,
  videoDurationSeconds,
  onChange,
  onFieldChange,
}: {
  value: LocalVideoKitClaudeInserts;
  timingIssuesByItemId: Record<string, string[]>;
  videoDurationSeconds: number;
  onChange: (id: LocalVideoKitClaudeModelId, patch: Partial<LocalVideoKitClaudeModel>) => void;
  onFieldChange: (id: LocalVideoKitClaudeModelId, index: number, value: string) => void;
}) {
  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b bg-muted/20 pb-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <WandSparkles className="h-4 w-4 text-primary" />
              Modelos visuais
            </CardTitle>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              Escolha cartelas prontas para dados, notícias, mecanismos, evidências ou fontes.
            </p>
          </div>
          <span className="shrink-0 border border-[#6fe3d2]/35 bg-[#08181c] px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-[#6fe3d2]">
            Midnight
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {CLAUDE_MIDNIGHT_MODEL_SPECS.map((spec) => {
          const model = value[spec.id];
          const timingIssues = timingIssuesByItemId[`manual:${spec.id}`] || [];
          const timingDefaults = MANUAL_VISUAL_TIMING[spec.id];
          const resolvedStart =
            model.startSeconds ?? videoDurationSeconds * timingDefaults.startRatio;
          const resolvedDuration = Math.min(
            8,
            Math.max(1, model.durationSeconds ?? timingDefaults.durationSeconds),
          );
          const resolvedEnd = Math.min(
            videoDurationSeconds || resolvedStart + resolvedDuration,
            resolvedStart + resolvedDuration,
          );
          return (
            <article
              key={spec.id}
              className={`overflow-hidden border transition-colors ${
                timingIssues.length
                  ? "border-destructive/45 bg-destructive/[0.035]"
                  : model.enabled
                    ? "border-[#6fe3d2]/45 bg-[#08181c]/35"
                    : "bg-muted/15"
              }`}
            >
              <div className="flex items-start justify-between gap-3 p-3">
                <div>
                  <div className="text-sm font-semibold">{spec.title}</div>
                  <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                    {spec.detail}
                  </p>
                </div>
                <Switch
                  checked={model.enabled}
                  onCheckedChange={(enabled) => onChange(spec.id, { enabled })}
                  aria-label={`Aplicar ${spec.title}`}
                />
              </div>

              {model.enabled ? (
                <div className="space-y-3 border-t border-[#6fe3d2]/18 p-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <Label htmlFor={`claude-${spec.id}-start`}>Entra aos</Label>
                      <Input
                        id={`claude-${spec.id}-start`}
                        type="number"
                        min={0.5}
                        step={0.25}
                        value={model.startSeconds ?? ""}
                        placeholder={`Automático: ${resolvedStart.toFixed(2)}s`}
                        onChange={(event) =>
                          onChange(spec.id, {
                            startSeconds: event.target.value ? Number(event.target.value) : null,
                          })
                        }
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor={`claude-${spec.id}-duration`}>Sai aos</Label>
                      <Input
                        id={`claude-${spec.id}-duration`}
                        type="number"
                        min={resolvedStart + 1}
                        max={videoDurationSeconds || undefined}
                        step={0.25}
                        value={Number.isFinite(resolvedEnd) ? Number(resolvedEnd.toFixed(2)) : ""}
                        onChange={(event) =>
                          onChange(spec.id, {
                            startSeconds: resolvedStart,
                            durationSeconds: Math.max(
                              1,
                              Math.min(8, Number(event.target.value) - resolvedStart),
                            ),
                          })
                        }
                      />
                    </div>
                  </div>

                  <div className="flex items-center justify-between gap-3 text-[10px] text-muted-foreground">
                    <span className="tabular-nums">Duração: {resolvedDuration.toFixed(2)}s</span>
                    {model.startSeconds === null ? (
                      <span>Entrada distribuída automaticamente</span>
                    ) : null}
                  </div>

                  {timingIssues.length ? (
                    <ul
                      className="space-y-1 rounded-lg border border-destructive/25 bg-background p-2.5 text-[11px] leading-relaxed text-destructive"
                      role="alert"
                    >
                      {timingIssues.map((issue) => (
                        <li key={issue}>• {issue}</li>
                      ))}
                    </ul>
                  ) : null}

                  <div className="grid gap-3 sm:grid-cols-2">
                    {model.fields.map((field, index) => {
                      const fieldId = `claude-${spec.id}-field-${index}`;
                      return (
                        <div
                          key={fieldId}
                          className={`space-y-1.5 ${
                            field.length > 70 || (spec.id === "editorialClip" && index === 3)
                              ? "sm:col-span-2"
                              : ""
                          }`}
                        >
                          <Label htmlFor={fieldId}>
                            {spec.fieldLabels[index] || `Texto ${index + 1}`}
                          </Label>
                          <Input
                            id={fieldId}
                            value={field}
                            maxLength={190}
                            onChange={(event) => onFieldChange(spec.id, index, event.target.value)}
                          />
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : null}
            </article>
          );
        })}
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          Os tempos automáticos distribuem as cartelas pelo vídeo. Ative somente as que quiser usar
          no render; áreas sem elementos continuam 100% transparentes.
        </p>
      </CardContent>
    </Card>
  );
}

function InsertTimeInput({
  id,
  label,
  value,
  max,
  onChange,
}: {
  id: string;
  label: string;
  value: number;
  max?: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <div className="relative">
        <Input
          id={id}
          type="number"
          min={0}
          max={max}
          step={0.25}
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
          className="pr-8 tabular-nums"
        />
        <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-[10px] text-muted-foreground">
          s
        </span>
      </div>
    </div>
  );
}

function accentWithOpacity(color: string, opacity: string) {
  return /^#[0-9a-fA-F]{6}$/.test(color) ? `${color}${opacity}` : undefined;
}

function MotionPreview({
  preset,
  accent,
}: {
  preset: LocalVideoKitConfig["motionPreset"];
  accent: string;
}) {
  const frameClass = preset === "social" ? "inset-7" : preset === "subtle" ? "inset-5" : "inset-1";
  const label =
    preset === "social" ? "Zoom suave 22%" : preset === "subtle" ? "Zoom suave 14%" : "Sem zoom";
  const moments = preset === "social" ? [12, 34, 58, 80] : preset === "subtle" ? [20, 54, 82] : [];

  return (
    <div
      className="rounded-xl border bg-muted/20 p-3"
      aria-label="Prévia do ritmo de enquadramento"
    >
      <div className="relative h-32 overflow-hidden rounded-lg bg-[radial-gradient(circle_at_50%_24%,#506879_0%,#1c2d37_48%,#091319_100%)]">
        <div className="absolute left-1/2 top-5 h-10 w-10 -translate-x-1/2 rounded-full border border-white/10 bg-white/16" />
        <div className="absolute left-1/2 top-14 h-24 w-20 -translate-x-1/2 rounded-t-[2rem] border border-white/10 bg-white/12" />
        <div
          className={`absolute ${frameClass} rounded-md border`}
          style={{ borderColor: accentWithOpacity(accent, preset === "none" ? "3D" : "B3") }}
        />
        <span className="absolute right-2 top-2 rounded bg-black/45 px-2 py-1 text-[9px] font-semibold uppercase tracking-wide text-white/75">
          {label}
        </span>
      </div>
      <div className="relative mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
        {moments.map((position) => (
          <span
            key={position}
            className="absolute top-0 h-full w-[11%] rounded-full"
            style={{
              left: `${position}%`,
              backgroundImage: `linear-gradient(90deg, transparent, ${accent}, ${accent}, transparent)`,
            }}
          />
        ))}
      </div>
      <div className="mt-1.5 flex justify-between text-[9px] font-medium uppercase tracking-wide text-muted-foreground">
        <span>Início</span>
        <span>{moments.length ? `${moments.length} momentos` : "Enquadramento fixo"}</span>
        <span>Fim</span>
      </div>
    </div>
  );
}

function CaptionPreview({ config }: { config: LocalVideoKitConfig }) {
  const positionClass =
    config.captionPosition === "upper"
      ? "justify-start pt-5"
      : config.captionPosition === "center"
        ? "justify-center"
        : "justify-end pb-6";
  const captionClass =
    config.captionStyle === "clean"
      ? "rounded-xl border border-white/15 bg-slate-950/85 px-3 py-2 text-base font-bold leading-tight shadow-xl"
      : config.captionStyle === "editorial"
        ? "font-serif text-xl font-bold italic leading-tight drop-shadow-[0_3px_1px_rgba(0,0,0,0.9)]"
        : "text-lg font-black uppercase leading-none tracking-tight drop-shadow-[0_3px_1px_rgba(0,0,0,0.95)]";

  return (
    <div
      className={`relative flex h-44 flex-col items-center overflow-hidden rounded-xl border bg-[radial-gradient(circle_at_50%_25%,#496578_0%,#172630_48%,#081116_100%)] px-5 ${positionClass}`}
      aria-label="Prévia do estilo da legenda"
    >
      <div className="absolute left-1/2 top-4 h-24 w-16 -translate-x-1/2 rounded-full bg-white/8 blur-xl" />
      <div className={`relative z-10 mx-auto max-w-[290px] text-center text-white ${captionClass}`}>
        Informação com{" "}
        <span style={{ color: config.highlightKeywords ? config.accent : undefined }}>clareza</span>
      </div>
      <span className="absolute bottom-2 right-2 rounded bg-black/35 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide text-white/65">
        Prévia
      </span>
    </div>
  );
}

function TextField({
  id,
  label,
  value,
  onChange,
  optional = false,
  disabled = false,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  optional?: boolean;
  disabled?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-3">
        <Label htmlFor={id}>{label}</Label>
        {optional ? <span className="text-[11px] text-muted-foreground">Opcional</span> : null}
      </div>
      <Input
        id={id}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

function PieceSwitch({
  label,
  detail,
  checked,
  onCheckedChange,
}: {
  label: string;
  detail: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg px-2 py-2.5">
      <div>
        <div className="text-sm font-medium">{label}</div>
        <div className="text-xs text-muted-foreground">{detail}</div>
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} aria-label={`Aplicar ${label}`} />
    </div>
  );
}

function VideoPanel({
  title,
  url,
  pending = false,
  onDuration,
}: {
  title: string;
  url: string | null;
  pending?: boolean;
  onDuration?: (duration: number) => void;
}) {
  return (
    <div>
      <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </div>
      <div className="relative mx-auto aspect-[9/16] w-full max-w-[360px] overflow-hidden rounded-xl border bg-[#0f0f10] shadow-sm">
        {url ? (
          <video
            src={url}
            controls
            playsInline
            preload="metadata"
            onLoadedMetadata={(event) => onDuration?.(event.currentTarget.duration)}
            className="h-full w-full object-contain"
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center px-8 text-center text-muted-foreground">
            {pending ? (
              <LoaderCircle className="h-7 w-7 animate-spin" />
            ) : (
              <Film className="h-7 w-7" />
            )}
            <p className="mt-3 text-xs leading-relaxed">
              {pending ? "Renderizando localmente..." : "O resultado aparecerá aqui."}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
