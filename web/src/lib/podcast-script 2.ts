import type { PodcastSpeakerId } from "@/lib/api/local";

export type ImportedPodcastTurn = {
  speakerId: PodcastSpeakerId;
  text: string;
};

const SPEAKER_LABELS: Record<string, PodcastSpeakerId> = {
  HOST: "a",
  APRESENTADOR: "a",
  GUEST: "b",
  CONVIDADO: "b",
  ESPECIALISTA: "b",
};

function normalizeLabel(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toUpperCase();
}

export function parsePodcastScript(input: string): ImportedPodcastTurn[] {
  const lines = input.replace(/\r\n?/g, "\n").split("\n");
  const turns: ImportedPodcastTurn[] = [];
  let current: ImportedPodcastTurn | null = null;

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) continue;
    const tagged = line.match(/^([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ ]{1,29})\s*:\s*(.*)$/);
    if (tagged) {
      const label = normalizeLabel(tagged[1]);
      const speakerId = SPEAKER_LABELS[label];
      if (!speakerId) {
        throw new Error(`Rótulo “${tagged[1].trim()}” não reconhecido. Use HOST: e GUEST:.`);
      }
      current = { speakerId, text: tagged[2].trim() };
      turns.push(current);
      continue;
    }
    if (!current) {
      throw new Error("Comece cada fala com HOST: ou GUEST:.");
    }
    current.text = `${current.text} ${line}`.trim();
  }

  if (turns.length < 2) throw new Error("Cole pelo menos uma fala de HOST e uma de GUEST.");
  if (turns.length > 30) throw new Error("O podcast aceita no máximo 30 falas.");
  if (turns.some((turn) => !turn.text))
    throw new Error("Existe um rótulo sem texto depois dos dois-pontos.");
  const speakers = new Set(turns.map((turn) => turn.speakerId));
  if (!speakers.has("a") || !speakers.has("b")) {
    throw new Error("O roteiro precisa conter falas de HOST e GUEST.");
  }
  return turns;
}
