import type { AvatarSetRole, VideoVisualLayout, VideoVisualType } from "@/lib/api/local";

export const AVATAR_SET_ROLE_OPTIONS: Array<{ value: AvatarSetRole; label: string }> = [
  { value: "primary", label: "Principal" },
  { value: "front", label: "Frontal" },
  { value: "close", label: "Close" },
  { value: "three_quarter", label: "3/4" },
  { value: "standing", label: "Em pé" },
  { value: "seated", label: "Sentado" },
  { value: "wide", label: "Aberto" },
];

export function avatarSetRoleLabel(role: AvatarSetRole) {
  return AVATAR_SET_ROLE_OPTIONS.find((option) => option.value === role)?.label || role;
}

export const VIDEO_VISUAL_TYPE_OPTIONS: Array<{ value: VideoVisualType; label: string }> = [
  { value: "none", label: "Nenhum visual" },
  { value: "full_slide", label: "Slide completo" },
  { value: "overlay", label: "Overlay" },
  { value: "statistic", label: "Estatística" },
  { value: "comparison", label: "Comparação" },
  { value: "quote", label: "Citação" },
];

export const VIDEO_VISUAL_LAYOUT_OPTIONS: Array<{ value: VideoVisualLayout; label: string }> = [
  { value: "hero_photo", label: "Hero com foto" },
  { value: "photo_split", label: "Foto dividida" },
  { value: "big_statement", label: "Big statement" },
  { value: "question", label: "Pergunta" },
  { value: "myth_fact", label: "Mito e fato" },
  { value: "number_stat", label: "Número" },
  { value: "three_points", label: "Três pontos" },
  { value: "explainer", label: "Explicador" },
  { value: "doctor_quote", label: "Citação médica" },
  { value: "photo_overlay", label: "Foto com overlay" },
  { value: "do_dont", label: "Faça / não faça" },
  { value: "cta_photo", label: "Encerramento com foto" },
];
