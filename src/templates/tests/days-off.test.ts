// Tests of the days off helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import type { DayRangeResult } from '../ts/api.ts';
import { describeConflict, describePreview } from '../ts/days-off.ts';

function result(changes: Partial<DayRangeResult>): DayRangeResult {
  return { saved: false, days: [], conflicts: [], left_out: [], pto_days: 0, ...changes };
}

test('preview of a PTO range with the days left out', () => {
  const summer = result({
    days: ['2026-07-13', '2026-07-14', '2026-07-31'], pto_days: 3,
    left_out: [
      { date: '2026-07-18', weekday: 'Sat', reason: 'day_off', holiday: null, pto_days: 0 },
      { date: '2026-07-19', weekday: 'Sun', reason: 'day_off', holiday: null, pto_days: 0 },
    ],
  });
  assert.equal(describePreview(summer, 'pto'),
    '3 work days, 13.07.2026 – 31.07.2026 · uses 3 PTO days · left out: 2 days off');
  assert.equal(describePreview(summer, 'sick'), '3 work days, 13.07.2026 – 31.07.2026 · left out: 2 days off');
});

test('company half days in the range say that they take their half PTO day by themselves', () => {
  const christmasEve = { date: '2026-12-24', weekday: 'Thu', reason: 'company_half_day', holiday: 'Christmas Eve',
    pto_days: 0.5 } as const;
  const newYearsEve = { ...christmasEve, date: '2026-12-31', holiday: "New Year's Eve" };
  const christmas = result({ days: ['2026-12-21', '2026-12-22', '2026-12-23'], pto_days: 3, left_out: [christmasEve] });
  assert.equal(describePreview(christmas, 'pto'), '3 work days, 21.12.2026 – 23.12.2026 · uses 3 PTO days · '
    + 'Thu 24.12. is a company half day: 0.5 PTO, booked automatically · left out: 1 company half day');
  const both = result({ days: ['2026-12-28'], pto_days: 1, left_out: [christmasEve, newYearsEve] });
  assert.match(describePreview(both, 'sick'),
    / · Thu 24.12. and Thu 31.12. are company half days: 0.5 PTO each, booked automatically · /);
});

test('preview without work days', () => {
  assert.equal(describePreview(result({}), 'pto'), 'No work days in this range.');
  const conflict = { date: '2026-07-14', weekday: 'Tue', worked: '8:00', entries: 1 };
  assert.equal(describePreview(result({ conflicts: [conflict] }), 'pto'),
    'All work days in this range hold times or entries.');
});

test('days holding times or entries', () => {
  assert.equal(describeConflict({ date: '2026-07-14', weekday: 'Tue', worked: '8:00', entries: 2 }),
    'Tue 14.07.2026 · 8:00 worked · 2 entries');
  assert.equal(describeConflict({ date: '2026-07-15', weekday: 'Wed', worked: '0:00', entries: 1 }),
    'Wed 15.07.2026 · 1 entry');
});
