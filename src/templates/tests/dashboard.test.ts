// Tests of the dashboard helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { describeComingUp, hourTicks, labelIndexes, pointLabel } from '../ts/dashboard.ts';

test('hour ticks cover the values and zero at round steps', () => {
  assert.deepEqual(hourTicks(-174 * 60, 16 * 60), [-200, -150, -100, -50, 0, 50].map((hours) => hours * 60));
  assert.deepEqual(hourTicks(2 * 60, 18 * 60), [0, 5, 10, 15, 20].map((hours) => hours * 60));
  assert.deepEqual(hourTicks(0, 0), [0]);
});

test('x-axis labels spread evenly and include the last point', () => {
  assert.deepEqual(labelIndexes(5, 7), [0, 1, 2, 3, 4]);
  assert.deepEqual(labelIndexes(28, 6), [0, 6, 12, 18, 24, 27]);
  assert.deepEqual(labelIndexes(29, 7), [0, 5, 10, 15, 20, 25, 28]);
});

test('points as days or months', () => {
  assert.equal(pointLabel({ date: '2026-10-28', minutes: 0, balance: '0:00' }, 'month'), 'Wed 28.10.2026');
  assert.equal(pointLabel({ date: '2026-09-30', minutes: 0, balance: '0:00' }, 'year'), 'September 2026');
});

test('coming up: ranges with their days, holidays by name', () => {
  assert.equal(describeComingUp({ start: '2026-11-05', end: '2026-11-09', day_type: 'pto', holiday: null, days: 3 }),
    'Thu 05.11. – Mon 09.11. · PTO · 3 days');
  assert.equal(describeComingUp({ start: '2026-12-25', end: '2026-12-25', day_type: 'public_holiday',
    holiday: 'Christmas Day', days: 1 }), 'Fri 25.12. · Christmas Day');
});
