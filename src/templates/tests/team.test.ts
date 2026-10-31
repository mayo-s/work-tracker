// Tests of the team page helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { teamId } from '../ts/team.ts';

test('the team from the address, otherwise the own one', () => {
  assert.equal(teamId('?team=0190a3c4-0007', '0190a3c4-0003'), '0190a3c4-0007');
  assert.equal(teamId('', '0190a3c4-0003'), '0190a3c4-0003');
  assert.equal(teamId('?team=', null), null);
});
