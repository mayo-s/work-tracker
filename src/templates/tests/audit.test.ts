// Tests of the audit log texts; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import type { AuditView } from '../ts/api.ts';
import { auditText } from '../ts/audit.ts';

const ENTRY: AuditView = {
  at: '2026-11-02T09:00:00', actor: 'Pascal Turbo', action: 'role_changed', user: 'Hans Dampf', team: null, detail: 'admin',
};

test('each change reads as a sentence', () => {
  assert.equal(auditText(ENTRY), 'Pascal Turbo made Hans Dampf an admin');
  assert.equal(auditText({ ...ENTRY, actor: 'Klara Himmel', action: 'team_role_changed', team: 'Platform', detail: 'team_admin' }),
    'Klara Himmel made Hans Dampf team admin of Platform');
  assert.equal(auditText({ ...ENTRY, action: 'registration_switched', user: null, detail: 'on' }),
    'Pascal Turbo switched registration on');
  assert.equal(auditText({ ...ENTRY, action: 'team_renamed', user: null, team: 'Core', detail: 'Platform' }),
    'Pascal Turbo renamed the team Platform to Core');
  assert.equal(auditText({ ...ENTRY, action: 'deactivated', detail: '' }), 'Pascal Turbo deactivated Hans Dampf');
});

test('auditor assignments read as sentences', () => {
  const assigned = { ...ENTRY, actor: 'Klara Himmel', action: 'auditor_assigned' as const, team: 'Platform' };
  assert.equal(auditText({ ...assigned, detail: '2026-11-30' }), 'Klara Himmel made Hans Dampf auditor of Platform until 30.11.2026');
  assert.equal(auditText({ ...assigned, detail: '' }), 'Klara Himmel made Hans Dampf auditor of Platform');
  assert.equal(auditText({ ...assigned, action: 'auditor_removed', detail: '' }), "Klara Himmel ended Hans Dampf's audit of Platform");
});

test('a reset of the root login', () => {
  assert.equal(auditText({ ...ENTRY, action: 'root_login_reset', user: 'Pascal Turbo', detail: '' }),
    'Pascal Turbo reset the root login with a new setup token');
});

test('changes to the own login', () => {
  const own = { ...ENTRY, actor: 'Hans Dampf', detail: '' };
  assert.equal(auditText({ ...own, action: 'password_changed' }), 'Hans Dampf changed their password');
  assert.equal(auditText({ ...own, action: 'password_changed', detail: 'command' }),
    'The password of Hans Dampf was set with the set-password command');
  assert.equal(auditText({ ...own, action: 'two_factor_on' }), 'Hans Dampf switched two-factor login on');
  assert.equal(auditText({ ...own, action: 'two_factor_off' }), 'Hans Dampf switched two-factor login off');
  assert.equal(auditText({ ...own, action: 'two_factor_new_app' }),
    'Hans Dampf moved two-factor login to a new authenticator app');
  assert.equal(auditText({ ...own, action: 'recovery_codes_renewed' }), 'Hans Dampf made new recovery codes');
});

test('a deleted account, without whose', () => {
  const deleted = { ...ENTRY, action: 'account_deleted' as const, user: null, detail: '' };
  assert.equal(auditText({ ...deleted, actor: 'Klara Himmel' }), 'Klara Himmel deleted an account');
  assert.equal(auditText({ ...deleted, actor: 'Deleted user', detail: 'own' }), 'Deleted user deleted their account');
});

test('a full backup', () => {
  assert.equal(auditText({ ...ENTRY, action: 'backup_made', user: null, detail: '' }), 'Pascal Turbo downloaded a full backup');
  assert.equal(auditText({ ...ENTRY, action: 'backup_restored', user: null, detail: '' }), 'Pascal Turbo restored a full backup');
  assert.equal(auditText({ ...ENTRY, action: 'backup_restored', user: null, detail: 'root login' }),
    'Pascal Turbo restored a full backup with its root login');
});

test('a reset of two-factor login', () => {
  assert.equal(auditText({ ...ENTRY, actor: 'Klara Himmel', action: 'two_factor_reset', detail: '' }),
    'Klara Himmel reset the two-factor login of Hans Dampf');
});
