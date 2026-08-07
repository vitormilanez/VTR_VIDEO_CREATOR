import type { Idea, Script } from "./mock-data";

export function buildScriptFromIdea(
  idea: Idea,
  id: string,
  createdAt = new Date().toISOString(),
): Script {
  const theme = cleanTheme(idea.titulo);
  const medication = idea.familia === "medicamento" || hasMedicationTerms(theme);
  const fromArticle =
    /artigo|cient/i.test(idea.tipo || "") ||
    /estudo|artigo|coorte|observacional/i.test(idea.angulo);
  const audiencePain = cleanSentence(
    idea.publicoDor || "A pessoa quer uma resposta simples para um tema que depende de contexto.",
  );
  const angle = cleanAngle(idea.angulo);
  const hook = buildHook(idea, theme, medication);

  return {
    id,
    ideaId: idea.id,
    categoria: idea.familia,
    tema: theme,
    titulo: buildTitle(idea, theme, medication),
    hook,
    dorConflito: audiencePain,
    explicacaoSimples: buildExplanation(theme, angle, medication, fromArticle),
    virada: buildTurn(theme, medication, fromArticle),
    cta: buildCta(idea, medication),
    cuidadosMedicos: buildMedicalCautions(idea, medication),
    risco: medication ? "alto" : idea.familia === "comportamento" ? "alto" : "medio",
    prioridade: idea.prioridade,
    formatoSugerido: idea.tipo || "Reel educativo",
    status: "aguardando_validacao",
    criadoEm: createdAt,
    link: idea.linkOrigem || undefined,
  };
}

function cleanTheme(title: string): string {
  return (
    title
      .replace(/^Ideia a partir de:\s*/i, "")
      .replace(/^Roteiro:\s*/i, "")
      .trim() || title
  );
}

function cleanSentence(value: string): string {
  const cleaned = value.replace(/\s+/g, " ").trim();
  return cleaned.endsWith(".") || cleaned.endsWith("?") ? cleaned : `${cleaned}.`;
}

function cleanAngle(value: string): string {
  return value
    .replace(/^Angulo:\s*/i, "")
    .replace(/^Ângulo:\s*/i, "")
    .replace(/\s+/g, " ")
    .trim();
}

function hasMedicationTerms(value: string): boolean {
  return /glp|mounjaro|ozempic|wegovy|semaglutida|tirzepatida/i.test(value);
}

function buildTitle(idea: Idea, theme: string, medication: boolean): string {
  if (!/^Ideia a partir de:/i.test(idea.titulo) && idea.titulo.length > 8) return idea.titulo;
  return medication ? `${theme}: o que ninguém deve simplificar` : `${theme}: entenda sem culpa`;
}

function buildHook(idea: Idea, theme: string, medication: boolean): string {
  const hook = idea.hook.trim();
  if (hook && !/hook educativo sugerido|revise antes/i.test(hook)) return hook;
  if (medication) {
    return `${theme} não é atalho mágico. É um assunto médico que precisa de contexto.`;
  }
  return `Se todo mundo fala sobre ${theme}, por que quase ninguém explica do jeito certo?`;
}

function buildExplanation(
  theme: string,
  angle: string,
  medication: boolean,
  fromArticle: boolean,
): string {
  if (fromArticle) {
    return [
      angle ||
        "Explique o achado do artigo em linguagem simples, sem transformar associação em promessa.",
      "Traduza o estudo para o público: o que foi observado, em quem foi observado, qual número importa e qual limite precisa aparecer.",
      "A mensagem central deve ser: evidência promissora ajuda a fazer perguntas melhores, mas não substitui consulta, rastreio ou decisão individual.",
    ].join(" ");
  }
  if (medication) {
    return [
      `${theme} pode aparecer nas notícias como solução simples, mas tratamento não começa pelo nome do remédio.`,
      "Começa por avaliação clínica, histórico, riscos, objetivos e acompanhamento.",
      angle || "A ideia é traduzir a notícia sem transformar conteúdo em prescrição.",
    ].join(" ");
  }
  return [
    angle || `${theme} costuma ser explicado de forma rasa nas redes sociais.`,
    "O ponto é mostrar o mecanismo de forma simples, sem culpar a pessoa e sem prometer resultado.",
  ].join(" ");
}

function buildTurn(theme: string, medication: boolean, fromArticle: boolean): string {
  if (fromArticle) {
    return "A virada é simples: artigo bom não serve para vender certeza. Serve para explicar melhor o que ainda precisa ser confirmado.";
  }
  if (medication) {
    return `A pergunta não é “${theme} serve para todo mundo?”. A pergunta é “qual é o contexto de cada paciente?”.`;
  }
  return "Quando a explicação ignora rotina, saúde e contexto, ela vira conselho bonito e pouco útil.";
}

function buildCta(idea: Idea, medication: boolean): string {
  const cta = idea.cta.trim();
  if (cta && !/procure avaliacao individualizada/i.test(cta)) return cta;
  return medication
    ? "Salve para lembrar: medicamento exige avaliação individual, não decisão por vídeo."
    : "Salve para rever quando aparecer uma explicação simplista sobre esse tema.";
}

function buildMedicalCautions(idea: Idea, medication: boolean): string {
  const base = [
    idea.observacaoCompliance.trim(),
    medication
      ? "Não prescrever, não citar dose, não prometer resultado e reforçar avaliação individual."
      : "Evitar promessa de resultado, diagnóstico direto e culpabilização.",
  ]
    .filter(Boolean)
    .join(" ");
  return base || "Revisar linguagem antes de gravar.";
}
