// Tests of the services and activity types helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import type { TicketView } from '../ts/api.ts';
import { deleteServiceQuestion, ticketCounts } from '../ts/lists.ts';

function ticket(key: string, serviceId: number | null): TicketView {
  return { key, service_id: serviceId, service: null, entries: 1 };
}

test('tickets per service, without unassigned tickets', () => {
  const counts = ticketCounts([ticket('TNG-1', 2), ticket('TNG-2', 2), ticket('KP-3', 5), ticket('AGA-4', null)]);
  assert.deepEqual([...counts], [[2, 2], [5, 1]]);
});

test('delete question names the tickets that lose their service', () => {
  assert.equal(deleteServiceQuestion('MSB', 12), 'Delete MSB? 12 tickets lose their service and show up in the review.');
  assert.equal(deleteServiceQuestion('MSB', 1), 'Delete MSB? 1 ticket loses its service and shows up in the review.');
  assert.equal(deleteServiceQuestion('TTS', 0), 'Delete TTS? No ticket uses it.');
});
