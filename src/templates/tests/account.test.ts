// Tests of the account helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { accountError, emptyAccount, passwordError, profileInput, safeNext } from '../ts/account.ts';

const MARIO = {
  username: 'mario', email: 'mario@example.com', first_name: 'Mario', last_name: '', password: 'correct horse battery',
  repeat: 'correct horse battery',
};

test('account values are checked like the API does', () => {
  assert.equal(accountError(MARIO, true), null);
  assert.equal(accountError(emptyAccount(), false), 'Enter your first name.');
  assert.equal(accountError({ ...MARIO, username: 'm' }, false),
    'The username needs 3 to 30 letters, digits, dots, dashes or underscores.');
  assert.equal(accountError({ ...MARIO, email: 'mario' }, false), 'Enter a valid e-mail address.');
  assert.equal(accountError({ ...MARIO, password: 'short' }, false), null);
});

test('passwords need 12 characters, twice the same', () => {
  assert.equal(passwordError('correct horse battery', 'correct horse battery'), null);
  assert.equal(passwordError('short', 'short'), 'The password needs at least 12 characters.');
  assert.equal(passwordError('correct horse battery', 'correct horse batterY'), 'The two passwords differ.');
});

test('profile input is trimmed', () => {
  assert.deepEqual(profileInput({ ...MARIO, username: ' mario ', last_name: ' S. ' }),
    { username: 'mario', email: 'mario@example.com', first_name: 'Mario', last_name: 'S.' });
});

test('after logging in, only paths of this app', () => {
  assert.equal(safeNext('/year?year=2025'), '/year?year=2025');
  assert.equal(safeNext(null), '/');
  assert.equal(safeNext('https://example.com/'), '/');
  assert.equal(safeNext('//example.com/'), '/');
});
