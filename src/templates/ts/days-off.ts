// Booking days off as a range (week page): a form with a live preview, and a popup for days that hold times or entries.

import { api, errorText, type DayRangeInput, type DayRangeResult } from './api.ts';
import { addDays, formatDate, formatDay, isoWeek, type IsoDate } from './dates.ts';
import { ask } from './dialog.ts';
import { el, onEscape } from './dom.ts';
import { decimal, listOf, t, tn } from './i18n.ts';
import { DAY_TYPE_LABELS } from './labels.ts';

type RangeType = DayRangeInput['day_type'];
type Conflict = DayRangeResult['conflicts'][number];

const RANGE_TYPES: RangeType[] = ['pto', 'sick', 'unpaid_leave', 'overtime_off'];
type LeftOutReason = DayRangeResult['left_out'][number]['reason'];

/** `3 days off`, `1 public holiday`, … */
function leftOutText(reason: LeftOutReason, count: number): string {
  const texts: Record<LeftOutReason, () => string> = {
    day_off: () => tn(count, '{count} day off', '{count} days off'),
    public_holiday: () => tn(count, '{count} public holiday', '{count} public holidays'),
    company_half_day: () => tn(count, '{count} company half day', '{count} company half days'),
  };
  return texts[reason]();
}

/** Company half days in the range, which take their half PTO day by themselves:
 * `Thu 24.12. and Thu 31.12. are company half days: 0.5 PTO each, booked automatically`. */
function automaticPto(leftOut: DayRangeResult['left_out']): string | null {
  const days = leftOut.filter((day) => day.reason === 'company_half_day' && day.pto_days > 0);
  if (!days.length) {
    return null;
  }
  const listed = listOf(days.map((day) => formatDay(day.date, day.weekday)));
  return tn(days.length, '{days} is a company half day: {pto} PTO, booked automatically',
    '{days} are company half days: {pto} PTO each, booked automatically', { days: listed, pto: decimal(days[0]!.pto_days) });
}

/** The preview of a range: `15 work days, 13.07.2026 – 31.07.2026 · uses 15 PTO days · left out: 6 days off`. */
export function describePreview(result: DayRangeResult, type: RangeType): string {
  const days = result.days;
  if (!days.length) {
    return result.conflicts.length ? t('All work days in this range hold times or entries.') : t('No work days in this range.');
  }
  const parts = [tn(days.length, '{count} work day, {from} – {to}', '{count} work days, {from} – {to}',
    { from: formatDate(days[0]!), to: formatDate(days.at(-1)!) })];
  if (type === 'pto') {
    parts.push(tn(result.pto_days, 'uses {count} PTO day', 'uses {count} PTO days', { count: decimal(result.pto_days) }));
  }
  const automatic = automaticPto(result.left_out);
  if (automatic) {
    parts.push(automatic);
  }
  const counts = new Map<LeftOutReason, number>();
  for (const day of result.left_out) {
    counts.set(day.reason, (counts.get(day.reason) ?? 0) + 1);
  }
  if (counts.size) {
    parts.push(t('left out: {days}', { days: [...counts].map(([reason, count]) => leftOutText(reason, count)).join(', ') }));
  }
  return parts.join(' · ');
}

/** `Tue 14.07.2026 · 8:00 worked · 1 entry` */
export function describeConflict(day: Conflict): string {
  const parts = [`${formatDay(day.date, day.weekday)}${day.date.slice(0, 4)}`];
  if (day.worked !== '0:00') {
    parts.push(t('{duration} worked', { duration: day.worked }));
  }
  if (day.entries) {
    parts.push(tn(day.entries, '{count} entry', '{count} entries'));
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
  return ask<'skip' | 'include'>(
    tn(conflicts.length, '{count} day already holds times or entries', '{count} days already hold times or entries'),
    [el('ul', {}, ...conflicts.map((day) => el('li', {}, describeConflict(day)))),
      t('Booked days keep their times and entries; hours on a day off count as overtime.')],
    [{ label: t('Skip these days'), value: 'skip', primary: true }, { label: t('Book them too'), value: 'include' }],
  );
}

/** The form to book a full-day type on the work days of a range; `onClose` removes it. */
export function daysOffForm(monday: IsoDate, onClose: () => void): HTMLElement {
  const start = dateInput('start', monday);
  const end = dateInput('end', addDays(monday, 4));
  const type = el('select', { name: 'day_type', id: 'days-off-type' },
    ...RANGE_TYPES.map((value) => el('option', { value }, DAY_TYPE_LABELS[value])));
  const note = el('input', {
    name: 'note', id: 'days-off-note', maxlength: 500, autocomplete: 'off', placeholder: t('e.g. summer holidays'),
  });
  const preview = el('p', { class: 'days-off-preview muted', 'aria-live': 'polite' });
  const book = el('button', { type: 'submit', class: 'primary', disabled: true }, t('Book'));
  const cancel = el('button', { type: 'button' }, t('Cancel'));
  const form = el('form', { class: 'card days-off-form' },
    el('h2', {}, t('Book days off')),
    el('div', { class: 'days-off-fields' }, labelled(t('From'), start), labelled(t('To'), end), labelled(t('Type'), type),
      labelled(t('Note'), note)),
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
        + (conflicts ? ` · ${tn(conflicts, '{count} day holds times or entries', '{count} days hold times or entries')}` : '');
      preview.className = 'days-off-preview muted';
      book.disabled = !current.days.length && !current.conflicts.length;
    } catch (error) {
      preview.textContent = errorText(error, t('The days could not be booked.'));
      preview.className = 'days-off-preview field-error';
    }
  };
  for (const control of [start, end, type]) {
    control.addEventListener('change', () => void update());
  }
  cancel.addEventListener('click', onClose);
  onEscape(form, onClose);
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
        window.location.assign(first ? `/week?week=${isoWeek(first)}` : window.location.href);
      } catch (error) {
        preview.textContent = errorText(error, t('The days could not be booked.'));
        preview.className = 'days-off-preview field-error';
      }
    })();
  });
  void update();
  queueMicrotask(() => start.focus());
  return form;
}
