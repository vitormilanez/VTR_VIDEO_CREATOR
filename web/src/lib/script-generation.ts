// Fluxo unico de geracao de roteiro com IA: o usuario escolhe o tom editorial
// ANTES da chamada paga, entao geramos o texto falado uma unica vez (nunca
// tres vezes por ideia, o que triplicaria o custo).
import { appendIdea, appendScript, generateScript, type ArticleAnalysis } from "@/lib/api/local";
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
    outro,
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
    outroText: outro,
  };

  const savedScript = await appendScript(script);
  return { idea: persistedIdea, script: savedScript, provider };
}
