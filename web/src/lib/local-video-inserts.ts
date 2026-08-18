import type { LocalVideoKitInsert, LocalVideoKitInsertAsset } from "@/lib/api/local";

const MIN_INSERT_SECONDS = 0.25;
const TIME_TOLERANCE = 0.12;

function clampTime(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, Number.isFinite(value) ? value : minimum));
}

export function roundInsertTime(value: number) {
  return Math.round(value * 1000) / 1000;
}

export function createInsertFromAsset(
  asset: LocalVideoKitInsertAsset,
  id: string,
  timelineStartSeconds = 3,
): LocalVideoKitInsert {
  const duration = Math.min(3, asset.durationSeconds);
  return {
    id,
    uploadId: asset.uploadId,
    sourceName: asset.filename,
    sourceDurationSeconds: asset.durationSeconds,
    timelineStartSeconds: roundInsertTime(Math.max(0, timelineStartSeconds)),
    timelineEndSeconds: roundInsertTime(Math.max(0, timelineStartSeconds) + duration),
    sourceStartSeconds: 0,
    sourceEndSeconds: roundInsertTime(duration),
  };
}

export type InsertTimeField =
  "timelineStartSeconds" | "timelineEndSeconds" | "sourceStartSeconds" | "sourceEndSeconds";

export function updateInsertTime(
  insert: LocalVideoKitInsert,
  field: InsertTimeField,
  rawValue: number,
): LocalVideoKitInsert {
  const sourceDuration = Math.max(MIN_INSERT_SECONDS, insert.sourceDurationSeconds);
  const currentDuration = Math.max(
    MIN_INSERT_SECONDS,
    insert.sourceEndSeconds - insert.sourceStartSeconds,
  );
  if (field === "timelineStartSeconds") {
    const start = Math.max(0, rawValue || 0);
    return {
      ...insert,
      timelineStartSeconds: roundInsertTime(start),
      timelineEndSeconds: roundInsertTime(start + currentDuration),
    };
  }
  if (field === "timelineEndSeconds") {
    const requestedDuration = Math.max(
      MIN_INSERT_SECONDS,
      (rawValue || 0) - insert.timelineStartSeconds,
    );
    const availableDuration = Math.max(
      MIN_INSERT_SECONDS,
      sourceDuration - insert.sourceStartSeconds,
    );
    const duration = Math.min(requestedDuration, availableDuration);
    return {
      ...insert,
      timelineEndSeconds: roundInsertTime(insert.timelineStartSeconds + duration),
      sourceEndSeconds: roundInsertTime(insert.sourceStartSeconds + duration),
    };
  }
  if (field === "sourceStartSeconds") {
    const sourceStart = clampTime(
      rawValue || 0,
      0,
      Math.max(0, sourceDuration - MIN_INSERT_SECONDS),
    );
    const duration = Math.min(currentDuration, sourceDuration - sourceStart);
    return {
      ...insert,
      sourceStartSeconds: roundInsertTime(sourceStart),
      sourceEndSeconds: roundInsertTime(sourceStart + duration),
      timelineEndSeconds: roundInsertTime(insert.timelineStartSeconds + duration),
    };
  }
  const sourceEnd = clampTime(
    rawValue || 0,
    insert.sourceStartSeconds + MIN_INSERT_SECONDS,
    sourceDuration,
  );
  const duration = sourceEnd - insert.sourceStartSeconds;
  return {
    ...insert,
    sourceEndSeconds: roundInsertTime(sourceEnd),
    timelineEndSeconds: roundInsertTime(insert.timelineStartSeconds + duration),
  };
}

export function createNextUnusedInsert(
  current: LocalVideoKitInsert,
  inserts: LocalVideoKitInsert[],
  id: string,
): LocalVideoKitInsert | null {
  const sameAsset = inserts.filter((insert) => insert.uploadId === current.uploadId);
  const nextSourceStart = Math.max(...sameAsset.map((insert) => insert.sourceEndSeconds));
  const remaining = current.sourceDurationSeconds - nextSourceStart;
  if (remaining < MIN_INSERT_SECONDS) return null;
  const currentDuration = Math.max(
    MIN_INSERT_SECONDS,
    current.sourceEndSeconds - current.sourceStartSeconds,
  );
  const duration = Math.min(currentDuration, remaining);
  const timelineStart = Math.max(...inserts.map((insert) => insert.timelineEndSeconds)) + 1;
  return {
    ...current,
    id,
    timelineStartSeconds: roundInsertTime(timelineStart),
    timelineEndSeconds: roundInsertTime(timelineStart + duration),
    sourceStartSeconds: roundInsertTime(nextSourceStart),
    sourceEndSeconds: roundInsertTime(nextSourceStart + duration),
  };
}

export function validateLocalVideoKitInserts(
  inserts: LocalVideoKitInsert[],
  sourceDuration?: number | null,
): string[] {
  const errors: string[] = [];
  const ordered = [...inserts].sort(
    (first, second) => first.timelineStartSeconds - second.timelineStartSeconds,
  );
  ordered.forEach((insert, index) => {
    const label = `Insert ${index + 1}`;
    const targetDuration = insert.timelineEndSeconds - insert.timelineStartSeconds;
    const clipDuration = insert.sourceEndSeconds - insert.sourceStartSeconds;
    if (targetDuration < MIN_INSERT_SECONDS || clipDuration < MIN_INSERT_SECONDS) {
      errors.push(`${label}: use pelo menos 0,25 segundo.`);
    }
    if (Math.abs(targetDuration - clipDuration) > TIME_TOLERANCE) {
      errors.push(
        `${label}: o intervalo no vídeo e o trecho do clipe precisam ter a mesma duração.`,
      );
    }
    if (insert.sourceEndSeconds > insert.sourceDurationSeconds + TIME_TOLERANCE) {
      errors.push(`${label}: o trecho ultrapassa o fim do arquivo.`);
    }
    if (sourceDuration && insert.timelineEndSeconds > sourceDuration + TIME_TOLERANCE) {
      errors.push(`${label}: a saída ultrapassa o fim do vídeo principal.`);
    }
    ordered.slice(0, index).forEach((previous) => {
      const overlapsTimeline =
        insert.timelineStartSeconds < previous.timelineEndSeconds - TIME_TOLERANCE &&
        insert.timelineEndSeconds > previous.timelineStartSeconds + TIME_TOLERANCE;
      if (overlapsTimeline) {
        errors.push(`${label}: dois inserts ocupam o mesmo momento do vídeo.`);
      }
      if (previous.uploadId !== insert.uploadId) return;
      const repeatsSource =
        insert.sourceStartSeconds < previous.sourceEndSeconds - TIME_TOLERANCE &&
        insert.sourceEndSeconds > previous.sourceStartSeconds + TIME_TOLERANCE;
      if (repeatsSource) {
        errors.push(`${label}: esse trecho do clipe já foi usado.`);
      }
    });
  });
  return [...new Set(errors)];
}
