// Year report (/year): totals, PTO account, days off, the months with their running balance, and the work by service
// and activity type (its parts follow the way of working).

import { api, errorText, type DayType, type WorkMode, type YearReport } from './api.ts';
import { isoDate, isoMonth, type IsoDate } from './dates.ts';
import { el, scrolling } from './dom.ts';
import { fromMinutes, toMinutes } from './durations.ts';
import { DAY_TYPE_LABELS } from './labels.ts';
import { viewedMember } from './team-view.ts';
import { entriesOfWorked, periodHeader, periodSummary, value } from './week.ts';
import { ownWorkMode, workParts, type WorkPart } from './work-modes.ts';

const MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** The year from `?year=2025`, otherwise the current year. */
export function yearFromSearch(search: string, today: IsoDate): number {
  const year = Number(new URLSearchParams(search).get('year'));
  return Number.isInteger(year) && year >= 2000 && year <= 2100 ? year : Number(today.slice(0, 4));
}

/** The overtime balance at the end of each month: the balance before the year plus the overtime so far. */
export function runningBalances(balanceIn: string, overtimes: string[]): string[] {
  let balance = toMinutes(balanceIn);
  return overtimes.map((overtime) => fromMinutes((balance += toMinutes(overtime))));
}

/** Label and count of each day type off, in the order of the day types. */
export function daysOffRows(daysOff: Partial<Record<DayType, number>>): [string, number][] {
  return (Object.keys(DAY_TYPE_LABELS) as DayType[])
    .filter((type) => daysOff[type])
    .map((type) => [DAY_TYPE_LABELS[type], daysOff[type] ?? 0]);
}

/** `2.5` → `2.5`, `17` → `17` (PTO days without trailing zeros) */
export function formatDays(days: number): string {
  return String(Number(days.toFixed(1)));
}

function cardRow(label: string, value: string): HTMLElement {
  return el('tr', {}, el('td', {}, label), el('td', { class: 'num' }, value));
}

function ptoCard(report: YearReport): HTMLElement {
  const pto = report.pto;
  if (!pto) {
    return el('div', { class: 'card' }, el('h3', {}, 'PTO'), el('p', { class: 'muted' }, 'No PTO days entered for this year.'));
  }
  return el('div', { class: 'card' }, el('h3', {}, 'PTO'),
    el('table', { class: 'card-table' }, el('tbody', {},
      cardRow(pto.carried_over_fixed ? 'Carried over (fixed)' : 'Carried over', formatDays(pto.carried_over)),
      cardRow('+ Allowance', formatDays(pto.allowance)),
      pto.extra_days ? cardRow('+ Extra days', formatDays(pto.extra_days)) : null,
      cardRow('− Used', formatDays(pto.used)),
      cardRow('− Planned', formatDays(pto.planned)),
      el('tr', { class: 'card-table-total' }, el('td', {}, el('strong', {}, 'Remaining')),
        el('td', { class: `num ${pto.remaining < 0 ? 'value-negative' : 'value-positive'}` },
          el('strong', {}, formatDays(pto.remaining)))))));
}

function daysOffCard(report: YearReport): HTMLElement {
  const rows = daysOffRows(report.days_off);
  return el('div', { class: 'card' }, el('h3', {}, 'Days off'),
    rows.length
      ? el('table', { class: 'card-table' }, el('tbody', {}, ...rows.map(([label, count]) => cardRow(label, String(count)))))
      : el('p', { class: 'muted' }, 'None'));
}

/** A card of the year's work: hours by service or activity type and the total; `None` if there is none. */
function workCard(title: string, rows: [string, string][], total: string): HTMLElement {
  return el('div', { class: 'card' }, el('h3', {}, title),
    rows.length
      ? el('table', { class: 'card-table' }, el('tbody', {}, ...rows.map(([label, duration]) => cardRow(label, duration)),
        el('tr', { class: 'card-table-total' }, el('td', {}, el('strong', {}, 'Total')),
          el('td', { class: 'num' }, el('strong', {}, total)))))
      : el('p', { class: 'muted' }, 'None'));
}

function byService(services: YearReport['coding']): [string, string][] {
  return services.map((service) => [service.service ?? 'No service', service.duration]);
}

function workCardOf(part: WorkPart, report: YearReport): HTMLElement {
  switch (part) {
    case 'coding':
      return workCard('Coding work', byService(report.coding), report.coding_total);
    case 'other_work':
      return workCard('Other ticket work', byService(report.other_work), report.other_work_total);
    case 'ticket_work':  // no coding work in the year: all ticket work is other ticket work
      return workCard('Ticket work', byService(report.other_work), report.other_work_total);
    case 'activities':
      return workCard('Activities', report.activities.map((activity) => [activity.activity_type, activity.duration]),
        report.activities_total);
  }
}

/** The work cards of the way of working; none (and no "Work" heading) in "Times only" without entries. */
function workCards(report: YearReport, mode: WorkMode): HTMLElement[] {
  const cards = workParts(mode, report).map((part) => workCardOf(part, report));
  return cards.length ? [el('h2', { class: 'year-work' }, 'Work'), el('div', { class: 'year-cards' }, ...cards)] : [];
}

function monthsTable(report: YearReport): HTMLElement {
  const balances = runningBalances(report.totals.balance_in, report.months.map((month) => month.overtime));
  const counted = report.totals.until ? isoMonth(report.totals.until) : '';
  return scrolling(el('table', { class: 'year-months' },
    el('thead', {}, el('tr', {}, el('th', {}, 'Month'), el('th', { class: 'num' }, 'Worked'), el('th', { class: 'num' }, 'Target'),
      el('th', { class: 'num' }, 'Overtime'), el('th', { class: 'num' }, 'Balance'))),
    el('tbody', {}, ...report.months.map((month, index) => {
      const future = !counted || month.month > counted;
      return el('tr', { class: future ? 'is-future' : null },
        el('td', {}, el('a', { href: `/month?month=${month.month}` }, MONTH_LABELS[index] ?? month.month)),
        el('td', { class: 'num' }, future ? '—' : month.worked),
        el('td', { class: 'num muted' }, future ? '—' : month.target),
        el('td', { class: 'num' }, future ? '—' : value(month.overtime, true)),
        el('td', { class: 'num' }, future ? '—' : value(balances[index] ?? '0:00')));
    })),
  ));
}

export async function renderYearPage(doc: Document): Promise<void> {
  const root = doc.querySelector<HTMLElement>('#year');
  if (!root) {
    return;
  }
  const today = isoDate(new Date());
  const year = yearFromSearch(doc.location.search, today);
  periodHeader(doc, 'year', {
    title: String(year), start: `${year}-01-01`, shifted: (shift) => `/year?year=${year + shift}`,
    of: (date) => `/year?year=${date.slice(0, 4)}`, current: year === Number(today.slice(0, 4)),
  });
  root.replaceChildren(el('p', { class: 'muted' }, 'Loading…'));
  try {
    const member = viewedMember(doc.location.search);
    const [report, mode] = await Promise.all([api.yearReport(year, member), ownWorkMode(member)]);
    const worked = el('div', {}, el('span', { class: 'muted' }, 'Days worked '), el('span', { class: 'num' }, String(report.days_worked)),
      el('span', { class: 'muted' }, ' · average '), el('span', { class: 'num' }, report.average_per_day_worked));
    const work = workCards(report, mode);
    root.replaceChildren(
      periodSummary(report.totals, work.length ? entriesOfWorked(report.entries, report.totals) : null, worked),
      el('div', { class: 'year-cards' }, ptoCard(report), daysOffCard(report)),
      el('h2', {}, 'Months'), monthsTable(report), ...work);
  } catch (error) {
    root.replaceChildren(el('div', { class: 'card is-warning', role: 'alert' },
      errorText(error, 'The year could not be loaded.')));
  }
}
