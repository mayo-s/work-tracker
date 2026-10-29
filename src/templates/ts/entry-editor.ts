// Form to add or change a task entry: a ticket entry or an activity entry.

import { api, ApiError, type ActivityType, type EntryInput, type EntryView, type Service } from './api.ts';
import { el } from './dom.ts';
import { field, formFooter, submit } from './forms.ts';

export type EntryKind = 'ticket' | 'activity';
export type EntryFormValues = {
  kind: EntryKind; duration: string; ticket_key: string; service_id: string; description: string; coding: boolean;
  activity_type_id: string; note: string;
};

const PREFIX = 'entry';
const FIELDS = ['duration', 'ticket_key', 'service_id', 'description', 'coding', 'activity_type_id', 'note'] as const;

export type EntryEditorOptions = {
  date: string;
  entry: EntryView | null;  // null: a new entry
  services: Service[];
  activityTypes: ActivityType[];
  onDone: () => void;
  onCancel: () => void;
};

export function entryFormValues(entry: EntryView | null): EntryFormValues {
  return {
    kind: entry?.kind ?? 'ticket',
    duration: entry?.duration ?? '',
    ticket_key: entry?.ticket_key ?? '',
    service_id: entry?.service_id != null ? String(entry.service_id) : '',
    description: entry?.description ?? '',
    coding: entry?.coding ?? false,
    activity_type_id: entry?.activity_type_id != null ? String(entry.activity_type_id) : '',
    note: entry?.note ?? '',
  };
}

/** The API input; `service_id` only if the service was changed (it applies to all entries of the ticket). */
export function entryInput(values: EntryFormValues, date: string, serviceChanged: boolean): EntryInput {
  const duration = values.duration.trim();
  if (values.kind === 'activity') {
    return {
      kind: 'activity', date, duration, activity_type_id: values.activity_type_id ? Number(values.activity_type_id) : null,
      note: values.note.trim(),
    };
  }
  const input: EntryInput = {
    kind: 'ticket', date, duration, ticket_key: values.ticket_key.trim().toUpperCase() || null,
    description: values.description.trim(), coding: values.coding,
  };
  if (serviceChanged) {
    input.service_id = values.service_id ? Number(values.service_id) : null;
  }
  return input;
}

function select(name: string, value: string, empty: string, options: [number, string][]): HTMLSelectElement {
  const element = el('select', { id: `${PREFIX}-${name}`, name, 'aria-describedby': `${PREFIX}-${name}-error` },
    el('option', { value: '' }, empty), ...options.map(([id, label]) => el('option', { value: id }, label)));
  element.value = value;
  return element;
}

function input(name: string, value: string, placeholder: string, extra: Record<string, string> = {}): HTMLInputElement {
  return el('input', {
    id: `${PREFIX}-${name}`, name, value, placeholder, autocomplete: 'off', 'aria-describedby': `${PREFIX}-${name}-error`, ...extra,
  });
}

function kindToggle(kind: EntryKind, locked: boolean): HTMLElement {
  const option = (value: EntryKind, label: string): HTMLElement => el('label', { class: 'kind-option' },
    el('input', { type: 'radio', name: 'kind', value, checked: kind === value, disabled: locked && kind !== value }), label);
  return el('fieldset', { class: 'kind-toggle' }, el('legend', { class: 'visually-hidden' }, 'Kind'),
    option('ticket', 'Ticket'), option('activity', 'Activity'));
}

function values(form: HTMLFormElement): EntryFormValues {
  const data = new FormData(form);
  const text = (name: string): string => String(data.get(name) ?? '');
  return {
    kind: text('kind') === 'activity' ? 'activity' : 'ticket', duration: text('duration'), ticket_key: text('ticket_key'),
    service_id: text('service_id'), description: text('description'), coding: data.get('coding') === 'on',
    activity_type_id: text('activity_type_id'), note: text('note'),
  };
}

function showKind(form: HTMLFormElement): void {
  const kind = values(form).kind;
  form.querySelectorAll<HTMLElement>('[data-kind]').forEach((element) => (element.hidden = element.dataset.kind !== kind));
}

/** Pre-fills the service a known ticket remembers; unknown tickets keep the chosen service. */
async function prefillService(form: HTMLFormElement, serviceSelect: HTMLSelectElement, hint: HTMLElement): Promise<void> {
  const key = values(form).ticket_key.trim();
  if (!key) {
    return;
  }
  try {
    const ticket = await api.ticket(key);
    serviceSelect.value = ticket.service_id != null ? String(ticket.service_id) : '';
    hint.textContent = `${ticket.key}: ${ticket.entries} ${ticket.entries === 1 ? 'entry' : 'entries'}`;
  } catch (error) {
    hint.textContent = error instanceof ApiError && error.status === 404 ? 'New ticket' : '';
  }
}

function onlyFor(kind: EntryKind, element: HTMLElement): HTMLElement {
  element.dataset.kind = kind;
  return element;
}

function fields(initial: EntryFormValues, options: EntryEditorOptions): HTMLElement {
  const services = options.services.map((service): [number, string] => [service.id ?? 0, service.short_name]);
  const activities = options.activityTypes.map((activity): [number, string] => [activity.id ?? 0, activity.name]);
  return el('div', {},
    kindToggle(initial.kind, options.entry !== null),
    el('div', { class: 'entry-editor-fields' },
      field(PREFIX, 'duration', 'Duration', input('duration', initial.duration, '1:30', { inputmode: 'numeric' }), 'h:mm'),
      onlyFor('ticket', field(PREFIX, 'ticket_key', 'Ticket', input('ticket_key', initial.ticket_key, 'ENGINE-461'))),
      onlyFor('ticket', field(PREFIX, 'service_id', 'Service', select('service_id', initial.service_id, '— no service —', services),
        ' ')),
      onlyFor('ticket', el('label', { class: 'coding-option' },
        el('input', { type: 'checkbox', name: 'coding', id: `${PREFIX}-coding`, checked: initial.coding }), 'Coding')),
      onlyFor('ticket', field(PREFIX, 'description', 'Description', input('description', initial.description, 'What was done'))),
      onlyFor('activity', field(PREFIX, 'activity_type_id', 'Activity',
        select('activity_type_id', initial.activity_type_id, '— choose —', activities))),
      onlyFor('activity', field(PREFIX, 'note', 'Note', input('note', initial.note, 'Optional'))),
    ),
  );
}

function wire(form: HTMLFormElement, options: EntryEditorOptions, serviceChanged: { value: boolean }): void {
  const serviceSelect = form.querySelector<HTMLSelectElement>(`#${PREFIX}-service_id`)!;
  const serviceHint = serviceSelect.parentElement!.querySelector<HTMLElement>('.field-hint')!;
  form.querySelectorAll('input[name="kind"]').forEach((radio) => radio.addEventListener('change', () => showKind(form)));
  form.querySelector('#entry-ticket_key')!.addEventListener('change', () => {
    serviceChanged.value = false;
    void prefillService(form, serviceSelect, serviceHint);
  });
  serviceSelect.addEventListener('change', () => {
    serviceChanged.value = true;
    const key = values(form).ticket_key.trim().toUpperCase();
    serviceHint.textContent = key ? `Applies to all entries of ${key}` : '';
  });
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const input = entryInput(values(form), options.date, serviceChanged.value);
    const save = options.entry ? () => api.updateEntry(options.entry!.id, input) : () => api.createEntry(input);
    void submit(form, PREFIX, FIELDS, save, options.onDone);
  });
  form.querySelector('[data-action="cancel"]')!.addEventListener('click', options.onCancel);
  form.addEventListener('keydown', (event) => event.key === 'Escape' && options.onCancel());
  form.querySelector('[data-action="delete"]')?.addEventListener('click', () => {
    if (options.entry && window.confirm('Delete this entry? Its history is kept.')) {
      void submit(form, PREFIX, FIELDS, () => api.deleteEntry(options.entry!.id), options.onDone);
    }
  });
}

/** The editor of a new or existing entry of a day. */
export function entryEditor(options: EntryEditorOptions): HTMLFormElement {
  const initial = entryFormValues(options.entry);
  const form = el('form', { class: 'entry-editor', 'aria-label': options.entry ? 'Edit entry' : 'New entry', novalidate: true },
    fields(initial, options),
    ...formFooter(options.entry ? 'Delete entry' : null),
  );
  wire(form, options, { value: options.entry === null });
  showKind(form);
  return form;
}
