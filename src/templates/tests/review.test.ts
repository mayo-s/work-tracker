// Tests of the review page helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import type { EntryView, ReviewEntry, TicketView } from '../ts/api.ts';
import {
  describeSplit, entryTexts, filterTickets, groupReview, reviewTotal, splitSuggestion,
} from '../ts/review.ts';

const TICKETS: TicketView[] = ['AGA-39', 'AGA-40', 'TNG-4950', 'TNG-5214'].map((key) => ({ key, service_id: null, service: null, entries: 1 }));

test('total of open review items', () => {
  assert.equal(reviewTotal({ tickets_without_service: 185, entries: 104, days: 3 }), 292);
  assert.equal(reviewTotal({ tickets_without_service: 0, entries: 0, days: 0 }), 0);
});

test('filtering tickets by part of the key, case-insensitive', () => {
  assert.deepEqual(filterTickets(TICKETS, 'aga').map((ticket) => ticket.key), ['AGA-39', 'AGA-40']);
  assert.deepEqual(filterTickets(TICKETS, ' TNG-49 ').map((ticket) => ticket.key), ['TNG-4950']);
  assert.equal(filterTickets(TICKETS, '').length, 4);
  assert.equal(filterTickets(TICKETS, 'KP').length, 0);
});

function reviewEntry(
  id: number, date: string, key: string | null, reasons: ReviewEntry['reasons'], flags: [number, string][] = [],
  split: ReviewEntry['split_on_import'] = [], suggestion: string[] = [],
): ReviewEntry {
  return {
    original: null,
    split_on_import: split,
    split_suggestion: suggestion,
    entry: {
      id, kind: 'ticket', date, duration: '1:00', ticket_key: key, changed: false,
      flags: flags.map(([flagId, detail]) => ({ id: flagId, reason: 'uncertain_ticket', detail })),
    } as ReviewEntry['entry'],
    reasons,
  };
}

test('guessed tickets are grouped by key, other reasons stay per entry', () => {
  const { guessed, others } = groupReview([
    reviewEntry(1, '2024-06-24', 'TNG-4057', ['uncertain_ticket'], [[11, '6,0 #4057 update appointment status']]),
    reviewEntry(2, '2024-06-25', 'TNG-4057', ['uncertain_ticket'], [[12, '6,0 #4057 adapt service']]),
    reviewEntry(3, '2024-07-04', null, ['no_ticket']),
    reviewEntry(4, '2024-07-05', 'TNG-4159', ['uncertain_ticket', 'zero_duration'], [[14, '#4159']]),
    reviewEntry(5, '2024-07-08', 'TNG-4057', ['uncertain_ticket'], [[15, '6,0 #4057 update appointment status']]),
  ]);
  assert.deepEqual(guessed.map((group) => [group.key, group.entries.map((entry) => entry.id), group.flagIds]), [
    ['TNG-4057', [1, 2, 5], [11, 12, 15]],
    ['TNG-4159', [4], [14]],
  ]);
  assert.deepEqual(guessed[0]?.originals, ['6,0 #4057 update appointment status', '6,0 #4057 adapt service']);
  assert.deepEqual(others.map((item) => [item.entry.id, item.reasons]), [[3, ['no_ticket']], [4, ['zero_duration']]]);
});

test('a split is offered when the API suggests one, starting with the guessed ticket', () => {
  const alias = '6,0 #4347 aka #1482 check permission';
  const { guessed } = groupReview([
    reviewEntry(1, '2024-07-01', 'TNG-4347', ['uncertain_ticket'], [[11, alias]], [], ['KP-1482', 'TNG-4347']),
    reviewEntry(2, '2024-07-02', 'TNG-4347', ['uncertain_ticket'], [[12, alias]], [], ['KP-1482', 'TNG-4347']),
    reviewEntry(3, '2024-07-03', 'TNG-4057', ['uncertain_ticket'], [[13, '6,0 #4057 update appointment status']]),
  ]);
  assert.deepEqual(guessed.map(splitSuggestion), [['TNG-4347', 'KP-1482'], null]);
});

test('the split of the import is kept per original line', () => {
  const line = '6,0 #4138, #4139 create meeting service';
  const split = [{ ticket_key: 'TNG-4138', duration: '3:00' }, { ticket_key: 'TNG-4139', duration: '3:00' }];
  const { guessed } = groupReview([
    reviewEntry(2, '2024-06-10', 'TNG-4138', ['uncertain_ticket'], [[21, line]], split),
    reviewEntry(7, '2024-06-18', 'TNG-4138', ['uncertain_ticket'], [[27, '3,0 #4138 add tests'], ]),
  ]);
  assert.deepEqual(guessed[0]?.splits, { [line]: split });
  assert.equal(describeSplit(split), 'TNG-4138 3:00 · TNG-4139 3:00');
});

test('descriptions of entries, each once ignoring case', () => {
  const entries = ['PR Review', '', 'pr review', 'Sprint planning', ' adapt tests '].map((description) => ({ description })) as
    EntryView[];
  assert.deepEqual(entryTexts(entries), ['PR Review', 'Sprint planning', 'adapt tests']);
});
