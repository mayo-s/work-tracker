// Tests of the team view helpers; run with `npm test`.

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { memberTeam, ownView, reportLink, staysText, viewedMember, viewedText, withMember } from '../ts/team-view.ts';
import type { AuditedTeam, MemberView } from '../ts/api.ts';

test('the member from the address', () => {
  assert.equal(viewedMember('?week=2026-W45&member=abc'), 'abc');
  assert.equal(viewedMember('?member='), null);
});

test('links to the team view pages keep the member, others stay', () => {
  assert.equal(withMember('/month?month=2026-10', 'abc'), '/month?month=2026-10&member=abc');
  assert.equal(withMember('/', 'abc'), '/?member=abc');
  assert.equal(withMember('/week?member=abc', 'abc'), '/week?member=abc');
  assert.equal(withMember('/settings#team', 'abc'), '/settings#team');
  assert.equal(withMember('https://example.com/week', 'abc'), 'https://example.com/week');
});

test('back to the own data', () => {
  assert.equal(ownView('/month', '?month=2026-10&member=abc'), '/month?month=2026-10');
  assert.equal(ownView('/', '?member=abc'), '/');
});

test('an auditor sees the stays: each from the day joined to the day before leaving', () => {
  assert.equal(staysText([{ joined_on: '2026-11-02', left_on: '2026-11-04' }, { joined_on: '2026-11-05', left_on: null }]),
    '02.11.2026–03.11.2026, from 05.11.2026');
});

test('the banner names the member and their days, as team admin or as auditor', () => {
  const rainer = { user_id: 'r', username: 'rainer', email: 'rainer.zufall@example.com', first_name: 'Rainer',
    last_name: 'Zufall', team_role: 'member' as const, joined_on: '2026-11-04' };
  assert.deepEqual(viewedText('r', { name: 'Platform', members: [rainer] }, []),
    ['Rainer Zufall', ' from 04.11.2026, when they joined Platform']);
  const audit = { team_id: 't', team: 'Billing', until: null,
    members: [{ user_id: 'r', name: 'Rainer Zufall', stays: [{ joined_on: '2026-11-02', left_on: '2026-11-04' }] }] };
  assert.deepEqual(viewedText('r', null, [audit]), ['Rainer Zufall', ' on their days in Billing (02.11.2026–03.11.2026)']);
  assert.equal(viewedText('x', null, [audit]), null);
});

test('the team report a member belongs to: the own team first, then an audited one', () => {
  const own = { id: 'mine', members: [{ user_id: 'm1' } as MemberView] };
  const audits = [{ team_id: 'audited', members: [{ user_id: 'm1' }, { user_id: 'm2' }] }] as AuditedTeam[];
  assert.equal(memberTeam('m1', own, audits), 'mine');
  assert.equal(memberTeam('m2', own, audits), 'audited');
  assert.equal(memberTeam('m3', own, audits), null);
  assert.equal(memberTeam('m2', null, audits), 'audited');
});

test('the link back to the team report keeps the month or year shown', () => {
  assert.equal(reportLink('t', '?month=2026-10&member=m1'), '/team/report?team=t&month=2026-10');
  assert.equal(reportLink('t', '?year=2026&member=m1'), '/team/report?team=t&year=2026');
  assert.equal(reportLink('t', '?week=2026-W45&member=m1'), '/team/report?team=t');
});
