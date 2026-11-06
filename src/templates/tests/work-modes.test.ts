// Tests of the ways of working; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { showsWork } from '../ts/work-modes.ts';

test('the reports show the work, in "Times only" only when the period holds entries', () => {
  assert.equal(showsWork('activities', false), true);
  assert.equal(showsWork('times', false), false);
  assert.equal(showsWork('times', true), true);
});
