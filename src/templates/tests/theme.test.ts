// Tests of the color theme helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { applyTheme, shownTheme } from '../ts/theme.ts';

test('a chosen theme is set on the root element and shown; with system the system decides', () => {
  const root = { dataset: {} } as HTMLElement;
  applyTheme(root, 'dark');
  assert.equal(root.dataset.theme, 'dark');
  assert.equal(shownTheme(root, false), 'dark');
  applyTheme(root, 'system');
  assert.equal(root.dataset.theme, undefined);
  assert.deepEqual([shownTheme(root, true), shownTheme(root, false)], ['dark', 'light']);
});
