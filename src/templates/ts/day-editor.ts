// Form to record a day in the week view: day type, times, break and note.

import { api, type DayInput, type DayType, type DayView } from './api.ts';
import { formatDay } from './dates.ts';
import { el } from './dom.ts';
import { field, formFooter, submit } from './forms.ts';
import { DAY_TYPE_LABELS } from './labels.ts';

export type DayFormValues = { day_type: string; start: string; end: string; break_time: string; note: string };

const PREFIX = 'day';
const FIELDS = ['day_type', 'start', 'end', 'break_time', 'note'] as const;

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
  for (const name of ['start', 'end', 'break_time'] as const) {
    if (values[name].trim()) {
      input[name] = values[name].trim();
    }
  }
  return input;
}

function textInput(name: string, value: string, placeholder: string): HTMLInputElement {
  return el('input', {
    id: `${PREFIX}-${name}`, name, value, placeholder, inputmode: 'numeric', autocomplete: 'off',
    'aria-describedby': `${PREFIX}-${name}-error`,
  });
}

function typeSelect(value: string): HTMLSelectElement {
  const select = el('select', { id: `${PREFIX}-day_type`, name: 'day_type' },
    el('option', { value: '' }, 'Automatic (work day / holiday)'),
    ...Object.entries(DAY_TYPE_LABELS).map(([type, label]) => el('option', { value: type }, label)));
  select.value = value;
  return select;
}

function values(form: HTMLFormElement): DayFormValues {
  const data = new FormData(form);
  return Object.fromEntries(FIELDS.map((name) => [name, String(data.get(name) ?? '')])) as DayFormValues;
}

/** The editor of one day; `onDone` after saving or deleting, `onCancel` on Cancel or Escape. */
export function dayEditor(day: DayView, onDone: () => void, onCancel: () => void): HTMLFormElement {
  const initial = formValues(day);
  const form = el('form', { class: 'day-editor', 'aria-label': `Edit ${formatDay(day.date, day.weekday)}`, novalidate: true },
    el('div', { class: 'day-editor-fields' },
      field(PREFIX, 'day_type', 'Day type', typeSelect(initial.day_type)),
      field(PREFIX, 'start', 'Start', textInput('start', initial.start, '08:00')),
      field(PREFIX, 'end', 'End', textInput('end', initial.end, '16:30')),
      field(PREFIX, 'break_time', 'Break', textInput('break_time', initial.break_time, 'legal'), 'empty: legal minimum'),
      field(PREFIX, 'note', 'Note', el('textarea', { id: `${PREFIX}-note`, name: 'note', rows: 2,
        'aria-describedby': `${PREFIX}-note-error` }, initial.note)),
    ),
    ...formFooter(day.recorded ? 'Delete day' : null),
  );
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    void submit(form, PREFIX, FIELDS, () => api.saveDay(day.date, dayInput(values(form))), onDone);
  });
  form.querySelector('[data-action="cancel"]')!.addEventListener('click', onCancel);
  form.addEventListener('keydown', (event) => event.key === 'Escape' && onCancel());
  form.querySelector('[data-action="delete"]')?.addEventListener('click', () => {
    if (window.confirm(`Delete type, times and note of ${formatDay(day.date, day.weekday)}? Its entries stay.`)) {
      void submit(form, PREFIX, FIELDS, () => api.deleteDay(day.date), onDone);
    }
  });
  return form;
}
