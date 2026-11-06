// Display names shared by the pages.

import type { DayType, WorkMode } from './api.ts';

export const DAY_TYPE_LABELS: Record<DayType, string> = {
  work: 'Work',
  pto: 'PTO',
  pto_half: 'PTO ½',
  sick: 'Sick',
  sick_half: 'Sick ½',
  overtime_off: 'Overtime off',
  unpaid_leave: 'Unpaid leave',
  public_holiday: 'Holiday',
  company_half_day: 'Company half day',
};

/** The ways of working (SPEC 5.11): name and what it means. */
export const WORK_MODES: [WorkMode, string, string][] = [
  ['developer', 'Developer', 'Tickets and activities; ticket work can be marked as coding.'],
  ['tickets', 'Tickets, no coding', 'Tickets and activities, without coding work.'],
  ['activities', 'Activities only', 'Activities such as meetings or travel, no tickets.'],
  ['times', 'Times only', 'Start, end and break of each day, no entries.'],
];

export const WEEKDAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const;

/** German federal states, whose public holidays a work schedule follows. */
export const STATE_NAMES: Record<string, string> = {
  BB: 'Brandenburg', BE: 'Berlin', BW: 'Baden-Württemberg', BY: 'Bayern', HB: 'Bremen', HE: 'Hessen', HH: 'Hamburg',
  MV: 'Mecklenburg-Vorpommern', NI: 'Niedersachsen', NW: 'Nordrhein-Westfalen', RP: 'Rheinland-Pfalz',
  SH: 'Schleswig-Holstein', SL: 'Saarland', SN: 'Sachsen', ST: 'Sachsen-Anhalt', TH: 'Thüringen',
};
