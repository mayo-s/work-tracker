// Tests of the shared form helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { cleanMessage, fieldErrors } from '../ts/forms.ts';

test('messages without the pydantic prefix', () => {
  assert.equal(cleanMessage('Value error, End 08:00 is before start 16:00'), 'End 08:00 is before start 16:00');
  assert.equal(cleanMessage('Value error, Value error, x'), 'x');
  assert.equal(cleanMessage('Field required'), 'Field required');
});

test('validation errors by field and general ones', () => {
  const errors = fieldErrors([
    { loc: ['start'], msg: "Value error, Invalid time '25:00', out of range" },
    { loc: [], msg: 'Value error, End 08:00 is before start 16:00' },
    { loc: ['unknown'], msg: 'Extra inputs are not permitted' },
  ], ['day_type', 'start', 'end', 'break_time', 'note']);
  assert.deepEqual(errors.fields, { start: "Invalid time '25:00', out of range" });
  assert.deepEqual(errors.general, ['End 08:00 is before start 16:00', 'Extra inputs are not permitted']);
});

test('validation errors of an unexpected body', () => {
  assert.deepEqual(fieldErrors({ title: '409 Conflict' }, ['start']), { fields: {}, general: [] });
  assert.deepEqual(fieldErrors(null, ['start']), { fields: {}, general: [] });
});
