// Tests of the API client with a fake fetch; run with `npm test` (Node runs TypeScript directly).

import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

import { api, ApiError, errorMessage, fileName } from '../ts/api.ts';

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

  test('saving a day sends JSON', async () => {
    respond(200, { date: '2026-10-28' });
    await api.saveDay('2026-10-28', { start: '07:15', end: '16:00' });
    assert.equal(calls[0]?.headers['Content-Type'], 'application/json');
  });

  test('creating an entry returns the created entry', async () => {
    respond(201, { id: 'e7' });
    const entry = await api.createEntry({ date: '2026-10-28', activity_type_id: 'a1', duration: '1:30', ticket_key: 'TNG-5882' });
    assert.equal(entry.id, 'e7');
  });

  test('each call reaches its route', async () => {
    respond(200, {});
    await api.entries({ start: '2026-10-01', end: '2026-10-31' });
    await api.saveDay('2026-10-28', { start: '07:15', end: '16:00' });
    await api.renameTicket('TNG-2035', 'KP-2035');
    await api.ticket('a/b');
    await api.assignService(['AGA-39', 'AGA-40'], 's4');
    await api.setTicketService('AGA-39', null);
    await api.tickets(true);
    await api.monthReport('2026-10');
    await api.savePtoYear(2027, { allowance: 25 });
    await api.bookRange({ start: '2026-07-13', end: '2026-07-31', day_type: 'pto', preview: true });
    assert.deepEqual(calls.map((call) => [call.method, call.url, call.body]), [
      ['GET', '/api/entries?start=2026-10-01&end=2026-10-31', undefined],
      ['PUT', '/api/days/2026-10-28', { start: '07:15', end: '16:00' }],
      ['POST', '/api/tickets/TNG-2035/rename', { new_key: 'KP-2035' }],
      ['GET', '/api/tickets/a%2Fb', undefined],  // keys are encoded in paths
      ['POST', '/api/tickets/assign-service', { keys: ['AGA-39', 'AGA-40'], service_id: 's4' }],
      ['PUT', '/api/tickets/AGA-39', { service_id: null }],
      ['GET', '/api/tickets?without_service=true', undefined],
      ['GET', '/api/reports/months/2026-10', undefined],
      ['PUT', '/api/pto-years/2027', { allowance: 25 }],
      ['POST', '/api/days/range', { start: '2026-07-13', end: '2026-07-31', day_type: 'pto', preview: true }],
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

  test('validation errors join their messages, without pydantic\'s "Value error, " prefix', async () => {
    respond(422, [
      { loc: ['start'], msg: 'Value error, Value error, End 480 is before start 960', type: 'value_error' },
      { loc: ['end'], msg: 'Field required', type: 'missing' },
    ]);
    await assert.rejects(api.saveDay('2026-10-28', { start: '16:00', end: '08:00' }), {
      name: 'ApiError',
      message: 'End 480 is before start 960; Field required',
    });
  });

  test('message falls back to title or status', () => {
    assert.equal(errorMessage(409, { title: '409 Conflict' }), '409 Conflict');
    assert.equal(errorMessage(500, null), 'Request failed with status 500');
    assert.equal(errorMessage(422, []), 'Request failed with status 422');
  });
});

describe('files', () => {
  test('the backup comes as a file with its name', async () => {
    nextResponse = new Response(new Uint8Array([1, 2, 3]), {
      headers: { 'Content-Disposition': 'attachment; filename="work-tracker-backup-2026-11-03.wtbackup"' },
    });
    const file = await api.backup('a long backup passphrase');
    assert.deepEqual([calls[0]?.method, calls[0]?.url, calls[0]?.body], ['POST', '/api/admin/backup',
      { passphrase: 'a long backup passphrase' }]);
    assert.equal(file.name, 'work-tracker-backup-2026-11-03.wtbackup');
    assert.deepEqual([...new Uint8Array(await file.blob.arrayBuffer())], [1, 2, 3]);
  });

  test('a refused download is an ApiError', async () => {
    respond(403, { description: 'Only root may do this' });
    await assert.rejects(api.backup('a long backup passphrase'),
      (error) => error instanceof ApiError && error.status === 403 && error.message === 'Only root may do this');
  });

  test('a file without a name', () => {
    assert.equal(fileName(null), 'download');
  });
});
