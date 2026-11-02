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
