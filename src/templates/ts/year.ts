// Year report (/year): totals, PTO account, days off and the months with their running balance.

import { api, ApiError, type DayType, type YearReport } from './api.ts';
import { isoDate, isoMonth, type IsoDate } from './dates.ts';
import { el } from './dom.ts';
import { fromMinutes, toMinutes } from './durations.ts';
import { DAY_TYPE_LABELS } from './labels.ts';
import { viewedMember } from './team-view.ts';
import { periodSummary, value } from './week.ts';

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

function renderHeader(doc: Document, year: number, today: IsoDate): void {
  doc.querySelector('#year-title')!.textContent = String(year);
  doc.querySelector<HTMLAnchorElement>('#year-previous')!.href = `/year?year=${year - 1}`;
  doc.querySelector<HTMLAnchorElement>('#year-next')!.href = `/year?year=${year + 1}`;
  doc.querySelector<HTMLAnchorElement>('#year-current')!.toggleAttribute('aria-disabled', year === Number(today.slice(0, 4)));
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

function monthsTable(report: YearReport): HTMLElement {
  const balances = runningBalances(report.totals.balance_in, report.months.map((month) => month.overtime));
  const counted = report.totals.until ? isoMonth(report.totals.until) : '';
  return el('table', { class: 'year-months' },
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
  );
}

export async function renderYearPage(doc: Document): Promise<void> {
  const root = doc.querySelector<HTMLElement>('#year');
  if (!root) {
    return;
  }
  const today = isoDate(new Date());
  const year = yearFromSearch(doc.location.search, today);
  renderHeader(doc, year, today);
  root.replaceChildren(el('p', { class: 'muted' }, 'Loading…'));
  try {
    const report = await api.yearReport(year, viewedMember(doc.location.search));
    const worked = el('div', {}, el('span', { class: 'muted' }, 'Days worked '), el('span', { class: 'num' }, String(report.days_worked)),
      el('span', { class: 'muted' }, ' · average '), el('span', { class: 'num' }, report.average_per_day_worked));
    root.replaceChildren(periodSummary(report.totals, worked),
      el('div', { class: 'year-cards' }, ptoCard(report), daysOffCard(report)),
      el('h2', {}, 'Months'), monthsTable(report));
  } catch (error) {
    root.replaceChildren(el('div', { class: 'card is-warning', role: 'alert' },
      error instanceof ApiError ? error.message : 'The year could not be loaded.'));
  }
}
