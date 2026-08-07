// Tipos e seeds do AI Video Creator. Todos os dados sao mockados nesta fase.
// TODO(cloud): substituir por tabelas Supabase (trends, ideas, scripts, ...).

export type ThemeFamily =
  "medicamento" | "comportamento" | "metabolismo" | "obesidade" | "educativo";

export type RiskLevel = "baixo" | "medio" | "alto";
export type Prioridade = "alta" | "media" | "baixa";

export type TrendStatus = "novo" | "em_analise" | "descartado";
export type IdeaStatus = "novo" | "em_analise" | "aprovado" | "descartado";
export type ScriptStatus =
  "aguardando_validacao" | "aprovado_clinicamente" | "rejeitado" | "em_revisao";
/** Tom editorial escolhido pelo usuario ANTES da geracao paga do texto falado. */
export type EditorialTone = "positivo" | "neutro" | "apreensivo";
export type VideoJobStatus = "fila" | "processando" | "pronto" | "erro";
export type PostStatus = "pendente" | "agendado" | "publicado";
export type Canal = "instagram" | "tiktok" | "youtube_shorts";

export interface Trend {
  id: string;
  titulo: string;
  fonte: string;
  volume: number;
  familia: ThemeFamily;
  risco: RiskLevel;
  prioridade: Prioridade;
  status: TrendStatus;
  criadoEm: string;
  notas?: string;
  // Campos do radar real (Google Sheets)
  subtema?: string;
  sinal?: string;
  dorPublico?: string;
  link?: string;
  potencial?: number; // 0..10
}

export interface Idea {
  id: string;
  trendId?: string;
  titulo: string;
  familia: ThemeFamily;
  hook: string;
  angulo: string;
  tipo?: string;
  publicoDor?: string;
  cta: string;
  linkOrigem?: string;
  observacaoCompliance: string;
  prioridade: Prioridade;
  status: IdeaStatus;
  criadoEm: string;
}

export interface Script {
  id: string;
  ideaId?: string;
  categoria: ThemeFamily;
  tema: string;
  titulo: string;
  hook: string;
  dorConflito: string;
  explicacaoSimples: string;
  virada: string;
  cta: string;
  cuidadosMedicos: string;
  risco: RiskLevel;
  prioridade: Prioridade;
  formatoSugerido: string;
  aprovador?: string;
  link?: string;
  status: ScriptStatus;
  criadoEm: string;
  validadoEm?: string;
  motivoRejeicao?: string;
  /** Tom editorial usado na geracao com IA (ausente em roteiros criados por template). */
  editorialTone?: EditorialTone;
  /** Texto falado completo gerado pela IA, pronto para revisao na tela de roteiro. */
  textoFalado?: string;
  /** Encerramento escolhido pelo usuario para este roteiro. */
  outroText?: string;
  /** Provedor que efetivamente escreveu o texto; usado para auditoria do fluxo. */
  generationProvider?: "claude" | "fallback" | "manual";
  /** Versao do fluxo que criou o roteiro, preservada no Sheets. */
  generationFlowVersion?: string;
}

export interface VideoJob {
  id: string;
  scriptId: string;
  status: VideoJobStatus;
  provider: "heygen" | "local";
  progresso: number; // 0..100
  criadoEm: string;
  atualizadoEm: string;
  videoUrl?: string;
  thumbnailUrl?: string;
  duracaoSegundos?: number;
  erro?: string;
  remoteSessionId?: string;
  remoteVideoId?: string;
  isPreview?: boolean;
  isScene?: boolean;
  isComposed?: boolean;
  sceneId?: string;
  sceneOrder?: number;
  sourceSceneJobs?: string[];
  outputPath?: string;
  sceneCount?: number;
  visualCount?: number;
  productionSettings?: {
    generationMode?: "direct" | "video_agent" | "cinematic";
    voiceSpeed?: number;
    [key: string]: unknown;
  };
}

export interface CalendarPost {
  id: string;
  scriptId?: string;
  videoJobId?: string;
  titulo: string;
  dataAgendada: string; // ISO
  canal: Canal;
  status: PostStatus;
  publicadoEm?: string;
  // Campos reais da aba Calendario
  tema?: string;
  formato?: string;
  responsavel?: string;
  link?: string;
}

export interface PerformanceMetric {
  id: string;
  postId: string;
  tema?: string;
  canal?: Canal;
  views: number;
  likes: number;
  retencao?: number; // %
  comments: number;
  shares: number;
  saves: number;
  novosSeguidores?: number;
  cliques?: number;
  leads?: number;
  nota?: string;
  aprendizado?: string;
  link?: string;
  coletadoEm: string;
  /** Preenchidos quando o Link post bate com um post do Calendario (ver /api/state). */
  calendarPostId?: string | null;
  scriptId?: string | null;
  videoJobId?: string | null;
  formatoSugerido?: string | null;
}

export interface AppSettings {
  temasPrioritarios: string[];
  palavrasProibidas: string[];
  radar: {
    termosExtras: string[];
    fontes: Array<"google_news" | "gdelt" | "pubmed" | "reddit" | "serpapi">;
    periodo: "dia" | "semana" | "quinzena" | "mes";
    limitePorBusca: number;
    potencialMinimo: number;
  };
  integracoes: {
    heygen: boolean;
    meta: boolean;
    googleSheets: boolean;
  };
  heygen: {
    defaultAvatarId: string | null;
    favoriteAvatarIds: string[];
  };
}

// Configuracoes padrao (nao sao dados mock de dominio; sao defaults de app).
export const defaultSettings: AppSettings = {
  temasPrioritarios: [
    "obesidade",
    "GLP-1",
    "Mounjaro",
    "Ozempic",
    "Wegovy",
    "dieta",
    "metabolismo",
    "comportamento alimentar",
  ],
  palavrasProibidas: [
    "cura",
    "milagre",
    "garantido",
    "sem esforco",
    "resultado certo",
    "emagrece rapido",
    "prometo",
  ],
  radar: {
    termosExtras: ["atividade fisica", "sono", "compulsao alimentar"],
    fontes: ["google_news", "gdelt", "pubmed", "reddit", "serpapi"],
    periodo: "semana",
    limitePorBusca: 20,
    potencialMinimo: 1,
  },
  integracoes: { heygen: false, meta: false, googleSheets: true },
  heygen: { defaultAvatarId: null, favoriteAvatarIds: [] },
};
