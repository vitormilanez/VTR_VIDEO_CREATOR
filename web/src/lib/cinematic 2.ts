import type { Script } from "./mock-data";

export type CinematicSupportingImages = "auto" | "avatar_only";
export type CinematicVisualStyle = "editorial" | "documentary" | "clean";
export type CinematicPresenterMode = "anchor" | "always" | "intro_outro";
export type CinematicMediaType = "motion_graphics" | "stock_media" | "ai_generated";

export const CINEMATIC_DIRECTION_MAX_LENGTH = 2000;

const VISUAL_STYLE_DIRECTIONS: Record<CinematicVisualStyle, string> = {
  editorial:
    "Use a contemporary editorial look: polished, sober, premium composition, smooth cuts, and restrained motion.",
  documentary:
    "Use a human, realistic documentary look with natural imagery, subtle movement, and authentic environments.",
  clean:
    "Use a clean, minimalist look with an organized background, few elements, and clear focus on the presenter.",
};

const PRESENTER_DIRECTIONS: Record<CinematicPresenterMode, string> = {
  anchor:
    "Use the selected presenter as the recurring on-camera anchor. Supporting visuals may temporarily take focus, but return to the presenter often and preserve continuity.",
  always:
    "Keep the selected presenter visible throughout. Supporting visuals may appear only as overlays, side panels, or picture-in-picture without replacing the presenter.",
  intro_outro:
    "Show the selected presenter on camera for the opening and closing. Use approved supporting visuals through the middle, with a clear visual return to the presenter at the end.",
};

const MEDIA_DIRECTIONS: Record<CinematicMediaType, string> = {
  motion_graphics:
    "Use Motion Graphics for data, simple diagrams, keywords, and visual explanations; keep them concise and legible on mobile.",
  stock_media:
    "Use Stock Media for real environments, people, actions, and emotional context; every shot must directly support the narration.",
  ai_generated:
    "Use AI-Generated visuals only for custom or abstract concepts that Stock Media cannot represent clearly; avoid uncanny or misleading imagery.",
};

export function cinematicProjectTitle(speech: string): string {
  const normalized = speech.replace(/\s+/gu, " ").trim();
  if (!normalized) return "Novo vídeo Cinematic";
  const firstSentence = normalized.match(/^.+?(?=[.!?…](?:\s|$)|$)/u)?.[0] || normalized;
  const withoutEnding = firstSentence.replace(/[.!?…]+$/u, "").trim();
  if (withoutEnding.length <= 82) return withoutEnding;
  const shortened = withoutEnding
    .slice(0, 82)
    .replace(/\s+\S*$/u, "")
    .trim();
  return `${shortened || withoutEnding.slice(0, 82).trim()}…`;
}

export function buildCinematicScript({
  id,
  speech,
  createdAt,
}: {
  id: string;
  speech: string;
  createdAt: string;
}): Script {
  const reviewedSpeech = speech.trim();
  const title = cinematicProjectTitle(reviewedSpeech);
  return {
    id,
    categoria: "educativo",
    tema: title,
    titulo: title,
    // O backend ainda usa os blocos editoriais para reconhecer que o roteiro
    // possui conteúdo, mas textoFalado continua sendo a fonte canônica da voz.
    hook: title,
    dorConflito: "",
    explicacaoSimples: "",
    virada: "",
    cta: "",
    cuidadosMedicos: "Fala inserida e confirmada manualmente no fluxo Cinematic.",
    risco: "medio",
    prioridade: "media",
    formatoSugerido: "Cinematic",
    aprovador: "Gui via Cinematic",
    status: "aprovado_clinicamente",
    criadoEm: createdAt,
    validadoEm: createdAt,
    textoFalado: reviewedSpeech,
    outroText: "",
    generationProvider: "manual",
    generationFlowVersion: "cinematic-open-v1",
  };
}

export function buildCinematicDirection({
  durationSeconds,
  supportingImages,
  presenterMode,
  mediaTypes,
  visualStyle,
  requiredElements,
  excludedElements,
  criticalOnScreenText,
  notes,
}: {
  durationSeconds: number;
  supportingImages: CinematicSupportingImages;
  presenterMode: CinematicPresenterMode;
  mediaTypes: CinematicMediaType[];
  visualStyle: CinematicVisualStyle;
  requiredElements: string;
  excludedElements: string;
  criticalOnScreenText: string;
  notes: string;
}): string {
  const targetDuration = Math.max(1, Math.round(durationSeconds));
  const normalizedRequired = normalizeDirectionText(requiredElements);
  const normalizedExcluded = normalizeDirectionText(excludedElements);
  const normalizedNotes = normalizeDirectionText(notes);
  const literalText = criticalOnScreenText
    .split(/\r?\n/u)
    .map((line) => line.trim())
    .filter(Boolean)
    .join("\n");
  const approvedMediaTypes = Array.from(new Set(mediaTypes));

  const sections = [
    [
      "VIDEO BRIEF",
      `Create one single-topic portrait (9:16) video. Target duration: ${targetDuration} seconds.`,
      "The selected presenter explains the approved topic in Brazilian Portuguese. Preserve the central thesis, factual boundaries, tone, and CTA of the approved narration.",
    ].join("\n"),
    [
      "PRESENTER",
      supportingImages === "avatar_only"
        ? "Keep the selected presenter visible throughout. Do not use full-screen B-roll, Stock Media, or AI-generated visuals. Vary only framing, pacing, composition, and restrained on-screen overlays."
        : PRESENTER_DIRECTIONS[presenterMode],
    ].join("\n"),
    [
      "MEDIA DIRECTION",
      supportingImages === "avatar_only"
        ? "Presenter-only mode is required. Any graphic element must remain secondary and must not replace the presenter."
        : approvedMediaTypes.length
          ? approvedMediaTypes.map((mediaType) => MEDIA_DIRECTIONS[mediaType]).join("\n")
          : "No supporting media type was approved. Keep the selected presenter on camera and use only restrained framing changes.",
    ].join("\n"),
    [
      "REQUIRED VISUAL ELEMENTS",
      normalizedRequired ||
        "Choose only contextually relevant visual elements that clarify the narration; do not add unrelated decoration.",
    ].join("\n"),
  ];

  if (literalText) {
    sections.push(
      [
        "CRITICAL ON-SCREEN TEXT — DISPLAY LITERALLY",
        "Display the following text exactly as written. Do not translate, paraphrase, or correct it:",
        "<<<LITERAL_TEXT",
        literalText,
        "LITERAL_TEXT",
      ].join("\n"),
    );
  }

  sections.push(
    [
      "AVOID",
      normalizedExcluded || "Avoid irrelevant, sensational, stereotyped, or misleading imagery.",
    ].join("\n"),
    ["STYLE AND PACING", VISUAL_STYLE_DIRECTIONS[visualStyle], normalizedNotes]
      .filter(Boolean)
      .join("\n"),
    [
      "GUARDRAILS",
      "Do not invent data, medical claims, testimonials, brands, or unrelated spoken content. Keep captions readable, accurate, and synchronized with the narration.",
    ].join("\n"),
  );

  return sections.join("\n\n");
}

function normalizeDirectionText(value: string): string {
  return value.replace(/\s+/gu, " ").trim();
}
