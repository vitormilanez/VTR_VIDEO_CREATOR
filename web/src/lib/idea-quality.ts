import type { Idea } from "./mock-data";

export interface IdeaQuality {
  score: number;
  ready: boolean;
  issues: string[];
}

const GENERIC_TITLES = /^(ideia contextualizada|ideia a partir de|entenda sem culpa|novo tema)$/i;

/** Verifica se a ideia tem material suficiente para o avatar explicar o tema. */
export function evaluateIdeaQuality(idea: Idea): IdeaQuality {
  let score = 100;
  const issues: string[] = [];
  const title = idea.titulo.trim();
  const hook = idea.hook.trim();
  const angle = idea.angulo.trim();
  const audience = (idea.publicoDor || "").trim();
  const compliance = (idea.observacaoCompliance || "").trim();

  if (title.length < 12 || GENERIC_TITLES.test(title)) {
    score -= 20;
    issues.push("Título ainda genérico.");
  }
  if (hook.length < 35 || /hook educativo sugerido|revise antes/i.test(hook)) {
    score -= 25;
    issues.push("Hook precisa apresentar uma pergunta, tensão ou descoberta clara.");
  }
  if (angle.length < 100 || /contextualizar o tema|explicar o tema/i.test(angle)) {
    score -= 25;
    issues.push("Ângulo precisa explicar tese, contexto e virada para o avatar.");
  }
  if (audience.length < 20) {
    score -= 15;
    issues.push("Defina para quem a ideia fala e qual dor resolve.");
  }
  if (compliance.length < 20) {
    score -= 15;
    issues.push("Inclua o limite clínico ou editorial.");
  }

  return { score: Math.max(0, score), ready: score >= 70, issues };
}
