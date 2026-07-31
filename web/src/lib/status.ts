import type {
  EditorialTone,
  IdeaStatus,
  PostStatus,
  Prioridade,
  RiskLevel,
  ScriptStatus,
  TrendStatus,
  VideoJobStatus,
} from "./mock-data";

export type StatusTone = "info" | "success" | "warn" | "danger" | "neutral";

export const statusToneClass: Record<StatusTone, string> = {
  info: "bg-status-info/15 text-status-info border-status-info/30",
  success: "bg-status-success/25 text-status-success-foreground border-status-success/40",
  warn: "bg-status-warn/20 text-status-warn-foreground border-status-warn/40",
  danger: "bg-status-danger/15 text-status-danger border-status-danger/30",
  neutral: "bg-status-neutral text-status-neutral-foreground border-status-neutral",
};

export const trendStatusLabel: Record<TrendStatus, { label: string; tone: StatusTone }> = {
  novo: { label: "Novo", tone: "info" },
  em_analise: { label: "Em analise", tone: "warn" },
  descartado: { label: "Descartado", tone: "neutral" },
};

export const ideaStatusLabel: Record<IdeaStatus, { label: string; tone: StatusTone }> = {
  novo: { label: "Novo", tone: "info" },
  em_analise: { label: "Em analise", tone: "warn" },
  aprovado: { label: "Aprovado", tone: "success" },
  descartado: { label: "Descartado", tone: "neutral" },
};

// Sem passo de validacao medica: status neutro de progresso do roteiro.
export const scriptStatusLabel: Record<ScriptStatus, { label: string; tone: StatusTone }> = {
  aguardando_validacao: { label: "Rascunho", tone: "neutral" },
  em_revisao: { label: "Em edicao", tone: "info" },
  aprovado_clinicamente: { label: "Pronto", tone: "success" },
  rejeitado: { label: "Arquivado", tone: "neutral" },
};

export const videoJobStatusLabel: Record<VideoJobStatus, { label: string; tone: StatusTone }> = {
  fila: { label: "Na fila", tone: "info" },
  processando: { label: "Processando", tone: "warn" },
  pronto: { label: "Pronto", tone: "success" },
  erro: { label: "Erro", tone: "danger" },
};

export const postStatusLabel: Record<PostStatus, { label: string; tone: StatusTone }> = {
  pendente: { label: "Pendente", tone: "warn" },
  agendado: { label: "Agendado", tone: "info" },
  publicado: { label: "Publicado", tone: "success" },
};

export const riskLabel: Record<RiskLevel, { label: string; tone: StatusTone }> = {
  baixo: { label: "Risco baixo", tone: "success" },
  medio: { label: "Risco medio", tone: "warn" },
  alto: { label: "Risco alto", tone: "danger" },
};

export const prioridadeLabel: Record<Prioridade, { label: string; tone: StatusTone }> = {
  alta: { label: "Prioridade alta", tone: "danger" },
  media: { label: "Prioridade media", tone: "warn" },
  baixa: { label: "Prioridade baixa", tone: "neutral" },
};

/** Tom editorial escolhido pelo usuario antes da geracao paga do texto falado. */
export const editorialToneLabel: Record<EditorialTone, { label: string; tone: StatusTone }> = {
  positivo: { label: "Tom positivo", tone: "success" },
  neutro: { label: "Tom neutro", tone: "info" },
  apreensivo: { label: "Tom apreensivo", tone: "warn" },
};

export const familiaLabel: Record<string, string> = {
  medicamento: "Medicamento",
  comportamento: "Comportamento",
  metabolismo: "Metabolismo",
  obesidade: "Obesidade",
  educativo: "Educativo",
};

export const canalLabel: Record<string, string> = {
  instagram: "Instagram",
  tiktok: "TikTok",
  youtube_shorts: "YouTube Shorts",
};
