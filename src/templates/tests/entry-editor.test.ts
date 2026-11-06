// Tests of the entry form helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import type { ActivityType, EntryView } from '../ts/api.ts';
import { entryForm, entryFormValues, entryInput, entryProblem, type EntryFormValues } from '../ts/entry-editor.ts';

const CODING: ActivityType = { id: 'a1', name: 'Coding', ticket_required: true };
const MEETING: ActivityType = { id: 'a2', name: 'Meeting', ticket_required: false };
const TYPES = [MEETING, CODING];
const REVIEW: EntryView = {
  id: 'e7', date: '2026-10-27', duration: '0:30', activity_type_id: 'a1', activity_type: 'Coding', ticket_required: true,
  ticket_key: 'TNG-5882', service_id: 's2', service: 'MSB', description: 'PR Review', changed: false, flags: [],
};

function values(changes: Partial<EntryFormValues> = {}): EntryFormValues {
  return { ...entryFormValues(null), activity_type_id: 'a1', duration: '1:30', ...changes };
}

test('ticket and service per way of working; types that require a ticket only with them', () => {
  assert.deepEqual(entryForm('tickets', null, TYPES), { ticket: true, activityTypes: TYPES });
  assert.deepEqual(entryForm('activities', null, TYPES), { ticket: false, activityTypes: [MEETING] });
  assert.deepEqual(entryForm('activities', REVIEW, TYPES), { ticket: true, activityTypes: TYPES });  // keeps its ticket
});

test('a new entry starts with Coding where tickets are entered; an entry with its values', () => {
  assert.equal(entryFormValues(null, TYPES, true).activity_type_id, 'a1');
  assert.equal(entryFormValues(null, [MEETING], false).activity_type_id, '');
  assert.deepEqual(entryFormValues(REVIEW), {
    activity_type_id: 'a1', duration: '0:30', ticket_key: 'TNG-5882', service_id: 's2', description: 'PR Review',
  });
});

test('an activity type is chosen, and the ticket it requires is entered', () => {
  assert.deepEqual(entryProblem(values({ activity_type_id: '' }), TYPES), ['activity_type_id', 'Choose an activity type.']);
  assert.deepEqual(entryProblem(values({ ticket_key: ' ' }), TYPES), ['ticket_key', 'Coding needs a ticket.']);
  assert.equal(entryProblem(values({ activity_type_id: 'a2' }), TYPES), null);
});

test('input: trimmed, upper-case key, the service only with a ticket and when changed', () => {
  assert.deepEqual(entryInput(values({ ticket_key: ' tng-5882 ', description: ' PR Review ', service_id: 's2' }),
    '2026-10-27', false), {
    date: '2026-10-27', activity_type_id: 'a1', duration: '1:30', ticket_key: 'TNG-5882', description: 'PR Review',
  });
  assert.equal(entryInput(values({ ticket_key: 'TNG-5882', service_id: '' }), '2026-10-27', true).service_id, null);
  assert.equal(entryInput(values({ activity_type_id: 'a2', service_id: 's2' }), '2026-10-28', true).service_id, undefined);
});
