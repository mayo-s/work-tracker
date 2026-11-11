// Team report (/team/report): a summary of a team's activities in a month or a year, in cards (SPEC 5.12).

import { api, errorText, type AuditedTeam, type AuthStatus, type TeamReport } from './api.ts';
import { clockTime, formatMonth, formatShortDate, isoDate, isoMonth, shiftMonth, type IsoDate } from './dates.ts';
import { button, el } from './dom.ts';
import { t } from './i18n.ts';
import { monthFromSearch } from './month.ts';
import { periodHeader, value, type Period } from './week.ts';
import { yearFromSearch } from './year.ts';

export type ReportPeriod = { kind: 'month'; month: string } | { kind: 'year'; year: number };
type TeamChoice = { id: string; name: string };
type Hours = TeamReport['totals'];
type Member = TeamReport['members'][number];
type Service = TeamReport['services'][number];
/** Who looks at which period. */
type ReportView = { me: string | null; period: ReportPeriod };

/** The period from `?year=2026` or `?month=2026-10`, otherwise the current month. */
export function periodFromSearch(search: string, today: IsoDate): ReportPeriod {
  return new URLSearchParams(search).has('year') ? { kind: 'year', year: yearFromSearch(search, today) }
    : { kind: 'month', month: monthFromSearch(search, today) };
}

function periodParams(period: ReportPeriod): { month: string } | { year: string } {
  return period.kind === 'month' ? { month: period.month } : { year: String(period.year) };
}

/** The address of a team's report for a period; without a team, the page chooses the first one. */
export function reportHref(team: string | null, period: ReportPeriod): string {
  return `/team/report?${new URLSearchParams({ ...(team ? { team } : {}), ...periodParams(period) })}`;
}

/** The address of the report's CSV file. */
export function csvHref(team: string, period: ReportPeriod): string {
  return `/api/teams/${encodeURIComponent(team)}/report.csv?${new URLSearchParams(periodParams(period))}`;
}

/** The same time as a year, or as a month: the current month in the current year, otherwise January. */
export function otherKind(period: ReportPeriod, today: IsoDate): ReportPeriod {
  if (period.kind === 'month') {
    return { kind: 'year', year: Number(period.month.slice(0, 4)) };
  }
  return { kind: 'month', month: String(period.year) === today.slice(0, 4) ? isoMonth(today) : `${period.year}-01` };
}

/** The suggested name of an exported file, the same as the CSV's, e.g. `20261109_1430_team_report_Platform`: other
 * characters than letters, digits, `.` and `-` in the team's name become `_`. */
export function exportFileName(team: string, now: Date): string {
  const name = team.replace(/[^\p{L}\p{N}_.-]+/gu, '_').replace(/^_+|_+$/g, '');
  return `${isoDate(now).replaceAll('-', '')}_${clockTime(now).replace(':', '')}_team_report_${name}`;
}

/** The browser's print dialog, where "Save as PDF" suggests the page's title as the file name. */
function saveAsPdf(team: string): void {
  const title = document.title;
  document.title = exportFileName(team, new Date());
  window.addEventListener('afterprint', () => {
    document.title = title;
  }, { once: true });
  window.print();
}

/** The current period of the same kind. */
function currentPeriod(period: ReportPeriod, today: IsoDate): ReportPeriod {
  return period.kind === 'month' ? { kind: 'month', month: isoMonth(today) } : { kind: 'year', year: Number(today.slice(0, 4)) };
}

function header(period: ReportPeriod, team: string | null, today: IsoDate): Period {
  const href = (next: ReportPeriod): string => reportHref(team, next);
  if (period.kind === 'month') {
    return {
      title: t('Team report · {period}', { period: formatMonth(period.month) }), start: `${period.month}-01`,
      shifted: (shift) => href({ kind: 'month', month: shiftMonth(period.month, shift) }),
      of: (date) => href({ kind: 'month', month: isoMonth(date) }), current: period.month === isoMonth(today),
    };
  }
  return {
    title: t('Team report · {period}', { period: period.year }), start: `${period.year}-01-01`,
    shifted: (shift) => href({ kind: 'year', year: period.year + shift }),
    of: (date) => href({ kind: 'year', year: Number(date.slice(0, 4)) }), current: String(period.year) === today.slice(0, 4),
  };
}

/** The teams the user may see the report of: their own as team admin, then those they audit. */
export function reportTeams(status: Pick<AuthStatus, 'team'>, audits: Pick<AuditedTeam, 'team_id' | 'team'>[]): TeamChoice[] {
  const own = status.team?.team_role === 'team_admin' ? [{ id: status.team.id, name: status.team.name }] : [];
  return [...own, ...audits.filter((audit) => audit.team_id !== own[0]?.id).map((audit) => ({ id: audit.team_id, name: audit.team }))];
}

/** The team from `?team=<id>` (the API decides whether the user may see it), otherwise the first one. */
export function chosenTeam(search: string, teams: TeamChoice[]): string | null {
  return new URLSearchParams(search).get('team') || teams[0]?.id || null;
}

function figure(label: string, ...content: (HTMLElement | string)[]): HTMLElement {
  return el('div', {}, el('span', { class: 'muted' }, `${label} `), ...content);
}

function figures(hours: Hours): HTMLElement[] {
  return [
    figure(t('Worked'), el('span', { class: 'num' }, hours.worked), el('span', { class: 'muted' }, ` ${t('of')} `),
      el('span', { class: 'num' }, hours.target)),
    figure(t('Overtime'), value(hours.overtime, true)),
    figure(t('Entries'), el('span', { class: 'num' }, hours.entries ?? '—')),
  ];
}

/** Names with their hours, e.g. the tickets of a service. */
function hoursList(rows: [string, string][]): HTMLElement {
  return el('ul', { class: 'report-hours' }, ...rows.map(([name, duration]) => el('li', {}, el('span', {}, name),
    el('span', { class: 'num' }, duration))));
}

function serviceCard(service: Service): HTMLElement {
  return el('div', { class: 'card' },
    el('div', { class: 'work-service-header' }, el('h3', {}, service.service ?? t('No service')),
      el('span', { class: 'num' }, service.duration)),
    hoursList(service.tickets.map((ticket) => [ticket.ticket_key ?? t('No ticket'), ticket.duration])));
}

/** A member's month or year report in the team view, for the same period; the own one is not a look at someone else's. */
export function memberHref(member: string, me: string | null, period: ReportPeriod): string {
  const params = new URLSearchParams(periodParams(period));
  if (member !== me) {
    params.set('member', member);
  }
  return `/${period.kind}?${params}`;
}

/** The whole card links to the member's report. */
function memberCard(member: Member, view: ReportView): HTMLElement {
  return el('a', { class: 'card report-member', href: memberHref(member.user_id, view.me, view.period) },
    el('h3', {}, member.name),
    member.note ? el('p', { class: 'muted' }, member.note) : null,
    ...figures(member),
    member.activity_types.length
      ? hoursList(member.activity_types.map((item) => [item.activity_type, item.duration])) : null,
    el('span', { class: 'report-open' }, t('Open report ›')));
}

function cards(title: string, items: HTMLElement[], empty: string | null): HTMLElement | null {
  if (!items.length && !empty) {
    return null;
  }
  return el('section', {}, el('h2', {}, title),
    items.length ? el('div', { class: 'report-cards' }, ...items) : el('p', { class: 'muted' }, empty));
}

function reportContent(report: TeamReport, view: ReportView): (HTMLElement | null)[] {
  return [
    el('div', { class: 'card card-surface week-summary' }, el('strong', {}, report.team), ...figures(report.totals),
      report.until && report.until < report.end
        ? el('div', { class: 'muted' }, t('counted up to {date}', { date: formatShortDate(report.until) })) : null),
    report.current_members_only ? el('p', { class: 'muted' },
      t('Current members only, each from the day they joined: the total of a past period shrinks when someone leaves.')) : null,
    cards(t('Activity types'), report.activity_types.map((item) => el('div', { class: 'card' }, el('h3', {}, item.activity_type),
      el('p', { class: 'tile-value num' }, item.duration))), t('No entries in this period.')),
    cards(t('Services'), report.services.map(serviceCard), null),
    cards(t('Members'), report.members.map((member) => memberCard(member, view)), t('Nobody was in the team in this period.')),
  ];
}

/** The choice of team, for someone who has several: a form, so nothing changes before "Show". */
function teamChooser(teams: TeamChoice[], team: string | null, period: ReportPeriod): HTMLElement | null {
  if (teams.length < 2) {
    return null;
  }
  const hidden = period.kind === 'month' ? { name: 'month', value: period.month } : { name: 'year', value: String(period.year) };
  return el('form', { class: 'member-chooser', method: 'get', action: '/team/report' },
    el('label', { for: 'team-report-team' }, t('Team')),
    el('select', { id: 'team-report-team', name: 'team' },
      ...teams.map((item) => el('option', { value: item.id, selected: item.id === team }, item.name))),
    el('input', { type: 'hidden', ...hidden }),
    el('button', { type: 'submit', class: 'button-small' }, t('Show')));
}

function periodLinks(doc: Document, period: ReportPeriod, team: string | null, today: IsoDate): void {
  const current = doc.querySelector<HTMLAnchorElement>('#team-report-current')!;
  current.href = reportHref(team, currentPeriod(period, today));
  current.textContent = period.kind === 'month' ? t('Current month') : t('Current year');
  const kind = doc.querySelector<HTMLAnchorElement>('#team-report-kind')!;
  kind.href = reportHref(team, otherKind(period, today));
  kind.textContent = period.kind === 'month' ? t('Year') : t('Month');
}

/** The exports of the shown report, next to the date field. */
function showExports(doc: Document, team: string, report: TeamReport, period: ReportPeriod): void {
  doc.querySelector('#team-report-exports')?.replaceChildren(
    el('a', { class: 'button', href: csvHref(team, period) }, t('Export CSV')),
    button(t('Save as PDF'), () => saveAsPdf(report.team), { class: 'button' }));
}

function loadReport(team: string, period: ReportPeriod): Promise<TeamReport> {
  return api.teamReport(team, periodParams(period));
}

export async function renderTeamReportPage(doc: Document): Promise<void> {
  const root = doc.querySelector<HTMLElement>('#team-report');
  if (!root) {
    return;
  }
  root.replaceChildren(el('p', { class: 'muted' }, t('Loading…')));
  try {
    const today = isoDate(new Date());
    const period = periodFromSearch(doc.location.search, today);
    const [status, audits] = await Promise.all([api.authStatus(), api.audits()]);
    const teams = reportTeams(status, audits);
    const team = chosenTeam(doc.location.search, teams);
    periodHeader(doc, 'team-report', header(period, team, today));
    periodLinks(doc, period, team, today);
    if (team === null) {
      root.replaceChildren(el('div', { class: 'card' }, t('The team report is for the team admins and auditors of a team.')));
      return;
    }
    const chooser = teamChooser(teams, team, period);
    if (chooser) {
      doc.querySelector('.week-header')?.append(chooser);
    }
    const report = await loadReport(team, period);
    root.replaceChildren(...reportContent(report, { me: status.user?.id ?? null, period }).filter((part) => part !== null));
    showExports(doc, team, report, period);
  } catch (error) {
    root.replaceChildren(el('div', { class: 'card is-warning', role: 'alert' },
      errorText(error, t('The team report could not be loaded.'))));
  }
}
