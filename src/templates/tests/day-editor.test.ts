// Tests of the day form helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import type { DayView } from '../ts/api.ts';
import { dayInput, formValues } from '../ts/day-editor.ts';

function day(changes: Partial<DayView> = {}): DayView {
  return {
    date: '2026-10-28', weekday: 'Wed', day_type: 'work', automatic: true, holiday: null, recorded: true, start: '07:15',
    end: '16:00', break_time: '0:30', break_default: true, worked: '8:15', target: '8:00', overtime: '0:15', pto_days: 0, work_day: true,
    note: 'OFFICE DAY', ...changes,
  };
}

test('form values leave an automatic type and a legal break empty, keep a chosen type and an explicit one', () => {
  assert.deepEqual(formValues(day()), { day_type: '', start: '07:15', end: '16:00', break_time: '', note: 'OFFICE DAY' });
  const chosen = formValues(day({ day_type: 'pto_half', automatic: false, break_default: false, break_time: '0:00' }));
  assert.deepEqual([chosen.day_type, chosen.break_time], ['pto_half', '0:00']);
  const unrecorded = formValues(day({ recorded: false, start: null, end: null, break_time: null, break_default: false, note: '' }));
  assert.deepEqual(unrecorded, { day_type: '', start: '', end: '', break_time: '', note: '' });
});

test('day input leaves out empty fields and trims', () => {
  assert.deepEqual(dayInput({ day_type: '', start: ' 7:15 ', end: '16:00', break_time: '', note: ' Anreise ' }),
    { note: 'Anreise', start: '7:15', end: '16:00' });
  assert.deepEqual(dayInput({ day_type: 'pto', start: '', end: '', break_time: '0:00', note: '' }),
    { note: '', day_type: 'pto', break_time: '0:00' });
});
