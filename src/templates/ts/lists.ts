// Lists page (/lists): the services and activity types to choose from in entries (add, change, delete).

import { api, ApiError, type ActivityType, type Service, type TicketView } from './api.ts';
import { el } from './dom.ts';

/** A field of a list item, e.g. the short name of a service. */
type Field = { name: string; label: string; maxLength: number; required: boolean };

/** A list item as text values by field name; `label` names it in messages, `usage` fills the optional usage column. */
type Item = { id: number; label: string; values: Record<string, string>; usage?: string };

/** One managed list: its items and how to save and delete them. */
type List = {
  id: string;
  title: string;
  hint: string;
  noun: string;
  fields: Field[];
  usageLabel?: string;
  items: Item[];
  save: (id: number | null, values: Record<string, string>) => Promise<unknown>;
  remove: (id: number) => Promise<unknown>;
  deleteQuestion: (item: Item) => string;
};

type Page = { reload: (message: string) => void; fail: (error: unknown) => void };

/** Number of tickets per service id. */
export function ticketCounts(tickets: TicketView[]): Map<number, number> {
  const counts = new Map<number, number>();
  for (const ticket of tickets) {
    if (ticket.service_id !== null) {
      counts.set(ticket.service_id, (counts.get(ticket.service_id) ?? 0) + 1);
    }
  }
  return counts;
}

/** `Delete MSB? 12 tickets lose their service and show up in the review.` */
export function deleteServiceQuestion(shortName: string, tickets: number): string {
  if (!tickets) {
    return `Delete ${shortName}? No ticket uses it.`;
  }
  return tickets === 1
    ? `Delete ${shortName}? 1 ticket loses its service and shows up in the review.`
    : `Delete ${shortName}? ${tickets} tickets lose their service and show up in the review.`;
}

function button(label: string, onClick: () => void, className = 'button-small'): HTMLButtonElement {
  const element = el('button', { type: 'button', class: className }, label);
  element.addEventListener('click', onClick);
  return element;
}

function inputs(list: List, item: Item | null): HTMLInputElement[] {
  return list.fields.map((field) => el('input', {
    name: field.name,
    value: item?.values[field.name] ?? '',
    placeholder: field.label,
    'aria-label': item ? `${field.label} of ${item.label}` : `New ${list.noun}: ${field.label.toLowerCase()}`,
    maxlength: field.maxLength,
    required: field.required,
    autocomplete: 'off',
  }));
}

function values(fields: HTMLInputElement[]): Record<string, string> {
  return Object.fromEntries(fields.map((input) => [input.name, input.value.trim()]));
}

/** Saves the form's values (a new item if `item` is null), then reloads the page with a message. */
function itemForm(list: List, item: Item | null, page: Page, ...buttons: HTMLElement[]): HTMLFormElement {
  const fields = inputs(list, item);
  const form = el('form', { class: 'list-form' }, ...fields, ...buttons);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const entered = values(fields);
    const name = entered[list.fields[0]!.name];
    list.save(item?.id ?? null, entered).then(() => page.reload(`${item ? 'Saved' : 'Added'} ${list.noun} ${name}`), page.fail);
  });
  return form;
}

function editRow(list: List, item: Item, page: Page, row: HTMLTableRowElement): void {
  const original = [...row.childNodes];
  const columns = list.fields.length + (list.usageLabel ? 2 : 1);
  const form = itemForm(list, item, page,
    el('button', { type: 'submit', class: 'button-small primary' }, 'Save'),
    button('Cancel', () => row.replaceChildren(...original)));
  row.replaceChildren(el('td', { colspan: columns }, form));
  queueMicrotask(() => form.querySelector('input')?.select());
}

function itemRow(list: List, item: Item, page: Page): HTMLTableRowElement {
  const row = el('tr', {});
  row.append(
    ...list.fields.map((field, index) => {
      const value = item.values[field.name];
      return el('td', {}, !value ? el('span', { class: 'muted' }, '—') : index === 0 ? el('strong', {}, value) : value);
    }),
    list.usageLabel ? el('td', { class: 'num' }, item.usage ?? '') : '',
    el('td', { class: 'row-actions' },
      button('Edit', () => editRow(list, item, page, row)),
      button('Delete', () => {
        if (window.confirm(list.deleteQuestion(item))) {
          list.remove(item.id).then(() => page.reload(`Deleted ${list.noun} ${item.label}`), page.fail);
        }
      })),
  );
  return row;
}

function listSection(list: List, page: Page): HTMLElement {
  const header = el('tr', {},
    ...list.fields.map((field) => el('th', {}, field.label)),
    list.usageLabel ? el('th', { class: 'num' }, list.usageLabel) : '',
    el('th', {}, el('span', { class: 'visually-hidden' }, 'Actions')));
  return el('section', { class: 'review-section', id: list.id },
    el('h2', {}, list.title),
    el('p', { class: 'muted' }, list.hint),
    list.items.length
      ? el('table', { class: 'review-table list-table' }, el('thead', {}, header),
        el('tbody', {}, ...list.items.map((item) => itemRow(list, item, page))))
      : el('p', {}, `No ${list.noun}s yet.`),
    itemForm(list, null, page, el('button', { type: 'submit', class: 'primary' }, `Add ${list.noun}`)),
  );
}

function servicesList(services: Service[], tickets: TicketView[]): List {
  const counts = ticketCounts(tickets);
  return {
    id: 'services',
    title: 'Services',
    hint: 'The service of a ticket applies to all its entries; the month report groups coding work by service.',
    noun: 'service',
    fields: [
      { name: 'short_name', label: 'Short name', maxLength: 30, required: true },
      { name: 'name', label: 'Full name', maxLength: 100, required: false },
    ],
    usageLabel: 'Tickets',
    items: services.map((service) => ({
      id: service.id!, label: service.short_name, values: { short_name: service.short_name, name: service.name ?? '' },
      usage: String(counts.get(service.id!) ?? 0),
    })),
    save: (id, input) => {
      const service = { short_name: input['short_name'] ?? '', name: input['name'] ?? '' };
      return id === null ? api.addService(service) : api.updateService(id, service);
    },
    remove: (id) => api.deleteService(id),
    deleteQuestion: (item) => deleteServiceQuestion(item.label, counts.get(item.id) ?? 0),
  };
}

function activityTypesList(activityTypes: ActivityType[]): List {
  return {
    id: 'activity-types',
    title: 'Activity types',
    hint: 'For entries without a ticket, e.g. meetings or travel. A type used by entries cannot be deleted.',
    noun: 'activity type',
    fields: [{ name: 'name', label: 'Name', maxLength: 50, required: true }],
    items: activityTypes.map((type) => ({ id: type.id!, label: type.name, values: { name: type.name } })),
    save: (id, input) => {
      const type = { name: input['name'] ?? '' };
      return id === null ? api.addActivityType(type) : api.updateActivityType(id, type);
    },
    remove: (id) => api.deleteActivityType(id),
    deleteQuestion: (item) => `Delete ${item.label}?`,
  };
}

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : 'The action failed.';
}

export async function renderListsPage(doc: Document): Promise<void> {
  const root = doc.querySelector<HTMLElement>('#lists');
  const status = doc.querySelector<HTMLElement>('#lists-status');
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
      const [services, activityTypes, tickets] = await Promise.all([api.services(), api.activityTypes(), api.tickets()]);
      const page: Page = { reload: (text) => void load(text), fail: (error) => show(errorText(error), true) };
      root.replaceChildren(listSection(servicesList(services, tickets), page), listSection(activityTypesList(activityTypes), page));
      show(message);
    } catch (error) {
      root.replaceChildren(el('div', { class: 'card is-warning', role: 'alert' }, errorText(error)));
    }
  };
  root.replaceChildren(el('p', { class: 'muted' }, 'Loading…'));
  await load();
}
