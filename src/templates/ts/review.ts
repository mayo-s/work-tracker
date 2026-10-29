// Review page (/review): tickets without service, entries and days that need attention after the import.

import {
  api, ApiError, type DayView, type ReviewEntry, type ReviewReason, type ReviewView, type ServiceChoice, type TicketView,
} from './api.ts';
import { formatDay, isoWeek, type IsoDate } from './dates.ts';
import { el, onEscape } from './dom.ts';
import { serviceOptions } from './lists.ts';
import { entryContent } from './week.ts';

export const REASON_LABELS: Record<ReviewReason, string> = {
  uncertain_ticket: 'Ticket guessed',
  zero_duration: 'No duration',
  no_ticket: 'No ticket',
};

/** A link into the week view of a date, e.g. `/week?week=2024-W45&entry=129`. */
export function weekLink(date: IsoDate, parameter: string): string {
  return `/week?week=${isoWeek(date)}&${parameter}`;
}

export function reviewTotal(counts: ReviewView['counts']): number {
  return counts.tickets_without_service + counts.entries + counts.days;
}

/** Tickets whose key contains the filter text (case-insensitive). */
export function filterTickets(tickets: TicketView[], text: string): TicketView[] {
  const filter = text.trim().toUpperCase();
  return filter ? tickets.filter((ticket) => ticket.key.includes(filter)) : tickets;
}

/** Flagged entries of one guessed ticket key, e.g. TNG-4057 from `#4057` in the spreadsheet. */
export type GuessedTicket = {
  key: string;
  entries: ReviewEntry['entry'][];
  originals: string[];
  flagIds: number[];
  /** Per original line: all entries the import made from it, if it named several tickets. */
  splits: Record<string, ReviewEntry['split_on_import']>;
};

/** Guessed tickets grouped by key (in order of their first entry), and the entries that need a fix of their own. */
export function groupReview(entries: ReviewEntry[]): { guessed: GuessedTicket[]; others: ReviewEntry[] } {
  const guessed = new Map<string, GuessedTicket>();
  const others: ReviewEntry[] = [];
  for (const item of entries) {
    const key = item.entry.ticket_key;
    if (key && item.reasons.includes('uncertain_ticket')) {
      const group = guessed.get(key) ?? { key, entries: [], originals: [], flagIds: [], splits: {} };
      group.entries.push(item.entry);
      group.flagIds.push(...item.entry.flags.map((flag) => flag.id));
      for (const detail of item.entry.flags.map((flag) => flag.detail)) {
        if (!group.originals.includes(detail)) {
          group.originals.push(detail);
        }
        if (item.split_on_import.length) {
          group.splits[detail] = item.split_on_import;
        }
      }
      guessed.set(key, group);
    }
    const reasons = item.reasons.filter((reason) => reason !== 'uncertain_ticket' || !key);
    if (reasons.length) {
      others.push({ ...item, reasons });
    }
  }
  return { guessed: [...guessed.values()], others };
}

const MENTIONED = /\b(KP|TNG|ENGINE|AGA|MSI)[- ]?(\d+)|#\s?(\d+)/gi;
const ALIAS = /\baka\b|#\s?\d+\s*\/\s*#\s?\d+/i;
const FOLLOWING = /\d+ff\b/i;

/** Ticket keys mentioned in a spreadsheet line, e.g. `#4347 aka #1482` → TNG-4347, KP-1482 (as in the import). */
export function mentionedTickets(line: string): string[] {
  const keys = [...line.matchAll(MENTIONED)].map(([, prefix, number, bare]) => prefix
    ? `${prefix.toUpperCase()}-${Number(number)}`
    : `${Number(bare) >= 4000 ? 'TNG' : 'KP'}-${Number(bare)}`);
  return [...new Set(keys)];
}

/** Tickets to split a guessed ticket into, if its spreadsheet line had an alias or "ff"; null if there is nothing to split. */
export function splitSuggestion(group: GuessedTicket): string[] | null {
  const originals = group.originals.filter((line) => ALIAS.test(line) || FOLLOWING.test(line));
  if (!originals.length) {
    return null;
  }
  return [...new Set([group.key, ...originals.flatMap(mentionedTickets)])];
}

type Page = { data: ReviewView; services: ServiceChoice[]; reload: (message: string) => void; fail: (error: unknown) => void };

function button(label: string, onClick: () => void, className = 'button-small'): HTMLButtonElement {
  const element = el('button', { type: 'button', class: className }, label);
  element.addEventListener('click', onClick);
  return element;
}

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : 'The action failed.';
}

function act(page: Page, action: () => Promise<unknown>, message: string): void {
  action().then(() => page.reload(message), page.fail);
}

function clearFlags(flagIds: number[]): Promise<unknown> {
  return Promise.all(flagIds.map((id) => api.clearFlag(id)));
}

/** An inline form to rename a ticket, or merge it into an existing one; `flagIds` are cleared afterwards. */
function renameForm(key: string, page: Page, onCancel: () => void, flagIds: number[] = []): HTMLElement {
  const input = el('input', { value: key, 'aria-label': `New key for ${key}`, autocomplete: 'off', class: 'rename-input' });
  const form = el('form', { class: 'rename-form' }, input,
    el('button', { type: 'submit', class: 'button-small primary' }, 'Rename'), button('Cancel', onCancel));
  onEscape(form, onCancel);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const newKey = input.value.trim().toUpperCase();
    api.renameTicket(key, newKey).then(async (result) => {
      await clearFlags(flagIds);
      return result;
    }).then(
      (result) => page.reload(`${key} ${result.action === 'merged' ? 'merged into' : 'renamed to'} ${result.ticket.key} `
        + `(${result.moved} ${result.moved === 1 ? 'entry' : 'entries'})`),
      page.fail,
    );
  });
  queueMicrotask(() => input.select());
  return form;
}

/** Shows `form` in place of the cell's content; canceling restores the content and focuses `opener` again. */
function openInCell(cell: HTMLElement, opener: HTMLElement, form: (cancel: () => void) => HTMLElement): void {
  const original = [...cell.childNodes];
  cell.replaceChildren(form(() => {
    cell.replaceChildren(...original);
    opener.focus();
  }));
}

function renameAction(key: string, page: Page, cell: HTMLElement, flagIds: number[] = []): HTMLButtonElement {
  const rename: HTMLButtonElement = button('Rename',
    () => openInCell(cell, rename, (cancel) => renameForm(key, page, cancel, flagIds)));
  return rename;
}

function ticketRow(ticket: TicketView, page: Page, selected: Set<string>, onSelect: () => void): HTMLElement {
  const checkbox = el('input', { type: 'checkbox', 'aria-label': `Select ${ticket.key}`, checked: selected.has(ticket.key) });
  checkbox.addEventListener('change', () => {
    if (checkbox.checked) {
      selected.add(ticket.key);
    } else {
      selected.delete(ticket.key);
    }
    onSelect();
  });
  const actions = el('td', { class: 'row-actions' });
  actions.append(renameAction(ticket.key, page, actions));
  return el('tr', { 'data-key': ticket.key },
    el('td', { class: 'select-cell' }, checkbox),
    el('td', {}, el('strong', {}, ticket.key)),
    el('td', { class: 'num' }, String(ticket.entries)),
    actions);
}

function serviceSelect(services: ServiceChoice[]): HTMLSelectElement {
  return el('select', { 'aria-label': 'Service to assign' },
    ...serviceOptions(services, (service) => `${service.short_name}${service.name ? ` · ${service.name}` : ''}`));
}

function ticketsSection(page: Page): HTMLElement {
  const tickets = page.data.tickets_without_service;
  const selected = new Set<string>();
  const filter = el('input', { type: 'search', placeholder: 'Filter, e.g. AGA or TNG-49', 'aria-label': 'Filter tickets' });
  const selectAll = el('input', { type: 'checkbox', 'aria-label': 'Select all shown tickets' });
  const services = serviceSelect(page.services);
  const assign = el('button', { type: 'button', class: 'primary', disabled: true }, 'Assign');
  const rows = tickets.map((ticket) => ticketRow(ticket, page, selected, () => update()));
  const update = (): void => {
    assign.disabled = selected.size === 0;
    assign.textContent = selected.size ? `Assign to ${selected.size} selected` : 'Assign';
  };
  filter.addEventListener('input', () => {
    const shown = new Set(filterTickets(tickets, filter.value).map((ticket) => ticket.key));
    rows.forEach((row) => (row.hidden = !shown.has(row.dataset.key ?? '')));
    selectAll.checked = false;
  });
  selectAll.addEventListener('change', () => {
    for (const row of rows.filter((item) => !item.hidden)) {
      const checkbox = row.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
      checkbox.checked = selectAll.checked;
      checkbox.dispatchEvent(new Event('change'));
    }
  });
  assign.addEventListener('click', () => {
    const service = page.services.find((item) => String(item.id) === services.value);
    act(page, () => api.assignService([...selected], Number(services.value)),
      `${service?.short_name ?? 'Service'} assigned to ${selected.size} ${selected.size === 1 ? 'ticket' : 'tickets'}`);
  });
  return el('section', { class: 'review-section', id: 'tickets' },
    el('h2', {}, 'Tickets without service ', el('span', { class: 'badge warning' }, String(tickets.length))),
    el('p', { class: 'muted' }, 'A service applies to all entries of a ticket. Filter, select, then assign.'),
    tickets.length ? el('div', { class: 'review-toolbar' }, filter, services, assign) : null,
    tickets.length
      ? el('table', { class: 'review-table' },
        el('thead', {}, el('tr', {}, el('th', { class: 'select-cell' }, selectAll), el('th', {}, 'Ticket'),
          el('th', { class: 'num' }, 'Entries'), el('th', {}, el('span', { class: 'visually-hidden' }, 'Actions')))),
        el('tbody', {}, ...rows))
      : el('p', {}, 'All tickets have a service.'),
  );
}

function flagActions(flags: { id: number }[], page: Page): HTMLElement[] {
  return flags.map((flag) => button('Done', () => act(page, () => api.clearFlag(flag.id), 'Flag cleared')));
}

function formatDate(date: IsoDate): string {
  return date.split('-').reverse().join('.');
}

/** An inline form to split all entries of a guessed ticket among several tickets; clears their flags afterwards. */
function splitForm(group: GuessedTicket, suggestion: string[], page: Page, onCancel: () => void): HTMLElement {
  const input = el('input', { value: suggestion.join(', '), 'aria-label': `Split ${group.key} into`, autocomplete: 'off',
    class: 'split-input' });
  const form = el('form', { class: 'rename-form' }, input,
    el('button', { type: 'submit', class: 'button-small primary' }, 'Split'), button('Cancel', onCancel));
  onEscape(form, onCancel);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const keys = input.value.split(/[\s,;/]+/).map((key) => key.trim().toUpperCase()).filter(Boolean);
    const run = async (): Promise<void> => {
      for (const entry of group.entries) {
        await api.splitEntry(entry.id, keys);
      }
      await clearFlags(group.flagIds);
    };
    run().then(() => page.reload(`${group.key} split into ${keys.join(', ')} (${group.entries.length} `
      + `${group.entries.length === 1 ? 'entry' : 'entries'})`), page.fail);
  });
  queueMicrotask(() => input.focus());
  return form;
}

/** `TNG-4138 3:00 · TNG-4139 3:00` */
export function describeSplit(parts: ReviewEntry['split_on_import']): string {
  return parts.map((part) => `${part.ticket_key ?? 'No ticket'} ${part.duration}`).join(' · ');
}

function originalLine(original: string, split: ReviewEntry['split_on_import'] | undefined): HTMLElement {
  return el('div', {}, `Original: ${original}`,
    split?.length ? el('div', { class: 'muted' }, 'Split on import: ', el('span', { class: 'num' }, describeSplit(split))) : null);
}

function guessedRow(group: GuessedTicket, page: Page): HTMLElement {
  const first = group.entries[0]!;
  const count = `${group.entries.length} ${group.entries.length === 1 ? 'entry' : 'entries'}`;
  const actions = el('td', { class: 'row-actions' },
    el('a', { class: 'button button-small', href: weekLink(first.date, `entry=${first.id}`) }, 'Open'),
    button('Key is right', () => act(page, () => clearFlags(group.flagIds), `${group.key} confirmed (${count})`)));
  actions.append(renameAction(group.key, page, actions, group.flagIds));
  const suggestion = splitSuggestion(group);
  if (suggestion) {
    const split: HTMLButtonElement = button('Split',
      () => openInCell(actions, split, (cancel) => splitForm(group, suggestion, page, cancel)));
    actions.append(split);
  }
  const shown = group.originals.slice(0, 3);
  return el('tr', {},
    el('td', {}, el('strong', {}, group.key), el('div', { class: 'muted' }, count)),
    el('td', {},
      el('div', { class: 'muted' }, formatDate(first.date),
        group.entries.length > 1 ? ` – ${formatDate(group.entries[group.entries.length - 1]!.date)}` : ''),
      ...shown.map((original) => originalLine(original, group.splits[original])),
      group.originals.length > shown.length ? el('div', { class: 'muted' }, `… and ${group.originals.length - shown.length} more`) : null),
    actions);
}

function guessedSection(groups: GuessedTicket[], page: Page): HTMLElement {
  const entries = groups.reduce((sum, group) => sum + group.entries.length, 0);
  return el('section', { class: 'review-section', id: 'guessed' },
    el('h2', {}, 'Guessed tickets ', el('span', { class: 'badge warning' }, String(groups.length))),
    el('p', { class: 'muted' },
      `${entries} entries got their ticket key from old numbers (#4057 → TNG-4057, lower numbers → KP), aliases or "ff". `
      + 'Confirm the key, rename the ticket, or split it if the spreadsheet named several; each clears the flags of all '
      + 'its entries.'),
    groups.length
      ? el('table', { class: 'review-table' },
        el('thead', {}, el('tr', {}, el('th', {}, 'Ticket'), el('th', {}, 'Spreadsheet'),
          el('th', {}, el('span', { class: 'visually-hidden' }, 'Actions')))),
        el('tbody', {}, ...groups.map((group) => guessedRow(group, page))))
      : el('p', {}, 'Nothing to review.'),
  );
}

function entryRow(item: ReviewEntry, page: Page): HTMLElement {
  const entry = item.entry;
  const link = weekLink(entry.date, `entry=${entry.id}`);
  return el('tr', {},
    el('td', { class: 'num' }, el('a', { href: link }, formatDate(entry.date))),
    el('td', {},
      el('div', { class: 'entry' }, ...entryContent(entry, false)),
      el('div', {}, ...item.reasons.map((reason) => el('span', { class: 'badge warning' }, REASON_LABELS[reason])))),
    el('td', { class: 'row-actions' }, el('a', { class: 'button button-small', href: link }, 'Open'),
      ...flagActions(entry.flags.filter(() => item.reasons.includes('uncertain_ticket')), page)));
}

function entriesSection(others: ReviewEntry[], page: Page): HTMLElement {
  return el('section', { class: 'review-section', id: 'entries' },
    el('h2', {}, 'Entries ', el('span', { class: 'badge warning' }, String(others.length))),
    el('p', { class: 'muted' }, 'Entries without duration or without ticket; open them in the week view to fix them.'),
    others.length
      ? el('table', { class: 'review-table' }, el('tbody', {}, ...others.map((item) => entryRow(item, page))))
      : el('p', {}, 'Nothing to review.'),
  );
}

function dayRow(day: DayView, page: Page): HTMLElement {
  return el('tr', {},
    el('td', {}, el('a', { href: weekLink(day.date, `edit=${day.date}`) }, formatDay(day.date, day.weekday)),
      el('div', { class: 'muted' }, day.date.slice(0, 4))),
    el('td', { class: 'num' }, day.worked),
    el('td', {}, ...day.flags.map((flag) => el('div', { class: 'muted' }, flag.detail))),
    el('td', { class: 'row-actions' },
      el('a', { class: 'button button-small', href: weekLink(day.date, `edit=${day.date}`) }, 'Open day'),
      ...flagActions(day.flags, page)));
}

function daysSection(page: Page): HTMLElement {
  const days = page.data.days;
  return el('section', { class: 'review-section', id: 'days' },
    el('h2', {}, 'Days ', el('span', { class: 'badge warning' }, String(days.length))),
    el('p', { class: 'muted' }, 'Weekend hours the spreadsheet counted differently. Check the times, then mark as done.'),
    days.length
      ? el('table', { class: 'review-table' },
        el('thead', {}, el('tr', {}, el('th', {}, 'Day'), el('th', { class: 'num' }, 'Worked'), el('th', {}, 'Spreadsheet'),
          el('th', {}, el('span', { class: 'visually-hidden' }, 'Actions')))),
        el('tbody', {}, ...days.map((day) => dayRow(day, page))))
      : el('p', {}, 'Nothing to review.'),
  );
}

export async function renderReviewPage(doc: Document): Promise<void> {
  const root = doc.querySelector<HTMLElement>('#review');
  const status = doc.querySelector<HTMLElement>('#review-status');
  if (!root || !status) {
    return;
  }
  const show = (message: string, warning = false): void => {
    status.textContent = message;
    status.className = warning ? 'review-status field-error' : 'review-status value-positive';
    status.hidden = !message;
  };
  const load = async (message = ''): Promise<void> => {
    try {
      const [data, services] = await Promise.all([api.review(), api.serviceChoices()]);
      const page: Page = { data, services, reload: (text) => void load(text), fail: (error) => show(errorText(error), true) };
      const { guessed, others } = groupReview(data.entries);
      root.replaceChildren(guessedSection(guessed, page), entriesSection(others, page), daysSection(page), ticketsSection(page));
      show(message);
    } catch (error) {
      root.replaceChildren(el('div', { class: 'card is-warning', role: 'alert' }, errorText(error)));
    }
  };
  root.replaceChildren(el('p', { class: 'muted' }, 'Loading…'));
  await load();
}
