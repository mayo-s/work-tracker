// Search (/search): finds entries of a period by text, service or activity type and sums them up by ticket or activity
// type and by month. The criteria are in the URL (`?text=…&service_id=…&start=…&end=…`), as the API takes them.

import { api, errorText, type ActivityType, type EntryView, type SearchResult, type ServiceChoice } from './api.ts';
import { formatDate, formatMonth, isoDate, weekLink, type IsoDate } from './dates.ts';
import { el, scrolling } from './dom.ts';
import { detailsButton } from './entry-details.ts';
import { entryContent } from './week.ts';

const NO_SERVICE = 'none';
const DATE = /^\d{4}-\d{2}-\d{2}$/;

/** What to search for: text, at most one of service (`none`: tickets without service) and activity type, period. */
export type SearchCriteria = {
  text: string; service_id: string | null; activity_type_id: string | null; start: IsoDate; end: IsoDate;
};

/** The criteria from the URL; the period defaults to this year. */
export function criteriaFromSearch(search: string, today: IsoDate): SearchCriteria {
  const params = new URLSearchParams(search);
  const date = (name: string, fallback: IsoDate): IsoDate => {
    const value = params.get(name);
    return value && DATE.test(value) ? value : fallback;
  };
  return {
    text: params.get('text')?.trim() ?? '', service_id: params.get('service_id') || null,
    activity_type_id: params.get('activity_type_id') || null,
    start: date('start', `${today.slice(0, 4)}-01-01`), end: date('end', `${today.slice(0, 4)}-12-31`),
  };
}

/** The query of the criteria, for the URL and the API; empty ones left out. */
export function searchQuery(criteria: SearchCriteria): string {
  const params = Object.entries(criteria).filter((pair): pair is [string, string] => Boolean(pair[1]));
  return new URLSearchParams(params).toString();
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

function scopeOptions(services: ServiceChoice[], activityTypes: ActivityType[]): HTMLElement[] {
  return [
    el('optgroup', { label: 'Service' },
      ...services.map((service) => el('option', { value: `service:${service.id}` }, service.short_name)),
      el('option', { value: `service:${NO_SERVICE}` }, 'No service')),
    el('optgroup', { label: 'Activity type' },
      ...activityTypes.map((type) => el('option', { value: `activity:${type.id}` }, type.name))),
  ];
}

function fillForm(form: HTMLFormElement, criteria: SearchCriteria, options: HTMLElement[], doc: Document): void {
  const control = <T extends HTMLElement>(name: string): T => form.querySelector<T>(`[name="${name}"]`)!;
  control<HTMLSelectElement>('scope').append(...options);
  control<HTMLInputElement>('text').value = criteria.text;
  control<HTMLSelectElement>('scope').value = scopeValue(criteria);
  control<HTMLInputElement>('start').value = criteria.start;
  control<HTMLInputElement>('end').value = criteria.end;
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const value = (name: string): string => control<HTMLInputElement>(name).value;
    const chosen = { text: value('text').trim(), ...scopeCriteria(value('scope')), start: value('start'), end: value('end') };
    doc.location.assign(`/search?${searchQuery(chosen)}`);
  });
}

function summary(result: SearchResult): HTMLElement {
  return el('div', { class: 'card card-surface week-summary' },
    el('div', {}, el('span', { class: 'muted' }, 'Found '), el('strong', { class: 'num' }, result.duration),
      el('span', { class: 'muted' }, ` in ${result.count} ${result.count === 1 ? 'entry' : 'entries'}`)),
    el('div', { class: 'muted' }, `${formatDate(result.start)} – ${formatDate(result.end)}`));
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

function results(result: SearchResult, fail: (error: unknown) => void): HTMLElement[] {
  if (!result.count) {
    return [summary(result), el('p', { class: 'muted' }, 'No entries found.')];
  }
  return [
    summary(result),
    el('div', { class: 'search-cards' },
      sumCard('By ticket or activity type', 'Ticket or activity', result.groups.map((group) => [
        group.kind === 'activity' ? el('span', {}, group.key ?? '', el('span', { class: 'muted' }, ' · activity'))
          : el('strong', { class: group.key ? '' : 'value-negative' }, group.key ?? 'No ticket'),
        group.entries, group.duration])),
      sumCard('By month', 'Month', result.months.map((month) => [
        el('a', { href: `/month?month=${month.month}` }, formatMonth(month.month)), month.entries, month.duration]))),
    el('h2', {}, 'Entries'),
    scrolling(el('table', { class: 'review-table' },
      el('tbody', {}, ...result.entries.map((entry) => entryRow(entry, fail))))),
  ];
}

export async function renderSearchPage(doc: Document): Promise<void> {
  const root = doc.querySelector<HTMLElement>('#search');
  const form = doc.querySelector<HTMLFormElement>('#search-form');
  if (!root || !form) {
    return;
  }
  const criteria = criteriaFromSearch(doc.location.search, isoDate(new Date()));
  const fail = (error: unknown): void => root.prepend(el('div', { class: 'card is-warning', role: 'alert' },
    errorText(error, 'Something went wrong.')));
  try {
    const [services, activityTypes] = await Promise.all([api.serviceChoices(), api.activityTypes()]);
    fillForm(form, criteria, scopeOptions(services, activityTypes), doc);
    if (!doc.location.search) {  // nothing asked yet
      return;
    }
    root.replaceChildren(el('p', { class: 'muted' }, 'Searching…'));
    root.replaceChildren(...results(await api.search(searchQuery(criteria)), fail));
  } catch (error) {
    root.replaceChildren(el('div', { class: 'card is-warning', role: 'alert' }, errorText(error, 'The search failed.')));
  }
}
