// Tests of the review page helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import type { ReviewEntry, TicketView } from '../ts/api.ts';
import { filterEntries, filterTickets, groupReview, reviewTotal } from '../ts/review.ts';

const TICKETS: TicketView[] = ['AGA-39', 'AGA-40', 'TNG-4950', 'TNG-5214'].map((key) => ({ key, service_id: null, service: null, entries: 1 }));

test('total of open review items', () => {
  assert.equal(reviewTotal({ tickets_without_service: 185, entries: 104 }), 289);
  assert.equal(reviewTotal({ tickets_without_service: 0, entries: 0 }), 0);
});

test('filtering tickets by part of the key, case-insensitive', () => {
  assert.deepEqual(filterTickets(TICKETS, 'aga').map((ticket) => ticket.key), ['AGA-39', 'AGA-40']);
  assert.deepEqual(filterTickets(TICKETS, ' TNG-49 ').map((ticket) => ticket.key), ['TNG-4950']);
  assert.equal(filterTickets(TICKETS, '').length, 4);
  assert.equal(filterTickets(TICKETS, 'KP').length, 0);
});

function reviewEntry(id: string, key: string | null, reasons: ReviewEntry['reasons'], description = ''): ReviewEntry {
  return { entry: { id, date: '2026-10-27', duration: '1:00', ticket_key: key, description } as ReviewEntry['entry'], reasons };
}

test('filtering entries by the start of the ticket key or part of the description, ignoring case', () => {
  const items = [reviewEntry('e1', 'TNG-4950', [], 'Investigation'), reviewEntry('e2', 'KP-1951', [], 'documentation')];
  assert.deepEqual(filterEntries(items, 'tng-49').map((item) => item.entry.id), ['e1']);
  assert.deepEqual(filterEntries(items, 'DOC').map((item) => item.entry.id), ['e2']);
  assert.deepEqual(filterEntries(items, '1951').map((item) => item.entry.id), []);  // the key from its start only
  assert.equal(filterEntries(items, '').length, 2);
});

test('entries without activity type are chosen together, the others stay per entry', () => {
  const { untyped, others } = groupReview([
    reviewEntry('e1', 'TNG-4200', ['no_activity_type', 'zero_duration']),
    reviewEntry('e2', null, ['no_ticket']),
  ]);
  assert.deepEqual([untyped.map((item) => item.entry.id), others.map((item) => item.entry.id)], [['e1'], ['e2']]);
});
