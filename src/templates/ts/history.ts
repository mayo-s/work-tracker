// The change history of an entry, as readable lines.

import { api, ApiError, type ChangeView } from './api.ts';
import { el } from './dom.ts';

const FIELD_LABELS: Record<string, string> = {
  date: 'date', ticket_key: 'ticket', activity_type_id: 'activity', duration: 'duration', description: 'description',
  note: 'note', coding: 'coding',
};
const ACTION_LABELS: Record<string, string> = {
  created: 'Created', imported: 'Imported', updated: 'Changed', renamed: 'Ticket renamed', merged: 'Ticket merged', split: 'Split',
  deleted: 'Deleted',
};

function minutes(value: number): string {
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`;
}

/** A stored value as text: durations in h:mm, dates as DD.MM.YYYY, activity type names instead of ids. */
export function formatValue(field: string, value: unknown, activityNames: Map<number, string>): string {
  if (value === null || value === undefined || value === '') {
    return '—';
  }
  if (field === 'duration' && typeof value === 'number') {
    return minutes(value);
  }
  if (field === 'date' && typeof value === 'string') {
    return value.split('-').reverse().join('.');
  }
  if (field === 'activity_type_id' && typeof value === 'number') {
    return activityNames.get(value) ?? `#${value}`;
  }
  if (typeof value === 'boolean') {
    return value ? 'yes' : 'no';
  }
  return String(value);
}

/** The changed fields of a history line: `old → new`, or only the value for created, imported and deleted. */
export function describeChanges(change: ChangeView, activityNames: Map<number, string>): string[] {
  const values = Object.values(change.changes);
  const onlyValue = ['created', 'imported', 'deleted'].includes(change.action)
    || (values.length > 0 && values.every(([before]) => before === null));  // e.g. an entry created by a split
  return Object.entries(change.changes).map(([field, [before, after]]) => {
    const label = FIELD_LABELS[field] ?? field;
    const shown = change.action === 'deleted' ? before : after;
    return onlyValue
      ? `${label}: ${formatValue(field, shown, activityNames)}`
      : `${label}: ${formatValue(field, before, activityNames)} → ${formatValue(field, after, activityNames)}`;
  });
}

/** `2026-10-28T16:47:11` → `28.10.2026 16:47` */
export function formatTimestamp(value: string): string {
  const [date = '', time = ''] = value.split('T');
  return `${date.split('-').reverse().join('.')} ${time.slice(0, 5)}`;
}

function historyItem(change: ChangeView, activityNames: Map<number, string>): HTMLElement {
  return el('li', {},
    el('span', { class: 'num muted' }, formatTimestamp(change.changed_at)), ' ',
    el('strong', {}, ACTION_LABELS[change.action] ?? change.action), ' ',
    el('span', {}, describeChanges(change, activityNames).join(' · ')),
    change.detail ? el('div', { class: 'muted' }, change.action === 'imported' ? `Original: ${change.detail}` : change.detail) : null,
  );
}

/** Loads and shows the history of an entry, oldest first. */
export function historyPanel(entryId: number, activityNames: Map<number, string>): HTMLElement {
  const panel = el('div', { class: 'history' }, el('p', { class: 'muted' }, 'Loading history…'));
  api.entryHistory(entryId).then(
    (changes) => panel.replaceChildren(el('ol', { class: 'history-list' }, ...changes.map((item) => historyItem(item, activityNames)))),
    (error: unknown) => panel.replaceChildren(el('p', { class: 'field-error' },
      error instanceof ApiError ? error.message : 'The history could not be loaded.')),
  );
  return panel;
}
