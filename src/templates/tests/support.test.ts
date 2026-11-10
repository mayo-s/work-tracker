// Tests of the support page helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import type { MessageView } from '../ts/api.ts';
import { answerLink, describeChange, senderLabel } from '../ts/support.ts';

const MESSAGE: MessageView = {
  id: '0190a3c4-5d2e-7f1a-9b3c-000000000001', sent_at: '2026-11-09T09:00:00', name: 'Rainer Zufall',
  email: 'rainer.zufall@example.com', username: null, known: false, subject: 'Access & rights', text: 'May I join?',
  status: 'new', done_at: null, archived: false, changes: [],
};

test('the answer opens the mail program with address and subject', () => {
  assert.equal(answerLink(MESSAGE), 'mailto:rainer.zufall@example.com?subject=Re%3A%20Access%20%26%20rights');
});

test('the label tells whether a logged-in user sent it', () => {
  assert.deepEqual([senderLabel(MESSAGE), senderLabel({ ...MESSAGE, known: true })], ['Unknown user', 'Known user']);
});

test('a change shows the new status or the note', () => {
  const change = { at: '2026-11-09T10:00:00', actor: 'Klara Himmel' };
  assert.deepEqual([describeChange({ ...change, kind: 'status', detail: 'in_progress' }),
    describeChange({ ...change, kind: 'note', detail: 'Asked Hans' })], ['Status: In progress', 'Note: Asked Hans']);
});
