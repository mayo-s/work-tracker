// Tests of the search page helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  apiQuery, criteriaFromSearch, describePeriod, periodRange, scopeCriteria, scopeValue, searchQuery, type SearchCriteria,
} from '../ts/search.ts';

const TODAY = '2026-11-05';
const CRITERIA: SearchCriteria = {
  text: 'PR review', service_id: null, activity_type_id: 'a2', period: '', start: '', end: '',
};

test('the criteria come from the URL: all time by default, dates alone are a custom period, broken ones are left out', () => {
  assert.deepEqual(criteriaFromSearch('?text=+ENGINE-59+europace+&service_id=s1&period=toString'), {
    text: 'ENGINE-59 europace', service_id: 's1', activity_type_id: null, period: '', start: '', end: '',
  });
  assert.deepEqual([criteriaFromSearch('?start=2026-03-01&end=31.12.'), criteriaFromSearch('?period=this-year&start=2026-03-01')]
    .map(({ period, start, end }) => [period, start, end]), [['custom', '2026-03-01', ''], ['this-year', '', '']]);
});

test('a period turns into its days on today', () => {
  const ranges = (['', 'this-year', 'last-year', 'last-12-months', 'this-month'] as const)
    .map((period) => periodRange({ period, start: '', end: '' }, TODAY));
  assert.deepEqual(ranges, [
    { start: null, end: null }, { start: '2026-01-01', end: '2026-12-31' }, { start: '2025-01-01', end: '2025-12-31' },
    { start: '2025-12-01', end: '2026-11-05' }, { start: '2026-11-01', end: '2026-11-30' },
  ]);
  assert.deepEqual(periodRange({ period: 'custom', start: '2026-03-01', end: '' }, TODAY), { start: '2026-03-01', end: null });
});

test('the period as shown above the results', () => {
  assert.deepEqual([
    describePeriod('', { start: null, end: null }),
    describePeriod('this-year', { start: '2026-01-01', end: '2026-12-31' }),
    describePeriod('custom', { start: '2026-03-01', end: null }),
    describePeriod('custom', { start: null, end: '2026-03-31' }),
  ], ['All time', 'This year · 01.01.2026 – 31.12.2026', 'from 01.03.2026', 'until 31.03.2026']);
});

test('the URL keeps the period, the API gets its dates and the limit; empty criteria are left out', () => {
  const lastYear = { ...CRITERIA, period: 'last-year' as const };
  assert.equal(searchQuery(lastYear), 'text=PR+review&activity_type_id=a2&period=last-year');
  assert.equal(apiQuery(lastYear, TODAY, 100), 'text=PR+review&activity_type_id=a2&start=2025-01-01&end=2025-12-31&limit=100');
  assert.equal(apiQuery(CRITERIA, TODAY, null), 'text=PR+review&activity_type_id=a2');
});

test('a choice of the select is a service, no service, an activity type or nothing, and back', () => {
  const choices = ['service:s1', 'service:none', 'activity:a2', ''];
  assert.deepEqual(choices.map(scopeCriteria), [
    { service_id: 's1', activity_type_id: null }, { service_id: 'none', activity_type_id: null },
    { service_id: null, activity_type_id: 'a2' }, { service_id: null, activity_type_id: null },
  ]);
  assert.deepEqual(choices.map((value) => scopeValue(scopeCriteria(value))), choices);
});
