// Tests of the contact page helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { contactProblems } from '../ts/contact.ts';

const MESSAGE = { name: 'Rainer Zufall', email: 'rainer.zufall@example.com', subject: 'Access', text: 'May I join?' };

test('a message needs a name, an e-mail address, a subject and a text', () => {
  assert.deepEqual(contactProblems(MESSAGE), []);
  assert.deepEqual(contactProblems({ ...MESSAGE, name: ' ', email: 'rainer', text: '' }), [
    { loc: ['name'], msg: 'Enter your name.' },
    { loc: ['email'], msg: 'Enter an e-mail address like name@example.com.' },
    { loc: ['text'], msg: 'Enter your message.' },
  ]);
});
