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

/** `2026-10-29T08:05:12` → `29.10.2026 08:05` */
export function formatTimestamp(value: string): string {
  return `${formatDate(value.slice(0, 10))} ${value.slice(11, 16)}`;
}

/** `2026-10-28`, `Wed` → `Wed 28.10.` */
export function formatDay(value: IsoDate, weekday: string): string {
  const [, month, day] = value.split('-');
  return `${weekday} ${day}.${month}.`;
}

export type IsoMonth = string;

const MONTH_PATTERN = /^(\d{4})-(0[1-9]|1[0-2])$/;
const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December',
];

/** `2026-10-28` → `2026-10` */
export function isoMonth(value: IsoDate): IsoMonth {
  return value.slice(0, 7);
}

export function isValidMonth(month: string): boolean {
  return MONTH_PATTERN.test(month);
}

/** `2026-12`, +1 → `2027-01` */
export function shiftMonth(month: IsoMonth, months: number): IsoMonth {
  const [year = 0, number = 1] = month.split('-').map(Number);
  const date = new Date(year, number - 1 + months, 1);
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}`;
}

/** `2026-10` → `October 2026` */
export function formatMonth(month: IsoMonth): string {
  const [year, number] = month.split('-');
  return `${MONTH_NAMES[Number(number) - 1]} ${year}`;
}
