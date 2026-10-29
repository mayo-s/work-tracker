// Tests of the entry form helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import type { EntryView } from '../ts/api.ts';
import { entryFormValues, entryInput, type EntryFormValues } from '../ts/entry-editor.ts';

const TICKET: EntryView = {
  id: 7, kind: 'ticket', date: '2026-10-27', duration: '0:30', ticket_key: 'TNG-5882', service_id: 2, service: 'MSB',
  description: 'PR Review', coding: true, activity_type_id: null, activity_type: null, note: null, changed: false, flags: [],
};

function values(changes: Partial<EntryFormValues> = {}): EntryFormValues {
  return { ...entryFormValues(null), duration: '1:30', ...changes };
}

test('form values of a new entry', () => {
  assert.deepEqual(entryFormValues(null), {
    kind: 'ticket', duration: '', ticket_key: '', service_id: '', description: '', coding: false, activity_type_id: '', note: '',
  });
});

test('form values of a ticket entry', () => {
  assert.deepEqual(entryFormValues(TICKET), {
    kind: 'ticket', duration: '0:30', ticket_key: 'TNG-5882', service_id: '2', description: 'PR Review', coding: true,
    activity_type_id: '', note: '',
  });
});

test('form values of an activity entry', () => {
  const activity: EntryView = { ...TICKET, kind: 'activity', ticket_key: null, service_id: null, service: null, description: null,
    coding: false, activity_type_id: 1, activity_type: 'Tool Management', note: 'GCC' };
  const result = entryFormValues(activity);
  assert.equal(result.kind, 'activity');
  assert.equal(result.activity_type_id, '1');
  assert.equal(result.note, 'GCC');
});

test('ticket input: trimmed, upper-case key, service left out unless changed', () => {
  const input = entryInput(values({ ticket_key: ' tng-5882 ', description: ' PR Review ', coding: true, service_id: '2' }),
    '2026-10-27', false);
  assert.deepEqual(input, {
    kind: 'ticket', date: '2026-10-27', duration: '1:30', ticket_key: 'TNG-5882', description: 'PR Review', coding: true,
  });
});

test('ticket input with a changed service, also unassigning it', () => {
  assert.equal(entryInput(values({ ticket_key: 'TNG-5882', service_id: '4' }), '2026-10-27', true).service_id, 4);
  assert.equal(entryInput(values({ ticket_key: 'TNG-5882', service_id: '' }), '2026-10-27', true).service_id, null);
});

test('ticket input without ticket sends null, so the API explains what is missing', () => {
  assert.equal(entryInput(values(), '2026-10-27', false).ticket_key, null);
});

test('activity input', () => {
  assert.deepEqual(entryInput(values({ kind: 'activity', activity_type_id: '1', note: ' GCC ', ticket_key: 'X-1' }), '2026-10-28', true), {
    kind: 'activity', date: '2026-10-28', duration: '1:30', activity_type_id: 1, note: 'GCC',
  });
});
