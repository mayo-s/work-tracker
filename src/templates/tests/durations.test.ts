// Tests of the duration helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { fromMinutes, toMinutes } from '../ts/durations.ts';

test('durations to minutes', () => {
  assert.equal(toMinutes('12:30'), 750);
  assert.equal(toMinutes('-1:45'), -105);
  assert.equal(toMinutes('+0:15'), 15);
  assert.equal(toMinutes('0:00'), 0);
  assert.equal(toMinutes('2913:15'), 174795);
});

test('minutes to durations', () => {
  assert.equal(fromMinutes(750), '12:30');
  assert.equal(fromMinutes(-105), '-1:45');
  assert.equal(fromMinutes(-15), '-0:15');
  assert.equal(fromMinutes(0), '0:00');
});
