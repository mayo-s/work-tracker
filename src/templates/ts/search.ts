// Search (/search): finds entries by text, service or activity type, of all time or a period, and sums them up by
// ticket or activity type and by month. The criteria are in the URL (`?text=…&period=last-12-months`, or
// `period=custom&start=…&end=…`); the page turns the period into the dates the API takes. Without ticket entries
// (way of working), the page offers no service.

import {
  api, errorText, type ActivityType, type EntryView, type SearchResult, type ServiceChoice, type WorkMode,
} from './api.ts';
import { addDays, formatDate, formatMonth, isoDate, isoMonth, shiftMonth, weekLink, type IsoDate } from './dates.ts';
import { button, el, scrolling } from './dom.ts';
import { detailsButton } from './entry-details.ts';
import { entryContent } from './week.ts';
import { hasTickets } from './work-modes.ts';

const NO_SERVICE = 'none';
const DATE = /^\d{4}-\d{2}-\d{2}$/;
/** The entries listed at first; the sums always count all. */
export const LIMIT = 100;

const PERIODS = {
  '': 'All time', 'this-year': 'This year', 'last-year': 'Last year', 'last-12-months': 'Last 12 months',
  'this-month': 'This month', custom: 'Custom',
} as const;
export type Period = keyof typeof PERIODS;

/** What to search for: text, at most one of service (`none`: tickets without service) and activity type, and the
 * period; `start` and `end` (each may be empty: open) only for a custom period. */
export type SearchCriteria = {
  text: string; service_id: string | null; activity_type_id: string | null; period: Period; start: IsoDate | '';
  end: IsoDate | '';
};

/** First and last day of a period; null: open on that side. */
export type DateRange = { start: IsoDate | null; end: IsoDate | null };

/** The criteria from the URL; all time unless a period is given (dates alone are a custom period). */
export function criteriaFromSearch(search: string): SearchCriteria {
  const params = new URLSearchParams(search);
  const date = (name: string): IsoDate | '' => {
    const value = params.get(name) ?? '';
    return DATE.test(value) ? value : '';
  };
  const asked = params.get('period');
  const period: Period = asked && Object.hasOwn(PERIODS, asked) ? asked as Period
    : date('start') || date('end') ? 'custom' : '';
  return {
    text: params.get('text')?.trim() ?? '', service_id: params.get('service_id') || null,
    activity_type_id: params.get('activity_type_id') || null, period,
    start: period === 'custom' ? date('start') : '', end: period === 'custom' ? date('end') : '',
  };
}

/** The days of the period on `today`; "Last 12 months" from the first of the month eleven months before. */
export function periodRange(criteria: Pick<SearchCriteria, 'period' | 'start' | 'end'>, today: IsoDate): DateRange {
  const year = Number(today.slice(0, 4));
  const month = isoMonth(today);
  switch (criteria.period) {
    case 'this-year':
      return { start: `${year}-01-01`, end: `${year}-12-31` };
    case 'last-year':
      return { start: `${year - 1}-01-01`, end: `${year - 1}-12-31` };
    case 'last-12-months':
      return { start: `${shiftMonth(month, -11)}-01`, end: today };
    case 'this-month':
      return { start: `${month}-01`, end: addDays(`${shiftMonth(month, 1)}-01`, -1) };
    case 'custom':
      return { start: criteria.start || null, end: criteria.end || null };
    default:
      return { start: null, end: null };
  }
}

/** `This year · 01.01.2026 – 31.12.2026`, `from 01.03.2026`, `All time`. */
export function describePeriod(period: Period, range: DateRange): string {
  const { start, end } = range;
  const dates = start && end ? `${formatDate(start)} – ${formatDate(end)}`
    : start ? `from ${formatDate(start)}` : end ? `until ${formatDate(end)}` : '';
  if (period === 'custom' || period === '') {
    return dates || PERIODS[''];
  }
  return `${PERIODS[period]} · ${dates}`;
}

function query(params: Record<string, string | number | null>): string {
  const given = Object.entries(params).filter((pair): pair is [string, string | number] => Boolean(pair[1]));
  return new URLSearchParams(given.map(([name, value]) => [name, String(value)])).toString();
}

/** The query of the criteria for the URL; empty ones left out. */
export function searchQuery(criteria: SearchCriteria): string {
  return query(criteria);
}

/** The query for the API: the period as dates, and the limit of the entries listed (null: all). */
export function apiQuery(criteria: SearchCriteria, today: IsoDate, limit: number | null): string {
  const { start, end } = periodRange(criteria, today);
  const { text, service_id, activity_type_id } = criteria;
  return query({ text, service_id, activity_type_id, start, end, limit });
}

/** The choice of the service or activity type select: `service:<id>`, `service:none`, `activity:<id>` or empty. */
export function scopeValue(criteria: Pick<SearchCriteria, 'service_id' | 'activity_type_id'>): string {
  if (criteria.service_id) {
    return `service:${criteria.service_id}`;
  }
  return criteria.activity_type_id ? `activity:${criteria.activity_type_id}` : '';
}

/** The service and activity type of a choice of the select. */
export function scopeCriteria(value: string): Pick<SearchCriteria, 'service_id' | 'activity_type_id'> {
  const [kind, id] = value.split(/:(.*)/);
  return { service_id: kind === 'service' ? id || null : null, activity_type_id: kind === 'activity' ? id || null : null };
}

/** The labels of the text field and the select: without ticket entries there are no ticket keys and services. */
export function searchLabels(mode: WorkMode): { text: string; scope: string } {
  return hasTickets(mode) ? { text: 'Words or ticket key', scope: 'Service or activity type' }
    : { text: 'Words', scope: 'Activity type' };
}

function scopeOptions(services: ServiceChoice[], activityTypes: ActivityType[], mode: WorkMode): HTMLElement[] {
  const activities = el('optgroup', { label: 'Activity type' },
    ...activityTypes.map((type) => el('option', { value: `activity:${type.id}` }, type.name)));
  return hasTickets(mode) ? [
    el('optgroup', { label: 'Service' },
      ...services.map((service) => el('option', { value: `service:${service.id}` }, service.short_name)),
      el('option', { value: `service:${NO_SERVICE}` }, 'No service')),
    activities,
  ] : [activities];
}

function labelFields(doc: Document, mode: WorkMode): void {
  const labels = searchLabels(mode);
  doc.querySelector('label[for="search-text"]')!.textContent = labels.text;
  doc.querySelector('label[for="search-scope"]')!.textContent = labels.scope;
}

/** Fills the form with the criteria; From and To show only for a custom period; Search opens the URL of the new ones. */
function fillForm(form: HTMLFormElement, criteria: SearchCriteria, options: HTMLElement[], doc: Document): void {
  const control = <T extends HTMLElement>(name: string): T => form.querySelector<T>(`[name="${name}"]`)!;
  const period = control<HTMLSelectElement>('period');
  const showDates = (): void => form.querySelectorAll<HTMLElement>('.search-custom').forEach((field) => {
    field.hidden = period.value !== 'custom';
  });
  control<HTMLSelectElement>('scope').append(...options);
  control<HTMLInputElement>('text').value = criteria.text;
  control<HTMLSelectElement>('scope').value = scopeValue(criteria);
  period.value = criteria.period;
  control<HTMLInputElement>('start').value = criteria.start;
  control<HTMLInputElement>('end').value = criteria.end;
  showDates();
  period.addEventListener('change', showDates);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const value = (name: string): string => control<HTMLInputElement>(name).value;
    const custom = period.value === 'custom';
    const chosen = criteriaFromSearch(`?${query({
      text: value('text'), ...scopeCriteria(value('scope')), period: period.value,
      start: custom ? value('start') : null, end: custom ? value('end') : null,
    })}`);
    doc.location.assign(`/search?${searchQuery(chosen)}`);
  });
}

function summary(result: SearchResult, period: string): HTMLElement {
  return el('div', { class: 'card card-surface week-summary' },
    el('div', {}, el('span', { class: 'muted' }, 'Found '), el('strong', { class: 'num' }, result.duration),
      el('span', { class: 'muted' }, ` in ${result.count} ${result.count === 1 ? 'entry' : 'entries'}`)),
    el('div', { class: 'muted' }, period));
}

/** A card with a row per group or month: label, number of entries, hours. */
function sumCard(title: string, column: string, rows: [HTMLElement, number, string][]): HTMLElement {
  return el('div', { class: 'card' }, el('h2', {}, title),
    scrolling(el('table', { class: 'card-table' },
      el('thead', {}, el('tr', {}, el('th', {}, column),
        el('th', { class: 'num' }, 'Entries'), el('th', { class: 'num' }, 'Hours'))),
      el('tbody', {}, ...rows.map(([label, count, duration]) => el('tr', {},
        el('td', {}, label), el('td', { class: 'num' }, String(count)), el('td', { class: 'num' }, duration)))))));
}

function entryRow(entry: EntryView, fail: (error: unknown) => void): HTMLElement {
  const link = weekLink(entry.date, `entry=${entry.id}`);
  return el('tr', {},
    el('td', { class: 'num' }, el('a', { href: link }, formatDate(entry.date))),
    el('td', {}, el('div', { class: 'entry' }, ...entryContent(entry, false))),
    el('td', { class: 'row-actions' }, el('a', { class: 'button button-small', href: link }, 'Open'),
      detailsButton(entry.ticket_key ?? entry.activity_type ?? 'Entry without ticket', [entry], fail)));
}

/** The entries listed; while not all are, a note and "Show all" to load the rest. */
function entriesList(result: SearchResult, showAll: () => Promise<SearchResult>, fail: (error: unknown) => void): HTMLElement {
  const section = el('section', { class: 'search-entries' }, el('h2', {}, 'Entries'),
    scrolling(el('table', { class: 'review-table' },
      el('tbody', {}, ...result.entries.map((entry) => entryRow(entry, fail))))));
  if (result.entries.length < result.count) {
    const more = button('Show all', () => void showAll().then((all) => section.replaceWith(entriesList(all, showAll, fail)), fail),
      { class: 'button' });
    section.append(el('p', { class: 'search-more' },
      el('span', { class: 'muted' }, `The newest ${result.entries.length} of ${result.count} entries. `), more));
  }
  return section;
}

function results(result: SearchResult, period: string, showAll: () => Promise<SearchResult>,
  fail: (error: unknown) => void): HTMLElement[] {
  if (!result.count) {
    return [summary(result, period), el('p', { class: 'muted' }, 'No entries found.')];
  }
  return [
    summary(result, period),
    el('div', { class: 'search-cards' },
      sumCard('By ticket or activity type', 'Ticket or activity', result.groups.map((group) => [
        group.kind === 'activity' ? el('span', {}, group.key ?? '', el('span', { class: 'muted' }, ' · activity'))
          : el('strong', { class: group.key ? '' : 'value-negative' }, group.key ?? 'No ticket'),
        group.entries, group.duration])),
      sumCard('By month', 'Month', result.months.map((month) => [
        el('a', { href: `/month?month=${month.month}` }, formatMonth(month.month)), month.entries, month.duration]))),
    entriesList(result, showAll, fail),
  ];
}

export async function renderSearchPage(doc: Document): Promise<void> {
  const root = doc.querySelector<HTMLElement>('#search');
  const form = doc.querySelector<HTMLFormElement>('#search-form');
  if (!root || !form) {
    return;
  }
  const criteria = criteriaFromSearch(doc.location.search);
  const today = isoDate(new Date());
  const fail = (error: unknown): void => root.prepend(el('div', { class: 'card is-warning', role: 'alert' },
    errorText(error, 'Something went wrong.')));
  try {
    const [services, activityTypes, settings] = await Promise.all([api.serviceChoices(), api.activityTypes(), api.settings()]);
    const mode = settings.work_mode;
    labelFields(doc, mode);
    fillForm(form, criteria, scopeOptions(services, activityTypes, mode), doc);
    if (!doc.location.search) {  // nothing asked yet
      return;
    }
    root.replaceChildren(el('p', { class: 'muted' }, 'Searching…'));
    const showAll = (): Promise<SearchResult> => api.search(apiQuery(criteria, today, null));
    const period = describePeriod(criteria.period, periodRange(criteria, today));
    root.replaceChildren(...results(await api.search(apiQuery(criteria, today, LIMIT)), period, showAll, fail));
  } catch (error) {
    root.replaceChildren(el('div', { class: 'card is-warning', role: 'alert' }, errorText(error, 'The search failed.')));
  }
}
