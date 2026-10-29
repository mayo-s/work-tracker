// Tests of the team view helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { ownView, viewedMember, withMember } from '../ts/team-view.ts';

test('the member from the address', () => {
  assert.equal(viewedMember('?week=2026-W45&member=abc'), 'abc');
  assert.equal(viewedMember('?member='), null);
});

test('links to the team view pages keep the member, others stay', () => {
  assert.equal(withMember('/month?month=2026-10', 'abc'), '/month?month=2026-10&member=abc');
  assert.equal(withMember('/', 'abc'), '/?member=abc');
  assert.equal(withMember('/week?member=abc', 'abc'), '/week?member=abc');
  assert.equal(withMember('/settings#team', 'abc'), '/settings#team');
  assert.equal(withMember('https://example.com/week', 'abc'), 'https://example.com/week');
});

test('back to the own data', () => {
  assert.equal(ownView('/month', '?month=2026-10&member=abc'), '/month?month=2026-10');
  assert.equal(ownView('/', '?member=abc'), '/');
});
