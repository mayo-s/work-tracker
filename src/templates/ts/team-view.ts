// Team view: a team admin or an auditor looks at a member's dashboard, week, month and year, read-only
// (`?member=<id>`).

import { api, type AuditedTeam, type MemberView } from './api.ts';
import { addDays, formatDate } from './dates.ts';
import { el } from './dom.ts';
import { listOf, t } from './i18n.ts';

/** The pages of the team view; links to them keep the member. */
export const TEAM_VIEW_PAGES = ['/', '/week', '/month', '/year'];
const OWN_VIEW = 'data-own-view';

/** The member being viewed, or null for the user's own data. */
export function viewedMember(search: string): string | null {
  return new URLSearchParams(search).get('member') || null;
}

/** A link to a page of the team view with the member kept, e.g. `/month?month=2026-10&member=…`; others unchanged. */
export function withMember(href: string, member: string): string {
  const url = new URL(href, 'http://app');
  if (url.host !== 'app' || !TEAM_VIEW_PAGES.includes(url.pathname) || url.searchParams.get('member') === member) {
    return href;
  }
  url.searchParams.set('member', member);
  return `${url.pathname}${url.search}${url.hash}`;
}

/** The same page without the member: the user's own data. */
export function ownView(path: string, search: string): string {
  const params = new URLSearchParams(search);
  params.delete('member');
  return params.size ? `${path}?${params}` : path;
}

export function fullName(member: MemberView): string {
  return [member.first_name, member.last_name].filter(Boolean).join(' ');
}

type Stay = AuditedTeam['members'][number]['stays'][number];

/** The days an auditor sees, e.g. `02.11.2026–03.11.2026, from 05.11.2026` (`left_on` is the first day no longer in). */
export function staysText(stays: Stay[]): string {
  return stays.map((stay) => (stay.left_on ? `${formatDate(stay.joined_on)}–${formatDate(addDays(stay.left_on, -1))}`
    : t('from {date}', { date: formatDate(stay.joined_on) }))).join(', ');
}

/** Who is viewed and which of their days, for the banner: as team admin from the day they joined, as auditor their stays
 * in the audited teams. */
export function viewedText(member: string, team: { name: string; members: MemberView[] } | null,
  audits: AuditedTeam[]): [string, string] | null {
  const current = team?.members.find((item) => item.user_id === member);
  if (current && team) {
    return [fullName(current),
      ` ${t('from {date}, when they joined {team}', { date: formatDate(current.joined_on), team: team.name })}`];
  }
  const audited = audits.flatMap((item) => item.members.filter((one) => one.user_id === member)
    .map((one) => ({ team: item.team, name: one.name, stays: one.stays })));
  if (!audited.length) {
    return null;
  }
  const teams = listOf(audited.map((item) => `${item.team} (${staysText(item.stays)})`));
  return [audited[0]!.name, ` ${t('on their days in {teams}', { teams })}`];
}

/** The team whose report a member belongs to: the own team if they are in it, otherwise an audited one. */
export function memberTeam(member: string, team: { id: string; members: MemberView[] } | null,
  audits: AuditedTeam[]): string | null {
  if (team?.members.some((item) => item.user_id === member)) {
    return team.id;
  }
  return audits.find((item) => item.members.some((one) => one.user_id === member))?.team_id ?? null;
}

/** The team report of the team, for the month or year the page shows (otherwise the current month). */
export function reportLink(team: string, search: string): string {
  const shown = new URLSearchParams(search);
  const params = new URLSearchParams({ team });
  for (const name of ['month', 'year']) {
    const value = shown.get(name);
    if (value) {
      params.set(name, value);
    }
  }
  return `/team/report?${params}`;
}

/** Keeps the member in all links to the team view pages, also in those the page renders later. */
function keepMember(root: Node & ParentNode, member: string): void {
  const update = (): void => {
    for (const link of root.querySelectorAll<HTMLAnchorElement>(`a[href]:not([${OWN_VIEW}])`)) {
      const href = link.getAttribute('href')!;
      const kept = withMember(href, member);
      if (kept !== href) {
        link.setAttribute('href', kept);
      }
    }
  };
  update();
  new MutationObserver(update).observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ['href'] });
}

/** The banner of the team view on top of the page, and the member kept in the links. */
export async function showTeamView(doc: Document, member: string): Promise<void> {
  keepMember(doc.body, member);
  const status = await api.authStatus();
  const [team, audits] = await Promise.all([
    status.team?.team_role === 'team_admin' ? api.team(status.team.id) : null, api.audits()]);
  const [name, days] = viewedText(member, team, audits) ?? [t('A member'), ''];
  const report = memberTeam(member, team, audits);
  doc.querySelector('main')?.prepend(el('div', { class: 'card team-view-banner', role: 'status' },
    `${t('Read-only:')} `, el('strong', {}, t("{name}'s data", { name })), `${days}. `,
    `${t('The overtime balance and PTO left cover the whole time.')} `,
    report ? el('a', { href: reportLink(report, doc.location.search), [OWN_VIEW]: true }, t('Back to the team report')) : null,
    report ? ' · ' : null,
    el('a', { href: ownView(doc.location.pathname, doc.location.search), [OWN_VIEW]: true }, t('Back to your data'))));
}
