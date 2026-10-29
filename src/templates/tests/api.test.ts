// Tests of the API client with a fake fetch; run with `npm test` (Node runs TypeScript directly).

import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

import { api, ApiError, errorMessage } from '../ts/api.ts';

type Call = { url: string; method: string; body: unknown; headers: Record<string, string> };

let calls: Call[] = [];
let nextResponse: Response = new Response('null');
const realFetch = globalThis.fetch;

function respond(status: number, body?: unknown): void {
  nextResponse = body === undefined ? new Response(null, { status }) : Response.json(body, { status });
}

beforeEach(() => {
  calls = [];
  respond(200, []);
  globalThis.fetch = async (input: string | URL | Request, init?: RequestInit) => {
    calls.push({
      url: String(input),
      method: init?.method ?? 'GET',
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
      headers: (init?.headers ?? {}) as Record<string, string>,
    });
    return nextResponse;
  };
});

afterEach(() => {
  globalThis.fetch = realFetch;
});

describe('requests', () => {
  test('days of a week', async () => {
    await api.days({ week: '2026-W44' });
    assert.deepEqual(calls[0], {
      url: '/api/days?week=2026-W44', method: 'GET', body: undefined, headers: { Accept: 'application/json' },
    });
  });

  test('entries of a date range', async () => {
    await api.entries({ start: '2026-10-01', end: '2026-10-31' });
    assert.equal(calls[0]?.url, '/api/entries?start=2026-10-01&end=2026-10-31');
  });

  test('saving a day sends JSON', async () => {
    respond(200, { date: '2026-10-28' });
    await api.saveDay('2026-10-28', { start: '07:15', end: '16:00' });
    assert.equal(calls[0]?.method, 'PUT');
    assert.equal(calls[0]?.url, '/api/days/2026-10-28');
    assert.deepEqual(calls[0]?.body, { start: '07:15', end: '16:00' });
    assert.equal(calls[0]?.headers['Content-Type'], 'application/json');
  });

  test('creating an entry returns the created entry', async () => {
    respond(201, { id: 7, kind: 'ticket' });
    const entry = await api.createEntry({ kind: 'ticket', date: '2026-10-28', duration: '1:30', ticket_key: 'TNG-5882' });
    assert.equal(entry.id, 7);
    assert.equal(calls[0]?.method, 'POST');
  });

  test('ticket keys are encoded in paths', async () => {
    respond(200, {});
    await api.renameTicket('TNG-2035', 'KP-2035');
    await api.ticket('a/b');
    assert.equal(calls[0]?.url, '/api/tickets/TNG-2035/rename');
    assert.deepEqual(calls[0]?.body, { new_key: 'KP-2035' });
    assert.equal(calls[1]?.url, '/api/tickets/a%2Fb');
  });

  test('assigning and unassigning services', async () => {
    respond(200, {});
    await api.assignService(['AGA-39', 'AGA-40'], 4);
    await api.setTicketService('AGA-39', null);
    assert.deepEqual(calls[0]?.body, { keys: ['AGA-39', 'AGA-40'], service_id: 4 });
    assert.deepEqual(calls[1]?.body, { service_id: null });
  });

  test('tickets without service', async () => {
    await api.tickets(true);
    await api.tickets();
    assert.deepEqual(calls.map((call) => call.url), ['/api/tickets?without_service=true', '/api/tickets']);
  });

  test('reports', async () => {
    respond(200, {});
    await api.weekReport('2026-W44');
    await api.monthReport('2026-10');
    await api.yearReport(2026);
    assert.deepEqual(calls.map((call) => call.url), [
      '/api/reports/weeks/2026-W44', '/api/reports/months/2026-10', '/api/reports/years/2026',
    ]);
  });

  test('settings and PTO years', async () => {
    respond(200, {});
    await api.saveSettings({ balance_start: '2027-03-01', opening_balance: '-1:45' });
    await api.savePtoYear(2027, { allowance: 25 });
    assert.deepEqual(calls.map((call) => [call.method, call.url, call.body]), [
      ['PUT', '/api/settings', { balance_start: '2027-03-01', opening_balance: '-1:45' }],
      ['PUT', '/api/pto-years/2027', { allowance: 25 }],
    ]);
  });

  test('204 No Content resolves to undefined', async () => {
    respond(204);
    assert.equal(await api.deleteEntry(7), undefined);
    assert.equal(calls[0]?.method, 'DELETE');
  });
});

describe('errors', () => {
  test('not found carries status and description', async () => {
    respond(404, { title: '404 Not Found', description: 'No entry with id 404' });
    await assert.rejects(api.entry(404), (error: unknown) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 404);
      assert.equal(error.message, 'No entry with id 404');
      return true;
    });
  });

  test('validation errors join their messages', async () => {
    respond(422, [{ loc: ['start'], msg: 'Value error, End 480 is before start 960', type: 'value_error' }]);
    await assert.rejects(api.saveDay('2026-10-28', { start: '16:00', end: '08:00' }), {
      name: 'ApiError',
      message: 'Value error, End 480 is before start 960',
    });
  });

  test('message falls back to title or status', () => {
    assert.equal(errorMessage(409, { title: '409 Conflict' }), '409 Conflict');
    assert.equal(errorMessage(500, null), 'Request failed with status 500');
    assert.equal(errorMessage(422, []), 'Request failed with status 422');
  });
});
