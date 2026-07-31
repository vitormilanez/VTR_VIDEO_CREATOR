export const MANDATORY_OUTRO = "Me siga para mais dicas, e obrigado.";

const PLACEHOLDER_PATTERNS: Array<{ regex: RegExp; message: string }> = [
  {
    regex: /hook educativo sugerido|revise antes de aprovar/i,
    message: "Hook ainda parece sugestao automatica.",
  },
  {
    regex: /\brascunho\b/i,
    message: "Texto ainda contem marcacao de rascunho.",
  },
  {
    regex: /angulo:\s*angulo|ângulo:\s*ângulo/i,
    message: "Angulo duplicado ou com label tecnico.",
  },
  {
    regex: /explicar o tema sem prescrever|virada educativa reforcando/i,
    message: "Trecho ainda esta escrito como instrucao interna.",
  },
];

export function narrationQualityIssues(text: string, durationSeconds: number): string[] {
  const normalized = text.replace(/\s+/g, " ").trim();
  const issues: string[] = [];

  if (!normalized) return ["Texto falado esta vazio."];

  for (const pattern of PLACEHOLDER_PATTERNS) {
    if (pattern.regex.test(normalized)) issues.push(pattern.message);
  }

  const outroMatches =
    normalized.match(new RegExp(escapeRegExp(MANDATORY_OUTRO), "gi")) ?? [];
  if (outroMatches.length !== 1) {
    issues.push("Encerramento padrao deve aparecer exatamente uma vez.");
  } else if (!normalized.toLowerCase().endsWith(MANDATORY_OUTRO.toLowerCase())) {
    issues.push("Encerramento padrao precisa ser a ultima frase.");
  }

  const wordCount = normalized.split(/\s+/).filter(Boolean).length;
  const minimumWords = minWordsForDuration(durationSeconds);
  if (wordCount < minimumWords) {
    issues.push(`Texto muito curto para ${durationSeconds}s. Ajuste ou escolha uma duracao menor.`);
  }

  return Array.from(new Set(issues));
}

/** Remove versões antigas do CTA e recoloca o encerramento obrigatório uma única vez no fim. */
export function normalizeNarrationOutro(text: string): string {
  const withoutOutro = text
    .replace(new RegExp(`\\s*${escapeRegExp(MANDATORY_OUTRO)}\\s*`, "gi"), " ")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
    .replace(/[.!?…]+$/, "");

  return withoutOutro ? `${withoutOutro}.\n\n${MANDATORY_OUTRO}` : MANDATORY_OUTRO;
}

function minWordsForDuration(durationSeconds: number): number {
  if (durationSeconds <= 15) return 18;
  if (durationSeconds <= 30) return 35;
  if (durationSeconds <= 45) return 50;
  return 65;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
