// Form to record a day in the week view: day type, times, break and note.

import { api, ApiError, type DayInput, type DayType, type DayView } from './api.ts';
import { formatDay } from './dates.ts';
import { el } from './dom.ts';
import { DAY_TYPE_LABELS } from './labels.ts';

export type DayFormValues = { day_type: string; start: string; end: string; break_time: string; note: string };
type FieldName = keyof DayFormValues;

const FIELDS: FieldName[] = ['day_type', 'start', 'end', 'break_time', 'note'];

/** The form values of a day; an automatic day type and a legal break stay empty. */
export function formValues(day: DayView): DayFormValues {
  return {
    day_type: day.automatic ? '' : day.day_type,
    start: day.start ?? '',
    end: day.end ?? '',
    break_time: day.break_default ? '' : day.break_time ?? '',
    note: day.note,
  };
}

/** The API input of the form values; empty fields are left out (automatic type, legal break). */
export function dayInput(values: DayFormValues): DayInput {
  const input: DayInput = { note: values.note.trim() };
  if (values.day_type) {
    input.day_type = values.day_type as DayType;
  }
  for (const field of ['start', 'end', 'break_time'] as const) {
    if (values[field].trim()) {
      input[field] = values[field].trim();
    }
  }
  return input;
}

/** Validation messages without pydantic's "Value error, " prefix. */
export function cleanMessage(message: string): string {
  return message.replace(/^(Value error, )+/, '');
}

/** Validation errors of a 422 response, by field; errors not about one field are general. */
export function fieldErrors(details: unknown): { fields: Partial<Record<FieldName, string>>; general: string[] } {
  const result: { fields: Partial<Record<FieldName, string>>; general: string[] } = { fields: {}, general: [] };
  for (const item of Array.isArray(details) ? details : []) {
    const field = item?.loc?.[0];
    const message = cleanMessage(String(item?.msg ?? ''));
    if (FIELDS.includes(field)) {
      result.fields[field as FieldName] = message;
    } else if (message) {
      result.general.push(message);
    }
  }
  return result;
}

function field(name: FieldName, label: string, control: HTMLElement, hint?: string): HTMLElement {
  return el('div', { class: `field field-${name.replace('_', '-')}` },
    el('label', { for: `day-${name}` }, label),
    control,
    hint ? el('p', { class: 'field-hint muted' }, hint) : null,
    el('p', { class: 'field-error', id: `day-${name}-error`, hidden: true }),
  );
}

function textInput(name: FieldName, value: string, placeholder: string): HTMLInputElement {
  return el('input', {
    id: `day-${name}`, name, value, placeholder, inputmode: 'numeric', autocomplete: 'off', 'aria-describedby': `day-${name}-error`,
  });
}

function typeSelect(value: string): HTMLSelectElement {
  const select = el('select', { id: 'day-day_type', name: 'day_type' },
    el('option', { value: '' }, 'Automatic (work day / holiday)'),
    ...Object.entries(DAY_TYPE_LABELS).map(([type, label]) => el('option', { value: type }, label)));
  select.value = value;
  return select;
}

function showErrors(form: HTMLFormElement, details: unknown, fallback: string): void {
  const errors = fieldErrors(details);
  for (const name of FIELDS) {
    const message = errors.fields[name];
    const error = form.querySelector<HTMLElement>(`#day-${name}-error`)!;
    error.textContent = message ?? '';
    error.hidden = !message;
    form.querySelector(`#day-${name}`)?.toggleAttribute('aria-invalid', Boolean(message));
  }
  const general = form.querySelector<HTMLElement>('.form-error')!;
  general.textContent = errors.general.join(' ') || (Object.keys(errors.fields).length ? '' : fallback);
  general.hidden = !general.textContent;
}

function values(form: HTMLFormElement): DayFormValues {
  const data = new FormData(form);
  return Object.fromEntries(FIELDS.map((name) => [name, String(data.get(name) ?? '')])) as DayFormValues;
}

async function run(form: HTMLFormElement, action: () => Promise<unknown>, onDone: () => void): Promise<void> {
  form.querySelectorAll('button').forEach((button) => (button.disabled = true));
  try {
    await action();
    onDone();
  } catch (error) {
    const fallback = error instanceof ApiError ? error.message : 'The day could not be saved.';
    showErrors(form, error instanceof ApiError ? error.details : null, fallback);
    form.querySelectorAll('button').forEach((button) => (button.disabled = false));
  }
}

/** The editor of one day; `onDone` after saving or deleting, `onCancel` on Cancel or Escape. */
export function dayEditor(day: DayView, onDone: () => void, onCancel: () => void): HTMLFormElement {
  const initial = formValues(day);
  const remove = day.recorded ? el('button', { type: 'button', class: 'button-danger' }, 'Delete day') : null;
  const form = el('form', { class: 'day-editor', 'aria-label': `Edit ${formatDay(day.date, day.weekday)}`, novalidate: true },
    el('div', { class: 'day-editor-fields' },
      field('day_type', 'Day type', typeSelect(initial.day_type)),
      field('start', 'Start', textInput('start', initial.start, '08:00')),
      field('end', 'End', textInput('end', initial.end, '16:30')),
      field('break_time', 'Break', textInput('break_time', initial.break_time, 'legal'), 'empty: legal minimum'),
      field('note', 'Note', el('textarea', { id: 'day-note', name: 'note', rows: 2, 'aria-describedby': 'day-note-error' },
        initial.note)),
    ),
    el('p', { class: 'form-error field-error', role: 'alert', hidden: true }),
    el('div', { class: 'form-actions' },
      el('button', { type: 'submit', class: 'primary' }, 'Save'),
      el('button', { type: 'button', 'data-action': 'cancel' }, 'Cancel'),
      remove,
    ),
  );
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    void run(form, () => api.saveDay(day.date, dayInput(values(form))), onDone);
  });
  form.querySelector('[data-action="cancel"]')!.addEventListener('click', onCancel);
  form.addEventListener('keydown', (event) => event.key === 'Escape' && onCancel());
  remove?.addEventListener('click', () => {
    if (window.confirm(`Delete type, times and note of ${formatDay(day.date, day.weekday)}? Its entries stay.`)) {
      void run(form, () => api.deleteDay(day.date), onDone);
    }
  });
  return form;
}
