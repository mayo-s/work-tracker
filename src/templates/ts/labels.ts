// Display names shared by the pages.

import type { DayType } from './api.ts';
import { t } from './i18n.ts';

export const DAY_TYPE_LABELS: Record<DayType, string> = {
  work: t('Work'),
  pto: t('PTO'),
  pto_half: t('PTO ½'),
  sick: t('Sick'),
  sick_half: t('Sick ½'),
  overtime_off: t('Overtime off'),
  unpaid_leave: t('Unpaid leave'),
  public_holiday: t('Holiday'),
  company_half_day: t('Company half day'),
};

/** The weekdays as the API names them (work schedules, days); `weekdayName` shows them. */
export const WEEKDAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const;

/** The short name of a weekday of the API in the page's language, e.g. `Wed` → German `Mi`. */
export function weekdayName(code: string): string {
  const names: Record<string, string> = {
    Mon: t('Mon'), Tue: t('Tue'), Wed: t('Wed'), Thu: t('Thu'), Fri: t('Fri'), Sat: t('Sat'), Sun: t('Sun'),
  };
  return names[code] ?? code;
}

/** German federal states, whose public holidays a work schedule follows; their names in German in every language. */
export const STATE_NAMES: Record<string, string> = {
  BB: 'Brandenburg', BE: 'Berlin', BW: 'Baden-Württemberg', BY: 'Bayern', HB: 'Bremen', HE: 'Hessen', HH: 'Hamburg',
  MV: 'Mecklenburg-Vorpommern', NI: 'Niedersachsen', NW: 'Nordrhein-Westfalen', RP: 'Rheinland-Pfalz',
  SH: 'Schleswig-Holstein', SL: 'Saarland', SN: 'Sachsen', ST: 'Sachsen-Anhalt', TH: 'Thüringen',
};
