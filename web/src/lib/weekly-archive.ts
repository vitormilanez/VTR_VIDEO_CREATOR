export type WeeklyView = "current" | "archive";

export function startOfCurrentWeek(reference = new Date()) {
  const start = new Date(reference);
  const day = start.getDay();
  const daysSinceMonday = day === 0 ? 6 : day - 1;
  start.setDate(start.getDate() - daysSinceMonday);
  start.setHours(0, 0, 0, 0);
  return start;
}

export function isCurrentWeek(value: string | Date | null | undefined, reference = new Date()) {
  if (!value) return false;
  const date = value instanceof Date ? value : parseCalendarDate(value);
  if (Number.isNaN(date.getTime())) return false;
  const start = startOfCurrentWeek(reference);
  const nextWeek = new Date(start);
  nextWeek.setDate(nextWeek.getDate() + 7);
  return date >= start && date < nextWeek;
}

function parseCalendarDate(value: string) {
  const calendarDate = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!calendarDate) return new Date(value);
  return new Date(Number(calendarDate[1]), Number(calendarDate[2]) - 1, Number(calendarDate[3]));
}

export function splitWeekly<T>(items: T[], getDate: (item: T) => string | Date | null | undefined) {
  const current: T[] = [];
  const archive: T[] = [];
  items.forEach((item) => (isCurrentWeek(getDate(item)) ? current : archive).push(item));
  return { current, archive };
}

export function splitWeeklyUnique<T>(
  items: T[],
  getDate: (item: T) => string | Date | null | undefined,
  getKey: (item: T) => string,
) {
  const weekly = splitWeekly(items, getDate);
  const currentByRecency = [...weekly.current].sort(
    (left, right) => dateTimestamp(getDate(right)) - dateTimestamp(getDate(left)),
  );
  const seen = new Set<string>();
  const current: T[] = [];
  const duplicates: T[] = [];

  currentByRecency.forEach((item) => {
    const key = getKey(item);
    if (seen.has(key)) {
      duplicates.push(item);
      return;
    }
    seen.add(key);
    current.push(item);
  });

  return { current, archive: [...duplicates, ...weekly.archive] };
}

function dateTimestamp(value: string | Date | null | undefined) {
  if (!value) return 0;
  const date = value instanceof Date ? value : new Date(value);
  const timestamp = date.getTime();
  return Number.isFinite(timestamp) ? timestamp : 0;
}

export function currentWeekLabel(reference = new Date()) {
  const start = startOfCurrentWeek(reference);
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  return `${start.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })} — ${end.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })}`;
}
