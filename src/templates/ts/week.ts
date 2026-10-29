// Week view (/): the days of a week with times, balance and task entries (read-only).

import {
  api, ApiError, type ActivityType, type DayView, type EntryView, type PeriodTotals, type Service, type WeekReport,
} from './api.ts';
import { addDays, formatDate, formatDay, isoDate, isoWeek, isValidWeek, mondayOf, shiftWeek, type IsoDate } from './dates.ts';
import { dayEditor } from './day-editor.ts';
import { el } from './dom.ts';
import { entryEditor, type EntryEditorOptions } from './entry-editor.ts';
import { historyPanel } from './history.ts';
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

/** The entry to open for editing from `?entry=129`, if it is an entry of the shown week. */
export function entryFromSearch(search: string, entries: Map<IsoDate, EntryView[]>): Editing {
  const id = Number(new URLSearchParams(search).get('entry'));
  const entry = [...entries.values()].flat().find((item) => item.id === id);
  return entry ? { kind: 'entry', date: entry.date, id: entry.id } : null;
}

/** A duration as warning (negative), in mint (positive) or plain (zero). */
export function value(duration: string, withSign = false): HTMLElement {
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

/** Worked of target, overtime and balance of a week, month or year (shared by the week view and the reports). */
export function periodSummary(totals: PeriodTotals, extra: HTMLElement | null = null): HTMLElement {
  return el('div', { class: 'card card-surface week-summary' },
    el('div', {}, el('span', { class: 'muted' }, 'Worked '), el('span', { class: 'num' }, totals.worked),
      el('span', { class: 'muted' }, ' of '), el('span', { class: 'num' }, totals.target)),
    el('div', {}, el('span', { class: 'muted' }, 'Overtime '), value(totals.overtime, true)),
    el('div', {}, el('span', { class: 'muted' }, 'Balance '), value(totals.balance_in), el('span', { class: 'muted' }, ' → '),
      value(totals.balance_out)),
    totals.until && totals.until < totals.end
      ? el('div', { class: 'muted' }, `counted up to ${formatDate(totals.until)}`) : null,
    extra,
  );
}

type WeekData = {
  days: DayView[]; entries: Map<IsoDate, EntryView[]>; report: WeekReport; services: Service[]; activityTypes: ActivityType[];
};
/** What is open: the form of a day, of an entry (id) or of a new entry (null) on a date, or nothing. */
export type Editing = { kind: 'day'; date: IsoDate } | { kind: 'entry'; date: IsoDate; id: number | null } | null;
type View = { data: WeekData; today: IsoDate; editing: Editing; history: number | null; actions: Actions };
type Actions = {
  edit: (editing: Editing) => void; cancel: () => void; changed: () => void; toggleHistory: (entryId: number) => void;
};

const COLUMNS = 8;

function button(label: string, onClick: () => void, attributes: Record<string, string> = {}): HTMLButtonElement {
  const element = el('button', { type: 'button', class: 'button-small', ...attributes }, label);
  element.addEventListener('click', onClick);
  return element;
}

/** Duration, ticket or activity, service, text and badges of an entry (also used by the review page). */
export function entryContent(entry: EntryView, showFlags = true): (HTMLElement | null)[] {
  const label = entry.kind === 'ticket'
    ? el('strong', { class: entry.ticket_key ? '' : 'value-negative' }, entry.ticket_key ?? 'No ticket')
    : el('strong', {}, entry.activity_type ?? 'Activity');
  const text = entry.kind === 'ticket' ? entry.description : entry.note;
  return [
    el('span', { class: entry.duration === '0:00' ? 'num value-negative' : 'num', title: entry.duration === '0:00'
      ? 'No duration yet' : null }, entry.duration),
    label,
    entry.service ? el('span', { class: 'badge' }, entry.service) : null,
    text ? el('span', { class: 'entry-text' }, text) : null,
    entry.coding ? el('span', { class: 'badge positive' }, 'coding') : null,
    showFlags && entry.flags.length ? el('span', { class: 'badge warning', title: entry.flags.map((flag) => flag.detail).join('\n') },
      `${entry.flags.length} to review`) : null,
    entry.changed ? el('span', { class: 'badge', title: 'Changed after it was created or imported' }, 'changed') : null,
  ];
}

function editorOptions(view: View, date: IsoDate, entry: EntryView | null): EntryEditorOptions {
  return {
    date, entry, services: view.data.services, activityTypes: view.data.activityTypes,
    onDone: view.actions.changed, onCancel: view.actions.cancel,
  };
}

function entryItem(entry: EntryView, view: View): HTMLElement {
  const editing = view.editing;
  if (editing?.kind === 'entry' && editing.id === entry.id) {
    return el('li', { class: 'entry-editing' }, entryEditor(editorOptions(view, entry.date, entry)));
  }
  const activityNames = new Map(view.data.activityTypes.map((activity) => [activity.id ?? 0, activity.name]));
  const historyOpen = view.history === entry.id;
  return el('li', {},
    el('div', { class: 'entry' }, ...entryContent(entry),
      el('span', { class: 'entry-actions' },
        button(historyOpen ? 'Hide history' : 'History', () => view.actions.toggleHistory(entry.id), { 'aria-expanded': String(historyOpen) }),
        button('Edit', () => view.actions.edit({ kind: 'entry', date: entry.date, id: entry.id })))),
    historyOpen ? historyPanel(entry.id, activityNames) : null,
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

function rowClass(day: DayView, warning: boolean, today: IsoDate): string | null {
  const classes = [warning ? 'is-warning' : '', day.date === today ? 'is-today' : '', WEEKEND.has(day.weekday) ? 'is-weekend' : ''];
  return classes.filter(Boolean).join(' ') || null;
}

function dayRow(day: DayView, warning: boolean, view: View): HTMLElement {
  const editingDay = view.editing?.kind === 'day' && view.editing.date === day.date;
  const edit = editingDay ? null : button('Edit', () => view.actions.edit({ kind: 'day', date: day.date }),
    { 'aria-label': `Edit ${formatDay(day.date, day.weekday)}` });
  return el('tr', { class: rowClass(day, warning, view.today) },
    dayCell(day, warning, view.today),
    el('td', {}, day.day_type === 'work' ? null : el('span', { class: 'badge' }, DAY_TYPE_LABELS[day.day_type])),
    el('td', {}, day.start ? el('span', { class: 'num' }, `${day.start}–${day.end}`) : el('span', { class: 'muted' }, '—')),
    el('td', { class: 'num' }, day.break_time ?? '', day.break_default ? el('span', { class: 'muted' }, ' legal') : null),
    el('td', { class: 'num' }, day.worked),
    el('td', { class: 'num muted' }, day.target),
    el('td', { class: 'num' }, value(day.overtime, true)),
    el('td', { class: 'row-actions' }, edit),
  );
}

function newEntry(day: DayView, view: View): HTMLElement {
  const editing = view.editing;
  if (editing?.kind === 'entry' && editing.id === null && editing.date === day.date) {
    return el('div', { class: 'entry-editing' }, entryEditor(editorOptions(view, day.date, null)));
  }
  return button('+ Add entry', () => view.actions.edit({ kind: 'entry', date: day.date, id: null }));
}

function detailsRow(day: DayView, entries: EntryView[], className: string | null, view: View): HTMLElement {
  return el('tr', { class: ['day-details', className].filter(Boolean).join(' ') },
    el('td', { colspan: COLUMNS },
      day.note ? el('p', { class: 'day-note muted' }, day.note) : null,
      entries.length ? el('ul', { class: 'entries' }, ...entries.map((entry) => entryItem(entry, view))) : null,
      newEntry(day, view)));
}

function dayRows(day: DayView, view: View): HTMLElement[] {
  const entries = view.data.entries.get(day.date) ?? [];
  const warning = needsWarning(day, entries, view.today);
  const rows = [dayRow(day, warning, view)];
  if (view.editing?.kind === 'day' && view.editing.date === day.date) {
    rows.push(el('tr', { class: 'day-editor-row' },
      el('td', { colspan: COLUMNS }, dayEditor(day, view.actions.changed, view.actions.cancel))));
  }
  rows.push(detailsRow(day, entries, rowClass(day, warning, view.today), view));
  return rows;
}

/** Days shown: Monday to Friday, weekend days with data, and a weekend day being edited. */
export function shownDays(days: DayView[], entries: Map<IsoDate, EntryView[]>, editing: Editing): DayView[] {
  return days.filter((day) => visibleDays([day], entries).length || day.date === editing?.date);
}

function dayTable(view: View): HTMLElement {
  return el('table', { class: 'week-table' },
    el('thead', {}, el('tr', {},
      el('th', {}, 'Day'), el('th', {}, 'Type'), el('th', {}, 'Times'), el('th', { class: 'num' }, 'Break'),
      el('th', { class: 'num' }, 'Worked'), el('th', { class: 'num' }, 'Target'), el('th', { class: 'num' }, 'Overtime'),
      el('th', {}, el('span', { class: 'visually-hidden' }, 'Actions')))),
    el('tbody', {}, ...shownDays(view.data.days, view.data.entries, view.editing).flatMap((day) => dayRows(day, view))),
  );
}

function weekendLinks(view: View): HTMLElement | null {
  const hidden = view.data.days.filter((day) => !shownDays([day], view.data.entries, view.editing).length);
  if (!hidden.length) {
    return null;
  }
  return el('p', { class: 'muted week-weekend' }, 'Worked on the weekend? ',
    ...hidden.map((day) => button(`Record ${formatDay(day.date, day.weekday)}`,
      () => view.actions.edit({ kind: 'day', date: day.date }))));
}

function errorCard(error: unknown): HTMLElement {
  const message = error instanceof ApiError ? error.message : 'The week could not be loaded.';
  return el('div', { class: 'card is-warning', role: 'alert' }, message);
}

async function loadWeek(week: string): Promise<WeekData> {
  const [days, entries, report, services, activityTypes] = await Promise.all([
    api.days({ week }), api.entries({ week }), api.weekReport(week), api.services(), api.activityTypes(),
  ]);
  return { days, entries: entriesByDate(entries), report, services, activityTypes };
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
  const initialDay = editFromSearch(doc.location.search, week);
  let editing: Editing = initialDay ? { kind: 'day', date: initialDay } : null;
  let history: number | null = null;

  const draw = (): void => {
    if (!data) {
      return;
    }
    const view: View = { data, today, editing, history, actions };
    root.replaceChildren(periodSummary(data.report.totals), dayTable(view), weekendLinks(view) ?? '');
    root.querySelector<HTMLElement>('form input:not([type="radio"]):not(:disabled), form select')?.focus();
  };
  let firstLoad = true;
  const load = async (): Promise<void> => {
    try {
      data = await loadWeek(week);
      editing = firstLoad ? entryFromSearch(doc.location.search, data.entries) ?? editing : editing;
      firstLoad = false;
      draw();
    } catch (error) {
      root.replaceChildren(errorCard(error));
    }
  };
  const actions: Actions = {
    edit: (next) => {
      editing = next;
      draw();
    },
    cancel: () => {
      editing = null;
      draw();
    },
    changed: () => {
      editing = null;
      void load();
    },
    toggleHistory: (entryId) => {
      history = history === entryId ? null : entryId;
      draw();
    },
  };

  root.replaceChildren(el('p', { class: 'muted' }, 'Loading…'));
  await load();
}
