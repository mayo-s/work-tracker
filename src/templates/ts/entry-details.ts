// The whole of an entry in a dialog: its day with the times, every field, the flags, the history and a link to the week.

import { api, type DayView, type EntryView } from './api.ts';
import { formatDay, weekLink } from './dates.ts';
import { ask } from './dialog.ts';
import { button, el } from './dom.ts';
import { historyPanel } from './history.ts';
import { DAY_TYPE_LABELS } from './labels.ts';

/** `Mon 02.03.2026 · 08:00–16:30, break 0:30, worked 8:00`; the day type unless work, e.g. `Sat 06.12.2025 · PTO · no
 * times`. */
export function describeDay(day: DayView): string {
  const type = day.holiday ?? (day.day_type === 'work' ? null : DAY_TYPE_LABELS[day.day_type]);
  const times = day.start && day.end ? `${day.start}–${day.end}, break ${day.break_time}, worked ${day.worked}` : 'no times';
  return [`${formatDay(day.date, day.weekday)}${day.date.slice(0, 4)}`, type, times].filter(Boolean).join(' · ');
}

/** The fields of an entry as label and value. */
export function entryFields(entry: EntryView): [string, string][] {
  const common: [string, string][] = [['Duration', entry.duration]];
  if (entry.kind === 'activity') {
    return [...common, ['Activity', entry.activity_type ?? '—'], ['Note', entry.note || '—']];
  }
  return [...common, ['Ticket', entry.ticket_key ?? 'No ticket'], ['Service', entry.service ?? '—'],
    ['Coding', entry.coding ? 'Yes' : 'No'], ['Description', entry.description || '—']];
}

function entryBlock(entry: EntryView, day: DayView | undefined, activityNames: Map<string, string>): HTMLElement {
  return el('section', { class: 'entry-details' },
    el('h3', {}, day ? describeDay(day) : entry.date),
    el('dl', { class: 'details-list' }, ...entryFields(entry).flatMap(([label, value]) => [el('dt', {}, label),
      el('dd', {}, value)])),
    entry.flags.length ? el('div', {}, el('strong', {}, 'To review'),
      el('ul', { class: 'details-flags' }, ...entry.flags.map((flag) => el('li', {}, flag.detail || flag.reason)))) : null,
    el('strong', {}, 'History'),
    historyPanel(entry.id, activityNames),
    el('a', { href: weekLink(entry.date, `entry=${entry.id}`) }, 'Open in the week'));
}

/** Shows the whole of each entry (one, or e.g. all entries of a guessed ticket) in a dialog, once their days are
 * loaded; a button opens it, so it works with the keyboard and on touch screens. */
export async function showEntryDetails(title: string, entries: EntryView[]): Promise<void> {
  const [days, activityTypes] = await Promise.all([
    Promise.all([...new Set(entries.map((entry) => entry.date))].map((date) => api.day(date))),
    api.activityTypes(),
  ]);
  const byDate = new Map(days.map((day) => [day.date, day]));
  const names = new Map(activityTypes.map((type) => [type.id ?? '', type.name]));
  await ask(title, entries.map((entry) => entryBlock(entry, byDate.get(entry.date), names)), [], 'Close');
}

/** "Details": opens the whole of the entries in a dialog; `fail` shows what went wrong (review, search). */
export function detailsButton(title: string, entries: EntryView[], fail: (error: unknown) => void): HTMLButtonElement {
  return button('Details', () => void showEntryDetails(title, entries).catch(fail), { 'aria-label': `Details of ${title}` });
}
