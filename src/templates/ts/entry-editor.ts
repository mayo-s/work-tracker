// Form to add or change a task entry: an activity, optionally on a ticket (SPEC 4).

import {
  api, ApiError, type ActivityType, type EntryInput, type EntryView, type ServiceChoice, type WorkMode,
} from './api.ts';
import { el } from './dom.ts';
import { clockMinutes, normalizeOnLeave, settleDuration, type DurationRules } from './duration-input.ts';
import { field, formFooter, showErrors, submit } from './forms.ts';
import { t, tn } from './i18n.ts';
import { serviceOptions } from './lists.ts';
import { hasTickets } from './work-modes.ts';

export type EntryFormValues = {
  activity_type_id: string; duration: string; ticket_key: string; service_id: string; description: string;
};

const PREFIX = 'entry';
const FIELDS = ['activity_type_id', 'duration', 'ticket_key', 'service_id', 'description'] as const;

export type EntryEditorOptions = {
  date: string;
  entry: EntryView | null;  // null: a new entry
  dayStart: string | null;  // the day's start time, e.g. 08:00: an entry fits the rest of the day
  services: ServiceChoice[];
  activityTypes: ActivityType[];
  workMode: WorkMode;
  onDone: () => void;
  onCancel: () => void;
};

/** An entry is at most as long as the rest of its day (from 08:00: 16:00; no start: 24:00). */
export function entryRules(dayStart: string | null): DurationRules {
  return { limit: 24 * 60 - (clockMinutes(dayStart ?? '') ?? 0) };
}

/** What the form offers in a way of working (SPEC 5.11): ticket and service, and the activity types to choose. Without
 * ticket and service, types that require a ticket are left out; an entry that has a ticket (or such a type) still
 * shows them, so nothing of it is lost. */
export function entryForm(mode: WorkMode, entry: EntryView | null, activityTypes: ActivityType[]): {
  ticket: boolean; activityTypes: ActivityType[];
} {
  const ticket = hasTickets(mode) || Boolean(entry?.ticket_key);
  return {
    ticket,
    activityTypes: activityTypes.filter((type) => ticket || !type.ticket_required || type.id === entry?.activity_type_id),
  };
}

/** A new entry starts with the first activity type that requires a ticket (e.g. Coding) where tickets are entered. */
export function entryFormValues(entry: EntryView | null, offered: ActivityType[] = [], ticket = false): EntryFormValues {
  const first = ticket ? offered.find((type) => type.ticket_required)?.id : undefined;
  return {
    activity_type_id: entry ? entry.activity_type_id ?? '' : first ?? '',
    duration: entry?.duration ?? '',
    ticket_key: entry?.ticket_key ?? '',
    service_id: entry?.service_id ?? '',
    description: entry?.description ?? '',
  };
}

/** What has to be fixed before saving, as [field, message]: an activity type, and the ticket the type requires. */
export function entryProblem(values: EntryFormValues, activityTypes: ActivityType[]): [string, string] | null {
  const type = activityTypes.find((item) => item.id === values.activity_type_id);
  if (!type) {
    return ['activity_type_id', t('Choose an activity type.')];
  }
  return type.ticket_required && !values.ticket_key.trim() ? ['ticket_key', t('{type} needs a ticket.', { type: type.name })] : null;
}

/** The API input; `service_id` only with a ticket and if the service was changed (it applies to all the ticket's
 * entries). */
export function entryInput(values: EntryFormValues, date: string, serviceChanged: boolean): EntryInput {
  const ticketKey = values.ticket_key.trim().toUpperCase() || null;
  const input: EntryInput = {
    date, activity_type_id: values.activity_type_id, duration: values.duration.trim(), ticket_key: ticketKey,
    description: values.description.trim(),
  };
  if (ticketKey && serviceChanged) {
    input.service_id = values.service_id || null;
  }
  return input;
}

function select(name: string, value: string, empty: string, options: [string, string][] | HTMLElement[]): HTMLSelectElement {
  const children = options.map((option) => (option instanceof HTMLElement ? option
    : el('option', { value: option[0] }, option[1])));
  const element = el('select', { id: `${PREFIX}-${name}`, name, 'aria-describedby': `${PREFIX}-${name}-error` },
    el('option', { value: '' }, empty), ...children);
  element.value = value;
  return element;
}

function input(name: string, value: string, placeholder: string, extra: Record<string, string> = {}): HTMLInputElement {
  return el('input', {
    id: `${PREFIX}-${name}`, name, value, placeholder, autocomplete: 'off', 'aria-describedby': `${PREFIX}-${name}-error`, ...extra,
  });
}

function values(form: HTMLFormElement): EntryFormValues {
  const data = new FormData(form);
  const text = (name: string): string => String(data.get(name) ?? '');
  return {
    activity_type_id: text('activity_type_id'), duration: text('duration'), ticket_key: text('ticket_key'),
    service_id: text('service_id'), description: text('description'),
  };
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
    hint.textContent = tn(ticket.entries, '{key}: {count} entry', '{key}: {count} entries', { key: ticket.key });
  } catch (error) {
    hint.textContent = error instanceof ApiError && error.status === 404 ? t('New ticket') : '';
  }
}

function fields(initial: EntryFormValues, options: EntryEditorOptions): HTMLElement {
  const form = entryForm(options.workMode, options.entry, options.activityTypes);
  const activities = form.activityTypes.map((type): [string, string] => [type.id ?? '', type.name]);
  const services = serviceOptions(options.services, (service) => service.short_name);
  return el('div', { class: 'entry-editor-fields' },
    field(PREFIX, 'activity_type_id', t('Activity'),
      select('activity_type_id', initial.activity_type_id, t('— choose —'), activities)),
    field(PREFIX, 'duration', t('Duration'), input('duration', initial.duration, '1:30'), t('e.g. 1.5 or 90m')),
    form.ticket ? field(PREFIX, 'ticket_key', t('Ticket'), input('ticket_key', initial.ticket_key, 'ENGINE-461')) : null,
    form.ticket ? field(PREFIX, 'service_id', t('Service'),
      select('service_id', initial.service_id, t('— no service —'), services), ' ') : null,
    field(PREFIX, 'description', t('Description'), input('description', initial.description, t('What was done'))),
  );
}

/** The ticket field pre-fills the service; choosing a service says that it applies to all entries of the ticket. */
function wireService(form: HTMLFormElement, serviceChanged: { value: boolean }): void {
  const serviceSelect = form.querySelector<HTMLSelectElement>(`#${PREFIX}-service_id`);
  if (!serviceSelect) {
    return;  // no ticket and service in this way of working
  }
  const serviceHint = serviceSelect.parentElement!.querySelector<HTMLElement>('.field-hint')!;
  form.querySelector(`#${PREFIX}-ticket_key`)!.addEventListener('change', () => {
    serviceChanged.value = false;
    void prefillService(form, serviceSelect, serviceHint);
  });
  serviceSelect.addEventListener('change', () => {
    serviceChanged.value = true;
    const key = values(form).ticket_key.trim().toUpperCase();
    serviceHint.textContent = key ? t('Applies to all entries of {key}', { key }) : '';
  });
}

function wire(form: HTMLFormElement, options: EntryEditorOptions, serviceChanged: { value: boolean }): void {
  wireService(form, serviceChanged);
  const duration = form.querySelector<HTMLInputElement>(`#${PREFIX}-duration`)!;
  const rules = entryRules(options.dayStart);
  normalizeOnLeave(duration, () => rules);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const problem = entryProblem(values(form), options.activityTypes);
    if (problem) {
      showErrors(form, PREFIX, FIELDS, [{ loc: [problem[0]], msg: problem[1] }], '');
      return;
    }
    if (!await settleDuration(duration, rules)) {
      return;
    }
    const input = entryInput(values(form), options.date, serviceChanged.value);
    const save = options.entry ? () => api.updateEntry(options.entry!.id, input) : () => api.createEntry(input);
    void submit(form, PREFIX, FIELDS, save, options.onDone);
  });
  form.querySelector('[data-action="cancel"]')!.addEventListener('click', options.onCancel);
  form.addEventListener('keydown', (event) => event.key === 'Escape' && options.onCancel());
  form.querySelector('[data-action="delete"]')?.addEventListener('click', () => {
    if (options.entry && window.confirm(t('Delete this entry? Its history is kept.'))) {
      void submit(form, PREFIX, FIELDS, () => api.deleteEntry(options.entry!.id), options.onDone);
    }
  });
}

/** The editor of a new or existing entry of a day. */
export function entryEditor(options: EntryEditorOptions): HTMLFormElement {
  const offered = entryForm(options.workMode, options.entry, options.activityTypes);
  const initial = entryFormValues(options.entry, offered.activityTypes, offered.ticket);
  const form = el('form', { class: 'entry-editor', 'aria-label': options.entry ? t('Edit entry') : t('New entry'),
    novalidate: true },
  fields(initial, options),
  ...formFooter(options.entry ? t('Delete entry') : null),
  );
  wire(form, options, { value: options.entry === null });
  return form;
}
