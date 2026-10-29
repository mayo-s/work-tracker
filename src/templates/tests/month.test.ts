// Tests of the month report helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { describeDaysOff, monthFromSearch } from '../ts/month.ts';

test('month from the address, otherwise the current month', () => {
  assert.equal(monthFromSearch('?month=2025-02', '2026-10-29'), '2025-02');
  assert.equal(monthFromSearch('', '2026-10-29'), '2026-10');
  assert.equal(monthFromSearch('?month=2026-13', '2026-10-29'), '2026-10');
});

test('days off as text', () => {
  assert.equal(describeDaysOff({ pto: 2, pto_half: 1 }), 'PTO 2 · PTO ½ 1');
  assert.equal(describeDaysOff({}), '');
});
