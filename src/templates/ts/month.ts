// Month report (/month): totals, days off and the monthly work report: coding and other ticket work (or all ticket
// work, without coding) by service and ticket, activities by type; its parts follow the way of working.

import { api, errorText, type DayType, type MonthReport, type WorkMode } from './api.ts';
import { formatMonth, isoDate, isoMonth, isValidMonth, shiftMonth, type IsoDate } from './dates.ts';
import { el, scrolling } from './dom.ts';
import { DAY_TYPE_LABELS } from './labels.ts';
import { viewedMember } from './team-view.ts';
import { entriesOfWorked, periodHeader, periodSummary } from './week.ts';
import { ownWorkMode, workParts, type WorkPart } from './work-modes.ts';

type ServiceWork = MonthReport['coding'][number];
type ActivityWork = MonthReport['activities'][number];

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
    ? el('div', {}, el('span', { class: 'muted' }, 'Days off '), text || '—',
      report.pto_days ? el('span', { class: 'muted' }, ` (PTO used: ${report.pto_days})`) : null)
    : null;
}

function serviceSection(work: ServiceWork, readOnly: boolean): HTMLElement {
  const unassigned = work.service_id === null;
  return el('section', { class: 'work-service' },
    el('div', { class: 'work-service-header' },
      el('h3', {}, unassigned ? 'No service ' : `${work.service} `,
        unassigned && !readOnly ? el('a', { class: 'badge warning', href: '/review#tickets' }, 'assign in review') : null),
      el('span', { class: 'num' }, work.duration)),
    scrolling(el('table', {},
      el('tbody', {}, ...work.tickets.map((ticket) => el('tr', {},
        el('td', { class: 'work-ticket' }, ticket.ticket_key ? el('strong', {}, ticket.ticket_key)
          : el('strong', { class: 'value-negative' }, 'No ticket')),
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

/** A part of the work report with its total: "Coding work", "Other ticket work", "Ticket work" or "Activities". */
function workSection(title: string, total: string, content: HTMLElement | null, empty: string): HTMLElement {
  return el('section', { class: 'work-report' },
    el('div', { class: 'work-service-header' }, el('h2', {}, title),
      el('span', { class: 'num' }, el('span', { class: 'muted' }, 'Total '), el('strong', {}, total))),
    content ?? el('p', { class: 'muted' }, empty),
  );
}

function servicesContent(services: ServiceWork[], readOnly: boolean): HTMLElement | null {
  return services.length ? el('div', {}, ...services.map((work) => serviceSection(work, readOnly))) : null;
}

function activitiesContent(activities: ActivityWork[]): HTMLElement | null {
  return activities.length ? scrolling(el('table', {},
    el('tbody', {}, ...activities.map((activity) => el('tr', {},
      el('td', { class: 'work-ticket' }, el('strong', {}, activity.activity_type)),
      el('td', {}, texts(activity.notes)),
      el('td', { class: 'num' }, activity.duration)))))) : null;
}

function workSectionOf(part: WorkPart, report: MonthReport): HTMLElement {
  const readOnly = Boolean(report.visible_from);
  switch (part) {
    case 'coding':
      return workSection('Coding work', report.coding_total, servicesContent(report.coding, readOnly),
        'No coding work recorded in this month.');
    case 'other_work':
      return workSection('Other ticket work', report.other_work_total, servicesContent(report.other_work, readOnly),
        'No other ticket work recorded in this month.');
    case 'ticket_work':  // no coding work in the month: all ticket work is other ticket work
      return workSection('Ticket work', report.other_work_total, servicesContent(report.other_work, readOnly),
        'No ticket work recorded in this month.');
    case 'activities':
      return workSection('Activities', report.activities_total, activitiesContent(report.activities),
        'No activities recorded in this month.');
  }
}

function workReport(report: MonthReport, mode: WorkMode): HTMLElement[] {
  return workParts(mode, report).map((part) => workSectionOf(part, report));
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
  root.replaceChildren(el('p', { class: 'muted' }, 'Loading…'));
  try {
    const member = viewedMember(doc.location.search);
    const [report, mode] = await Promise.all([api.monthReport(month, member), ownWorkMode(member)]);
    const parts = workReport(report, mode);
    root.replaceChildren(
      periodSummary(report.totals, parts.length ? entriesOfWorked(report.entries, report.totals) : null, daysOff(report)),
      ...parts);
  } catch (error) {
    root.replaceChildren(el('div', { class: 'card is-warning', role: 'alert' },
      errorText(error, 'The month could not be loaded.')));
  }
}
