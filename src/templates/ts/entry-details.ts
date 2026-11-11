// The whole of an entry in a dialog: its day with the times, every field, the history and a link to the week.

import { api, type DayView, type EntryView } from './api.ts';
import { formatDay, weekLink } from './dates.ts';
import { ask } from './dialog.ts';
import { button, el } from './dom.ts';
import { historyPanel } from './history.ts';
import { t } from './i18n.ts';
import { DAY_TYPE_LABELS } from './labels.ts';

function describeTimes(day: DayView): string {
  if (!day.start) {
    return t('no times');
  }
  return day.end
    ? t('{start}–{end}, break {break}, worked {worked}', { start: day.start, end: day.end, break: day.break_time ?? '',
      worked: day.worked })
    : t('from {start}, no end yet', { start: day.start });
}

/** `Mon 02.03.2026 · 08:00–16:30, break 0:30, worked 8:00`; the day type unless work, e.g. `Sat 06.12.2025 · PTO · no
 * times`. */
export function describeDay(day: DayView): string {
  const type = day.holiday ?? (day.day_type === 'work' ? null : DAY_TYPE_LABELS[day.day_type]);
  return [`${formatDay(day.date, day.weekday)}${day.date.slice(0, 4)}`, type, describeTimes(day)].filter(Boolean).join(' · ');
}

/** The fields of an entry as label and value. */
export function entryFields(entry: EntryView): [string, string][] {
  return [[t('Duration'), entry.duration], [t('Activity'), entry.activity_type ?? t('No activity type')],
    [t('Ticket'), entry.ticket_key ?? (entry.ticket_required ? t('No ticket') : '—')], [t('Service'), entry.service ?? '—'],
    [t('Description'), entry.description || '—']];
}

function entryBlock(entry: EntryView, day: DayView | undefined, activityNames: Map<string, string>): HTMLElement {
  return el('section', { class: 'entry-details' },
    el('h3', {}, day ? describeDay(day) : entry.date),
    el('dl', { class: 'details-list' }, ...entryFields(entry).flatMap(([label, value]) => [el('dt', {}, label),
      el('dd', {}, value)])),
    el('strong', {}, t('History')),
    historyPanel(entry.id, activityNames),
    el('a', { href: weekLink(entry.date, `entry=${entry.id}`) }, t('Open in the week')));
}

/** Shows the whole of each entry in a dialog, once their days are
 * loaded; a button opens it, so it works with the keyboard and on touch screens. */
export async function showEntryDetails(title: string, entries: EntryView[]): Promise<void> {
  const [days, activityTypes] = await Promise.all([
    Promise.all([...new Set(entries.map((entry) => entry.date))].map((date) => api.day(date))),
    api.activityTypes(),
  ]);
  const byDate = new Map(days.map((day) => [day.date, day]));
  const names = new Map(activityTypes.map((type) => [type.id ?? '', type.name]));
  await ask(title, entries.map((entry) => entryBlock(entry, byDate.get(entry.date), names)), [], t('Close'));
}

/** "Details": opens the whole of the entries in a dialog; `fail` shows what went wrong (review, search). */
export function detailsButton(title: string, entries: EntryView[], fail: (error: unknown) => void): HTMLButtonElement {
  return button(t('Details'), () => void showEntryDetails(title, entries).catch(fail),
    { 'aria-label': t('Details of {title}', { title }) });
}
