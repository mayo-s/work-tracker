// Review page (/review): past days without an end, entries without activity type, other entries with something missing,
// and tickets without service.

import {
  api, errorText, type ActivityType, type DayView, type ReviewCounts, type ReviewEntry, type ReviewReason, type ReviewView,
  type ServiceChoice, type TicketView,
} from './api.ts';
import { formatDate, weekLink } from './dates.ts';
import { button, el, onEscape, scrolling } from './dom.ts';
import { detailsButton } from './entry-details.ts';
import { t, tn } from './i18n.ts';
import { serviceOptions } from './lists.ts';
import { entryContent } from './week.ts';

export const REASON_LABELS: Record<ReviewReason, string> = {
  zero_duration: t('No duration'),
  no_ticket: t('No ticket'),
  no_activity_type: t('No activity type'),
};

export function reviewTotal(counts: ReviewCounts): number {
  return counts.tickets_without_service + counts.entries + counts.open_days;
}

/** Shows the number of open review items next to the Review link of the navigation, as a warning badge (none at 0),
 * and the link itself while there are any; replaces the badge shown before, so the count follows every review action.
 * The same on the header's shortcut for phones (SPEC 5.5a), which shows only while there are any. */
export function showReviewBadge(doc: Document, counts: ReviewCounts): void {
  const total = reviewTotal(counts);
  for (const link of doc.querySelectorAll<HTMLElement>('.app-nav a[href="/review"], .review-shortcut')) {
    const shown = link.querySelector('.badge');
    shown?.previousSibling?.remove();  // the space before it
    shown?.remove();
    if (total) {
      link.hidden = false;
      link.append(' ', el('span', { class: 'badge warning' }, String(total)));
    } else if (link.classList.contains('review-shortcut')) {
      link.hidden = true;
    }
  }
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

/** The entries without activity type (to choose one for several at once), and the others that need a fix of their own. */
export function groupReview(entries: ReviewEntry[]): { untyped: ReviewEntry[]; others: ReviewEntry[] } {
  const untyped = entries.filter((item) => item.reasons.includes('no_activity_type'));
  return { untyped, others: entries.filter((item) => !untyped.includes(item)) };
}

type Page = {
  data: ReviewView; services: ServiceChoice[]; activityTypes: ActivityType[]; reload: (message: string) => void;
  fail: (error: unknown) => void;
};

function act(page: Page, action: () => Promise<unknown>, message: string): void {
  action().then(() => page.reload(message), page.fail);
}

/** An inline form to rename a ticket, or merge it into an existing one. */
function renameForm(key: string, page: Page, onCancel: () => void): HTMLElement {
  const input = el('input', { value: key, 'aria-label': t('New key for {key}', { key }), autocomplete: 'off',
    class: 'rename-input' });
  const form = el('form', { class: 'rename-form' }, input,
    el('button', { type: 'submit', class: 'button-small primary' }, t('Rename')), button(t('Cancel'), onCancel));
  onEscape(form, onCancel);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const newKey = input.value.trim().toUpperCase();
    api.renameTicket(key, newKey).then(
      (result) => page.reload(renamed(key, result.ticket.key, result.action === 'merged', result.moved)),
      page.fail,
    );
  });
  queueMicrotask(() => input.select());
  return form;
}

/** `TNG-4347 renamed to KP-1483 (1 entry)`, or `merged into` an existing ticket. */
function renamed(key: string, newKey: string, merged: boolean, moved: number): string {
  const keys = { key, new: newKey };
  return merged ? tn(moved, '{key} merged into {new} ({count} entry)', '{key} merged into {new} ({count} entries)', keys)
    : tn(moved, '{key} renamed to {new} ({count} entry)', '{key} renamed to {new} ({count} entries)', keys);
}

/** Shows `form` in place of the cell's content; canceling restores the content and focuses `opener` again. */
function openInCell(cell: HTMLElement, opener: HTMLElement, form: (cancel: () => void) => HTMLElement): void {
  const original = [...cell.childNodes];
  cell.replaceChildren(form(() => {
    cell.replaceChildren(...original);
    opener.focus();
  }));
}

function renameAction(key: string, page: Page, cell: HTMLElement): HTMLButtonElement {
  const rename: HTMLButtonElement = button(t('Rename'),
    () => openInCell(cell, rename, (cancel) => renameForm(key, page, cancel)));
  return rename;
}

/** Rows to select (each `data-key`), with a filter, "select all shown" (`selectAllLabel`) and a button that assigns the
 * chosen value of `choice` to the selected rows. `shown` gives the keys a filter text leaves. */
type BulkAssign = {
  selectAllLabel: string; filterLabel: string; placeholder: string; choice: HTMLSelectElement;
  shown: (text: string) => Set<string>; assign: (keys: string[]) => void;
};

function bulkAssign(options: BulkAssign): {
  toolbar: HTMLElement; selectAll: HTMLInputElement; select: (row: HTMLElement) => HTMLElement;
} {
  const selected = new Set<string>();
  const rows: HTMLElement[] = [];
  const filter = el('input', { type: 'search', placeholder: options.placeholder, 'aria-label': options.filterLabel });
  const selectAll = el('input', { type: 'checkbox', 'aria-label': options.selectAllLabel });
  const assign = el('button', { type: 'button', class: 'primary', disabled: true }, t('Assign'));
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
    const checkbox = el('input', { type: 'checkbox', 'aria-label': t('Select {item}', { item: row.dataset.label ?? key }) });
    checkbox.addEventListener('change', () => {
      if (checkbox.checked) {
        selected.add(key);
      } else {
        selected.delete(key);
      }
      assign.disabled = selected.size === 0;
      assign.textContent = selected.size ? t('Assign to {count} selected', { count: selected.size }) : t('Assign');
    });
    row.prepend(el('td', { class: 'select-cell' }, checkbox));
    rows.push(row);
    return row;
  };
  return { toolbar: el('div', { class: 'review-toolbar' }, filter, options.choice, assign), selectAll, select };
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
  return el('select', { 'aria-label': t('Service to assign') },
    ...serviceOptions(services, (service) => `${service.short_name}${service.name ? ` · ${service.name}` : ''}`));
}

function ticketsSection(page: Page): HTMLElement {
  const tickets = page.data.tickets_without_service;
  const choice = serviceSelect(page.services);
  const bulk = bulkAssign({
    selectAllLabel: t('Select all shown tickets'), filterLabel: t('Filter tickets'),
    placeholder: t('Filter, e.g. AGA or TNG-49'), choice,
    shown: (text) => new Set(filterTickets(tickets, text).map((ticket) => ticket.key)),
    assign: (keys) => {
      const service = page.services.find((item) => String(item.id) === choice.value)?.short_name ?? t('Service');
      act(page, () => api.assignService(keys, choice.value),
        tn(keys.length, '{name} assigned to {count} ticket', '{name} assigned to {count} tickets', { name: service }));
    },
  });
  return el('section', { class: 'review-section', id: 'tickets' },
    el('h2', {}, `${t('Tickets without service')} `, el('span', { class: 'badge warning' }, String(tickets.length))),
    el('p', { class: 'muted' }, t('A service applies to all entries of a ticket. Filter, select, then assign.')),
    tickets.length ? bulk.toolbar : null,
    tickets.length
      ? scrolling(el('table', { class: 'review-table' },
        el('thead', {}, el('tr', {}, el('th', { class: 'select-cell' }, bulk.selectAll), el('th', {}, t('Ticket')),
          el('th', { class: 'num' }, t('Entries')), el('th', {}, el('span', { class: 'visually-hidden' }, t('Actions'))))),
        el('tbody', {}, ...tickets.map((ticket) => bulk.select(ticketRow(ticket, page))))))
      : el('p', {}, t('All tickets have a service.')),
  );
}

function entryRow(item: ReviewEntry, page: Page): HTMLElement {
  const entry = item.entry;
  const link = weekLink(entry.date, `entry=${entry.id}`);
  const label = t('{entry} of {date}', { entry: entry.ticket_key ?? entry.description, date: formatDate(entry.date) });
  return el('tr', { 'data-key': entry.id, 'data-label': label },
    el('td', { class: 'num' }, el('a', { href: link }, formatDate(entry.date))),
    el('td', {},
      el('div', { class: 'entry' }, ...entryContent(entry)),
      el('div', {}, ...item.reasons.map((reason) => el('span', { class: 'badge warning' }, REASON_LABELS[reason])))),
    el('td', { class: 'row-actions' }, el('a', { class: 'button button-small', href: link }, t('Open')),
      detailsButton(entry.ticket_key ?? entry.activity_type ?? t('Entry without ticket'), [entry], page.fail)));
}

function activityTypeSelect(activityTypes: ActivityType[]): HTMLSelectElement {
  return el('select', { 'aria-label': t('Activity type to assign') },
    ...activityTypes.map((type) => el('option', { value: type.id ?? '' }, type.name)));
}

/** Former ticket entries whose activity was unclear (SPEC 4.6): choose one, also for several at once. */
function untypedSection(untyped: ReviewEntry[], page: Page): HTMLElement | null {
  if (!untyped.length) {
    return null;
  }
  const choice = activityTypeSelect(page.activityTypes);
  const bulk = bulkAssign({
    selectAllLabel: t('Select all shown entries'), filterLabel: t('Filter entries'),
    placeholder: t('Filter, e.g. TNG-49 or investigation'), choice,
    shown: (text) => new Set(filterEntries(untyped, text).map((item) => item.entry.id)),
    assign: (ids) => {
      const type = page.activityTypes.find((item) => item.id === choice.value)?.name ?? t('Activity type');
      act(page, () => api.assignActivityType(ids, choice.value),
        tn(ids.length, '{name} assigned to {count} entry', '{name} assigned to {count} entries', { name: type }));
    },
  });
  return el('section', { class: 'review-section', id: 'activity-types' },
    el('h2', {}, `${t('Entries without activity type')} `, el('span', { class: 'badge warning' }, String(untyped.length))),
    el('p', { class: 'muted' },
      t('Ticket entries from before every entry had an activity type, whose activity was not clear. Filter, select, then assign.')),
    bulk.toolbar,
    scrolling(el('table', { class: 'review-table' },
      el('thead', {}, el('tr', {}, el('th', { class: 'select-cell' }, bulk.selectAll), el('th', {}, t('Date')),
        el('th', {}, t('Entry')), el('th', {}, el('span', { class: 'visually-hidden' }, t('Actions'))))),
      el('tbody', {}, ...untyped.map((item) => bulk.select(entryRow(  // the section names the missing activity type
        { ...item, reasons: item.reasons.filter((reason) => reason !== 'no_activity_type') }, page)))))),
  );
}

function openDayRow(day: DayView): HTMLElement {
  const link = weekLink(day.date, `edit=${day.date}`);
  return el('tr', {},
    el('td', { class: 'num' }, el('a', { href: link }, formatDate(day.date))),
    el('td', {}, el('span', { class: 'num' }, t('Start {time}', { time: day.start ?? '' })),
      day.best_end ? el('span', { class: 'num muted' }, ` · ${t('best end {time}', { time: day.best_end })}`) : null),
    el('td', { class: 'row-actions' }, el('a', { class: 'button button-small', href: link }, t('Open'))));
}

function openDaysSection(days: DayView[]): HTMLElement | null {
  if (!days.length) {
    return null;
  }
  return el('section', { class: 'review-section', id: 'open-days' },
    el('h2', {}, `${t('Days without an end')} `, el('span', { class: 'badge warning' }, String(days.length))),
    el('p', { class: 'muted' }, t('A day with a start but no end counts as nothing worked until it has an end.')),
    scrolling(el('table', { class: 'review-table' }, el('tbody', {}, ...days.map(openDayRow)))));
}

function entriesSection(others: ReviewEntry[], page: Page): HTMLElement {
  return el('section', { class: 'review-section', id: 'entries' },
    el('h2', {}, `${t('Entries')} `, el('span', { class: 'badge warning' }, String(others.length))),
    el('p', { class: 'muted' },
      t('Entries without duration or without the ticket their activity type requires; open them in the week view to fix them.')),
    others.length
      ? scrolling(el('table', { class: 'review-table' }, el('tbody', {}, ...others.map((item) => entryRow(item, page)))))
      : el('p', {}, t('Nothing to review.')),
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
      const { untyped, others } = groupReview(data.entries);
      root.replaceChildren(openDaysSection(data.open_days) ?? '', untypedSection(untyped, page) ?? '',
        entriesSection(others, page), ticketsSection(page));
      showReviewBadge(doc, data.counts);
      show(message);
    } catch (error) {
      root.replaceChildren(el('div', { class: 'card is-warning', role: 'alert' }, errorText(error)));
    }
  };
  root.replaceChildren(el('p', { class: 'muted' }, t('Loading…')));
  await load();
}
