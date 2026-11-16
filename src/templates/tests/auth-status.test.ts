// Tests of the login status a page comes with; run with `npm test`. In a file of its own: the API client remembers
// that the page has changed something.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { api } from '../ts/api.ts';

const KLARA = { enabled: true, has_users: true, user: { id: 'u1', first_name: 'Klara' } };

test('the login status comes with the page, and from the API once the page has changed something', async () => {
  const calls: string[] = [];
  globalThis.fetch = async (input: string | URL | Request, init?: RequestInit) => {
    calls.push(`${init?.method} ${String(input)}`);
    return Response.json({ enabled: true, has_users: true, user: null });
  };
  const page = { querySelector: (selector: string) => (selector === '#auth-status' ? { textContent: JSON.stringify(KLARA) } : null) };
  Object.assign(globalThis, { document: page });

  assert.equal((await api.authStatus()).user?.first_name, 'Klara');
  assert.deepEqual(calls, []);

  await api.logout();
  assert.equal((await api.authStatus()).user, null);
  assert.deepEqual(calls, ['POST /api/auth/logout', 'GET /api/auth/status']);
});
