// Week view (/): the days of a week with times, balance and task entries (read-only).

import { api, ApiError, type DayView, type EntryView, type WeekReport } from './api.ts';
import { addDays, formatDate, formatDay, isoDate, isoWeek, isValidWeek, mondayOf, shiftWeek, type IsoDate } from './dates.ts';
import { dayEditor } from './day-editor.ts';
import { el } from './dom.ts';
import { DAY_TYPE_LABELS } from './labels.ts';

const WEEKEND = new Set(['Sat', 'Sun']);

/** Overtime with a sign: `0:15` → `+0:15`; negative values and zero stay as they are. */
export function signed(duration: string): string {
  return duration.startsWith('-') || duration === '0:00' ? duration : `+${duration}`;
}

/** Negative values as warning, positive ones in mint, zero plain. */
export function valueClass(duration: string): string {
  if (duration.startsWith('-')) {
    return 'value-negative';
  }
  return duration === '0:00' ? '' : 'value-positive';
}

export function entriesByDate(entries: EntryView[]): Map<IsoDate, EntryView[]> {
  const byDate = new Map<IsoDate, EntryView[]>();
  for (const entry of entries) {
    byDate.set(entry.date, [...(byDate.get(entry.date) ?? []), entry]);
  }
  return byDate;
}

/** Monday to Friday always; Saturday and Sunday only if something was recorded. */
export function visibleDays(days: DayView[], entries: Map<IsoDate, EntryView[]>): DayView[] {
  return days.filter((day) => !WEEKEND.has(day.weekday) || day.recorded || entries.has(day.date));
}

/** A past work day (Monday to Friday) without any entry. */
export function needsWarning(day: DayView, entries: EntryView[], today: IsoDate): boolean {
  return day.date < today && day.day_type === 'work' && !WEEKEND.has(day.weekday) && entries.length === 0;
}

/** The week from `?week=2026-W44`, otherwise the current week. */
export function weekFromSearch(search: string, today: IsoDate): string {
  const week = new URLSearchParams(search).get('week');
  return week && isValidWeek(week) ? week : isoWeek(today);
}

/** The day to open for editing from `?edit=2026-10-28`, if it belongs to the shown week. */
export function editFromSearch(search: string, week: string): IsoDate | null {
  const date = new URLSearchParams(search).get('edit');
  return date && /^\d{4}-\d{2}-\d{2}$/.test(date) && isoWeek(date) === week ? date : null;
}

function value(duration: string, withSign = false): HTMLElement {
  return el('span', { class: `num ${valueClass(duration)}`.trim() }, withSign ? signed(duration) : duration);
}

function renderHeader(doc: Document, week: string, today: IsoDate): void {
  const monday = mondayOf(week);
  const [year, number] = week.split('-W');
  doc.querySelector('#week-title')!.textContent = `Week ${Number(number)} · ${year}`;
  doc.querySelector('#week-period')!.textContent = `${formatDate(monday)} – ${formatDate(addDays(monday, 6))}`;
  doc.querySelector<HTMLAnchorElement>('#week-previous')!.href = `/?week=${shiftWeek(week, -1)}`;
  doc.querySelector<HTMLAnchorElement>('#week-next')!.href = `/?week=${shiftWeek(week, 1)}`;
  doc.querySelector<HTMLAnchorElement>('#week-today')!.toggleAttribute('aria-disabled', week === isoWeek(today));
}

function summary(report: WeekReport): HTMLElement {
  const totals = report.totals;
  return el('div', { class: 'card card-surface week-summary' },
    el('div', {}, el('span', { class: 'muted' }, 'Worked '), el('span', { class: 'num' }, totals.worked),
      el('span', { class: 'muted' }, ' of '), el('span', { class: 'num' }, totals.target)),
    el('div', {}, el('span', { class: 'muted' }, 'Overtime '), value(totals.overtime, true)),
    el('div', {}, el('span', { class: 'muted' }, 'Balance '), value(totals.balance_in), el('span', { class: 'muted' }, ' → '),
      value(totals.balance_out)),
    totals.until && totals.until < totals.end
      ? el('div', { class: 'muted' }, `counted up to ${formatDate(totals.until)}`) : null,
  );
}

function entryItem(entry: EntryView): HTMLElement {
  const label = entry.kind === 'ticket'
    ? el('strong', { class: entry.ticket_key ? '' : 'value-negative' }, entry.ticket_key ?? 'No ticket')
    : el('strong', {}, entry.activity_type ?? 'Activity');
  const text = entry.kind === 'ticket' ? entry.description : entry.note;
  return el('li', { class: 'entry' },
    el('span', { class: entry.duration === '0:00' ? 'num value-negative' : 'num', title: entry.duration === '0:00'
      ? 'No duration yet' : null }, entry.duration),
    label,
    entry.service ? el('span', { class: 'badge' }, entry.service) : null,
    text ? el('span', { class: 'entry-text' }, text) : null,
    entry.coding ? el('span', { class: 'badge positive' }, 'coding') : null,
    entry.flags.length ? el('span', { class: 'badge warning', title: entry.flags.map((flag) => flag.detail).join('\n') },
      `${entry.flags.length} to review`) : null,
    entry.changed ? el('span', { class: 'badge', title: 'Changed after it was created or imported' }, 'changed') : null,
  );
}

function dayCell(day: DayView, warning: boolean, today: IsoDate): HTMLElement {
  return el('td', {},
    day.date === today ? el('strong', {}, formatDay(day.date, day.weekday)) : formatDay(day.date, day.weekday),
    day.holiday ? el('div', { class: 'muted' }, day.holiday) : null,
    warning ? el('div', {}, el('span', { class: 'badge warning' }, 'No entries')) : null,
    day.flags.length ? el('div', {}, el('span', { class: 'badge warning', title: day.flags.map((flag) => flag.detail).join('\n') },
      'to review')) : null,
  );
}

type WeekData = { days: DayView[]; entries: Map<IsoDate, EntryView[]>; report: WeekReport };
type Actions = { edit: (date: IsoDate) => void; cancel: () => void; changed: () => void };

const COLUMNS = 8;

function rowClass(day: DayView, warning: boolean, today: IsoDate): string | null {
  const classes = [warning ? 'is-warning' : '', day.date === today ? 'is-today' : '', WEEKEND.has(day.weekday) ? 'is-weekend' : ''];
  return classes.filter(Boolean).join(' ') || null;
}

function dayRow(day: DayView, warning: boolean, today: IsoDate, edit: HTMLElement | null): HTMLElement {
  return el('tr', { class: rowClass(day, warning, today) },
    dayCell(day, warning, today),
    el('td', {}, day.day_type === 'work' ? null : el('span', { class: 'badge' }, DAY_TYPE_LABELS[day.day_type])),
    el('td', {}, day.start ? el('span', { class: 'num' }, `${day.start}–${day.end}`) : el('span', { class: 'muted' }, '—')),
    el('td', { class: 'num' }, day.break_time ?? '', day.break_default ? el('span', { class: 'muted' }, ' legal') : null),
    el('td', { class: 'num' }, day.worked),
    el('td', { class: 'num muted' }, day.target),
    el('td', { class: 'num' }, value(day.overtime, true)),
    el('td', { class: 'row-actions' }, edit),
  );
}

function detailsRow(day: DayView, entries: EntryView[], className: string | null): HTMLElement | null {
  if (!entries.length && !day.note) {
    return null;
  }
  return el('tr', { class: ['day-details', className].filter(Boolean).join(' ') },
    el('td', { colspan: COLUMNS },
      day.note ? el('p', { class: 'day-note muted' }, day.note) : null,
      entries.length ? el('ul', { class: 'entries' }, ...entries.map(entryItem)) : null));
}

function dayRows(day: DayView, entries: EntryView[], today: IsoDate, editing: IsoDate | null, actions: Actions): HTMLElement[] {
  const warning = needsWarning(day, entries, today);
  const details = detailsRow(day, entries, rowClass(day, warning, today));
  if (day.date === editing) {
    const editor = el('tr', { class: 'day-editor-row' },
      el('td', { colspan: COLUMNS }, dayEditor(day, actions.changed, actions.cancel)));
    return [dayRow(day, warning, today, null), editor, ...(details ? [details] : [])];
  }
  const edit = el('button', { type: 'button', class: 'button-small', 'aria-label': `Edit ${formatDay(day.date, day.weekday)}` },
    'Edit');
  edit.addEventListener('click', () => actions.edit(day.date));
  return [dayRow(day, warning, today, edit), ...(details ? [details] : [])];
}

function dayTable(data: WeekData, today: IsoDate, editing: IsoDate | null, actions: Actions): HTMLElement {
  const days = visibleDays(data.days, data.entries);
  if (editing && !days.some((day) => day.date === editing)) {
    days.push(...data.days.filter((day) => day.date === editing));  // e.g. a weekend day opened for editing
  }
  return el('table', { class: 'week-table' },
    el('thead', {}, el('tr', {},
      el('th', {}, 'Day'), el('th', {}, 'Type'), el('th', {}, 'Times'), el('th', { class: 'num' }, 'Break'),
      el('th', { class: 'num' }, 'Worked'), el('th', { class: 'num' }, 'Target'), el('th', { class: 'num' }, 'Overtime'),
      el('th', {}, el('span', { class: 'visually-hidden' }, 'Actions')))),
    el('tbody', {}, ...days.sort((a, b) => a.date.localeCompare(b.date))
      .flatMap((day) => dayRows(day, data.entries.get(day.date) ?? [], today, editing, actions))),
  );
}

function weekendLinks(data: WeekData, edit: (date: IsoDate) => void): HTMLElement | null {
  const hidden = data.days.filter((day) => !visibleDays([day], data.entries).length);
  if (!hidden.length) {
    return null;
  }
  return el('p', { class: 'muted week-weekend' }, 'Worked on the weekend? ',
    ...hidden.map((day) => {
      const button = el('button', { type: 'button', class: 'button-small' }, `Record ${formatDay(day.date, day.weekday)}`);
      button.addEventListener('click', () => edit(day.date));
      return button;
    }));
}

function errorCard(error: unknown): HTMLElement {
  const message = error instanceof ApiError ? error.message : 'The week could not be loaded.';
  return el('div', { class: 'card is-warning', role: 'alert' }, message);
}

export async function renderWeekPage(doc: Document): Promise<void> {
  const root = doc.querySelector<HTMLElement>('#week');
  if (!root) {
    return;
  }
  const today = isoDate(new Date());
  const week = weekFromSearch(doc.location.search, today);
  renderHeader(doc, week, today);
  let data: WeekData | null = null;
  let editing: IsoDate | null = null;
  let firstLoad = true;

  const draw = (): void => {
    if (!data) {
      return;
    }
    root.replaceChildren(summary(data.report), dayTable(data, today, editing, actions), weekendLinks(data, actions.edit) ?? '');
    root.querySelector<HTMLElement>('.day-editor select, .day-editor input')?.focus();
  };
  const load = async (): Promise<void> => {
    try {
      const [days, entries, report] = await Promise.all([api.days({ week }), api.entries({ week }), api.weekReport(week)]);
      data = { days, entries: entriesByDate(entries), report };
      editing = firstLoad ? editFromSearch(doc.location.search, week) : null;
      firstLoad = false;
      draw();
    } catch (error) {
      root.replaceChildren(errorCard(error));
    }
  };
  const actions: Actions = {
    edit: (date) => {
      editing = date;
      draw();
    },
    cancel: () => {
      editing = null;
      draw();
    },
    changed: () => void load(),
  };

  root.replaceChildren(el('p', { class: 'muted' }, 'Loading…'));
  await load();
}
