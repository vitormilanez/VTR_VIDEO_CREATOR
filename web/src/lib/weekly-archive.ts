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

export function currentWeekLabel(reference = new Date()) {
  const start = startOfCurrentWeek(reference);
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  return `${start.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })} — ${end.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })}`;
}
