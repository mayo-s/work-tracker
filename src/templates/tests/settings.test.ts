// Tests of the settings page helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { ptoYearInput } from '../ts/settings.ts';

test('PTO year input: empty extra days are 0, an empty carry-over is calculated', () => {
  assert.deepEqual(ptoYearInput({ year: '2027', allowance: '25', extra_days: '', carried_over: '', note: 'pro rata' }),
    { allowance: 25, extra_days: 0, carried_over: null, note: 'pro rata' });
});

test('PTO year input with extra days and a fixed, also negative, carry-over', () => {
  assert.deepEqual(ptoYearInput({ allowance: '30', extra_days: '1', carried_over: '-2.5', note: '' }),
    { allowance: 30, extra_days: 1, carried_over: -2.5, note: '' });
});
