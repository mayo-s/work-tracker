// Review page (/review): tickets without service, entries without activity type, and entries and days that need
// attention after the import.

import {
  api, errorText, type ActivityType, type DayView, type EntryView, type ReviewCounts, type ReviewEntry, type ReviewReason,
  type ReviewView, type ServiceChoice, type TicketView,
} from './api.ts';
import { formatDate, formatDay, weekLink } from './dates.ts';
import { button, el, onEscape, scrolling } from './dom.ts';
import { detailsButton } from './entry-details.ts';
import { serviceOptions } from './lists.ts';
import { entryContent } from './week.ts';

export const REASON_LABELS: Record<ReviewReason, string> = {
  uncertain_ticket: 'Ticket guessed',
  zero_duration: 'No duration',
  no_ticket: 'No ticket',
  no_activity_type: 'No activity type',
};

export function reviewTotal(counts: ReviewCounts): number {
  return counts.tickets_without_service + counts.entries + counts.days;
}

/** Shows the number of open review items next to the Review link of the navigation, as a warning badge (none at 0),
 * and the link itself while there are any; replaces the badge shown before, so the count follows every review action. */
export function showReviewBadge(doc: Document, counts: ReviewCounts): void {
  const link = doc.querySelector<HTMLElement>('.app-nav a[href="/review"]');
  if (!link) {
    return;
  }
  const shown = link.querySelector('.badge');
  shown?.previousSibling?.remove();  // the space before it
  shown?.remove();
  const total = reviewTotal(counts);
  if (total) {
    link.hidden = false;
    link.append(' ', el('span', { class: 'badge warning' }, String(total)));
  }
}

/** The descriptions of the entries, each once (ignoring case), in order. */
export function entryTexts(entries: EntryView[]): string[] {
  const texts = new Map<string, string>();
  for (const entry of entries) {
    const text = entry.description.trim();
    if (text && !texts.has(text.toLowerCase())) {
      texts.set(text.toLowerCase(), text);
    }
  }
  return [...texts.values()];
}

/** Tickets whose key contains the filter text (case-insensitive). */
export function filterTickets(tickets: TicketView[], text: string): TicketView[] {
  const filter = text.trim().toUpperCase();
  return filter ? tickets.filter((ticket) => ticket.key.includes(filter)) : tickets;
}

/** Entries whose ticket key starts with, or whose description or activity type contains, the filter text (ignoring
 * case). */
export function filterEntries(items: ReviewEntry[], text: string): ReviewEntry[] {
  const filter = text.trim().toLowerCase();
  return items.filter(({ entry }) => (entry.ticket_key ?? '').toLowerCase().startsWith(filter)
    || entry.description.toLowerCase().includes(filter));
}

/** Flagged entries of one guessed ticket key, e.g. TNG-4057 from `#4057` in the spreadsheet. */
export type GuessedTicket = {
  key: string;
  entries: ReviewEntry['entry'][];
  originals: string[];
  flagIds: string[];
  /** Tickets to split into, from aliases or "ff" in the original lines (suggested by the API). */
  suggested: string[];
  /** Per original line: all entries the import made from it, if it named several tickets. */
  splits: Record<string, ReviewEntry['split_on_import']>;
};

/** Guessed tickets grouped by key (in order of their first entry), the entries without activity type (to choose one
 * for several at once), and the other entries that need a fix of their own. */
export function groupReview(entries: ReviewEntry[]): {
  guessed: GuessedTicket[]; untyped: ReviewEntry[]; others: ReviewEntry[];
} {
  const guessed = new Map<string, GuessedTicket>();
  const others: ReviewEntry[] = [];
  for (const item of entries) {
    const key = item.entry.ticket_key;
    if (key && item.reasons.includes('uncertain_ticket')) {
      const group = guessed.get(key) ?? { key, entries: [], originals: [], flagIds: [], suggested: [], splits: {} };
      group.entries.push(item.entry);
      group.suggested.push(...item.split_suggestion);
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
  const untyped = others.filter((item) => item.reasons.includes('no_activity_type'));
  return { guessed: [...guessed.values()], untyped, others: others.filter((item) => !untyped.includes(item)) };
}

/** Tickets to split a guessed ticket into, if its spreadsheet line had an alias or "ff"; null if there is nothing to split. */
export function splitSuggestion(group: GuessedTicket): string[] | null {
  return group.suggested.length ? [...new Set([group.key, ...group.suggested])] : null;
}

type Page = {
  data: ReviewView; services: ServiceChoice[]; activityTypes: ActivityType[]; reload: (message: string) => void;
  fail: (error: unknown) => void;
};

function act(page: Page, action: () => Promise<unknown>, message: string): void {
  action().then(() => page.reload(message), page.fail);
}

function clearFlags(flagIds: string[]): Promise<unknown> {
  return Promise.all(flagIds.map((id) => api.clearFlag(id)));
}

/** An inline form to rename a ticket, or merge it into an existing one; `flagIds` are cleared afterwards. */
function renameForm(key: string, page: Page, onCancel: () => void, flagIds: string[] = []): HTMLElement {
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

function renameAction(key: string, page: Page, cell: HTMLElement, flagIds: string[] = []): HTMLButtonElement {
  const rename: HTMLButtonElement = button('Rename',
    () => openInCell(cell, rename, (cancel) => renameForm(key, page, cancel, flagIds)));
  return rename;
}

/** Rows to select (each `data-key`), with a filter, "select all shown" and a button that assigns the chosen value of
 * `choice` to the selected rows. `shown` gives the keys a filter text leaves. */
type BulkAssign = {
  noun: [string, string]; filterLabel: string; placeholder: string; choice: HTMLSelectElement;
  shown: (text: string) => Set<string>; assign: (keys: string[]) => void;
};

function bulkAssign(options: BulkAssign): {
  toolbar: HTMLElement; selectAll: HTMLInputElement; select: (row: HTMLElement) => HTMLElement;
} {
  const selected = new Set<string>();
  const rows: HTMLElement[] = [];
  const filter = el('input', { type: 'search', placeholder: options.placeholder, 'aria-label': options.filterLabel });
  const selectAll = el('input', { type: 'checkbox', 'aria-label': `Select all shown ${options.noun[1]}` });
  const assign = el('button', { type: 'button', class: 'primary', disabled: true }, 'Assign');
  filter.addEventListener('input', () => {
    const shown = options.shown(filter.value);
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
  assign.addEventListener('click', () => options.assign([...selected]));
  /** The row with its checkbox in a first cell. */
  const select = (row: HTMLElement): HTMLElement => {
    const key = row.dataset.key ?? '';
    const checkbox = el('input', { type: 'checkbox', 'aria-label': `Select ${row.dataset.label ?? key}` });
    checkbox.addEventListener('change', () => {
      if (checkbox.checked) {
        selected.add(key);
      } else {
        selected.delete(key);
      }
      assign.disabled = selected.size === 0;
      assign.textContent = selected.size ? `Assign to ${selected.size} selected` : 'Assign';
    });
    row.prepend(el('td', { class: 'select-cell' }, checkbox));
    rows.push(row);
    return row;
  };
  return { toolbar: el('div', { class: 'review-toolbar' }, filter, options.choice, assign), selectAll, select };
}

/** A count with its noun in the singular or plural, e.g. `2 tickets`. */
function counted(count: number, noun: [string, string]): string {
  return `${count} ${count === 1 ? noun[0] : noun[1]}`;
}

function ticketRow(ticket: TicketView, page: Page): HTMLElement {
  const actions = el('td', { class: 'row-actions' });
  actions.append(renameAction(ticket.key, page, actions));
  return el('tr', { 'data-key': ticket.key },
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
  const noun: [string, string] = ['ticket', 'tickets'];
  const choice = serviceSelect(page.services);
  const bulk = bulkAssign({
    noun, filterLabel: 'Filter tickets', placeholder: 'Filter, e.g. AGA or TNG-49', choice,
    shown: (text) => new Set(filterTickets(tickets, text).map((ticket) => ticket.key)),
    assign: (keys) => {
      const service = page.services.find((item) => String(item.id) === choice.value);
      act(page, () => api.assignService(keys, choice.value),
        `${service?.short_name ?? 'Service'} assigned to ${counted(keys.length, noun)}`);
    },
  });
  return el('section', { class: 'review-section', id: 'tickets' },
    el('h2', {}, 'Tickets without service ', el('span', { class: 'badge warning' }, String(tickets.length))),
    el('p', { class: 'muted' }, 'A service applies to all entries of a ticket. Filter, select, then assign.'),
    tickets.length ? bulk.toolbar : null,
    tickets.length
      ? scrolling(el('table', { class: 'review-table' },
        el('thead', {}, el('tr', {}, el('th', { class: 'select-cell' }, bulk.selectAll), el('th', {}, 'Ticket'),
          el('th', { class: 'num' }, 'Entries'), el('th', {}, el('span', { class: 'visually-hidden' }, 'Actions')))),
        el('tbody', {}, ...tickets.map((ticket) => bulk.select(ticketRow(ticket, page))))))
      : el('p', {}, 'All tickets have a service.'),
  );
}

function flagActions(flags: { id: string }[], page: Page): HTMLElement[] {
  return flags.map((flag) => button('Done', () => act(page, () => api.clearFlag(flag.id), 'Flag cleared')));
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
  actions.append(detailsButton(`${group.key}: ${count}`, group.entries, page.fail));
  const shown = group.originals.slice(0, 3);
  const texts = entryTexts(group.entries);
  return el('tr', {},
    el('td', {}, el('strong', {}, group.key), el('div', { class: 'muted' }, count),
      texts.length ? el('div', { class: 'entry-text' }, texts.slice(0, 3).join(' · ') + (texts.length > 3 ? ' · …' : '')) : null),
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
      ? scrolling(el('table', { class: 'review-table' },
        el('thead', {}, el('tr', {}, el('th', {}, 'Ticket'), el('th', {}, 'Spreadsheet'),
          el('th', {}, el('span', { class: 'visually-hidden' }, 'Actions')))),
        el('tbody', {}, ...groups.map((group) => guessedRow(group, page)))))
      : el('p', {}, 'Nothing to review.'),
  );
}

function entryRow(item: ReviewEntry, page: Page): HTMLElement {
  const entry = item.entry;
  const link = weekLink(entry.date, `entry=${entry.id}`);
  const label = `${entry.ticket_key ?? entry.description} of ${formatDate(entry.date)}`;  // for its checkbox
  return el('tr', { 'data-key': entry.id, 'data-label': label },
    el('td', { class: 'num' }, el('a', { href: link }, formatDate(entry.date))),
    el('td', {},
      el('div', { class: 'entry' }, ...entryContent(entry, false)),
      item.original ? el('div', { class: 'muted' }, `Original: ${item.original}`) : null,
      el('div', {}, ...item.reasons.map((reason) => el('span', { class: 'badge warning' }, REASON_LABELS[reason])))),
    el('td', { class: 'row-actions' }, el('a', { class: 'button button-small', href: link }, 'Open'),
      detailsButton(entry.ticket_key ?? entry.activity_type ?? 'Entry without ticket', [entry], page.fail),
      ...flagActions(entry.flags.filter(() => item.reasons.includes('uncertain_ticket')), page)));
}

function activityTypeSelect(activityTypes: ActivityType[]): HTMLSelectElement {
  return el('select', { 'aria-label': 'Activity type to assign' },
    ...activityTypes.map((type) => el('option', { value: type.id ?? '' }, type.name)));
}

/** Former ticket entries whose activity was unclear (SPEC 4.6): choose one, also for several at once. */
function untypedSection(untyped: ReviewEntry[], page: Page): HTMLElement | null {
  if (!untyped.length) {
    return null;
  }
  const noun: [string, string] = ['entry', 'entries'];
  const choice = activityTypeSelect(page.activityTypes);
  const bulk = bulkAssign({
    noun, filterLabel: 'Filter entries', placeholder: 'Filter, e.g. TNG-49 or investigation', choice,
    shown: (text) => new Set(filterEntries(untyped, text).map((item) => item.entry.id)),
    assign: (ids) => {
      const type = page.activityTypes.find((item) => item.id === choice.value);
      act(page, () => api.assignActivityType(ids, choice.value),
        `${type?.name ?? 'Activity type'} assigned to ${counted(ids.length, noun)}`);
    },
  });
  return el('section', { class: 'review-section', id: 'activity-types' },
    el('h2', {}, 'Entries without activity type ', el('span', { class: 'badge warning' }, String(untyped.length))),
    el('p', { class: 'muted' }, 'Ticket entries from before every entry had an activity type, whose activity was not '
      + 'clear. Filter, select, then assign.'),
    bulk.toolbar,
    scrolling(el('table', { class: 'review-table' },
      el('thead', {}, el('tr', {}, el('th', { class: 'select-cell' }, bulk.selectAll), el('th', {}, 'Date'),
        el('th', {}, 'Entry'), el('th', {}, el('span', { class: 'visually-hidden' }, 'Actions')))),
      el('tbody', {}, ...untyped.map((item) => bulk.select(entryRow(  // the section names the missing activity type
        { ...item, reasons: item.reasons.filter((reason) => reason !== 'no_activity_type') }, page)))))),
  );
}

function entriesSection(others: ReviewEntry[], page: Page): HTMLElement {
  return el('section', { class: 'review-section', id: 'entries' },
    el('h2', {}, 'Entries ', el('span', { class: 'badge warning' }, String(others.length))),
    el('p', { class: 'muted' }, 'Entries without duration or without the ticket their activity type requires; open them '
      + 'in the week view to fix them.'),
    others.length
      ? scrolling(el('table', { class: 'review-table' }, el('tbody', {}, ...others.map((item) => entryRow(item, page)))))
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
      ? scrolling(el('table', { class: 'review-table' },
        el('thead', {}, el('tr', {}, el('th', {}, 'Day'), el('th', { class: 'num' }, 'Worked'), el('th', {}, 'Spreadsheet'),
          el('th', {}, el('span', { class: 'visually-hidden' }, 'Actions')))),
        el('tbody', {}, ...days.map((day) => dayRow(day, page)))))
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
      const [data, services, activityTypes] = await Promise.all([api.review(), api.serviceChoices(), api.activityTypes()]);
      const page: Page = {
        data, services, activityTypes, reload: (text) => void load(text), fail: (error) => show(errorText(error), true),
      };
      const { guessed, untyped, others } = groupReview(data.entries);
      root.replaceChildren(guessedSection(guessed, page), untypedSection(untyped, page) ?? '', entriesSection(others, page),
        daysSection(page), ticketsSection(page));
      showReviewBadge(doc, data.counts);
      show(message);
    } catch (error) {
      root.replaceChildren(el('div', { class: 'card is-warning', role: 'alert' }, errorText(error)));
    }
  };
  root.replaceChildren(el('p', { class: 'muted' }, 'Loading…'));
  await load();
}
