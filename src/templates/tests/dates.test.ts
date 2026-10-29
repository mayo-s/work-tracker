// Tests of the calendar helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  addDays, formatDate, formatDay, formatMonth, formatTimestamp, isoDate, isoMonth, isoWeek, isValidMonth, isValidWeek,
  mondayOf, shiftMonth, shiftWeek,
} from '../ts/dates.ts';

test('iso date of a local date', () => {
  assert.equal(isoDate(new Date(2026, 9, 28)), '2026-10-28');
});

test('adding days across months and years', () => {
  assert.equal(addDays('2026-10-28', 4), '2026-11-01');
  assert.equal(addDays('2026-12-31', 1), '2027-01-01');
  assert.equal(addDays('2024-03-01', -1), '2024-02-29');
});

test('iso weeks, including weeks belonging to the neighbouring year', () => {
  assert.equal(isoWeek('2026-10-28'), '2026-W44');
  assert.equal(isoWeek('2026-10-26'), '2026-W44');
  assert.equal(isoWeek('2026-11-01'), '2026-W44');
  assert.equal(isoWeek('2025-12-29'), '2026-W01');
  assert.equal(isoWeek('2021-01-03'), '2020-W53');
  assert.equal(isoWeek('2026-03-29'), '2026-W13'); // daylight saving time starts
});

test('monday of a week', () => {
  assert.equal(mondayOf('2026-W44'), '2026-10-26');
  assert.equal(mondayOf('2026-W01'), '2025-12-29');
  assert.equal(mondayOf('2020-W53'), '2020-12-28');
});

test('valid weeks', () => {
  assert.ok(isValidWeek('2026-W44'));
  assert.ok(isValidWeek('2020-W53'));
  assert.ok(isValidWeek('2026-W53'), '2026 starts on a Thursday, so it has 53 weeks');
  assert.ok(!isValidWeek('2025-W53'));
  assert.ok(!isValidWeek('2026-W00'));
  assert.ok(!isValidWeek('2026-44'));
});

test('shifting weeks across years', () => {
  assert.equal(shiftWeek('2026-W44', 1), '2026-W45');
  assert.equal(shiftWeek('2026-W01', -1), '2025-W52');
  assert.equal(shiftWeek('2026-W52', 1), '2026-W53');
  assert.equal(shiftWeek('2026-W53', 1), '2027-W01');
});

test('formatting dates', () => {
  assert.equal(formatDate('2026-10-28'), '28.10.2026');
  assert.equal(formatDay('2026-10-28', 'Wed'), 'Wed 28.10.');
});

test('months', () => {
  assert.equal(isoMonth('2026-10-28'), '2026-10');
  assert.ok(isValidMonth('2026-10'));
  assert.ok(!isValidMonth('2026-13'));
  assert.ok(!isValidMonth('2026-1'));
  assert.equal(shiftMonth('2026-12', 1), '2027-01');
  assert.equal(shiftMonth('2026-01', -1), '2025-12');
  assert.equal(shiftMonth('2026-10', 0), '2026-10');
  assert.equal(formatMonth('2026-10'), 'October 2026');
});

test('timestamps show date and minutes', () => {
  assert.equal(formatTimestamp('2026-10-29T08:05:12'), '29.10.2026 08:05');
});
