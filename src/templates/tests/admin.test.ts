// Tests of the admin page helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { editable, passphraseError, roleName, userByEmail, userInput } from '../ts/admin.ts';
import type { AdminUserView } from '../ts/api.ts';

const HANS: AdminUserView = {
  id: '24bed067-7677-4f18-87ca-01dfff1229c0', username: 'hans', email: 'hans.dampf@example.com', first_name: 'Hans',
  last_name: 'Dampf', role: 'user', active: true, registered_at: '2026-10-29T08:05:12', last_login_at: null, team: null,
  team_role: null, must_change_password: false,
};

test('a change keeps the rest of the user', () => {
  assert.deepEqual(userInput(HANS, { active: false }), { role: 'user', team_role: null, active: false });
  assert.deepEqual(userInput({ ...HANS, role: 'admin' }, { active: false }), { role: 'admin', team_role: null, active: false });
  const member = { ...HANS, team: 'Platform', team_role: 'member' as const };
  assert.deepEqual(userInput(member, { team_role: 'team_admin' }), { role: 'user', team_role: 'team_admin', active: true });
});

test('roles read as a sentence', () => {
  assert.equal(roleName('admin'), 'an admin');
  assert.equal(roleName('team_admin'), 'a team admin');
});

test('the user for a one-time password is found by e-mail address, ignoring case and spaces', () => {
  assert.equal(userByEmail([HANS], ' Hans.Dampf@Example.com ')?.username, 'hans');
  assert.equal(userByEmail([HANS], 'hans@example.com'), undefined);
});

test('root changes the role of anyone and the status of admins; admins team roles and the status of the others', () => {
  const admin = { ...HANS, role: 'admin' as const };
  const member = { ...HANS, team: 'Platform', team_role: 'member' as const };
  assert.deepEqual(editable('root', HANS, false), { role: true, teamRole: false, status: false });
  assert.deepEqual(editable('root', admin, false), { role: true, teamRole: false, status: true });
  assert.deepEqual(editable('admin', member, false), { role: false, teamRole: true, status: true });
  assert.deepEqual(editable('admin', admin, false), { role: false, teamRole: false, status: false });
});

test('nobody changes their own row, and root stays', () => {
  const none = { role: false, teamRole: false, status: false };
  assert.deepEqual(editable('admin', { ...HANS, role: 'admin', team: 'Platform', team_role: 'member' }, true), none);
  assert.deepEqual(editable('admin', { ...HANS, role: 'root' }, false), none);
  assert.deepEqual(editable('root', { ...HANS, role: 'root' }, true), none);
});

test('the passphrase of the backup needs 12 characters, entered twice', () => {
  assert.equal(passphraseError('too short', 'too short'), 'The passphrase needs at least 12 characters.');
  assert.equal(passphraseError('a long passphrase', 'a long passphrasE'), 'The two passphrases differ.');
  assert.equal(passphraseError('a long passphrase', 'a long passphrase'), null);
});
