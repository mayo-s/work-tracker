// Tests of the admin page helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { roleName, userInput } from '../ts/admin.ts';
import type { AdminUserView } from '../ts/api.ts';

const HANS: AdminUserView = {
  id: '24bed067-7677-4f18-87ca-01dfff1229c0', username: 'hans', email: 'hans.dampf@example.com', first_name: 'Hans',
  last_name: 'Dampf', role: 'user', active: true, registered_at: '2026-10-29T08:05:12', last_login_at: null, team: null,
};

test('a change keeps the rest of the user', () => {
  assert.deepEqual(userInput(HANS, { active: false }), { role: 'user', active: false });
  assert.deepEqual(userInput({ ...HANS, role: 'admin' }, { active: false }), { role: 'admin', active: false });
  assert.deepEqual(userInput({ ...HANS, role: 'team_admin' }, {}), { role: 'team_admin', active: true });
});

test('roles read as a sentence', () => {
  assert.equal(roleName('team_admin'), 'a team admin');
});
