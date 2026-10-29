// Tests of the setup page helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { countedMonths, initialState, proRata, setupInput, stepError, steps, summary } from '../ts/setup.ts';

const PASCAL = {
  username: ' pascal ', email: 'turbo.pascal@example.com', first_name: 'Pascal', last_name: '',
  password: 'correct horse battery',
  repeat: 'correct horse battery',
};

test('the start month counts if starting by the 15th', () => {
  assert.equal(countedMonths('2027-03-01'), 10);
  assert.equal(countedMonths('2027-03-15'), 10);
  assert.equal(countedMonths('2027-03-20'), 9);
  assert.equal(countedMonths('2027-01-01'), 12);
  assert.equal(countedMonths('2027-12-20'), 0);
});

test('pro rata PTO is rounded up to half days', () => {
  assert.equal(proRata(30, '2027-03-01'), 25);
  assert.equal(proRata(30, '2027-03-20'), 22.5);
  assert.equal(proRata(28, '2027-08-01'), 12);  // 11.67
  assert.equal(proRata(30, '2024-06-01'), 17.5);
});

test('initial state proposes the first year', () => {
  const state = initialState('2027-03-01');
  assert.equal(state.firstYear, '25');
  assert.deepEqual(state.workDays, ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']);
});

test('steps check their values before going on', () => {
  const state = initialState('2027-03-01');
  assert.equal(stepError(state, 'Start'), null);
  assert.equal(stepError({ ...state, opening: '1,5' }, 'Start'), 'Enter the opening balance as h:mm, e.g. 0:00.');
  assert.equal(stepError({ ...state, workDays: [] }, 'Work schedule'), 'Choose at least one work day.');
  assert.equal(stepError({ ...state, weeklyHours: '40' }, 'Work schedule'), 'Enter the hours per week as h:mm, e.g. 40:00.');
  assert.equal(stepError({ ...state, firstYear: '' }, 'PTO'), 'Enter the PTO days.');
  assert.equal(stepError(state, 'Services'), null);
  assert.equal(stepError(state, 'Login'), 'Enter your first name.');
  assert.equal(stepError({ ...state, account: PASCAL }, 'Login'), null);
  assert.equal(stepError({ ...state, account: null }, 'Login'), null);
});

test('the login step only when the database has no user yet', () => {
  assert.deepEqual(steps(initialState('2027-03-01')), ['Login', 'Start', 'Work schedule', 'PTO', 'Services', 'Summary']);
  assert.deepEqual(steps({ ...initialState('2027-03-01'), account: null }),
    ['Start', 'Work schedule', 'PTO', 'Services', 'Summary']);
});

test('setup input leaves out empty services and trims', () => {
  const state = { ...initialState('2027-03-01'), opening: ' +2:30 ', account: PASCAL,
    services: [{ short_name: ' AUTH ', name: ' auth-service ' }, { short_name: ' ', name: 'unused' }] };
  assert.deepEqual(setupInput(state), {
    balance_start: '2027-03-01', opening_balance: '+2:30',
    schedule: { weekly_hours: '40:00', work_days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'], state: 'BE', company_half_days: true },
    pto_per_year: 30, pto_first_year: 25, services: [{ short_name: 'AUTH', name: 'auth-service' }],
    user: {
      username: 'pascal', email: 'turbo.pascal@example.com', first_name: 'Pascal', last_name: '',
      password: 'correct horse battery',
    },
  });
  assert.equal(setupInput({ ...state, account: null }).user, null);
});

test('summary of all steps', () => {
  assert.deepEqual(summary({ ...initialState('2027-03-01'), state: 'HH', companyHalfDays: false, account: PASCAL }), [
    ['Login', 'pascal · turbo.pascal@example.com'],
    ['First day', '01.03.2027'],
    ['Opening balance', '0:00'],
    ['Work schedule', '40:00 h per week, Mon, Tue, Wed, Thu, Fri'],
    ['Public holidays', 'Hamburg'],
    ['PTO', '25 days in 2027, 30 days from 2028'],
    ['Services', 'none yet'],
  ]);
});
