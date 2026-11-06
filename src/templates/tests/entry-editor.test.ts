// Tests of the entry form helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import type { EntryView } from '../ts/api.ts';
import { entryForm, entryFormValues, entryInput, type EntryFormValues } from '../ts/entry-editor.ts';

const TICKET: EntryView = {
  id: 'e7', kind: 'ticket', date: '2026-10-27', duration: '0:30', ticket_key: 'TNG-5882', service_id: 's2', service: 'MSB',
  description: 'PR Review', coding: true, activity_type_id: null, activity_type: null, note: null, changed: false, flags: [],
};

function values(changes: Partial<EntryFormValues> = {}): EntryFormValues {
  return { ...entryFormValues(null), duration: '1:30', ...changes };
}

test('form values of a new, a ticket and an activity entry', () => {
  assert.deepEqual(entryFormValues(null), {
    kind: 'ticket', duration: '', ticket_key: '', service_id: '', description: '', coding: false, activity_type_id: '', note: '',
  });
  assert.deepEqual(entryFormValues(TICKET), {
    kind: 'ticket', duration: '0:30', ticket_key: 'TNG-5882', service_id: 's2', description: 'PR Review', coding: true,
    activity_type_id: '', note: '',
  });
  const activity: EntryView = { ...TICKET, kind: 'activity', ticket_key: null, service_id: null, service: null, description: null,
    coding: false, activity_type_id: 'a1', activity_type: 'Tool Management', note: 'GCC' };
  const result = entryFormValues(activity);
  assert.deepEqual([result.kind, result.activity_type_id, result.note], ['activity', 'a1', 'GCC']);
});

test('the form per way of working; an entry it does not record opens in the full form', () => {
  const activity: EntryView = { ...TICKET, kind: 'activity', coding: false };
  assert.deepEqual(entryForm('developer', null), { choice: true, coding: true, kind: 'ticket' });
  assert.deepEqual(entryForm('tickets', null), { choice: true, coding: false, kind: 'ticket' });
  assert.deepEqual(entryForm('tickets', { ...TICKET, coding: false }), { choice: true, coding: false, kind: 'ticket' });
  assert.deepEqual(entryForm('tickets', TICKET), { choice: true, coding: true, kind: 'ticket' });
  assert.deepEqual(entryForm('activities', null), { choice: false, coding: false, kind: 'activity' });
  assert.deepEqual(entryForm('activities', activity), { choice: false, coding: false, kind: 'activity' });
  assert.deepEqual(entryForm('activities', TICKET), { choice: true, coding: true, kind: 'activity' });
  assert.deepEqual(entryForm('times', activity), { choice: true, coding: true, kind: 'ticket' });
});

test('a new entry starts with the kind of the way of working', () => {
  assert.equal(entryFormValues(null, 'activity').kind, 'activity');
});

test('ticket input: trimmed, upper-case key, service left out unless changed', () => {
  const input = entryInput(values({ ticket_key: ' tng-5882 ', description: ' PR Review ', coding: true, service_id: '2' }),
    '2026-10-27', false);
  assert.deepEqual(input, {
    kind: 'ticket', date: '2026-10-27', duration: '1:30', ticket_key: 'TNG-5882', description: 'PR Review', coding: true,
  });
});

test('ticket input with a changed service, also unassigning it', () => {
  assert.equal(entryInput(values({ ticket_key: 'TNG-5882', service_id: 's4' }), '2026-10-27', true).service_id, 's4');
  assert.equal(entryInput(values({ ticket_key: 'TNG-5882', service_id: '' }), '2026-10-27', true).service_id, null);
});

test('ticket input without ticket sends null, so the API explains what is missing', () => {
  assert.equal(entryInput(values(), '2026-10-27', false).ticket_key, null);
});

test('activity input', () => {
  assert.deepEqual(entryInput(values({ kind: 'activity', activity_type_id: 'a1', note: ' GCC ', ticket_key: 'X-1' }), '2026-10-28', true), {
    kind: 'activity', date: '2026-10-28', duration: '1:30', activity_type_id: 'a1', note: 'GCC',
  });
});
