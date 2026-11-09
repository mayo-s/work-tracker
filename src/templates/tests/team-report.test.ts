// Tests of the team report helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { chosenTeam, csvHref, exportFileName, memberHref, otherKind, periodFromSearch, reportHref, reportTeams } from '../ts/team-report.ts';

const TODAY = '2026-11-09';
const OWN = { team: { id: 't1', name: 'Platform', team_role: 'team_admin' } } as Parameters<typeof reportTeams>[0];
const AUDITS = [{ team_id: 't2', team: 'Sales' }];

test('the period from the address, otherwise the current month', () => {
  assert.deepEqual(periodFromSearch('?month=2026-10', TODAY), { kind: 'month', month: '2026-10' });
  assert.deepEqual(periodFromSearch('?year=2025', TODAY), { kind: 'year', year: 2025 });
  assert.deepEqual(periodFromSearch('', TODAY), { kind: 'month', month: '2026-11' });
});

test('the address keeps the team and the period', () => {
  assert.equal(reportHref('t1', { kind: 'month', month: '2026-10' }), '/team/report?team=t1&month=2026-10');
  assert.equal(reportHref(null, { kind: 'year', year: 2026 }), '/team/report?year=2026');
});

test('the CSV file of the same team and period', () => {
  assert.equal(csvHref('t1', { kind: 'month', month: '2026-10' }), '/api/teams/t1/report.csv?month=2026-10');
  assert.equal(csvHref('t1', { kind: 'year', year: 2026 }), '/api/teams/t1/report.csv?year=2026');
});

test('the file name holds the time of the export and the team, as the CSV', () => {
  const now = new Date(2026, 10, 9, 14, 7);
  assert.equal(exportFileName('Platform', now), '20261109_1407_team_report_Platform');
  assert.equal(exportFileName('Büro Süd', now), '20261109_1407_team_report_Büro_Süd');
  assert.equal(exportFileName('"a/b"\r\n', now), '20261109_1407_team_report_a_b');
});

test('switching between month and year stays at the same time', () => {
  assert.deepEqual(otherKind({ kind: 'month', month: '2025-03' }, TODAY), { kind: 'year', year: 2025 });
  assert.deepEqual(otherKind({ kind: 'year', year: 2026 }, TODAY), { kind: 'month', month: '2026-11' });
  assert.deepEqual(otherKind({ kind: 'year', year: 2025 }, TODAY), { kind: 'month', month: '2025-01' });
});

test('the teams of a team admin and auditor, each once', () => {
  assert.deepEqual(reportTeams(OWN, AUDITS), [{ id: 't1', name: 'Platform' }, { id: 't2', name: 'Sales' }]);
  assert.deepEqual(reportTeams(OWN, [{ team_id: 't1', team: 'Platform' }]), [{ id: 't1', name: 'Platform' }]);
  const member = { team: { id: 't1', name: 'Platform', team_role: 'member' } } as Parameters<typeof reportTeams>[0];
  assert.deepEqual(reportTeams(member, []), []);
});

test('the team from the address, otherwise the first one', () => {
  const teams = [{ id: 't1', name: 'Platform' }, { id: 't2', name: 'Sales' }];
  assert.equal(chosenTeam('?team=t2', teams), 't2');
  assert.equal(chosenTeam('', teams), 't1');
  assert.equal(chosenTeam('', []), null);
});

test("a member's card opens their report for the same period, the own card the own report", () => {
  assert.equal(memberHref('m1', 'me', { kind: 'month', month: '2026-10' }), '/month?month=2026-10&member=m1');
  assert.equal(memberHref('m1', 'me', { kind: 'year', year: 2026 }), '/year?year=2026&member=m1');
  assert.equal(memberHref('me', 'me', { kind: 'month', month: '2026-10' }), '/month?month=2026-10');
});
