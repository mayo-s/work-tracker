// Tests of the entry details dialog helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import type { DayView, EntryView } from '../ts/api.ts';
import { describeDay, entryFields } from '../ts/entry-details.ts';

function day(changes: Partial<DayView> = {}): DayView {
  return {
    date: '2026-03-02', weekday: 'Mon', day_type: 'work', automatic: true, holiday: null, recorded: true, start: '08:00',
    end: '16:30', break_time: '0:30', break_default: true, worked: '8:00', target: '8:00', overtime: '0:00', pto_days: 0,
    work_day: true, note: '', ...changes,
  };
}

test('the day of an entry with its times, its day type unless work', () => {
  assert.equal(describeDay(day()), 'Mon 02.03.2026 · 08:00–16:30, break 0:30, worked 8:00');
  assert.equal(describeDay(day({ date: '2025-12-24', weekday: 'Wed', day_type: 'company_half_day', holiday: 'Christmas Eve',
    start: null, end: null })), 'Wed 24.12.2025 · Christmas Eve · no times');
  assert.equal(describeDay(day({ day_type: 'pto_half', start: '08:00', end: '12:00', break_time: '0:00', worked: '4:00' })),
    'Mon 02.03.2026 · PTO ½ · 08:00–12:00, break 0:00, worked 4:00');
});

test('the fields of an entry; a missing ticket only where its activity type requires one', () => {
  const review = { duration: '6:00', activity_type: 'Coding', ticket_required: true, ticket_key: null, service: null,
    description: 'PR reviews' };
  assert.deepEqual(entryFields(review as EntryView), [
    ['Duration', '6:00'], ['Activity', 'Coding'], ['Ticket', 'No ticket'], ['Service', '—'], ['Description', 'PR reviews']]);
  const meeting = { ...review, activity_type: 'Meeting', ticket_required: false, description: '' };
  assert.deepEqual(entryFields(meeting as EntryView).slice(1), [
    ['Activity', 'Meeting'], ['Ticket', '—'], ['Service', '—'], ['Description', '—']]);
});
