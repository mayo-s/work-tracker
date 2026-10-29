// Tests of the entry history lines; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import type { ChangeView } from '../ts/api.ts';
import { describeChanges, formatTimestamp, formatValue } from '../ts/history.ts';

const ACTIVITIES = new Map([[1, 'Tool Management']]);

function change(action: ChangeView['action'], changes: ChangeView['changes']): ChangeView {
  return { id: 1, changed_at: '2026-10-28T16:47:11', action, changes, detail: '' };
}

test('values: durations, dates, activity names, booleans and empty values', () => {
  assert.equal(formatValue('duration', 90, ACTIVITIES), '1:30');
  assert.equal(formatValue('date', '2026-10-28', ACTIVITIES), '28.10.2026');
  assert.equal(formatValue('activity_type_id', 1, ACTIVITIES), 'Tool Management');
  assert.equal(formatValue('activity_type_id', 9, ACTIVITIES), '#9');
  assert.equal(formatValue('coding', true, ACTIVITIES), 'yes');
  assert.equal(formatValue('description', '', ACTIVITIES), '—');
  assert.equal(formatValue('ticket_key', null, ACTIVITIES), '—');
});

test('changes show old and new value', () => {
  const lines = describeChanges(change('updated', { duration: [30, 60], ticket_key: ['TNG-2035', 'KP-2035'] }), ACTIVITIES);
  assert.deepEqual(lines, ['duration: 0:30 → 1:00', 'ticket: TNG-2035 → KP-2035']);
});

test('created, imported and deleted show only the value', () => {
  assert.deepEqual(describeChanges(change('imported', { duration: [null, 180] }), ACTIVITIES), ['duration: 3:00']);
  assert.deepEqual(describeChanges(change('deleted', { note: ['GCC', null] }), ACTIVITIES), ['note: GCC']);
});

test('timestamps', () => {
  assert.equal(formatTimestamp('2026-10-28T16:47:11'), '28.10.2026 16:47');
});
