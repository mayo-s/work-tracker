// Tests of the search page helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { criteriaFromSearch, scopeCriteria, scopeValue, searchQuery } from '../ts/search.ts';

test('the criteria come from the URL; the period defaults to this year, also for a broken date', () => {
  assert.deepEqual(criteriaFromSearch('?text=+ENGINE-59+europace+&service_id=s1&end=31.12.', '2026-11-05'), {
    text: 'ENGINE-59 europace', service_id: 's1', activity_type_id: null, start: '2026-01-01', end: '2026-12-31',
  });
});

test('the query leaves out empty criteria', () => {
  const criteria = { text: 'PR review', service_id: null, activity_type_id: 'a2', start: '2026-01-01', end: '2026-06-30' };
  assert.equal(searchQuery(criteria), 'text=PR+review&activity_type_id=a2&start=2026-01-01&end=2026-06-30');
});

test('a choice of the select is a service, no service, an activity type or nothing, and back', () => {
  const choices = ['service:s1', 'service:none', 'activity:a2', ''];
  assert.deepEqual(choices.map(scopeCriteria), [
    { service_id: 's1', activity_type_id: null }, { service_id: 'none', activity_type_id: null },
    { service_id: null, activity_type_id: 'a2' }, { service_id: null, activity_type_id: null },
  ]);
  assert.deepEqual(choices.map((value) => scopeValue(scopeCriteria(value))), choices);
});
