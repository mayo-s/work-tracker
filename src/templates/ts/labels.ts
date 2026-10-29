// Display names shared by the pages.

import type { DayType } from './api.ts';

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
