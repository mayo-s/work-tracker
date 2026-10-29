// Booking days off as a range (week page): a form with a live preview, and a popup for days that hold times or entries.

import { api, ApiError, type DayRangeInput, type DayRangeResult } from './api.ts';
import { addDays, formatDate, formatDay, isoWeek, type IsoDate } from './dates.ts';
import { el } from './dom.ts';
import { DAY_TYPE_LABELS } from './labels.ts';

type RangeType = DayRangeInput['day_type'];
type Conflict = DayRangeResult['conflicts'][number];

const RANGE_TYPES: RangeType[] = ['pto', 'sick', 'unpaid_leave', 'overtime_off'];
type LeftOutReason = DayRangeResult['left_out'][number]['reason'];

const LEFT_OUT_LABELS: Record<LeftOutReason, [string, string]> = {
  day_off: ['day off', 'days off'],
  public_holiday: ['public holiday', 'public holidays'],
  company_half_day: ['company half day', 'company half days'],
};

function plural(count: number, [one, many]: [string, string]): string {
  return `${count} ${count === 1 ? one : many}`;
}

/** The preview of a range: `15 work days, 13.07.2026 – 31.07.2026 · uses 15 PTO days · left out: 6 days off`. */
export function describePreview(result: DayRangeResult, type: RangeType): string {
  const days = result.days;
  if (!days.length) {
    return result.conflicts.length ? 'All work days in this range hold times or entries.' : 'No work days in this range.';
  }
  const parts = [`${plural(days.length, ['work day', 'work days'])}, ${formatDate(days[0]!)} – ${formatDate(days.at(-1)!)}`];
  if (type === 'pto') {
    parts.push(`uses ${plural(result.pto_days, ['PTO day', 'PTO days'])}`);
  }
  const counts = new Map<LeftOutReason, number>();
  for (const day of result.left_out) {
    counts.set(day.reason, (counts.get(day.reason) ?? 0) + 1);
  }
  if (counts.size) {
    parts.push(`left out: ${[...counts].map(([reason, count]) => plural(count, LEFT_OUT_LABELS[reason])).join(', ')}`);
  }
  return parts.join(' · ');
}

/** `Tue 14.07.2026 · 8:00 worked · 1 entry` */
export function describeConflict(day: Conflict): string {
  const parts = [`${formatDay(day.date, day.weekday)}${day.date.slice(0, 4)}`];
  if (day.worked !== '0:00') {
    parts.push(`${day.worked} worked`);
  }
  if (day.entries) {
    parts.push(plural(day.entries, ['entry', 'entries']));
  }
  return parts.join(' · ');
}

function dateInput(name: string, value: IsoDate): HTMLInputElement {
  return el('input', { type: 'date', name, id: `days-off-${name}`, value, required: true });
}

function labelled(label: string, control: HTMLElement): HTMLElement {
  return el('div', { class: 'field' }, el('label', { for: control.id }, label), control);
}

/** Asks what to do with days that hold times or entries; resolves to the choice, or null for cancel. */
function askAboutConflicts(conflicts: Conflict[]): Promise<'skip' | 'include' | null> {
  return new Promise((resolve) => {
    const dialog = el('dialog', { class: 'dialog', 'aria-labelledby': 'conflicts-title' });
    const choose = (choice: 'skip' | 'include' | null) => (): void => {
      dialog.close();
      dialog.remove();
      resolve(choice);
    };
    const choice = (label: string, value: 'skip' | 'include' | null, className = ''): HTMLButtonElement => {
      const button = el('button', { type: 'button', class: className }, label);
      button.addEventListener('click', choose(value));
      return button;
    };
    dialog.addEventListener('cancel', choose(null));
    dialog.append(
      el('h2', { id: 'conflicts-title' },
        `${plural(conflicts.length, ['day already holds', 'days already hold'])} times or entries`),
      el('ul', {}, ...conflicts.map((day) => el('li', {}, describeConflict(day)))),
      el('p', { class: 'muted' }, 'Booked days keep their times and entries; hours on a day off count as overtime.'),
      el('div', { class: 'form-actions' },
        choice('Skip these days', 'skip', 'primary'), choice('Book them too', 'include'), choice('Cancel', null)),
    );
    document.body.append(dialog);
    dialog.showModal();
  });
}

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : 'The days could not be booked.';
}

/** The form to book a full-day type on the work days of a range; `onClose` removes it. */
export function daysOffForm(monday: IsoDate, onClose: () => void): HTMLElement {
  const start = dateInput('start', monday);
  const end = dateInput('end', addDays(monday, 4));
  const type = el('select', { name: 'day_type', id: 'days-off-type' },
    ...RANGE_TYPES.map((value) => el('option', { value }, DAY_TYPE_LABELS[value])));
  const note = el('input', {
    name: 'note', id: 'days-off-note', maxlength: 500, autocomplete: 'off', placeholder: 'e.g. summer holidays',
  });
  const preview = el('p', { class: 'days-off-preview muted', 'aria-live': 'polite' });
  const book = el('button', { type: 'submit', class: 'primary', disabled: true }, 'Book');
  const cancel = el('button', { type: 'button' }, 'Cancel');
  const form = el('form', { class: 'card days-off-form' },
    el('h2', {}, 'Book days off'),
    el('div', { class: 'days-off-fields' }, labelled('From', start), labelled('To', end), labelled('Type', type),
      labelled('Note', note)),
    preview,
    el('div', { class: 'form-actions' }, book, cancel));
  const input = (extra: Partial<DayRangeInput> = {}): DayRangeInput => ({
    start: start.value, end: end.value, day_type: type.value as RangeType, note: note.value.trim(), ...extra,
  });
  let current: DayRangeResult | null = null;
  const update = async (): Promise<void> => {
    current = null;
    book.disabled = true;
    if (!start.value || !end.value) {
      preview.textContent = '';
      return;
    }
    try {
      current = await api.bookRange(input({ preview: true }));
      const conflicts = current.conflicts.length;
      preview.textContent = describePreview(current, type.value as RangeType)
        + (conflicts ? ` · ${plural(conflicts, ['day holds', 'days hold'])} times or entries` : '');
      preview.className = 'days-off-preview muted';
      book.disabled = !current.days.length && !current.conflicts.length;
    } catch (error) {
      preview.textContent = errorText(error);
      preview.className = 'days-off-preview field-error';
    }
  };
  for (const control of [start, end, type]) {
    control.addEventListener('change', () => void update());
  }
  cancel.addEventListener('click', onClose);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    void (async () => {
      const conflicts = current?.conflicts.length ? await askAboutConflicts(current.conflicts) : 'refuse';
      if (!conflicts) {
        return;
      }
      try {
        const result = await api.bookRange(input({ conflicts }));
        const first = result.days[0];
        window.location.assign(first ? `/?week=${isoWeek(first)}` : window.location.href);
      } catch (error) {
        preview.textContent = errorText(error);
        preview.className = 'days-off-preview field-error';
      }
    })();
  });
  void update();
  queueMicrotask(() => start.focus());
  return form;
}
