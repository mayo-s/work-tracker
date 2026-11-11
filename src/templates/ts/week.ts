// Week view (/week): the days of a week with times, balance and task entries; a table, on phones a card per day.

import {
  api, errorText, type ActivityType, type DayView, type EntryView, type PeriodTotals, type ServiceChoice, type WeekReport,
  type WorkMode,
} from './api.ts';
import { addDays, formatDate, formatDay, isoDate, isoWeek, isValidWeek, mondayOf, shiftWeek, type IsoDate } from './dates.ts';
import { clockedInput, dayEditor } from './day-editor.ts';
import { daysOffForm } from './days-off.ts';
import { ask } from './dialog.ts';
import { button, el, PHONE, scrolling } from './dom.ts';
import { entryEditor, type EntryEditorOptions } from './entry-editor.ts';
import { historyPanel } from './history.ts';
import { decimal, t } from './i18n.ts';
import { DAY_TYPE_LABELS } from './labels.ts';
import { viewedMember, withMember } from './team-view.ts';

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

/** Work days of the schedule always; other days (e.g. weekends) only if something was recorded. */
export function visibleDays(days: DayView[], entries: Map<IsoDate, EntryView[]>): DayView[] {
  return days.filter((day) => day.work_day || day.recorded || entries.has(day.date));
}

/** A past work day of the schedule, of type work, without any entry (in the team view only days in the team); not in
 * "Times only", which records no entries. */
export function needsWarning(day: DayView, entries: EntryView[], today: IsoDate, mode: WorkMode): boolean {
  return mode !== 'times' && day.date < today && day.day_type === 'work' && day.work_day && entries.length === 0
    && day.in_team !== false;
}

/** A past day with a start but no end; today's may still be running. */
export function leftOpen(day: DayView, today: IsoDate): boolean {
  return Boolean(day.start) && !day.end && day.date < today;
}

/** What "now" would set on the day: the start of today while it has none, its end while it is open. */
export function clockField(day: DayView, today: IsoDate): 'start' | 'end' | null {
  if (day.date !== today || (day.start && day.end)) {
    return null;
  }
  return day.start ? 'end' : 'start';
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

/** The entry to open for editing from `?entry=<id>`, if it is an entry of the shown week. */
export function entryFromSearch(search: string, entries: Map<IsoDate, EntryView[]>): Editing {
  const id = new URLSearchParams(search).get('entry');
  const entry = [...entries.values()].flat().find((item) => item.id === id);
  return entry ? { kind: 'entry', date: entry.date, id: entry.id } : null;
}

/** A duration as warning (negative), in mint (positive) or plain (zero). */
/** The day type as shown; a company half day says that it takes half a PTO day by itself:
 * `Company half day · 0.5 PTO (half free)`. */
export function dayTypeLabel(day: Pick<DayView, 'day_type' | 'pto_days'>): string {
  const label = DAY_TYPE_LABELS[day.day_type];
  return day.day_type === 'company_half_day' && day.pto_days
    ? t('{type} · {days} PTO (half free)', { type: label, days: decimal(day.pto_days) }) : label;
}

export function value(duration: string, withSign = false): HTMLElement {
  return el('span', { class: `num ${valueClass(duration)}`.trim() }, withSign ? signed(duration) : duration);
}

/** A shown week, month or year: its title and first day, the link to the period `shift` periods away, the link to
 * the period of a date, and whether it is the current period. */
export type Period = {
  title: string; start: IsoDate; shifted: (shift: number) => string; of: (date: IsoDate) => string; current: boolean;
};

/** The header of the week, month or year page (`page`): its title, the links to the period before and after, the
 * link to the current period (disabled while that is shown), and the date field whose "Go" opens the period of the
 * date, starting at the shown period's first day; in the team view the member is kept. */
export function periodHeader(doc: Document, page: string, period: Period): void {
  doc.querySelector(`#${page}-title`)!.textContent = period.title;
  doc.querySelector<HTMLAnchorElement>(`#${page}-previous`)!.href = period.shifted(-1);
  doc.querySelector<HTMLAnchorElement>(`#${page}-next`)!.href = period.shifted(1);
  doc.querySelector<HTMLAnchorElement>(`#${page}-current`)!.toggleAttribute('aria-disabled', period.current);
  const date = doc.querySelector<HTMLInputElement>(`#${page}-go-date`)!;
  date.value = period.start;
  doc.querySelector(`#${page}-go`)!.addEventListener('submit', (event) => {
    event.preventDefault();
    const href = period.of(date.value);
    const member = viewedMember(doc.location.search);
    doc.location.assign(member ? withMember(href, member) : href);
  });
}

function renderHeader(doc: Document, week: string, today: IsoDate): void {
  const monday = mondayOf(week);
  const [year, number] = week.split('-W');
  periodHeader(doc, 'week', {
    title: t('Week {number} · {year}', { number: Number(number), year: year ?? '' }), start: monday, shifted: (shift) => `/week?week=${shiftWeek(week, shift)}`,
    of: (date) => `/week?week=${isoWeek(date)}`, current: week === isoWeek(today),
  });
  doc.querySelector('#week-period')!.textContent = `${formatDate(monday)} – ${formatDate(addDays(monday, 6))}`;
}

/** Worked of target, overtime and balance of a week, month or year (shared by the week view and the reports), then
 * the `extra` lines of the page. */
export function periodSummary(totals: PeriodTotals, ...extra: (HTMLElement | null)[]): HTMLElement {
  return el('div', { class: 'card card-surface week-summary' },
    el('div', {}, el('span', { class: 'muted' }, `${t('Worked')} `), el('span', { class: 'num' }, totals.worked),
      el('span', { class: 'muted' }, ` ${t('of')} `), el('span', { class: 'num' }, totals.target)),
    el('div', {}, el('span', { class: 'muted' }, `${t('Overtime')} `), value(totals.overtime, true)),
    el('div', {}, el('span', { class: 'muted' }, `${t('Balance')} `), value(totals.balance_in),
      el('span', { class: 'muted' }, ' → '), value(totals.balance_out)),
    totals.until && totals.until < totals.end
      ? el('div', { class: 'muted' }, t('counted up to {date}', { date: formatDate(totals.until) })) : null,
    ...extra,
  );
}

/** `Entries 152:30 of 160:00 worked`: the hours in entries next to the hours worked by the day times (month, year). */
export function entriesOfWorked(entries: string, totals: PeriodTotals): HTMLElement {
  return el('div', {}, el('span', { class: 'muted' }, `${t('Entries')} `), el('span', { class: 'num' }, entries),
    el('span', { class: 'muted' }, ` ${t('of')} `), el('span', { class: 'num' }, totals.worked),
    el('span', { class: 'muted' }, ` ${t('worked')}`));
}

type WeekData = {
  days: DayView[]; entries: Map<IsoDate, EntryView[]>; report: WeekReport; services: ServiceChoice[];
  activityTypes: ActivityType[]; workMode: WorkMode;
};
/** What is open: the form of a day, of an entry (id) or of a new entry (null) on a date, or nothing. */
export type Editing = { kind: 'day'; date: IsoDate } | { kind: 'entry'; date: IsoDate; id: string | null } | null;
/** `readOnly`: the team view of a member's week (no editing, no history). */
type View = {
  data: WeekData; today: IsoDate; editing: Editing; history: string | null; actions: Actions; readOnly: boolean;
};
type Actions = {
  edit: (editing: Editing) => void; cancel: () => void; changed: () => void; toggleHistory: (entryId: string) => void;
  clock: (day: DayView, name: 'start' | 'end') => void;
};

const COLUMNS = 8;

/** The key of the button that opens a form (`data-opens`), so focus can return to it when the form closes. */
export function openerKey(editing: Editing): string | null {
  if (!editing) {
    return null;
  }
  return editing.kind === 'day' ? `day-${editing.date}` : editing.id === null ? `add-${editing.date}` : `entry-${editing.id}`;
}

/** The name an entry is listed by: its ticket (or "No ticket" where its activity type requires one), otherwise its
 * activity type; then the activity type of an entry on a ticket. */
function entryLabel(entry: EntryView): (HTMLElement | null)[] {
  const activity = entry.activity_type ?? t('No activity type');
  if (!entry.ticket_key && !entry.ticket_required) {
    return [el('strong', { class: entry.activity_type ? '' : 'value-negative' }, activity)];
  }
  return [el('strong', { class: entry.ticket_key ? '' : 'value-negative' }, entry.ticket_key ?? t('No ticket')),
    el('span', { class: entry.activity_type ? 'badge positive' : 'badge warning' }, activity)];
}

/** Duration, ticket and activity type, service, text and badges of an entry (also used by the review page). */
export function entryContent(entry: EntryView): (HTMLElement | null)[] {
  return [
    el('span', { class: entry.duration === '0:00' ? 'num value-negative' : 'num', title: entry.duration === '0:00'
      ? t('No duration yet') : null }, entry.duration),
    ...entryLabel(entry),
    entry.service ? el('span', { class: 'badge' }, entry.service) : null,
    entry.description ? el('span', { class: 'entry-text' }, entry.description) : null,
    entry.changed ? el('span', { class: 'badge', title: t('Changed after it was created or imported') }, t('changed')) : null,
  ];
}

function editorOptions(view: View, date: IsoDate, entry: EntryView | null): EntryEditorOptions {
  return {
    date, entry, dayStart: view.data.days.find((day) => day.date === date)?.start ?? null,
    services: view.data.services, activityTypes: view.data.activityTypes, workMode: view.data.workMode,
    onDone: view.actions.changed, onCancel: view.actions.cancel,
  };
}

function entryItem(entry: EntryView, view: View): HTMLElement {
  const editing = view.editing;
  if (editing?.kind === 'entry' && editing.id === entry.id) {
    return el('li', { class: 'entry-editing' }, entryEditor(editorOptions(view, entry.date, entry)));
  }
  if (view.readOnly) {
    return el('li', {}, el('div', { class: 'entry' }, ...entryContent(entry)));
  }
  const activityNames = new Map(view.data.activityTypes.map((activity) => [activity.id ?? '', activity.name]));
  const historyOpen = view.history === entry.id;
  return el('li', {},
    el('div', { class: 'entry' }, ...entryContent(entry),
      el('span', { class: 'entry-actions' },
        button(historyOpen ? t('Hide history') : t('History'), () => view.actions.toggleHistory(entry.id),
          { 'aria-expanded': String(historyOpen) }),
        button(t('Edit'), () => view.actions.edit({ kind: 'entry', date: entry.date, id: entry.id }),
          { 'data-opens': `entry-${entry.id}` }))),
    historyOpen ? historyPanel(entry.id, activityNames) : null,
  );
}

/** The holiday and the warnings of a day, under its date. */
function dayNotes(day: DayView, warnings: string[]): (HTMLElement | null)[] {
  return [day.holiday ? el('div', { class: 'muted' }, day.holiday) : null,
    ...warnings.map((warning) => el('div', {}, el('span', { class: 'badge warning' }, warning)))];
}

function dayCell(day: DayView, warnings: string[], today: IsoDate): HTMLElement {
  return el('td', {},
    day.date === today ? el('strong', {}, formatDay(day.date, day.weekday)) : formatDay(day.date, day.weekday),
    ...dayNotes(day, warnings),
  );
}

/** "Start now" or "End now" on today's row, saved at once; not while a form is open, as saving redraws the page. */
function clockButton(day: DayView, view: View): HTMLElement | null {
  const name = view.readOnly || view.editing ? null : clockField(day, view.today);
  return name && button(name === 'start' ? t('Start now') : t('End now'), () => view.actions.clock(day, name),
    { class: 'button-small primary clock-button', 'data-opens': `clock-${day.date}` });
}

/** Start and end; an open day shows the end that meets its target instead, and today "Start now" or "End now". */
function times(day: DayView, view: View): (HTMLElement | null)[] {
  const clock = clockButton(day, view);
  if (!day.start) {
    return [el('span', { class: 'muted' }, '—'), clock];
  }
  return day.end ? [el('span', { class: 'num' }, `${day.start}–${day.end}`)]
    : [el('span', { class: 'num' }, `${day.start}–`), day.best_end ? el('span',
      { class: 'num muted', title: t('The end that meets the target, without overtime or loss') },
      ` ${t('best {time}', { time: day.best_end })}`) : null, clock];
}

/** The break; `legal` when it is the legal minimum, as none was entered. */
function breakTime(day: DayView): (HTMLElement | string)[] {
  return [day.break_time ?? '', day.break_default ? el('span', { class: 'muted' }, ` ${t('legal')}`) : ''];
}

function typeBadge(day: DayView): HTMLElement | null {
  return day.day_type === 'work' ? null : el('span', { class: 'badge' }, dayTypeLabel(day));
}

function editDayButton(day: DayView, view: View): HTMLElement | null {
  const editingDay = view.editing?.kind === 'day' && view.editing.date === day.date;
  return editingDay || view.readOnly ? null : button(t('Edit'), () => view.actions.edit({ kind: 'day', date: day.date }),
    { 'aria-label': t('Edit {day}', { day: formatDay(day.date, day.weekday) }), 'data-opens': `day-${day.date}` });
}

function rowClass(day: DayView, warning: boolean, today: IsoDate): string | null {
  const classes = [warning ? 'is-warning' : '', day.date === today ? 'is-today' : '', day.work_day ? '' : 'is-weekend'];
  return classes.filter(Boolean).join(' ') || null;
}

/** A day before the member joined the team (team view): no data. */
function outsideTeamRow(day: DayView, view: View): HTMLElement {
  return el('tr', { class: rowClass(day, false, view.today) },
    dayCell(day, [], view.today),
    el('td', { colspan: COLUMNS - 1 }, el('span', { class: 'muted' }, t('Not in this team'))));
}

function dayRow(day: DayView, warnings: string[], view: View): HTMLElement {
  if (day.in_team === false) {
    return outsideTeamRow(day, view);
  }
  return el('tr', { class: rowClass(day, warnings.length > 0, view.today) },
    dayCell(day, warnings, view.today),
    el('td', {}, typeBadge(day)),
    el('td', {}, ...times(day, view)),
    el('td', { class: 'num' }, ...breakTime(day)),
    el('td', { class: 'num' }, day.worked),
    el('td', { class: 'num muted' }, day.target),
    el('td', { class: 'num' }, value(day.overtime, true)),
    el('td', { class: 'row-actions' }, editDayButton(day, view)),
  );
}

/** The form of a new entry, or the button that opens it. */
function newEntry(day: DayView, view: View): HTMLElement {
  const editing = view.editing;
  if (editing?.kind === 'entry' && editing.id === null && editing.date === day.date) {
    return el('div', { class: 'entry-editing' }, entryEditor(editorOptions(view, day.date, null)));
  }
  return button(t('+ Add entry'), () => view.actions.edit({ kind: 'entry', date: day.date, id: null }),
    { 'data-opens': `add-${day.date}` });
}

/** The note, the entries and "+ Add entry" of a day. */
function details(day: DayView, entries: EntryView[], view: View): (HTMLElement | null)[] {
  return [day.note ? el('p', { class: 'day-note muted' }, day.note) : null,
    entries.length ? el('ul', { class: 'entries' }, ...entries.map((entry) => entryItem(entry, view))) : null,
    view.readOnly ? null : newEntry(day, view)];
}

function detailsRow(day: DayView, entries: EntryView[], className: string | null, view: View): HTMLElement {
  return el('tr', { class: ['day-details', className].filter(Boolean).join(' ') },
    el('td', { colspan: COLUMNS }, ...details(day, entries, view)));
}

/** A day's entries and warnings: "No entries" on a past work day without any, "No end" on a past open day. */
function dayState(day: DayView, view: View): { entries: EntryView[]; warnings: string[] } {
  const entries = view.data.entries.get(day.date) ?? [];
  return { entries, warnings: [needsWarning(day, entries, view.today, view.data.workMode) ? t('No entries') : '',
    leftOpen(day, view.today) ? t('No end') : ''].filter(Boolean) };
}

function openDayEditor(day: DayView, view: View): HTMLElement | null {
  return view.editing?.kind === 'day' && view.editing.date === day.date
    ? dayEditor(day, view.actions.changed, view.actions.cancel) : null;
}

function dayRows(day: DayView, view: View): HTMLElement[] {
  const { entries, warnings } = dayState(day, view);
  const rows = [dayRow(day, warnings, view)];
  const editor = openDayEditor(day, view);
  if (editor) {
    rows.push(el('tr', { class: 'day-editor-row' }, el('td', { colspan: COLUMNS }, editor)));
  }
  if (!view.readOnly || entries.length) {
    rows.push(detailsRow(day, entries, rowClass(day, warnings.length > 0, view.today), view));
  }
  return rows;
}

/** On phones (SPEC 5.5a) a day is a card: its date, type and "Edit"; times and break; worked, target and overtime;
 * then the open form, the note, the entries and "+ Add entry". */
function dayCard(day: DayView, view: View): HTMLElement {
  const { entries, warnings } = dayState(day, view);
  const title = el('div', { class: 'day-card-title' }, el('h2', {}, formatDay(day.date, day.weekday)), ...dayNotes(day, warnings));
  const className = ['card day-card', rowClass(day, warnings.length > 0, view.today)].filter(Boolean).join(' ');
  if (day.in_team === false) {
    return el('li', { class: className }, title, el('p', { class: 'muted' }, t('Not in this team')));
  }
  const label = (text: string): HTMLElement => el('span', { class: 'muted' }, `${text} `);
  return el('li', { class: className },
    el('div', { class: 'day-card-head' }, title, typeBadge(day), editDayButton(day, view)),
    // the spaces between the parts are for screen readers and copied text; the layout spaces them itself
    el('p', { class: 'day-card-line' }, el('span', {}, label(t('Times')), ...times(day, view)),
      ...(day.break_time ? [' ', el('span', {}, label(t('Break')), el('span', { class: 'num' }, ...breakTime(day)))] : [])),
    el('p', { class: 'day-card-line' }, el('span', {}, label(t('Worked')), el('span', { class: 'num' }, day.worked)), ' ',
      el('span', {}, label(t('Target')), el('span', { class: 'num' }, day.target)), ' ',
      el('span', {}, label(t('Overtime')), value(day.overtime, true))),
    openDayEditor(day, view),
    ...(view.readOnly && !entries.length ? [] : details(day, entries, view)),
  );
}

function dayCards(view: View): HTMLElement {
  return el('ol', { class: 'day-cards', 'aria-label': t('Days') },
    ...shownDays(view.data.days, view.data.entries, view.editing).map((day) => dayCard(day, view)));
}

/** Days shown: work days, other days with data, and another day being edited. */
export function shownDays(days: DayView[], entries: Map<IsoDate, EntryView[]>, editing: Editing): DayView[] {
  return days.filter((day) => visibleDays([day], entries).length || day.date === editing?.date);
}

function dayTable(view: View): HTMLElement {
  return scrolling(el('table', { class: 'week-table' },
    el('thead', {}, el('tr', {},
      el('th', {}, t('Day')), el('th', {}, t('Type')), el('th', {}, t('Times')), el('th', { class: 'num' }, t('Break')),
      el('th', { class: 'num' }, t('Worked')), el('th', { class: 'num' }, t('Target')),
      el('th', { class: 'num' }, t('Overtime')), el('th', {}, el('span', { class: 'visually-hidden' }, t('Actions'))))),
    el('tbody', {}, ...shownDays(view.data.days, view.data.entries, view.editing).flatMap((day) => dayRows(day, view))),
  ));
}

function weekendLinks(view: View): HTMLElement | null {
  const hidden = view.data.days.filter((day) => !shownDays([day], view.data.entries, view.editing).length);
  if (!hidden.length || view.readOnly) {
    return null;
  }
  return el('p', { class: 'muted week-weekend' }, `${t('Worked on a day off?')} `,
    ...hidden.map((day) => button(t('Record {day}', { day: formatDay(day.date, day.weekday) }),
      () => view.actions.edit({ kind: 'day', date: day.date }), { 'data-opens': `day-${day.date}` })));
}

function errorCard(error: unknown): HTMLElement {
  const message = errorText(error, t('The week could not be loaded.'));
  return el('div', { class: 'card is-warning', role: 'alert' }, message);
}

/** The week of the user, or in the team view of the member (without the lists to choose from, as nothing is edited);
 * its report brings the way of working of whose week it is. */
async function loadWeek(week: string, member: string | null): Promise<WeekData> {
  const [days, entries, report, services, activityTypes] = await Promise.all([
    api.days({ week }, member), api.entries({ week }, member), api.weekReport(week, member),
    member ? [] : api.serviceChoices(), member ? [] : api.activityTypes(),
  ]);
  return { days, entries: entriesByDate(entries), report, services, activityTypes, workMode: report.work_mode };
}

export async function renderWeekPage(doc: Document): Promise<void> {
  const root = doc.querySelector<HTMLElement>('#week');
  if (!root) {
    return;
  }
  const today = isoDate(new Date());
  const week = weekFromSearch(doc.location.search, today);
  const member = viewedMember(doc.location.search);
  renderHeader(doc, week, today);
  let data: WeekData | null = null;
  const initialDay = member ? null : editFromSearch(doc.location.search, week);
  let editing: Editing = initialDay ? { kind: 'day', date: initialDay } : null;
  let history: string | null = null;
  let returnFocus: { key: string | null; date: IsoDate } | null = null;  // the opener of the form that just closed

  const draw = (): void => {
    if (!data) {
      return;
    }
    const view: View = { data, today, editing, history, actions, readOnly: member !== null };
    root.replaceChildren(periodSummary(data.report.totals), phone.matches ? dayCards(view) : dayTable(view),
      weekendLinks(view) ?? '');
    const form = root.querySelector<HTMLElement>('form input:not([type="radio"]):not(:disabled), form select');
    const opener = returnFocus && (root.querySelector<HTMLElement>(`[data-opens="${returnFocus.key}"]`)
      ?? root.querySelector<HTMLElement>(`[data-opens="add-${returnFocus.date}"]`));  // e.g. after deleting an entry
    returnFocus = null;
    (form ?? opener)?.focus();
  };
  const close = (): void => {
    returnFocus = editing ? { key: openerKey(editing), date: editing.date } : null;
    editing = null;
  };
  let firstLoad = true;
  const load = async (): Promise<void> => {
    try {
      data = await loadWeek(week, member);
      editing = firstLoad && !member ? entryFromSearch(doc.location.search, data.entries) ?? editing : editing;
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
      close();
      draw();
    },
    changed: () => {
      close();
      void load();
    },
    toggleHistory: (entryId) => {
      history = history === entryId ? null : entryId;
      draw();
    },
    clock: (day, name) => {
      const input = clockedInput(day, name, new Date());
      if (!input) {
        doc.location.reload();  // the page stayed open past midnight: show the new day, and write nothing on the old one
        return;
      }
      api.saveDay(day.date, input).then(() => {
        returnFocus = { key: `clock-${day.date}`, date: day.date };
        return load();
      }, (error: unknown) => ask(t('The time was not saved'), [errorText(error)], [], t('Close')));
    },
  };

  // Cards on phones, the table on wider screens; a turned phone keeps an open form as it is, until it closes
  const phone = doc.defaultView!.matchMedia(PHONE);
  phone.addEventListener('change', () => {
    if (!editing) {
      draw();
    }
  });
  if (member) {
    doc.querySelector('#week-book-days-off')?.remove();  // nothing is booked in the team view
  } else {
    wireDaysOff(doc, mondayOf(week));
  }
  root.replaceChildren(el('p', { class: 'muted' }, t('Loading…')));
  await load();
}

/** The "Book days off" button opens and closes the form above the week, starting on the week's Monday. */
function wireDaysOff(doc: Document, monday: IsoDate): void {
  const button = doc.querySelector<HTMLButtonElement>('#week-book-days-off');
  const container = doc.querySelector<HTMLElement>('#days-off');
  if (!button || !container) {
    return;
  }
  const close = (): void => {
    container.replaceChildren();
    button.setAttribute('aria-expanded', 'false');
    button.focus();
  };
  button.addEventListener('click', () => {
    if (container.childElementCount) {
      close();
    } else {
      container.replaceChildren(daysOffForm(monday, close));
      button.setAttribute('aria-expanded', 'true');
    }
  });
}
