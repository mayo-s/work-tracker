// Tests of the admin page helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { confirmsDeletion, editable, passphraseError, restoredText, roleName, toBase64, userByEmail, userInput } from '../ts/admin.ts';
import type { AdminUserView } from '../ts/api.ts';

const HANS: AdminUserView = {
  id: '24bed067-7677-4f18-87ca-01dfff1229c0', username: 'hans', email: 'hans.dampf@example.com', first_name: 'Hans',
  last_name: 'Dampf', role: 'user', active: true, registered_at: '2026-10-29T08:05:12', last_login_at: null, team: null,
  team_role: null, must_change_password: false,
};

test('a change keeps the rest of the user', () => {
  assert.deepEqual(userInput(HANS, { active: false }), { role: 'user', team_role: null, active: false, support: false });
  assert.deepEqual(userInput({ ...HANS, role: 'admin', support: true }, { active: false }),
    { role: 'admin', team_role: null, active: false, support: true });
  const member = { ...HANS, team: 'Platform', team_role: 'member' as const };
  assert.deepEqual(userInput(member, { team_role: 'team_admin' }),
    { role: 'user', team_role: 'team_admin', active: true, support: false });
});

test('a deletion is confirmed by typing the exact username', () => {
  assert.equal(confirmsDeletion(HANS, ' hans '), true);
  assert.equal(confirmsDeletion(HANS, 'Hans'), false);
});

test('roles read as a sentence', () => {
  assert.equal(roleName('admin'), 'an admin');
  assert.equal(roleName('team_admin'), 'a team admin');
});

test('the user for a one-time password is found by e-mail address, ignoring case and spaces', () => {
  assert.equal(userByEmail([HANS], ' Hans.Dampf@Example.com ')?.username, 'hans');
  assert.equal(userByEmail([HANS], 'hans@example.com'), undefined);
});

test('root changes the role of anyone and the status of admins; admins team roles, support and the status of the others',
  () => {
    const admin = { ...HANS, role: 'admin' as const };
    const member = { ...HANS, team: 'Platform', team_role: 'member' as const };
    assert.deepEqual(editable('root', HANS, false), { role: true, teamRole: false, status: false, support: false });
    assert.deepEqual(editable('root', admin, false), { role: true, teamRole: false, status: true, support: false });
    assert.deepEqual(editable('admin', member, false), { role: false, teamRole: true, status: true, support: true });
    assert.deepEqual(editable('admin', admin, false), { role: false, teamRole: false, status: false, support: true });
  });

test('nobody changes their own row but an admin their support role, and root stays', () => {
  const none = { role: false, teamRole: false, status: false, support: false };
  assert.deepEqual(editable('admin', { ...HANS, role: 'admin', team: 'Platform', team_role: 'member' }, true),
    { ...none, support: true });
  assert.deepEqual(editable('admin', { ...HANS, role: 'root' }, false), none);
  assert.deepEqual(editable('root', { ...HANS, role: 'root' }, true), none);
});

test('the passphrase of the backup needs 12 characters, entered twice', () => {
  assert.equal(passphraseError('too short', 'too short'), 'The passphrase needs at least 12 characters.');
  assert.equal(passphraseError('a long passphrase', 'a long passphrasE'), 'The two passphrases differ.');
  assert.equal(passphraseError('a long passphrase', 'a long passphrase'), null);
});

test('the backup file goes as base64, also when large', () => {
  assert.equal(toBase64(new Uint8Array([0, 255, 16])), 'AP8Q');
  const large = new Uint8Array(200_000).map((_, index) => index % 251);
  assert.equal(toBase64(large), Buffer.from(large).toString('base64'));
});

test('what a restore brought back', () => {
  assert.equal(restoredText({ users: 3, teams: 1, entries: 120, audit_entries: 9 }),
    'Restored the backup: 3 users, 1 team, 120 entries');
  assert.equal(restoredText({ users: 1, teams: 0, entries: 1, audit_entries: 0 }),
    'Restored the backup: 1 user, 0 teams, 1 entry');
});
