// Fluxo unico de geracao de roteiro com IA: o usuario escolhe o tom editorial
// ANTES da chamada paga, entao geramos o texto falado uma unica vez (nunca
// tres vezes por ideia, o que triplicaria o custo).
import {
  appendIdea,
  appendScript,
  generateCaptureHooks,
  generateScript,
  type ArticleAnalysis,
} from "@/lib/api/local";
import { genId } from "@/lib/store";
import { DEFAULT_OUTRO } from "@/lib/script-quality";
import type { EditorialTone, Idea, Script } from "@/lib/mock-data";

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
  durationSeconds?: 10 | 15 | 30 | 45 | 60;
  outro?: string;
  /** true quando a ideia ainda nao foi salva no Sheets (sugestao de artigo/ideia manual). */
  persistIdea?: boolean;
}

export interface GenerateScriptResult {
  idea: Idea;
  script: Script;
  provider: "claude" | "fallback";
}

export async function generateAndPersistCaptureScripts(
  options: Pick<GenerateScriptOptions, "idea" | "persistIdea"> & {
    durationSeconds: 10 | 15;
  },
): Promise<{ idea: Idea; scripts: Script[]; provider: "claude" | "fallback" }> {
  const persistedIdea = options.persistIdea ? await appendIdea(options.idea) : options.idea;
  const result = await generateCaptureHooks({
    durationSeconds: options.durationSeconds,
    trendId: persistedIdea.trendId || persistedIdea.id,
    titulo: persistedIdea.titulo,
    subtema: persistedIdea.tipo,
    sinal: persistedIdea.angulo,
    dorPublico: persistedIdea.publicoDor,
    notas: persistedIdea.observacaoCompliance,
    familia: persistedIdea.familia,
    prioridade: persistedIdea.prioridade,
    sourceUrl: persistedIdea.linkOrigem || null,
  });
  const scripts: Script[] = [];
  for (const variant of result.variants) {
    const saved = await appendScript({
      id: genId("s"),
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
      editorialTone: "neutro",
      textoFalado: variant.spokenText,
      outroText: options.durationSeconds === 10 ? "" : DEFAULT_OUTRO,
    });
    scripts.push(saved);
  }
  return { idea: persistedIdea, scripts, provider: result.provider };
}

/**
 * Gera o roteiro + texto falado completo via IA (uma unica chamada paga) e
 * persiste ideia (se necessario) e roteiro no Sheets.
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
  });

  // A geracao e validada antes de qualquer escrita. Em uma repeticao com o
  // mesmo payload, o backend devolve o cache e nao consome novos tokens.
  const persistedIdea = options.persistIdea ? await appendIdea(idea) : idea;

  const script: Script = {
    id: genId("s"),
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
  };

  const savedScript = await appendScript(script);
  return { idea: persistedIdea, script: savedScript, provider };
}
