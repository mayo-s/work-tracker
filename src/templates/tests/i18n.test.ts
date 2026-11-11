// Tests of the translations and the language switch's names; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { decimal, listOf, loadCatalog, t, tn } from '../ts/i18n.ts';
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

test('day counts and lists as the language writes them; a count may come formatted', async () => {
  await loadCatalog('de', serving({ 'uses {count} PTO days': 'braucht {count} Urlaubstage' }));
  assert.deepEqual([decimal(2.5), decimal(17), listOf(['Do 24.12.', 'Do 31.12.']),
    tn(14.5, 'uses {count} PTO day', 'uses {count} PTO days', { count: decimal(14.5) })],
  ['2,5', '17', 'Do 24.12. und Do 31.12.', 'braucht 14,5 Urlaubstage']);
  await loadCatalog('en');
  assert.deepEqual([decimal(2.5), listOf(['A', 'B'])], ['2.5', 'A and B']);
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
