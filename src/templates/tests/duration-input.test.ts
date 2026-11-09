// Tests of the duration fields: the formats read and the limits; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { breakRules } from '../ts/day-editor.ts';
import { checkDuration, clockMinutes, parseDuration } from '../ts/duration-input.ts';
import { entryRules } from '../ts/entry-editor.ts';

test('the formats the API reads', () => {
  const read: [string, number][] = [
    ['1:30', 90], ['1,5', 90], ['2', 120], ['1h30', 90], ['1.5h', 90], ['1 H 30 Min', 90], ['45M', 45],
  ];
  for (const [text, minutes] of read) {
    assert.equal(parseDuration(text)?.minutes, minutes, text);
  }
  for (const text of ['', '1:5', '1:60', '1.01', '1h60m', '1.5h30m', 'abc', '-1:30']) {
    assert.equal(parseDuration(text), null, text);
  }
});

test('plain numbers are marked, signed durations only where allowed', () => {
  assert.deepEqual(parseDuration('90'), { minutes: 5400, bare: true });
  assert.deepEqual(parseDuration('90m'), { minutes: 90, bare: false });
  assert.deepEqual(parseDuration('-1.5', true), { minutes: -90, bare: true });
});

test('an entry fits the rest of its day, in any minutes', () => {
  const rules = entryRules('08:00');
  assert.deepEqual(checkDuration('1.5', rules), { kind: 'ok', minutes: 90 });
  assert.deepEqual(checkDuration('90', rules), { kind: 'minutes', hours: '90', minutes: 90 });
  assert.deepEqual(checkDuration('17h', rules), { kind: 'over', limit: 960 });
  assert.deepEqual(checkDuration('1.1', rules), { kind: 'ok', minutes: 66 });
  assert.deepEqual(checkDuration('', rules), { kind: 'empty' });
  assert.deepEqual(checkDuration('soon', rules), { kind: 'invalid' });
  assert.equal(entryRules(null).limit, 24 * 60);
});

test('a break fits the day from start to end, in any minutes', () => {
  const rules = breakRules({ day_type: '', start: '08:00', end: '16:30', break_time: '', note: '' });
  assert.deepEqual(rules, { limit: 510 });
  assert.deepEqual(checkDuration('30', rules), { kind: 'minutes', hours: '30', minutes: 30 });
  assert.deepEqual(checkDuration('0:40', rules), { kind: 'ok', minutes: 40 });
  assert.deepEqual(breakRules({ day_type: '', start: '', end: '', break_time: '', note: '' }), {});
});

test('clock times of the day form', () => {
  assert.equal(clockMinutes('08:15'), 495);
  assert.equal(clockMinutes('24:00'), null);
});
