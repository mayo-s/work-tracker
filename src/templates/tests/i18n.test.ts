// Tests of the translations and the language switch's names; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { loadCatalog, t, tn } from '../ts/i18n.ts';
import { languageName } from '../ts/language.ts';

const GERMAN = { Week: 'Woche', '{count} open team invitation': '{count} offene Team-Einladung',
  '{count} open team invitations': '{count} offene Team-Einladungen' };

function serving(body: unknown, status = 200): typeof fetch {
  return async (input) => {
    assert.equal(String(input), '/static/locales/de.json');
    return Response.json(body, { status });
  };
}

test('a loaded catalog translates, fills in placeholders and keeps unknown texts', async () => {
  await loadCatalog('de', serving(GERMAN));
  assert.deepEqual([t('Week'), tn(1, '{count} open team invitation', '{count} open team invitations'),
    tn(3, '{count} open team invitation', '{count} open team invitations'), t('Deleted {username}', { username: 'hans' })],
  ['Woche', '1 offene Team-Einladung', '3 offene Team-Einladungen', 'Deleted hans']);
});

test('English needs no catalog, and without one the texts stay English', async () => {
  await loadCatalog('en', () => assert.fail('nothing to load'));
  assert.equal(t('Week'), 'Week');
  await loadCatalog('de', serving({}, 404));
  assert.equal(t('Week'), 'Week');
  await loadCatalog('de', () => Promise.reject(new Error('offline')));
  assert.equal(t('Week'), 'Week');
});

test('each language is named in its own language', () => {
  assert.deepEqual(['de', 'en', 'es', 'fr'].map(languageName), ['Deutsch', 'English', 'Español', 'fr']);
});
