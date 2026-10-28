// Tests of the week view rules; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import type { DayView, EntryView } from '../ts/api.ts';
import { DAY_TYPE_LABELS, entriesByDate, needsWarning, signed, valueClass, visibleDays, weekFromSearch } from '../ts/week.ts';

function day(date: string, weekday: string, changes: Partial<DayView> = {}): DayView {
  return {
    date, weekday, day_type: 'work', automatic: true, holiday: null, recorded: false, start: null, end: null,
    break_time: null, break_default: false, worked: '0:00', target: '8:00', overtime: '-8:00', pto_days: 0, note: '',
    flags: [], ...changes,
  };
}

function entry(date: string): EntryView {
  return { id: 1, kind: 'ticket', date, duration: '1:00', ticket_key: 'TNG-5882', changed: false, flags: [] } as EntryView;
}

test('overtime with a sign', () => {
  assert.equal(signed('0:15'), '+0:15');
  assert.equal(signed('-0:30'), '-0:30');
  assert.equal(signed('0:00'), '0:00');
});

test('value classes: negative as warning, positive in mint, zero plain', () => {
  assert.equal(valueClass('-8:00'), 'value-negative');
  assert.equal(valueClass('12:30'), 'value-positive');
  assert.equal(valueClass('0:00'), '');
});

test('entries grouped by date', () => {
  const grouped = entriesByDate([entry('2026-10-27'), entry('2026-10-28'), entry('2026-10-27')]);
  assert.deepEqual([...grouped.keys()], ['2026-10-27', '2026-10-28']);
  assert.equal(grouped.get('2026-10-27')?.length, 2);
});

test('weekend days only when something was recorded', () => {
  const days = [day('2026-10-30', 'Fri'), day('2026-10-31', 'Sat'), day('2026-11-01', 'Sun', { recorded: true })];
  assert.deepEqual(visibleDays(days, new Map()).map((item) => item.weekday), ['Fri', 'Sun']);
  assert.deepEqual(visibleDays(days, entriesByDate([entry('2026-10-31')])).map((item) => item.weekday), ['Fri', 'Sat', 'Sun']);
});

test('warning for past work days without entries', () => {
  const today = '2026-10-28';
  assert.ok(needsWarning(day('2026-10-27', 'Tue'), [], today));
  assert.ok(!needsWarning(day('2026-10-27', 'Tue'), [entry('2026-10-27')], today));
  assert.ok(!needsWarning(day('2026-10-28', 'Wed'), [], today), 'not today');
  assert.ok(!needsWarning(day('2026-10-29', 'Thu'), [], today), 'not in the future');
  assert.ok(!needsWarning(day('2026-10-27', 'Tue', { day_type: 'pto' }), [], today), 'not on days off');
  assert.ok(!needsWarning(day('2026-10-25', 'Sun'), [], today), 'not on weekends');
});

test('week from the address, otherwise the current week', () => {
  assert.equal(weekFromSearch('?week=2026-W40', '2026-10-28'), '2026-W40');
  assert.equal(weekFromSearch('', '2026-10-28'), '2026-W44');
  assert.equal(weekFromSearch('?week=2026-W99', '2026-10-28'), '2026-W44');
});

test('every day type has a label', () => {
  assert.equal(DAY_TYPE_LABELS.pto_half, 'PTO ½');
  assert.equal(Object.keys(DAY_TYPE_LABELS).length, 9);
});
