// Tests of the review page helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import type { ReviewEntry, TicketView } from '../ts/api.ts';
import {
  describeSplit, filterTickets, groupReview, mentionedTickets, REASON_LABELS, reviewTotal, splitSuggestion, weekLink, type GuessedTicket,
} from '../ts/review.ts';

const TICKETS: TicketView[] = ['AGA-39', 'AGA-40', 'TNG-4950', 'TNG-5214'].map((key) => ({ key, service_id: null, service: null, entries: 1 }));

test('links into the week view of a date', () => {
  assert.equal(weekLink('2024-10-31', 'entry=129'), '/?week=2024-W44&entry=129');
  assert.equal(weekLink('2025-12-06', 'edit=2025-12-06'), '/?week=2025-W49&edit=2025-12-06');
  assert.equal(weekLink('2025-12-29', 'entry=1'), '/?week=2026-W01&entry=1');
});

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

test('every review reason has a label', () => {
  assert.deepEqual(Object.keys(REASON_LABELS).sort(), ['no_ticket', 'uncertain_ticket', 'zero_duration']);
});

function reviewEntry(
  id: number, date: string, key: string | null, reasons: ReviewEntry['reasons'], flags: [number, string][] = [],
  split: ReviewEntry['split_on_import'] = [],
): ReviewEntry {
  return {
    split_on_import: split,
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

test('tickets mentioned in a spreadsheet line, mapped like the import', () => {
  assert.deepEqual(mentionedTickets('6,0 #4347 aka #1482 check permission'), ['TNG-4347', 'KP-1482']);
  assert.deepEqual(mentionedTickets('2,0 #4347/#1482 Logging'), ['TNG-4347', 'KP-1482']);
  assert.deepEqual(mentionedTickets('1,0 TNG-2035ff PR and deployment'), ['TNG-2035']);
  assert.deepEqual(mentionedTickets('1,5 #KP-1494 Discuss, TNG 5212 and # 4251'), ['KP-1494', 'TNG-5212', 'TNG-4251']);
});

function group(key: string, originals: string[]): GuessedTicket {
  return { key, entries: [], originals, flagIds: [], splits: {} };
}

test('split is offered for aliases and "ff", not for lines the import already split', () => {
  assert.deepEqual(splitSuggestion(group('TNG-4347', ['6,0 #4347 aka #1482 check permission'])), ['TNG-4347', 'KP-1482']);
  assert.deepEqual(splitSuggestion(group('TNG-4347', ['2,0 #4347/#1482 Logging'])), ['TNG-4347', 'KP-1482']);
  assert.deepEqual(splitSuggestion(group('TNG-2035', ['1,0 TNG-2035ff PR and deployment'])), ['TNG-2035']);
  assert.equal(splitSuggestion(group('TNG-4138', ['6,0 #4138, #4139 create meeting service'])), null);
  assert.equal(splitSuggestion(group('TNG-4057', ['6,0 #4057 update appointment status'])), null);
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
