// Tests of the component gallery helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { snippet } from '../ts/gallery.ts';

test('snippet removes the common indentation and surrounding blank lines', () => {
  const html = '\n            <span class="badge">PTO</span>\n            <div>\n              <b>x</b>\n            </div>\n          ';
  assert.equal(snippet(html), '<span class="badge">PTO</span>\n<div>\n  <b>x</b>\n</div>');
  assert.equal(snippet('<button type="button">Cancel</button>'), '<button type="button">Cancel</button>');
  assert.equal(snippet('   \n  '), '');
});
