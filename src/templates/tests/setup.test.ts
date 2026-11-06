// Tests of the setup page helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  countedMonths, importSummary, initialState, parseExportFile, proRata, setupInput, setupSteps, stepError, summary,
} from '../ts/setup.ts';

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
  assert.equal(stepError({ ...state, opening: '-1,5' }, 'Start'), null);
  assert.equal(stepError({ ...state, opening: 'soon' }, 'Start'),
    'Enter the opening balance, e.g. 0:00, 12:30, -1:45 or 1.5.');
  assert.equal(stepError({ ...state, workDays: [] }, 'Work schedule'), 'Choose at least one work day.');
  assert.equal(stepError({ ...state, weeklyHours: '38.5' }, 'Work schedule'), null);
  assert.equal(stepError({ ...state, weeklyHours: '200' }, 'Work schedule'),
    'Enter the hours per week, e.g. 40:00 or 38.5 (at most 168:00).');
  assert.equal(stepError({ ...state, firstYear: '' }, 'PTO'), 'Enter the PTO days.');
  assert.equal(stepError(state, 'Services'), null);
});

test('the setup is about the own data only (root is created before); services only with ticket entries', () => {
  assert.deepEqual(setupSteps('tickets'), ['Start', 'Work schedule', 'PTO', 'Services', 'Summary']);
  assert.deepEqual(setupSteps('activities'), ['Start', 'Work schedule', 'PTO', 'Summary']);
});

test('setup input leaves out empty services and trims', () => {
  const state = { ...initialState('2027-03-01'), opening: ' +2:30 ',
    services: [{ short_name: ' AUTH ', name: ' auth-service ' }, { short_name: ' ', name: 'unused' }] };
  assert.deepEqual(setupInput(state), {
    balance_start: '2027-03-01', opening_balance: '+2:30',
    schedule: { weekly_hours: '40:00', work_days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'], state: 'BE', company_half_days: true },
    pto_per_year: 30, pto_first_year: 25, services: [{ short_name: 'AUTH', name: 'auth-service' }], work_mode: 'tickets',
    coding: true,
  });
  const times = setupInput({ ...state, workMode: 'times' });  // services and Coding chosen before choosing times only
  assert.deepEqual([times.services, times.coding], [[], false]);
});

test('summary of all steps', () => {
  assert.deepEqual(summary({ ...initialState('2027-03-01'), state: 'HH', companyHalfDays: false }), [
    ['Way of working', 'Tickets and activities, with Coding'],
    ['First day', '01.03.2027'],
    ['Opening balance', '0:00'],
    ['Work schedule', '40:00 h per week, Mon, Tue, Wed, Thu, Fri'],
    ['Public holidays', 'Hamburg'],
    ['PTO', '25 days in 2027, 30 days from 2028'],
    ['Services', 'none yet'],
  ]);
  assert.deepEqual(summary({ ...initialState('2027-03-01'), workMode: 'activities' }).map(([label]) => label),
    ['Way of working', 'First day', 'Opening balance', 'Work schedule', 'Public holidays', 'PTO']);
});

test('an export file is read when it has the format and a known version', () => {
  const file = { format: 'work-tracker', version: 1, entries: [] };
  assert.deepEqual(parseExportFile(JSON.stringify(file)), { data: file });
});

test('other files and newer versions are not imported', () => {
  const noExport = { problem: 'This is no Work Tracker export file: choose the file of "Export my data".' };
  assert.deepEqual(parseExportFile('Datum;Start;Ende'), noExport);
  assert.deepEqual(parseExportFile('{"format": "spreadsheet"}'), noExport);
  assert.deepEqual(parseExportFile('null'), noExport);
  assert.deepEqual(parseExportFile('{"format": "work-tracker", "version": 2}'),
    { problem: 'The file has version 2; this Work Tracker reads up to version 1.' });
});

test('the import summary lists the counts per type', () => {
  const counts = { days: 633, entries: 732, history: 746, review_flags: 3, tickets: 189, services: 7, activity_types: 4,
    work_schedules: 1, pto_years: 4 };
  assert.deepEqual(importSummary(counts).slice(0, 3), [['Days', '633'], ['Entries', '732'], ['History lines', '746']]);
  assert.equal(importSummary(counts).length, 9);
});
