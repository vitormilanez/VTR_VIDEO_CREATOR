import type { Idea, Trend } from "./mock-data";

export function buildIdeaFromTrend(
  trend: Trend,
  id: string,
  createdAt = new Date().toISOString(),
): Idea {
  const headline = cleanHeadline(trend.sinal || trend.subtema || trend.titulo);
  const theme = cleanTheme(trend.titulo, headline);
  const medication = trend.familia === "medicamento" || hasMedicationTerms(theme, headline);

  return {
    id,
    trendId: trend.id,
    titulo: buildTitle(theme, headline, medication),
    familia: trend.familia,
    hook: buildHook(theme, headline, medication),
    angulo: buildAngle(theme, headline, medication),
    tipo: medication ? "Reel educativo com contexto" : "Reel educativo",
    publicoDor: trend.dorPublico || buildAudiencePain(theme, medication),
    cta: medication
      ? "Salve para lembrar: medicamento exige avaliação individual, não decisão por vídeo."
      : "Salve para rever quando aparecer uma explicação simplista sobre esse tema.",
    observacaoCompliance: medication
      ? "Não prescrever, não citar dose, não prometer resultado e reforçar avaliação individual."
      : "Evitar promessa de resultado, diagnóstico direto e sensacionalismo.",
    prioridade: trend.prioridade,
    status: "novo",
    criadoEm: createdAt,
  };
}

function cleanHeadline(value: string): string {
  return value
    .replace(/\s+-\s+[^-]{2,80}$/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function cleanTheme(title: string, headline: string): string {
  const cleaned = title.replace(/\s+/g, " ").trim();
  if (cleaned.length > 4 && !/^glp-?1$/i.test(cleaned)) return cleaned;
  return headline.match(/\b(GLP-?1|Ozempic|Mounjaro|Wegovy|Rybelsus)\b/i)?.[0] || cleaned;
}

function hasMedicationTerms(...values: string[]): boolean {
  return /glp|ozempic|mounjaro|wegovy|rybelsus|semaglutida|tirzepatida/i.test(values.join(" "));
}

function buildTitle(theme: string, headline: string, medication: boolean): string {
  if (medication) {
    if (/reembolso|eleg[ií]vel|plano|cobertura/i.test(headline)) {
      return `${theme}: quem pode ter acesso sem cair em promessa`;
    }
    if (/diretriz|seguran[cç]a|indica/i.test(headline)) {
      return `${theme}: o que muda na conversa sobre segurança`;
    }
    if (/online|vendido|teste|farm[aá]cia/i.test(headline)) {
      return `${theme}: compra online exige cuidado médico`;
    }
    if (/longevidade/i.test(headline)) {
      return `${theme}: remédio para emagrecer não é atalho de longevidade`;
    }
    return `${theme}: o ponto que o vídeo curto não pode simplificar`;
  }
  if (/sono/i.test(headline)) return "Sono ruim também pesa na fome do dia seguinte";
  if (/compuls/i.test(headline)) return "Compulsão alimentar não se resolve com bronca";
  if (/metabolismo|metabolism/i.test(headline))
    return "Metabolismo lento virou explicação fácil demais";
  return `${theme}: uma explicação simples, sem culpa`;
}

function buildHook(theme: string, headline: string, medication: boolean): string {
  if (medication) {
    if (/reembolso|eleg[ií]vel|plano|cobertura/i.test(headline)) {
      return `Viu notícia sobre ${theme} e cobertura do plano? Antes de transformar isso em expectativa, existe uma parte que precisa de contexto.`;
    }
    if (/online|vendido|teste|farm[aá]cia/i.test(headline)) {
      return `${theme} vendido online pode parecer praticidade, mas medicamento não deveria começar pelo clique.`;
    }
    return `${theme} aparece como solução simples nas notícias, mas a indicação correta depende de avaliação individual.`;
  }
  return `Quando todo mundo fala sobre ${theme}, a pergunta é: o que dá para explicar sem simplificar demais?`;
}

function buildAngle(theme: string, headline: string, medication: boolean): string {
  if (medication) {
    return [
      `Usar a notícia "${headline}" como gancho educativo.`,
      `Explicar que ${theme} exige avaliação clínica, histórico, riscos e acompanhamento.`,
      "Não citar doses, não indicar uso e não prometer resultado.",
    ].join(" ");
  }
  return [
    `Usar a tendência "${headline}" como gancho.`,
    "Traduzir o tema para a rotina do público, sem culpabilizar e sem promessa de resultado.",
  ].join(" ");
}

function buildAudiencePain(theme: string, medication: boolean): string {
  return medication
    ? `Pessoa confusa com notícias sobre ${theme}, indicação, segurança e acesso.`
    : `Pessoa buscando uma explicação prática sobre ${theme}, sem julgamento.`;
}
