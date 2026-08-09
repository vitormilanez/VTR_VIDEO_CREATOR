import contractData from "../../../shared/script_editor_contract.json";

export type DurationPreset = 10 | 15 | 30 | 45 | 60;
export type DurationStatus = "ideal" | "warning" | "blocking";
export type MedicalReviewStatus = "not_required" | "recommended" | "required" | "approved";
export type TitleAlignmentStatus = "aligned" | "possible_mismatch" | "unknown";
export type GenerationEligibility = "allowed" | "blocked";
export type EditorOperation = "medical_rewrite" | "fit_duration";

export interface SpeechProfile {
  id: string;
  language: string;
  wordsPerMinute: number;
  tolerancePercent: number;
  generationTargetMinPercent: number;
  generationTargetMaxPercent: number;
}

export interface DurationAssessment {
  durationSeconds: DurationPreset;
  wordCount: number;
  estimatedSeconds: number;
  estimatedSecondsDisplay: string;
  targetWords: number;
  hardLimitWords: number;
  generationMinWords: number;
  generationMaxWords: number;
  status: DurationStatus;
  message: string;
}

export interface TitleAlignment {
  status: TitleAlignmentStatus;
  suggestedTitle?: string;
  reason?: string;
}

export interface MedicalSafetyAssessment {
  meaningPreserved: boolean;
  newClaimsAdded: boolean;
  unsupportedPersonalExperienceAdded: boolean;
  requiresHumanReview: boolean;
  reasons: string[];
}

export interface QualityCheck {
  id: string;
  label: string;
  source: "deterministic" | "ai" | "ai+deterministic" | "policy";
  status: "pass" | "info" | "warning" | "blocking" | DurationStatus;
  detail: string;
}

export interface EditorAssistResult {
  ok: boolean;
  operation: EditorOperation;
  script: string;
  summaryOfChanges: string[];
  titleAlignment: TitleAlignment;
  medicalSafety: MedicalSafetyAssessment;
  warnings: string[];
  durationAssessment: DurationAssessment;
  medicalReviewStatus: MedicalReviewStatus;
  qualityChecks: QualityCheck[];
  promptVersion: string;
  provider: string;
  model: string;
  cacheHit: boolean;
  deduplicated?: boolean;
  retryCount: number;
  noOp?: boolean;
  message?: string;
  schemaValid: boolean;
  technicalError?: string | null;
  previousScript?: string;
}

export interface GenerationGateInput {
  speech: string;
  durationSeconds: DurationPreset;
  aiOperationInFlight: boolean;
  schemaValid: boolean;
  technicalError?: string | null;
  medicalReviewStatus: MedicalReviewStatus;
  humanReviewApproved: boolean;
  scriptStatus: string;
  finalSaved: boolean;
  finalConfirmed: boolean;
}

export interface GenerationGate {
  eligibility: GenerationEligibility;
  allowed: boolean;
  reason: string | null;
  reasons: Array<{ code: string; message: string }>;
}

type Contract = {
  contractVersion: string;
  durationPresets: number[];
  durationStatuses: DurationStatus[];
  medicalReviewStatuses: MedicalReviewStatus[];
  titleAlignmentStatuses: TitleAlignmentStatus[];
  generationEligibilityStatuses: GenerationEligibility[];
  generationGateReasonCodes: string[];
  wordPattern: string;
  speechProfile: SpeechProfile;
  editorialProfile: { id: string; language: string; promptVersion: string };
};

export const SCRIPT_EDITOR_CONTRACT = contractData as Contract;
export const SCRIPT_EDITOR_CONTRACT_VERSION = SCRIPT_EDITOR_CONTRACT.contractVersion;
export const DURATION_PRESETS = SCRIPT_EDITOR_CONTRACT.durationPresets as DurationPreset[];
export const DEFAULT_SPEECH_PROFILE = SCRIPT_EDITOR_CONTRACT.speechProfile;
export const MEDICAL_EDITORIAL_PROMPT_VERSION =
  SCRIPT_EDITOR_CONTRACT.editorialProfile.promptVersion;
const WORD_PATTERN = new RegExp(SCRIPT_EDITOR_CONTRACT.wordPattern, "gu");

export function normalizeScriptText(text: string): string {
  return (text || "").normalize("NFKC").replace(/\s+/gu, " ").trim();
}

export function countScriptWords(text: string): number {
  return normalizeScriptText(text).match(WORD_PATTERN)?.length ?? 0;
}

export function assessScriptDuration(
  text: string,
  durationSeconds: DurationPreset,
  profile: SpeechProfile = DEFAULT_SPEECH_PROFILE,
): DurationAssessment {
  if (!DURATION_PRESETS.includes(durationSeconds)) {
    throw new Error(`Preset de duração não suportado: ${durationSeconds}`);
  }
  const targetWords = Math.round((durationSeconds * profile.wordsPerMinute) / 60);
  const hardLimitWords = Math.ceil(targetWords * (1 + profile.tolerancePercent));
  const generationMinWords = Math.floor(targetWords * profile.generationTargetMinPercent);
  const generationMaxWords = Math.floor(targetWords * profile.generationTargetMaxPercent);
  const wordCount = countScriptWords(text);
  const estimatedSeconds = Number(((wordCount * 60) / profile.wordsPerMinute).toFixed(2));
  let status: DurationStatus;
  let message: string;
  if (wordCount <= targetWords) {
    status = "ideal";
    message = `Duração ideal para ${durationSeconds}s.`;
  } else if (wordCount <= hardLimitWords) {
    status = "warning";
    message = `Texto ligeiramente acima da meta de ${targetWords} palavras. Pode seguir para o HeyGen, mas vale revisar o ritmo.`;
  } else {
    status = "blocking";
    message = `Texto muito longo para ${durationSeconds}s (${wordCount} palavras). Ajuste a duração antes de enviar ao HeyGen; máximo seguro: ${hardLimitWords}.`;
  }
  return {
    durationSeconds,
    wordCount,
    estimatedSeconds,
    estimatedSecondsDisplay: `~${Math.round(estimatedSeconds)}s`,
    targetWords,
    hardLimitWords,
    generationMinWords,
    generationMaxWords,
    status,
    message,
  };
}

export function medicalReviewForRisk(riskLevel: string, approved = false): MedicalReviewStatus {
  if (approved) return "approved";
  const normalized = normalizeScriptText(riskLevel).toLocaleLowerCase("pt-BR");
  if (["alto", "high"].includes(normalized)) return "required";
  if (["medio", "médio", "moderado", "medium"].includes(normalized)) return "recommended";
  return "not_required";
}

export function evaluateGenerationGate(input: GenerationGateInput): GenerationGate {
  const reasons: Array<{ code: string; message: string }> = [];
  if (!normalizeScriptText(input.speech)) {
    reasons.push({ code: "speech_empty", message: "A fala final está vazia." });
  }
  const duration = assessScriptDuration(input.speech, input.durationSeconds);
  if (duration.status === "blocking") {
    reasons.push({ code: "duration_blocking", message: duration.message });
  }
  if (input.aiOperationInFlight) {
    reasons.push({ code: "ai_in_flight", message: "Aguarde a operação de IA terminar." });
  }
  if (!input.schemaValid) {
    reasons.push({
      code: "ai_schema_invalid",
      message: "A última saída de IA não passou na validação.",
    });
  }
  if (input.technicalError) {
    reasons.push({
      code: "technical_error",
      message: "Resolva o erro técnico do editor antes de gerar.",
    });
  }
  if (input.medicalReviewStatus === "required" && !input.humanReviewApproved) {
    reasons.push({
      code: "medical_review_required",
      message: "A revisão médica obrigatória ainda não foi aprovada.",
    });
  }
  if (input.scriptStatus !== "aprovado_clinicamente") {
    reasons.push({
      code: "script_not_ready",
      message: "Marque o roteiro como Pronto após a revisão editorial.",
    });
  }
  if (!input.finalSaved) {
    reasons.push({ code: "unsaved", message: "Salve a fala final antes de gerar o vídeo." });
  }
  if (!input.finalConfirmed) {
    reasons.push({ code: "not_confirmed", message: "Confirme a geração do vídeo final." });
  }
  return {
    eligibility: reasons.length ? "blocked" : "allowed",
    allowed: reasons.length === 0,
    reason: reasons[0]?.message ?? null,
    reasons,
  };
}

export function durationStatusLabel(status: DurationStatus): string {
  if (status === "blocking") return "Ajuste necessário";
  if (status === "warning") return "Atenção ao ritmo";
  return "Duração ideal";
}
