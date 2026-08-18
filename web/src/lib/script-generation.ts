// Fluxo unico de geracao de roteiro com IA: o usuario escolhe o tom editorial
// ANTES da chamada paga, entao geramos o texto falado uma unica vez (nunca
// tres vezes por ideia, o que triplicaria o custo).
import {
  appendIdea,
  appendScript,
  generateCaptureHooks,
  generateScript,
  type ArticleAnalysis,
  type CaptureHooksResult,
} from "@/lib/api/local";
import { DEFAULT_OUTRO } from "@/lib/script-quality";
import type { EditorialTone, Idea, Script } from "@/lib/mock-data";
import type { DurationPreset } from "@/lib/script-editor";

export const SCRIPT_FLOW_VERSION = "social-to-script-v1";

/** ID deterministico: repetir a mesma acao nao duplica linhas nem consome um novo fluxo. */
function stableWorkflowId(prefix: string, ...parts: unknown[]): string {
  const value = JSON.stringify(parts);
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `${prefix}-${(hash >>> 0).toString(36)}`;
}

function isMedicationIdea(idea: Idea): boolean {
  return (
    idea.familia === "medicamento" ||
    /glp|mounjaro|ozempic|wegovy|semaglutida|tirzepatida/i.test(idea.titulo)
  );
}

/** Mesma heuristica de risco usada no template legado (script-builder.ts). */
export function riskForIdea(idea: Idea): Script["risco"] {
  if (isMedicationIdea(idea)) return "alto";
  if (idea.familia === "comportamento") return "alto";
  return "medio";
}

export interface GenerateScriptOptions {
  idea: Idea;
  articleAnalysis?: ArticleAnalysis | null;
  editorialTone: EditorialTone;
  durationSeconds?: DurationPreset;
  outro?: string;
  /** true quando a ideia ainda não foi persistida (sugestão de artigo/ideia manual). */
  persistIdea?: boolean;
}

export interface GenerateScriptResult {
  idea: Idea;
  script: Script;
  provider: "claude" | "fallback";
}

export async function generateAndPersistCaptureScripts(
  options: Pick<GenerateScriptOptions, "idea" | "persistIdea" | "editorialTone" | "outro"> & {
    durationSeconds: 10 | 15;
  },
): Promise<{
  idea: Idea;
  scripts: Script[];
  provider: "claude" | "fallback";
  analysis: CaptureHooksResult["analysis"];
  variants: CaptureHooksResult["variants"];
}> {
  const result = await generateCaptureHooks({
    durationSeconds: options.durationSeconds,
    trendId: options.idea.trendId || options.idea.id,
    titulo: options.idea.titulo,
    subtema: options.idea.tipo,
    sinal: options.idea.angulo,
    dorPublico: options.idea.publicoDor,
    notas: options.idea.observacaoCompliance,
    familia: options.idea.familia,
    prioridade: options.idea.prioridade,
    sourceUrl: options.idea.linkOrigem || null,
    editorialTone: options.editorialTone,
    outro: options.durationSeconds === 10 ? "" : options.outro || DEFAULT_OUTRO,
    requireClaude: true,
  });
  // Persistencia somente depois de o Claude responder e o backend validar as falas.
  const persistedIdea = options.persistIdea ? await appendIdea(options.idea) : options.idea;
  const scripts: Script[] = [];
  for (const variant of result.variants) {
    const saved = await appendScript({
      id: stableWorkflowId(
        "s-capture",
        persistedIdea.id,
        options.editorialTone,
        options.durationSeconds,
        variant.variant,
        variant.spokenText,
      ),
      ideaId: persistedIdea.id,
      categoria: persistedIdea.familia,
      tema: persistedIdea.titulo,
      titulo: `Captura ${variant.variant}: ${variant.title}`,
      hook: variant.hook,
      dorConflito: "",
      explicacaoSimples: "",
      virada: variant.turn,
      cta: options.durationSeconds === 10 ? "" : DEFAULT_OUTRO,
      cuidadosMedicos: variant.complianceNotes,
      risco: riskForIdea(persistedIdea),
      prioridade: persistedIdea.prioridade,
      formatoSugerido: `Hook de captura · ${options.durationSeconds} segundos`,
      status: "aguardando_validacao",
      criadoEm: new Date().toISOString(),
      link: persistedIdea.linkOrigem || undefined,
      editorialTone: options.editorialTone,
      textoFalado: variant.spokenText,
      outroText: options.durationSeconds === 10 ? "" : options.outro || DEFAULT_OUTRO,
      generationProvider: result.provider,
      generationFlowVersion: SCRIPT_FLOW_VERSION,
    });
    scripts.push(saved);
  }
  return {
    idea: persistedIdea,
    scripts,
    provider: result.provider,
    analysis: result.analysis,
    variants: result.variants,
  };
}

/**
 * Gera o roteiro + texto falado completo via IA (uma unica chamada paga) e
 * persiste ideia (se necessário) e roteiro no backend configurado.
 */
export async function generateAndPersistScript(
  options: GenerateScriptOptions,
): Promise<GenerateScriptResult> {
  const {
    idea,
    articleAnalysis,
    editorialTone,
    durationSeconds = 45,
    outro = DEFAULT_OUTRO,
  } = options;
  const effectiveOutro = durationSeconds === 10 ? "" : outro;

  const { provider, script: generated } = await generateScript({
    idea: {
      titulo: idea.titulo,
      hook: idea.hook,
      angulo: idea.angulo,
      tipo: idea.tipo,
      publicoDor: idea.publicoDor,
      cta: idea.cta,
      familia: idea.familia,
      observacaoCompliance: idea.observacaoCompliance,
      prioridade: idea.prioridade,
      linkOrigem: idea.linkOrigem,
    },
    articleAnalysis,
    editorialTone,
    durationSeconds,
    outro: effectiveOutro,
    requireClaude: true,
  });

  // A geracao e validada antes de qualquer escrita. Em uma repeticao com o
  // mesmo payload, o backend devolve o cache e nao consome novos tokens.
  const persistedIdea = options.persistIdea ? await appendIdea(idea) : idea;

  const script: Script = {
    id: stableWorkflowId(
      "s",
      persistedIdea.id,
      persistedIdea.titulo,
      persistedIdea.hook,
      persistedIdea.angulo,
      editorialTone,
      durationSeconds,
      effectiveOutro,
    ),
    ideaId: persistedIdea.id,
    categoria: persistedIdea.familia,
    tema: persistedIdea.titulo,
    titulo: generated.titulo || persistedIdea.titulo,
    hook: generated.hook,
    dorConflito: generated.dorConflito,
    explicacaoSimples: generated.explicacaoSimples,
    virada: generated.virada,
    cta: generated.cta,
    cuidadosMedicos: generated.cuidadosMedicos,
    risco: riskForIdea(persistedIdea),
    prioridade: persistedIdea.prioridade,
    formatoSugerido: persistedIdea.tipo || "Reel educativo",
    status: "aguardando_validacao",
    criadoEm: new Date().toISOString(),
    link: persistedIdea.linkOrigem || undefined,
    editorialTone,
    textoFalado: generated.textoFalado,
    outroText: effectiveOutro,
    generationProvider: provider,
    generationFlowVersion: SCRIPT_FLOW_VERSION,
  };

  const savedScript = await appendScript(script);
  return { idea: persistedIdea, script: savedScript, provider };
}
