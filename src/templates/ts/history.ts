// The change history of an entry, as readable lines.

import { api, errorText, type ChangeView } from './api.ts';
import { formatDate, formatTimestamp } from './dates.ts';
import { el } from './dom.ts';
import { fromMinutes } from './durations.ts';
import { t } from './i18n.ts';

const FIELD_LABELS: Record<string, string> = {
  date: t('date'), ticket_key: t('ticket'), activity_type_id: t('activity'), duration: t('duration'),
  description: t('description'), note: t('note'), coding: t('coding'),
};
const ACTION_LABELS: Record<string, string> = {
  created: t('Created'), imported: t('Imported'), updated: t('Changed'), renamed: t('Ticket renamed'),
  merged: t('Ticket merged'), split: t('Split'), deleted: t('Deleted'),
};

/** A stored value as text: durations in h:mm, dates as DD.MM.YYYY, activity type names instead of ids. */
export function formatValue(field: string, value: unknown, activityNames: Map<string, string>): string {
  if (value === null || value === undefined || value === '') {
    return '—';
  }
  if (field === 'duration' && typeof value === 'number') {
    return fromMinutes(value);
  }
  if (field === 'date' && typeof value === 'string') {
    return formatDate(value);
  }
  if (field === 'activity_type_id' && typeof value === 'string') {
    return activityNames.get(value) ?? t('deleted activity type');
  }
  if (typeof value === 'boolean') {
    return value ? t('yes') : t('no');
  }
  return String(value);
}

/** The changed fields of a history line: `old → new`, or only the value for created, imported and deleted. */
export function describeChanges(change: ChangeView, activityNames: Map<string, string>): string[] {
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

function historyItem(change: ChangeView, activityNames: Map<string, string>): HTMLElement {
  return el('li', {},
    el('span', { class: 'num muted' }, formatTimestamp(change.changed_at)), ' ',
    el('strong', {}, ACTION_LABELS[change.action] ?? change.action), ' ',
    el('span', {}, describeChanges(change, activityNames).join(' · ')),
    change.detail ? el('div', { class: 'muted' }, change.action === 'imported' ? t('Original: {line}', { line: change.detail }) : change.detail) : null,
  );
}

/** Loads and shows the history of an entry, oldest first. */
export function historyPanel(entryId: string, activityNames: Map<string, string>): HTMLElement {
  const panel = el('div', { class: 'history' }, el('p', { class: 'muted' }, t('Loading history…')));
  api.entryHistory(entryId).then(
    (changes) => panel.replaceChildren(el('ol', { class: 'history-list' }, ...changes.map((item) => historyItem(item, activityNames)))),
    (error: unknown) => panel.replaceChildren(el('p', { class: 'field-error' },
      errorText(error, t('The history could not be loaded.')))),
  );
  return panel;
}
