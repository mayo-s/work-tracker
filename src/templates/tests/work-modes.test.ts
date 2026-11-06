// Tests of the ways of working; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { workParts } from '../ts/work-modes.ts';

const NONE = { coding: [], other_work: [], activities: [] };

test('the work report has the parts of the way of working', () => {
  assert.deepEqual(workParts('developer', NONE), ['coding', 'other_work', 'activities']);
  assert.deepEqual(workParts('tickets', NONE), ['ticket_work', 'activities']);
  assert.deepEqual(workParts('activities', NONE), ['activities']);
  assert.deepEqual(workParts('times', NONE), []);
});

test('and the parts with data in the period', () => {
  assert.deepEqual(workParts('tickets', { ...NONE, coding: [{}] }), ['coding', 'other_work', 'activities']);
  assert.deepEqual(workParts('activities', { ...NONE, other_work: [{}] }), ['ticket_work', 'activities']);
  assert.deepEqual(workParts('times', { ...NONE, activities: [{}] }), ['activities']);
});
