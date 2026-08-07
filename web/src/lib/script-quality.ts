export const DEFAULT_OUTRO = "Me siga para mais dicas, e obrigado.";
const LEGACY_CAPTURE_OUTRO = "Veja o contexto no perfil.";

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

export function narrationQualityIssues(
  text: string,
  durationSeconds: number,
  outro = DEFAULT_OUTRO,
): string[] {
  const normalized = text.replace(/\s+/g, " ").trim();
  const issues: string[] = [];

  if (!normalized) return ["Texto falado esta vazio."];

  for (const pattern of PLACEHOLDER_PATTERNS) {
    if (pattern.regex.test(normalized)) issues.push(pattern.message);
  }

  const selectedOutro = durationSeconds === 10 ? "" : outro.replace(/\s+/g, " ").trim();
  if (selectedOutro) {
    const outroMatches = normalized.match(new RegExp(escapeRegExp(selectedOutro), "gi")) ?? [];
    if (outroMatches.length !== 1) {
      issues.push("A frase final deve aparecer exatamente uma vez.");
    } else if (!normalized.toLowerCase().endsWith(selectedOutro.toLowerCase())) {
      issues.push("A frase final precisa ser a última frase.");
    }
  }

  const wordCount = normalized.split(/\s+/).filter(Boolean).length;
  const minimumWords = minimumWordsForDuration(durationSeconds);
  if (wordCount < minimumWords) {
    issues.push(`Texto muito curto para ${durationSeconds}s. Ajuste ou escolha uma duracao menor.`);
  }
  const maximumWords = maximumWordsForDuration(durationSeconds);
  if (wordCount > maximumWords) {
    issues.push(
      `Texto muito longo para ${durationSeconds}s (${wordCount} palavras). Encurte para no máximo ${maximumWords}.`,
    );
  }

  return Array.from(new Set(issues));
}

/** Remove o encerramento selecionado e recoloca uma única vez no fim. */
export function normalizeNarrationOutro(text: string, outro = DEFAULT_OUTRO): string {
  const selectedOutro = outro.replace(/\s+/g, " ").trim();
  if (!selectedOutro) return removeNarrationOutro(text);
  const withoutOutro = text
    .replace(new RegExp(`\\s*${escapeRegExp(DEFAULT_OUTRO)}\\s*`, "gi"), " ")
    .replace(new RegExp(`\\s*${escapeRegExp(selectedOutro)}\\s*`, "gi"), " ")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
    .replace(/[.!?…]+$/, "");

  return withoutOutro ? `${withoutOutro}.\n\n${selectedOutro}` : selectedOutro;
}

/** Remove encerramentos conhecidos ou o encerramento atualmente selecionado. */
export function removeNarrationOutro(text: string, outro = ""): string {
  const candidates = [outro, DEFAULT_OUTRO, LEGACY_CAPTURE_OUTRO]
    .map((candidate) => candidate.replace(/\s+/g, " ").trim())
    .filter(Boolean);
  let body = text;
  for (const candidate of candidates) {
    body = body.replace(new RegExp(`\\s*${escapeRegExp(candidate)}\\s*`, "gi"), " ");
  }
  return body
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
    .replace(/\s+([.!?…])/g, "$1");
}

export function minimumWordsForDuration(durationSeconds: number): number {
  if (durationSeconds <= 10) return 18;
  if (durationSeconds <= 15) return 25;
  if (durationSeconds <= 30) return 55;
  if (durationSeconds <= 45) return 85;
  return 115;
}

export function maximumWordsForDuration(durationSeconds: number): number {
  if (durationSeconds <= 10) return 24;
  if (durationSeconds <= 15) return 36;
  if (durationSeconds <= 30) return 72;
  if (durationSeconds <= 45) return 108;
  return 144;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
