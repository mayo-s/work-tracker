// Tests of the team page helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { teamId } from '../ts/team.ts';

test('the team from the address, otherwise the own one', () => {
  assert.equal(teamId('?team=7', 3), 7);
  assert.equal(teamId('', 3), 3);
  assert.equal(teamId('?team=abc', null), null);
});
