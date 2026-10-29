// Tests of the account helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { accountError, emptyAccount, passwordError, profileInput, safeNext } from '../ts/account.ts';

const RAINER = {
  username: 'rainer', email: 'rainer.zufall@example.com', first_name: 'Rainer', last_name: '',
  password: 'correct horse battery 9!',
  repeat: 'correct horse battery 9!',
};

test('account values are checked like the API does', () => {
  assert.equal(accountError(RAINER, true), null);
  assert.equal(accountError(emptyAccount(), false), 'Enter your first name.');
  assert.equal(accountError({ ...RAINER, username: 'm' }, false),
    'The username needs 3 to 30 letters, digits, dots, dashes or underscores.');
  assert.equal(accountError({ ...RAINER, email: 'rainer' }, false), 'Enter a valid e-mail address.');
  assert.equal(accountError({ ...RAINER, password: 'short' }, false), null);
});

test('passwords need 12 characters with letters, digits and a special character, twice the same', () => {
  assert.equal(passwordError('correct horse battery 9!', 'correct horse battery 9!'), null);
  assert.equal(passwordError('ÄÖÜäöüß 1234#', 'ÄÖÜäöüß 1234#'), null);
  assert.equal(passwordError('short', 'short'), 'The password needs at least 12 characters.');
  for (const weak of ['only letters and spaces', 'letters and 1234 digits', '1234567890!?', 'no-digits-but-special']) {
    assert.equal(passwordError(weak, weak), 'The password needs letters, digits and a special character, e.g. ! ? # or %.');
  }
  assert.equal(passwordError('correct horse battery 9!', 'correct horse batterY'), 'The two passwords differ.');
});

test('profile input is trimmed', () => {
  assert.deepEqual(profileInput({ ...RAINER, username: ' rainer ', last_name: ' Z. ' }),
    { username: 'rainer', email: 'rainer.zufall@example.com', first_name: 'Rainer', last_name: 'Z.' });
});

test('after logging in, only paths of this app', () => {
  assert.equal(safeNext('/year?year=2025'), '/year?year=2025');
  assert.equal(safeNext(null), '/');
  assert.equal(safeNext('https://example.com/'), '/');
  assert.equal(safeNext('//example.com/'), '/');
});
