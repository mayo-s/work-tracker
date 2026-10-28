// Calendar helpers on ISO dates (`2026-10-28`) and ISO weeks (`2026-W44`), in local time.

export type IsoDate = string;
export type IsoWeek = string;

const DAY_MS = 24 * 60 * 60 * 1000;
const WEEK_PATTERN = /^(\d{4})-W(\d{2})$/;

function pad(value: number): string {
  return String(value).padStart(2, '0');
}

export function isoDate(date: Date): IsoDate {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function parseIsoDate(value: IsoDate): Date {
  const [year = 0, month = 1, day = 1] = value.split('-').map(Number);
  return new Date(year, month - 1, day);
}

export function addDays(value: IsoDate, days: number): IsoDate {
  const date = parseIsoDate(value);
  date.setDate(date.getDate() + days);
  return isoDate(date);
}

/** Monday = 0 … Sunday = 6 */
function weekdayIndex(date: Date): number {
  return (date.getDay() + 6) % 7;
}

/** The ISO week of a date: weeks start on Monday, week 1 contains the 4th of January. */
export function isoWeek(value: IsoDate): IsoWeek {
  const date = parseIsoDate(value);
  const thursday = new Date(date.getFullYear(), date.getMonth(), date.getDate() - weekdayIndex(date) + 3);
  const firstThursday = new Date(thursday.getFullYear(), 0, 4);
  firstThursday.setDate(firstThursday.getDate() - weekdayIndex(firstThursday) + 3);
  const week = 1 + Math.round((thursday.getTime() - firstThursday.getTime()) / (7 * DAY_MS));
  return `${thursday.getFullYear()}-W${pad(week)}`;
}

/** Monday of an ISO week, e.g. `2026-W44` → `2026-10-26`. */
export function mondayOf(week: IsoWeek): IsoDate {
  const match = WEEK_PATTERN.exec(week);
  if (!match) {
    throw new Error(`Invalid week ${week}`);
  }
  const fourth = new Date(Number(match[1]), 0, 4);
  fourth.setDate(fourth.getDate() - weekdayIndex(fourth) + (Number(match[2]) - 1) * 7);
  return isoDate(fourth);
}

export function isValidWeek(week: string): boolean {
  return WEEK_PATTERN.test(week) && isoWeek(mondayOf(week)) === week;
}

export function shiftWeek(week: IsoWeek, weeks: number): IsoWeek {
  return isoWeek(addDays(mondayOf(week), 7 * weeks));
}

/** `2026-10-28` → `28.10.2026` */
export function formatDate(value: IsoDate): string {
  const [year, month, day] = value.split('-');
  return `${day}.${month}.${year}`;
}

/** `2026-10-28`, `Wed` → `Wed 28.10.` */
export function formatDay(value: IsoDate, weekday: string): string {
  const [, month, day] = value.split('-');
  return `${weekday} ${day}.${month}.`;
}
