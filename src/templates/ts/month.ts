// Month report (/month): totals, days off and the monthly work report (coding hours by service and ticket).

import { api, ApiError, type DayType, type MonthReport } from './api.ts';
import { formatMonth, isoDate, isoMonth, isValidMonth, shiftMonth, type IsoDate } from './dates.ts';
import { el } from './dom.ts';
import { DAY_TYPE_LABELS } from './labels.ts';
import { periodSummary } from './week.ts';

type ServiceWork = MonthReport['coding'][number];

/** The month from `?month=2026-10`, otherwise the current month. */
export function monthFromSearch(search: string, today: IsoDate): string {
  const month = new URLSearchParams(search).get('month');
  return month && isValidMonth(month) ? month : isoMonth(today);
}

/** `PTO 2 · PTO ½ 1` */
export function describeDaysOff(daysOff: Partial<Record<DayType, number>>): string {
  return Object.entries(daysOff).map(([type, count]) => `${DAY_TYPE_LABELS[type as DayType]} ${count}`).join(' · ');
}

function renderHeader(doc: Document, month: string, today: IsoDate): void {
  doc.querySelector('#month-title')!.textContent = formatMonth(month);
  doc.querySelector<HTMLAnchorElement>('#month-previous')!.href = `/month?month=${shiftMonth(month, -1)}`;
  doc.querySelector<HTMLAnchorElement>('#month-next')!.href = `/month?month=${shiftMonth(month, 1)}`;
  doc.querySelector<HTMLAnchorElement>('#month-current')!.toggleAttribute('aria-disabled', month === isoMonth(today));
}

function daysOff(report: MonthReport): HTMLElement | null {
  const text = describeDaysOff(report.days_off);
  return text || report.pto_days
    ? el('div', {}, el('span', { class: 'muted' }, 'Days off '), text || '—',
      report.pto_days ? el('span', { class: 'muted' }, ` (PTO used: ${report.pto_days})`) : null)
    : null;
}

function serviceSection(work: ServiceWork): HTMLElement {
  const unassigned = work.service_id === null;
  return el('section', { class: 'work-service' },
    el('div', { class: 'work-service-header' },
      el('h3', {}, unassigned ? 'No service ' : `${work.service} `,
        unassigned ? el('a', { class: 'badge warning', href: '/review#tickets' }, 'assign in review') : null),
      el('span', { class: 'num' }, work.duration)),
    el('table', {},
      el('tbody', {}, ...work.tickets.map((ticket) => el('tr', {},
        el('td', { class: 'work-ticket' }, ticket.ticket_key ? el('strong', {}, ticket.ticket_key)
          : el('strong', { class: 'value-negative' }, 'No ticket')),
        el('td', {}, ticket.descriptions.length
          ? el('ul', { class: 'work-descriptions' }, ...ticket.descriptions.map((text) => el('li', {}, text)))
          : el('span', { class: 'muted' }, '—')),
        el('td', { class: 'num' }, ticket.duration))))),
  );
}

function workReport(report: MonthReport): HTMLElement {
  return el('section', { class: 'work-report' },
    el('div', { class: 'work-service-header' }, el('h2', {}, 'Coding work'),
      el('span', { class: 'num' }, el('span', { class: 'muted' }, 'Total '), el('strong', {}, report.coding_total))),
    report.coding.length
      ? el('div', {}, ...report.coding.map(serviceSection))
      : el('p', { class: 'muted' }, 'No coding work recorded in this month.'),
  );
}

export async function renderMonthPage(doc: Document): Promise<void> {
  const root = doc.querySelector<HTMLElement>('#month');
  if (!root) {
    return;
  }
  const today = isoDate(new Date());
  const month = monthFromSearch(doc.location.search, today);
  renderHeader(doc, month, today);
  root.replaceChildren(el('p', { class: 'muted' }, 'Loading…'));
  try {
    const report = await api.monthReport(month);
    root.replaceChildren(periodSummary(report.totals, daysOff(report)), workReport(report));
  } catch (error) {
    root.replaceChildren(el('div', { class: 'card is-warning', role: 'alert' },
      error instanceof ApiError ? error.message : 'The month could not be loaded.'));
  }
}
