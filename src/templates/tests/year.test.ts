// Tests of the year report helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { daysOffRows, formatDays, runningBalances, yearFromSearch } from '../ts/year.ts';

test('year from the address, otherwise the current year', () => {
  assert.equal(yearFromSearch('?year=2025', '2026-10-29'), 2025);
  assert.equal(yearFromSearch('', '2026-10-29'), 2026);
  assert.equal(yearFromSearch('?year=abc', '2026-10-29'), 2026);
  assert.equal(yearFromSearch('?year=1999', '2026-10-29'), 2026);
});

test('running balance at the end of each month', () => {
  assert.deepEqual(runningBalances('6:30', ['1:00', '-2:15', '0:00', '4:45']), ['7:30', '5:15', '5:15', '10:00']);
  assert.deepEqual(runningBalances('0:30', ['-1:00']), ['-0:30']);
});

test('PTO days without trailing zeros', () => {
  assert.equal(formatDays(2.5), '2.5');
  assert.equal(formatDays(17), '17');
  assert.equal(formatDays(-0.5), '-0.5');
});

test('days off in the order of the day types, without zero counts', () => {
  assert.deepEqual(daysOffRows({ sick: 2, pto: 27, company_half_day: 2, pto_half: 2, unpaid_leave: 0 }),
    [['PTO', 27], ['PTO ½', 2], ['Sick', 2], ['Company half day', 2]]);
  assert.deepEqual(daysOffRows({}), []);
});
