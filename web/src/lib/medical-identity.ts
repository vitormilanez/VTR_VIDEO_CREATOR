import profileData from "../../../shared/medical_editorial_profile.json";

export const MEDICAL_EDITORIAL_PROFILE = profileData;
export const MEDICAL_PROFESSIONAL_IDENTIFICATION = profileData.professional.identification;
export const MEDICAL_EDUCATIONAL_DISCLAIMER = profileData.publication.disclaimer;
export const MEDICAL_PUBLICATION_NOTICE = `${MEDICAL_EDUCATIONAL_DISCLAIMER}\n${MEDICAL_PROFESSIONAL_IDENTIFICATION}`;
export const MEDICAL_DEFAULT_SAFE_CTA = profileData.editorial.defaultSafeCta;
export const MEDICAL_MINIMUM_END_CARD_SECONDS = profileData.publication.minimumEndCardSeconds;

const prohibitedCtaPatterns = profileData.editorial.prohibitedCtaPatterns.map(
  (pattern) => new RegExp(pattern, "i"),
);

const legacyPublicationNotices = [
  "Conteúdo educativo. Não substitui avaliação médica individual.",
  "Conteudo educativo. Nao substitui avaliacao medica individual.",
  "Conteúdo educativo. Não substitui avaliação médica.",
  "Conteudo educativo. Nao substitui avaliacao medica.",
];

function normalized(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLocaleLowerCase("pt-BR");
}

export function hasMedicalProfessionalIdentification(value: string): boolean {
  return normalized(value).includes(normalized(MEDICAL_PROFESSIONAL_IDENTIFICATION));
}

export function hasMedicalPublicationNotice(value: string): boolean {
  return normalized(value).includes(normalized(MEDICAL_PUBLICATION_NOTICE));
}

export function hasProhibitedEditorialCta(value: string): boolean {
  return prohibitedCtaPatterns.some((pattern) => pattern.test(value));
}

export function safeEditorialCta(
  value: string | null | undefined,
  fallback = MEDICAL_DEFAULT_SAFE_CTA,
): string {
  const clean = value?.replace(/\s+/g, " ").trim() ?? "";
  return !clean || hasProhibitedEditorialCta(clean) ? fallback : clean;
}

export function stripProhibitedEditorialCtas(value: string): string {
  return value
    .replace(/\r\n?/g, "\n")
    .trim()
    .split(/\n{2,}/)
    .map((block) =>
      block
        .split("\n")
        .map((line) =>
          line
            .trim()
            .split(/(?<=[.!?])\s+/)
            .filter((sentence) => sentence && !hasProhibitedEditorialCta(sentence))
            .join(" "),
        )
        .filter(Boolean)
        .join("\n"),
    )
    .filter(Boolean)
    .join("\n\n")
    .trim();
}

/**
 * Separadores que sobram quando o aviso e removido do meio da copy.
 *
 * Uma legenda escrita como "... individual. | Dr. Guilherme ..." voltava do
 * saneamento terminando em "| ", e esse resto aparecia literalmente na legenda
 * copiada para publicacao.
 */
const orphanSeparators = "|\u2013\u2014\u00b7\u2022";

function dropOrphanSeparators(value: string): string {
  return value
    .split("\n")
    .map((line) =>
      line
        .replace(new RegExp(`^[\\s${orphanSeparators}]+`), "")
        .replace(new RegExp(`[\\s${orphanSeparators}]+$`), "")
        .trimEnd(),
    )
    .join("\n");
}

function withoutExistingPublicationNotice(value: string): string {
  let clean = value.replace(/\r\n?/g, "\n").trim();
  for (const notice of [
    MEDICAL_PUBLICATION_NOTICE,
    MEDICAL_EDUCATIONAL_DISCLAIMER,
    MEDICAL_PROFESSIONAL_IDENTIFICATION,
    ...legacyPublicationNotices,
  ]) {
    clean = clean.replace(new RegExp(notice.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"), "");
  }
  return stripProhibitedEditorialCtas(dropOrphanSeparators(clean))
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function ensureMedicalPublicationNotice(value: string, maximum?: number): string {
  const clean = stripProhibitedEditorialCtas(value)
    .replace(/\r\n?/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  if (hasMedicalPublicationNotice(clean)) {
    // O aviso ja esta presente, mas a copy pode ter sido escrita com o
    // separador colado nele. Limpa apenas o trecho antes do aviso.
    const cut = clean.indexOf(MEDICAL_EDUCATIONAL_DISCLAIMER);
    if (cut > 0) {
      const head = dropOrphanSeparators(clean.slice(0, cut)).trimEnd();
      return `${head}\n\n${clean.slice(cut)}`.replace(/\n{3,}/g, "\n\n").trim();
    }
    return clean;
  }

  const body = withoutExistingPublicationNotice(clean);
  const content =
    maximum === undefined
      ? body
      : body.slice(0, Math.max(0, maximum - 2 - MEDICAL_PUBLICATION_NOTICE.length)).trimEnd();
  return `${content}${content ? "\n\n" : ""}${MEDICAL_PUBLICATION_NOTICE}`;
}

export function ensureMedicalProfessionalIdentification(value: string, maximum?: number): string {
  return ensureMedicalPublicationNotice(value, maximum);
}

export function formatPublicationCaption(
  body: string,
  hashtags: readonly string[] | string = [],
  maximum = 2200,
): string {
  const rawTags: readonly string[] =
    typeof hashtags === "string" ? hashtags.split(/\s+/) : hashtags;
  const tags = rawTags
    .map((tag) => tag.trim())
    .filter(Boolean)
    .map((tag) => (tag.startsWith("#") ? tag : `#${tag}`));
  const tagBlock = tags.join(" ");
  if (tags.some((tag) => body.includes(tag))) {
    return ensureMedicalProfessionalIdentification(body, maximum);
  }

  const availableForBody = maximum - (tagBlock ? tagBlock.length + 2 : 0);
  const caption = ensureMedicalProfessionalIdentification(body, availableForBody);
  return tagBlock ? `${caption}\n\n${tagBlock}` : caption;
}
