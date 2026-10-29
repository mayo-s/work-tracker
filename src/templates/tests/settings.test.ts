// Tests of the settings page helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { formatWorkDays, ptoYearInput, scheduleInput } from '../ts/settings.ts';

test('PTO year input: empty extra days are 0, an empty carry-over is calculated', () => {
  assert.deepEqual(ptoYearInput({ year: '2027', allowance: '25', extra_days: '', carried_over: '', note: 'pro rata' }),
    { allowance: 25, extra_days: 0, carried_over: null, note: 'pro rata' });
});

test('PTO year input with extra days and a fixed, also negative, carry-over', () => {
  assert.deepEqual(ptoYearInput({ allowance: '30', extra_days: '1', carried_over: '-2.5', note: '' }),
    { allowance: 30, extra_days: 1, carried_over: -2.5, note: '' });
});

test('work days in short form', () => {
  assert.equal(formatWorkDays('Mon,Tue,Wed,Thu,Fri'), 'Mon–Fri');
  assert.equal(formatWorkDays('Mon,Tue,Wed,Thu'), 'Mon–Thu');
  assert.equal(formatWorkDays('Mon,Wed,Fri'), 'Mon, Wed, Fri');
  assert.equal(formatWorkDays('Mon,Tue,Thu,Fri,Sat'), 'Mon, Tue, Thu–Sat');
  assert.equal(formatWorkDays('Sat,Sun'), 'Sat, Sun');
});

test('schedule input with work days as a list', () => {
  assert.deepEqual(scheduleInput({ valid_from: '2027-03-01', weekly_hours: '32:00', work_days: 'Mon,Tue,Wed,Thu' }),
    { valid_from: '2027-03-01', weekly_hours: '32:00', work_days: ['Mon', 'Tue', 'Wed', 'Thu'] });
  assert.deepEqual(scheduleInput({ valid_from: '2027-03-01', weekly_hours: '32:00', work_days: '' }).work_days, []);
});
