import type {
  LocalVideoKitClaudeModelId,
  LocalVideoKitConfig,
  VisualTimelineEvent,
} from "@/lib/api/local";

const OVERLAP_TOLERANCE_SECONDS = 0.12;
const MIN_AUTOMATIC_VISUAL_SECONDS = 1.5;
const MAX_AUTOMATIC_VISUAL_SECONDS = 5.5;

export const MANUAL_VISUAL_TIMING: Record<
  LocalVideoKitClaudeModelId,
  { label: string; startRatio: number; durationSeconds: number }
> = {
  numberGlass: { label: "Número em Vidro", startRatio: 0.16, durationSeconds: 3.8 },
  editorialClip: { label: "Recorte Editorial", startRatio: 0.22, durationSeconds: 4.2 },
  mechanismBars: { label: "Barras de Mecanismo", startRatio: 0.34, durationSeconds: 3.6 },
  evidenceStamp: { label: "Selo de Evidência", startRatio: 0.48, durationSeconds: 4.4 },
  glossarySource: { label: "Glossário + Fonte", startRatio: 0.12, durationSeconds: 4.2 },
};

interface VisualInterval {
  id: string;
  label: string;
  startSeconds: number;
  endSeconds: number;
  automatic: boolean;
}

export interface VisualTimingValidation {
  issues: string[];
  issuesByItemId: Record<string, string[]>;
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, Number.isFinite(value) ? value : minimum));
}

function readableSeconds(value: number) {
  return `${value.toFixed(2).replace(/0+$/, "").replace(/\.$/, "")}s`;
}

function addIssue(result: VisualTimingValidation, message: string, itemIds: string[]) {
  if (!result.issues.includes(message)) result.issues.push(message);
  itemIds.forEach((id) => {
    const current = result.issuesByItemId[id] || [];
    if (!current.includes(message)) result.issuesByItemId[id] = [...current, message];
  });
}

function resolveIntervals(
  events: VisualTimelineEvent[],
  config: LocalVideoKitConfig,
  durationSeconds: number,
): VisualInterval[] {
  const intervals: VisualInterval[] = events
    .filter((event) => event.enabled)
    .map((event) => ({
      id: `event:${event.id}`,
      label: event.visualText || `Visual ${event.interactionType}`,
      startSeconds: event.startMs / 1000,
      endSeconds: event.endMs / 1000,
      automatic: true,
    }));

  if (config.includeSection && config.sectionTitle.trim()) {
    const start = clamp(
      config.sectionStartSeconds ?? durationSeconds * 0.52,
      3,
      Math.max(3, durationSeconds - 0.5),
    );
    const visibleFor = Math.min(
      Math.max(0.5, config.sectionDurationSeconds ?? 3),
      Math.max(0.5, durationSeconds - start),
    );
    intervals.push({
      id: "manual:section",
      label: config.sectionTitle || "Cartela de tópico",
      startSeconds: start,
      endSeconds: start + visibleFor,
      automatic: false,
    });
  }

  if (config.manualVisualsEnabled && config.fiveStack?.enabled) {
    const start = clamp(
      config.fiveStack.startSeconds ?? durationSeconds * 0.28,
      0.5,
      Math.max(0.5, durationSeconds - 0.5),
    );
    const visibleFor = Math.min(
      Math.max(1, config.fiveStack.durationSeconds ?? 4.5),
      Math.max(0.5, durationSeconds - start),
    );
    intervals.push({
      id: "manual:five-stack",
      label: "Lista em 5 pontos",
      startSeconds: start,
      endSeconds: start + visibleFor,
      automatic: false,
    });
  }

  if (!config.manualVisualsEnabled) return intervals;

  Object.entries(MANUAL_VISUAL_TIMING).forEach(([rawId, defaults]) => {
    const id = rawId as LocalVideoKitClaudeModelId;
    const model = config.claudeInserts?.[id];
    if (!model?.enabled) return;
    const start = clamp(
      model.startSeconds ?? durationSeconds * defaults.startRatio,
      0.5,
      Math.max(0.5, durationSeconds - 0.5),
    );
    const visibleFor = Math.min(
      Math.max(1, Math.min(8, model.durationSeconds ?? defaults.durationSeconds)),
      Math.max(0.5, durationSeconds - start),
    );
    intervals.push({
      id: `manual:${id}`,
      label: model.fields[0]?.trim() || defaults.label,
      startSeconds: start,
      endSeconds: start + visibleFor,
      automatic: false,
    });
  });

  return intervals;
}

export function validateLocalVideoVisualTiming(
  events: VisualTimelineEvent[],
  config: LocalVideoKitConfig,
  durationSeconds: number,
): VisualTimingValidation {
  const result: VisualTimingValidation = { issues: [], issuesByItemId: {} };
  const safeDuration = Math.max(0, durationSeconds || 0);
  const intervals = resolveIntervals(events, config, safeDuration);

  intervals.forEach((interval) => {
    if (!interval.automatic) return;
    const visibleFor = interval.endSeconds - interval.startSeconds;
    if (visibleFor < MIN_AUTOMATIC_VISUAL_SECONDS || visibleFor > MAX_AUTOMATIC_VISUAL_SECONDS) {
      addIssue(result, `“${interval.label}” precisa durar entre 1,5 e 5,5 segundos.`, [
        interval.id,
      ]);
    }
    if (
      interval.startSeconds < 0 ||
      interval.endSeconds <= interval.startSeconds ||
      (safeDuration > 0 && interval.endSeconds > safeDuration + 0.25)
    ) {
      addIssue(result, `“${interval.label}” precisa ficar dentro da duração do vídeo.`, [
        interval.id,
      ]);
    }
  });

  intervals.forEach((current, index) => {
    intervals.slice(index + 1).forEach((candidate) => {
      const overlaps =
        current.startSeconds < candidate.endSeconds - OVERLAP_TOLERANCE_SECONDS &&
        current.endSeconds > candidate.startSeconds + OVERLAP_TOLERANCE_SECONDS;
      if (!overlaps) return;
      addIssue(
        result,
        `“${current.label}” (${readableSeconds(current.startSeconds)}–${readableSeconds(current.endSeconds)}) se sobrepõe a “${candidate.label}” (${readableSeconds(candidate.startSeconds)}–${readableSeconds(candidate.endSeconds)}).`,
        [current.id, candidate.id],
      );
    });
  });

  return result;
}
