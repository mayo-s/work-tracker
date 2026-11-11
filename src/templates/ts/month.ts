// Month report (/month): totals, days off and the monthly work report by activity type, each with its ticket work by
// service and ticket and the descriptions of its other entries ("Times only": only when the month holds entries).

import { api, errorText, type DayType, type MonthReport, type WorkMode } from './api.ts';
import { formatMonth, isoDate, isoMonth, isValidMonth, shiftMonth, type IsoDate } from './dates.ts';
import { el, scrolling } from './dom.ts';
import { decimal, t } from './i18n.ts';
import { DAY_TYPE_LABELS } from './labels.ts';
import { viewedMember } from './team-view.ts';
import { entriesOfWorked, periodHeader, periodSummary } from './week.ts';
import { showsWork } from './work-modes.ts';

type ActivityWork = MonthReport['work'][number];
type ServiceWork = ActivityWork['services'][number];

/** The month from `?month=2026-10`, otherwise the current month. */
export function monthFromSearch(search: string, today: IsoDate): string {
  const month = new URLSearchParams(search).get('month');
  return month && isValidMonth(month) ? month : isoMonth(today);
}

/** `PTO 2 · PTO ½ 1` */
export function describeDaysOff(daysOff: Partial<Record<DayType, number>>): string {
  return Object.entries(daysOff).map(([type, count]) => `${DAY_TYPE_LABELS[type as DayType]} ${count}`).join(' · ');
}

function daysOff(report: MonthReport): HTMLElement | null {
  const text = describeDaysOff(report.days_off);
  return text || report.pto_days
    ? el('div', {}, el('span', { class: 'muted' }, `${t('Days off')} `), text || '—',
      report.pto_days ? el('span', { class: 'muted' }, ` ${t('(PTO used: {days})', { days: decimal(report.pto_days) })}`)
        : null)
    : null;
}

function serviceSection(work: ServiceWork, readOnly: boolean): HTMLElement {
  const unassigned = work.service_id === null;
  return el('section', { class: 'work-service' },
    el('div', { class: 'work-service-header' },
      el('h3', {}, `${unassigned ? t('No service') : work.service} `,
        unassigned && !readOnly ? el('a', { class: 'badge warning', href: '/review#tickets' }, t('assign in review')) : null),
      el('span', { class: 'num' }, work.duration)),
    scrolling(el('table', { class: 'work-tickets' },
      el('tbody', {}, ...work.tickets.map((ticket) => el('tr', {},
        el('td', { class: 'work-ticket' }, ticket.ticket_key ? el('strong', {}, ticket.ticket_key)
          : el('strong', { class: 'value-negative' }, t('No ticket'))),
        el('td', {}, texts(ticket.descriptions)),
        el('td', { class: 'num' }, ticket.duration)))))),
  );
}

/** The descriptions or notes as a list, or a dash. */
function texts(items: string[]): HTMLElement {
  return items.length
    ? el('ul', { class: 'work-descriptions' }, ...items.map((text) => el('li', {}, text)))
    : el('span', { class: 'muted' }, '—');
}

/** A part of the work report with its total: an activity type, or "Work" when nothing was recorded. */
function workSection(title: string, total: string, content: HTMLElement | null, empty: string): HTMLElement {
  return el('section', { class: 'work-report' },
    el('div', { class: 'work-service-header' }, el('h2', {}, title),
      el('span', { class: 'num' }, el('span', { class: 'muted' }, `${t('Total')} `), el('strong', {}, total))),
    content ?? el('p', { class: 'muted' }, empty),
  );
}

function servicesContent(services: ServiceWork[], readOnly: boolean): HTMLElement | null {
  return services.length ? el('div', {}, ...services.map((work) => serviceSection(work, readOnly))) : null;
}

/** An activity type's part: its ticket work by service and ticket, then the descriptions of its other entries. */
function activitySection(work: ActivityWork, readOnly: boolean): HTMLElement {
  const content = [servicesContent(work.services, readOnly), work.descriptions.length ? texts(work.descriptions) : null]
    .filter((part) => part !== null);
  return workSection(work.activity_type, work.duration, content.length ? el('div', {}, ...content) : null,
    t('No descriptions.'));
}

function workReport(report: MonthReport, mode: WorkMode): HTMLElement[] {
  if (!showsWork(mode, report.work.length > 0)) {
    return [];
  }
  const readOnly = Boolean(report.visible_from);
  return report.work.length ? report.work.map((work) => activitySection(work, readOnly))
    : [workSection(t('Work'), report.work_total, null, t('No work recorded in this month.'))];
}

export async function renderMonthPage(doc: Document): Promise<void> {
  const root = doc.querySelector<HTMLElement>('#month');
  if (!root) {
    return;
  }
  const today = isoDate(new Date());
  const month = monthFromSearch(doc.location.search, today);
  periodHeader(doc, 'month', {
    title: formatMonth(month), start: `${month}-01`, shifted: (shift) => `/month?month=${shiftMonth(month, shift)}`,
    of: (date) => `/month?month=${isoMonth(date)}`, current: month === isoMonth(today),
  });
  root.replaceChildren(el('p', { class: 'muted' }, t('Loading…')));
  try {
    const member = viewedMember(doc.location.search);
    const report = await api.monthReport(month, member);
    const parts = workReport(report, report.work_mode);  // the member's way of working in the team view
    root.replaceChildren(
      periodSummary(report.totals, parts.length ? entriesOfWorked(report.entries, report.totals) : null, daysOff(report)),
      ...parts);
  } catch (error) {
    root.replaceChildren(el('div', { class: 'card is-warning', role: 'alert' },
      errorText(error, t('The month could not be loaded.'))));
  }
}
